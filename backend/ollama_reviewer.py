"""
Ollama LLM reasoning module for the SAHPRA M5 S.5 agent (Phase 5).

Responsibilities:
  - Detect whether Ollama is running locally and which models are available.
  - Select a suitable model from the preferred list.
  - Build a structured prompt from an S5Claim + S5Finding.
  - Call the Ollama generate API and parse the response into a ModelReview.
  - Degrade gracefully (return None) on any connectivity or parse failure.

Separation of concerns
──────────────────────
  This module ONLY produces ModelReview objects — AI reasoning commentary.
  It does NOT set qa_status, verdict, evidence_sufficiency or any other
  deterministic assessment field.  Python validation logic in s5_standards.py
  and qa_critic.py remains solely responsible for those fields.
  The human assessor retains final decision-making authority.

Ollama API used
───────────────
  GET  http://localhost:11434/api/tags      — list available models
  POST http://localhost:11434/api/generate  — generate a completion
  No authentication.  Calls are fire-and-forget with a 15-second timeout.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx

from models import ModelReview, S5Claim, S5Finding

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TIMEOUT_SECONDS = 15.0

# Models tried in preference order.  The first match found in the available
# list is used.  Preference: recency + instruction-following quality.
_PREFERRED_MODELS: list[str] = [
    "llama3.2",
    "llama3.1",
    "llama3",
    "mistral",
    "phi3",
    "gemma2",
    "qwen2.5",
]

# ── Availability check ────────────────────────────────────────────────────────

def check_ollama_available() -> tuple[bool, list[str]]:
    """
    Check whether Ollama is running and return the list of available model names.

    Returns:
      (True,  ["llama3.2", ...]) — Ollama is reachable; models listed.
      (False, [])                — Ollama is not reachable or returned an error.

    Never raises.
    """
    try:
        response = httpx.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()
        # Response: {"models": [{"name": "llama3.2:latest", ...}, ...]}
        models_raw: list[dict] = data.get("models", [])
        # Normalise: strip tag suffix so "llama3.2:latest" matches "llama3.2"
        model_names = [m["name"].split(":")[0] for m in models_raw if "name" in m]
        return True, model_names
    except Exception as exc:  # noqa: BLE001
        logger.debug("Ollama availability check failed: %s", exc)
        return False, []


def pick_model(available: list[str]) -> str | None:
    """
    Return the first preferred model found in the available list, or None.

    Matching is case-insensitive and ignores tag suffixes (already stripped by
    check_ollama_available).
    """
    available_lower = {m.lower() for m in available}
    for preferred in _PREFERRED_MODELS:
        if preferred.lower() in available_lower:
            # Return the original casing from the available list
            for m in available:
                if m.lower() == preferred.lower():
                    return m
    return None


# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(
    claim: S5Claim,
    finding: S5Finding,
    kb_hits: "list | None" = None,
    dossier_hits: "list | None" = None,
) -> str:
    """
    Build the structured prompt sent to the Ollama model.

    The prompt instructs the model to:
      - Reason only — not to produce a verdict or QA status.
      - Respond with a JSON object containing exactly four keys.
      - Base reasoning on IPRP QWGG S.5 and Ph. Eur. 5.12.
      - Flag gaps, inconsistencies, and suggested questions.

    Optional:
      kb_hits      — ExtractionResult list from regulatory KB (Phase 4 RAG).
      dossier_hits — ExtractionResult list from applicant dossier (Phase 4 RAG).
      When provided, up to 4 excerpts from each are injected into the prompt
      so the model reasons against retrieved evidence rather than training memory.
    """
    flags_text = (
        "\n".join(f"  - {f}" for f in finding.completeness_flags)
        if finding.completeness_flags
        else "  (none identified by deterministic check)"
    )

    claim_summary_lines = [
        f"Substance: {claim.substance_name}",
        f"Standard: {claim.standard}",
        f"Edition claimed: {claim.edition_claimed}",
        f"Submission date: {claim.submission_date}",
        f"Standard type: {claim.standard_type.value if claim.standard_type else 'not stated'}",
        f"Lot number: {claim.lot_number or 'not provided'}",
        f"CoA submitted: {claim.coa_submitted}",
        f"IR spectra submitted: {claim.ir_spectra_submitted}",
        f"Working standard qualified against primary: {claim.working_std_qualified_against_primary}",
        f"Reference standard source: {claim.reference_standard_source_detail or 'not provided'}",
        f"Test method: {claim.test_method or 'not stated'}",
        f"Intended use: {', '.join(claim.intended_use) if claim.intended_use else 'not declared'}",
    ]
    if claim.inhouse_characterisation_methods:
        claim_summary_lines.append(
            f"In-house characterisation methods: {', '.join(claim.inhouse_characterisation_methods)}"
        )
    if claim.purity_assignment:
        pa = claim.purity_assignment
        claim_summary_lines.append(
            f"Purity assignment: {pa.method}, {pa.value_percent}%, "
            f"source={pa.source}, traceable={pa.is_traceable}"
        )
    if claim.impurity_standards:
        for imp in claim.impurity_standards:
            claim_summary_lines.append(
                f"Impurity standard: {imp.official_name}, source={imp.source}, "
                f"purity={imp.purity_percent}%, methods={imp.characterisation_methods}"
            )

    claim_text = "\n".join(f"  {line}" for line in claim_summary_lines)

    # Build optional KB evidence block (up to 4 excerpts, truncated to 150 chars each)
    if kb_hits:
        _kb_lines = []
        for h in kb_hits[:4]:
            excerpt = h.raw_text[:150].replace("\n", " ").strip()
            _kb_lines.append(f"  [{h.source_type.value}:{h.section_id}] {excerpt}")
        _kb_context_block = (
            "REGULATORY KNOWLEDGE BASE EVIDENCE (retrieved — not authoritative)\n"
            "────────────────────────────────────────────────────────────────────\n"
            + "\n".join(_kb_lines)
            + "\n\n"
            "Note: These excerpts are from ingested guidance documents. They are\n"
            "provided to inform your reasoning only, not as verified regulatory decisions.\n\n"
        )
    else:
        _kb_context_block = ""

    # Build optional dossier evidence block (up to 4 excerpts)
    if dossier_hits:
        _dos_lines = []
        for h in dossier_hits[:4]:
            excerpt = h.raw_text[:150].replace("\n", " ").strip()
            _dos_lines.append(f"  [{h.section_id}] {excerpt}")
        _dossier_context_block = (
            "APPLICANT DOSSIER EXTRACTS (uploaded — not independently verified)\n"
            "────────────────────────────────────────────────────────────────────\n"
            + "\n".join(_dos_lines)
            + "\n\n"
            "Note: These excerpts are from the applicant's uploaded dossier. They\n"
            "represent the applicant's claims, not independently verified evidence.\n\n"
        )
    else:
        _dossier_context_block = ""

    prompt = f"""You are a pharmaceutical regulatory QA support tool assisting a human assessor
