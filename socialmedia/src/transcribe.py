"""Audio and video transcription powered by Groq Whisper-large-v3.

Features:
- Extracts audio tracks from video or audio containers using FFmpeg.
- Automatically splits oversized audio files into chunks under Groq's 25MB limit.
- Transcribes each chunk with Groq Whisper API (whisper-large-v3) with timestamps.
- Merges chunks into a unified transcript with continuous segment offsets.
- Outputs a normalized document schema: {title, source_type, text, segments[]}.
"""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple
from groq import Groq
import imageio_ffmpeg
from pydantic import BaseModel, Field

from src.config import get_settings
from src.logging.logger import get_logger

logger = get_logger("transcribe")

# Groq hard file size limit is 25MB; keep chunks under 24MB for safe margin
GROQ_MAX_FILE_BYTES = 24 * 1024 * 1024  # 24 MB


class Segment(BaseModel):
    """Timestamped segment in a transcript."""

    id: int
    start: float
    end: float
    text: str


class IngestedDocument(BaseModel):
    """Normalized document output across all media and text ingestion sources."""

    title: str
    source_type: str
    text: str
    segments: List[Segment] = Field(default_factory=list)


# Backward-compatible model aliases
class TranscriptSegment(Segment):
    pass


class TranscriptionResult(BaseModel):
    text: str
    language: Optional[str] = "en"
    duration: Optional[float] = None
    segments: List[TranscriptSegment] = Field(default_factory=list)
    raw_response: Dict[str, Any] = Field(default_factory=dict)


def get_ffmpeg_executable() -> str:
    """Find the best available FFmpeg executable."""
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        logger.error(f"FFmpeg binary discovery failed: {e}")
        raise RuntimeError(
            "FFmpeg executable not found. Please install ffmpeg or imageio-ffmpeg."
        ) from e


