# API contract

Base path: `/api/v1`. `/api` is kept as an alias for the bundled frontend.

The full OpenAPI schema is served at `/docs` and `/openapi.json` while the server runs.

## Conventions

- **Auth.** `POST /auth/login` returns a bearer token; send it as `Authorization: Bearer <token>`.
- **Idempotency.** Every state-changing `POST` accepts an `Idempotency-Key` header. A replay with the same key returns the original response with `Idempotent-Replay: true`.
- **Optimistic locking.** Application actions take `expected_version`. A stale version returns `409`.
- **Errors.** `403` for a role or assignee mismatch. `409` for a workflow conflict (wrong stage, already decided, stale version). `422` for invalid input (missing checklist item, short EVC video, missing reason).
- **Times.** ISO 8601 with a `+05:30` offset. Due times are 17:30 IST.
- **Request IDs.** Every response carries `X-Request-ID`, and the same ID is written into the audit chain.

## Endpoints

### Auth and session
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/login` | anyone | Username and password, returns a token |
| GET | `/auth/me`, `/me` | signed in | Current user, role and scope |
| GET | `/demo/users` | demo mode | Demo account list |

### Reference data
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/meta` | signed in | Regions, labels, clock |
| GET | `/application-types` | signed in | Table 2.3 / Chapter I types with route, window and checklist for the caller's institution |

### Demo clock
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/clock` | signed in | Current simulated time |
| POST | `/clock/advance` | officials, demo mode | Move simulated time forward |
| POST | `/demo/reset` | bureau, admin | Reseed |
| POST | `/tick` | officials | Run the deadline engine now |

### Dashboard
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/dashboard`, `/dashboard/summary` | signed in | KPIs, pendency, ageing, regions, watchlist, workload, unacknowledged escalations |

### Applications
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/applications` | scoped | List, with filters `status`, `stage`, `mine`, `q` |
| POST | `/applications` | institution | Submit: `application_type`, `documents` {doc_code: file_id}. The checklist is enforced and the ruleset pinned. |
| GET | `/applications/{id}` | scoped | Detail: stages, deficiencies, checklist, rule trace, EVC, obligations, audit, allowed actions |
| GET | `/applications/{id}/route` | scoped | Resolved route and stage list |
| POST | `/applications/{id}/actions` | assignee / role | One endpoint for every transition (see below) |
| GET | `/officers` | officials | Reassignment targets |

Actions (`action` field):
- `record_outcome`: takes `deficiencies[]` with `finding`, `reference` and `correction_requested`.
- `return_for_clarification`
- `institution_respond`: takes `item_responses[]`.
- `verify_deficiencies`: takes `verdicts` {deficiency_id: RESOLVED or UNRESOLVED}.
- `assign_route`: rule admin, for `MANUAL_RULE_REVIEW`.
- `revert`, `reassign`
- `decide`: competent authority. Takes `decision`, `decision_ref` and `file_id`.
- `file_appeal`: within the window; one appeal per application.

### EVC
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/evc`, `/evc/queue` | coordinator, members, authority | Queue and scheduled visits. Members see only their own visits; `can_report` flags the ones they can report on. |
| GET | `/evc/{id}/panel` | coordinator | Random panel draw with conflict checks |
| POST | `/evc/{id}/schedule` | coordinator | Date, mode (PHYSICAL or ONLINE) and panel of expert IDs |
| POST | `/evc/{id}/report` | assigned EVC member | `outcome`, `remarks`, `file_id`; plus `video_url` and `video_minutes` (≥ 30) when online |

### Compliance
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/undertakings`, `/obligations/undertakings` | scoped | Time-bound requirements, with `was_late` and `source_document` |
| POST | `/undertakings/{id}/evidence` | institution | Evidence files |
| POST | `/undertakings/{id}/verify` | scrutiny officer | `accept` and `remarks` |
| GET | `/documents` | scoped | Tracked documents plus virtual `MISSING` rows; each with `checks[]` and `source` |
| POST | `/documents` | institution | Upload a missing document |
| POST | `/documents/{id}/renew` | institution | New version |
| POST | `/documents/{id}/verify`, `/review` | scrutiny officer | Accept or reject, with advisory checks |
| GET | `/documents/{id}/versions` | scoped | Version history |

### Deadlines and alerts
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/obligations` | scoped | All open deadlines, with filters `state`, `kind`, `escalated`, `mine` |
| GET | `/escalations` | officials | Filters `open_only`, `mine`; `can_acknowledge` flags the ones you can acknowledge |
| POST | `/escalations/{id}/acknowledge` | target role | Takes `note` |
| GET | `/notifications` | signed in | In-app alerts and unread count |
| GET | `/notifications/outbox` | signed in | Simulated emails (bureau and admin see all) |
| POST | `/notifications/read-all`, `/{id}/read`, `/{id}/acknowledge` | signed in | Mark read |

### Governance
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/audit` | officials | Audit events |
| GET | `/audit/verify` | officials | Hash-chain verification |
| GET | `/config`, `/admin/rulesets` | officials | Active ruleset, versions with pinned counts, routes, types, checklists, calendars, policies, settings |
| PUT | `/config/stages/{id}` | rule admin | `sla_days` and `reason`; publishes a new ruleset version |
| PUT | `/config/policies/{id}` | rule admin | Reminder offsets and escalation steps (`after_days`, `to_role`), with `reason` |
| GET | `/reports/{kind}[.csv]` | officials | `pendency`, `evc`, `undertakings`, `documents`, `overdue`, `escalations`, `regions` |

### Files
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/files` | signed in | Upload: PDF, JPG or PNG, up to 10 MB, malware check, SHA-256 stored |
| GET | `/files/{id}` | scoped | Download (audited) |
