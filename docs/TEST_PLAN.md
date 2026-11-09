# Test plan

## Automated

| Layer | Command | What it covers |
|---|---|---|
| API / engine (pytest, 49 tests) | `cd backend && python -m pytest -q` | Routing matrix, workflow, deadlines, documents, security. SQLite by default. |
| Same suite on PostgreSQL | `DATABASE_URL=postgresql+psycopg://user@host/db python -m pytest -q` | Verified against PostgreSQL 16 |
| Migrations | `cd backend && DATABASE_URL=... alembic upgrade head` | The initial schema creates all 25 tables |
| Browser smoke (Playwright) | `cd frontend && node e2e/smoke.cjs http://localhost:8000 /tmp/shots` | See below |

The browser smoke test does the following:
- Signs in as seven roles and opens every page each role can see.
- Fails on any console error, uncaught exception or 5xx response.
- Publishes a ruleset version as `ruleadmin` and checks that the version label changes.
- Checks that the rule trace renders on an application.

Tests use a frozen clock (5 Nov 2026, 10:30 IST), so results never depend on the real date.

### Test files

| File | Tests |
|---|---|
| `test_routing.py` | Table 2.3 matrix matches config (21 rows) · each category reaches its first queue · Chapter I route for new institutions · council-initiated types refused for institutions · unmapped category → manual rule review → route assigned · mandatory checklist enforced · stability certificate only for buildings over 30 years |
| `test_workflow.py` | **Demo A**: itemised deficiencies → per-item replies → Re-Scrutiny limited to recorded items → EVC (member-only report, online video of at least 30 min) → authority decision with reference · return pauses the clock · unresolved Re-Scrutiny goes to the authority as not recommended · 7-day single appeal (cl. 2.24) · Chapter I appeal trigger on the LoD (cl. 1.11) · revert by a regional officer |
| `test_deadlines.py` | **Demo C**: security-deposit undertaking → reminders → L1/L2 escalation → acknowledge → late evidence closes but stays flagged late; no duplicate notifications · deposit only for self-financing institutions and listed types · academic-year assignment and public-notice refusal · two-level escalation fires once · email marked SIMULATED · calendar days, due 17:30 IST |
| `test_documents.py` | **Demo B**: lease critical date and checks, fire-certificate renewal, stability validity · missing stability certificate flagged and uploadable |
| `test_security.py` | Institution isolation, including documents and files · only the assignee can act · rule changes need `RULE_ADMIN` and publish a new version with pinning · idempotency key prevents a duplicate submission · optimistic lock rejects a stale action · upload type, size and malware rules · audit-chain tampering detected, request IDs recorded · reports |

## Manual checks before a demo

1. `docs/DEMO_RUNBOOK.md`: walk Demos A, B and C on a fresh seed.
2. Check the login and footer still carry the "prototype, not an official AICTE service" notice.
3. Check the page references in `docs/APH_TRACEABILITY.md` against the official APH PDF.
