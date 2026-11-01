"""Graphics design, Pillow image generation, and Pixabay asset retrieval.

Creates branded thumbnails, watermark cards, lower-thirds, and retrieves
royalty-free b-roll stock assets using PIXABAY_API_KEY from .env only.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from pydantic import BaseModel
import requests

from src.config import get_brand_config, get_settings
from src.logging.logger import get_logger

logger = get_logger("graphics.designer")


class StockAsset(BaseModel):
    id: int
    page_url: str
    preview_url: str
    large_image_url: str
    tags: str


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    """Convert hex color string like #0F172A to RGB tuple (15, 23, 42)."""
    hex_clean = hex_code.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join([c * 2 for c in hex_clean])
    return tuple(int(hex_clean[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


class GraphicsDesigner:
    """Manages visual asset retrieval and Pillow rendering of brand graphics."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.brand = get_brand_config()

    def search_pixabay_assets(self, query: str, limit: int = 3) -> List[StockAsset]:
        """Search Pixabay API for royalty-free stock photos."""
        api_key = self.settings.pixabay_api_key
        if not api_key or api_key.startswith("your_"):
            logger.warning("PIXABAY_API_KEY not configured in .env; skipping stock search.")
            return []

        url = "https://pixabay.com/api/"
        params = {
            "key": api_key,
            "q": query,
            "image_type": "photo",
            "orientation": "vertical",
            "per_page": limit,
            "safesearch": "true",
        }

        try:
            logger.info(f"Querying Pixabay API for: '{query}'")
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            assets: List[StockAsset] = []
            for hit in hits:
                assets.append(
                    StockAsset(
                        id=hit.get("id"),
                        page_url=hit.get("pageURL", ""),
                        preview_url=hit.get("previewURL", ""),
                        large_image_url=hit.get("largeImageURL", ""),
                        tags=hit.get("tags", ""),
                    )
                )
            logger.info(f"Retrieved {len(assets)} stock assets from Pixabay.")
            return assets
        except Exception as e:
            logger.warning(f"Pixabay asset search failed: {e}")
            return []

    def download_image(self, url: str, destination: Path) -> Path:
        """Download an image from a URL and save locally."""
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as f:
            f.write(resp.content)
        return destination

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        """Attempt to load a crisp TrueType font, or fallback to default."""
        font_candidates = [
            "arial.ttf" if not bold else "arialbd.ttf",
            "seguiemj.ttf",
            "calibri.ttf",
            "DejaVuSans.ttf",
        ]
        for name in font_candidates:
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    def generate_gradient_background(self, width: int, height: int) -> Image.Image:
        """Render a vertical linear gradient using brand palette colors."""
        palette = self.brand.visual.palette
        c_top = hex_to_rgb(palette.background)
        c_bottom = hex_to_rgb(palette.primary)

        base = Image.new("RGB", (width, height), c_top)
        draw = ImageDraw.Draw(base)

        for y in range(height):
            ratio = y / max(1, height - 1)
            r = int(c_top[0] * (1 - ratio) + c_bottom[0] * ratio)
            g = int(c_top[1] * (1 - ratio) + c_bottom[1] * ratio)
            b = int(c_top[2] * (1 - ratio) + c_bottom[2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        return base

    def generate_thumbnail(
        self,
        title: str,
        subtitle: Optional[str] = None,
        output_path: Optional[Path] = None,
        width: int = 1080,
        height: int = 1920,
        bg_image_path: Optional[Path] = None,
    ) -> Path:
        """Generate high-impact vertical video thumbnail with brand styling."""
        target_path = output_path or (self.settings.outputs_dir / "thumbnail.png")
        target_path.parent.mkdir(parents=True, exist_ok=True)

        palette = self.brand.visual.palette

        # 1. Background layer
        if bg_image_path and Path(bg_image_path).exists():
            try:
                img = Image.open(bg_image_path).convert("RGBA")
                img = img.resize((width, height), Image.Resampling.LANCZOS)
                # Darken slightly for readability
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(0.4)
            except Exception as e:
                logger.warning(f"Could not load custom background, generating gradient: {e}")
                img = self.generate_gradient_background(width, height).convert("RGBA")
        else:
            img = self.generate_gradient_background(width, height).convert("RGBA")

        draw = ImageDraw.Draw(img)

        # 2. Brand Watermark Badge (Top Right)
        wm = self.brand.visual.watermark
        if wm.enabled:
            wm_font = self._get_font(38, bold=True)
            wm_text = wm.text
            wm_margin = wm.margin
            # Draw badge background
            badge_w, badge_h = 240, 60
            badge_x = width - badge_w - wm_margin
            badge_y = wm_margin + 20
            draw.rounded_rectangle(
                [(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)],
                radius=12,
                fill=hex_to_rgb(palette.secondary) + (180,),
            )
            draw.text(
                (badge_x + 35, badge_y + 12),
                wm_text,
                font=wm_font,
                fill=hex_to_rgb(palette.text_primary),
            )

        # 3. Main Hook Title Card (Center)
        title_font = self._get_font(72, bold=True)
        sub_font = self._get_font(42, bold=False)

        # Word wrap title
        words = title.split()
        lines: List[str] = []
        cur_line = []
        for word in words:
            cur_line.append(word)
            if len(" ".join(cur_line)) > 20:
                lines.append(" ".join(cur_line))
                cur_line = []
        if cur_line:
            lines.append(" ".join(cur_line))

        # Draw card container
        card_margin = 60
        card_w = width - (card_margin * 2)
        line_height = 85
        total_text_h = (len(lines) * line_height) + (100 if subtitle else 40)
        card_top = (height // 2) - (total_text_h // 2)
        card_bottom = card_top + total_text_h

        draw.rounded_rectangle(
            [(card_margin, card_top - 40), (card_margin + card_w, card_bottom + 40)],
            radius=24,
            fill=hex_to_rgb(palette.card_bg) + (230,),
            outline=hex_to_rgb(palette.secondary),
            width=4,
        )

        # Render Title lines
        y_cursor = card_top
        for line in lines:
            draw.text(
                (card_margin + 40, y_cursor),
                line,
                font=title_font,
                fill=hex_to_rgb(palette.text_primary),
            )
            y_cursor += line_height

        # Render Subtitle
        if subtitle:
            y_cursor += 20
            draw.text(
                (card_margin + 40, y_cursor),
                subtitle,
                font=sub_font,
                fill=hex_to_rgb(palette.accent),
            )

        # 4. Save Final Image
        img = img.convert("RGB")
        img.save(str(target_path), format="PNG", quality=95)
        logger.info(f"Generated brand thumbnail at: {target_path}")
        return target_path
