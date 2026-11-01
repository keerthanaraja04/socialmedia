"""Configuration management for Incubrix Engine.

Loads environment variables strictly from .env and parses YAML configuration files
into type-safe Pydantic models. API keys are never hardcoded anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Locate project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables strictly from .env located in PROJECT_ROOT or config/.env
env_paths = [PROJECT_ROOT / ".env", PROJECT_ROOT / "config" / ".env"]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        break
else:
    # Try general load_dotenv if no explicit file found
    load_dotenv()


class VisualPalette(BaseModel):
    primary: str = "#0F172A"
    secondary: str = "#6366F1"
    accent: str = "#10B981"
    background: str = "#030712"
    card_bg: str = "#1E293B"
    text_primary: str = "#F8FAFC"
    text_muted: str = "#94A3B8"


class WatermarkConfig(BaseModel):
    enabled: bool = True
    text: str = "INCUBRIX"
    position: str = "top_right"
    opacity: float = 0.85
    margin: int = 40


class VisualConfig(BaseModel):
    palette: VisualPalette = Field(default_factory=VisualPalette)
    typography: Dict[str, Any] = Field(default_factory=dict)
    watermark: WatermarkConfig = Field(default_factory=WatermarkConfig)


class BrandTone(BaseModel):
    primary: str = "visionary"
    secondary: str = "authoritative"
    style: str = "concise, punchy, forward-looking, highly engaging"


class BrandRules(BaseModel):
    prohibited_words: List[str] = Field(default_factory=list)
    required_keywords: List[str] = Field(default_factory=list)
    mandatory_hashtags: List[str] = Field(default_factory=list)
    min_compliance_score: int = 80
    max_sentence_length_words: int = 25


class BrandConfig(BaseModel):
    name: str = "IncuBrix"
    tagline: str = "The High-Velocity Repurposing & Distribution Engine for Modern Creators"
    audience: Dict[str, Any] = Field(default_factory=dict)
    tone: BrandTone = Field(default_factory=BrandTone)
    voice_rules: List[Dict[str, Any]] = Field(default_factory=list)
    banned_phrases: List[str] = Field(default_factory=list)
    content_pillars: List[Dict[str, Any]] = Field(default_factory=list)
    verified_features: List[str] = Field(default_factory=list)
    visual: VisualConfig = Field(default_factory=VisualConfig)
    rules: BrandRules = Field(default_factory=BrandRules)


class PlatformSpec(BaseModel):
    name: str
    format: str = "mp4"
    max_caption_length: int = 2200
    aspect_ratio: str = "9:16"
    video_length_limit: Optional[str] = None
    max_duration_seconds: int = 60
    min_duration_seconds: int = 5
    target_duration_seconds: int = 30
    hashtag_count: Optional[str] = None
    recommended_hashtag_count: int = 4
    hook_rules: Optional[Dict[str, Any]] = None
    cta_style: Optional[str] = None
    width: int = 1080
    height: int = 1920
    fps: int = 30
    audio_codec: str = "aac"
    video_codec: str = "libx264"
    max_title_length: Optional[int] = None
    max_description_length: Optional[int] = None


class PlatformsConfig(BaseModel):
    platforms: Dict[str, PlatformSpec] = Field(default_factory=dict)


class AppSettings(BaseModel):
    """Runtime application settings loaded strictly from environment (.env)."""

    project_root: Path = PROJECT_ROOT
    groq_api_key: Optional[str] = Field(default=None)
    pixabay_api_key: Optional[str] = Field(default=None)
    groq_llm_model: str = "llama-3.3-70b-versatile"
    groq_whisper_model: str = "whisper-large-v3"
    log_level: str = "INFO"

    # Directories
    config_dir: Path = PROJECT_ROOT / "config"
    content_dir: Path = PROJECT_ROOT / "content"
    data_dir: Path = PROJECT_ROOT / "data"
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"
    inputs_dir: Path = PROJECT_ROOT / "data" / "inputs"
    outputs_dir: Path = PROJECT_ROOT / "data" / "outputs"
    logs_dir: Path = PROJECT_ROOT / "data" / "logs"

    def validate_groq_key(self) -> str:
        """Validate that GROQ_API_KEY is present in .env before making Groq calls."""
        if not self.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Please set it in your .env file in the project root.\n"
                "Example: GROQ_API_KEY=gsk_your_actual_groq_api_key_here\n"
                "Copy config/.env.example to .env to get started."
            )
        return self.groq_api_key

    def validate_pixabay_key(self) -> str:
        """Validate that PIXABAY_API_KEY is present in .env before querying Pixabay."""
        if not self.pixabay_api_key:
            raise ValueError(
                "PIXABAY_API_KEY is not set. Please set it in your .env file in the project root.\n"
                "Example: PIXABAY_API_KEY=your_actual_pixabay_api_key_here\n"
                "Copy config/.env.example to .env to get started."
            )
        return self.pixabay_api_key


# Cached singleton instances
_settings_instance: Optional[AppSettings] = None
_brand_instance: Optional[BrandConfig] = None
_platforms_instance: Optional[PlatformsConfig] = None


def get_settings() -> AppSettings:
    """Retrieve application settings loaded strictly from .env."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AppSettings(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            pixabay_api_key=os.getenv("PIXABAY_API_KEY"),
            groq_llm_model=os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"),
            groq_whisper_model=os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        # Ensure data directories exist
        _settings_instance.inputs_dir.mkdir(parents=True, exist_ok=True)
        _settings_instance.outputs_dir.mkdir(parents=True, exist_ok=True)
        _settings_instance.logs_dir.mkdir(parents=True, exist_ok=True)
    return _settings_instance


def get_brand_config(config_path: Optional[Path] = None) -> BrandConfig:
    """Load and parse brand.yaml into BrandConfig model."""
    global _brand_instance
    if _brand_instance is None or config_path is not None:
        path = config_path or (PROJECT_ROOT / "config" / "brand.yaml")
        if not path.exists():
            return BrandConfig()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        brand_data = data.get("brand", data)
        _brand_instance = BrandConfig.model_validate(brand_data)
    return _brand_instance


def get_platforms_config(config_path: Optional[Path] = None) -> PlatformsConfig:
    """Load and parse platforms.yaml into PlatformsConfig model."""
    global _platforms_instance
    if _platforms_instance is None or config_path is not None:
        path = config_path or (PROJECT_ROOT / "config" / "platforms.yaml")
        if not path.exists():
            return PlatformsConfig()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _platforms_instance = PlatformsConfig.model_validate(data)
    return _platforms_instance
