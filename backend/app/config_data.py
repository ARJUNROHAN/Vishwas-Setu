"""Rules configuration — APH 2024-25 to 2026-27 (Approval Process Handbook) and the
AICTE (Grant of Approvals for Technical Institutions) Regulations 2024-27.

Every rule carries ``source_type``:
  APH        – taken from the handbook (clause/table cited in ``source``)
  REGULATION – taken from the Grant of Approval Regulations 2024-27
  DESIGN     – prototype default; NOT an AICTE requirement (time limits, reminder offsets,
               escalation steps). Editable by the rule administrator.
Anything marked ``verify`` should be checked against the official PDF before real use.
"""

APH_SOURCE_URL = ("https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/"
                  "uploads/2025/03/2025031399.pdf")

RULESET = {
    "code": "APH-2024-27", "version": 1, "aph_edition": "APH 2024-25 to 2026-27",
    "source_url": APH_SOURCE_URL, "effective_from": "2024-01-01",
    "notes": "Initial ruleset: Table 2.3 routing matrix, Chapter I new-institution process, "
             "conditional SHC/SAC, appeal triggers, document checklists (Annexures 1-2).",
}

# --------------------------------------------------------------------------- routes
# on_deficiency: RETURN | RETURN_THEN:<STAGE> | GOTO:<STAGE> | TO_DECISION
# managed_by: officer | evc | deficiency_review (re-scrutiny of recorded items only) | rule_review
ROUTES = [
    {"code": "CH1_NEW_INSTITUTION", "name": "Chapter I: Scrutiny → Re-Scrutiny → EVC",
     "description": "New institution: scrutiny of documents; deficiencies go to the institution and are "
                    "re-verified by the Re-Scrutiny Committee (only the recorded deficiencies); on nil "
                    "deficiency an EVC verifies readiness; the competent authority decides (LoA/LoD).",
     "source_type": "APH", "source": "APH Ch. I cl. 1.8–1.10 (printed pp. 7–8); Annexure 7 (p. 100)",
     "stages": [
         {"code": "SCRUTINY", "name": "Scrutiny Committee", "sla": 14, "role": "SCRUTINY_OFFICER",
          "on_deficiency": "RETURN_THEN:RE_SCRUTINY"},
         {"code": "RE_SCRUTINY", "name": "Re-Scrutiny Committee", "sla": 10, "role": "RESCRUTINY_OFFICER",
          "conditional": True, "managed_by": "deficiency_review", "on_deficiency": "TO_DECISION"},
         {"code": "EVC", "name": "Expert Visit Committee", "sla": 14, "role": "EVC_COORDINATOR",
          "managed_by": "evc", "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "SELF_DISCLOSURE", "name": "Self-disclosure",
     "description": "Processed on the institution's self-disclosure: no routine Scrutiny or EVC. "
                    "An incomplete or inconsistent disclosure is returned for correction.",
     "source_type": "APH", "source": "APH Table 2.3 rows 1–2 (printed p. 30); cl. 2.1",
     "stages": [
         {"code": "SELF_DISCLOSURE", "name": "Self-disclosure check", "sla": 10, "role": "SCRUTINY_OFFICER",
          "on_deficiency": "RETURN"},
     ]},
    {"code": "SCRUTINY_ONLY", "name": "Scrutiny only",
     "description": "Scrutiny with Re-Scrutiny of recorded deficiencies; no EVC.",
     "source_type": "APH", "source": "APH Table 2.3 (printed p. 30); cl. 1.8, 2.23",
     "stages": [
         {"code": "SCRUTINY", "name": "Scrutiny Committee", "sla": 14, "role": "SCRUTINY_OFFICER",
          "on_deficiency": "RETURN_THEN:RE_SCRUTINY"},
         {"code": "RE_SCRUTINY", "name": "Re-Scrutiny Committee", "sla": 10, "role": "RESCRUTINY_OFFICER",
          "conditional": True, "managed_by": "deficiency_review", "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "SCRUTINY_EVC_CONDITIONAL", "name": "Scrutiny + EVC (+ SHC as applicable)",
     "description": "Scrutiny with Re-Scrutiny of recorded deficiencies, then EVC. Shortcomings found by "
                    "the EVC go to the Standing Hearing Committee; SHC is 'as applicable', never automatic.",
     "source_type": "APH", "source": "APH Table 2.3 (printed p. 30); cl. 2.23 (p. 29)",
     "stages": [
         {"code": "SCRUTINY", "name": "Scrutiny Committee", "sla": 14, "role": "SCRUTINY_OFFICER",
          "on_deficiency": "RETURN_THEN:RE_SCRUTINY"},
         {"code": "RE_SCRUTINY", "name": "Re-Scrutiny Committee", "sla": 10, "role": "RESCRUTINY_OFFICER",
          "conditional": True, "managed_by": "deficiency_review", "on_deficiency": "TO_DECISION"},
         {"code": "EVC", "name": "Expert Visit Committee", "sla": 14, "role": "EVC_COORDINATOR",
          "managed_by": "evc", "on_deficiency": "GOTO:SHC"},
         {"code": "SHC", "name": "Standing Hearing Committee", "sla": 14, "role": "SHC_MEMBER",
          "conditional": True, "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "REG_ONLY_EVC", "name": "EVC before first batch passes out",
     "description": "Council-initiated inspection; shortcomings go to the SHC. Outside Table 2.3.",
     "source_type": "REGULATION", "source": "Grant of Approval Regs 2024-27 cl. 6.2(j)",
     "stages": [
         {"code": "EVC", "name": "Expert Visit Committee", "sla": 14, "role": "EVC_COORDINATOR",
          "managed_by": "evc", "on_deficiency": "GOTO:SHC"},
         {"code": "SHC", "name": "Standing Hearing Committee", "sla": 14, "role": "SHC_MEMBER",
          "conditional": True, "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "REG_EVC_SHC", "name": "Inspection + SHC hearing (show cause / complaint)",
     "description": "Council-initiated on a complaint or show-cause notice. Outside Table 2.3.",
     "source_type": "REGULATION", "source": "Grant of Approval Regs 2024-27 cl. 6.3(b), 6.11, 11.2",
     "stages": [
         {"code": "EVC", "name": "Expert Visit Committee", "sla": 14, "role": "EVC_COORDINATOR",
          "managed_by": "evc", "on_deficiency": "GOTO:SHC"},
         {"code": "SHC", "name": "Standing Hearing Committee", "sla": 14, "role": "SHC_MEMBER",
          "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "APPEAL_SAC", "name": "Appeal to the Standing Appellate Committee",
     "description": "One appeal against a decision; the SAC recommends, the competent authority decides.",
     "source_type": "APH", "source": "APH cl. 2.24 (p. 29) for existing institutions; cl. 1.11 (p. 9) for new",
     "stages": [
         {"code": "SAC", "name": "Standing Appellate Committee", "sla": 14, "role": "SAC_MEMBER",
          "on_deficiency": "TO_DECISION"},
     ]},
    {"code": "MANUAL_RULE_REVIEW", "name": "Manual rule review",
     "description": "Category not expressly mapped in Table 2.3. A rule administrator reviews the applicable "
                    "clauses and assigns a route; the system does not guess.",
     "source_type": "DESIGN", "source": "Blueprint §3.1: unmapped categories → MANUAL_RULE_REVIEW",
     "stages": [
         {"code": "RULE_REVIEW", "name": "Rule review", "sla": 10, "role": "RULE_ADMIN",
          "managed_by": "rule_review", "on_deficiency": "RETURN"},
     ]},
]

# --------------------------------------------------------------------------- application types
# notice: PUBLIC_NOTICE (submission within the public-notice window) | YEAR_ROUND (Table 2.2 / cl. 2.22)
# notice_verified=False → category placement in Table 2.2 to be verified against the PDF.
# initiated_by: INSTITUTION | COUNCIL
APPLICATION_TYPES = [
    {"code": "NEW_INSTITUTION", "label": "Setting up a new institution", "chapter": "I", "row": None,
     "route": "CH1_NEW_INSTITUTION", "notice": "PUBLIC_NOTICE", "notice_verified": True, "checklist": "ANNEX1"},
    {"code": "EOA_SELF_DISCLOSURE", "label": "Extension of approval (EoA) on self-disclosure", "chapter": "II", "row": 1,
     "route": "SELF_DISCLOSURE", "notice": "PUBLIC_NOTICE", "notice_verified": True, "checklist": "ANNEX2_EOA"},
    {"code": "NRI_SEATS", "label": "Introduction / continuation of NRI seats", "chapter": "II", "row": 2,
     "route": "SELF_DISCLOSURE", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_EOA"},
    {"code": "DIPLOMA_DEGREE_CONVERSION", "label": "Conversion of diploma ↔ degree level", "chapter": "II", "row": 3,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_NOC"},
    {"code": "NAME_OR_TYPE_CHANGE", "label": "Change in name of institution / affiliating body, or type of institution",
     "chapter": "II", "row": 4, "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": False,
     "checklist": "ANNEX2_GENERAL"},
    {"code": "NEW_PROGRAMME_LEVEL", "label": "Start new programme / level in an existing institution", "chapter": "II",
     "row": 5, "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": True,
     "checklist": "ANNEX2_NOC"},
    {"code": "MERGER_OF_INSTITUTIONS", "label": "Merger of institutions (same campus / city)", "chapter": "II", "row": 6,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_NOC"},
    {"code": "EOA_AFTER_BREAK", "label": "EoA after a break / restoration of intake / hibernation", "chapter": "II",
     "row": 7, "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False,
     "checklist": "ANNEX2_EOA"},
    {"code": "SUPERNUMERARY_FN_OCI_GULF", "label": "Supernumerary seats: foreign nationals / OCI / Gulf",
     "chapter": "II", "row": 8, "route": "SCRUTINY_ONLY", "notice": "PUBLIC_NOTICE", "notice_verified": False,
     "checklist": "ANNEX2_GENERAL"},
    {"code": "INCREASE_INTAKE", "label": "Increase in intake / additional course(s)", "chapter": "II", "row": 9,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": True, "checklist": "ANNEX2_GENERAL"},
    {"code": "INTEGRATED_DUAL_DEGREE", "label": "Integrated / dual-degree course", "chapter": "II", "row": 10,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "FPM", "label": "Fellow Programme in Management", "chapter": "II", "row": 11,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "COURSE_NAME_MERGER_REDUCTION", "label": "Change of course name / merger of courses / reduction in intake",
     "chapter": "II", "row": 12, "route": "SCRUTINY_ONLY", "notice": "PUBLIC_NOTICE", "notice_verified": False,
     "checklist": "ANNEX2_GENERAL"},
    {"code": "COLLABORATION_TWINNING", "label": "Collaboration / twinning programme", "chapter": "II", "row": 13,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "PUBLIC_NOTICE", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "CHANGE_OF_SITE", "label": "Change of site / location", "chapter": "II", "row": 14,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": "ANNEX2_SITE"},
    {"code": "CLOSURE_OF_INSTITUTION", "label": "Closure of institution", "chapter": "II", "row": 15,
     "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": "ANNEX2_GENERAL"},
    {"code": "WOMEN_COED_CONVERSION", "label": "Women's institution ↔ co-educational", "chapter": "II", "row": 16,
     "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": False, "checklist": "ANNEX2_NOC"},
    {"code": "CLOSURE_OF_COURSE", "label": "Closure of programme / course(s)", "chapter": "II", "row": 17,
     "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "BANK_DETAILS_CHANGE", "label": "Change in bank details", "chapter": "II", "row": 18,
     "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": "ANNEX2_GENERAL"},
    {"code": "TRUST_NAME_CHANGE", "label": "Change in name of trust / society / company", "chapter": "II", "row": 19,
     "route": "SCRUTINY_ONLY", "notice": "YEAR_ROUND", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "CONVERSION_TO_DEEMED_UNIVERSITY", "label": "Institution converted into a Deemed-to-be University",
     "chapter": "II", "row": 20, "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "YEAR_ROUND", "notice_verified": False,
     "checklist": "ANNEX2_GENERAL"},
    {"code": "ODL_ONLINE", "label": "Online learning / ODL courses", "chapter": "II", "row": 21,
     "route": "SCRUTINY_EVC_CONDITIONAL", "notice": "ODL_CYCLE", "notice_verified": True, "checklist": "ANNEX2_GENERAL",
     "note": "Processed twice a year per UGC norms (Table 2.3 footnote)"},
    {"code": "OFF_CAMPUS", "label": "Introduction of off-campus (not mapped in Table 2.3)", "chapter": "II", "row": None,
     "route": "MANUAL_RULE_REVIEW", "notice": "YEAR_ROUND", "notice_verified": False, "checklist": "ANNEX2_GENERAL"},
    {"code": "PRE_FIRST_BATCH_INSPECTION", "label": "EVC before the first batch passes out", "chapter": "REG", "row": None,
     "route": "REG_ONLY_EVC", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": None, "initiated_by": "COUNCIL"},
    {"code": "SHOW_CAUSE", "label": "Show cause / complaint hearing", "chapter": "REG", "row": None,
     "route": "REG_EVC_SHC", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": None, "initiated_by": "COUNCIL"},
    {"code": "APPEAL", "label": "Appeal against a decision", "chapter": "II", "row": None,
     "route": "APPEAL_SAC", "notice": "YEAR_ROUND", "notice_verified": True, "checklist": None, "initiated_by": "APPEAL"},
]

# --------------------------------------------------------------------------- document checklists
# condition: always | optional | building_over_30 | land_leased
CHECKLISTS = {
    "ANNEX2_EOA": {"source": "APH Annexure 2, cl. 2.1 (printed p. 81)", "items": [
        ("AFFIDAVIT_2", "Affidavit 2 (authenticated / digitally signed)", "always"),
        ("PAYMENT_RECEIPT", "Payment receipt, if any", "optional"),
        ("OCCUPANCY_CERT", "Occupancy / Completion Certificate, Building Licence or Form D", "always"),
        ("STABILITY_CERT", "Structural Stability Certificate (building older than 30 years)", "building_over_30"),
        ("FIRE_SAFETY", "Valid Fire Safety Certificate from the competent authority", "always"),
        ("SATELLITE_MAP", "Satellite / location map with latitude and longitude of the main entrance", "always"),
        ("AUDITED_ACCOUNTS", "Previous year's audited statement of accounts", "always"),
    ]},
    "ANNEX2_GENERAL": {"source": "APH Annexure 2 (printed p. 81 onward)", "items": [
        ("AFFIDAVIT_2", "Affidavit 2 (authenticated / digitally signed)", "always"),
        ("CATEGORY_DOCS", "Documents prescribed in Annexure 2 for this category", "always"),
        ("STABILITY_CERT", "Structural Stability Certificate (building older than 30 years)", "building_over_30"),
    ]},
    "ANNEX2_NOC": {"source": "APH Annexure 2, cl. 2.3", "items": [
        ("AFFIDAVIT_2", "Affidavit 2 (authenticated / digitally signed)", "always"),
        ("NOC", "No Objection Certificate from the affiliating body / State Government, as applicable", "always"),
        ("ORG_RESOLUTION", "Resolution of the applicant organisation", "always"),
        ("STABILITY_CERT", "Structural Stability Certificate (building older than 30 years)", "building_over_30"),
    ]},
    "ANNEX2_SITE": {"source": "APH Annexure 2, cl. 2.3; change of site also requires all Annexure 1 documents", "items": [
        ("AFFIDAVIT_2", "Affidavit 2 (authenticated / digitally signed)", "always"),
        ("NOC", "No Objection Certificate from the affiliating body / State Government, as applicable", "always"),
        ("ORG_RESOLUTION", "Resolution of the applicant organisation", "always"),
        ("BUILDING_PLAN", "Approved building plan for the new site (Annexure 1)", "always"),
        ("LAND_DOCS", "Land ownership documents or registered lease for the new site (Annexure 1)", "always"),
        ("LEASE_SUPPORT", "Supporting evidence for leased land (lessor's title, registration)", "land_leased"),
        ("FIRE_SAFETY", "Valid Fire Safety Certificate for the new site", "always"),
    ]},
    "ANNEX1": {"source": "APH Annexure 1 (printed pp. 77–80)", "items": [
        ("BUILDING_PLAN", "Approved building plan and architect / authority certificates", "always"),
        ("AFFIDAVIT_2", "Affidavit 2 (authenticated / digitally signed)", "always"),
        ("ORG_REGISTRATION", "Registration document of the Society / Trust / Section-8 Company", "always"),
        ("ORG_RESOLUTION", "Resolution allocating land, building and funds", "always"),
        ("OCCUPANCY_CERT", "Occupancy / Completion Certificate or applicable building document", "always"),
        ("FIRE_SAFETY", "Valid Fire Safety Certificate", "always"),
        ("BANK_CERT", "Bank manager's certificate of financial status", "always"),
        ("LAND_DOCS", "Land ownership documents or registered lease (minimum 30 years)", "always"),
        ("LEASE_SUPPORT", "Supporting evidence for leased land (lessor's title, registration)", "land_leased"),
    ]},
}

# --------------------------------------------------------------------------- academic calendar
CALENDARS = [
    {"academic_year": "2027-28", "notice_ref": "DEMO calendar — replace with the official Public Notice for AY 2027-28",
     "application_open": "2026-08-01", "application_close": "2027-01-31",
     "odl_cycles": [{"cycle": "ODL January 2027 session", "open": "2026-09-01", "close": "2026-11-30"},
                    {"cycle": "ODL July 2027 session", "open": "2027-03-01", "close": "2027-05-31"}]},
    {"academic_year": "2028-29", "notice_ref": "DEMO calendar — future academic year",
     "application_open": "2027-08-01", "application_close": "2028-01-31", "odl_cycles": []},
]

# --------------------------------------------------------------------------- timings
# (key, value, unit, source_type, source)
SETTINGS = [
    ("appeal_window_days", "7", "days", "APH", "cl. 2.24(a): within 7 days after upload of the EC decision; cl. 1.11(a): within 7 days of issue of the LoD"),
    ("security_deposit_days", "15", "days", "APH", "cl. 2.25(f): proof of security deposit with Affidavit 3 within 15 days of intimation"),
    ("security_deposit_applies_to", "NEW_INSTITUTION,NEW_PROGRAMME_LEVEL", "types", "REGULATION",
     "Regs 6.2(f) (new institutions) and 6.3(l) (new programmes); self-financing institutions only"),
    ("stability_validity_years", "5", "years", "APH", "Ch. VI (printed p. 57): structural stability certificate valid 5 years from issue — verify"),
    ("stability_building_age_years", "30", "years", "APH", "Annexure 2: certificate required if the building is older than 30 years"),
    ("lease_min_term_years", "30", "years", "APH", "Land lease of at least 30 years (Ch. VI; Annexure 1)"),
    ("lease_min_live_years_on_renewal", "25", "years", "APH", "AICTE FAQ on cl. 2.1(e): lease extended for 30 years with at least 25 years live"),
    ("online_evc_min_video_minutes", "30", "minutes", "APH", "cl. 1.9: online EVC video of not less than 30 minutes"),
    ("institution_compliance_days", "7", "days", "DESIGN", "Prototype default for replying to deficiencies"),
    ("decision_days", "7", "days", "DESIGN", "Prototype default for the competent authority's queue"),
    ("evc_schedule_days_new", "10", "days", "DESIGN", "Prototype default: tighter EVC scheduling for new institutions"),
    ("evc_report_days", "3", "days", "DESIGN", "Prototype default for report submission after the visit"),
    ("verify_days", "7", "days", "DESIGN", "Prototype default for verification of evidence / renewals"),
    ("resubmit_days", "7", "days", "DESIGN", "Prototype default for resubmission after rejected evidence"),
    ("clock_offset_days", "0", "days", "DESIGN", "Demo clock offset"),
]

# reminder offsets (days before due) and escalation (days overdue) — DESIGN, example policy T-30/T-7/T-1/T+0/T+1
POLICIES = [
    {"kind": "STAGE_SLA", "name": "Stage time limit", "reminders": [3, 1],
     "steps": [{"level": 1, "after_days": 2, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 7, "to_role": "BUREAU"}]},
    {"kind": "EVC_SCHEDULE", "name": "EVC to be scheduled", "reminders": [3, 1],
     "steps": [{"level": 1, "after_days": 2, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 7, "to_role": "BUREAU"}]},
    {"kind": "EVC_REPORT", "name": "EVC report submission", "reminders": [1],
     "steps": [{"level": 1, "after_days": 1, "to_role": "EVC_COORDINATOR"}, {"level": 2, "after_days": 4, "to_role": "REGIONAL_HEAD"}]},
    {"kind": "DECISION", "name": "Competent authority decision", "reminders": [2],
     "steps": [{"level": 1, "after_days": 3, "to_role": "BUREAU"}]},
    {"kind": "INSTITUTION_COMPLIANCE", "name": "Institution reply to deficiencies", "reminders": [3, 1],
     "steps": [{"level": 1, "after_days": 1, "to_role": "SCRUTINY_OFFICER"}, {"level": 2, "after_days": 7, "to_role": "REGIONAL_HEAD"}]},
    {"kind": "UNDERTAKING", "name": "Time-bound undertaking", "reminders": [30, 7, 1],
     "steps": [{"level": 1, "after_days": 1, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 14, "to_role": "BUREAU"}]},
    {"kind": "UNDERTAKING_VERIFY", "name": "Verification of compliance evidence", "reminders": [2],
     "steps": [{"level": 1, "after_days": 2, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 7, "to_role": "BUREAU"}]},
    {"kind": "DOC_EXPIRY", "name": "Document renewal", "reminders": [90, 30, 7, 1],
     "steps": [{"level": 1, "after_days": 1, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 14, "to_role": "BUREAU"}]},
    {"kind": "DOC_VERIFY", "name": "Verification of renewed document", "reminders": [2],
     "steps": [{"level": 1, "after_days": 2, "to_role": "REGIONAL_HEAD"}, {"level": 2, "after_days": 7, "to_role": "BUREAU"}]},
    {"kind": "RULE_REVIEW", "name": "Manual rule review", "reminders": [3],
     "steps": [{"level": 1, "after_days": 3, "to_role": "BUREAU"}]},
    {"kind": "APPEAL_WINDOW", "name": "Appeal window", "reminders": [3, 1], "steps": []},
]

REGIONS = [
    {"code": "NRO", "name": "Northern", "office_city": "Kanpur", "states": ["Uttar Pradesh", "Bihar", "Jharkhand"]},
    {"code": "WRO", "name": "Western", "office_city": "Mumbai", "states": ["Maharashtra", "Goa"]},
    {"code": "SRO", "name": "Southern", "office_city": "Chennai", "states": ["Tamil Nadu", "Puducherry"]},
    {"code": "CRO", "name": "Central", "office_city": "Bhopal", "states": ["Madhya Pradesh", "Chhattisgarh"]},
]
