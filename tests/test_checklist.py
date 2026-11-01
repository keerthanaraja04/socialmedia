"""Unit tests for the 8-point readiness checklist validator in scripts/build_30.py.

Verifies programmatic validation of:
1. hook
2. caption
3. hashtags
4. CTA
5. UTM tracking link
6. source file on disk
7. license entry in licenses.csv
8. brand check passed
"""

import csv
import json
from pathlib import Path
import pytest

from scripts.build_30 import (
    AssetChecklistAudit,
    ChecklistValidator,
    _write_markdown_report,
    Build30Report,
)
from src.pipeline import CostMetrics


@pytest.fixture
def dummy_licenses_csv(tmp_path: Path) -> Path:
    lic_file = tmp_path / "licenses.csv"
    with open(lic_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["pixabay_id", "page_url", "author", "download_date", "asset_id", "manual_review", "manual_review_reason"])
        writer.writerow(["99001", "https://pixabay.com/v/99001", "JohnDoe", "2026-10-23", "asset_test_01", "FALSE", "Approved"])
    return lic_file


def test_checklist_fully_compliant_asset(tmp_path: Path, dummy_licenses_csv: Path) -> None:
    # Create dummy rendered file
    dummy_file = tmp_path / "video.mp4"
    dummy_file.write_bytes(b"dummy mp4 data")

    validator = ChecklistValidator(licenses_csv=dummy_licenses_csv)

    compliant_row = {
        "id": "asset_test_01",
        "platform": "tiktok",
        "format": "9:16 vertical video",
        "pillar": "Practical Workflows",
        "hook": "Stop cutting video cutdowns manually.",
        "caption": "Here is the exact 3-step autonomous pipeline we use at IncuBrix to automate media cutdowns.",
        "hashtags": "#IncuBrix #CreatorEconomy #TechInnovation",
        "CTA": "Follow @IncuBrix for weekly engineering breakdowns.",
        "tracking_link": "https://incubrix.com/?utm_source=tiktok&utm_medium=social_video&utm_campaign=launch",
        "file_path": str(dummy_file),
        "source_file_path": str(dummy_file),
        "scheduled_datetime": "2026-10-24 09:00:00",
        "target_metric": "shares",
        "status": "scheduled",
    }

    audit: AssetChecklistAudit = validator.validate_asset(
        row=compliant_row,
        brand_score=95.0,
        brand_passed=True,
    )

    assert audit.overall_passed is True
    assert len(audit.violations) == 0
    assert audit.hook_valid is True
    assert audit.caption_valid is True
    assert audit.hashtags_valid is True
    assert audit.cta_valid is True
    assert audit.utm_valid is True
    assert audit.source_file_valid is True
    assert audit.license_entry_valid is True
    assert audit.brand_check_passed is True


def test_checklist_detects_missing_hook(tmp_path: Path, dummy_licenses_csv: Path) -> None:
    dummy_file = tmp_path / "post.txt"
    dummy_file.write_text("Hello world", encoding="utf-8")

    validator = ChecklistValidator(licenses_csv=dummy_licenses_csv)

    row = {
        "id": "asset_test_01",
        "platform": "linkedin",
        "format": "1080x1350 carousel",
        "hook": "",  # Missing hook
        "caption": "Comprehensive breakdown of media repurposing architectures.",
        "hashtags": "#IncuBrix",
        "CTA": "Visit incubrix.com",
        "tracking_link": "https://incubrix.com/?utm_source=linkedin&utm_medium=carousel&utm_campaign=launch",
        "file_path": str(dummy_file),
    }

    audit = validator.validate_asset(row, brand_score=90.0, brand_passed=True)
    assert audit.overall_passed is False
    assert audit.hook_valid is False
    assert any("Hook is missing" in v for v in audit.violations)


