"""Unified Ingestion Engine for Incubrix.

Accepts:
1. Blog URL or local text/markdown/json file
2. Podcast, audio, or video file (transcribed via Groq Whisper with FFmpeg chunking)
3. Pasted raw demo script

Outputs a normalized JSON document:
{
  "title": str,
  "source_type": "url" | "text_file" | "pasted_script" | "audio_file" | "video_file",
  "text": str,
  "segments": [
    {"id": int, "start": float, "end": float, "text": str}
  ]
}
"""

from __future__ import annotations

from enum import Enum
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
from pydantic import BaseModel, Field
import requests

from src.config import get_settings
from src.logging.logger import get_logger
from src.transcribe import GroqTranscriber, IngestedDocument, Segment

logger = get_logger("ingest")

TEXT_EXTENSIONS = {".txt"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
JSON_EXTENSIONS = {".json"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


# Backward-compatible enum & models
class ContentType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    AUDIO = "audio"
    VIDEO = "video"


class IngestPayload(BaseModel):
    """Legacy normalized payload for existing pipeline integrations."""

    source_path: Path
    content_type: ContentType
    file_name: str
    file_size_bytes: int
    content_hash: str
    raw_text: Optional[str] = None
    media_path: Optional[Path] = None
    duration_seconds: Optional[float] = None
    word_count: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def clean_html_to_text(html_content: str) -> tuple[str, str]:
    """Extract clean title and body text from HTML markup."""
    # 1. Extract <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    if not title:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_content, re.IGNORECASE | re.DOTALL)
        title = h1_match.group(1).strip() if h1_match else "Web Article"

    # Clean HTML tags inside title
    title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()

    # 2. Strip scripts, styles, nav, footer, header
    clean = re.sub(r"<(script|style|nav|footer|header|aside)[^>]*>.*?</\1>", " ", html_content, flags=re.DOTALL | re.IGNORECASE)

    # 3. Strip tags and unescape entities
    text = re.sub(r"<[^>]+>", " ", clean)
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

    return title, text


def segment_text_by_sentences(text: str, words_per_minute: int = 150) -> List[Segment]:
    """Generate sequential timestamped segments from text based on speech cadence."""
    raw_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not raw_sentences:
        raw_sentences = [text] if text else []

    segments: List[Segment] = []
    current_time = 0.0
    words_per_second = max(1.0, words_per_minute / 60.0)

    for idx, sentence in enumerate(raw_sentences):
        word_count = max(1, len(sentence.split()))
        duration = round(word_count / words_per_second, 2)
        end_time = round(current_time + duration, 2)

        segments.append(
            Segment(
                id=idx,
                start=round(current_time, 2),
                end=end_time,
                text=sentence,
            )
        )
        current_time = end_time

    return segments


class IngestManager:
    """Universal ingestion manager accepting URLs, files, or pasted scripts."""

    def __init__(self, transcriber: Optional[GroqTranscriber] = None) -> None:
        self.settings = get_settings()
        self.transcriber = transcriber or GroqTranscriber()

    def ingest_url(self, url: str) -> IngestedDocument:
        """Fetch and extract readable text and title from a web URL."""
        logger.info(f"Ingesting blog/web article from URL: {url}")
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError(f"Invalid URL provided: {url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 IncuBrix/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch content from URL '{url}': {e}")
            raise RuntimeError(f"Could not retrieve blog URL ({url}): {e}") from e

        title, clean_text = clean_html_to_text(resp.text)
        if not clean_text or len(clean_text) < 20:
            raise ValueError(f"URL did not contain sufficient textual content: {url}")

        segments = segment_text_by_sentences(clean_text)
        logger.info(f"Successfully ingested URL: '{title}' ({len(clean_text.split())} words, {len(segments)} segments)")

        return IngestedDocument(
            title=title,
            source_type="url",
            text=clean_text,
            segments=segments,
        )

    def ingest_text_file(self, file_path: Path) -> IngestedDocument:
        """Ingest local text, markdown, or JSON document."""
        logger.info(f"Ingesting local text file: {file_path.name}")
        path = file_path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        title = path.stem.replace("_", " ").title()

        if suffix in JSON_EXTENSIONS:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                title = data.get("title") or title
                text = data.get("text") or data.get("content") or data.get("script") or json.dumps(data, indent=2)
            else:
                text = json.dumps(data, indent=2)
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read().strip()

            # Attempt to extract markdown title from # Heading
            first_line = raw_content.splitlines()[0] if raw_content.splitlines() else ""
            if first_line.startswith("#"):
                title = re.sub(r"^#+\s*", "", first_line).strip()
            text = raw_content

        segments = segment_text_by_sentences(text)
        logger.info(f"Ingested text file '{title}': {len(text.split())} words, {len(segments)} segments")

        return IngestedDocument(
            title=title,
            source_type="text_file",
            text=text,
            segments=segments,
        )

    def ingest_pasted_script(self, raw_script: str, title: Optional[str] = None) -> IngestedDocument:
        """Ingest pasted demo script or raw text."""
        cleaned = raw_script.strip()
        if not cleaned:
            raise ValueError("Pasted demo script is empty.")

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        first_line = lines[0] if lines else "Demo Script"
        doc_title = title or (re.sub(r"^#+\s*", "", first_line)[:50] if first_line else "Pasted Demo Script")

        segments = segment_text_by_sentences(cleaned)
        logger.info(f"Ingested pasted demo script '{doc_title}': {len(cleaned.split())} words, {len(segments)} segments")

        return IngestedDocument(
            title=doc_title,
            source_type="pasted_script",
            text=cleaned,
            segments=segments,
        )

    def ingest(self, source: Union[str, Path], title: Optional[str] = None) -> IngestedDocument:
        """Main entry point: detects URL, file path, media, or pasted script."""
        str_source = str(source).strip()

        # 1. Check if source is a URL
        if str_source.startswith("http://") or str_source.startswith("https://"):
            return self.ingest_url(str_source)

        # 2. Check if source is an existing file path
        path = Path(str_source)
        if path.exists() and path.is_file():
            suffix = path.suffix.lower()
            if suffix in (AUDIO_EXTENSIONS | VIDEO_EXTENSIONS):
                # Audio or Video file -> FFmpeg extraction + Groq Whisper transcription
                return self.transcriber.transcribe_media(path, title=title)
            elif suffix in (TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | JSON_EXTENSIONS):
                return self.ingest_text_file(path)
            else:
                # Default to reading as text file
                return self.ingest_text_file(path)

        # 3. Check if source is a multi-line pasted script or text string
        if "\n" in str_source or len(str_source.split()) >= 3:
            return self.ingest_pasted_script(str_source, title=title)

        # 4. If path was intended but does not exist
        if "." in str_source and not str_source.startswith(("#", "-", "*")):
            raise FileNotFoundError(f"Input file not found: {str_source}")

        # Fallback to pasted script
        return self.ingest_pasted_script(str_source, title=title)

    # --------------------------------------------------------------------------
    # Backward-compatible methods for existing pipeline
    # --------------------------------------------------------------------------
    def compute_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file for integrity and deduplication."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def detect_type(self, path: Path) -> ContentType:
        """Determine ContentType from file suffix."""
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:
            return ContentType.TEXT
        elif suffix in MARKDOWN_EXTENSIONS:
            return ContentType.MARKDOWN
        elif suffix in JSON_EXTENSIONS:
            return ContentType.JSON
        elif suffix in AUDIO_EXTENSIONS:
            return ContentType.AUDIO
        elif suffix in VIDEO_EXTENSIONS:
            return ContentType.VIDEO
        return ContentType.TEXT

    def load(self, source: Union[str, Path]) -> IngestPayload:
        """Backward-compatible loader returning IngestPayload."""
        path = Path(source).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Input file does not exist: {path}")

        file_size = path.stat().st_size
        content_hash = self.compute_hash(path)
        content_type = self.detect_type(path)

        raw_text = None
        media_path = None
        duration_sec = None
        word_count = None
        metadata: Dict[str, Any] = {}

        if content_type in (ContentType.TEXT, ContentType.MARKDOWN):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read().strip()
            word_count = len(raw_text.split())
        elif content_type == ContentType.JSON:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_text = data.get("text") or data.get("content") or json.dumps(data)
            word_count = len(raw_text.split())
        elif content_type in (ContentType.AUDIO, ContentType.VIDEO):
            media_path = path

        return IngestPayload(
            source_path=path,
            content_type=content_type,
            file_name=path.name,
            file_size_bytes=file_size,
            content_hash=content_hash,
            raw_text=raw_text,
            media_path=media_path,
            duration_seconds=duration_sec,
            word_count=word_count,
            metadata=metadata,
        )


# Backward compatibility aliasing for legacy imports
sys.modules["src.ingest.loader"] = sys.modules[__name__]
sys.modules["src.ingest.models"] = sys.modules[__name__]
