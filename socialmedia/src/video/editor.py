"""Video assembly and transformation engine using MoviePy and ffmpeg.

Creates vertical short-form reels/shorts (9:16), handles aspect ratio
resizing, audio track synchronization, and platform-specific exports.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from moviepy.editor import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

from src.config import PlatformSpec, get_settings
from src.logging.logger import get_logger

logger = get_logger("video.editor")


class VideoEngine:
    """Assembles and renders social video clips formatted for target platforms."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_video_from_images(
        self,
        image_paths: List[Path],
        output_path: Path,
        duration_seconds: float = 15.0,
        spec: Optional[PlatformSpec] = None,
        audio_path: Optional[Path] = None,
    ) -> Path:
        """Compose a sequence of images/slides into a synchronized social video."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        width = spec.width if spec else 1080
        height = spec.height if spec else 1920
        fps = spec.fps if spec else 30

        if not image_paths:
            raise ValueError("At least one image path must be provided to create a video.")

        logger.info(
            f"Assembling video from {len(image_paths)} images -> {output_path.name} ({width}x{height} @ {fps}fps)"
        )

        slide_duration = duration_seconds / len(image_paths)
        clips: List[ImageClip] = []

        for p in image_paths:
            clip = ImageClip(str(p)).set_duration(slide_duration).resize((width, height))
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")

        # Attach audio track if supplied
        if audio_path and audio_path.exists():
            try:
                audio = AudioFileClip(str(audio_path))
                # Match clip duration to audio duration
                final_clip = final_clip.set_duration(audio.duration).set_audio(audio)
            except Exception as e:
                logger.warning(f"Failed to attach audio clip: {e}")

        final_clip.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac" if final_clip.audio else None,
            threads=2,
            preset="ultrafast",
            verbose=False,
            logger=None,
        )

        # Close clips to release file locks on Windows
        final_clip.close()
        for c in clips:
            c.close()

        logger.info(f"Video rendering complete: {output_path}")
        return output_path

    def adapt_video_to_aspect_ratio(
        self,
        input_video_path: Path,
        output_path: Path,
        spec: PlatformSpec,
    ) -> Path:
        """Crop and center an existing video to target platform dimensions."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Adapting {input_video_path.name} to {spec.name} dimensions ({spec.width}x{spec.height})"
        )

        with VideoFileClip(str(input_video_path)) as video:
            target_w = spec.width
            target_h = spec.height
            src_w, src_h = video.w, video.h

            # Scale to cover target dimensions
            scale_ratio = max(target_w / src_w, target_h / src_h)
            resized = video.resize(scale_ratio)

            # Center crop
            x_center = resized.w / 2
            y_center = resized.h / 2
            x1 = max(0, int(x_center - (target_w / 2)))
            y1 = max(0, int(y_center - (target_h / 2)))

            cropped = resized.crop(x1=x1, y1=y1, width=target_w, height=target_h)

            # Trim duration if platform maximum is exceeded
            if spec.max_duration_seconds and cropped.duration > spec.max_duration_seconds:
                cropped = cropped.subclip(0, spec.max_duration_seconds)

            cropped.write_videofile(
                str(output_path),
                fps=spec.fps,
                codec=spec.video_codec,
                audio_codec=spec.audio_codec,
                preset="ultrafast",
                threads=2,
                verbose=False,
                logger=None,
            )
            cropped.close()

        logger.info(f"Aspect ratio adaptation completed: {output_path}")
        return output_path
