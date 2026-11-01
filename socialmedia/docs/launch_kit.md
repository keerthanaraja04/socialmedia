# IncuBrix 30-Day Omnichannel Launch Kit & Production Playbook

> **Document Status**: Production Launch-Kit Template  
> **Campaign**: IncuBrix 30-Day Autonomous Omnichannel Content Launch  
> **Framework**: 1 Long-Form Core Input &rarr; 30 Omnichannel Assets (10+ 9:16 Videos, 5+ Carousels, 15+ Micro-Posts)  
> **Notice**: Pre-launch verification metrics (Section 3) and audience preference test findings (Section 4) are populated directly from verified audit logs (`reports/audit_report_30.md`, `reports/preference_test_summary.md`) with 100% test pass rates. Campaign OKR targets and marketing budgets remain customizable via `[TODO: ...]` placeholders. **Zero synthetic or fake metrics are included.**

---

## 1. Executive Summary & Launch Strategy

The IncuBrix Omnichannel Engine transforms long-form technical media (founder interviews, architecture deep dives, and product demo transcripts) into a 30-day continuous stream of high-converting social assets. This playbook defines the day-by-day execution plan, team ownership (RACI), daily operational workflows, tooling dependencies, paid-boost rules, and risk contingencies.

### 1.1 Core Strategic Pillars
1. **Pillar 1: System Architecture & Engineering Rigor** &mdash; Behind-the-scenes teardowns of the high-throughput pipeline, MoviePy/FFmpeg rendering, and Groq inference speeds.
2. **Pillar 2: Creator Economy ROI & Time Savings** &mdash; Before/after case studies turning 6 hours of manual editing into 90 seconds of autonomous generation.
3. **Pillar 3: Tactical Playbooks & Workflows** &mdash; Step-by-step swipeable LinkedIn carousels, command-line cheatsheets, and prompt architectures.
4. **Pillar 4: Industry Perspective & Media Critique** &mdash; Contrarian takes on the obsolete manual media agency model and the future of autonomous agentic creation.

---

## 2. Quantitative Targets & KPI Scorecard

> **Fill Notice**: Populate the following baseline benchmarks and targets from your internal business model and quarterly growth OKRs.

| Funnel Stage | Key Performance Indicator (KPI) | 30-Day Campaign Target | Tracking Source / Verification Method |
| :--- | :--- | :--- | :--- |
| **Top of Funnel (Awareness)** | Total Unique Reach | `[TODO: Enter Target Unique Reach - e.g., 250,000 unique accounts]` | Native Platform Analytics (LinkedIn, YouTube, IG, TikTok) |
| **Top of Funnel (Awareness)** | Total Impressions / Views | `[TODO: Enter Target Total Impressions - e.g., 500,000 total impressions]` | Aggregated Platform Dashboards |
| **Middle of Funnel (Engagement)**| Blended Engagement Rate | `[TODO: Enter Target Engagement Rate % - e.g., 4.5% across all formats]` | (Engagements / Total Impressions) &times; 100 |
| **Middle of Funnel (Engagement)**| Total Saves / Bookmarks | `[TODO: Enter Target Total Saves - e.g., 1,500 total bookmarks]` | LinkedIn Carousel Saves & IG Bookmarks |
| **Bottom of Funnel (Traffic)** | Outbound UTM Link Clicks | `[TODO: Enter Target Link Clicks - e.g., 3,200 tracked clicks]` | Google Analytics 4 / Bitly UTM parameters |
| **Bottom of Funnel (Traffic)** | Click-Through Rate (CTR) | `[TODO: Enter Target Average CTR % - e.g., 1.8%]` | (Total Clicks / Total Impressions) &times; 100 |
| **Conversion (Sign-ups)** | Waitlist / Product Sign-ups | `[TODO: Enter Target Conversions - e.g., 650 product sign-ups]` | Product Auth Database / Waitlist CRM |
| **Conversion (Sign-ups)** | Landing Page Conversion Rate | `[TODO: Enter Target LP Conversion % - e.g., 20.3%]` | (Sign-ups / Total Landings) &times; 100 |
| **Efficiency / CAC** | Target Cost Per Acquisition (CPA)| `[TODO: Enter Max CPA Threshold - e.g., $12.50 per verified sign-up]` | (Total Boost Spend / Total Paid Sign-ups) |

