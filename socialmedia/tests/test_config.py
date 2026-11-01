"""Unit tests for configuration loaders and environment validation."""

from pathlib import Path
import pytest
from src.config import (
    AppSettings,
    get_brand_config,
    get_platforms_config,
    get_settings,
)


def test_brand_config_loaded() -> None:
    brand = get_brand_config()
    assert brand.name.lower() == "incubrix"
    assert "guaranteed returns" in brand.rules.prohibited_words
    assert any("incubrix" in h.lower() for h in brand.rules.mandatory_hashtags)
    assert brand.visual.palette.primary.startswith("#")

    # Verify IncuBrix Creator Audience & Guidelines
    assert "creators" in brand.audience.get("primary", "").lower()
    assert "US" in brand.audience.get("geographic_markets", [])
    assert len(brand.voice_rules) >= 4
    assert len(brand.banned_phrases) >= 10
    assert "game-changer" in brand.banned_phrases
    assert len(brand.content_pillars) >= 4
    assert isinstance(brand.verified_features, list)
    assert len(brand.verified_features) == 0  # Verified features left empty for manual filling


def test_platforms_config_loaded() -> None:
    platforms_cfg = get_platforms_config()
    required_platforms = ["linkedin", "instagram", "youtube_shorts", "tiktok"]
    for p in required_platforms:
        assert p in platforms_cfg.platforms

    # Verify per-platform specifications
    linkedin = platforms_cfg.platforms["linkedin"]
    assert linkedin.max_caption_length == 3000
    assert linkedin.aspect_ratio == "1:1"
    assert linkedin.video_length_limit is not None
    assert linkedin.hook_rules is not None
    assert linkedin.cta_style is not None

    instagram = platforms_cfg.platforms["instagram"]
    assert instagram.max_caption_length == 2200
    assert instagram.aspect_ratio == "9:16"
    assert "safe zones" in instagram.hook_rules.get("rule_description", "").lower()
    assert "save" in instagram.cta_style.lower()

    shorts = platforms_cfg.platforms["youtube_shorts"]
    assert shorts.aspect_ratio == "9:16"
    assert shorts.max_title_length == 100
    assert shorts.hook_rules is not None

    tiktok = platforms_cfg.platforms["tiktok"]
    assert tiktok.aspect_ratio == "9:16"
    assert tiktok.hook_rules is not None
    assert "stitch" in tiktok.cta_style.lower() or "comment" in tiktok.cta_style.lower()


def test_api_keys_never_hardcoded_and_raise_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure AppSettings strictly reads keys from .env and raises when empty."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)

    settings = AppSettings(groq_api_key=None, pixabay_api_key=None)

    with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
        settings.validate_groq_key()

    with pytest.raises(ValueError, match="PIXABAY_API_KEY is not set"):
        settings.validate_pixabay_key()


def test_api_keys_valid_when_set() -> None:
    settings = AppSettings(
        groq_api_key="gsk_test_key_12345",
        pixabay_api_key="pixabay_test_key_67890",
    )
    assert settings.validate_groq_key() == "gsk_test_key_12345"
    assert settings.validate_pixabay_key() == "pixabay_test_key_67890"
