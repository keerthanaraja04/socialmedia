# Incubrix Engine

> **Autonomous AI Content Ingestion, Generation, Brand Compliance & Omnichannel Video Production Engine**

Incubrix Engine is an autonomous end-to-end media production system that transforms long-form text, audio, and video (podcasts, technical blogs, keynotes, whitepapers) into 30+ platform-native social assets—including 9:16 vertical reels with burned-in captions, 1080x1350 carousels, and platform-tailored copy—in minutes.

---

## ⚡ Key Features

- **Sub-Second Groq LPU Inference**: Offloads LLM operations to Groq LPUs (`llama-3.3-70b-versatile`, `whisper-large-v3`) with bounded concurrency (`ThreadPoolExecutor(max_workers=5)`) to complete multi-variant campaigns in minutes.
- **14-Column Master Content Calendar**: Generates `calendar.csv` strictly adhering to 14 core metadata fields:
  ```csv
  id,platform,format,pillar,hook,caption,hashtags,CTA,tracking_link,file_path,source_file_path,scheduled_datetime,target_metric,status
  ```
- **1-Click Bulk Schedulers**: Exports ready-to-import CSVs for **Buffer** (`buffer_schedule.csv`) and **Hootsuite** (`hootsuite_schedule.csv` with GMT formatting).
- **MoviePy 9:16 Vertical Video**: Auto-renders vertical reels (1080x1920, <=60s) with high-impact hook overlay in the first 2 seconds, safe-zone captions, and open-source font license tracking (`DejaVu Sans`).
- **Pillow 1080x1350 Carousels**: Renders high-contrast 4:5 portrait slide decks from curated brand tokens (`#0F172A`, `#6366F1`, `#10B981`, `#F8FAFC`).
- **Editable Source Files**: For every video and carousel, saves an editable spec (`spec.json`) alongside HTML and SVG templates in `content/assets/<id>/`.
- **Dual-Layer Brand Compliance & Self-Healing**: Deterministic regex checks paired with a Groq LLM Brand Judge that automatically triggers an asset regeneration loop to purge non-compliant claims.
- **Smart Deduplication & Refresh Mode**: Embedding-free SHA-256 hash checking and TF-IDF cosine similarity. Refresh mode (`--refresh`) skips previously processed inputs in **0.05 seconds**.
- **8-Point Programmatic Readiness Audit**: Validates hook, caption, hashtags, CTA, UTM tracking links, source files, license entries, and brand check scores before release.

---

## 🛠️ Prerequisites

Before getting started, ensure you have the following installed on your system:

1. **Python 3.11 or higher** (Python 3.11, 3.12, or 3.13 supported):
   ```bash
   python --version
   ```
2. **FFmpeg** (Required by MoviePy for video and audio rendering):
   - **Windows**:
     ```powershell
     winget install "Gyan.FFmpeg"
     # Or download from https://ffmpeg.org/download.html and add ffmpeg/bin to PATH
     ```
   - **macOS** (Homebrew):
     ```bash
     brew install ffmpeg
     ```
   - **Linux** (Debian/Ubuntu):
     ```bash
     sudo apt update && sudo apt install -y ffmpeg
     ```