class GroqTranscriber:
    """Manages audio extraction, chunking, Groq Whisper transcription, and merging."""

    def __init__(self, client: Optional[Groq] = None) -> None:
        self.settings = get_settings()
        self._client = client
        self.ffmpeg_exe = get_ffmpeg_executable()

    @property
    def client(self) -> Groq:
        """Lazy-initialize Groq client using GROQ_API_KEY from .env only."""
        if self._client is None:
            api_key = self.settings.validate_groq_key()
            self._client = Groq(api_key=api_key)
        return self._client

    def extract_audio(
        self,
        media_path: Path,
        output_audio_path: Optional[Path] = None,
    ) -> Path:
        """Extract a 16kHz mono MP3 audio track from any video or audio file via FFmpeg."""
        input_path = Path(media_path).resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"Source media file not found: {input_path}")

        if output_audio_path is None:
            temp_dir = Path(tempfile.gettempdir())
            output_audio_path = temp_dir / f"incubrix_extracted_{input_path.stem}.mp3"

        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Extracting audio via FFmpeg: {input_path.name} -> {output_audio_path.name}")

        cmd = [
            self.ffmpeg_exe,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            str(output_audio_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                logger.error(f"FFmpeg audio extraction failed: {result.stderr}")
                raise RuntimeError(
                    f"FFmpeg extraction failed (code {result.returncode}): {result.stderr[-400:]}"
                )
        except Exception as e:
            logger.error(f"Failed to execute FFmpeg command: {e}")
            raise

        if not output_audio_path.exists() or output_audio_path.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg produced an empty or missing audio file: {output_audio_path}")

        return output_audio_path

    def get_audio_duration_seconds(self, audio_path: Path) -> float:
        """Probe audio duration using FFmpeg."""
        cmd = [
            self.ffmpeg_exe,
            "-i",
            str(audio_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Parse Duration: 00:01:23.45 from stderr
        for line in result.stderr.splitlines():
            if "Duration:" in line:
                try:
                    part = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = part.split(":")
                    return float(h) * 3600 + float(m) * 60 + float(s)
                except Exception:
                    break
        # Fallback approximation from file size at 64 kbps (8 KB/s)
        file_size = audio_path.stat().st_size
        return max(1.0, file_size / 8000.0)

    def split_audio_into_chunks(
        self,
        audio_path: Path,
        max_bytes: int = GROQ_MAX_FILE_BYTES,
    ) -> List[Tuple[Path, float]]:
        """Split audio into chunks under max_bytes limit if necessary.

        Returns a list of tuples: (chunk_file_path, start_offset_seconds).
        """
        file_size = audio_path.stat().st_size
        if file_size <= max_bytes:
            return [(audio_path, 0.0)]

        total_duration = self.get_audio_duration_seconds(audio_path)
        num_chunks = math.ceil(file_size / max_bytes) + 1
        chunk_duration = math.ceil(total_duration / num_chunks)

        logger.info(
            f"Audio file ({file_size / (1024 * 1024):.2f}MB) exceeds {max_bytes / (1024 * 1024):.0f}MB limit. "
            f"Splitting into ~{num_chunks} chunks of {chunk_duration}s using FFmpeg."
        )

        temp_dir = Path(tempfile.gettempdir())
        chunks: List[Tuple[Path, float]] = []
        current_offset = 0.0
        chunk_idx = 0

        while current_offset < total_duration:
            chunk_file = temp_dir / f"{audio_path.stem}_chunk_{chunk_idx:03d}.mp3"
            cmd = [
                self.ffmpeg_exe,
                "-y",
                "-ss",
                str(current_offset),
                "-t",
                str(chunk_duration),
                "-i",
                str(audio_path),
                "-c",
                "copy",
                str(chunk_file),
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and chunk_file.exists() and chunk_file.stat().st_size > 0:
                chunks.append((chunk_file, current_offset))
                chunk_idx += 1
            else:
                logger.warning(f"FFmpeg chunk split notice at offset {current_offset}s: {res.stderr}")
                break

            current_offset += chunk_duration

        if not chunks:
            # Fallback to original
            chunks.append((audio_path, 0.0))

        return chunks

    def transcribe_chunk(self, audio_chunk_path: Path) -> List[Dict[str, Any]]:
        """Transcribe a single audio chunk via Groq whisper-large-v3 with timestamps."""
        logger.info(
            f"Transcribing audio chunk {audio_chunk_path.name} ({audio_chunk_path.stat().st_size / 1024:.1f} KB) "
            f"via Groq ({self.settings.groq_whisper_model})..."
        )

        with open(audio_chunk_path, "rb") as f:
            file_bytes = f.read()

        try:
            response = self.client.audio.transcriptions.create(
                file=(audio_chunk_path.name, file_bytes),
                model=self.settings.groq_whisper_model,
                response_format="verbose_json",
            )
        except Exception as e:
            logger.error(f"Groq Whisper transcription API call failed: {e}")
            raise RuntimeError(f"Groq Whisper transcription failed for {audio_chunk_path.name}: {e}") from e

        # Extract segments
        if hasattr(response, "segments"):
            raw_segments = getattr(response, "segments") or []
        elif isinstance(response, dict):
            raw_segments = response.get("segments", [])
        else:
            raw_segments = []

        segments_data = []
        for s in raw_segments:
            if isinstance(s, dict):
                segments_data.append(s)
            else:
                segments_data.append({
                    "id": getattr(s, "id", 0),
                    "start": getattr(s, "start", 0.0),
                    "end": getattr(s, "end", 0.0),
                    "text": getattr(s, "text", ""),
                })
        return segments_data

    def transcribe_media(
        self,
        media_path: Path,
        title: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> IngestedDocument:
        """Full pipeline: extract audio, chunk under 25MB, transcribe via Groq, merge offsets."""
        path = Path(media_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        doc_title = title or path.stem.replace("_", " ").title()
        suffix = path.suffix.lower()

        is_video = suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"}
        resolved_source_type = source_type or ("video_file" if is_video else "audio_file")

        temp_audio_file: Optional[Path] = None
        created_chunks: List[Path] = []

        try:
            # 1. Extract clean audio via FFmpeg
            temp_audio_file = self.extract_audio(path)

            # 2. Split audio into chunks under Groq's file-size limit
            chunks_with_offsets = self.split_audio_into_chunks(temp_audio_file)
            created_chunks = [c[0] for c in chunks_with_offsets if c[0] != temp_audio_file]

            # 3. Transcribe chunks and merge with continuous timestamps
            all_segments: List[Segment] = []
            full_text_pieces: List[str] = []
            segment_counter = 0

            for chunk_file, offset in chunks_with_offsets:
                raw_segments = self.transcribe_chunk(chunk_file)
                for seg in raw_segments:
                    start_time = round(float(seg.get("start", 0.0)) + offset, 2)
                    end_time = round(float(seg.get("end", 0.0)) + offset, 2)
                    text_str = str(seg.get("text", "")).strip()
                    if text_str:
                        all_segments.append(
                            Segment(
                                id=segment_counter,
                                start=start_time,
                                end=end_time,
                                text=text_str,
                            )
                        )
                        full_text_pieces.append(text_str)
                        segment_counter += 1

            merged_text = " ".join(full_text_pieces).strip()
            logger.info(
                f"Completed transcription for '{doc_title}': {len(merged_text.split())} words across {len(all_segments)} segments."
            )

            return IngestedDocument(
                title=doc_title,
                source_type=resolved_source_type,
                text=merged_text,
                segments=all_segments,
            )

        finally:
            # Cleanup temporary audio files
            if temp_audio_file and temp_audio_file.exists():
                try:
                    temp_audio_file.unlink()
                except Exception:
                    pass
            for chunk_p in created_chunks:
                if chunk_p.exists():
                    try:
                        chunk_p.unlink()
                    except Exception:
                        pass

    # Backward-compatible method
    def transcribe(self, media_path: Path) -> TranscriptionResult:
        """Backward compatibility for existing pipeline calls."""
        doc = self.transcribe_media(media_path)
        segments = [
            TranscriptSegment(id=s.id, start=s.start, end=s.end, text=s.text)
            for s in doc.segments
        ]
        duration = segments[-1].end if segments else 0.0
        return TranscriptionResult(
            text=doc.text,
            language="en",
            duration=duration,
            segments=segments,
            raw_response={"word_count": len(doc.text.split())},
        )


# Backward compatibility aliasing for legacy imports
sys.modules["src.transcribe.transcriber"] = sys.modules[__name__]
