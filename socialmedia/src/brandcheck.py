"""Brand compliance and safety verification engine for IncuBrix.

Features:
- Rule-based checks:
  * Banned phrases from config/brand.yaml
  * Length limits (platform caption limits, max sentence length)
  * Hook presence verification
  * UTM tracking link presence & parameter validation
  * Hashtag count & mandatory brand hashtag adherence
- Groq-based judge (llama-3.3-70b-versatile):
  * Scores voice match (practitioner-led, punchy, anti-hype)
  * Flags any product claims not in VERIFIED_FEATURES
  * Flags any invented numbers, fake metrics, testimonials, or customer names
- Automated regeneration loop:
  * Failing assets are automatically regenerated up to 2 times with corrective feedback
  * Flags assets permanently if they fail after 2 regeneration attempts
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prioritize project root in sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
_src_dir = str(Path(__file__).resolve().parent)
while _src_dir in sys.path:
    sys.path.remove(_src_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from groq import Groq
from pydantic import BaseModel, Field

from src.config import get_brand_config, get_platforms_config, get_settings
from src.llm import GroqLLM
from src.logging.logger import get_logger

logger = get_logger("brandcheck")


class RuleCheckResult(BaseModel):
    """Outcome of deterministic rule-based checks."""

    passed: bool
    rule_score: float = Field(ge=0.0, le=100.0)
    banned_phrases_found: List[str] = Field(default_factory=list)
    length_violations: List[str] = Field(default_factory=list)
    hook_missing: bool = False
    utm_missing: bool = False
    hashtag_issues: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class GroqJudgeResult(BaseModel):
    """Outcome of Groq LLM editorial & safety evaluation."""

    passed: bool
    voice_score: float = Field(ge=0.0, le=100.0)
    unverified_claims: List[str] = Field(default_factory=list)
    invented_numbers_or_testimonials: List[str] = Field(default_factory=list)
    feedback: List[str] = Field(default_factory=list)
    suggested_revision: Optional[str] = None


class BrandCheckReport(BaseModel):
    """Consolidated audit report for an asset."""

    passed: bool
    score: float = Field(ge=0.0, le=100.0, description="Overall compliance score out of 100")
    rule_score: float = Field(ge=0.0, le=100.0)
    llm_tone_score: float = Field(ge=0.0, le=100.0)
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    unverified_claims: List[str] = Field(default_factory=list)
    invented_numbers_or_testimonials: List[str] = Field(default_factory=list)
    regeneration_attempts: int = 0
    status: str = "passed"  # "passed", "regenerated_and_passed", "flagged_failed"
    refined_text: str = ""


class BrandChecker:
    """Enterprise brand compliance auditor and automated regenerator."""

    def __init__(
        self,
        client: Optional[Groq] = None,
        max_regeneration_attempts: int = 2,
    ) -> None:
        self.settings = get_settings()
        self.brand = get_brand_config()
        self.platforms = get_platforms_config()
        self.max_regeneration_attempts = max_regeneration_attempts
        self.llm = GroqLLM(client=client, model=self.settings.groq_llm_model)

    @property
    def client(self) -> Groq:
        return self.llm.client

    # --------------------------------------------------------------------------
    # 1. Deterministic Rule-Based Checks
    # --------------------------------------------------------------------------
    def check_deterministic_rules(
        self,
        text: str,
        platform_id: Optional[str] = None,
        utm_url: Optional[str] = None,
        hook_text: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
    ) -> RuleCheckResult:
        """Run rule-based checks: banned phrases, length limits, hook, UTM, hashtags."""
        violations: List[str] = []
        warnings: List[str] = []
        banned_found: List[str] = []
        length_violations: List[str] = []
        hashtag_issues: List[str] = []
        score = 100.0

        lower_text = text.lower()
        banned_phrases = set(self.brand.rules.prohibited_words + (self.brand.banned_phrases or []))

        # 1. Banned Phrases Check (Hard violation: -25 pts each)
        for phrase in banned_phrases:
            pattern = r"\b" + re.escape(phrase.lower()) + r"\b"
            if re.search(pattern, lower_text):
                banned_found.append(phrase)
                violations.append(f"Contains banned phrase: '{phrase}'")
                score -= 25.0

        # 2. Length Limits Check
        spec = self.platforms.platforms.get(platform_id.lower()) if platform_id else None
        if spec:
            if len(text) > spec.max_caption_length:
                msg = f"Caption length ({len(text)} chars) exceeds {spec.name} limit ({spec.max_caption_length} chars)"
                length_violations.append(msg)
                violations.append(msg)
                score -= 20.0

        # Check sentence length
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        max_words = self.brand.rules.max_sentence_length_words
        for s in sentences:
            w_count = len(s.split())
            if w_count > max_words + 10:
                msg = f"Sentence exceeds length limit ({w_count} > {max_words} words): '{s[:45]}...'"
                warnings.append(msg)
                score -= 5.0
                break

        # 3. Hook Present Check
        effective_hook = hook_text or (sentences[0] if sentences else "")
        hook_missing = False
        if not effective_hook or len(effective_hook.strip()) < 8:
            hook_missing = True
            violations.append("Missing scroll-stopping hook statement")
            score -= 15.0

        # 4. UTM Tracking Link Present Check
        # Check text or explicit utm_url
        found_utm = False
        text_or_url = f"{text} {utm_url or ''}"
        if ("utm_source=" in text_or_url and "utm_campaign=" in text_or_url) or (utm_url and "utm_source=" in utm_url):
            found_utm = True

        utm_missing = not found_utm
        if utm_missing:
            warnings.append("Missing required UTM tracking link with campaign parameters")
            score -= 10.0

        # 5. Hashtag Count & Mandatory Brand Hashtags Check
        effective_tags = hashtags or re.findall(r"#\w+", text)
        if spec and spec.recommended_hashtag_count:
            if len(effective_tags) > spec.recommended_hashtag_count + 5:
                issue = f"Too many hashtags ({len(effective_tags)} > {spec.recommended_hashtag_count + 5})"
                hashtag_issues.append(issue)
                warnings.append(issue)
                score -= 5.0

        # Check mandatory brand hashtags
        for m_tag in self.brand.rules.mandatory_hashtags:
            if not any(m_tag.lower() == t.lower() for t in effective_tags) and "#incubrix" not in [t.lower() for t in effective_tags]:
                issue = f"Missing mandatory brand hashtag: '{m_tag}'"
                hashtag_issues.append(issue)
                warnings.append(issue)
                score -= 5.0
                break

        score = max(0.0, min(100.0, score))
        passed = (len(violations) == 0) and (score >= self.brand.rules.min_compliance_score)

        return RuleCheckResult(
            passed=passed,
            rule_score=round(score, 1),
            banned_phrases_found=banned_found,
            length_violations=length_violations,
            hook_missing=hook_missing,
            utm_missing=utm_missing,
            hashtag_issues=hashtag_issues,
            violations=violations,
            warnings=warnings,
        )

    # --------------------------------------------------------------------------
    # 2. Groq-Based Safety, Voice & Claim Judge
    # --------------------------------------------------------------------------
    def judge_with_groq(
        self,
        text: str,
        platform_id: Optional[str] = None,
    ) -> GroqJudgeResult:
        """Call Groq to judge voice match, unverified claims, and invented numbers/testimonials."""
        verified_features = self.brand.verified_features or []
        verified_features_str = (
            "\n".join(f"- {f}" for f in verified_features)
            if verified_features
            else "(NO VERIFIED FEATURES CURRENTLY REGISTERED. Any specific technical feature or performance claim must be rejected!)"
        )

        judge_prompt = f"""You are a strict, skeptical brand compliance auditor and fact-checker for {self.brand.name}.
