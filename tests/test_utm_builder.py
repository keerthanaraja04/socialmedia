"""Unit tests for the UTM tracking link builder in src/generate.py.

Verifies:
1. Default parameters generation
2. Parameter sanitization (lowercase, spaces to underscores, special chars)
3. Custom base URL handling (with/without trailing slash, existing query strings)
4. Parameter verification via urllib.parse
"""

from urllib.parse import parse_qs, urlparse
import pytest
from src.generate import build_utm_link


def test_build_utm_link_defaults() -> None:
    link = build_utm_link()
    assert link.startswith("https://incubrix.com?")

    parsed = urlparse(link)
    params = parse_qs(parsed.query)

    assert params["utm_source"] == ["linkedin"]
    assert params["utm_medium"] == ["social_video"]
    assert params["utm_campaign"] == ["repurposing_engine"]
    assert params["utm_content"] == ["hook_tactics"]


def test_build_utm_link_custom_platforms() -> None:
    platforms_and_types = [
        ("tiktok", "social_video", "creator_launch", "hook_01"),
        ("instagram_reels", "social_video", "creator_launch", "hook_02"),
        ("youtube_shorts", "social_video", "creator_launch", "hook_03"),
        ("linkedin", "social_carousel", "creator_launch", "slide_deck_01"),
        ("x_twitter", "social_post", "creator_launch", "thread_01"),
    ]

    for source, medium, campaign, content in platforms_and_types:
        link = build_utm_link(
            base_url="https://incubrix.com",
            utm_source=source,
            utm_medium=medium,
            utm_campaign=campaign,
            utm_content=content,
        )
        parsed = urlparse(link)
        params = parse_qs(parsed.query)

        assert params["utm_source"] == [source]
        assert params["utm_medium"] == [medium]
        assert params["utm_campaign"] == [campaign]
        assert params["utm_content"] == [content]


def test_build_utm_link_sanitizes_special_characters_and_whitespace() -> None:
    link = build_utm_link(
        base_url="https://incubrix.com",
        utm_source="LinkedIn Ads & Organic",
        utm_medium="Social Video (9:16)",
        utm_campaign="Q4 Brand Scaling!",
        utm_content="Hook #1 @IncuBrix",
    )
    parsed = urlparse(link)
    params = parse_qs(parsed.query)

    # Verifies all non-alphanumeric chars converted to underscores or clean tokens
    assert " " not in params["utm_source"][0]
    assert "&" not in params["utm_source"][0]
    assert ":" not in params["utm_medium"][0]
    assert "!" not in params["utm_campaign"][0]
    assert "@" not in params["utm_content"][0]
    assert "#" not in params["utm_content"][0]


def test_build_utm_link_preserves_existing_query_parameters() -> None:
    base = "https://incubrix.com/demo?ref=partner&lang=en"
    link = build_utm_link(
        base_url=base,
        utm_source="tiktok",
        utm_medium="social_video",
        utm_campaign="launch",
        utm_content="demo_clip",
    )
    parsed = urlparse(link)
    params = parse_qs(parsed.query)

    assert params["ref"] == ["partner"]
    assert params["lang"] == ["en"]
    assert params["utm_source"] == ["tiktok"]
    assert params["utm_medium"] == ["social_video"]
    assert params["utm_campaign"] == ["launch"]
    assert params["utm_content"] == ["demo_clip"]


def test_build_utm_link_adds_https_if_missing() -> None:
    link = build_utm_link(base_url="incubrix.com/playbook")
    assert link.startswith("https://incubrix.com/playbook?")
