"""Unit tests for src/ingest.py accepting URLs, files, media, and pasted scripts."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.ingest import ContentType, IngestManager, IngestedDocument, Segment


def test_ingest_pasted_demo_script() -> None:
    """Validate ingesting a pasted demo script string."""
    manager = IngestManager()
    script_text = """Stop spending 10 hours cutting podcast episodes.
Here is the 3-step engine we use to generate 15 vertical clips.
Follow for more creator workflows."""

    doc: IngestedDocument = manager.ingest(script_text)

    assert isinstance(doc, IngestedDocument)
    assert doc.source_type == "pasted_script"
    assert "Stop spending 10 hours" in doc.title
    assert "Follow for more creator workflows." in doc.text
    assert len(doc.segments) >= 2
    assert doc.segments[0].id == 0
    assert doc.segments[0].start == 0.0
    assert doc.segments[0].end > 0.0


def test_ingest_blog_url_with_mock() -> None:
    """Validate fetching and parsing a blog URL."""
    manager = IngestManager()
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head><title>The Future of Short-Form Video Repurposing</title></head>
    <body>
        <nav><a href="/">Home</a></nav>
        <article>
            <h1>The Future of Short-Form Video Repurposing</h1>
            <p>Creators are facing burnout from manual editing workflows across multiple platforms.</p>
            <p>Automated ingestion and transcription allow editors to focus purely on creative storytelling.</p>
        </article>
        <footer>Copyright 2026</footer>
    </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.text = html_sample
    mock_resp.raise_for_status.return_value = None

    with patch("src.ingest.requests.get", return_value=mock_resp) as mock_get:
        doc = manager.ingest("https://example.com/blog/video-repurposing")
        mock_get.assert_called_once()
        assert doc.source_type == "url"
        assert doc.title == "The Future of Short-Form Video Repurposing"
        assert "Creators are facing burnout" in doc.text
        assert len(doc.segments) >= 2
        # Ensure footer/nav were stripped
        assert "Copyright" not in doc.text
        assert "Home" not in doc.text


def test_ingest_local_text_file(tmp_path: Path) -> None:
    """Validate ingesting a local markdown/text file."""
    manager = IngestManager()
    test_md = tmp_path / "guide.md"
    test_md.write_text(
        "# High-Retention Hook Mechanics\n\nThe first 1.5 seconds dictate whether a viewer scrolls past.",
        encoding="utf-8",
    )

    doc = manager.ingest(test_md)

    assert doc.source_type == "text_file"
    assert doc.title == "High-Retention Hook Mechanics"
    assert "The first 1.5 seconds" in doc.text
    assert len(doc.segments) >= 1


def test_ingest_audio_file_delegation(tmp_path: Path) -> None:
    """Validate that audio file inputs are routed to GroqTranscriber."""
    mock_transcriber = MagicMock()
    mock_doc = IngestedDocument(
        title="Podcast Episode 42",
        source_type="audio_file",
        text="Welcome back to the podcast.",
        segments=[Segment(id=0, start=0.0, end=2.4, text="Welcome back to the podcast.")],
    )
    mock_transcriber.transcribe_media.return_value = mock_doc

    manager = IngestManager(transcriber=mock_transcriber)
    dummy_audio = tmp_path / "episode42.mp3"
    dummy_audio.write_bytes(b"\x00" * 64)

    doc = manager.ingest(dummy_audio)

    mock_transcriber.transcribe_media.assert_called_once_with(dummy_audio, title=None)
    assert doc.title == "Podcast Episode 42"
    assert doc.source_type == "audio_file"
    assert len(doc.segments) == 1


def test_ingest_invalid_url_raises_clear_error() -> None:
    manager = IngestManager()
    with pytest.raises(Exception):
        manager.ingest("http://invalid-non-existent-domain-12345.xyz")


def test_ingest_missing_file_raises_not_found() -> None:
    manager = IngestManager()
    with pytest.raises(FileNotFoundError):
        manager.ingest("non_existent_file.mp4")