---

## 3. Engine Audit & Quality Assurance Baseline

The content assets scheduled in this campaign are generated and audited via `scripts/build_30.py` and recorded in `IncuBrix_Submission_Workbook.xlsx`.

### 3.1 Pre-Launch Verification Metrics
* **Total Assets Generated**: `40 assets` (Target: >= 30, verified in `reports/audit_report_30.json`)
* **Total 9:16 Vertical Videos (MP4)**: `20 videos` (Target: >= 10, 1080x1920, <=60s)
* **Total Multi-Slide Carousels**: `16 carousels` (Target: >= 5, 1080x1350)
* **Audit Checklist Pass Rate**: `100.0%` (8/8 rules passed across all 40 assets in `reports/audit_report_30.md`)
* **Brand Voice Check Pass Rate**: `100.0%` (Zero violations, brand score >= 80/100)
* **Pixabay Video License Compliance**: `100.0%` (All video clip licenses logged in `content/licenses.csv`)
* **Total Engine LLM Cost**: `$0.000000 USD` (Batch test inference run via Groq LPUs)
* **Total Engine Execution Runtime**: `120.04s` (2m 00s across 4 long-form inputs)

---

## 4. Target-Audience Preference Test Results

Prior to launch, content variants were submitted to 20+ target-audience respondents across 5 industry demographics (Creators/Podcasters, Video Editors, B2B Marketing Leads, Technical Founders, and Social Media Managers) using `tools/preference_test.html` and analyzed with `scripts/compute_preference.py`.

### 4.1 Preference Test Summary Data
* **Total Survey Respondents Evaluated**: `24 respondents` (Target: >= 20 respondents met, 120 total decisions)
* **Overall Preferred Variant**: `Variant A` (`71.7%` overall preference vs Variant B `28.3%`)

| Test Dimension | Variant A Description | Variant B Description | Audience Preference Result | Production Decision |
| :--- | :--- | :--- | :--- | :--- |
| **1. Short-Form Video Hook** | Quantified time savings (6h &rarr; 90s) | Problem callout ("Stop editing manually") | **A: 83.3%** (20) vs B: 16.7% (4) | Deploy Variant A: 2-second pattern interrupt (+66.6% lead) |
| **2. Carousel Title Slide** | Architectural framework title | Personal burnout narrative title | **A: 62.5%** (15) vs B: 37.5% (9) | Deploy Variant A for B2B (+25.0% lead); Variant B for Personal |
| **3. Caption Safe Zones & Pacing**| Structured scannable bullet points | Conversational storytelling block | **A: 79.2%** (19) vs B: 20.8% (5) | Deploy Variant A: High scannability & safe margins (+58.4% lead) |
| **4. Call to Action (CTA)** | Single keyword comment trigger | Direct GitHub repo bio link | **A: 58.3%** (14) vs B: 41.7% (10) | Deploy Variant A for Social (+16.6% lead); Variant B for Devs |
| **5. Visual Aesthetic / Color** | Deep Navy & Electric Indigo | Energetic Emerald Glow | **A: 75.0%** (18) vs B: 25.0% (6) | Deploy Variant A: Navy/Indigo brand theme (+50.0% lead) |

---

## 5. Master 30-Day Launch Content Calendar

All assets reference `calendar.csv` and source templates located in `content/assets/<id>/`.

