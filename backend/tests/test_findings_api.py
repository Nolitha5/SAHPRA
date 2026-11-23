from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_get_findings_returns_raw_fixture_records():
    response = client.get("/findings")

    assert response.status_code == 200
    findings = response.json()
    assert [finding["finding_id"] for finding in findings] == ["F-003"]
    assert all(finding["qa_status"] is None for finding in findings)


def test_get_finding_returns_matching_raw_fixture_record():
    response = client.get("/findings/F-003")

    assert response.status_code == 200
    assert response.json()["finding_id"] == "F-003"
    assert response.json()["qa_status"] is None


def test_get_reviewed_findings_still_returns_reviewed_records():
    response = client.get("/findings/reviewed")

    assert response.status_code == 200
    findings = response.json()
    assert [finding["ctd_section"] for finding in findings] == ["3.2.S.5"]
    assert all(finding["qa_status"] is not None for finding in findings)


def test_reviewed_finding_restores_latest_local_decision(monkeypatch, tmp_path):
    import main
    from adapters.m4_adapter import LocalFileAuditAdapter

    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(main, "_m4", LocalFileAuditAdapter(audit_path))
    for decision in ("Approve", "Query"):
        response = client.post("/decisions/F-003", json={
            "finding_id": "F-003",
            "decision": decision,
            "disposition_note": "Verify reference-standard evidence.",
        })
        assert response.status_code == 200
        assert response.json()["audit_saved"] is True

    with audit_path.open("a", encoding="utf-8") as file:
        file.write("{incomplete audit line")

    findings = client.get("/findings/reviewed").json()
    assert findings[0]["assessor_decision"] == "Query"
    assert findings[0]["disposition_note"] == "Verify reference-standard evidence."
    assert findings[0]["decision_timestamp"] is not None
