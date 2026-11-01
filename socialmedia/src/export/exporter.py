"""Packaging, calendar generation, and scheduler export manager for Incubrix content.

Organizes final video assets, carousels, platform-tailored copy, and audit manifests
into date-stamped output folders under data/outputs/.
Generates:
1. calendar.csv (one row per asset with exact 14 columns):
   id, platform, format, pillar, hook, caption, hashtags, CTA, tracking_link,
   file_path, source_file_path, scheduled_datetime, target_metric, status
2. Buffer-style bulk scheduler CSV (buffer_schedule.csv):
   Date, Text, Media, Platform
3. Hootsuite-style bulk scheduler CSV (hootsuite_schedule.csv):
   Date (GMT), Time (GMT), Text, URL
4. General scheduler CSV (scheduler.csv)
5. master manifest.json
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.brandcheck.models import BrandCheckReport
from src.config import PROJECT_ROOT, get_settings
from src.generate.models import GenerationResult, PlatformAsset, PlatformPost
from src.logging.logger import get_logger

logger = get_logger("export.manager")

# Exact 14 columns requested for calendar.csv
CALENDAR_CSV_HEADERS: List[str] = [
    "id",
    "platform",
    "format",
    "pillar",
    "hook",
    "caption",
    "hashtags",
    "CTA",
    "tracking_link",
    "file_path",
    "source_file_path",
    "scheduled_datetime",
    "target_metric",
    "status",
]


class CalendarRow(BaseModel):
    """Specification of an individual asset entry in calendar.csv."""
    id: str
    platform: str
    format: str
    pillar: str = "Practical Workflows"
    hook: str
    caption: str
    hashtags: str
    CTA: str
    tracking_link: str
    file_path: str
    source_file_path: str
    scheduled_datetime: str
    target_metric: str = "shares"
    status: str = "scheduled"


class PlatformPackage(BaseModel):
    platform_id: str
    directory: Path
    video_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    copy_path: Path
    metadata_path: Path
    assets: List[Dict[str, Any]] = Field(default_factory=list)


class ExportBundle(BaseModel):
    run_id: str
    export_dir: Path
    timestamp: str
    packages: Dict[str, PlatformPackage] = Field(default_factory=dict)
    manifest_path: Path
    calendar_csv_path: Optional[Path] = None
    buffer_csv_path: Optional[Path] = None
    hootsuite_csv_path: Optional[Path] = None
    total_assets: int = 0


class ExportManager:
    """Creates standardized multi-platform distribution packages, calendar.csv, and scheduler CSVs."""

    def __init__(self, base_output_dir: Optional[Path] = None) -> None:
        self.settings = get_settings()
        self.base_output_dir = base_output_dir or self.settings.outputs_dir

    def calculate_schedule_times(self, count: int, start_days_ahead: int = 1) -> List[datetime]:
        """Compute realistic staggered publication slots across upcoming days at high-engagement hours."""
        slots = [
            (9, 0),   # 09:00 AM
            (13, 30), # 01:30 PM
            (17, 0),  # 05:00 PM
            (20, 0),  # 08:00 PM
        ]
        now = datetime.now()
        base_date = (now + timedelta(days=start_days_ahead)).replace(minute=0, second=0, microsecond=0)

        scheduled_times: List[datetime] = []
        for i in range(count):
            day_offset = i // len(slots)
            slot_idx = i % len(slots)
            hour, minute = slots[slot_idx]
            slot_time = (base_date + timedelta(days=day_offset)).replace(hour=hour, minute=minute)
            scheduled_times.append(slot_time)

        return scheduled_times

    def build_calendar_rows(
        self,
        generation: GenerationResult,
        packages: Dict[str, PlatformPackage],
        source_file_path: str = "",
        run_dir: Optional[Path] = None,
    ) -> List[CalendarRow]:
        """Construct structured CalendarRow items for all generated assets."""
        rows: List[CalendarRow] = []

        # If generation has rich platform assets list, use that
        raw_assets = getattr(generation, "assets", [])
        if raw_assets:
            schedule_times = self.calculate_schedule_times(len(raw_assets))
            for i, asset in enumerate(raw_assets):
                slot_time = schedule_times[i]
                pkg = packages.get(asset.platform_id)
                file_rel = ""
                if pkg:
                    if asset.asset_type == "short_video" and pkg.video_path:
                        file_rel = str(pkg.video_path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in pkg.video_path.parents else pkg.video_path)
                    elif asset.asset_type == "carousel" and (pkg.directory / "carousel").exists():
                        c_slides = sorted(list((pkg.directory / "carousel").glob("*.png")))
                        if c_slides:
                            file_rel = str(c_slides[0].relative_to(PROJECT_ROOT) if PROJECT_ROOT in c_slides[0].parents else c_slides[0])
                        elif pkg.thumbnail_path:
                            file_rel = str(pkg.thumbnail_path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in pkg.thumbnail_path.parents else pkg.thumbnail_path)
                        else:
                            file_rel = str(pkg.copy_path)
                    elif pkg.thumbnail_path:
                        file_rel = str(pkg.thumbnail_path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in pkg.thumbnail_path.parents else pkg.thumbnail_path)
                    elif pkg.video_path:
                        file_rel = str(pkg.video_path.relative_to(PROJECT_ROOT) if PROJECT_ROOT in pkg.video_path.parents else pkg.video_path)
                    else:
                        file_rel = str(pkg.copy_path)

                hook = ""
                if asset.short_video_script:
                    hook = asset.short_video_script.hook_first_2s
                elif asset.carousel and asset.carousel.slides:
                    hook = asset.carousel.slides[0].headline
                else:
                    hook = asset.title or generation.script.hook

                fmt = "9:16 vertical video" if asset.asset_type == "short_video" else ("1080x1350 carousel" if asset.asset_type == "carousel" else "text post")

                rows.append(
                    CalendarRow(
                        id=asset.asset_id or f"asset_{asset.platform_id}_{i+1:02d}",
                        platform=asset.platform_id,
                        format=fmt,
                        pillar=asset.content_pillar or "Practical Workflows",
                        hook=hook,
                        caption=asset.caption,
                        hashtags=" ".join(asset.hashtags) if isinstance(asset.hashtags, list) else str(asset.hashtags),
                        CTA=asset.cta or "Follow @IncuBrix",
                        tracking_link=asset.utm_url or "https://incubrix.com",
                        file_path=file_rel,
                        source_file_path=str(source_file_path),
                        scheduled_datetime=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                        target_metric=asset.target_metric or "shares",
                        status="scheduled",
                    )
                )

        # Fallback / backward-compatibility: use platform_posts
        if not rows and generation.platform_posts:
            post_items = list(generation.platform_posts.items())
            schedule_times = self.calculate_schedule_times(len(post_items))
            for i, (p_id, post) in enumerate(post_items):
                slot_time = schedule_times[i]
                pkg = packages.get(p_id)
                file_rel = ""
                if pkg and pkg.video_path:
                    file_rel = str(pkg.video_path)
                elif pkg and pkg.thumbnail_path:
                    file_rel = str(pkg.thumbnail_path)
                elif pkg:
                    file_rel = str(pkg.copy_path)

                rows.append(
                    CalendarRow(
                        id=f"asset_{p_id}_{i+1:02d}",
                        platform=p_id,
                        format="9:16 vertical video" if p_id in ("tiktok", "instagram_reels", "youtube_shorts") else "text post",
                        pillar="Practical Workflows",
                        hook=generation.script.hook,
                        caption=post.caption,
                        hashtags=" ".join(post.hashtags) if isinstance(post.hashtags, list) else str(post.hashtags),
                        CTA=generation.script.call_to_action,
                        tracking_link=f"https://incubrix.com/?utm_source={p_id}&utm_medium=social",
                        file_path=file_rel,
                        source_file_path=str(source_file_path),
                        scheduled_datetime=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                        target_metric="shares",
                        status="scheduled",
                    )
                )

        return rows

    def export_calendar_csv(self, rows: List[CalendarRow], output_path: Path) -> Path:
        """Write calendar.csv strictly matching the 14 requested columns."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CALENDAR_CSV_HEADERS)
            for r in rows:
                writer.writerow([
                    r.id,
                    r.platform,
                    r.format,
                    r.pillar,
                    r.hook,
                    r.caption,
                    r.hashtags,
                    r.CTA,
                    r.tracking_link,
                    r.file_path,
                    r.source_file_path,
                    r.scheduled_datetime,
                    r.target_metric,
                    r.status,
                ])
        logger.info(f"Exported calendar.csv with {len(rows)} entries to: {output_path}")
        return output_path

    def export_buffer_csv(self, rows: List[CalendarRow], output_path: Path) -> Path:
        """Export Buffer bulk schedule CSV: Date, Text, Media, Platform."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Text", "Media", "Platform"])
            for r in rows:
                full_text = f"{r.caption}\n\n{r.hashtags}\n\n{r.tracking_link}".strip()
                writer.writerow([
                    r.scheduled_datetime,
                    full_text,
                    r.file_path,
                    r.platform,
                ])
        logger.info(f"Exported Buffer scheduler CSV to: {output_path}")
        return output_path

    def export_hootsuite_csv(self, rows: List[CalendarRow], output_path: Path) -> Path:
        """Export Hootsuite bulk schedule CSV: Date (GMT), Time (GMT), Text, URL."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date (GMT)", "Time (GMT)", "Text", "URL"])
            for r in rows:
                try:
                    dt = datetime.strptime(r.scheduled_datetime, "%Y-%m-%d %H:%M:%S")
                    d_str = dt.strftime("%d/%m/%Y")
                    t_str = dt.strftime("%H:%M")
                except Exception:
                    d_str = datetime.now().strftime("%d/%m/%Y")
                    t_str = "09:00"

                text_combined = f"{r.caption}\n\n{r.hashtags}".strip()
                writer.writerow([
                    d_str,
                    t_str,
                    text_combined,
                    r.tracking_link,
                ])
        logger.info(f"Exported Hootsuite scheduler CSV to: {output_path}")
        return output_path

    def create_bundle(
        self,
        generation: GenerationResult,
        brand_report: BrandCheckReport,
        rendered_videos: Optional[Dict[str, Path]] = None,
        thumbnails: Optional[Dict[str, Path]] = None,
        run_name: Optional[str] = None,
        source_file_path: str = "",
        carousels: Optional[Dict[str, List[Path]]] = None,
    ) -> ExportBundle:
        """Package all generated artifacts, calendar.csv, and scheduler CSVs into date-stamped output."""
        rendered_videos = rendered_videos or {}
        thumbnails = thumbnails or {}
        carousels = carousels or {}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = "".join([c if c.isalnum() else "_" for c in generation.topic.lower()])[:30]
        run_id = f"{timestamp}_{slug}"
        if run_name:
            run_id = f"{run_id}_{run_name}"

        run_dir = self.base_output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Packaging distribution bundle in: {run_dir}")

        packages: Dict[str, PlatformPackage] = {}

        # 1. Package platform folders
        for p_id, post in generation.platform_posts.items():
            p_dir = run_dir / p_id
            p_dir.mkdir(parents=True, exist_ok=True)

            final_video_path = None
            if p_id in rendered_videos and rendered_videos[p_id].exists():
                src_video = rendered_videos[p_id]
                target_video = p_dir / f"{p_id}_video{src_video.suffix}"
                shutil.copy2(src_video, target_video)
                final_video_path = target_video

            final_thumb_path = None
            if p_id in thumbnails and thumbnails[p_id].exists():
                src_thumb = thumbnails[p_id]
                target_thumb = p_dir / f"{p_id}_thumbnail{src_thumb.suffix}"
                shutil.copy2(src_thumb, target_thumb)
                final_thumb_path = target_thumb

            # Copy carousel slides if present
            if p_id in carousels:
                carousel_dir = p_dir / "carousel"
                carousel_dir.mkdir(parents=True, exist_ok=True)
                for slide_p in carousels[p_id]:
                    if slide_p.exists():
                        shutil.copy2(slide_p, carousel_dir / slide_p.name)

            copy_file = p_dir / "post_content.txt"
            with open(copy_file, "w", encoding="utf-8") as f:
                if post.title:
                    f.write(f"TITLE:\n{post.title}\n\n")
                f.write(f"CAPTION / POST:\n{post.caption}\n\n")
                if post.hashtags:
                    f.write(f"HASHTAGS:\n{' '.join(post.hashtags)}\n")

            meta_file = p_dir / "metadata.json"
            meta_data = {
                "platform": p_id,
                "title": post.title,
                "character_count": len(post.caption),
                "hashtags": post.hashtags,
                "visual_prompt": post.visual_search_term,
                "brand_compliance_score": brand_report.score,
                "video_file": final_video_path.name if final_video_path else None,
                "thumbnail_file": final_thumb_path.name if final_thumb_path else None,
            }
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)

            packages[p_id] = PlatformPackage(
                platform_id=p_id,
                directory=p_dir,
                video_path=final_video_path,
                thumbnail_path=final_thumb_path,
                copy_path=copy_file,
                metadata_path=meta_file,
            )

        # 2. Build Calendar Rows and Export calendar.csv
        calendar_rows = self.build_calendar_rows(
            generation=generation,
            packages=packages,
            source_file_path=source_file_path,
            run_dir=run_dir,
        )

        calendar_csv_path = run_dir / "calendar.csv"
        self.export_calendar_csv(calendar_rows, calendar_csv_path)

        # 3. Export Buffer & Hootsuite Scheduler CSVs
        buffer_csv_path = run_dir / "buffer_schedule.csv"
        self.export_buffer_csv(calendar_rows, buffer_csv_path)

        hootsuite_csv_path = run_dir / "hootsuite_schedule.csv"
        self.export_hootsuite_csv(calendar_rows, hootsuite_csv_path)

        # 4. Write master manifest.json
        manifest_file = run_dir / "manifest.json"
        manifest_data = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "topic": generation.topic,
            "core_message": generation.core_message,
            "model_used": generation.model_used,
            "total_assets": len(calendar_rows),
            "calendar_csv": calendar_csv_path.name,
            "buffer_schedule_csv": buffer_csv_path.name,
            "hootsuite_schedule_csv": hootsuite_csv_path.name,
            "brandcheck": {
                "passed": brand_report.passed,
                "score": brand_report.score,
                "rule_score": brand_report.rule_score,
                "llm_tone_score": brand_report.llm_tone_score,
                "violations": brand_report.violations,
                "warnings": brand_report.warnings,
            },
            "platforms": list(packages.keys()),
        }
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        bundle = ExportBundle(
            run_id=run_id,
            export_dir=run_dir,
            timestamp=timestamp,
            packages=packages,
            manifest_path=manifest_file,
            calendar_csv_path=calendar_csv_path,
            buffer_csv_path=buffer_csv_path,
            hootsuite_csv_path=hootsuite_csv_path,
            total_assets=len(calendar_rows),
        )

        logger.info(f"Successfully packaged {len(calendar_rows)} assets into {run_dir}")
        return bundle