reviewing CTD Module 3.2.S.5 (Reference Standards or Materials) for a drug substance dossier.

Your role is REASONING SUPPORT ONLY. You must NOT produce a verdict, compliance determination,
or QA status. The human assessor makes all final decisions.

CLAIM SUBMITTED BY APPLICANT
─────────────────────────────
{claim_text}

PYTHON DETERMINISTIC ASSESSMENT (already complete — do not repeat or override)
────────────────────────────────────────────────────────────────────────────────
  Verdict: {finding.verdict}
  Verdict reason: {finding.verdict_reason}
  Evidence sufficiency: {finding.evidence_sufficiency or 'not yet derived'}
  Completeness flags (IPRP checklist gaps already identified):
{flags_text}

{_kb_context_block}{_dossier_context_block}YOUR TASK
──────────
Review the claim above against the IPRP QWGG Guidance for Quality Assessors — Drug Substance,
Section S.5 Reference Standards or Materials, and Ph. Eur. Chapter 5.12.

Identify any of the following that the Python check may have MISSED or that warrant
additional assessor attention:
  1. Potential inconsistencies between stated fields (e.g. standard type vs characterisation
     requirements, lot number format vs claimed pharmacopoeia conventions).
  2. Missing information not covered by the deterministic flags above.
  3. Claims or statements that appear unsupported by the evidence provided.
  4. Questions the assessor should put to the applicant.

RESPONSE FORMAT — respond with ONLY valid JSON, no prose before or after:
{{
  "potential_issues": ["<issue 1>", "<issue 2>"],
  "missing_info": ["<item 1>", "<item 2>"],
  "unsupported_conclusions": ["<statement 1>"],
  "assessor_questions": ["<question 1>", "<question 2>"]
}}

Rules:
- Each list may be empty ([]) if nothing applies.
- Maximum 5 items per list.
- Each item is a single concise sentence (≤ 25 words).
- Do not restate information already in the Python completeness flags.
- Do not produce a verdict, compliance score, or QA status.
- Do not fabricate regulatory citations you are not certain of.
"""
    return prompt


# ── Ollama API call ───────────────────────────────────────────────────────────

def run_ollama_review(
    claim: S5Claim,
    finding: S5Finding,
    model: str,
    kb_hits: "list | None" = None,
    dossier_hits: "list | None" = None,
) -> ModelReview | None:
    """
    Call the Ollama generate API and parse the response into a ModelReview.

    Returns None on any error: timeout, connection refused, non-200 response,
    JSON parse failure, or missing required keys.

    kb_hits / dossier_hits — optional Phase 4 RAG evidence lists.  When
    provided they are injected into the prompt as evidence context.

    Never raises.
    """
    prompt = build_prompt(claim, finding, kb_hits=kb_hits, dossier_hits=dossier_hits)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,   # low temperature for consistent structured output
            "num_predict": 512,   # cap token count — we only need a short JSON object
        },
    }

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        raw_text: str = data.get("response", "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama generate call failed for model %r: %s", model, exc)
        return None

    # Parse the JSON response — the model should have responded with only JSON
    parsed = _extract_json(raw_text)
    if parsed is None:
        logger.warning(
            "Ollama response for model %r could not be parsed as JSON. Raw: %.200s",
            model,
            raw_text,
        )
        return None

    try:
        return ModelReview(
            model_name=model,
            generated_at=datetime.now(timezone.utc).isoformat(),
            potential_issues=_safe_list(parsed.get("potential_issues")),
            missing_info=_safe_list(parsed.get("missing_info")),
            unsupported_conclusions=_safe_list(parsed.get("unsupported_conclusions")),
            assessor_questions=_safe_list(parsed.get("assessor_questions")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ModelReview construction failed: %s", exc)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """
    Extract the first JSON object from text.

    Models sometimes wrap their response in prose or markdown code fences.
    This function tries three strategies:
      1. Direct parse of the full text.
      2. Extract content between the first { and last }.
      3. Strip a ```json ... ``` markdown fence then parse.
    """
    text = text.strip()

    # Strategy 1: direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Strategy 2: find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: strip markdown fence
    if "```" in text:
        lines = text.splitlines()
        inner = []
        in_fence = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                inner.append(line)
        joined = "\n".join(inner).strip()
        try:
            result = json.loads(joined)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


def _safe_list(value: object) -> list[str]:
    """Return value as a list[str], or [] if value is not a list."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]
