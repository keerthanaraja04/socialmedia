# High-Throughput Agentic Video Generation: Architecture, Deterministic Guardrails, and Distributed Scheduling

## Abstract
Autonomous content generation pipelines require balancing sub-second neural inference with deterministic compliance guarantees. This paper presents the architecture of the IncuBrix Autonomous Engine, designed to repurpose unstructured long-form text, audio, and video into multi-platform production assets in parallel. We examine:
1. Parallelized Groq LPU inference using ThreadPoolExecutor for sub-30-minute campaign synthesis.
2. Embedding-free deduplication using SHA-256 hash checking and TF-IDF cosine similarity.
3. Dual-layer brand compliance: regex-based deterministic banned word audits paired with an LLM Brand Judge and a self-healing regeneration loop.
4. Omnichannel calendar scheduling with exact 14-column export and Buffer/Hootsuite format compatibility.

---

## 1. High-Concurrency LPU Orchestration
Scaling media generation to 30+ assets across five distinct platforms requires strict concurrency controls. Traditional sequential LLM API calls introduce compounding network latency, often exceeding 40 minutes for multi-variant campaigns.

The IncuBrix engine employs a bounded `ThreadPoolExecutor(max_workers=5)` architecture. Once the core insight and conversational soundbites are extracted, independent workers synthesize:
- Short-form vertical scripts for TikTok, Instagram Reels, and YouTube Shorts.
- 4-slide carousel specifications with headline hierarchies and category tags.
- Long-form thought leadership copy for LinkedIn.
- High-velocity discussion threads for X/Twitter.

By utilizing Groq's high-speed LPU infrastructure, each LLM inference step achieves 750+ tokens per second. Token usage, prompt counts, completion lengths, and calculated dollar costs are continuously written to `data/logs/runs.jsonl`, enabling granular cost audits per campaign run.

---

## 2. Embedding-Free Deduplication Architecture
To prevent redundant LLM inference and avoid republishing identical content, the engine utilizes a two-tier deduplication mechanism:
1. **Tier 1 (Exact Hash Match)**: A normalized SHA-256 hash is computed over inbound text content. If the hash matches an existing record in `data/dedupe_cache.json`, the engine triggers refresh mode, skipping reprocessing in less than 0.1 seconds.
2. **Tier 2 (TF-IDF Cosine Similarity)**: For inbound text with minor modifications, the engine runs a lightweight TF-IDF vectorizer across previous campaign records. If the cosine similarity exceeds a 0.82 threshold, the system flags the collision and requests user override via `--force`.

Because this approach avoids external vector databases and heavy embedding models, deduplication executes in under 15 milliseconds on CPU.

---

## 3. Brand Compliance & Automated Self-Healing
Generative language models frequently introduce over-promising marketing rhetoric. The IncuBrix Brand Checker deploys a two-stage evaluation pipeline:
- **Rule Verification**: Deterministic regex scans enforce character limits, hashtag requirements (mandatory `#IncuBrix`), UTM link formatting, and a zero-tolerance blacklist for unverified claims (e.g., "guaranteed 10x ROI", "instant passive income").
- **LLM Brand Judge**: A secondary Groq prompt scores voice authority, professional cadence, and clarity on a 0 to 100 scale.

If an asset scores below the passing threshold of 80.0, the pipeline initiates a self-healing regeneration cycle. The exact violation reasons are provided to the generator as correction constraints, producing a compliant variant that maintains narrative punch without regulatory risk.

---

## 4. Multi-Platform Calendar Distribution
Generated assets are compiled into a comprehensive publishing schedule:
- **Master Calendar (`calendar.csv`)**: Formats each asset with 14 strict metadata columns: `id`, `platform`, `format`, `pillar`, `hook`, `caption`, `hashtags`, `CTA`, `tracking_link`, `file_path`, `source_file_path`, `scheduled_datetime`, `target_metric`, and `status`.
- **Buffer Bulk Scheduler (`buffer_schedule.csv`)**: Formatted as `Date`, `Text`, `Media`, `Platform` for 1-click import into Buffer.
- **Hootsuite Bulk Scheduler (`hootsuite_schedule.csv`)**: Formatted as `Date (GMT)`, `Time (GMT)`, `Text`, `URL` adhering strictly to Hootsuite's CSV import standard.

---

## Key Takeaway
By combining sub-second Groq LPU inference with deterministic typography, safe-zone positioning, and rigorous automated validation, media organizations can systematically eliminate manual video production overhead.

Explore the engine and download the specification at https://incubrix.com.
