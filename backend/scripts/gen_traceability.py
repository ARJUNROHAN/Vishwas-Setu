"""Regenerate docs/APH_TRACEABILITY.md from the rule configuration.

Usage (from backend/):  python scripts/gen_traceability.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config_data import APPLICATION_TYPES as T, CHECKLISTS as C, ROUTES as R, SETTINGS as S  # noqa: E402

REQS = [
    ("Category decides the processing route (21 Table 2.3 rows)", "APH Table 2.3 (printed p. 30)", "config_data.APPLICATION_TYPES, rules.route", "test_routing::test_configured_matrix_matches_table_2_3, test_each_category_routes_to_its_first_queue"),
    ("New institutions follow Chapter I: Scrutiny → Re-Scrutiny → EVC → decision (LoA/LoD)", "APH Ch. I cl. 1.8–1.10", "ROUTES CH1_NEW_INSTITUTION", "test_routing::test_new_institution_follows_chapter_i"),
    ("Re-Scrutiny verifies only the deficiencies recorded by Scrutiny", "APH cl. 1.8", "workflow.verify_deficiencies, models.Deficiency", "test_workflow::test_demo_a_full_flow_with_scoped_rescrutiny"),
    ("Unresolved deficiencies after Re-Scrutiny go to the competent authority, not back into a loop", "APH cl. 1.8", "stage on_deficiency TO_DECISION", "test_workflow::test_unresolved_rescrutiny_goes_to_authority_not_recommended"),
    ("Online EVC requires a video of at least 30 minutes", "APH cl. 1.9", "evc.submit_report, setting online_evc_min_video_minutes", "test_workflow::test_demo_a_full_flow_with_scoped_rescrutiny"),
    ("EVC report is submitted by an assigned EVC member, not the coordinator", "APH cl. 1.9", "evc.submit_report", "test_workflow::test_demo_a_full_flow_with_scoped_rescrutiny"),
    ("SHC is 'as applicable' (EVC shortcomings only), never automatic", "APH cl. 2.23", "ROUTES SCRUTINY_EVC_CONDITIONAL (SHC conditional)", "test_workflow::test_demo_a_full_flow_with_scoped_rescrutiny"),
    ("Only the competent authority decides; a decision reference is recorded", "Regs cl. 6; APH cl. 2.23", "workflow.decide", "test_workflow::test_demo_a_full_flow_with_scoped_rescrutiny"),
    ("One appeal within 7 days of the decision (existing institutions)", "APH cl. 2.24(a)", "workflow.file_appeal, APPEAL_WINDOW obligation", "test_workflow::test_appeal_window_and_single_appeal"),
    ("One appeal within 7 days of the LoD (new institutions)", "APH cl. 1.11(a)", "workflow.file_appeal", "test_workflow::test_new_institution_rejection_uses_chapter_i_trigger"),
    ("Academic year assigned by submission date; public-notice categories refused outside the window", "APH Table 2.2, cl. 2.22", "rules.assign_academic_year", "test_deadlines::test_year_round_after_cutoff_moves_to_next_year_and_public_notice_is_refused"),
    ("ODL / Online programmes received in two cycles a year", "APH Table 2.3 row 21; Table 2.2", "CALENDARS odl_cycles", "test_routing::test_each_category_routes_to_its_first_queue"),
    ("Mandatory Annexure 1 / 2 documents enforced at submission", "APH Annexures 1–2", "rules.checklist_for, workflow.submit_application", "test_routing::test_mandatory_checklist_enforced_at_submission"),
    ("Structural stability certificate only for buildings older than 30 years", "APH Annexure 2", "rules.condition_applies (building_over_30)", "test_routing::test_stability_certificate_required_only_for_old_buildings"),
    ("Missing required compliance documents are flagged and can be uploaded", "APH Annexure 2", "compliance.required_doc_types; /documents MISSING rows", "test_documents::test_missing_stability_certificate_is_flagged_and_uploadable"),
    ("Lease: alert when live lease ≤ longest course duration; renewal ≥ 30-year term with ≥ 25 years live", "APH cl. 2.1(e); Ch. VI", "compliance.lease_critical_date, lease_checks", "test_documents::test_demo_b_lease_and_certificates"),
    ("Security deposit with Affidavit 3 within 15 days; self-financing and listed types only", "APH cl. 2.25(f); Regs 6.2(f), 6.3(l)", "compliance.security_deposit_applies", "test_deadlines::test_security_deposit_only_for_self_financing_and_listed_types"),
    ("No conditional approvals: tracked items are time-bound requirements, not conditions", "Regs 6.10", "compliance.UNDERTAKING_TEMPLATES", "test_deadlines::test_demo_c_undertaking_overdue_escalation_ack_and_late_closure"),
    ("Late compliance is closed but marked late", "DESIGN (blueprint)", "compliance.submit_evidence (was_late), Obligation.was_overdue", "test_deadlines::test_demo_c_undertaking_overdue_escalation_ack_and_late_closure"),
    ("Deadlines in calendar days, falling due at 17:30 IST", "DESIGN (blueprint)", "clock.due_after_days", "test_deadlines::test_deadlines_use_calendar_days_ist"),
    ("Reminders T−n, T+0, T+1; two-level escalation; acknowledgement", "DESIGN (blueprint)", "obligations.evaluate, obligations.acknowledge", "test_deadlines::test_overdue_stage_escalates_two_levels_once"),
    ("Email delivery simulated and recorded", "DESIGN", "obligations.notify (status SIMULATED)", "test_deadlines::test_emails_are_simulated"),
    ("Rules versioned; submitted applications stay pinned to their version", "DESIGN (blueprint)", "rules.publish_new_version, Application.ruleset_id", "test_security::test_rule_changes_need_rule_admin_and_publish_new_version"),
    ("Categories not mapped in Table 2.3 go to manual rule review", "DESIGN (blueprint §3.1)", "ROUTES MANUAL_RULE_REVIEW, workflow.assign_route", "test_routing::test_unmapped_category_goes_to_manual_rule_review"),
    ("Council-initiated inspections cannot be filed by institutions", "Regs 6.2(j), 6.3(b), 11.2", "APPLICATION_TYPES initiated_by=COUNCIL", "test_routing::test_council_initiated_types_cannot_be_filed_by_institution"),
    ("Only the assigned officer can act; stale actions rejected", "DESIGN", "workflow.can_act, Application.version", "test_security::test_only_assigned_officer_can_act, test_optimistic_locking_rejects_stale_action"),
    ("Tamper-evident audit trail with request IDs", "DESIGN", "audit.record, /audit/verify", "test_security::test_audit_chain_detects_tampering_and_records_request_ids"),
]


def main() -> None:
    rn = {r["code"]: r["name"] for r in R}
    L = ["# APH traceability matrix", "",
         "Every rule the prototype enforces, with the clause it comes from. Source types: **APH** = Approval Process "
         "Handbook 2024-25 to 2026-27; **REGULATION** = AICTE (Grant of Approval for Technical Institutions) "
         "Regulations 2024; **DESIGN** = a prototype default the APH does not fix.", "",
         "> Generated by `backend/scripts/gen_traceability.py` from `app/config_data.py`. Page numbers are printed page "
         "numbers taken from the team blueprint; they could not be re-checked against the official PDF from the build "
         "environment, so verify each before presenting. Rows marked *verify* are placements we are not certain of.", "",
         "## 1. Requirement → clause → implementation → test", "",
         "| # | Requirement | Source | Implemented in | Test |", "|---|---|---|---|---|"]
    L += [f"| {i} | {a} | {b} | `{c}` | `{d}` |" for i, (a, b, c, d) in enumerate(REQS, 1)]
    L += ["", "## 2. Category matrix (Chapter I, Table 2.3, Regulations)", "",
          "| Ch. | Row | Code | Route | Submission window | Checklist | Filed by |", "|---|---|---|---|---|---|---|"]
    for t in T:
        nv = "" if t.get("notice_verified") else " *(verify)*"
        L.append(f"| {t.get('chapter')} | {t.get('row') or '—'} | `{t['code']}` | {rn[t['route']]} | "
                 f"{t.get('notice')}{nv} | {t.get('checklist') or '—'} | {(t.get('initiated_by') or 'INSTITUTION').title()} |")
    L += ["", "## 3. Routes", ""]
    for r in R:
        L.append(f"**{r['name']}** (`{r['code']}`). {r['source_type']}: {r['source']}  ")
        L.append("Stages: " + " → ".join(
            f"{s['name']} ({s['sla']} d{', conditional' if s.get('conditional') else ''})" for s in r["stages"]))
        L.append("")
    L += ["Stage time limits are DESIGN defaults: the APH fixes the sequence of committees, not their durations.", "",
          "## 4. Settings", "", "| Key | Value | Source type | Source |", "|---|---|---|---|"]
    L += [f"| `{k}` | {v} {u} | {st} | {src} |" for k, v, u, st, src in S if k != "clock_offset_days"]
    L += ["", "## 5. Checklists", ""]
    for code, c in C.items():
        L.append(f"**{code}**. {c['source']}  ")
        L.append(", ".join(lbl + (f" *({cond.replace('_', ' ')})*" if cond != "always" else "") for _, lbl, cond in c["items"]))
        L.append("")
    L += ["## 6. Known gaps and items to verify", "",
          "- Table 2.2 submission-window placements marked *verify* above.",
          "- The 5-year validity of the structural stability certificate (Ch. VI) comes from the blueprint; confirm against the PDF.",
          "- Academic-calendar dates are illustrative; replace them with the notified schedule.",
          "- Printed page numbers have not been re-checked against the official PDF.",
          "- Off-campus centres are routed to manual rule review rather than guessed.", ""]
    out = ROOT.parent / "docs" / "APH_TRACEABILITY.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
