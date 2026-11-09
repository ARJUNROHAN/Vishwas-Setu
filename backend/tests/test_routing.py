"""Routing: all 21 Table 2.3 categories, the Chapter I path, Regulation routes and manual review."""
import pytest

from conftest import detail, inst_user, login, submit

# Table 2.3 (printed p. 30): row → (category, scrutiny?, EVC?, SHC as applicable?)
TABLE_2_3 = {
    1: ("EOA_SELF_DISCLOSURE", False, False), 2: ("NRI_SEATS", False, False),
    3: ("DIPLOMA_DEGREE_CONVERSION", True, True), 4: ("NAME_OR_TYPE_CHANGE", True, False),
    5: ("NEW_PROGRAMME_LEVEL", True, True), 6: ("MERGER_OF_INSTITUTIONS", True, True),
    7: ("EOA_AFTER_BREAK", True, True), 8: ("SUPERNUMERARY_FN_OCI_GULF", True, False),
    9: ("INCREASE_INTAKE", True, True), 10: ("INTEGRATED_DUAL_DEGREE", True, True), 11: ("FPM", True, True),
    12: ("COURSE_NAME_MERGER_REDUCTION", True, False), 13: ("COLLABORATION_TWINNING", True, True),
    14: ("CHANGE_OF_SITE", True, True), 15: ("CLOSURE_OF_INSTITUTION", True, False),
    16: ("WOMEN_COED_CONVERSION", True, False), 17: ("CLOSURE_OF_COURSE", True, False),
    18: ("BANK_DETAILS_CHANGE", True, False), 19: ("TRUST_NAME_CHANGE", True, False),
    20: ("CONVERSION_TO_DEEMED_UNIVERSITY", True, True), 21: ("ODL_ONLINE", True, True),
}


def test_configured_matrix_matches_table_2_3(client):
    types = {t["code"]: t for t in client.get("/api/application-types", headers=login(client, "bureau")).json()["types"]}
    rows = {t["table_row"]: t for t in types.values() if t["table_row"]}
    assert sorted(rows) == list(range(1, 22)), "all 21 Table 2.3 rows must be configured"
    for row, (code, scrutiny, evc) in TABLE_2_3.items():
        t = rows[row]
        assert t["code"] == code
        stages = {s["code"]: s for s in t["route"]["stages"]}
        assert ("SCRUTINY" in stages) == scrutiny, code
        assert ("EVC" in stages) == evc, code
        if scrutiny:
            assert stages["RE_SCRUTINY"]["conditional"], f"{code}: re-scrutiny only if deficiencies"
        if "SHC" in stages:
            assert stages["SHC"]["conditional"], f"{code}: SHC is 'as applicable', never unconditional"
        assert "SAC" not in stages, f"{code}: SAC is a separate appeal workflow"
        if not scrutiny:
            assert list(stages) == ["SELF_DISCLOSURE"], f"{code}: self-disclosure must not enter routine scrutiny/EVC"
    assert types["NEW_INSTITUTION"]["chapter"] == "I"
    assert [s["code"] for s in types["NEW_INSTITUTION"]["route"]["stages"]] == ["SCRUTINY", "RE_SCRUTINY", "EVC"]
    assert types["OFF_CAMPUS"]["route"]["code"] == "MANUAL_RULE_REVIEW"
    assert types["ODL_ONLINE"]["notice_category"] == "ODL_CYCLE"


@pytest.mark.parametrize("row", list(TABLE_2_3))
def test_each_category_routes_to_its_first_queue(client, row):
    code, scrutiny, _ = TABLE_2_3[row]
    uname, _ = inst_user("SRO")
    h = login(client, uname)
    app = detail(client, h, submit(client, h, code))
    assert app["stage"] == ("SCRUTINY" if scrutiny else "SELF_DISCLOSURE")
    assert app["rule_trace"]["table_row"] == row
    assert app["rule_trace"]["ruleset"].startswith("APH-2024-27")
    assert any(e["action"] == "ROUTED" for e in app["audit"])


def test_new_institution_follows_chapter_i(client):
    uname, _ = inst_user("NRO", new=True)
    h = login(client, uname)
    app = detail(client, h, submit(client, h, "NEW_INSTITUTION"))
    assert app["route_code"] == "CH1_NEW_INSTITUTION" and app["rule_trace"]["chapter"] == "I"


def test_council_initiated_types_cannot_be_filed_by_institution(client):
    uname, _ = inst_user("NRO")
    r = client.post("/api/applications", headers=login(client, uname),
                    json={"application_type": "SHOW_CAUSE", "documents": {}})
    assert r.status_code == 403


def test_unmapped_category_goes_to_manual_rule_review(client):
    uname, _ = inst_user("WRO")
    h = login(client, uname)
    app_id = submit(client, h, "OFF_CAMPUS")
    hr = login(client, "ruleadmin")
    app = detail(client, hr, app_id)
    assert app["stage"] == "RULE_REVIEW" and "assign_route" in app["allowed_actions"]
    r = client.post(f"/api/applications/{app_id}/actions", headers=hr,
                    json={"action": "assign_route", "route_code": "SCRUTINY_EVC_CONDITIONAL", "remarks": ""})
    assert r.status_code == 422  # clause must be cited
    r = client.post(f"/api/applications/{app_id}/actions", headers=hr,
                    json={"action": "assign_route", "route_code": "SCRUTINY_EVC_CONDITIONAL",
                          "remarks": "Off-campus provisions reviewed; processed as Scrutiny + EVC"})
    assert r.status_code == 200 and r.json()["stage"] == "SCRUTINY"


def test_mandatory_checklist_enforced_at_submission(client):
    uname, _ = inst_user("NRO")
    r = client.post("/api/applications", headers=login(client, uname),
                    json={"application_type": "EOA_SELF_DISCLOSURE", "documents": {}})
    assert r.status_code == 422 and "Affidavit 2" in r.json()["detail"]


def test_stability_certificate_required_only_for_old_buildings(client):
    h = login(client, "bureau")
    with __import__("app.db", fromlist=["SessionLocal"]).SessionLocal() as db:
        from app.models import Institution, User
        old = next(i for i in db.query(Institution).all()
                   if i.building_completion_date and i.building_completion_date.year < 1995)
        new = next(i for i in db.query(Institution).all()
                   if i.building_completion_date and i.building_completion_date.year > 2000)
        u_old = db.query(User).filter(User.institution_id == old.id).first().username
        u_new = db.query(User).filter(User.institution_id == new.id).first().username

    def codes(u):
        types = client.get("/api/application-types", headers=login(client, u)).json()["types"]
        return {i["doc_code"] for i in next(t for t in types if t["code"] == "EOA_SELF_DISCLOSURE")["checklist"]}
    assert "STABILITY_CERT" in codes(u_old)
    assert "STABILITY_CERT" not in codes(u_new)
    assert h
