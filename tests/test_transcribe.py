"""Unit tests for src/transcribe.py Groq Whisper transcription, chunking, and timestamp merging."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.transcribe import GroqTranscriber, IngestedDocument, Segment


def test_transcribe_media_with_chunk_merging(tmp_path: Path) -> None:
    """Validate audio chunking and merging segments with continuous timestamp offsets."""
    mock_groq = MagicMock()

    # Chunk 1 transcription response (0 - 10s)
    mock_chunk1_resp = MagicMock()
    mock_chunk1_resp.segments = [
        {"id": 0, "start": 0.0, "end": 4.5, "text": "Welcome to the IncuBrix podcast."},
        {"id": 1, "start": 4.6, "end": 9.8, "text": "Today we explore autonomous editing engines."},
    ]

    # Chunk 2 transcription response (10s offset -> 10.0 - 18.5s)
    mock_chunk2_resp = MagicMock()
    mock_chunk2_resp.segments = [
        {"id": 0, "start": 0.2, "end": 5.1, "text": "We will learn how to turn one episode into fifteen clips."},
        {"id": 1, "start": 5.2, "end": 8.5, "text": "Stay tuned for the full breakdown."},
    ]

    mock_groq.audio.transcriptions.create.side_effect = [
        mock_chunk1_resp,
        mock_chunk2_resp,
    ]

    dummy_media = tmp_path / "long_interview.mp4"
    dummy_media.write_bytes(b"\x00" * 512)

    dummy_audio_file = tmp_path / "extracted_audio.mp3"
    dummy_audio_file.write_bytes(b"\x00" * 256)

    dummy_chunk1 = tmp_path / "chunk_000.mp3"
    dummy_chunk1.write_bytes(b"\x00" * 128)
    dummy_chunk2 = tmp_path / "chunk_001.mp3"
    dummy_chunk2.write_bytes(b"\x00" * 128)

    transcriber = GroqTranscriber(client=mock_groq)

    # Mock extract_audio and split_audio_into_chunks to simulate 2 chunks with offsets
    with patch.object(transcriber, "extract_audio", return_value=dummy_audio_file):
        with patch.object(
            transcriber,
            "split_audio_into_chunks",
            return_value=[(dummy_chunk1, 0.0), (dummy_chunk2, 10.0)],
        ):
            doc: IngestedDocument = transcriber.transcribe_media(
                media_path=dummy_media,
                title="Long Interview Ep 1",
            )

    assert isinstance(doc, IngestedDocument)
    assert doc.title == "Long Interview Ep 1"
    assert doc.source_type == "video_file"
    assert len(doc.segments) == 4

    # Verify Chunk 1 timestamps (offset = 0.0)
    assert doc.segments[0].id == 0
    assert doc.segments[0].start == 0.0
    assert doc.segments[0].end == 4.5
    assert doc.segments[0].text == "Welcome to the IncuBrix podcast."

    # Verify Chunk 2 timestamps (offset = 10.0 applied to 0.2 and 5.1)
    assert doc.segments[2].id == 2
    assert doc.segments[2].start == 10.2
    assert doc.segments[2].end == 15.1
    assert "fifteen clips" in doc.segments[2].text

    assert doc.segments[3].id == 3
    assert doc.segments[3].start == 15.2
    assert doc.segments[3].end == 18.5

    # Verify merged text
    assert "Welcome to the IncuBrix podcast." in doc.text
    assert "Stay tuned for the full breakdown." in doc.text


def test_transcribe_missing_file_raises_not_found() -> None:
    transcriber = GroqTranscriber(client=MagicMock())
    with pytest.raises(FileNotFoundError):
        transcriber.transcribe_media(Path("non_existent_audio.mp3"))


def test_transcribe_failure_logs_and_raises_clear_error(tmp_path: Path) -> None:
    mock_groq = MagicMock()
    mock_groq.audio.transcriptions.create.side_effect = RuntimeError("Groq API 500 Internal Error")

    dummy_media = tmp_path / "error_test.mp3"
    dummy_media.write_bytes(b"\x00" * 128)

    transcriber = GroqTranscriber(client=mock_groq)
    with patch.object(transcriber, "extract_audio", return_value=dummy_media):
        with patch.object(transcriber, "split_audio_into_chunks", return_value=[(dummy_media, 0.0)]):
            with pytest.raises(RuntimeError, match="Groq Whisper transcription failed"):
                transcriber.transcribe_media(dummy_media)