Target Voice: {self.brand.tone.primary}, {self.brand.tone.secondary} ({self.brand.tone.style}).

VERIFIED FEATURES LIST:
\"\"\"
{verified_features_str}
\"\"\"

CONTENT TO EVALUATE:
\"\"\"
{text}
\"\"\"

CRITICAL AUDITING INSTRUCTIONS:
1. VOICE MATCH: Score voice alignment from 0 to 100 (practitioner-led, punchy, creator-fluent, anti-hype).
2. UNVERIFIED PRODUCT CLAIMS: Check if the text claims specific product capabilities, technical specs, or feature automations not explicitly in the VERIFIED FEATURES LIST.
   - Any claim outside the list MUST be flagged!
3. INVENTED NUMBERS / TESTIMONIALS: Flag any fabricated stats (e.g. "used by 50,000 creators", "boosted revenue by 342%"), fake customer names, or quotes.
4. If violations are found, write an improved, clean revision that fixes all issues without changing the core thesis.

Respond with valid JSON matching this schema:
{{
  "voice_score": <number 0-100>,
  "unverified_claims": ["claim 1", "claim 2"],
  "invented_numbers_or_testimonials": ["item 1", "item 2"],
  "feedback": ["feedback 1", "feedback 2"],
  "suggested_revision": "Clean revised copy removing unverified claims, fake numbers, and corporate hype"
}}
"""

        try:
            content, _ = self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a ruthless brand auditor. Always respond with valid JSON."},
                    {"role": "user", "content": judge_prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            data = json.loads(content)
            voice_score = float(data.get("voice_score", 85.0))
            unverified = data.get("unverified_claims", [])
            invented = data.get("invented_numbers_or_testimonials", [])
            feedback = data.get("feedback", [])
            suggested = data.get("suggested_revision", text)

            passed = (len(unverified) == 0) and (len(invented) == 0) and (voice_score >= 75.0)

            return GroqJudgeResult(
                passed=passed,
                voice_score=voice_score,
                unverified_claims=unverified,
                invented_numbers_or_testimonials=invented,
                feedback=feedback,
                suggested_revision=suggested,
            )
        except Exception as e:
            logger.warning(f"Groq brand judge unavailable or offline ({e}). Using deterministic heuristics.")
            # Heuristic check for invented metrics & customer testimonials
            invented = []
            if re.search(r"\b(100,000\+|50,000|10x|99%|300%|million dollars|\bclient \w+ said\b)\b", text, re.IGNORECASE):
                invented.append("Potential invented metric or unverified numerical claim detected")

            unverified = []
            if not verified_features and re.search(r"\b(guaranteed|patented technology|instant rendering engine)\b", text, re.IGNORECASE):
                unverified.append("Unverified product feature claim outside VERIFIED_FEATURES")

            passed = len(invented) == 0 and len(unverified) == 0
            return GroqJudgeResult(
                passed=passed,
                voice_score=85.0 if passed else 60.0,
                unverified_claims=unverified,
                invented_numbers_or_testimonials=invented,
                feedback=["Automated heuristic check executed"],
                suggested_revision=text,
            )

    # --------------------------------------------------------------------------
    # 3. Regeneration Loop (up to 2 attempts)
    # --------------------------------------------------------------------------
    def regenerate_asset_with_feedback(
        self,
        current_text: str,
        feedback_list: List[str],
        platform_id: Optional[str] = None,
    ) -> str:
        """Ask Groq to rewrite the asset strictly incorporating corrective feedback."""
        logger.info(f"Triggering automated asset regeneration with {len(feedback_list)} feedback points...")
        regen_prompt = f"""Rewrite the following social media post to fix all compliance failures.

