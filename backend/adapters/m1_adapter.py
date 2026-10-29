"""
Replaceable adapter for Member 1 (Orchestrator).

M1 supplies:
  - A POST /analyse endpoint that accepts a dossier identifier and returns a
    list of raw findings (before QA review).
  - A Human Gate callback endpoint that receives the QA-stamped findings list
    and the assessor's decision after the reviewer acts.

CONTRACT STILL REQUIRED FROM M1:
  - Exact URL and authentication mechanism for /analyse
  - Request schema: what identifies a dossier (ID? path? metadata?)
  - Response schema: are findings in the Finding format defined in models.py,
    or does M1 use a different shape that needs mapping?
  - Human Gate callback URL and expected payload schema
  - Whether M1 expects a synchronous response or uses a webhook/queue

Until M1 supplies these contracts, MockM1Adapter is used.  Replace it by
implementing the M1Adapter Protocol with a real HTTP client.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from models import Finding
from qa_critic import review_findings


class M1Adapter(Protocol):
    def get_findings(self, dossier_id: str) -> list[Finding]:
        """
        Retrieve raw findings for a dossier from M1's /analyse endpoint.
        Returns an empty list if no findings are available.
        """
        ...

    def post_human_gate_result(
        self,
        dossier_id: str,
        findings: list[Finding],
    ) -> bool:
        """
        Post QA-stamped findings and assessor decisions back to M1's Human Gate.
        Returns True if M1 acknowledged receipt, False otherwise.
        """
        ...


class MockM1Adapter:
    """
    Stub implementation.  Loads findings from the local mock fixture and
    runs them through the QA/Critic.  Replace with a real HTTP adapter once
    M1 supplies the endpoint contract.
    """

    _FIXTURE = Path(__file__).parent.parent / "mock_findings.json"

    def get_findings(self, dossier_id: str) -> list[Finding]:  # noqa: ARG002
        data = json.loads(self._FIXTURE.read_text(encoding="utf-8"))
        findings = [Finding(**item) for item in data["findings"]]
        return review_findings(findings)

    def post_human_gate_result(
        self,
        dossier_id: str,
        findings: list[Finding],
    ) -> bool:
        # Stub: log and return True.  Replace with real HTTP POST to M1.
        print(
            f"[M1 stub] post_human_gate_result dossier={dossier_id!r} "
            f"findings={len(findings)}"
        )
        return True