def test_checklist_detects_missing_brand_hashtag(tmp_path: Path, dummy_licenses_csv: Path) -> None:
    dummy_file = tmp_path / "post.txt"
    dummy_file.write_text("Content", encoding="utf-8")

    validator = ChecklistValidator(licenses_csv=dummy_licenses_csv)

    row = {
        "id": "asset_test_01",
        "platform": "tiktok",
        "format": "9:16 vertical video",
        "hook": "Stop wasting time on editing.",
        "caption": "Autonomous media repurposing is here.",
        "hashtags": "#RandomHashtag #Unrelated",  # Missing #IncuBrix
        "CTA": "Follow for more",
        "tracking_link": "https://incubrix.com/?utm_source=tiktok&utm_medium=video&utm_campaign=launch",
        "file_path": str(dummy_file),
    }

    audit = validator.validate_asset(row, brand_score=90.0, brand_passed=True)
    assert audit.overall_passed is False
    assert audit.hashtags_valid is False
    assert any("mandatory brand tag" in v for v in audit.violations)


def test_checklist_detects_malformed_utm(tmp_path: Path, dummy_licenses_csv: Path) -> None:
    dummy_file = tmp_path / "post.txt"
    dummy_file.write_text("Content", encoding="utf-8")

    validator = ChecklistValidator(licenses_csv=dummy_licenses_csv)

    row = {
        "id": "asset_test_01",
        "platform": "tiktok",
        "format": "9:16 vertical video",
        "hook": "Stop wasting time on editing.",
        "caption": "Autonomous media repurposing is here.",
        "hashtags": "#IncuBrix",
        "CTA": "Follow @IncuBrix",
        "tracking_link": "https://incubrix.com/blog",  # Missing utm_source, utm_medium, utm_campaign
        "file_path": str(dummy_file),
    }

    audit = validator.validate_asset(row, brand_score=90.0, brand_passed=True)
    assert audit.overall_passed is False
    assert audit.utm_valid is False
    assert any("UTM tracking link is missing required parameters" in v for v in audit.violations)


def test_checklist_detects_failed_brand_check(tmp_path: Path, dummy_licenses_csv: Path) -> None:
    dummy_file = tmp_path / "post.txt"
    dummy_file.write_text("Content", encoding="utf-8")

    validator = ChecklistValidator(licenses_csv=dummy_licenses_csv)

    row = {
        "id": "asset_test_01",
        "platform": "tiktok",
        "format": "9:16 vertical video",
        "hook": "Guaranteed 100x viral scale overnight!",
        "caption": "IncuBrix guarantees infinite viral reach and automated passive revenue.",
        "hashtags": "#IncuBrix",
        "CTA": "Follow @IncuBrix",
        "tracking_link": "https://incubrix.com/?utm_source=tiktok&utm_medium=video&utm_campaign=launch",
        "file_path": str(dummy_file),
    }

    audit = validator.validate_asset(row, brand_score=65.0, brand_passed=False)
    assert audit.overall_passed is False
    assert audit.brand_check_passed is False
    assert any("Brand compliance check did not pass" in v for v in audit.violations)


def test_markdown_report_generation(tmp_path: Path) -> None:
    report = Build30Report(
        timestamp="2026-10-23T20:00:00Z",
        total_inputs_processed=4,
        total_assets=32,
        total_videos=12,
        total_carousels=8,
        platforms=["tiktok", "instagram_reels", "youtube_shorts", "linkedin", "x_twitter"],
        total_runtime_seconds=45.2,
        cost_metrics=CostMetrics(total_calls=8, prompt_tokens=5000, completion_tokens=2000, total_tokens=7000, estimated_cost_usd=0.005),
        checklist_pass_rate_pct=100.0,
        all_checklist_passed=True,
        assets_audit=[],
    )

    md_path = tmp_path / "test_audit_report.md"
    _write_markdown_report(report, md_path)

    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "Readiness Pass Rate:" in content
    assert "100.0%" in content
    assert "Short-Form Videos | >= 10 | **12**" in content
    assert "1080x1350 Carousels | >= 5 | **8**" in content
