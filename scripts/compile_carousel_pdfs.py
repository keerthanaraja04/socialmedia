"""Batch compiles all existing carousel slide images into multi-page carousel.pdf files.

LinkedIn carousels require uploading a document (PDF). This script iterates through
all carousel folders in content/assets/ and packages slide_01.png, slide_02.png, ...
into a clean 1080x1350 multi-page PDF ready for 1-click LinkedIn document upload.
"""

from pathlib import Path
import sys
from PIL import Image

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def compile_all():
    assets_dir = PROJECT_ROOT / "content" / "assets"
    count = 0
    if not assets_dir.exists():
        print("No content/assets directory found.")
        return

    for d in sorted(assets_dir.iterdir()):
        if d.is_dir() and d.name.startswith("carousel_"):
            slides = sorted([f for f in d.iterdir() if f.name.startswith("slide_") and f.name.endswith(".png")])
            if slides:
                try:
                    imgs = [Image.open(s).convert("RGB") for s in slides]
                    pdf_path = d / "carousel.pdf"
                    imgs[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=imgs[1:])
                    count += 1
                    print(f"✅ Generated {pdf_path.relative_to(PROJECT_ROOT)} ({len(slides)} pages)")
                except Exception as e:
                    print(f"❌ Failed {d.name}: {e}")

    # Also do the same for data/outputs/final_submission_bundle/carousels if exists
    bundle_carousels = PROJECT_ROOT / "data" / "outputs" / "final_submission_bundle" / "carousels"
    if bundle_carousels.exists():
        for d in sorted(bundle_carousels.iterdir()):
            if d.is_dir() and d.name.startswith("carousel_"):
                slides = sorted([f for f in d.iterdir() if f.name.startswith("slide_") and f.name.endswith(".png")])
                if slides:
                    try:
                        imgs = [Image.open(s).convert("RGB") for s in slides]
                        pdf_path = d / "carousel.pdf"
                        imgs[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=imgs[1:])
                        print(f"✅ Generated bundle PDF {pdf_path.relative_to(PROJECT_ROOT)}")
                    except Exception as e:
                        print(f"❌ Failed bundle {d.name}: {e}")

    print(f"\n🎉 Successfully compiled {count} carousels into multi-page LinkedIn PDFs!")

if __name__ == "__main__":
    compile_all()
