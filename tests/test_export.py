"""Unit tests for export packaging and manifest generation."""

import json
from pathlib import Path
from src.brandcheck.models import BrandCheckReport
from src.export.exporter import ExportManager
from src.generate.models import GenerationResult, PlatformPost, ScriptBeat


def test_export_bundle_packaging(tmp_path: Path) -> None:
    export_mgr = ExportManager(base_output_dir=tmp_path)

    generation = GenerationResult(
        topic="Agentic AI Architecture",
        core_message="Shift from syntax to architecture",
        script=ScriptBeat(
            hook="The future of software is agentic",
            body_points=["Fast", "Autonomous"],
            call_to_action="Follow for more",
            estimated_duration_sec=30,
        ),
        platform_posts={
            "tiktok": PlatformPost(
                platform_id="tiktok",
                caption="Here is the TikTok caption! #Incubrix",
                hashtags=["#Incubrix", "#TechInnovation"],
            ),
            "linkedin": PlatformPost(
                platform_id="linkedin",
                title="The Agentic Shift",
                caption="Here is the LinkedIn post! #Incubrix",
                hashtags=["#Incubrix"],
            ),
        },
    )

    brand_report = BrandCheckReport(
        passed=True,
        score=92.5,
        rule_score=95.0,
        llm_tone_score=90.0,
        violations=[],
    )

    # Create dummy thumbnail
    dummy_thumb = tmp_path / "thumb.png"
    dummy_thumb.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    bundle = ExportManager(base_output_dir=tmp_path).create_bundle(
        generation=generation,
        brand_report=brand_report,
        rendered_videos={},
        thumbnails={"tiktok": dummy_thumb, "linkedin": dummy_thumb},
        run_name="unit_test",
    )

    assert bundle.export_dir.exists()
    assert bundle.manifest_path.exists()

    with open(bundle.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["topic"] == "Agentic AI Architecture"
    assert manifest["brandcheck"]["score"] == 92.5
    assert "tiktok" in manifest["platforms"]

    # Verify platform directory contents
    tiktok_dir = bundle.export_dir / "tiktok"
    assert (tiktok_dir / "post_content.txt").exists()
    assert (tiktok_dir / "metadata.json").exists()
    assert (tiktok_dir / "tiktok_thumbnail.png").exists()