| Day | Scheduled Date | Primary Platform | Asset ID | Format | Content Pillar | Hook / Headline | Primary CTA | Target Metric |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **D01** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_001` | Carousel | System Architecture | The 30-Day Repurposing Pipeline Architecture | Drop "PIPELINE" for code | `[TODO: Target Impressions]` |
| **D02** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_002` | 9:16 Video | Creator ROI | 6 Hours of Video Editing Done in 90 Seconds | Link in description | `[TODO: Target Views]` |
| **D03** | `[TODO: YYYY-MM-DD]` | Twitter / X | `asset_003` | Text + Graphic | Tactical Systems | How we parallelize Groq LLM calls under 30s | Clone the repo | `[TODO: Target Engagements]` |
| **D04** | `[TODO: YYYY-MM-DD]` | Instagram Reels| `asset_004` | 9:16 Video | Creator ROI | Stop Paying $3,000/mo to Repurposing Agencies | Comment "ENGINE" | `[TODO: Target Views]` |
| **D05** | `[TODO: YYYY-MM-DD]` | TikTok | `asset_005` | 9:16 Video | Tactical Systems | Building an AI Media Agency from your Terminal | Save for later | `[TODO: Target Views]` |
| **D06** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_006` | Text Post | Industry Critique | Why 90% of AI Video Wrappers Will Die in 2026 | Share your perspective | `[TODO: Target Comments]` |
| **D07** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_007` | 9:16 Video | System Architecture | Inside MoviePy & FFmpeg Headless Rendering | Subscribe for deep dives | `[TODO: Target Views]` |
| **D08** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_008` | Carousel | Tactical Systems | 5 Python Automation Patterns for Content Creators | Bookmark this carousel | `[TODO: Target Saves]` |
| **D09** | `[TODO: YYYY-MM-DD]` | Instagram Reels| `asset_009` | 9:16 Video | Creator ROI | Turn 1 Podcast Episode into 30 Omnichannel Assets | Link in bio | `[TODO: Target Views]` |
| **D10** | `[TODO: YYYY-MM-DD]` | Twitter / X | `asset_010` | Single Image | System Architecture | Complete Data Flow Diagram: Ingest to Render | Retweet if useful | `[TODO: Target Retweets]` |
| **D11** | `[TODO: YYYY-MM-DD]` | TikTok | `asset_011` | 9:16 Video | Tactical Systems | Watch AI generate video captions with zero drift | Comment "CODE" | `[TODO: Target Views]` |
| **D12** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_012` | Text Post | Creator ROI | The True Cost of Content Creation in 2026 | Read the breakdown | `[TODO: Target Engagements]` |
| **D13** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_013` | 9:16 Video | System Architecture | Zero Hallucination: The Brand Safety Linter | Watch full teardown | `[TODO: Target Views]` |
| **D14** | `[TODO: YYYY-MM-DD]` | Instagram Reels| `asset_014` | 9:16 Video | Tactical Systems | Automated Safe Zone Rendering for TikTok & Reels | Save for editing | `[TODO: Target Views]` |
| **D15** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_015` | Carousel | System Architecture | The IncuBrix Technical Stack: Ingest to Export | Comment "STACK" | `[TODO: Target Saves]` |
| **D16** | `[TODO: YYYY-MM-DD]` | Twitter / X | `asset_016` | Text + Graphic | Industry Critique | The Death of Manual Social Media Scheduling | Join the conversation | `[TODO: Target Engagements]` |
| **D17** | `[TODO: YYYY-MM-DD]` | TikTok | `asset_017` | 9:16 Video | Creator ROI | How I automated my entire weekly content queue | Link in bio | `[TODO: Target Views]` |
| **D18** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_018` | 9:16 Video | Tactical Systems | Open Source vs Closed AI Video Tools | Check pinned link | `[TODO: Target Views]` |
| **D19** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_019` | Text Post | System Architecture | Deduplicating 100+ AI Posts with Vector Cosine | Share with engineers | `[TODO: Target Comments]` |
| **D20** | `[TODO: YYYY-MM-DD]` | Instagram Reels| `asset_020` | 9:16 Video | Industry Critique | Why Founders Must Build in Public with Video | Comment "FOUNDER" | `[TODO: Target Views]` |
| **D21** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_021` | Carousel | Tactical Systems | Step-by-Step: Audio Transcription to Video MP4 | Download PDF | `[TODO: Target Saves]` |
| **D22** | `[TODO: YYYY-MM-DD]` | Twitter / X | `asset_022` | Text Post | Creator ROI | 3 KPIs Every B2B Marketing Lead Must Track | Bookmark thread | `[TODO: Target Retweets]` |
| **D23** | `[TODO: YYYY-MM-DD]` | TikTok | `asset_023` | 9:16 Video | System Architecture | High-Throughput Batch Processing with Python | Follow for code | `[TODO: Target Views]` |
| **D24** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_024` | 9:16 Video | Creator ROI | Stop Re-recording Video Hooks: Do This Instead | Watch next video | `[TODO: Target Views]` |
| **D25** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_025` | Text Post | Tactical Systems | UTM Parameter Architecture for Multi-Touch Attribution | Copy tracking sheet | `[TODO: Target Clicks]` |
| **D26** | `[TODO: YYYY-MM-DD]` | Instagram Reels| `asset_026` | 9:16 Video | System Architecture | Automated Dynamic Caption Burning with ImageMagick | Link in bio | `[TODO: Target Views]` |
| **D27** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_027` | Carousel | Industry Critique | The 2026 Autonomous Media Playbook | Drop "PLAYBOOK" | `[TODO: Target Saves]` |
| **D28** | `[TODO: YYYY-MM-DD]` | YouTube Shorts | `asset_028` | 9:16 Video | Tactical Systems | 3 Mistakes Killing Your Short-Form Video Retention | Watch full guide | `[TODO: Target Views]` |
| **D29** | `[TODO: YYYY-MM-DD]` | Twitter / X | `asset_029` | Text + Graphic | Creator ROI | Full Month Campaign Retrospective: By The Numbers | Check GitHub repo | `[TODO: Target Engagements]` |
| **D30** | `[TODO: YYYY-MM-DD]` | LinkedIn | `asset_030` | Carousel | System Architecture | The Complete Open-Source IncuBrix Pipeline Guide | Star on GitHub | `[TODO: Target Clicks]` |

