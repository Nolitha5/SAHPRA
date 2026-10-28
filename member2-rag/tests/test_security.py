"""Confidentiality: nothing sensitive reaches the logs."""

from __future__ import annotations

import json
import logging

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent
from app.logging_utils import JsonFormatter, redact, safe_fingerprint
from app.schemas import SponsorEvidence


def test_redact_replaces_forbidden_keys():
    out = redact({"query": "secret question", "count": 3})
    assert "query" not in out and out["query_fingerprint"] == safe_fingerprint("secret question")
    assert out["count"] == 3


def test_json_formatter_output_is_json():
    record = logging.LogRecord("member2.x", logging.INFO, __file__, 1, "evt", None, None)
    record.fields = {"text": "passage", "n": 1}
    data = json.loads(JsonFormatter().format(record))
    assert data["event"] == "evt" and "text" not in data and data["n"] == 1


def test_agents_do_not_log_question_or_sponsor_content(service, caplog):
    question = "Is impurity QX-77 at 0.07% acceptable for batch LOT-SECRET?"
    secret = "LOT-SECRET raw chromatogram values"
    sponsor = [SponsorEvidence(evidence_id="SP-9", content=secret)]
    with caplog.at_level(logging.DEBUG, logger="member2"):
        EvidenceReraAgent(service).assess(question, "3.2.S.4.4", sponsor_evidence=sponsor)
        S4ControlAgent(service).assess(question, "batch_analyses", sponsor_evidence=sponsor)
    logged = " ".join(f"{r.getMessage()} {getattr(r, 'fields', '')}" for r in caplog.records)
    assert caplog.records
    assert "QX-77" not in logged and "LOT-SECRET" not in logged
