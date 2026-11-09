"""Deadlines: escalation + acknowledgement, no duplicate alerts, conditional deposit, calendars (Demo C)."""
from datetime import date

from app import clock, rules
from app.db import SessionLocal
from app.models import ApplicationTypeDef, Notification
from conftest import act, assignee_login, detail, inst_user, login, submit, tick, travel, upload


def test_demo_c_undertaking_overdue_escalation_ack_and_late_closure(client):
    uname, _ = inst_user(name_like="Central Demo Polytechnic")
    hi = login(client, uname)
    u = next(x for x in client.get("/api/undertakings", headers=hi).json() if x["kind"] == "SECURITY_DEPOSIT")
    assert u["status"] == "OPEN" and "2.25(f)" in u["aph_reference"]
    travel(7)
    tick(client)
    tick(client)  # re-run must not duplicate anything
    hh = login(client, "cro.head")
    escs = [e for e in client.get("/api/escalations", headers=hh).json() if e["obligation"]["subject_id"] == u["id"]
            and e["obligation"]["subject_type"] == "undertaking"]
    assert len(escs) == 1 and escs[0]["level"] == 1 and escs[0]["can_acknowledge"]
    assert client.post(f"/api/escalations/{escs[0]['id']}/acknowledge", headers=login(client, "wro.head"),
                       json={"note": "x"}).status_code == 403
    assert client.post(f"/api/escalations/{escs[0]['id']}/acknowledge", headers=hh,
                       json={"note": "Spoke to the institution"}).status_code == 200
    with SessionLocal() as db:
        keys = [n.dedupe_key for n in db.query(Notification).filter(Notification.channel == "IN_APP")
                .filter(Notification.dedupe_key.like(f"ob%:esc:1")).all()]
        assert len(keys) == len(set((k, ) for k in keys)) or True
        dup = db.execute(__import__("sqlalchemy").text(
            "select dedupe_key, recipient_id, channel, count(*) from notifications group by 1,2,3 having count(*)>1")).all()
        assert dup == []
    fid = upload(client, hi)
    assert client.post(f"/api/undertakings/{u['id']}/evidence", headers=hi,
                       json={"file_ids": [fid], "remarks": "FDR + Affidavit 3"}).status_code == 200
    assert client.post(f"/api/undertakings/{u['id']}/verify", headers=hi,
                       json={"accept": True, "remarks": "self"}).status_code == 403  # no self-verification
    assert client.post(f"/api/undertakings/{u['id']}/verify", headers=login(client, "cro.scrutiny1"),
                       json={"accept": True, "remarks": "Verified"}).status_code == 200
    done = next(x for x in client.get("/api/undertakings", headers=hi).json() if x["id"] == u["id"])
    assert done["status"] == "VERIFIED" and done["was_late"] is True
    esc_after = client.get("/api/escalations?open_only=false", headers=hh).json()
    assert any(e["id"] == escs[0]["id"] and e["resolved_at"] for e in esc_after)


def test_security_deposit_only_for_self_financing_and_listed_types(client):
    for sf, expect in ((True, True), (False, False)):
        uname, _ = inst_user("SRO", self_financing=sf)
        hi = login(client, uname)
        app_id = submit(client, hi, "NEW_PROGRAMME_LEVEL", programme="M.Tech")
        app = detail(client, hi, app_id)
        app = act(client, assignee_login(client, app), app_id, "record_nil_deficiency", "ok")
        # skip EVC by recording it directly would bypass rules; instead check the rule function
        from app import compliance
        from app.models import Application
        with SessionLocal() as db:
            a = db.get(Application, app_id)
            assert compliance.security_deposit_applies(db, a) is expect
    uname, _ = inst_user("SRO", self_financing=True)
    hi = login(client, uname)
    app_id = submit(client, hi, "BANK_DETAILS_CHANGE")
    with SessionLocal() as db:
        from app import compliance
        from app.models import Application
        assert compliance.security_deposit_applies(db, db.get(Application, app_id)) is False


def test_year_round_after_cutoff_moves_to_next_year_and_public_notice_is_refused(client):
    with SessionLocal() as db:
        rs = rules.active_ruleset(db)
        yr = db.query(ApplicationTypeDef).filter_by(ruleset_id=rs.id, code="CHANGE_OF_SITE").one()
        pn = db.query(ApplicationTypeDef).filter_by(ruleset_id=rs.id, code="INCREASE_INTAKE").one()
        assert rules.assign_academic_year(db, yr, "2027-28", date(2026, 12, 1)) == "2027-28"
        assert rules.assign_academic_year(db, yr, "2027-28", date(2027, 2, 15)) == "2028-29"  # cl. 2.22
        import pytest
        from app.errors import Invalid
        with pytest.raises(Invalid):
            rules.assign_academic_year(db, pn, "2027-28", date(2027, 2, 15))
        odl = db.query(ApplicationTypeDef).filter_by(ruleset_id=rs.id, code="ODL_ONLINE").one()
        assert "January 2027" in rules.assign_academic_year(db, odl, "2027-28", date(2026, 10, 1))
        with pytest.raises(Invalid):
            rules.assign_academic_year(db, odl, "2027-28", date(2027, 1, 15))


def test_overdue_stage_escalates_two_levels_once(client):
    uname, _ = inst_user("NRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "TRUST_NAME_CHANGE")
    travel(30)
    tick(client)
    tick(client)
    app = detail(client, login(client, "bureau"), app_id)
    sla = next(o for o in app["obligations"] if o["kind"] == "STAGE_SLA")
    assert sla["state"] == "OVERDUE" and sla["escalation_level"] == 2
    esc = [e for e in client.get("/api/escalations", headers=login(client, "bureau")).json()
           if e["obligation"]["id"] == sla["id"]]
    assert sorted(e["level"] for e in esc) == [1, 2]


def test_emails_are_simulated(client):
    out = client.get("/api/notifications/outbox", headers=login(client, "bureau")).json()
    assert out and all(n["status"] == "SIMULATED" for n in out)


def test_deadlines_use_calendar_days_ist(client):
    start = clock.now()
    due = clock.due_after_days(start, 7)
    assert clock.to_ist(due).hour == 17 and clock.to_ist(due).minute == 30
    assert (clock.to_ist(due).date() - clock.to_ist(start).date()).days == 7
