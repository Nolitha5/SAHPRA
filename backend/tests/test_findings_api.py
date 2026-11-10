from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_get_findings_returns_raw_fixture_records():
    response = client.get("/findings")

    assert response.status_code == 200
    findings = response.json()
    assert [finding["finding_id"] for finding in findings] == [
        "F-001",
        "F-002",
        "F-003",
        "F-004",
        "F-005",
    ]
    assert all(finding["qa_status"] is None for finding in findings)


def test_get_finding_returns_matching_raw_fixture_record():
    response = client.get("/findings/F-001")

    assert response.status_code == 200
    assert response.json()["finding_id"] == "F-001"
    assert response.json()["qa_status"] is None


def test_get_reviewed_findings_still_returns_reviewed_records():
    response = client.get("/findings/reviewed")

    assert response.status_code == 200
    findings = response.json()
    assert len(findings) == 5
    assert all(finding["qa_status"] is not None for finding in findings)
