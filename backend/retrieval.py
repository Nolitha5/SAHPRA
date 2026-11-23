"""
backend/retrieval.py
====================
Controlled web-based monograph retrieval for SAHPRA M5 S.5 agent.

Architecture
------------
Three-tier evidence model:
  Tier 1  – Authoritative freely-accessible APIs (CrossRef / PubChem / OpenFDA)
  Tier 2  – Public regulatory guidance documents (IPRP QWGG, Ph. Eur. 5.12 summary)
  Tier 3  – General web discovery only  →  DISCOVERY_ONLY label, never promoted to findings

Design constraints (verbatim from project brief)
-------------------------------------------------
* Do NOT scrape restricted or paywalled pharmacopoeial content.
* Do NOT treat unverified copies as authoritative evidence.
* content_verified is ALWAYS False for machine-retrieved records.
  A human reviewer must check the primary source and flip the flag.
* No hardcoding for specific APIs – the same functions work for all 40 APIs
  in the inventory via INN→USAN synonym resolution (PubChem) + CrossRef prefix
  search (USP DOI prefix 10.31003).
* NEEDS_REVIEW is returned when records are unavailable rather than raising.
* This module is standalone – importing it never modifies models.py or
  s5_standards.py; it exposes the MonographRepository Protocol so
  s5_standards.py can inject either the mock or the real implementation.

Public API
----------
  RetrievedMonographRecord   – provenance-carrying dataclass
  MonographRepository        – Protocol (structural subtyping)
  MockMonographRepository    – in-memory, no outbound requests
  WebMonographRepository     – live CrossRef + PubChem lookup

Utility helpers (also importable for tests)
-------------------------------------------
  resolve_usp_name(inn_name)       – INN → USP/USAN name via PubChem
  crossref_usp_lookup(usp_name)    – DOI + date via CrossRef prefix 10.31003
  pubchem_substance_lookup(name)   – CID + CAS + InChIKey via PubChem REST
  build_usp_citation(record)       – doi.org citation string
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSL context – uses the proxy CA bundle present in the cloud container.
# Falls back to system default so local development still works.
# ---------------------------------------------------------------------------
_CA_BUNDLE = "/root/.ccr/ca-bundle.crt"

def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.load_verify_locations(_CA_BUNDLE)
    except (FileNotFoundError, ssl.SSLError, PermissionError):
        pass  # local dev or cloud container – system CAs are fine
    return ctx


_CTX = _ssl_context()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USP_DOI_PREFIX = "10.31003"
CROSSREF_WORKS_URL = "https://api.crossref.org/prefixes/{prefix}/works"
PUBCHEM_SYNONYMS_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON"
)
PUBCHEM_PROPS_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}"
    "/property/IUPACName,MolecularFormula,InChIKey/JSON"
)
PUBCHEM_CAS_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/synonyms/JSON"
)

# User-Agent string for all outbound requests
_UA = "SAHPRA-M5-Research/1.0 (SAHPRA regulatory prototype; not for clinical use)"

# Request timeout in seconds
_TIMEOUT = 12

# CrossRef polite-pool rate: max 1 req/s; we do not need to enforce it here
# because retrieval is called sequentially per claim, not in a tight loop.

# ---------------------------------------------------------------------------
# Evidence tier constants
# ---------------------------------------------------------------------------

TIER_1_EXISTENCE_CONFIRMED = "TIER_1_EXISTENCE_CONFIRMED"
TIER_1_CONTENT_VERIFIED = "TIER_1_CONTENT_VERIFIED"   # set by human only
TIER_2_GUIDANCE = "TIER_2_GUIDANCE"
TIER_3_DISCOVERY_ONLY = "TIER_3_DISCOVERY_ONLY"
NEEDS_REVIEW = "NEEDS_REVIEW"


# ---------------------------------------------------------------------------
# Dataclass: RetrievedMonographRecord
# ---------------------------------------------------------------------------

@dataclass
class RetrievedMonographRecord:
    """
    Provenance-carrying record returned by any MonographRepository
    implementation.

    Fields
    ------
    substance_name       Input name as provided by the caller (INN or USAN).
    usp_name             Resolved USP/USAN name (may differ from INN).
    pharmacopoeia        "USP" / "Ph. Eur." / "WHO Ph.Int." / None
    edition              Approximate edition string, e.g. "USP 46-NF 41 (est.)"
    doi                  CrossRef DOI if confirmed, else None.
    doi_url              Full doi.org hyperlink, else None.
    doi_created_date     ISO 8601 date string when CrossRef record was created.
    pubchem_cid          PubChem CID integer, else None.
    cas_number           CAS registry number string, else None.
    inchi_key            InChIKey string, else None.
    source_url           Primary citation URL (doi.org preferred).
    retrieved_at         ISO 8601 UTC timestamp of retrieval.
    evidence_tier        One of the TIER_* constants above.
    content_verified     Always False for machine retrieval.
                         A human reviewer sets this to True after consulting
                         the primary source (e.g. usp.org) directly.
    raw_excerpt          Short text excerpt if available; None otherwise.
    retrieval_note       Human-readable explanation of what was or was not found.
    """

    substance_name: str
    usp_name: Optional[str] = None
    pharmacopoeia: Optional[str] = None
    edition: Optional[str] = None
    doi: Optional[str] = None
    doi_url: Optional[str] = None
    doi_created_date: Optional[str] = None
    pubchem_cid: Optional[int] = None
    cas_number: Optional[str] = None
    inchi_key: Optional[str] = None
    source_url: Optional[str] = None
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    evidence_tier: str = NEEDS_REVIEW
    content_verified: bool = False
    raw_excerpt: Optional[str] = None
    retrieval_note: str = ""

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON output."""
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Protocol: MonographRepository
# ---------------------------------------------------------------------------

