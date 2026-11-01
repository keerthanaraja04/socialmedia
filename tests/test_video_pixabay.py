"""Unit tests for src/video/pixabay.py Pixabay Videos API client, scoring, single-clip download, and license logging."""

import csv
import json
from pathlib import Path
import time
from unittest.mock import MagicMock, patch
import pytest
import requests

from src.video.pixabay import (
    ClipCandidate,
    DownloadedClip,
    LicenseRegistry,
    PixabayVideoCache,
    PixabayVideoDownloader,
    PixabayVideoHit,
    PixabayVideoSize,
    extract_keywords_from_script,
)


def _sample_hit_dict(
    hit_id: int = 101,
    duration: int = 10,
    tags: str = "podcast, microphone, studio, audio",
    width: int = 1080,
    height: int = 1920,
    user: str = "AudioCreator",
) -> dict:
    return {
        "id": hit_id,
        "pageURL": f"https://pixabay.com/videos/sample-{hit_id}/",
        "tags": tags,
        "duration": duration,
        "videos": {
            "large": {
                "url": f"https://cdn.pixabay.com/sample_{hit_id}_large.mp4",
                "width": width,
                "height": height,
                "size": 5242880,
            },
            "medium": {
                "url": f"https://cdn.pixabay.com/sample_{hit_id}_med.mp4",
                "width": width // 2,
                "height": height // 2,
                "size": 2621440,
            },
        },
        "views": 12000,
        "downloads": 4500,
        "likes": 280,
        "comments": 12,
        "user": user,
    }


# ==============================================================================
# 1. Cache Tests (24-Hour TTL)
# ==============================================================================
def test_pixabay_video_cache_set_and_get(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.json"
    cache = PixabayVideoCache(cache_file=cache_file, ttl_seconds=86400)

    sample_hits = [_sample_hit_dict(101)]
    cache.set("podcast", sample_hits, per_page=20)

    # Cache hit
    result = cache.get("podcast", per_page=20)
    assert result is not None
    assert len(result) == 1
    assert result[0]["id"] == 101

    # Cache miss on different query
    assert cache.get("nonexistent_query", per_page=20) is None


def test_pixabay_video_cache_expiration_after_24h(tmp_path: Path) -> None:
    cache_file = tmp_path / "cache.json"
    # Default 24h TTL (86,400 seconds)
    cache = PixabayVideoCache(cache_file=cache_file, ttl_seconds=86400)

    base_time = 1700000000.0
    with patch("time.time", return_value=base_time):
        cache.set("microphone", [_sample_hit_dict(202)])
        assert cache.get("microphone") is not None

    # Advance time within 24h (e.g., 12 hours later) -> still valid
    with patch("time.time", return_value=base_time + 43200.0):
        assert cache.get("microphone") is not None

    # Advance time past 24h (e.g., 24 hours + 1 second later) -> expired
    with patch("time.time", return_value=base_time + 86401.0):
        assert cache.get("microphone") is None


# ==============================================================================
# 2. Candidate Evaluation & Vertical Clip Selection (< 15s, Face/Logo Safety)
# ==============================================================================
def test_evaluate_candidate_filters_clips_over_15s(tmp_path: Path) -> None:
    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=tmp_path / "licenses.csv",
    )

    # 1. Clip duration = 16s (exceeds 15s limit) -> must be rejected
    long_hit = PixabayVideoHit.model_validate(_sample_hit_dict(hit_id=301, duration=16))
    assert downloader.evaluate_candidate(long_hit, max_duration=15.0) is None

    # 2. Clip duration = 12s -> accepted
    short_hit = PixabayVideoHit.model_validate(_sample_hit_dict(hit_id=302, duration=12))
    candidate = downloader.evaluate_candidate(short_hit, max_duration=15.0)
    assert candidate is not None
    assert candidate.hit.duration == 12