---

## 6. Daily Operational Workflow & Hour-by-Hour Cadence

A repeatable, predictable operating cadence ensures consistent quality, platform algorithmic velocity, and timely engagement.

```
08:30 AM ── [1. Verify Staging & Assets]
09:45 AM ── [2. Platform Scheduling / Publishing]
10:00 AM ── [3. Golden Hour: Real-Time Community Response] (First 120 mins)
02:00 PM ── [4. Midday Cross-Promotion & Amplification]
05:30 PM ── [5. Analytics Inspection & Paid Boost Evaluation]
08:00 PM ── [6. Daily Debrief & D+1 Staging Lock]
```

### 6.1 Hourly Cadence Breakdown

#### Phase 1: Morning Verification & Staging (08:30 &ndash; 09:30 Local)
- **Action**: Check `calendar.csv` and `content/assets/<id>/` for today's scheduled asset.
- **Checklist**:
  - [ ] Video file playable, audio synced, captions readable within safe margins.
  - [ ] Carousel slides rendered at 1080x1350 with no clipped text.
  - [ ] Tracking link verified with correct UTM campaign tag (`utm_campaign=incubrix_30d`).
  - [ ] Buffer/Hootsuite queue confirmed for target time slot.

#### Phase 2: Golden Hour Community Velocity (10:00 &ndash; 12:00 Local)
- **Action**: The first 120 minutes dictate algorithmic distribution.
- **Checklist**:
  - [ ] Primary post published at peak active window (10:00 AM).
  - [ ] Team members (Founder + Lead) engage within first 15 minutes.
  - [ ] Respond to all inbound comments with substantive, value-add replies (avoid generic "Thanks!").
  - [ ] Send direct messages for keyword triggers ("PIPELINE", "STACK", "ENGINE") within 10 minutes.

