"""Scrutiny → re-scrutiny scope, EVC, SHC, decision and appeal (Demo A)."""
from datetime import timedelta

from app import clock
from conftest import act, assignee_login, detail, inst_user, login, submit, travel, upload


def test_demo_a_full_flow_with_scoped_rescrutiny(client):
    uname, _ = inst_user(name_like="Northern Demo Institute")
    hi = login(client, uname)
    app_id = submit(client, hi, "INCREASE_INTAKE", programme="MCA", intake_requested=60)
    app = detail(client, hi, app_id)
    assert app["stage"] == "SCRUTINY" and app["allowed_actions"] == []

    ho = assignee_login(client, app)
    # deficiency must be itemised
    act(client, ho, app_id, "record_deficiency", "Deficient", expect=422)
    app = act(client, ho, app_id, "record_deficiency", "Two deficiencies", deficiencies=[
        {"finding": "Affidavit 2 not in format", "reference": "Affidavit 2", "correction": "Re-upload"},
        {"finding": "Occupancy certificate missing", "reference": "Occupancy cert", "correction": "Upload it"}])
    assert app["status"] == "RETURNED" and app["pending_next_stage"] == "RE_SCRUTINY"
    defs = app["deficiencies"]
    assert [d["status"] for d in defs] == ["OPEN", "OPEN"]

    # institution must answer every item
    act(client, hi, app_id, "respond", "Partial", expect=422,
        item_responses={str(defs[0]["id"]): {"response": "Done", "file_ids": []}})
    fid = upload(client, hi)
    app = act(client, hi, app_id, "respond", "All corrected", item_responses={
        str(defs[0]["id"]): {"response": "Re-uploaded affidavit", "file_ids": [fid]},
        str(defs[1]["id"]): {"response": "Uploaded occupancy certificate", "file_ids": [fid]}})
    assert app["stage"] == "RE_SCRUTINY"

    hr = assignee_login(client, app)
    assert "verify_deficiencies" in detail(client, hr, app_id)["allowed_actions"]
    # cannot verify an item outside the recorded scope
    act(client, hr, app_id, "verify_deficiencies", "x", expect=422,
        verdicts={"999999": {"resolved": True}, str(defs[0]["id"]): {"resolved": True}, str(defs[1]["id"]): {"resolved": True}})
    # scrutiny officer cannot act on re-scrutiny
    act(client, ho, app_id, "verify_deficiencies", "x", expect=403, verdicts={})
    app = act(client, hr, app_id, "verify_deficiencies", "Both resolved", verdicts={
        str(defs[0]["id"]): {"resolved": True, "remarks": "OK"}, str(defs[1]["id"]): {"resolved": True, "remarks": "OK"}})
    assert app["stage"] == "EVC"  # no EVC before scrutiny is clear; now queued
    assert all(d["status"] == "RESOLVED" for d in app["deficiencies"])

    hc = login(client, "nro.evc")
    visit = next(v for v in client.get("/api/evc", headers=hc).json() if v["application_id"] == app_id)
    on = (clock.to_ist(clock.now()) + timedelta(days=3)).date()
    panel = client.get(f"/api/evc/{visit['id']}/panel", params={"on": on.isoformat()}, headers=hc).json()["panel"]
    r = client.post(f"/api/evc/{visit['id']}/schedule", headers=hc,
                    json={"date": on.isoformat(), "panel": panel, "mode": "ONLINE"})
    assert r.status_code == 200, r.text
    travel(4)
    # coordinator cannot file the report; an unassigned expert cannot either
    assert client.post(f"/api/evc/{visit['id']}/report", headers=hc,
                       json={"outcome": "CLEAR", "remarks": "x"}).status_code == 403
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        member = db.query(User).filter(User.expert_id == panel[0]["id"]).first().username
        outsider = db.query(User).filter(User.role == "EVC_MEMBER",
                                         User.expert_id.notin_([p["id"] for p in panel])).first().username
    assert client.post(f"/api/evc/{visit['id']}/report", headers=login(client, outsider),
                       json={"outcome": "CLEAR", "remarks": "x"}).status_code == 403
    hm = login(client, member)
    # online EVC needs a ≥30-minute video (cl. 1.9)
    assert client.post(f"/api/evc/{visit['id']}/report", headers=hm,
                       json={"outcome": "CLEAR", "remarks": "Verified", "video_url": "https://v.example/x",
                             "video_minutes": 12}).status_code == 422
    r = client.post(f"/api/evc/{visit['id']}/report", headers=hm,
                    json={"outcome": "CLEAR", "remarks": "Verified", "video_url": "https://v.example/x", "video_minutes": 35})
    assert r.status_code == 200, r.text

    ha = login(client, "authority")
    app = detail(client, ha, app_id)
    assert app["status"] == "READY_FOR_DECISION" and app["recommendation"] == "RECOMMENDED"
    # bureau monitors but cannot decide; scrutiny officer cannot decide
    act(client, login(client, "bureau"), app_id, "approve", "ok", expect=403, decision_ref="X")
    act(client, ho, app_id, "approve", "ok", expect=403, decision_ref="X")
    act(client, ha, app_id, "approve", "ok", expect=422)  # order reference required
    app = act(client, ha, app_id, "approve", "Approved as recommended", decision_ref="F.No. NRO/DEMO-A/2027-28")
    assert app["status"] == "APPROVED" and app["decision_ref"]
    actions = [e["action"] for e in app["audit"]]
    for a in ("ROUTED", "DEFICIENCIES_RECORDED", "INSTITUTION_RESPONDED", "DEFICIENCIES_VERIFIED", "AUTO_ADVANCED",
              "EVC_SCHEDULED", "EVC_REPORT_SUBMITTED", "READY_FOR_DECISION", "DECISION_RECORDED"):
        assert a in actions, a