3. **Groq API Key**:
   - Obtain a free API key at [console.groq.com](https://console.groq.com/).
4. **Pixabay API Key** (Optional):
   - Obtain a free API key at [pixabay.com/api/docs](https://pixabay.com/api/docs/).
   - *Note: If omitted or offline, the engine automatically synthesizes branded 9:16 video canvases.*

---

## 🚀 Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/incubrix/incubrix-engine.git
cd incubrix-engine
```

### 2. Create and Activate a Virtual Environment

- **On Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **On Linux / macOS**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the example environment configuration to `.env`:

```bash
# On Windows (PowerShell):
Copy-Item config\.env.example .env

# On Linux / macOS:
cp config/.env.example .env
```

Open `.env` and set your credentials:

```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
PIXABAY_API_KEY=your_pixabay_api_key_here
GROQ_LLM_MODEL=llama-3.3-70b-versatile
```

---

## 💻 One-Run Commands & Web Studio

### 0. Web Studio & Command Center (Interactive Browser Portal)
Launch the interactive web portal to browse generated assets, review audit tables, inspect carousel slide decks, and trigger runs from your browser:

```bash
# Launch server (runs on http://localhost:8000)
python server.py
# Or using make:
make serve
```

- **Web Studio Dashboard**: [http://localhost:8000](http://localhost:8000)
- **A/B Preference Survey Form**: [http://localhost:8000/tools/preference_test.html](http://localhost:8000/tools/preference_test.html)
- **REST Status Endpoint**: [http://localhost:8000/api/status](http://localhost:8000/api/status)

---

### 1. Batch Production & Readiness Audit (30+ Assets)
Runs the full engine on 4 real long-form inputs, producing 30+ assets across 5 platforms with at least 10 videos and 5 carousels, and validates the 8-point readiness checklist:

```bash
python scripts/build_30.py
```

*Fast Dry-Run Mode (skips video rendering for sub-10-second validation):*
```bash
python scripts/build_30.py --skip-video
```

### 2. Single Input Execution
Process any blog post, audio recording, keynote, or transcript through the unified CLI:

```bash
python -m src.main --input content/sources/input_1_autonomous_pipelines_blog.md
```

### 3. Refresh Mode (Incremental Ingestion)
Skips re-processing if the content hash has already been registered:

```bash
python -m src.main --input content/sources/input_1_autonomous_pipelines_blog.md --refresh
```

### 4. Failure-Injection Demo Mode
Simulates a non-compliant marketing claim to demonstrate the automated self-healing regeneration loop in action:

```bash
python -m src.main --input content/sources/input_1_autonomous_pipelines_blog.md --simulate-failure --force
```

---

## 📊 Expected Output & Distribution Structure

When the engine executes, it produces:

### 1. Executive Console Audit Table
```text
================================================================================
           INCUBRIX ENGINE: 30+ ASSET PRODUCTION & READINESS AUDIT           
================================================================================
Total Inputs Processed: 4
Total Assets Created:   40  (Target: >= 30)  [PASS]
Total Videos Rendered:  12  (Target: >= 10)  [PASS]
Total Carousels Built:  8   (Target: >= 5)   [PASS]
Platforms Covered (5):  instagram_reels, linkedin, tiktok, x_twitter, youtube_shorts  [PASS]
Checklist Pass Rate:    100.0%  (ALL CHECKS PASSED)
Total Pipeline Runtime: 48.20s
Groq Inference Cost:    $0.004120 USD

--------------------------------------------------------------------------------
                     READINESS CHECKLIST VERIFICATION (8/8)                    
--------------------------------------------------------------------------------
 [x] 1. Hook:               Non-empty, scroll-stopping first-2s pattern interrupt
 [x] 2. Caption:            Tailored copy with high-retention structure
 [x] 3. Hashtags:           Brand tag #IncuBrix included on all platform assets
 [x] 4. CTA:                Actionable call-to-action included
 [x] 5. UTM Link:           Valid tracking link with utm_source, utm_medium, utm_campaign
 [x] 6. Editable Source:    spec.json / HTML / SVG templates saved in content/assets/<id>/
 [x] 7. License Registry:   Provenance logged in content/licenses.csv
 [x] 8. Brand Compliance:   Deterministic rules & LLM Judge verified (Score >= 80)
================================================================================
```

### 2. Distribution Bundle Directory Layout
Outputs are structured into date-stamped folders under `data/outputs/`:

```text
data/outputs/20261023_200000_autonomous_pipelines/
├── calendar.csv              # Exact 14-column master content calendar
├── buffer_schedule.csv       # Buffer bulk import schedule (Date, Text, Media, Platform)
├── hootsuite_schedule.csv    # Hootsuite bulk schedule (Date GMT, Time GMT, Text, URL)
├── manifest.json             # Complete audit log with model parameters & scores
├── tiktok/
│   ├── tiktok_video.mp4      # 9:16 vertical reel with burned-in captions & hook overlay
│   ├── tiktok_thumbnail.png  # Branded high-contrast cover thumbnail
│   ├── post_content.txt      # Formatted hook, caption, hashtags, and CTA
│   └── metadata.json         # Asset metadata and character limits
├── instagram_reels/
│   ├── instagram_reels_video.mp4
│   └── carousel/             # 1080x1350 portrait carousel slides (slide_01.png ...)
├── youtube_shorts/
│   └── youtube_shorts_video.mp4
├── linkedin/
│   └── carousel/             # 1080x1350 4:5 portrait carousel slides
└── x_twitter/
    └── post_content.txt      # High-velocity discussion copy
```

### 3. Editable Source Files
For downstream editing by creative teams, every asset saves editable templates in `content/assets/<id>/`:
- `spec.json`: JSON specification detailing durations, fonts, colors, timestamps, and bounding boxes.
- `template.html`: Browser-renderable HTML template with inline brand CSS.
- `template.svg`: Vector SVG template for Adobe Illustrator or Figma import.

### 4. License Provenance (`content/licenses.csv`)
Logs every external media download and open-source font usage:
```csv
pixabay_id,page_url,author,download_date,asset_id,manual_review,manual_review_reason
1001,https://dejavu-fonts.github.io,DejaVu Sans,2026-10-23,reel_01,FALSE,Rendered with font 'DejaVu Sans Bold' (Bitstream Vera License)
```

---

## 🧪 Testing

The repository contains an exhaustive test suite covering all modules:

```bash
# Run the complete test suite
python -m pytest

# Run specific focus areas
python -m pytest tests/test_checklist.py      # 8-point readiness checklist
python -m pytest tests/test_export_calendar.py # Exact 14-column calendar.csv & schedulers
python -m pytest tests/test_utm_builder.py    # UTM parameter validation
python -m pytest tests/test_retry_logic.py    # Exponential backoff & self-healing
python -m pytest tests/test_dedupe.py         # SHA-256 and TF-IDF similarity
python -m pytest tests/test_main_cli.py       # CLI flags and refresh mode
```

---

## 🔧 Troubleshooting Guide

### 1. `FileNotFoundError: ffmpeg not found`
- **Cause**: MoviePy requires `ffmpeg` to compile MP4 video files.
- **Solution**: Install FFmpeg via `winget install "Gyan.FFmpeg"` (Windows), `brew install ffmpeg` (macOS), or `sudo apt install ffmpeg` (Linux). Ensure the directory containing `ffmpeg.exe` or `ffmpeg` is in your system's `PATH`.

### 2. `RateLimitError: HTTP 429` on Groq API
- **Cause**: High concurrency exceeding your Groq tier's requests-per-minute.
- **Solution**: The engine automatically applies exponential backoff with random jitter up to 3 retries. If persistent, reduce concurrency in `src/pipeline.py` or switch models in `.env` to `llama-3.1-8b-instant`.

### 3. MoviePy Stalls / Hangs during Video Compilation on Windows
- **Cause**: On Windows, piping large stderr outputs from ffmpeg can cause OS pipe deadlocks.
- **Solution**: The engine is configured with `ffmpeg_params=["-loglevel", "error"]` and `threads=1` to prevent pipe saturation. Do not remove these flags.

### 4. Running Without API Keys (Offline / Demo Mode)
- **Cause**: `GROQ_API_KEY` or `PIXABAY_API_KEY` not yet configured.
- **Solution**: The engine includes built-in graceful degradation:
  - If Groq is offline, it generates typed structured fallbacks adhering to all brand schemas.
  - If Pixabay is offline, it generates an animated 1080x1920 brand canvas clip to ensure video rendering completes successfully.

### 5. Font Licensing Audit
- **Cause**: Commercial video production requires permissive font licensing.
- **Solution**: The engine bundles `DejaVu Sans` and `DejaVu Sans Bold` in `content/assets/fonts/` (licensed under the Bitstream Vera / DejaVu open-source license) and records font licensing in both `content/licenses.csv` and `spec.json`.

---

## 📄 License

This project is licensed under the Apache 2.0 License. Free licensed fonts are used under the Bitstream Vera Fonts License.
