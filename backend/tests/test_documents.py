"""Demo B: lease threshold, certificate expiry, structural stability, versions, no duplicate alerts."""
from datetime import date

from app import clock
from app.db import SessionLocal
from app.models import Notification, TrackedDocument
from conftest import inst_user, login, tick, upload


def test_demo_b_lease_and_certificates(client):
    uname, inst_id = inst_user(name_like="Western Demo College")
    hi = login(client, uname)
    docs = {d["doc_type"]: d for d in client.get("/api/documents", headers=hi).json()}
    lease, fire, ssc = docs["LAND_LEASE"], docs["FIRE_NOC"], docs["STABILITY_CERT"]
    assert lease["status"] == "EXPIRING_SOON" and "2.1(e)" in lease["source"]
    assert lease["renew_by"] < lease["valid_until"]  # threshold = expiry minus longest course duration
    assert fire["status"] == "EXPIRING_SOON" and fire["renew_by"] == fire["valid_until"]
    assert ssc["checks"][0]["ok"]
    tick(client)
    tick(client)
    with SessionLocal() as db:
        dup = db.execute(__import__("sqlalchemy").text(
            "select dedupe_key, recipient_id, channel, count(*) from notifications group by 1,2,3 having count(*)>1")).all()
        assert dup == []
    # renewal: dates validated, then a new version that keeps the original
    fid = upload(client, hi, "lease.pdf")
    bad = client.post(f"/api/documents/{lease['id']}/renew", headers=hi,
                      json={"valid_from": "2040-01-01", "valid_until": "2030-01-01", "file_id": fid})
    assert bad.status_code == 422
    today = clock.today()
    r = client.post(f"/api/documents/{lease['id']}/renew", headers=hi,
                    json={"valid_from": today.isoformat(), "valid_until": date(today.year + 30, 12, 31).isoformat(),
                          "file_id": fid, "reference_no": "REG/PUNE/2026/991"})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    ho = login(client, "wro.scrutiny1")
    pending = next(d for d in client.get("/api/documents", headers=ho).json() if d["id"] == new_id)
    assert pending["status"] == "AWAITING_VERIFICATION" and all(c["ok"] for c in pending["checks"])
    assert client.post(f"/api/documents/{new_id}/verify", headers=hi,
                       json={"accept": True, "remarks": "self"}).status_code == 403
    assert client.post(f"/api/documents/{new_id}/verify", headers=ho,
                       json={"accept": True, "remarks": "Registered deed verified"}).status_code == 200
    versions = client.get(f"/api/documents/{new_id}/versions", headers=hi).json()
    assert [v["version"] for v in versions] == [1, 2] and versions[0]["status"] == "SUPERSEDED"


def test_missing_stability_certificate_is_flagged_and_uploadable(client):
    hb = login(client, "bureau")
    missing = [d for d in client.get("/api/documents", headers=hb).json()
               if d["status"] == "MISSING" and d["doc_type"] == "STABILITY_CERT"]
    assert missing, "old buildings without a certificate must show as MISSING"
    m = missing[0]
    with SessionLocal() as db:
        from app.models import User
        uname = db.query(User).filter(User.institution_id == m["institution_id"]).first().username
    hi = login(client, uname)
    fid = upload(client, hi)
    today = clock.today()
    r = client.post("/api/documents", headers=hi, json={"doc_type": "STABILITY_CERT", "valid_from": today.isoformat(),
                                                         "valid_until": date(today.year + 5, today.month, 1).isoformat(),
                                                         "file_id": fid})
    assert r.status_code == 200, r.text
    assert not any(d["status"] == "MISSING" and d["doc_type"] == "STABILITY_CERT"
                   for d in client.get("/api/documents", headers=hi).json())
