"""RBAC, record scoping, idempotency, optimistic locking, uploads, audit integrity, rule versioning."""
from app.db import SessionLocal
from app.models import AuditEvent
from conftest import PDF, act, assignee_login, detail, inst_user, login, submit, upload


def test_pages_origin_can_authenticate_upload_and_replay_requests(client):
    response = client.options('/api/applications', headers={
        'Origin': 'https://arjunrohan.github.io',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type,idempotency-key',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://arjunrohan.github.io'
    health = client.get('/api/health', headers={'Origin': 'https://arjunrohan.github.io'})
    assert health.json() == {'ok': True}
    assert 'Idempotent-Replay' in health.headers['access-control-expose-headers']
    denied = client.options('/api/applications', headers={
        'Origin': 'https://unrelated.example', 'Access-Control-Request-Method': 'POST',
    })
    assert 'access-control-allow-origin' not in denied.headers


def test_institution_isolation_including_documents(client):
    u1, _ = inst_user("NRO")
    u2, _ = inst_user("SRO")
    h1, h2 = login(client, u1), login(client, u2)
    app_id = submit(client, h1, "BANK_DETAILS_CHANGE")
    fid = upload(client, h1)
    assert client.get(f"/api/applications/{app_id}", headers=h2).status_code == 404
    assert client.get(f"/api/files/{fid}", headers=h2).status_code == 403
    assert client.get(f"/api/applications/{app_id}", headers=login(client, "sro.scrutiny1")).status_code == 404
    assert client.get(f"/api/files/{fid}", headers=login(client, "sro.scrutiny1")).status_code == 403


def test_only_assigned_officer_can_act(client):
    uname, _ = inst_user("NRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "CLOSURE_OF_INSTITUTION")
    app = detail(client, hi, app_id)
    assignee = app["assignee"]
    other = "nro.scrutiny2" if assignee != detail(client, login(client, "nro.scrutiny2"), app_id)["assignee"] else "nro.scrutiny1"
    with SessionLocal() as db:
        from app.models import User
        names = {u.username: u.full_name for u in db.query(User).filter(User.role == "SCRUTINY_OFFICER").all()}
    not_assigned = next(u for u in ("nro.scrutiny1", "nro.scrutiny2") if names[u] != assignee)
    act(client, login(client, not_assigned), app_id, "record_nil_deficiency", "x", expect=403)
    act(client, login(client, "nro.evc"), app_id, "record_nil_deficiency", "x", expect=403)
    assert other


def test_rule_changes_need_rule_admin_and_publish_new_version(client):
    hb, hr = login(client, "bureau"), login(client, "ruleadmin")
    cfg = client.get("/api/config", headers=hr).json()
    stage = cfg["routes"][0]["stages"][0]
    assert client.put(f"/api/config/stages/{stage['id']}", headers=hb,
                      json={"sla_days": 12, "reason": "x"}).status_code == 403
    uname, _ = inst_user("NRO")
    hi = login(client, uname)
    before = detail(client, hi, submit(client, hi, "TRUST_NAME_CHANGE"))
    r = client.put(f"/api/config/stages/{stage['id']}", headers=hr, json={"sla_days": 12, "reason": "Circular 12/2026 (demo)"})
    assert r.status_code == 200 and r.json()["ruleset"].endswith("v2")
    after = client.get("/api/config", headers=hr).json()
    assert after["ruleset"]["version"] == 2
    assert any(v["status"] == "RETIRED" and v["applications_pinned"] > 0 for v in after["versions"])
    # existing application keeps its pinned v1 rules
    assert detail(client, hi, before["id"])["rule_trace"]["ruleset"] == "APH-2024-27 v1"
    new = detail(client, hi, submit(client, hi, "TRUST_NAME_CHANGE"))
    assert new["rule_trace"]["ruleset"] == "APH-2024-27 v2"


def test_idempotency_key_prevents_duplicate_submission(client):
    uname, _ = inst_user("SRO")
    h = login(client, uname)
    types = {t["code"]: t for t in client.get("/api/application-types", headers=h).json()["types"]}
    docs = {i["doc_code"]: upload(client, h) for i in types["BANK_DETAILS_CHANGE"]["checklist"] if i["mandatory"]}
    body = {"application_type": "BANK_DETAILS_CHANGE", "documents": docs}
    hk = {**h, "Idempotency-Key": "test-key-001"}
    r1 = client.post("/api/applications", headers=hk, json=body)
    r2 = client.post("/api/applications", headers=hk, json=body)
    assert r1.status_code == 200 and r2.json()["id"] == r1.json()["id"]
    assert r2.headers.get("Idempotent-Replay") == "true"


def test_optimistic_locking_rejects_stale_action(client):
    uname, _ = inst_user("WRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "TRUST_NAME_CHANGE")
    app = detail(client, hi, app_id)
    ho = assignee_login(client, app)
    v = app["version"]
    act(client, ho, app_id, "return_for_clarification", "Need resolution", expected_version=v)
    act(client, hi, app_id, "respond", "Done", expected_version=v, expect=409)


def test_upload_rules(client):
    h = login(client, "nro.scrutiny1")
    assert client.post("/api/files", headers=h, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    assert client.post("/api/files", headers=h, files={"file": ("x.pdf", eicar, "application/pdf")}).status_code == 422
    assert client.post("/api/files", headers=h, files={"file": ("ok.pdf", PDF, "application/pdf")}).status_code == 200


def test_audit_chain_detects_tampering_and_records_request_ids(client):
    h = login(client, "bureau")
    assert client.get("/api/audit/verify", headers=h).json()["valid"] is True
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.seq == 10).first()
        original = ev.reason
        ev.reason = "tampered"
        db.commit()
    res = client.get("/api/audit/verify", headers=h).json()
    assert res["valid"] is False and res["broken_at_seq"] == 10
    with SessionLocal() as db:
        db.query(AuditEvent).filter(AuditEvent.seq == 10).first().reason = original
        db.commit()
    assert client.get("/api/audit/verify", headers=h).json()["valid"] is True
    recent = client.get("/api/audit?action=LOGIN&limit=1", headers=h).json()[0]
    assert recent["request_id"]


def test_reports(client):
    h = login(client, "bureau")
    for kind in ("pendency", "evc", "undertakings", "documents", "overdue", "escalations", "regions"):
        r = client.get(f"/api/reports/{kind}.csv", headers=h)
        assert r.status_code == 200 and r.text.count("\n") >= 1, kind
