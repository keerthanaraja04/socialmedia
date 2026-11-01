"""Unit tests for calendar.csv (14 exact columns) and Buffer/Hootsuite scheduler exports."""

import csv
import json
from pathlib import Path
import pytest

from src.brandcheck.models import BrandCheckReport
from src.export import (
    CALENDAR_CSV_HEADERS,
    CalendarRow,
    ExportBundle,
    ExportManager,
)
from src.generate.models import GenerationResult, PlatformAsset, PlatformPost, ScriptBeat


def test_calendar_csv_exact_14_columns(tmp_path: Path) -> None:
    export_mgr = ExportManager(base_output_dir=tmp_path)

    # Verify header list has strictly 14 columns
    expected_headers = [
        "id",
        "platform",
        "format",
        "pillar",
        "hook",
        "caption",
        "hashtags",
        "CTA",
        "tracking_link",
        "file_path",
        "source_file_path",
        "scheduled_datetime",
        "target_metric",
        "status",
    ]
    assert CALENDAR_CSV_HEADERS == expected_headers
    assert len(CALENDAR_CSV_HEADERS) == 14

    # Create dummy generation result with rich platform assets
    generation = GenerationResult(
        topic="Autonomous AI Pipelines",
        core_message="Shift from manual editing to intelligent orchestration",
        script=ScriptBeat(
            hook="Stop cutting video clips manually.",
            body_points=["Whisper LPU speed", "Automated safe zones"],
            call_to_action="Follow @IncuBrix for more",
            estimated_duration_sec=30,
        ),
        assets=[
            PlatformAsset(
                asset_id="asset_tiktok_01",
                platform_id="tiktok",
                content_pillar="Practical Workflows",
                asset_type="short_video",
                target_metric="shares",
                title="The Autonomous Shift",
                caption="Here is how to automate your video cutdowns with Groq LPUs.",
                hashtags=["#IncuBrix", "#CreatorEconomy", "#TechInnovation"],
                cta="Follow @IncuBrix • Link in bio",
                utm_url="https://incubrix.com/?utm_source=tiktok&utm_medium=video&utm_campaign=launch",
            ),
            PlatformAsset(
                asset_id="asset_linkedin_02",
                platform_id="linkedin",
                content_pillar="Industry Breakdown",
                asset_type="carousel",
                target_metric="saves",
                title="The 3-Step Media Repurposing Blueprint",
                caption="Why modern video editors are becoming system architects.",
                hashtags=["#IncuBrix", "#MediaInnovation"],
                cta="Visit incubrix.ai for engine access",
                utm_url="https://incubrix.com/?utm_source=linkedin&utm_medium=carousel&utm_campaign=launch",
            ),
        ],
        platform_posts={
            "tiktok": PlatformPost(
                platform_id="tiktok",
                caption="TikTok caption",
                hashtags=["#IncuBrix"],
            ),
            "linkedin": PlatformPost(
                platform_id="linkedin",
                caption="LinkedIn caption",
                hashtags=["#IncuBrix"],
            ),
        },
    )

    brand_report = BrandCheckReport(
        passed=True,
        score=95.0,
        rule_score=95.0,
        llm_tone_score=95.0,
        violations=[],
    )

    bundle: ExportBundle = export_mgr.create_bundle(
        generation=generation,
        brand_report=brand_report,
        run_name="calendar_test",
        source_file_path=str(tmp_path / "test_input.txt"),
    )

    # 1. Assert calendar.csv exists
    calendar_file = bundle.export_dir / "calendar.csv"
    assert calendar_file.exists()

    with open(calendar_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        # Check exact headers
        assert headers == expected_headers
        rows = list(reader)
        assert len(rows) == 2

        # Check Row 1 values
        row1 = rows[0]
        assert row1[0] == "asset_tiktok_01"  # id
        assert row1[1] == "tiktok"           # platform
        assert row1[2] == "9:16 vertical video"  # format
        assert row1[3] == "Practical Workflows"  # pillar
        assert "Stop" in row1[4] or "Autonomous" in row1[4]  # hook
        assert "automate" in row1[5] or "video" in row1[5]  # caption
        assert "#IncuBrix" in row1[6]        # hashtags
        assert "Follow" in row1[7]           # CTA
        assert "utm_source=tiktok" in row1[8] # tracking_link
        assert str(tmp_path / "test_input.txt") in row1[10] # source_file_path
        assert ":" in row1[11]               # scheduled_datetime
        assert row1[12] == "shares"          # target_metric
        assert row1[13] == "scheduled"       # status

    # 2. Assert Buffer-style CSV exists
    buffer_file = bundle.export_dir / "buffer_schedule.csv"
    assert buffer_file.exists()
    with open(buffer_file, "r", newline="", encoding="utf-8") as f:
        b_reader = list(csv.reader(f))
        assert b_reader[0] == ["Date", "Text", "Media", "Platform"]
        assert len(b_reader) == 3

    # 3. Assert Hootsuite-style CSV exists
    hootsuite_file = bundle.export_dir / "hootsuite_schedule.csv"
    assert hootsuite_file.exists()
    with open(hootsuite_file, "r", newline="", encoding="utf-8") as f:
        h_reader = list(csv.reader(f))
        assert h_reader[0] == ["Date (GMT)", "Time (GMT)", "Text", "URL"]
        assert len(h_reader) == 3
        assert "utm_source" in h_reader[1][3]
