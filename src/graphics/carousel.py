"""Graphics design and carousel slide rendering engine using Pillow (PIL).

Renders high-engagement social carousel slides at 1080x1350 (4:5 portrait)
tailored from brand colors, typography, and safe zones.
For every asset, saves editable source files (JSON spec + HTML/SVG templates)
next to the final rendered slide images in content/assets/<id>/.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import BaseModel, Field

from src.config import PROJECT_ROOT, get_brand_config, get_settings
from src.logging.logger import get_logger
from src.video.render import get_free_font, hex_to_rgb, wrap_text

logger = get_logger("graphics.carousel")

# Standard 4:5 vertical carousel dimensions for Instagram & LinkedIn
CAROUSEL_WIDTH = 1080
CAROUSEL_HEIGHT = 1350


class CarouselSlideData(BaseModel):
    """Specification of an individual carousel slide."""
    slide_number: int = 1
    slide_type: str = "content"  # "cover", "content", "cta"
    category: str = "CREATOR GUIDE"
    title: str
    body_points: List[str] = Field(default_factory=list)
    tip: Optional[str] = None
    cta_text: Optional[str] = None


class CarouselAssetSpec(BaseModel):
    """Complete editable specification for a multi-slide carousel asset."""
    asset_id: str
    asset_type: str = "carousel_1080x1350"
    width: int = CAROUSEL_WIDTH
    height: int = CAROUSEL_HEIGHT
    slides_count: int
    font_name: str
    font_license: str
    brand_palette: Dict[str, str]
    slides: List[CarouselSlideData]
    created_at: str


class CarouselRenderer:
    """Renders 1080x1350 carousel slides with Pillow and generates editable sources."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.brand = get_brand_config()

    def get_palette(self) -> Dict[str, str]:
        """Load brand color tokens."""
        return {
            "primary": self.brand.visual.palette.primary,
            "secondary": self.brand.visual.palette.secondary,
            "accent": self.brand.visual.palette.accent,
            "background": self.brand.visual.palette.background,
            "card_bg": self.brand.visual.palette.card_bg,
            "text_primary": self.brand.visual.palette.text_primary,
            "text_muted": self.brand.visual.palette.text_muted,
        }

    # --------------------------------------------------------------------------
    # Slide 1: Cover Slide
    # --------------------------------------------------------------------------
    def render_cover_slide(
        self,
        slide: CarouselSlideData,
        total_slides: int,
        palette: Dict[str, str],
    ) -> Image.Image:
        """Render the primary hook/cover slide with bold typography & swipe cue."""
        img = Image.new("RGB", (CAROUSEL_WIDTH, CAROUSEL_HEIGHT), hex_to_rgb(palette.get("background", "#030712")))
        draw = ImageDraw.Draw(img)

        # 1. Subtle background glow / decorative accent
        accent_rgb = hex_to_rgb(palette.get("accent", "#10B981"))
        draw.ellipse([800, -100, 1200, 300], fill=(*accent_rgb, 20) if hasattr(img, "mode") and img.mode == "RGBA" else None)

        # 2. Category Pill Badge (Top Left: x=80, y=90)
        badge_font, _, _ = get_free_font(size=28, bold=True)
        cat_text = f"🔥 {slide.category.upper()}"
        bbox = draw.textbbox((0, 0), cat_text, font=badge_font)
        bw = (bbox[2] - bbox[0]) + 40
        bh = (bbox[3] - bbox[1]) + 20
        draw.rounded_rectangle([80, 90, 80 + bw, 90 + bh], radius=12, fill=hex_to_rgb(palette.get("secondary", "#6366F1")))
        draw.text((100, 100), cat_text, font=badge_font, fill=(255, 255, 255))

        # Brand Watermark (Top Right)
        wm_font, _, _ = get_free_font(size=26, bold=True)
        draw.text((820, 100), "INCUBRIX // CO-PILOT", font=wm_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))

        # 3. Main Hook Headline (Center-weighted)
        title_font, _, _ = get_free_font(size=72, bold=True)
        wrapped_title = wrap_text(slide.title, title_font, 920, draw)
        start_y = 360
        line_h = 88
        for line in wrapped_title[:4]:
            draw.text((80, start_y), line, font=title_font, fill=hex_to_rgb(palette.get("text_primary", "#F8FAFC")))
            start_y += line_h

        # 4. Subtitle / Body Context Card
        if slide.body_points:
            subtitle_font, _, _ = get_free_font(size=36, bold=False)
            card_y0 = start_y + 40
            card_h = 160
            draw.rounded_rectangle(
                [80, card_y0, 1000, card_y0 + card_h],
                radius=20,
                fill=hex_to_rgb(palette.get("card_bg", "#1E293B")),
                outline=hex_to_rgb(palette.get("accent", "#10B981")),
                width=2,
            )
            sub_text = slide.body_points[0]
            wrapped_sub = wrap_text(sub_text, subtitle_font, 880, draw)[:2]
            sy = card_y0 + 36
            for sline in wrapped_sub:
                draw.text((120, sy), sline, font=subtitle_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))
                sy += 48

        # 5. Bottom Swipe Action Bar
        bottom_y = CAROUSEL_HEIGHT - 120
        draw.line([80, bottom_y - 20, 1000, bottom_y - 20], fill=hex_to_rgb(palette.get("card_bg", "#1E293B")), width=2)

        swipe_font, _, _ = get_free_font(size=30, bold=True)
        draw.text((80, bottom_y), "SWIPE FOR BLUEPRINT ➔", font=swipe_font, fill=hex_to_rgb(palette.get("accent", "#10B981")))

        # Slide counter dots
        draw.text((920, bottom_y), f"1 / {total_slides}", font=swipe_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))

        return img

    # --------------------------------------------------------------------------
    # Slides 2..N-1: Content & Value Slides
    # --------------------------------------------------------------------------
    def render_content_slide(
        self,
        slide: CarouselSlideData,
        total_slides: int,
        palette: Dict[str, str],
    ) -> Image.Image:
        """Render value/step slide with structured card containers."""
        img = Image.new("RGB", (CAROUSEL_WIDTH, CAROUSEL_HEIGHT), hex_to_rgb(palette.get("background", "#030712")))
        draw = ImageDraw.Draw(img)

        # Header: Step badge & Counter
        step_str = f"STEP {slide.slide_number:02d}"
        badge_font, _, _ = get_free_font(size=28, bold=True)
        draw.text((80, 90), step_str, font=badge_font, fill=hex_to_rgb(palette.get("accent", "#10B981")))

        prog_font, _, _ = get_free_font(size=26, bold=False)
        draw.text((900, 90), f"{slide.slide_number} / {total_slides}", font=prog_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))

        # Slide Title
        title_font, _, _ = get_free_font(size=56, bold=True)
        wrapped_title = wrap_text(slide.title, title_font, 920, draw)
        curr_y = 160
        for line in wrapped_title[:2]:
            draw.text((80, curr_y), line, font=title_font, fill=hex_to_rgb(palette.get("text_primary", "#F8FAFC")))
            curr_y += 72

        curr_y += 30

        # Main Value Card
        card_x0 = 80
        card_w = 920
        card_h = 560
        draw.rounded_rectangle(
            [card_x0, curr_y, card_x0 + card_w, curr_y + card_h],
            radius=24,
            fill=hex_to_rgb(palette.get("card_bg", "#1E293B")),
            outline=hex_to_rgb(palette.get("secondary", "#6366F1")),
            width=2,
        )

        body_font, _, _ = get_free_font(size=34, bold=False)
        item_y = curr_y + 48
        for pt in slide.body_points[:4]:
            # Accent bullet circle
            draw.ellipse([card_x0 + 44, item_y + 8, card_x0 + 64, item_y + 28], fill=hex_to_rgb(palette.get("accent", "#10B981")))
            wrapped_pt = wrap_text(pt, body_font, 780, draw)
            for pline in wrapped_pt[:2]:
                draw.text((card_x0 + 84, item_y), pline, font=body_font, fill=hex_to_rgb(palette.get("text_primary", "#F8FAFC")))
                item_y += 46
            item_y += 24

        curr_y += card_h + 36

        # Tip Box (if provided)
        if slide.tip:
            tip_h = 160
            draw.rounded_rectangle(
                [card_x0, curr_y, card_x0 + card_w, curr_y + tip_h],
                radius=18,
                fill=hex_to_rgb(palette.get("primary", "#0F172A")),
                outline=hex_to_rgb(palette.get("accent", "#10B981")),
                width=1,
            )
            tip_font, _, _ = get_free_font(size=28, bold=True)
            draw.text((card_x0 + 36, curr_y + 24), "💡 PRO TIP", font=tip_font, fill=hex_to_rgb(palette.get("accent", "#10B981")))

            tip_body_font, _, _ = get_free_font(size=28, bold=False)
            wrapped_tip = wrap_text(slide.tip, tip_body_font, 840, draw)[:2]
            ty = curr_y + 64
            for tline in wrapped_tip:
                draw.text((card_x0 + 36, ty), tline, font=tip_body_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))
                ty += 38

        # Footer
        bottom_y = CAROUSEL_HEIGHT - 90
        footer_font, _, _ = get_free_font(size=24, bold=False)
        draw.text((80, bottom_y), "@IncuBrix // Automated Repurposing", font=footer_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))

        return img

    # --------------------------------------------------------------------------
    # Slide N: CTA Slide
    # --------------------------------------------------------------------------
    def render_cta_slide(
        self,
        slide: CarouselSlideData,
        total_slides: int,
        palette: Dict[str, str],
    ) -> Image.Image:
        """Render high-conversion call-to-action slide."""
        img = Image.new("RGB", (CAROUSEL_WIDTH, CAROUSEL_HEIGHT), hex_to_rgb(palette.get("background", "#030712")))
        draw = ImageDraw.Draw(img)

        # Category pill
        badge_font, _, _ = get_free_font(size=28, bold=True)
        draw.rounded_rectangle([80, 90, 360, 140], radius=12, fill=hex_to_rgb(palette.get("accent", "#10B981")))
        draw.text((104, 102), "SAVE THIS POST", font=badge_font, fill=(0, 0, 0))

        # Title
        title_font, _, _ = get_free_font(size=64, bold=True)
        wrapped_title = wrap_text(slide.title or "Ready to scale your content pipeline?", title_font, 920, draw)
        curr_y = 220
        for line in wrapped_title[:3]:
            draw.text((80, curr_y), line, font=title_font, fill=hex_to_rgb(palette.get("text_primary", "#F8FAFC")))
            curr_y += 82

        curr_y += 40

        # Action Cards
        card_w = 920
        card_h = 420
        draw.rounded_rectangle(
            [80, curr_y, 80 + card_w, curr_y + card_h],
            radius=24,
            fill=hex_to_rgb(palette.get("card_bg", "#1E293B")),
            outline=hex_to_rgb(palette.get("secondary", "#6366F1")),
            width=3,
        )

        cta_title_font, _, _ = get_free_font(size=40, bold=True)
        draw.text((120, curr_y + 44), "IncuBrix Engine Access", font=cta_title_font, fill=hex_to_rgb(palette.get("accent", "#10B981")))

        cta_body_font, _, _ = get_free_font(size=32, bold=False)
        bullets = slide.body_points or [
            "Turn 1 video podcast into 15+ ready-to-post assets",
            "Whisper LPU cloud transcription in seconds",
            "Brand safety & compliance checks on every asset",
        ]
        by = curr_y + 116
        for b in bullets[:3]:
            draw.text((120, by), f"✓ {b}", font=cta_body_font, fill=hex_to_rgb(palette.get("text_primary", "#F8FAFC")))
            by += 54

        # Primary Button Badge
        btn_y0 = curr_y + card_h + 50
        draw.rounded_rectangle(
            [80, btn_y0, 1000, btn_y0 + 110],
            radius=20,
            fill=hex_to_rgb(palette.get("secondary", "#6366F1")),
        )
        btn_font, _, _ = get_free_font(size=36, bold=True)
        btn_text = slide.cta_text or "Follow @IncuBrix & Visit incubrix.ai"
        btn_bbox = draw.textbbox((0, 0), btn_text, font=btn_font)
        bw = btn_bbox[2] - btn_bbox[0]
        bx = 80 + (920 - bw) // 2
        draw.text((bx, btn_y0 + 34), btn_text, font=btn_font, fill=(255, 255, 255))

        # Bottom watermark
        footer_font, _, _ = get_free_font(size=24, bold=False)
        draw.text((80, CAROUSEL_HEIGHT - 90), "IncuBrix // Autonomous Content Engine", font=footer_font, fill=hex_to_rgb(palette.get("text_muted", "#94A3B8")))

        return img

    # --------------------------------------------------------------------------
    # Editable Source Exporters (spec.json + template.html/svg)
    # --------------------------------------------------------------------------
    def save_carousel_sources(
        self,
        asset_dir: Path,
        spec: CarouselAssetSpec,
    ) -> Tuple[Path, Path, Path]:
        """Save spec.json, interactive template.html, and template.svg in content/assets/<id>/."""
        asset_dir.mkdir(parents=True, exist_ok=True)

        # 1. spec.json
        spec_path = asset_dir / "spec.json"
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec.model_dump(), f, indent=2)

        # 2. template.html (Interactive multi-slide viewer)
        html_path = asset_dir / "template.html"
        p = spec.brand_palette

        slides_html = ""
        for s in spec.slides:
            bullets_html = "".join([f"<li>{pt}</li>" for pt in s.body_points])
            slides_html += f"""
        <div class="slide-card">
          <div class="slide-badge">{s.category} // SLIDE {s.slide_number}</div>
          <h2 class="slide-title">{s.title}</h2>
          <ul class="slide-points">{bullets_html}</ul>
          {f'<div class="slide-tip"><strong>PRO TIP:</strong> {s.tip}</div>' if s.tip else ''}
          {f'<div class="slide-cta">{s.cta_text}</div>' if s.cta_text else ''}
        </div>"""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Editable Carousel Spec: {spec.asset_id}</title>
  <style>
    :root {{
      --bg: {p.get("background", "#030712")};
      --primary: {p.get("primary", "#0F172A")};
      --secondary: {p.get("secondary", "#6366F1")};
      --accent: {p.get("accent", "#10B981")};
      --card-bg: {p.get("card_bg", "#1E293B")};
      --text: {p.get("text_primary", "#F8FAFC")};
      --text-muted: {p.get("text_muted", "#94A3B8")};
    }}
    body {{
      margin: 0;
      padding: 40px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .header {{ margin-bottom: 30px; border-bottom: 1px solid var(--card-bg); padding-bottom: 20px; }}
    .badge {{ background: var(--secondary); padding: 4px 10px; border-radius: 6px; font-size: 12px; }}
    .carousel-container {{
      display: flex;
      gap: 24px;
      overflow-x: auto;
      padding-bottom: 20px;
    }}
    .slide-card {{
      min-width: 320px;
      max-width: 320px;
      height: 400px;
      background: var(--card-bg);
      border: 2px solid var(--secondary);
      border-radius: 20px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .slide-badge {{ color: var(--accent); font-size: 11px; font-weight: bold; }}
    .slide-title {{ font-size: 18px; margin: 10px 0; line-height: 1.3; }}
    .slide-points {{ padding-left: 18px; font-size: 13px; color: var(--text-muted); line-height: 1.6; }}
    .slide-tip {{ background: var(--primary); border: 1px solid var(--accent); padding: 8px 12px; border-radius: 8px; font-size: 11px; }}
    .slide-cta {{ background: var(--secondary); text-align: center; padding: 10px; border-radius: 8px; font-weight: bold; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>Editable Carousel: {spec.asset_id}</h1>
    <p>Ratio: 4:5 (1080x1350) | Total Slides: {spec.slides_count} | Font: <span class="badge">{spec.font_name}</span> ({spec.font_license})</p>
  </div>
  <div class="carousel-container">
{slides_html}
  </div>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # 3. template.svg (Cover Slide Vector Template)
        svg_path = asset_dir / "template.svg"
        first_slide = spec.slides[0] if spec.slides else CarouselSlideData(slide_number=1, title="Master Blueprint")

        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350">
  <defs>
    <linearGradient id="bgGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{p.get('primary', '#0F172A')}" />
      <stop offset="100%" stop-color="{p.get('background', '#030712')}" />
    </linearGradient>
  </defs>

  <rect width="1080" height="1350" fill="url(#bgGradient)" />

  <!-- Top Badge -->
  <rect x="80" y="90" width="320" height="50" rx="12" fill="{p.get('secondary', '#6366F1')}" />
  <text x="100" y="126" font-family="DejaVu Sans, Arial, sans-serif" font-size="24" font-weight="bold" fill="#FFFFFF">{first_slide.category.upper()}</text>

  <!-- Title -->
  <text x="80" y="440" font-family="DejaVu Sans, Arial, sans-serif" font-size="64" font-weight="bold" fill="{p.get('text_primary', '#F8FAFC')}">{first_slide.title[:32]}</text>

  <!-- Swipe Pill -->
  <rect x="80" y="1200" width="920" height="60" rx="16" fill="{p.get('card_bg', '#1E293B')}" />
  <text x="120" y="1242" font-family="DejaVu Sans, Arial, sans-serif" font-size="28" font-weight="bold" fill="{p.get('accent', '#10B981')}">SWIPE TO READ ➔</text>
  <text x="920" y="1242" font-family="DejaVu Sans, Arial, sans-serif" font-size="28" font-weight="bold" fill="{p.get('text_muted', '#94A3B8')}">1 / {spec.slides_count}</text>
</svg>"""
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)

        return spec_path, html_path, svg_path

    # --------------------------------------------------------------------------
    # Master Render Function
    # --------------------------------------------------------------------------
    def render_carousel(
        self,
        slides_data: List[Union[CarouselSlideData, Dict[str, Any]]],
        asset_id: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ) -> List[Path]:
        """Render multi-slide carousel at 1080x1350 and save editable source files."""
        if not slides_data:
            raise ValueError("At least one slide definition must be provided.")

        parsed_slides: List[CarouselSlideData] = []
        for i, s in enumerate(slides_data):
            if isinstance(s, dict):
                s["slide_number"] = i + 1
                parsed_slides.append(CarouselSlideData.model_validate(s))
            else:
                s.slide_number = i + 1
                parsed_slides.append(s)

        total_slides = len(parsed_slides)

        title_slug = re.sub(r"[^a-zA-Z0-9]+", "_", parsed_slides[0].title[:24]).strip("_").lower()
        clean_id = asset_id or f"carousel_{title_slug}"
        target_dir = output_dir or (PROJECT_ROOT / "content" / "assets" / clean_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        palette = self.get_palette()
        rendered_paths: List[Path] = []

        for i, slide in enumerate(parsed_slides):
            out_file = target_dir / f"slide_{i + 1:02d}.png"
            if i == 0:
                img = self.render_cover_slide(slide, total_slides, palette)
            elif i == total_slides - 1 and (slide.slide_type == "cta" or total_slides > 2):
                img = self.render_cta_slide(slide, total_slides, palette)
            else:
                img = self.render_content_slide(slide, total_slides, palette)

            img.save(out_file, "PNG")
            rendered_paths.append(out_file)
            logger.info(f"Rendered carousel slide {i + 1}/{total_slides} -> {out_file.name}")

        # Also compile slides into multi-page PDF for direct LinkedIn carousel upload
        if rendered_paths:
            try:
                pdf_imgs = [Image.open(p).convert("RGB") for p in rendered_paths]
                pdf_path = target_dir / "carousel.pdf"
                pdf_imgs[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=pdf_imgs[1:])
                logger.info(f"Generated multi-page LinkedIn PDF -> {pdf_path.name}")
            except Exception as e:
                logger.warning(f"Could not compile carousel PDF: {e}")

        # Save editable sources (spec.json + template.html/svg)
        _, font_name, font_license = get_free_font(size=40)
        spec = CarouselAssetSpec(
            asset_id=clean_id,
            slides_count=total_slides,
            font_name=font_name,
            font_license=font_license,
            brand_palette=palette,
            slides=parsed_slides,
            created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self.save_carousel_sources(target_dir, spec)

        logger.info(f"Successfully generated carousel asset in {target_dir} ({len(rendered_paths)} slides)")
        return rendered_paths