@runtime_checkable
class MonographRepository(Protocol):
    """
    Structural protocol implemented by both MockMonographRepository and
    WebMonographRepository.  s5_standards.py accepts this type so the
    calling code never needs to know which backend is active.
    """

    def get(self, substance_name: str) -> RetrievedMonographRecord:
        """
        Look up a monograph by substance name (INN or USAN acceptable).

        Returns a RetrievedMonographRecord.  Never raises – returns a record
        with evidence_tier == NEEDS_REVIEW when nothing is found.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url: str, params: Optional[dict] = None) -> Optional[dict]:
    """
    GET *url* (with optional query *params*) and return parsed JSON, or None
    on any network / HTTP / parse error.  All errors are logged at WARNING.
    """
    if params:
        qs = "&".join(
            f"{k}={urllib.request.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP %s fetching %s", exc.code, url)
    except urllib.error.URLError as exc:
        logger.warning("URL error fetching %s: %s", url, exc.reason)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("JSON decode error from %s: %s", url, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error fetching %s: %s", url, exc)
    return None


# ---------------------------------------------------------------------------
# PubChem helpers
# ---------------------------------------------------------------------------

def pubchem_substance_lookup(name: str) -> dict:
    """
    Look up a substance by name in PubChem.

    Returns a dict with keys:
      cid          int | None
      cas_number   str | None
      inchi_key    str | None
      synonyms     list[str]
      found        bool
    """
    empty: dict = {
        "cid": None,
        "cas_number": None,
        "inchi_key": None,
        "synonyms": [],
        "found": False,
    }

    encoded = urllib.request.quote(name)

    # --- Synonyms (includes CAS) ---
    syn_url = PUBCHEM_SYNONYMS_URL.format(name=encoded)
    syn_data = _get_json(syn_url)
    synonyms: list[str] = []
    cas: Optional[str] = None
    cid: Optional[int] = None

    if syn_data:
        info_list = syn_data.get("InformationList", {}).get("Information", [])
        if info_list:
            entry = info_list[0]
            cid = entry.get("CID")
            synonyms = entry.get("Synonym", [])
            # CAS numbers match pattern NNN-NN-N (digits and hyphens)
            cas_pattern = re.compile(r"^\d{2,7}-\d{2}-\d$")
            for s in synonyms:
                if cas_pattern.match(s.strip()):
                    cas = s.strip()
                    break

    if not synonyms:
        return empty

    # --- Properties (InChIKey) ---
    prop_url = PUBCHEM_PROPS_URL.format(name=encoded)
    prop_data = _get_json(prop_url)
    inchi_key: Optional[str] = None
    if prop_data:
        props = (
            prop_data.get("PropertyTable", {})
            .get("Properties", [{}])[0]
        )
        inchi_key = props.get("InChIKey")

    return {
        "cid": cid,
        "cas_number": cas,
        "inchi_key": inchi_key,
        "synonyms": synonyms,
        "found": True,
    }


def resolve_usp_name(inn_name: str) -> str:
    """
    Resolve an INN name to its USP/USAN equivalent using PubChem synonyms.

    For many substances the names are identical.  For others the mapping is
    well-known (e.g. Paracetamol → Acetaminophen, Rifampicin → Rifampin,
    Salbutamol → Albuterol).  PubChem lists both INN and USAN as synonyms
    so we look for a synonym that CrossRef can find.

    Strategy
    --------
    1. Return *inn_name* unchanged (most APIs match directly).
    2. Try PubChem synonyms and check each one against CrossRef prefix
       10.31003 until a hit is found.
    3. If still nothing, return *inn_name* (CrossRef will return 0 results
       and the caller will record NEEDS_REVIEW).

    This function is intentionally lenient – it never raises.
    """
    # Short-circuit: try the name as-is first (avoids a PubChem round-trip)
    result = crossref_usp_lookup(inn_name)
    if result.get("found"):
        return inn_name

    # Fetch PubChem synonyms
    encoded = urllib.request.quote(inn_name)
    syn_url = PUBCHEM_SYNONYMS_URL.format(name=encoded)
    syn_data = _get_json(syn_url)
    if not syn_data:
        return inn_name

    info_list = syn_data.get("InformationList", {}).get("Information", [])
    if not info_list:
        return inn_name

    synonyms = info_list[0].get("Synonym", [])

    # Filter to plausible drug-name synonyms (letters, spaces, hyphens; ≤60 chars)
    name_re = re.compile(r"^[A-Za-z][A-Za-z0-9 \-]{1,58}$")
    candidates = [s for s in synonyms if name_re.match(s.strip())]

    for candidate in candidates[:20]:  # limit to avoid runaway requests
        if crossref_usp_lookup(candidate).get("found"):
            logger.info("INN→USAN resolved: %r → %r", inn_name, candidate)
            return candidate

    return inn_name


# ---------------------------------------------------------------------------
# CrossRef helpers
# ---------------------------------------------------------------------------

# Approximate USP edition from CrossRef creation year/month.
# Source: USP publication schedule (annual editions, May supplements).
# These are estimates; the authoritative edition is on the USP label itself.
_USP_EDITION_MAP = [
    # (year, month_from, month_to_inclusive, edition_label)
    (2021, 1, 12, "USP 44-NF 39 (est.)"),
    (2022, 1, 5, "USP 45-NF 40 (est.)"),
    (2022, 6, 12, "USP 46-NF 41 (est.)"),
    (2023, 1, 5, "USP 46-NF 41 (est.)"),
    (2023, 6, 12, "USP 47-NF 42 (est.)"),
    (2024, 1, 5, "USP 47-NF 42 (est.)"),
    (2024, 6, 12, "USP 48-NF 43 (est.)"),
    (2025, 1, 5, "USP 48-NF 43 (est.)"),
    (2025, 6, 12, "USP 49-NF 44 (est.)"),
    (2026, 1, 12, "USP 49-NF 44 (est.)"),
]


def _estimate_usp_edition(year: int, month: int) -> str:
    for y, m_from, m_to, label in _USP_EDITION_MAP:
        if y == year and m_from <= month <= m_to:
            return label
    return f"USP (est. {year})"


def crossref_usp_lookup(usp_name: str, max_results: int = 5) -> dict:
    """
    Search CrossRef for a USP monograph by name under prefix 10.31003.

    Returns a dict with keys:
      found          bool
      doi            str | None   – most-recent DOI for a substance monograph
      doi_url        str | None   – https://doi.org/<doi>
      created_date   str | None   – ISO date YYYY-MM-DD
      edition_est    str | None   – estimated USP edition (see _USP_EDITION_MAP)
      title          str | None   – title as recorded in CrossRef
      all_dois       list[str]    – all matching substance-monograph DOIs
    """
    empty: dict = {
        "found": False,
        "doi": None,
        "doi_url": None,
        "created_date": None,
        "edition_est": None,
        "title": None,
        "all_dois": [],
    }

    url = CROSSREF_WORKS_URL.format(prefix=USP_DOI_PREFIX)
    data = _get_json(
        url,
        params={
            "query": usp_name,
            "rows": max_results,
            "mailto": "research@sahpra.org.za",
        },
    )
    if not data:
        return empty

    items = data.get("message", {}).get("items", [])
    if not items:
        return empty

    # Keep only substance monographs: title matches the queried name and
    # is short (product monographs like "Amlodipine Besylate Tablets" are longer).
    name_lower = usp_name.lower()

    def _is_substance_monograph(item: dict) -> bool:
        titles = item.get("title", [])
        if not titles:
            return False
        t = titles[0].lower()
        return name_lower in t and len(titles[0]) < 70

    substance_items = [i for i in items if _is_substance_monograph(i)]
    if not substance_items:
        return empty

    # Pick the most recent by creation date
    def _creation_sort_key(item: dict) -> list:
        return item.get("created", {}).get("date-parts", [[0]])[0]

    substance_items.sort(key=_creation_sort_key, reverse=True)
    best = substance_items[0]

    doi = best.get("DOI", "")
    date_parts = best.get("created", {}).get("date-parts", [[None, None, None]])[0]
    year = date_parts[0] if len(date_parts) > 0 else None
    month = date_parts[1] if len(date_parts) > 1 else 1
    day = date_parts[2] if len(date_parts) > 2 else 1

    if year:
        created_date = f"{year:04d}-{month:02d}-{day:02d}"
        edition_est = _estimate_usp_edition(year, month)
    else:
        created_date = None
        edition_est = None

    return {
        "found": True,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else None,
        "created_date": created_date,
        "edition_est": edition_est,
        "title": best.get("title", [None])[0],
        "all_dois": [i.get("DOI", "") for i in substance_items],
    }


# ---------------------------------------------------------------------------
# Citation builder
# ---------------------------------------------------------------------------

def build_usp_citation(record: RetrievedMonographRecord) -> str:
    """
    Build a human-readable USP citation string from a retrieved record.

    Format (mirrors USP citation guidance):
      U.S. Pharmacopeial Convention. <Substance Name>. <Edition (est.)>.
      DOI: <doi>. Retrieved <YYYY-MM-DD>.
    """
    parts = ["U.S. Pharmacopeial Convention"]
    name = record.usp_name or record.substance_name
    parts.append(name + ".")
    if record.edition:
        parts.append(record.edition + ".")
    if record.doi:
        parts.append(f"DOI: {record.doi}.")
    if record.doi_url:
        parts.append(f"Available at: {record.doi_url}.")
    if record.retrieved_at:
        date_str = record.retrieved_at[:10]
        parts.append(f"Retrieved {date_str}.")
    parts.append("[content_verified=False — human review required]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# WebMonographRepository
# ---------------------------------------------------------------------------

class WebMonographRepository:
    """
    Live Tier-1 monograph existence lookup.

    Uses CrossRef (USP DOI prefix 10.31003) + PubChem (substance identity
    and INN→USAN resolution).  Never fetches paywalled content.

    Usage
    -----
    repo = WebMonographRepository()
    record = repo.get("Amlodipine Besylate")
    # → RetrievedMonographRecord with evidence_tier=TIER_1_EXISTENCE_CONFIRMED
    #   and content_verified=False

    Thread safety
    -------------
    Stateless — safe to call concurrently, though CrossRef polite-pool
    guidelines recommend ≤1 req/s from a single client.
    """

    def get(self, substance_name: str) -> RetrievedMonographRecord:
        """
        Look up *substance_name* (INN or USAN acceptable) in USP via CrossRef.

        Steps
        -----
        1. Attempt CrossRef lookup with the name as supplied.
        2. If not found, resolve INN→USAN via PubChem and retry CrossRef.
        3. Attempt PubChem substance identity lookup for CID/CAS/InChIKey.
        4. Compose and return a RetrievedMonographRecord.

        Never raises.  Returns evidence_tier=NEEDS_REVIEW if nothing found.
        """
        retrieved_at = datetime.now(timezone.utc).isoformat()
        note_parts: list[str] = []

        # --- Step 1: CrossRef lookup (name as-is) ---
        cr = crossref_usp_lookup(substance_name)

        # --- Step 2: INN→USAN resolution if needed ---
        resolved_name = substance_name
        if not cr["found"]:
            note_parts.append(
                f"CrossRef found no USP monograph for '{substance_name}' as supplied."
            )
            resolved_name = resolve_usp_name(substance_name)
            if resolved_name != substance_name:
                note_parts.append(
                    f"PubChem synonym resolution: '{substance_name}' → '{resolved_name}'."
                )
                cr = crossref_usp_lookup(resolved_name)
            else:
                note_parts.append(
                    "No USAN synonym found via PubChem; CrossRef result remains empty."
                )

        # --- Step 3: PubChem substance identity ---
        pc = pubchem_substance_lookup(resolved_name)
        if not pc["found"]:
            # Try original name in case resolved name fails PubChem
            pc = pubchem_substance_lookup(substance_name)

        # --- Step 4: Compose record ---
        if cr["found"]:
            edition = cr.get("edition_est") or "USP (edition unverified)"
            doi = cr["doi"]
            doi_url = cr["doi_url"]
            source_url = doi_url or f"https://store.usp.org"
            note_parts.append(
                f"USP monograph existence confirmed via CrossRef DOI {doi}. "
                f"Full text requires usp.org access. "
                f"content_verified=False — human review required."
            )
            evidence_tier = TIER_1_EXISTENCE_CONFIRMED
            retrieval_note = " ".join(note_parts)
        else:
            edition = None
            doi = None
            doi_url = None
            source_url = None
            evidence_tier = NEEDS_REVIEW
            note_parts.append(
                "No USP monograph found in CrossRef for this substance. "
                "Manual lookup on usp.org or alternative pharmacopoeia required."
            )
            retrieval_note = " ".join(note_parts)

        return RetrievedMonographRecord(
            substance_name=substance_name,
            usp_name=resolved_name if resolved_name != substance_name else None,
            pharmacopoeia="USP" if cr["found"] else None,
            edition=edition,
            doi=doi,
            doi_url=doi_url,
            doi_created_date=cr.get("created_date"),
            pubchem_cid=pc.get("cid"),
            cas_number=pc.get("cas_number"),
            inchi_key=pc.get("inchi_key"),
            source_url=source_url,
            retrieved_at=retrieved_at,
            evidence_tier=evidence_tier,
            content_verified=False,
            raw_excerpt=None,
            retrieval_note=retrieval_note,
        )


# ---------------------------------------------------------------------------
# MockMonographRepository
# ---------------------------------------------------------------------------

# Minimal in-memory fixture records for the three substances already in the
# s5_standards.py mock.  These are used by unit tests that run offline.
_MOCK_FIXTURE: dict[str, dict] = {
    "amlodipine besylate": {
        "usp_name": "Amlodipine Besylate",
        "pharmacopoeia": "USP",
        "edition": "USP 46-NF 41 (est.)",
        "doi": "10.31003/uspnf_m3570_06_01",
        "doi_url": "https://doi.org/10.31003/uspnf_m3570_06_01",
        "doi_created_date": "2022-11-14",
        "pubchem_cid": 60496,
        "cas_number": "111470-99-6",
        "inchi_key": "ZPBWCRDSRKPIDG-UHFFFAOYSA-N",
        "source_url": "https://doi.org/10.31003/uspnf_m3570_06_01",
        "evidence_tier": TIER_1_EXISTENCE_CONFIRMED,
        "content_verified": False,
        "raw_excerpt": None,
        "retrieval_note": (
            "Mock fixture — mirrors CrossRef DOI confirmed 2022-11-14. "
            "content_verified=False — human review required."
        ),
    },
    "valsartan": {
        "usp_name": "Valsartan",
        "pharmacopoeia": "USP",
        "edition": "USP 44-NF 39 (est.)",
        "doi": "10.31003/uspnf_m87730_05_01",
        "doi_url": "https://doi.org/10.31003/uspnf_m87730_05_01",
        "doi_created_date": "2021-08-16",
        "pubchem_cid": 60846,
        "cas_number": "137862-53-4",
        "inchi_key": None,
        "source_url": "https://doi.org/10.31003/uspnf_m87730_05_01",
        "evidence_tier": TIER_1_EXISTENCE_CONFIRMED,
        "content_verified": False,
        "raw_excerpt": None,
        "retrieval_note": (
            "Mock fixture — mirrors CrossRef DOI confirmed 2021-08-16. "
            "content_verified=False — human review required."
        ),
    },
    "hydrochlorothiazide": {
        "usp_name": "Hydrochlorothiazide",
        "pharmacopoeia": "USP",
        "edition": "USP 44-NF 39 (est.)",
        "doi": "10.31003/uspnf_m37940_05_01",
        "doi_url": "https://doi.org/10.31003/uspnf_m37940_05_01",
        "doi_created_date": "2021-08-16",
        "pubchem_cid": 3639,
        "cas_number": "58-93-5",
        "inchi_key": None,
        "source_url": "https://doi.org/10.31003/uspnf_m37940_05_01",
        "evidence_tier": TIER_1_EXISTENCE_CONFIRMED,
        "content_verified": False,
        "raw_excerpt": None,
        "retrieval_note": (
            "Mock fixture — mirrors CrossRef DOI confirmed 2021-08-16. "
            "content_verified=False — human review required."
        ),
    },
}


class MockMonographRepository:
    """
    In-memory monograph repository for unit tests and offline use.

    Returns fixture records for the three substances in _MOCK_FIXTURE.
    Returns a NEEDS_REVIEW record for any other name so tests can verify
    the fallback path without making real network requests.

    Implements the MonographRepository Protocol.
    """

    def get(self, substance_name: str) -> RetrievedMonographRecord:
        key = substance_name.strip().lower()
        fixture = _MOCK_FIXTURE.get(key)
        retrieved_at = datetime.now(timezone.utc).isoformat()

        if fixture:
            return RetrievedMonographRecord(
                substance_name=substance_name,
                retrieved_at=retrieved_at,
                **{k: v for k, v in fixture.items() if k != "substance_name"},
            )

        return RetrievedMonographRecord(
            substance_name=substance_name,
            retrieved_at=retrieved_at,
            evidence_tier=NEEDS_REVIEW,
            content_verified=False,
            retrieval_note=(
                f"No mock fixture for '{substance_name}'. "
                "Use WebMonographRepository for live lookup, or add a fixture."
            ),
        )


# ---------------------------------------------------------------------------
# Phase 3: query_ingested_documents
# ---------------------------------------------------------------------------

def query_ingested_documents(
    standard: str,
    substance_name: str,
    source_types: "list[str] | None" = None,
) -> "list":
    """
    Search the in-memory extraction store (populated by ingestor.py) for
    sections that mention *standard* and/or *substance_name*.

    Three-tier ranking
    ------------------
    Tier A  Exact match   – raw_text contains both standard AND substance_name
            (case-insensitive).
    Tier B  Standard match – raw_text contains standard only.
    Tier C  Source-type match – extraction's source_type is in *source_types*
            but no keyword match.

    Parameters
    ----------
    standard        : pharmacopoeial standard name, e.g. "USP", "Ph. Eur."
    substance_name  : INN/USAN name, e.g. "Amlodipine Besylate"
    source_types    : optional list of DocumentSourceType value strings to
                      limit results (e.g. ["v2_mapping", "iprp_guidance"]).
                      None means all source types.

    Returns
    -------
    list[ExtractionResult] – ranked Tier A first, then B, then C.
    Empty list when the extraction store is empty or no match is found.

    Design notes
    ------------
    * Imports from ingestor are done lazily (inside the function) to keep
      retrieval.py importable even when ingestor is not on the path.
    * Never raises.  Errors are logged at WARNING and an empty list is returned.
    * This function is intentionally read-only: it never modifies _EXTRACTION_STORE.
    """
    try:
        from ingestor import _EXTRACTION_STORE  # noqa: PLC0415
    except ImportError:
        logger.warning("query_ingested_documents: ingestor not available; returning []")
        return []

    std_lower = standard.strip().lower()
    sub_lower = substance_name.strip().lower()
    allowed_types = set(source_types) if source_types else None

    tier_a: list = []
    tier_b: list = []
    tier_c: list = []

    for extractions in _EXTRACTION_STORE.values():
        for ext in extractions:
            # Source-type filter (applied regardless of keyword match)
            if allowed_types is not None and ext.source_type.value not in allowed_types:
                continue

            text = ext.raw_text.lower()
            has_standard = std_lower in text
            has_substance = sub_lower in text

            if has_standard and has_substance:
                tier_a.append(ext)
            elif has_standard:
                tier_b.append(ext)
            elif allowed_types is not None:
                # source_type match only (Tier C: included because caller
                # explicitly requested this source type)
                tier_c.append(ext)

    return tier_a + tier_b + tier_c