#### Phase 3: Midday Amplification (14:00 &ndash; 15:30 Local)
- **Action**: Secondary cross-posting and community distribution.
- **Checklist**:
  - [ ] Repost carousel to secondary channels (Twitter thread / Reddit relevant subreddits).
  - [ ] Engage in 5 industry discussions on LinkedIn / Twitter with relevant technical insights.
  - [ ] Check comment mentions and tag relevant collaborators.

#### Phase 4: Analytics & Paid-Boost Decision (17:30 &ndash; 18:30 Local)
- **Action**: Evaluate post performance against baseline velocity thresholds.
- **Checklist**:
  - [ ] Log organic impressions and engagement rate at Hour +6.
  - [ ] Run Paid Boost Decision Matrix (Section 9): If engagement exceeds `[TODO: Benchmark %]`, trigger sponsored boost.
  - [ ] Verify UTM traffic conversions in Google Analytics 4.

#### Phase 5: Evening Debrief & Next-Day Staging (20:00 &ndash; 20:45 Local)
- **Action**: Complete daily log and lock tomorrow's assets.
- **Checklist**:
  - [ ] Update tracking spreadsheet with final daily metrics.
  - [ ] Review D+1 asset files and copy.
  - [ ] Ensure all API tokens (Groq, Buffer, Pixabay) have healthy quotas.

---

## 7. Team Roles & RACI Ownership Matrix

| Function / Deliverable | Campaign Lead (Founder) | Content Strategist | Video / Graphics Engineer | Community Manager | Performance / Growth Lead |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Pipeline Run & Asset Generation** | Accountable | Consulted | **Responsible** | Informed | Informed |
| **Brand Safety & Compliance Audit**| **Accountable** | Responsible | Consulted | Informed | Informed |
| **Daily Scheduling & Publishing** | Informed | Accountable | Consulted | **Responsible** | Informed |
| **Golden Hour Comment Engagement** | Responsible | Informed | Informed | **Accountable** | Informed |
| **Inbound Lead Magnet DM Delivery** | Informed | Informed | Informed | **Responsible** | Accountable |
| **Paid Boost Budget & Ad Ops** | Accountable | Informed | Informed | Informed | **Responsible** |
| **Weekly Retrospective & Reporting**| Accountable | **Responsible** | Consulted | Consulted | Responsible |

* **R (Responsible)**: The role that conducts the work to achieve the deliverable.
* **A (Accountable)**: The sole decision maker with veto and sign-off authority.
* **C (Consulted)**: Subject matter advisor who provides two-way input.
* **I (Informed)**: Kept updated on progress and results.

---

## 8. Technology & Production Stack

| Category | Primary Tool | Version / Model | Integration Purpose | Redundant Backup |
| :--- | :--- | :--- | :--- | :--- |
| **Audio Ingestion & Transcription** | Groq Whisper API | `whisper-large-v3` | High-speed transcript extraction | Local Faster-Whisper / OpenAI Whisper |
| **Content Generation Engine** | Groq API | `llama-3.3-70b-versatile`| Hook, caption, hashtag, and script generation | Anthropic Claude 3.5 Sonnet / OpenAI GPT-4o |
| **B-Roll & Video Footage** | Pixabay Videos API | REST v2 | Royalty-free vertical clips with license audit | Pexels API / Unsplash Video |
| **Video Composition & Captions**| MoviePy + FFmpeg | `moviepy>=1.0.3` | Headless 9:16 rendering, audio muxing, text overlays | Direct FFmpeg CLI script |
| **Carousel Graphic Rendering** | Python Pillow (PIL) | `pillow>=10.0` | 1080x1350 multi-slide typography rendering | Canva API / Figma headless CLI |
| **Workbook Reporting & Audit** | openpyxl | `openpyxl>=3.1.0` | Formula-safe Excel automation (`fill_workbook.py`)| Google Sheets API / CSV exports |
| **Social Media Scheduling** | Buffer / Hootsuite | Native API / CSV | Automated multi-platform queue management | Platform native schedulers |
| **Attribution & Analytics** | GA4 + Custom UTMs | Universal UTM | Full-funnel click & conversion tracking | Plausible Analytics / Bitly Enterprise |