def test_return_for_clarification_pauses_clock(client):
    uname, _ = inst_user("SRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "NAME_OR_TYPE_CHANGE")
    app = detail(client, hi, app_id)
    ho = assignee_login(client, app)
    due_before = next(o for o in app["obligations"] if o["kind"] == "STAGE_SLA")["due_at"]
    app = act(client, ho, app_id, "return_for_clarification", "Upload encumbrance certificate")
    assert next(o for o in app["obligations"] if o["kind"] == "STAGE_SLA")["state"] == "PAUSED"
    travel(5)
    app = act(client, hi, app_id, "respond", "Uploaded")
    from datetime import datetime
    shift = datetime.fromisoformat(next(o for o in app["obligations"] if o["kind"] == "STAGE_SLA")["due_at"]) - \
        datetime.fromisoformat(due_before)
    assert app["status"] == "IN_PROGRESS" and shift >= timedelta(days=5)


def test_unresolved_rescrutiny_goes_to_authority_not_recommended(client):
    uname, _ = inst_user("WRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "CLOSURE_OF_COURSE")
    app = detail(client, hi, app_id)
    act(client, assignee_login(client, app), app_id, "record_deficiency", "One item",
        deficiencies=[{"finding": "Closure resolution missing"}])
    d = detail(client, hi, app_id)["deficiencies"][0]
    app = act(client, hi, app_id, "respond", "Uploaded", item_responses={str(d["id"]): {"response": "Attached"}})
    app = act(client, assignee_login(client, app), app_id, "verify_deficiencies", "Still missing",
              verdicts={str(d["id"]): {"resolved": False, "remarks": "Unsigned"}})
    assert app["status"] == "READY_FOR_DECISION" and app["recommendation"] == "NOT_RECOMMENDED"


def test_appeal_window_and_single_appeal(client):
    uname, _ = inst_user("WRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "BANK_DETAILS_CHANGE")
    app = detail(client, hi, app_id)
    act(client, assignee_login(client, app), app_id, "record_nil_deficiency", "ok")
    ha = login(client, "authority")
    app = act(client, ha, app_id, "reject", "Bank letter not authenticated", decision_ref="F.No. WRO/BANK/1")
    window = next(o for o in app["obligations"] if o["kind"] == "APPEAL_WINDOW")
    assert "2.24(a)" in window["source_reference"]
    r = act(client, hi, app_id, "appeal", "Authenticated letter now attached")
    appeal = detail(client, hi, r["appeal_application_id"])
    assert appeal["route_code"] == "APPEAL_SAC" and appeal["stage"] == "SAC"
    act(client, hi, app_id, "appeal", "again", expect=403)


def test_new_institution_rejection_uses_chapter_i_trigger(client):
    from app.db import SessionLocal
    from app.models import Application
    with SessionLocal() as db:
        app = db.query(Application).filter(Application.application_type == "NEW_INSTITUTION",
                                           Application.status == "READY_FOR_DECISION").first()
        app_id = app.id if app else None
    if app_id is None:
        return
    app = act(client, login(client, "authority"), app_id, "reject", "Not recommended", decision_ref="LoD/1")
    w = next(o for o in app["obligations"] if o["kind"] == "APPEAL_WINDOW")
    assert "1.11(a)" in w["source_reference"]


def test_revert_by_regional_officer(client):
    uname, _ = inst_user("WRO")
    hi = login(client, uname)
    app_id = submit(client, hi, "CHANGE_OF_SITE")
    app = detail(client, hi, app_id)
    act(client, assignee_login(client, app), app_id, "record_nil_deficiency", "ok")
    app = act(client, login(client, "wro.head"), app_id, "revert", "Re-examine land conversion", target_stage="SCRUTINY")
    assert app["stage"] == "SCRUTINY" and any(e["action"] == "REVERTED" for e in app["audit"])
    assert not any(o["kind"] == "EVC_SCHEDULE" and o["state"] != "CLOSED" for o in app["obligations"])
