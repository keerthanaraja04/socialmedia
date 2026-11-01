"""Pillow carousel slide rendering engine at 1080x1350 from brand colors.

Exports CarouselRenderer, CarouselSlideData, CarouselAssetSpec,
and saves editable source files (JSON spec + HTML/SVG template) in content/assets/<id>/.
"""

from src.graphics.carousel import (
    CAROUSEL_HEIGHT,
    CAROUSEL_WIDTH,
    CarouselAssetSpec,
    CarouselRenderer,
    CarouselSlideData,
)
from src.graphics.designer import GraphicsDesigner, StockAsset

__all__ = [
    "CarouselRenderer",
    "CarouselSlideData",
    "CarouselAssetSpec",
    "CAROUSEL_WIDTH",
    "CAROUSEL_HEIGHT",
    "GraphicsDesigner",
    "StockAsset",
]
