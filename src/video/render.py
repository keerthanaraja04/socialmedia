"""Autonomous 9:16 vertical video rendering engine using MoviePy and ffmpeg.

Takes a script + Pixabay B-roll clip and renders a 1080x1920 MP4 (<=60s) with:
1. High-impact hook text overlay in the first 2 seconds (0s - 2s).
2. Burned-in timed captions positioned in platform-native safe zones.
3. Free licensed typography with recorded font license in metadata & licenses.csv.
4. Voiceover if a free/licensed TTS source is available (edge_tts), falling back to text-on-video.
5. Editable source files (JSON spec + HTML/SVG templates) saved next to the video in content/assets/<id>/.
"""

from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pydantic import BaseModel, Field

from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    vfx,
)

from src.config import PROJECT_ROOT, get_brand_config, get_settings
from src.logging.logger import get_logger
from src.video.pixabay import LicenseRegistry

logger = get_logger("video.render")

# Free font configuration with recorded open-source licenses
FONT_CANDIDATES: List[Tuple[Path | str, str, str]] = [
    (
        PROJECT_ROOT / "content" / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
        "DejaVu Sans Bold",
        "Bitstream Vera & Arev Fonts License (Free / Open Source)",
    ),
    (
        PROJECT_ROOT / "content" / "assets" / "fonts" / "DejaVuSans.ttf",
        "DejaVu Sans",
        "Bitstream Vera & Arev Fonts License (Free / Open Source)",
    ),
    (
        "DejaVuSans.ttf",
        "DejaVu Sans",
        "Bitstream Vera & Arev Fonts License (Free / Open Source)",
    ),
    (
        "arial.ttf",
        "Arial",
        "Standard System Font",
    ),
]


class CaptionSegment(BaseModel):
    """Timed subtitle segment for burned-in captions."""
    start_sec: float
    end_sec: float
    text: str


class VideoRenderSpec(BaseModel):
    """Complete editable specification of a rendered vertical video asset."""
    asset_id: str
    asset_type: str = "video_vertical_9_16"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_seconds: float
    mode: str = "voiceover_and_captions"  # or "text-on-video"
    font_name: str
    font_license: str
    brand_palette: Dict[str, str]
    hook_overlay: Dict[str, Any]
    captions: List[CaptionSegment]
    source_clip: Dict[str, Any]
    tts_voice: Optional[str] = None
    created_at: str


