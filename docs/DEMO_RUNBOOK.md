# Demo runbook

About 10 minutes. Every account uses the password `demo123`. The sign-in page lists all of them, and you can click one to sign in.

**Before you start**
- Reset to a known state. Delete `backend/aicte_flow.db` and restart, or sign in as `bureau` and call `POST /api/v1/demo/reset`.
- The demo clock starts at the real date. The **+1d / +5d / +10d** buttons in the top bar move simulated time forward. They are available only when `DEMO_MODE=1`.
- Keep `docs/APH_TRACEABILITY.md` open, so you can show the clause behind any rule you are asked about.

## Demo A: Northern Demo Institute, Re-Scrutiny scoped to the recorded deficiencies (APH cl. 1.8, 1.9)

1. **Submit as `inst40`.** Go to Applications → **New application** → *Increase in intake* (Table 2.3 row 9).
   - The form shows the route (Scrutiny + EVC, SHC as applicable) and the Annexure 2 checklist.
   - Try to submit with a mandatory item missing. The submission is refused.
   - Upload all the items and submit.
   - On the detail page, the **rule trace** shows the pinned ruleset, the category row and the submission window.
2. **Record deficiencies as `nro.scrutiny1`.** Open the application → **Record: deficiency**.
   - Add two itemised findings, for example "Fire certificate expired" and "Affidavit 2 not in format".
   - The application returns to the institution, the stage clock pauses, and the institution gets an *Institution compliance* deadline.
3. **Reply as `inst40`.** Reply to each item separately, uploading corrected evidence per item.
4. **Re-Scrutiny as `nro.rescrutiny`.** The re-scrutiny screen lists **only the two recorded items**. Mark each one Resolved.
   - Point out that the officer cannot raise new issues here; that is the cl. 1.8 rule.
5. **Schedule the EVC as `nro.evc`.** Go to the EVC queue → **Schedule**, then choose *Online* and **Draw panel**.
   - The draw excludes experts from the institution's home state and experts already booked that day.
6. **Report as `expert1`, or whichever expert was drawn.** Go to My EVC visits → **Submit report**.
   - Try 20 minutes of video. It is refused, because cl. 1.9 requires at least 30.
   - Enter 35 minutes and submit CLEAR.
   - The coordinator has no report button.
7. **Decide as `authority`.** Open the application, which is awaiting decision → **Approve**.
   - Enter a decision reference and attach the order file.
   - Only this role can decide; committees only recommend.

## Demo B: Western Demo College, lease and certificates (APH cl. 2.1(e), Annexure 2)

1. **As `inst41`,** go to Undertakings & documents → *Lease & documents*.
   - The land lease shows **Lease review required**. The alert falls on *lease expiry minus the longest course duration*, not on the expiry date.
   - The fire certificate is near expiry. Upload a renewal.
   - The building dates from 1992 (more than 30 years old), so a structural stability certificate is required. It is on record with a 5-year validity.
   - If a certificate is missing, it appears as **Missing** with an **Upload document** button.
2. **As `wro.scrutiny1`,** verify the renewal. The advisory checks show the lease term (≥ 30 years) and the live lease (≥ 25 years) with their sources.
   - The officer accepts or rejects; the system only advises.

## Demo C: Central Demo Polytechnic, time-bound requirement and escalation (cl. 2.25(f), Regs 6.10)

1. **As `inst42`,** open Undertakings. A *Security deposit with Affidavit 3* undertaking was created from the approval order and is due within 15 days.
   - It exists only because the institution is self-financing and the type is listed in `security_deposit_applies_to`.
   - Wording matters: Regs 6.10 rules out conditional approvals, so the screen calls it a time-bound requirement, not a condition.
2. Click **+10d** twice. The deadline passes T−7, T−1, T+0 and T+1 reminders, then escalates:
   - L1 to the Regional head
   - L2 to the Bureau
3. **As `cro.head`,** go to Deadlines & escalations → *Escalations* → **Acknowledge**, and add a note on the action being taken.
4. **As `inst42`,** submit the evidence. The item closes but stays flagged **Late**; it is never shown as on time.
5. **As `bureau`,** open Alerts → *Email outbox*. Every reminder and escalation appears there as a *Simulated* email.

## Governance (2 minutes)

- **`ruleadmin`:** Rules & timelines → Routes → **Edit** a stage time limit, giving a reason.
  - The change publishes a new ruleset version.
  - The *Versions* tab shows earlier applications still pinned to v1.
  - Point out the Table 2.3 matrix tab, with *verify* tags on uncertain placements.
- **`bureau`:** Audit trail → **Verify hash chain**.
- **Reports:** download pendency, EVC and overdue reports as CSV.