ORIGINAL TEXT:
\"\"\"
{current_text}
\"\"\"

SPECIFIC COMPLIANCE FAILURES TO FIX:
{chr(10).join(f"- {fb}" for fb in feedback_list)}

RULES:
1. Remove all banned phrases, unverified product feature claims, and invented numbers/testimonials.
2. Keep the opening hook strong, punchy, and under 2 seconds.
3. Ensure tone is practitioner-led, direct, and anti-hype.
4. Output valid JSON: {{"regenerated_text": "your clean rewritten post"}}
"""

        try:
            content, _ = self.llm.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an elite copy editor. Output valid JSON."},
                    {"role": "user", "content": regen_prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            data = json.loads(content)
            return data.get("regenerated_text", current_text)
        except Exception as e:
            logger.error(f"Asset regeneration failed: {e}")
            return current_text

    def verify(
        self,
        text: str,
        platform_id: Optional[str] = None,
        utm_url: Optional[str] = None,
        hook_text: Optional[str] = None,
        hashtags: Optional[List[str]] = None,
    ) -> BrandCheckReport:
        """Full audit with automated regeneration loop (up to 2 times)."""
        candidate_text = text
        attempts = 0
        status = "passed"

        rule_res = self.check_deterministic_rules(
            candidate_text, platform_id=platform_id, utm_url=utm_url, hook_text=hook_text, hashtags=hashtags
        )
        judge_res = self.judge_with_groq(candidate_text, platform_id=platform_id)

        all_violations = list(rule_res.violations)
        if judge_res.unverified_claims:
            all_violations.extend([f"Unverified claim: {c}" for c in judge_res.unverified_claims])
        if judge_res.invented_numbers_or_testimonials:
            all_violations.extend([f"Invented stat/testimonial: {i}" for i in judge_res.invented_numbers_or_testimonials])

        passed = rule_res.passed and judge_res.passed

        # Regeneration loop if failing
        while not passed and attempts < self.max_regeneration_attempts:
            attempts += 1
            logger.warning(
                f"Asset failed brand check (attempt {attempts}/{self.max_regeneration_attempts}). Regenerating with feedback..."
            )
            feedback = all_violations + rule_res.warnings + judge_res.feedback
            candidate_text = self.regenerate_asset_with_feedback(candidate_text, feedback, platform_id=platform_id)

            # Re-evaluate regenerated asset
            rule_res = self.check_deterministic_rules(
                candidate_text, platform_id=platform_id, utm_url=utm_url, hook_text=hook_text, hashtags=hashtags
            )
            judge_res = self.judge_with_groq(candidate_text, platform_id=platform_id)

            all_violations = list(rule_res.violations)
            if judge_res.unverified_claims:
                all_violations.extend([f"Unverified claim: {c}" for c in judge_res.unverified_claims])
            if judge_res.invented_numbers_or_testimonials:
                all_violations.extend([f"Invented stat/testimonial: {i}" for i in judge_res.invented_numbers_or_testimonials])

            passed = rule_res.passed and judge_res.passed

        if passed:
            status = "regenerated_and_passed" if attempts > 0 else "passed"
        else:
            status = "flagged_failed"
            logger.error(f"Asset failed after {attempts} regeneration attempts. Flagged permanently.")

        composite_score = (rule_res.rule_score * 0.5) + (judge_res.voice_score * 0.5)

        return BrandCheckReport(
            passed=passed,
            score=round(composite_score, 1),
            rule_score=round(rule_res.rule_score, 1),
            llm_tone_score=round(judge_res.voice_score, 1),
            violations=all_violations,
            warnings=rule_res.warnings,
            suggestions=judge_res.feedback,
            unverified_claims=judge_res.unverified_claims,
            invented_numbers_or_testimonials=judge_res.invented_numbers_or_testimonials,
            regeneration_attempts=attempts,
            status=status,
            refined_text=candidate_text,
        )


# Backward compatibility aliasing for legacy imports
sys.modules["src.brandcheck.checker"] = sys.modules[__name__]
sys.modules["src.brandcheck.models"] = sys.modules[__name__]
