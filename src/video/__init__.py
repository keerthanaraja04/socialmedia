"""Video editing, compilation, and aspect ratio adaptation using MoviePy."""

from src.video.editor import VideoEngine
from src.video.pixabay import (
    ClipCandidate,
    DownloadedClip,
    LicenseRegistry,
    PixabayVideoCache,
    PixabayVideoDownloader,
    PixabayVideoHit,
    PixabayVideoSize,
    extract_keywords_from_script,
)
from src.video.render import (
    CaptionSegment,
    VideoRenderer,
    VideoRenderSpec,
    get_free_font,
    render_caption_overlay,
    render_hook_overlay,
)

__all__ = [
    "VideoEngine",
    "VideoRenderer",
    "VideoRenderSpec",
    "CaptionSegment",
    "PixabayVideoDownloader",
    "DownloadedClip",
    "ClipCandidate",
    "PixabayVideoHit",
    "PixabayVideoSize",
    "PixabayVideoCache",
    "LicenseRegistry",
    "extract_keywords_from_script",
    "get_free_font",
    "render_hook_overlay",
    "render_caption_overlay",
]