def test_evaluate_candidate_ranks_vertical_and_face_free_higher(tmp_path: Path) -> None:
    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=tmp_path / "licenses.csv",
    )

    # Clip A: Native Vertical (1080x1920), 10s, clean b-roll (mic, studio)
    hit_vertical_clean = PixabayVideoHit.model_validate(
        _sample_hit_dict(
            hit_id=401,
            duration=10,
            tags="podcast, microphone, studio, sound",
            width=1080,
            height=1920,
        )
    )

    # Clip B: Horizontal (1920x1080), 10s, contains face/person
    hit_horizontal_person = PixabayVideoHit.model_validate(
        _sample_hit_dict(
            hit_id=402,
            duration=10,
            tags="woman, face, talking, podcast, interview",
            width=1920,
            height=1080,
        )
    )

    candidate_a = downloader.evaluate_candidate(hit_vertical_clean)
    candidate_b = downloader.evaluate_candidate(hit_horizontal_person)

    assert candidate_a is not None
    assert candidate_b is not None

    # Candidate A must score significantly higher
    assert candidate_a.is_vertical is True
    assert candidate_a.manual_review_needed is False
    assert "Clean b-roll asset" in candidate_a.manual_review_reason

    # Candidate B must be flagged for manual review due to recognizable person/face
    assert candidate_b.is_vertical is False
    assert candidate_b.manual_review_needed is True
    assert "face" in candidate_b.manual_review_reason.lower() or "woman" in candidate_b.manual_review_reason.lower()

    assert candidate_a.score > candidate_b.score


def test_select_best_clip_never_picks_disqualified_clip(tmp_path: Path) -> None:
    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=tmp_path / "licenses.csv",
    )

    hit_long = PixabayVideoHit.model_validate(_sample_hit_dict(hit_id=501, duration=22))
    hit_bad_duration = PixabayVideoHit.model_validate(_sample_hit_dict(hit_id=502, duration=0))
    hit_valid_horizontal = PixabayVideoHit.model_validate(
        _sample_hit_dict(hit_id=503, duration=8, tags="laptop, editing", width=1920, height=1080)
    )
    hit_valid_vertical = PixabayVideoHit.model_validate(
        _sample_hit_dict(hit_id=504, duration=9, tags="laptop, desk, screen", width=1080, height=1920)
    )

    winner = downloader.select_best_clip([hit_long, hit_bad_duration, hit_valid_horizontal, hit_valid_vertical])
    assert winner is not None
    # Winner must be the vertical valid clip (hit 504)
    assert winner.hit.id == 504
    assert winner.hit.duration == 9
    assert winner.is_vertical is True


