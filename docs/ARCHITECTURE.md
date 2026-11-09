# Architecture

```
React 18 SPA (Vite) ──HTTPS /api/v1──▶ FastAPI modular monolith ◀── asyncio scheduler tick (60 s)
                                        │
   rules.py ── versioned rulesets: routes, stages, Table 2.3 types, checklists, calendars, settings
   workflow.py ── submit → route → stages → deficiencies → re-scrutiny → EVC → SHC → decision → appeal
   evc.py ── queue, panel draw (conflict of interest, double booking), member reports, video rule
   compliance.py ── undertakings, tracked documents, lease rule, stability rule, verification
   obligations.py ── ONE deadline engine: reminders T−n/T+0/T+1, escalation L1/L2, acknowledgement
   audit.py ── append-only SHA-256 hash chain, request_id per HTTP request
                                        │
                     SQLAlchemy 2 → SQLite (default) | PostgreSQL 16 (Alembic migrations)
                     File store (SHA-256 per upload, scoped downloads, audited)
```

## Main decisions

| Decision | Why |
|---|---|
| Every deadline is an `Obligation` | Stage limits, institution replies, EVC scheduling and reports, decisions, undertakings, document renewals and appeal windows all remind, escalate and audit the same way. |
| Rules are data in a versioned `Ruleset` | The APH changes every cycle. A change publishes a new version. Each application is pinned to the version it was submitted under, so in-flight cases never change retroactively. |
| Unmapped categories go to `MANUAL_RULE_REVIEW` | The system does not guess a route that the handbook does not state. |
| Humans decide | The engine only moves a case to the next queue after its owner records an outcome. Decisions belong to `COMPETENT_AUTHORITY`. Checks are labelled advisory. |
| Calendar days, due at 17:30 IST, stored in UTC | Matches the blueprint and avoids holiday-calendar ambiguity. The UI shows IST with an explicit offset. |
| Idempotency keys + optimistic locking | Double clicks and two officers acting on the same case cannot create duplicate or conflicting transitions. |
| Simulated email | The outbox and the log record every message (status `SIMULATED`). A real adapter replaces one function. |

## Data model (main tables)

| Area | Tables |
|---|---|
| Rules | `rulesets`, `route_templates`, `stage_definitions`, `application_type_defs`, `document_requirements`, `academic_calendars`, `escalation_policies`, `settings` |
| Domain | `regions`, `institutions`, `applications`, `application_documents`, `stage_instances`, `deficiencies`, `evc_visits`, `experts`, `undertakings`, `tracked_documents` |
| Cross-cutting | `obligations`, `escalations`, `notifications`, `audit_events`, `idempotency_records`, `file_objects`, `users` |

## Roles

`INSTITUTION`, `SCRUTINY_OFFICER`, `RESCRUTINY_OFFICER`, `EVC_COORDINATOR`, `EVC_MEMBER`, `SHC_MEMBER`, `SAC_MEMBER`, `REGIONAL_HEAD`, `BUREAU`, `COMPETENT_AUTHORITY`, `RULE_ADMIN`, `ADMIN`.

Access is scoped as follows:
- Officials see their own Region.
- Institutions see only their own records.
- Bureau, competent authority, rule admin, SAC and admin see all of India.
- Only the assigned officer can act on a stage.

## Deviations from the blueprint

- JavaScript (JSX) instead of TypeScript, to keep the hackathon build simple.
- Integer primary keys instead of UUIDs; application numbers are separate public identifiers.
- A single asyncio tick instead of Celery Beat. For production, move it to a leader-locked worker.

## Path to production

- PostgreSQL with row-level security.
- OIDC / government SSO for officials.
- ClamAV and S3-compatible storage.
- A leader-locked scheduler.
- Real email and SMS adapters.
- An integration adapter to the existing AICTE portal in place of the demo intake.
- `DEMO_MODE=0`.