---

## 9. Optional Paid-Boost Strategy & Budget Framework

Paid boosting should only amplify organic traction, never rescue flatlining content.

### 9.1 The Golden Ratio Boost Rule
```
IF (Organic Engagement Rate in First 4 Hours) >= [TODO: Enter Organic Benchmark % - e.g., 3.8%]
AND (Outbound Link CTR) >= [TODO: Enter CTR Benchmark % - e.g., 1.5%]
THEN:
    Trigger 48-hour Paid Boost on Winning Asset
ELSE:
    Retain budget; keep post purely organic
```

### 9.2 Budget Allocation & Unit Economics
* **Total Launch Ad Budget (30 Days)**: `[TODO: Insert Total Ad Budget - e.g., $1,500.00 USD]`
* **Daily Boost Allocation Ceiling**: `[TODO: Insert Max Daily Spend - e.g., $50.00/day]`
* **Platform Budget Distribution**:
  * LinkedIn Sponsored Content (B2B Leads): `[TODO: Insert LinkedIn Share - e.g., 50% ($750)]`
  * Instagram Reels Boost (Top-of-Funnel Reach): `[TODO: Insert Meta Share - e.g., 30% ($450)]`
  * YouTube Shorts / TikTok Promotion: `[TODO: Insert Shorts/TikTok Share - e.g., 20% ($300)]`
* **Target Efficiency Caps**:
  * Maximum Acceptable Cost Per Click (CPC): `[TODO: Enter Max CPC - e.g., $1.25]`
  * Maximum Target Cost Per Acquisition (CPA): `[TODO: Enter Target CPA - e.g., $15.00]`

---

## 10. Comprehensive Risk Management & Contingency Playbook

| Risk ID | Potential Threat | Likelihood | Impact | Preventive Measure | Immediate Mitigation Protocol |
| :---: | :--- | :---: | :---: | :--- | :--- |
| **RSK-01** | **LLM API Rate Limit or Outage** | Medium | High | Parallel Groq key pooling and fallback logic in `src/llm.py` | Automatically failover to secondary provider or execute local Ollama script. |
| **RSK-02** | **MoviePy / FFmpeg Render Crash** | Low | High | Pre-render all 30 days of assets ahead of Day 1 launch | Deploy pre-rendered backup assets from `content/assets/` archive. |
| **RSK-03** | **Copyright / Music Claim on Video** | Low | Critical| All video clips audited and recorded in `content/licenses.csv` | Instantly provide license URL from CSV to platform dispute form; replace clip with alternate. |
| **RSK-04** | **Platform Safe-Zone Caption Clipping**| Medium | Medium | Automated bounding box checks in `src/video/render.py` (top 15%, bottom 20% margins) | Regenerate video with safe zone template (`tools/safe_zone_spec.json`). |
| **RSK-05** | **Low Engagement on Specific Days** | Medium | Low | Strict adherence to the 120-minute Golden Hour engagement rule | Run A/B test hook variant in comments; activate community engagement squad. |
| **RSK-06** | **Negative Community PR / Flame Comment**| Low | Medium | Brand voice rules in `config/brand.yaml` banning provocative politics/hype | Follow de-escalation protocol: Acknowledge with technical facts; move to direct message. |

---

## 11. Sign-off & Launch Approvals

| Role | Sign-off Name | Approval Date | Status |
| :--- | :--- | :--- | :--- |
| **Executive Sponsor / Founder** | `[TODO: Enter Executive Name]` | `[TODO: YYYY-MM-DD]` | `[TODO: Pending / Approved]` |
| **Campaign Operations Lead** | `[TODO: Enter Lead Name]` | `[TODO: YYYY-MM-DD]` | `[TODO: Pending / Approved]` |
| **Technical & Pipeline Lead** | `[TODO: Enter Engineer Name]` | `[TODO: YYYY-MM-DD]` | `[TODO: Pending / Approved]` |

---
*Created for the IncuBrix Autonomous Social Media Pipeline.*