# ==============================================================================
# 3. Single-Clip Download & License Registry
# ==============================================================================
@patch("src.video.pixabay.requests.get")
def test_download_only_selected_clip_and_logs_license(mock_get: MagicMock, tmp_path: Path) -> None:
    # Mock video file download stream
    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [b"MOCK_MP4_HEADER", b"_MOCK_FRAME_DATA"]
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    licenses_csv = tmp_path / "content" / "licenses.csv"
    broll_dir = tmp_path / "content" / "assets" / "broll"

    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=licenses_csv,
        min_request_interval_seconds=0.0,
    )

    hit = PixabayVideoHit.model_validate(
        _sample_hit_dict(
            hit_id=777,
            duration=11,
            tags="editing, laptop, timeline",
            width=1080,
            height=1920,
            user="VideoEditorPro",
        )
    )
    candidate = downloader.evaluate_candidate(hit)
    assert candidate is not None

    # Execute single-clip download
    downloaded: DownloadedClip = downloader.download_selected_clip(
        candidate=candidate,
        destination_dir=broll_dir,
    )

    # 1. Assert exactly 1 download request occurred (never bulk download)
    assert mock_get.call_count == 1
    assert "sample_777_large.mp4" in mock_get.call_args[0][0]

    # 2. Assert local file written
    assert downloaded.local_path.exists()
    assert downloaded.local_path.stat().st_size > 0
    assert downloaded.pixabay_id == 777
    assert downloaded.author == "VideoEditorPro"
    assert downloaded.duration == 11

    # 3. Assert licenses.csv created and appended properly
    assert licenses_csv.exists()
    with open(licenses_csv, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        row = reader[0]
        assert row["pixabay_id"] == "777"
        assert row["page_url"] == "https://pixabay.com/videos/sample-777/"
        assert row["author"] == "VideoEditorPro"
        assert row["asset_id"] == downloaded.asset_id
        assert row["manual_review"] == "FALSE"
        assert "Clean" in row["manual_review_reason"]


# ==============================================================================
# 4. Manual Review Flagging for Recognizable Brand Logos or Faces
# ==============================================================================
@patch("src.video.pixabay.requests.get")
def test_flag_for_manual_review_when_brand_or_person_in_tags(mock_get: MagicMock, tmp_path: Path) -> None:
    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [b"MP4_DATA"]
    mock_resp.raise_for_status.return_value = None
    mock_get.return_value = mock_resp

    licenses_csv = tmp_path / "content" / "licenses.csv"
    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=licenses_csv,
        min_request_interval_seconds=0.0,
    )

    hit_with_brand = PixabayVideoHit.model_validate(
        _sample_hit_dict(
            hit_id=888,
            duration=12,
            tags="apple, macbook, logo, laptop",
            width=1080,
            height=1920,
            user="TechReviewer",
        )
    )
    candidate = downloader.evaluate_candidate(hit_with_brand)
    assert candidate is not None
    assert candidate.manual_review_needed is True
    assert "apple" in candidate.manual_review_reason.lower() or "logo" in candidate.manual_review_reason.lower()

    downloaded = downloader.download_selected_clip(candidate, destination_dir=tmp_path / "broll")
    assert downloaded.manual_review is True

    # Check CSV record
    with open(licenses_csv, "r", newline="", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        row = reader[0]
        assert row["pixabay_id"] == "888"
        assert row["manual_review"] == "TRUE"
        assert "apple" in row["manual_review_reason"].lower() or "logo" in row["manual_review_reason"].lower()


# ==============================================================================
# 5. Rate Limit & 429 Handling
# ==============================================================================
@patch("src.video.pixabay.requests.get")
def test_rate_limit_429_retry_handling(mock_get: MagicMock, tmp_path: Path) -> None:
    # 1st call returns HTTP 429, 2nd call returns success JSON
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {"Retry-After": "0"}

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.raise_for_status.return_value = None
    mock_200.json.return_value = {"hits": [_sample_hit_dict(999, duration=10)]}

    mock_get.side_effect = [mock_429, mock_200]

    downloader = PixabayVideoDownloader(
        api_key="test_key",
        cache_file=tmp_path / "cache.json",
        licenses_csv=tmp_path / "licenses.csv",
        min_request_interval_seconds=0.0,
    )

    hits = downloader.search_videos("podcast", per_page=10, max_retries=3)
    assert len(hits) == 1
    assert hits[0].id == 999
    assert mock_get.call_count == 2


# ==============================================================================
# 6. Keyword Extraction from Script
# ==============================================================================
def test_extract_keywords_from_script() -> None:
    script_1 = (
        "In this podcast episode, we bring our microphone close and dive into laptop "
        "editing workflows for high-retention social reels."
    )
    keywords_1 = extract_keywords_from_script(script_1)
    assert "podcast" in keywords_1
    assert "microphone" in keywords_1
    assert "editing" in keywords_1
    assert "laptop" in keywords_1

    script_generic = "Today we discuss the new release."
    keywords_2 = extract_keywords_from_script(script_generic)
    # Falls back to high-intent defaults
    assert len(keywords_2) >= 2
    assert any(k in ["podcast", "microphone", "editing", "laptop"] for k in keywords_2)