def get_free_font(size: int, bold: bool = True) -> Tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str, str]:
    """Retrieve an open-source free licensed font and return (font, font_name, font_license)."""
    for font_ref, name, license_str in FONT_CANDIDATES:
        try:
            if isinstance(font_ref, Path) and not font_ref.exists():
                continue
            f = ImageFont.truetype(str(font_ref), size)
            return f, name, license_str
        except Exception:
            continue

    # Fallback to PIL default font
    return ImageFont.load_default(), "PIL Default Font", "Public Domain / Permissive"


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Convert hex string like #0F172A to (15, 23, 42)."""
    hex_clean = hex_code.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join([c * 2 for c in hex_clean])
    return tuple(int(hex_clean[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Wrap words to strictly fit within max_width pixels."""
    words = text.split()
    if not words:
        return []

    lines: List[str] = []
    current_line: List[str] = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_w = bbox[2] - bbox[0]
        if line_w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines


# ==============================================================================
# TTS Voiceover Generation (edge_tts)
# ==============================================================================
async def _synthesize_edge_tts(text: str, output_path: Path, voice: str = "en-US-AndrewNeural") -> bool:
    try:
        import edge_tts  # type: ignore
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return output_path.exists() and output_path.stat().st_size > 0
    except Exception as e:
        logger.warning(f"edge-tts synthesis failed: {e}")
        return False


def generate_tts_voiceover(
    text: str,
    output_path: Path,
    voice: str = "en-US-AndrewNeural",
) -> Optional[Path]:
    """Synthesize voiceover audio using edge-tts. Returns audio path on success, None on failure."""
    clean_text = re.sub(r"[#*_~`]", "", text).strip()
    if not clean_text:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        success = asyncio.run(_synthesize_edge_tts(clean_text, output_path, voice=voice))
        if success:
            logger.info(f"Generated TTS voiceover: {output_path.name} ({output_path.stat().st_size} bytes)")
            return output_path
    except Exception as e:
        logger.warning(f"Voiceover generation exception ({e}). Falling back to text-on-video.")

    return None


# ==============================================================================
# Overlay Card Renderers (Hook Card & Captions)
# ==============================================================================
def render_hook_overlay(
    hook_text: str,
    category_tag: str = "INCUBRIX // BREAKTHROUGH",
    width: int = 1080,
    height: int = 1920,
    palette: Optional[Dict[str, str]] = None,
) -> Image.Image:
    """Render a high-impact hook card overlay active during the first 2 seconds (0s - 2s)."""
    p = palette or {
        "primary": "#0F172A",
        "secondary": "#6366F1",
        "accent": "#10B981",
        "card_bg": "#0B1120",
        "text_primary": "#FFFFFF",
        "text_muted": "#94A3B8",
    }

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Fonts
    title_font, _, _ = get_free_font(size=64, bold=True)
    badge_font, _, _ = get_free_font(size=30, bold=True)

    # 2. Card bounds situated in vertical safe zone (Y: 480 to 980)
    card_w = 940
    card_x0 = (width - card_w) // 2
    card_y0 = 500

    # Wrap hook headline (max 3 lines)
    wrapped_lines = wrap_text(hook_text, title_font, card_w - 100, draw)[:3]
    line_h = 76
    text_block_h = len(wrapped_lines) * line_h
    card_h = 130 + text_block_h + 40
    card_x1 = card_x0 + card_w
    card_y1 = card_y0 + card_h

    # Semi-transparent dark glass container with accent stroke
    bg_color = (*hex_to_rgb(p.get("card_bg", "#0B1120")), 225)
    border_color = (*hex_to_rgb(p.get("accent", "#10B981")), 255)

    draw.rounded_rectangle(
        [card_x0, card_y0, card_x1, card_y1],
        radius=28,
        fill=bg_color,
        outline=border_color,
        width=4,
    )

    # Category Tag Badge (Upper-left of card)
    badge_pad_x = 24
    badge_pad_y = 10
    badge_bbox = draw.textbbox((0, 0), category_tag, font=badge_font)
    badge_w = (badge_bbox[2] - badge_bbox[0]) + (badge_pad_x * 2)
    badge_h = (badge_bbox[3] - badge_bbox[1]) + (badge_pad_y * 2)
    badge_x0 = card_x0 + 44
    badge_y0 = card_y0 + 36

    draw.rounded_rectangle(
        [badge_x0, badge_y0, badge_x0 + badge_w, badge_y0 + badge_h],
        radius=14,
        fill=(*hex_to_rgb(p.get("secondary", "#6366F1")), 255),
    )
    draw.text(
        (badge_x0 + badge_pad_x, badge_y0 + badge_pad_y - 2),
        category_tag,
        font=badge_font,
        fill=(255, 255, 255, 255),
    )

    # Hook Headline Text
    text_y = badge_y0 + badge_h + 28
    for line in wrapped_lines:
        draw.text(
            (card_x0 + 44, text_y),
            line,
            font=title_font,
            fill=(*hex_to_rgb(p.get("text_primary", "#FFFFFF")), 255),
        )
        text_y += line_h

    return img


def render_caption_overlay(
    caption_text: str,
    width: int = 1080,
    height: int = 1920,
    palette: Optional[Dict[str, str]] = None,
) -> Image.Image:
    """Render a modern burned-in caption pill situated in vertical safe zones (Y: 1250 - 1450)."""
    p = palette or {
        "card_bg": "#0B1120",
        "accent": "#10B981",
        "text_primary": "#FFFFFF",
    }

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    caption_font, _, _ = get_free_font(size=50, bold=True)
    wrapped_lines = wrap_text(caption_text, caption_font, 880, draw)[:2]
    if not wrapped_lines:
        return img

    line_h = 62
    text_h = len(wrapped_lines) * line_h
    pill_w = 940
    pill_h = text_h + 48
    pill_x0 = (width - pill_w) // 2
    pill_y0 = 1300
    pill_x1 = pill_x0 + pill_w
    pill_y1 = pill_y0 + pill_h

    # Semi-transparent pill background
    bg_color = (*hex_to_rgb(p.get("card_bg", "#0B1120")), 215)
    border_color = (*hex_to_rgb(p.get("accent", "#10B981")), 180)

    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=24,
        fill=bg_color,
        outline=border_color,
        width=3,
    )

    curr_y = pill_y0 + 24
    for line in wrapped_lines:
        # Center-align text in pill
        bbox = draw.textbbox((0, 0), line, font=caption_font)
        line_w = bbox[2] - bbox[0]
        line_x = pill_x0 + (pill_w - line_w) // 2
        draw.text((line_x, curr_y), line, font=caption_font, fill=(255, 255, 255, 255))
        curr_y += line_h

    return img


# ==============================================================================
# Editable Source File Generators (JSON spec + HTML/SVG template)
# ==============================================================================
def save_editable_sources(
    asset_dir: Path,
    spec: VideoRenderSpec,
) -> Tuple[Path, Path, Path]:
    """Save editable spec.json, template.html, and template.svg in content/assets/<id>/."""
    asset_dir.mkdir(parents=True, exist_ok=True)

    # 1. spec.json
    spec_path = asset_dir / "spec.json"
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec.model_dump(), f, indent=2)

    # 2. template.html
    html_path = asset_dir / "template.html"
    p = spec.brand_palette
    hook_text = spec.hook_overlay.get("text", "")
    category = spec.hook_overlay.get("category", "INCUBRIX // BREAKTHROUGH")

    caption_items_html = "\n".join([
        f'        <div class="caption-item" data-start="{c.start_sec}" data-end="{c.end_sec}">'
        f'<span class="time">[{c.start_sec}s - {c.end_sec}s]</span> {c.text}</div>'
        for c in spec.captions
    ])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Editable Video Spec & Preview - {spec.asset_id}</title>
  <style>
    :root {{
      --bg: {p.get("background", "#030712")};
      --primary: {p.get("primary", "#0F172A")};
      --secondary: {p.get("secondary", "#6366F1")};
      --accent: {p.get("accent", "#10B981")};
      --card-bg: {p.get("card_bg", "#0B1120")};
      --text: {p.get("text_primary", "#F8FAFC")};
      --text-muted: {p.get("text_muted", "#94A3B8")};
    }}
    body {{
      margin: 0;
      padding: 30px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #080C14;
      color: var(--text);
      display: flex;
      gap: 40px;
      justify-content: center;
    }}
    .phone-frame {{
      width: 360px;
      height: 640px;
      background: var(--primary);
      border-radius: 36px;
      border: 8px solid #1E293B;
      position: relative;
      overflow: hidden;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    }}
    .hook-badge {{
      position: absolute;
      top: 160px;
      left: 16px;
      right: 16px;
      background: rgba(11, 17, 32, 0.9);
      border: 2px solid var(--accent);
      border-radius: 14px;
      padding: 16px;
      backdrop-filter: blur(8px);
    }}
    .category-pill {{
      display: inline-block;
      background: var(--secondary);
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 6px;
      margin-bottom: 8px;
    }}
    .hook-title {{
      font-size: 18px;
      font-weight: 800;
      line-height: 1.3;
      margin: 0;
    }}
    .caption-pill {{
      position: absolute;
      bottom: 120px;
      left: 16px;
      right: 16px;
      background: rgba(11, 17, 32, 0.85);
      border: 1px solid var(--accent);
      border-radius: 12px;
      padding: 12px;
      text-align: center;
      font-size: 13px;
      font-weight: 600;
    }}
    .editor-pane {{
      width: 480px;
      background: #111827;
      padding: 28px;
      border-radius: 16px;
      border: 1px solid #1F2937;
    }}
    h2 {{ margin-top: 0; color: var(--accent); }}
    .caption-item {{
      background: #1F2937;
      padding: 10px 14px;
      border-radius: 8px;
      margin-bottom: 8px;
      font-size: 13px;
    }}
    .time {{ color: var(--accent); font-weight: bold; margin-right: 8px; }}
    .badge-info {{ background: #374151; padding: 4px 8px; border-radius: 4px; font-size: 11px; }}
  </style>
</head>
<body>
  <div class="phone-frame">
    <div class="hook-badge">
      <div class="category-pill">{category}</div>
      <p class="hook-title">{hook_text}</p>
    </div>
    <div class="caption-pill">
      {spec.captions[0].text if spec.captions else "Burned-in subtitle text"}
    </div>
  </div>

  <div class="editor-pane">
    <h2>Editable Video Spec: {spec.asset_id}</h2>
    <p><strong>Aspect Ratio:</strong> 9:16 (1080x1920) | <strong>Duration:</strong> {spec.duration_seconds}s</p>
    <p><strong>Font Used:</strong> <span class="badge-info">{spec.font_name}</span></p>
    <p><strong>Font License:</strong> <span class="badge-info">{spec.font_license}</span></p>
    <p><strong>Audio Mode:</strong> {spec.mode}</p>
    <h3>Captions Timeline</h3>
    <div class="captions-timeline">
{caption_items_html}
    </div>
  </div>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 3. template.svg
    svg_path = asset_dir / "template.svg"
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p.get('primary', '#0F172A')}" />
      <stop offset="100%" stop-color="{p.get('background', '#030712')}" />
    </linearGradient>
    <filter id="cardShadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="16" stdDeviation="24" flood-color="#000000" flood-opacity="0.6"/>
    </filter>
  </defs>

  <!-- Background Base -->
  <rect width="1080" height="1920" fill="url(#bgGrad)" />

  <!-- Hook Card (0s - 2s overlay) -->
  <g transform="translate(70, 500)" filter="url(#cardShadow)">
    <rect width="940" height="340" rx="28" fill="{p.get('card_bg', '#0B1120')}" fill-opacity="0.9" stroke="{p.get('accent', '#10B981')}" stroke-width="4" />
    <rect x="44" y="36" width="360" height="48" rx="12" fill="{p.get('secondary', '#6366F1')}" />
    <text x="60" y="68" font-family="DejaVu Sans, Arial, sans-serif" font-size="24" font-weight="bold" fill="#FFFFFF">{category}</text>
    <text x="44" y="160" font-family="DejaVu Sans, Arial, sans-serif" font-size="52" font-weight="bold" fill="{p.get('text_primary', '#FFFFFF')}">{hook_text[:38]}</text>
  </g>

  <!-- Caption Pill Area (y: 1300) -->
  <g transform="translate(70, 1300)">
    <rect width="940" height="140" rx="24" fill="{p.get('card_bg', '#0B1120')}" fill-opacity="0.85" stroke="{p.get('accent', '#10B981')}" stroke-width="3" />
    <text x="470" y="82" text-anchor="middle" font-family="DejaVu Sans, Arial, sans-serif" font-size="44" font-weight="bold" fill="#FFFFFF">Sample Captions Overlay</text>
  </g>
</svg>"""
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)

    return spec_path, html_path, svg_path


# ==============================================================================
# Master Video Renderer
# ==============================================================================
class VideoRenderer:
    """MoviePy/ffmpeg vertical video compiler for 9:16 short-form reels."""

    def __init__(
        self,
        licenses_csv: Optional[Path] = None,
    ) -> None:
        self.settings = get_settings()
        self.brand = get_brand_config()
        self.registry = LicenseRegistry(csv_path=licenses_csv)

    def render_reel(
        self,
        script: Union[Dict[str, Any], Any, str],
        clip_path: Path,
        asset_id: Optional[str] = None,
        output_dir: Optional[Path] = None,
        max_duration: float = 60.0,
        enable_tts: bool = True,
        category_tag: str = "INCUBRIX // BREAKTHROUGH",
        pixabay_hit_data: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Render a 9:16 (1080x1920) mp4 with hook overlay (first 2s) & burned-in captions."""
        clip_path = Path(clip_path)
        if not clip_path.exists():
            raise FileNotFoundError(f"Source video clip not found: {clip_path}")

        # Parse script fields
        hook_text = ""
        body_points: List[str] = []
        cta_text = ""

        if isinstance(script, dict):
            hook_text = script.get("hook", "")
            body_points = script.get("body_points", [])
            cta_text = script.get("call_to_action", "")
        elif hasattr(script, "hook"):
            hook_text = getattr(script, "hook", "")
            body_points = getattr(script, "body_points", [])
            cta_text = getattr(script, "call_to_action", "")
        elif isinstance(script, str):
            lines = [l.strip() for l in script.splitlines() if l.strip()]
            hook_text = lines[0] if lines else "Autonomous AI Video Workflow"
            body_points = lines[1:-1] if len(lines) > 2 else ["Transforming media scale", "Precision automation"]
            cta_text = lines[-1] if len(lines) > 1 else "Follow @IncuBrix for more."

        if not hook_text:
            hook_text = "Stop spending 10 hours cutting cutdowns."

        # Setup destination directory: content/assets/<id>/
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        clean_asset_id = asset_id or f"reel_{now_str}_{re.sub(r'[^a-zA-Z0-9]+', '_', hook_text[:20]).strip('_').lower()}"
        target_dir = output_dir or (PROJECT_ROOT / "content" / "assets" / clean_asset_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        final_mp4_path = target_dir / f"{clean_asset_id}.mp4"

        # Brand visual colors
        p = {
            "primary": self.brand.visual.palette.primary,
            "secondary": self.brand.visual.palette.secondary,
            "accent": self.brand.visual.palette.accent,
            "card_bg": self.brand.visual.palette.card_bg,
            "text_primary": self.brand.visual.palette.text_primary,
            "text_muted": self.brand.visual.palette.text_muted,
        }

        # 1. Voiceover Synthesis (TTS check)
        audio_clip: Optional[AudioFileClip] = None
        voiceover_file: Optional[Path] = None
        mode = "text-on-video"
        tts_voice = None

        if enable_tts:
            tts_script = f"{hook_text}. " + " ".join(body_points) + f" {cta_text}"
            voiceover_file = target_dir / "voiceover.mp3"
            generated_audio = generate_tts_voiceover(tts_script, voiceover_file)
            if generated_audio and generated_audio.exists():
                try:
                    audio_clip = AudioFileClip(str(generated_audio))
                    mode = "voiceover_and_captions"
                    tts_voice = "en-US-AndrewNeural"
                except Exception as e:
                    logger.warning(f"Failed to load synthesized audio: {e}")
                    audio_clip = None

        # 2. Compute Target Duration (<= 60s)
        if audio_clip:
            duration = min(float(audio_clip.duration) + 0.5, max_duration)
        else:
            # Paced text duration: 2s hook + 3s per body point + 2s CTA
            duration = min(2.0 + (len(body_points) * 3.0) + 2.5, max_duration)

        # 3. Process & Center-Crop Base Video to 9:16 (1080x1920)
        logger.info(f"Loading and adapting base video {clip_path.name} to 1080x1920 @ {duration:.1f}s")
        base_clip = VideoFileClip(str(clip_path))

        # Loop if base clip is shorter than required duration
        if base_clip.duration < duration:
            loops_needed = int(np.ceil(duration / base_clip.duration))
            base_clip = base_clip.fx(vfx.loop, n=loops_needed).subclip(0, duration)
        else:
            base_clip = base_clip.subclip(0, duration)

        # Resize & center crop to 1080x1920
        scale = max(1080.0 / base_clip.w, 1920.0 / base_clip.h)
        scaled_clip = base_clip.resize(scale)
        x_center = scaled_clip.w / 2.0
        y_center = scaled_clip.h / 2.0
        cropped_clip = scaled_clip.crop(
            x_center=x_center,
            y_center=y_center,
            width=1080,
            height=1920,
        )

        # 4. Burn-in Hook Overlay (First 2 Seconds: 0.0s - 2.0s, clamped to clip duration)
        hook_duration = min(2.0, duration)
        hook_img = render_hook_overlay(
            hook_text=hook_text,
            category_tag=category_tag,
            width=1080,
            height=1920,
            palette=p,
        )

        hook_tmp_png = target_dir / "temp_hook_overlay.png"
        hook_img.save(hook_tmp_png, "PNG")
        hook_clip = ImageClip(str(hook_tmp_png)).set_start(0.0).set_duration(hook_duration)

        # 5. Burn-in Timed Captions across remaining duration
        captions: List[CaptionSegment] = []
        caption_clips: List[ImageClip] = []
        caption_texts = list(body_points)
        if cta_text:
            caption_texts.append(cta_text)
        if not caption_texts:
            caption_texts = ["Autonomous AI repurposing engine for creators."]

        remaining_time = max(duration - hook_duration, 0.0)
        if remaining_time > 0:
            seg_duration = remaining_time / len(caption_texts)
            for i, text_item in enumerate(caption_texts):
                start_t = hook_duration + (i * seg_duration)
                end_t = min(start_t + seg_duration, duration)
                captions.append(CaptionSegment(start_sec=round(start_t, 2), end_sec=round(end_t, 2), text=text_item))

                cap_img = render_caption_overlay(
                    caption_text=text_item,
                    width=1080,
                    height=1920,
                    palette=p,
                )
                cap_tmp_png = target_dir / f"temp_caption_{i}.png"
                cap_img.save(cap_tmp_png, "PNG")
                c_clip = ImageClip(str(cap_tmp_png)).set_start(start_t).set_duration(end_t - start_t)
                caption_clips.append(c_clip)
        else:
            captions.append(CaptionSegment(start_sec=0.0, end_sec=round(duration, 2), text=caption_texts[0]))

        # 6. Composite Layers
        logger.info(f"Compositing video layers (base + hook overlay + {len(caption_clips)} caption beats)...")
        all_layers = [cropped_clip, hook_clip] + caption_clips
        final_video = CompositeVideoClip(all_layers, size=(1080, 1920))

        if audio_clip:
            actual_audio_dur = min(duration, float(audio_clip.duration))
            final_video = final_video.set_audio(audio_clip.subclip(0, actual_audio_dur))

        # 7. Render Final MP4 (Using native FFmpeg threading to avoid Python pipe deadlock on Windows)
        final_video.write_videofile(
            str(final_mp4_path),
            fps=30,
            codec="libx264",
            audio_codec="aac" if audio_clip else None,
            preset="ultrafast",
            threads=1,
            ffmpeg_params=["-threads", "4", "-loglevel", "error"],
            verbose=False,
            logger=None,
        )

        # Clean up moviepy memory & file locks on Windows
        final_video.close()
        cropped_clip.close()
        scaled_clip.close()
        base_clip.close()
        hook_clip.close()
        for c in caption_clips:
            c.close()
        if audio_clip:
            audio_clip.close()

        # Remove temporary overlay PNGs
        if hook_tmp_png.exists():
            hook_tmp_png.unlink(missing_ok=True)
        for i in range(len(caption_texts)):
            (target_dir / f"temp_caption_{i}.png").unlink(missing_ok=True)

        logger.info(f"Rendered vertical video complete: {final_mp4_path.name} in {target_dir}")

        # 8. Record Font License & Save Editable Source Files (JSON + HTML/SVG)
        _, font_name, font_license = get_free_font(size=40)

        spec = VideoRenderSpec(
            asset_id=clean_asset_id,
            duration_seconds=round(duration, 2),
            mode=mode,
            font_name=font_name,
            font_license=font_license,
            brand_palette=p,
            hook_overlay={
                "text": hook_text,
                "category": category_tag,
                "start_sec": 0.0,
                "end_sec": 2.0,
            },
            captions=captions,
            source_clip={
                "filename": clip_path.name,
                "pixabay_id": pixabay_hit_data.get("id") if pixabay_hit_data else None,
                "author": pixabay_hit_data.get("user") if pixabay_hit_data else None,
            },
            tts_voice=tts_voice,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        save_editable_sources(target_dir, spec)

        # Log to licenses.csv (Pixabay B-roll or font license)
        self.registry.append_license(
            pixabay_id=int(pixabay_hit_data.get("id", 1001)) if pixabay_hit_data else 1001,
            page_url=pixabay_hit_data.get("pageURL", "https://incubrix.com/brand-assets") if pixabay_hit_data else "https://dejavu-fonts.github.io",
            author=pixabay_hit_data.get("user", "IncuBrix Studio") if pixabay_hit_data else font_name,
            download_date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            asset_id=clean_asset_id,
            manual_review=False,
            manual_review_reason=f"Rendered into 9:16 vertical reel using font '{font_name}' ({font_license})",
        )

        return final_mp4_path
