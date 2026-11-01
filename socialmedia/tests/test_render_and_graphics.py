"""Unit tests for src/video/render.py and src/graphics.py:
- 9:16 vertical video compilation with hook overlay & captions.
- Free font license recording.
- TTS voiceover with fallback to text-on-video.
- 1080x1350 Pillow carousel slide rendering from brand colors.
- Editable source file generation (spec.json, template.html, template.svg) in content/assets/<id>/.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
import pytest

from src.graphics import (
    CAROUSEL_HEIGHT,
    CAROUSEL_WIDTH,
    CarouselAssetSpec,
    CarouselRenderer,
    CarouselSlideData,
)
from src.video.render import (
    CaptionSegment,
    VideoRenderer,
    VideoRenderSpec,
    get_free_font,
    render_caption_overlay,
    render_hook_overlay,
    save_editable_sources,
)


# Helper to generate a dummy 1-second video clip for testing MoviePy pipeline
def create_dummy_mp4(path: Path, width: int = 720, height: int = 1280, duration: float = 1.0) -> Path:
    from moviepy.editor import ColorClip

    clip = ColorClip(size=(width, height), color=(20, 30, 50), duration=duration)
    path.parent.mkdir(parents=True, exist_ok=True)
    clip.write_videofile(
        str(path),
        fps=10,
        codec="libx264",
        preset="ultrafast",
        threads=1,
        ffmpeg_params=["-loglevel", "error"],
        verbose=False,
        logger=None,
    )
    clip.close()
    return path


# ==============================================================================
# 1. Font & Overlay Tests
# ==============================================================================
def test_get_free_font_records_license() -> None:
    font, font_name, font_license = get_free_font(size=36, bold=True)
    assert font is not None
    assert isinstance(font_name, str) and len(font_name) > 0
    assert isinstance(font_license, str) and len(font_license) > 0
    # Must be open source / free license
    assert any(term in font_license.lower() for term in ["free", "open", "public", "license", "standard"])


def test_render_hook_overlay_dimensions() -> None:
    img = render_hook_overlay(
        hook_text="Stop spending 10 hours cutting cutdowns.",
        category_tag="CREATOR BREAKTHROUGH",
        width=1080,
        height=1920,
    )
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_render_caption_overlay_dimensions() -> None:
    img = render_caption_overlay(
        caption_text="Automate viral cutdowns in seconds with Whisper LPU.",
        width=1080,
        height=1920,
    )
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


# ==============================================================================
# 2. Editable Source File Generation (JSON + HTML/SVG)
# ==============================================================================
def test_save_editable_sources(tmp_path: Path) -> None:
    asset_dir = tmp_path / "content" / "assets" / "test_asset_001"
    spec = VideoRenderSpec(
        asset_id="test_asset_001",
        duration_seconds=14.5,
        mode="text-on-video",
        font_name="DejaVu Sans Bold",
        font_license="Bitstream Vera & Arev Fonts License (Free / Open Source)",
        brand_palette={"primary": "#0F172A", "secondary": "#6366F1", "accent": "#10B981"},
        hook_overlay={"text": "Stop writing code manually.", "category": "AI BREAKTHROUGH", "start_sec": 0.0, "end_sec": 2.0},
        captions=[CaptionSegment(start_sec=2.0, end_sec=5.0, text="Autonomous agents take the lead.")],
        source_clip={"filename": "clip.mp4", "pixabay_id": 999},
        created_at="2026-10-23T18:00:00Z",
    )

    spec_file, html_file, svg_file = save_editable_sources(asset_dir, spec)

    # 1. Assert spec.json exists and is valid
    assert spec_file.exists()
    loaded_spec = json.loads(spec_file.read_text(encoding="utf-8"))
    assert loaded_spec["asset_id"] == "test_asset_001"
    assert loaded_spec["font_name"] == "DejaVu Sans Bold"
    assert "Free" in loaded_spec["font_license"]
    assert loaded_spec["hook_overlay"]["end_sec"] == 2.0

    # 2. Assert template.html exists and contains interactive preview
    assert html_file.exists()
    html_text = html_file.read_text(encoding="utf-8")
    assert "test_asset_001" in html_text
    assert "Stop writing code manually." in html_text
    assert "AI BREAKTHROUGH" in html_text

    # 3. Assert template.svg exists
    assert svg_file.exists()
    svg_text = svg_file.read_text(encoding="utf-8")
    assert "<svg" in svg_text
    assert 'width="1080" height="1920"' in svg_text


# ==============================================================================
# 3. 9:16 Video Rendering Pipeline (MoviePy/ffmpeg)
# ==============================================================================
def test_video_renderer_compiles_9_16_reel_with_editable_sources(tmp_path: Path) -> None:
    # 1. Create source dummy clip
    clip_file = tmp_path / "source_broll.mp4"
    create_dummy_mp4(clip_file, width=640, height=360, duration=2.0)

    asset_dir = tmp_path / "content" / "assets" / "reel_demo_01"
    licenses_csv = tmp_path / "content" / "licenses.csv"

    renderer = VideoRenderer(licenses_csv=licenses_csv)

    script = {
        "hook": "Stop spending 10 hours cutting podcast cutdowns.",
        "body_points": [
            "Whisper large-v3 transcribes your full episode in seconds.",
            "LLaMA-3 formats 9:16 hooks and captions for TikTok.",
        ],
        "call_to_action": "Follow @IncuBrix for autonomous workflows.",
    }

    # Render without outbound network TTS to keep unit test self-contained & fast (1.0s duration)
    final_mp4 = renderer.render_reel(
        script=script,
        clip_path=clip_file,
        asset_id="reel_demo_01",
        output_dir=asset_dir,
        max_duration=1.0,
        enable_tts=False,  # Tests text-on-video fallback mode
        pixabay_hit_data={"id": 12345, "pageURL": "https://pixabay.com/videos/12345/", "user": "StudioGuy"},
    )

    # Assert video rendered
    assert final_mp4.exists()
    assert final_mp4.stat().st_size > 0
    assert final_mp4.suffix == ".mp4"

    # Assert editable source files saved in content/assets/<id>/
    spec_path = asset_dir / "spec.json"
    html_path = asset_dir / "template.html"
    svg_path = asset_dir / "template.svg"

    assert spec_path.exists()
    assert html_path.exists()
    assert svg_path.exists()

    spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec_data["asset_id"] == "reel_demo_01"
    assert spec_data["width"] == 1080
    assert spec_data["height"] == 1920
    assert spec_data["duration_seconds"] <= 60.0
    assert spec_data["mode"] == "text-on-video"
    assert "DejaVu" in spec_data["font_name"] or "Arial" in spec_data["font_name"]
    assert len(spec_data["font_license"]) > 0

    # Assert license logged in licenses.csv
    assert licenses_csv.exists()
    csv_text = licenses_csv.read_text(encoding="utf-8")
    assert "12345" in csv_text
    assert "reel_demo_01" in csv_text


# ==============================================================================
# 4. Pillow Carousel Slide Renderer (1080x1350)
# ==============================================================================
def test_carousel_renderer_1080x1350_and_editable_sources(tmp_path: Path) -> None:
    asset_dir = tmp_path / "content" / "assets" / "carousel_repurposing_01"
    renderer = CarouselRenderer()

    slides = [
        CarouselSlideData(
            slide_number=1,
            slide_type="cover",
            category="CREATOR BLUEPRINT",
            title="How to Scale Short-Form Media Without Burnout",
            body_points=["The 3-phase autonomous engine transforming modern media teams."],
        ),
        CarouselSlideData(
            slide_number=2,
            slide_type="content",
            category="BLUEPRINT",
            title="Ingestion & Whisper LPU Speed",
            body_points=[
                "Cloud-accelerated transcription in sub-second latency.",
                "Extract timestamp-aligned retention hooks.",
            ],
            tip="Keep video clips under 15s for maximal B-roll cutaway pacing.",
        ),
        CarouselSlideData(
            slide_number=3,
            slide_type="cta",
            category="GET STARTED",
            title="Scale Your Brand with IncuBrix",
            body_points=[
                "Turn 1 video podcast into 15+ ready-to-post assets",
                "Automated compliance, captions, and brand guardrails",
            ],
            cta_text="Follow @IncuBrix • Link in bio",
        ),
    ]

    rendered_files = renderer.render_carousel(
        slides_data=slides,
        asset_id="carousel_repurposing_01",
        output_dir=asset_dir,
    )

    # 1. Assert all 3 slide images generated
    assert len(rendered_files) == 3
    for s_file in rendered_files:
        assert s_file.exists()
        assert s_file.suffix == ".png"
        with Image.open(s_file) as img:
            # Must strictly match 1080x1350
            assert img.size == (CAROUSEL_WIDTH, CAROUSEL_HEIGHT)
            assert img.size == (1080, 1350)

    # 2. Assert editable sources saved in content/assets/<id>/
    spec_path = asset_dir / "spec.json"
    html_path = asset_dir / "template.html"
    svg_path = asset_dir / "template.svg"

    assert spec_path.exists()
    assert html_path.exists()
    assert svg_path.exists()

    spec_dict = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec_dict["asset_id"] == "carousel_repurposing_01"
    assert spec_dict["width"] == 1080
    assert spec_dict["height"] == 1350
    assert spec_dict["slides_count"] == 3
    assert "brand_palette" in spec_dict
    assert len(spec_dict["font_license"]) > 0

    # 3. Check HTML template content
    html_content = html_path.read_text(encoding="utf-8")
    assert "How to Scale Short-Form Media Without Burnout" in html_content
    assert "1080x1350" in html_content
