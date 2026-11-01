"""Unit tests for src/generate.py multi-asset generator, UTM builder, and platform assets."""

import json
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse
import pytest

from src.generate import (
    CarouselCopy,
    GenerationResult,
    GroqContentGenerator,
    PlatformAsset,
    ShortVideoScript,
    build_utm_link,
)


def test_build_utm_link() -> None:
    """Validate UTM tracking link builder parameters and base URL."""
    url = build_utm_link(
        base_url="https://incubrix.ai/demo",
        utm_source="linkedin",
        utm_medium="social_video",
        utm_campaign="repurposing_launch",
        utm_content="hook_first_2s",
    )

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "incubrix.ai"
    assert parsed.path == "/demo"

    qs = parse_qs(parsed.query)
    assert qs["utm_source"] == ["linkedin"]
    assert qs["utm_medium"] == ["social_video"]
    assert qs["utm_campaign"] == ["repurposing_launch"]
    assert qs["utm_content"] == ["hook_first_2s"]


def test_groq_content_generation_with_mock() -> None:
    """Verify legacy generation backward compatibility."""
    mock_groq = MagicMock()
    mock_choice = MagicMock()

    mock_payload = {
        "topic": "Autonomous AI Revolution",
        "core_message": "Agents are shifting coding from syntax writing to system architecture.",
        "script": {
            "hook": "Stop writing boilerplate code today.",
            "body_points": ["Point 1: Speed", "Point 2: Architecture"],
            "call_to_action": "How do you use agents?",
            "estimated_duration_sec": 30,
        },
        "visual_search_terms": ["cyberpunk coding", "developer at desk"],
        "platform_posts": {
            "tiktok": {
                "caption": "Software engineering just changed forever. 🚀 #Coding",
                "hashtags": ["#Coding"],
                "visual_search_term": "coding setup",
            },
            "linkedin": {
                "title": "The End of Boilerplate Code",
                "caption": "Why engineering leaders must adapt to agentic workflows now.",
                "hashtags": ["#EngineeringLeadership"],
                "visual_search_term": "modern tech office",
            },
        },
        "assets": [],
    }

    mock_choice.message.content = json.dumps(mock_payload)
    mock_groq.chat.completions.create.return_value.choices = [mock_choice]

    generator = GroqContentGenerator(client=mock_groq)
    result = generator.generate("Raw input article about AI agents", target_platforms=["tiktok", "linkedin"])

    assert result.topic == "Autonomous AI Revolution"
    assert result.script.hook == "Stop writing boilerplate code today."
    assert "tiktok" in result.platform_posts
    assert "linkedin" in result.platform_posts

    # Verify mandatory hashtags from brand.yaml were injected
    tiktok_tags = result.platform_posts["tiktok"].hashtags
    assert "#Incubrix" in tiktok_tags
    assert "#TechInnovation" in tiktok_tags


def test_generate_at_least_10_assets_with_video_and_carousels() -> None:
    """Validate generating >= 10 platform-native assets spread across platforms and pillars."""
    mock_groq = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"assets": []})
    mock_groq.chat.completions.create.return_value.choices = [mock_choice]

    generator = GroqContentGenerator(client=mock_groq, base_url="https://incubrix.com/playbook")
    source_content = """Podcast Episode 12: Why Creators Burn Out From Manual Repurposing.
In this episode we break down how creators spend 10+ hours chopping long-form video.
The solution is a 3-step automation pipeline to extract hooks and format for 4 platforms."""

    result: GenerationResult = generator.generate(
        raw_text=source_content,
        target_platforms=["linkedin", "instagram", "youtube_shorts", "tiktok"],
    )

    # 1. Produce AT LEAST 10 assets
    assert len(result.assets) >= 10

    # 2. Spread across platforms
    platforms_covered = {a.platform_id for a in result.assets}
    assert "linkedin" in platforms_covered
    assert "instagram" in platforms_covered
    assert "youtube_shorts" in platforms_covered
    assert "tiktok" in platforms_covered

    # 3. Spread across content pillars
    pillars_covered = {a.content_pillar for a in result.assets}
    assert len(pillars_covered) >= 3

    # 4. Each asset has a target_metric field
    for asset in result.assets:
        assert isinstance(asset, PlatformAsset)
        assert asset.target_metric is not None and len(asset.target_metric) > 0
        assert asset.utm_url.startswith("https://incubrix.com")
        assert "utm_source=" in asset.utm_url
        assert "utm_medium=" in asset.utm_url
        assert "utm_campaign=" in asset.utm_url
        assert "utm_content=" in asset.utm_url
        assert asset.cta is not None
        assert len(asset.caption) > 0

    # 5. Short video script constraints check (at least one short video asset)
    video_assets = [a for a in result.assets if a.short_video_script is not None]
    assert len(video_assets) >= 1
    sample_video = video_assets[0].short_video_script
    assert sample_video.total_duration_sec <= 60
    assert len(sample_video.hook_first_2s) > 0
    assert len(sample_video.on_screen_text_lines) >= 2
    assert len(sample_video.voiceover_script) > 0
    assert len(sample_video.beats) >= 2

    # 6. Carousel slide copy constraints check (at least one carousel asset)
    carousel_assets = [a for a in result.assets if a.carousel is not None]
    assert len(carousel_assets) >= 1
    sample_carousel = carousel_assets[0].carousel
    assert 6 <= sample_carousel.slide_count <= 8
    assert len(sample_carousel.slides) == sample_carousel.slide_count
    assert sample_carousel.slides[0].slide_number == 1
    assert len(sample_carousel.slides[0].headline) > 0
    assert len(sample_carousel.slides[0].body_text) > 0
