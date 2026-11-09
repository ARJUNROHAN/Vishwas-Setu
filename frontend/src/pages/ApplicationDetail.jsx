import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useApp, useFetch } from '../app-context'
import Icon from '../components/Icon'
import { ActionForm, Badge, DueBadge, ErrorBox, EscBadge, FileInput, Kind, Loading, StatusBadge, PageHeader } from '../components/ui'
import { ACTION_LABEL, fmtDate, fmtDateTime, ROLE_SHORT } from '../util'

const ACTION_META = {
  record_nil_deficiency: { label: 'Record: no deficiency', tone: 'primary', title: 'Record outcome: no deficiency' },
  record_deficiency: { label: 'Record deficiencies', tone: 'warn', title: 'Record deficiencies' },
  return_for_clarification: { label: 'Return for clarification', tone: 'ghost', title: 'Return to institution for clarification' },
  verify_deficiencies: { label: 'Verify recorded deficiencies', tone: 'primary', title: 'Re-scrutiny: verify recorded deficiencies' },
  assign_route: { label: 'Assign route', tone: 'primary', title: 'Rule review: assign processing route' },
  respond: { label: 'Submit compliance', tone: 'primary', title: 'Reply to deficiencies' },
  revert: { label: 'Revert to earlier stage', tone: 'ghost', title: 'Revert application' },
  reassign: { label: 'Reassign', tone: 'ghost', title: 'Reassign current stage' },
  approve: { label: 'Approve', tone: 'primary', title: 'Record decision: approve' },
  reject: { label: 'Reject', tone: 'danger', title: 'Record decision: reject' },
  appeal: { label: 'File appeal', tone: 'primary', title: 'File appeal (Standing Appellate Committee)' },
}

function stepState(stage, instances, app) {
  const mine = instances.filter((s) => s.code === stage.code)
  const last = mine[mine.length - 1]
  if (!last) return { state: stage.conditional ? 'skipped' : 'pending', last }
  if (!last.completed_at) return { state: app.status === 'RETURNED' ? 'returned' : 'current', last, count: mine.length }
  return { state: ['NIL_DEFICIENCY', 'ROUTE_ASSIGNED'].includes(last.outcome) ? 'done' : last.outcome === 'REVERTED' ? 'reverted' : 'deficient', last, count: mine.length }
}

function RouteStepper({ app }) {
  const decided = ['APPROVED', 'REJECTED', 'UNDER_APPEAL'].includes(app.status)
  return (
    <div className="stepper">
      {app.route_detail.stages.map((s) => {
        const st = stepState(s, app.stages, app)
        return (
          <div key={s.code} className={`step step-${st.state}`}>
            <div className="step-dot">{st.state === 'done' ? <Icon name="check" size={15} strokeWidth={3} /> : st.state === 'deficient' ? <Icon name="alert" size={14} /> : s.order}</div>
            <div className="step-name">{s.name}</div>
            <div className="step-meta">
              {st.state === 'skipped' ? (s.code === 'SHC' ? 'As applicable' : 'Only if deficiencies') : st.state === 'pending' ? `${s.sla_days} days (default)` :
                st.state === 'current' ? `In progress${st.last?.assignee ? `, ${st.last.assignee.name}` : ''}` :
                  st.state === 'returned' ? 'With institution' :
                    `${st.last.outcome === 'NIL_DEFICIENCY' ? 'No deficiency' : st.last.outcome === 'DEFICIENCY' ? 'Deficiency' : st.last.outcome === 'ROUTE_ASSIGNED' ? 'Route assigned' : 'Reverted'}, ${fmtDate(st.last.completed_at)}`}
              {st.count > 1 && ` (${st.count} rounds)`}
            </div>
          </div>
        )
      })}
      <div className={`step ${decided ? (app.status === 'APPROVED' ? 'step-done' : 'step-deficient') : app.status === 'READY_FOR_DECISION' ? 'step-current' : 'step-pending'}`}>
        <div className="step-dot">{app.status === 'APPROVED' ? <Icon name="check" size={15} strokeWidth={3} /> : <Icon name="checkCircle" size={15} />}</div>
        <div className="step-name">Decision</div>
        <div className="step-meta">{decided ? `${app.decision === 'APPROVED' ? 'Approved' : 'Not approved'}, ${fmtDate(app.decided_at)}` : 'Competent authority'}</div>
      </div>
    </div>
  )
}

function DeficiencyEditor({ items, setItems, checklist }) {
  const set = (i, k, v) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: v } : x)))
  return (
    <div className="def-editor">
      {items.map((d, i) => (
        <div key={i} className="def-item">
          <div className="row between center"><strong>Deficiency {i + 1}</strong>
            {items.length > 1 && <button type="button" className="link small" onClick={() => setItems(items.filter((_, j) => j !== i))}>Remove</button>}</div>
          <div className="field"><label>Finding</label><input value={d.finding} onChange={(e) => set(i, 'finding', e.target.value)} required /></div>
          <div className="row gap">
            <div className="field grow"><label>Document / standard</label>
              <input list="checklist-docs" value={d.reference} onChange={(e) => set(i, 'reference', e.target.value)} /></div>
            <div className="field grow"><label>Correction requested</label><input value={d.correction} onChange={(e) => set(i, 'correction', e.target.value)} /></div>
          </div>
        </div>
      ))}
      <datalist id="checklist-docs">{checklist.map((c) => <option key={c.id} value={c.label} />)}</datalist>
      <button type="button" className="btn ghost small" onClick={() => setItems([...items, { finding: '', reference: '', correction: '' }])}>Add another deficiency</button>
    </div>
  )
}

function ActionDialog({ action, app, onClose }) {
  const nav = useNavigate()
  const [target, setTarget] = useState(app.revert_targets[0] || '')
  const [routeCode, setRouteCode] = useState(app.assignable_routes[0]?.code || '')
  const [assignee, setAssignee] = useState('')
  const [fileIds, setFileIds] = useState([])
  const [items, setItems] = useState([{ finding: '', reference: '', correction: '' }])
  const openDefs = app.deficiencies.filter((d) => d.status === 'OPEN')
  const respondedDefs = app.deficiencies.filter((d) => d.status === 'RESPONDED')
  const [responses, setResponses] = useState({})
  const [verdicts, setVerdicts] = useState(Object.fromEntries(respondedDefs.map((d) => [d.id, { resolved: true, remarks: '' }])))
  const [decisionRef, setDecisionRef] = useState('')
  const meta = ACTION_META[action]
  const current = app.stages.filter((s) => !s.completed_at).slice(-1)[0]
  const stageDef = current && app.route_detail.stages.find((s) => s.code === current.code)
  const itemised = action === 'record_deficiency' && ['SCRUTINY', 'SELF_DISCLOSURE'].includes(current?.code)
  const { data: officers } = useFetch(action === 'reassign' && stageDef ? `/officers?role=${stageDef.assignee_role}&region_id=${app.region_id}` : null)
  const submit = async (remarks, key) => {
    const r = await api.post(`/applications/${app.id}/actions`, {
      action, remarks, expected_version: app.version,
      target_stage: action === 'revert' ? target : undefined, route_code: action === 'assign_route' ? routeCode : undefined,
      user_id: action === 'reassign' ? Number(assignee) : undefined, file_ids: fileIds,
      deficiencies: itemised ? items : [], decision_ref: decisionRef,
      decision_file_id: ['approve', 'reject'].includes(action) ? fileIds[0] : undefined,
      item_responses: Object.fromEntries(Object.entries(responses).map(([k, v]) => [k, { response: v.response, file_ids: v.file_ids || [] }])),
      verdicts,
    }, key)
    if (r.appeal_application_id) nav(`/applications/${r.appeal_application_id}`)
  }
  let hint = null
  if (action === 'record_deficiency' && stageDef) {
    const rule = stageDef.on_deficiency
    hint = rule === 'RETURN' ? 'The application returns to the institution for correction, then comes back to this stage.'
      : rule.startsWith('RETURN_THEN:') ? 'The institution replies to each item; the Re-Scrutiny Committee then verifies only these items (APH cl. 1.8).'
        : rule.startsWith('GOTO:') ? `The application moves to the ${rule.split(':')[1]} as applicable.`
          : 'The application goes to the competent authority marked “not recommended”.'
  }
  if (action === 'record_nil_deficiency') hint = 'The application moves to the next prescribed queue; nothing is approved automatically.'
  if (action === 'return_for_clarification') hint = 'Your stage clock pauses until the institution replies.'
  if (action === 'verify_deficiencies') hint = 'Re-scrutiny verifies only the deficiencies recorded by the Scrutiny Committee (APH cl. 1.8).'
  if (action === 'approve' || action === 'reject') hint = `Committee recommendation: ${app.recommendation === 'RECOMMENDED' ? 'recommended' : 'not recommended'}. The decision is yours and is recorded with your reasons and order reference.`
  const valid = action === 'reassign' ? !!assignee
    : action === 'respond' ? openDefs.every((d) => (responses[d.id]?.response || '').trim())
      : (action === 'approve' || action === 'reject') ? !!decisionRef.trim()
        : itemised ? items.every((d) => d.finding.trim()) : true
  return (
    <ActionForm title={meta.title} submitLabel={meta.label} onSubmit={submit} onClose={onClose} extraValid={valid}
      tone={meta.tone === 'danger' ? 'danger' : meta.tone === 'warn' ? 'warn' : 'primary'}
      remarksLabel={action === 'respond' ? 'Covering note' : action === 'appeal' ? 'Grounds of appeal' : action === 'assign_route' ? 'Clause / notification relied on' : 'Remarks / reasons (recorded in the audit trail)'}>
      {hint && <p className="hint">{hint}</p>}
      {itemised && <DeficiencyEditor items={items} setItems={setItems} checklist={app.checklist} />}
      {action === 'respond' && openDefs.map((d) => (
        <div key={d.id} className="def-item">
          <strong>{d.seq}. {d.finding}</strong>
          {d.correction_requested && <div className="muted small">Requested: {d.correction_requested}</div>}
          <div className="field"><label>Your response</label>
            <textarea rows={2} value={responses[d.id]?.response || ''} required
              onChange={(e) => setResponses({ ...responses, [d.id]: { ...responses[d.id], response: e.target.value } })} /></div>
          <FileInput label="Corrective evidence" onUploaded={(ids) => setResponses({ ...responses, [d.id]: { ...responses[d.id], file_ids: ids } })} />
        </div>
      ))}
      {action === 'respond' && !openDefs.length && <FileInput onUploaded={setFileIds} />}
      {action === 'verify_deficiencies' && respondedDefs.map((d) => (
        <div key={d.id} className="def-item">
          <strong>{d.seq}. {d.finding}</strong>
          <div className="small">Institution: “{d.response_text}”{d.response_file_ids.map((f) => <button type="button" key={f} className="link small" onClick={() => api.download(`/files/${f}`, `evidence-${f}`)}> evidence #{f}</button>)}</div>
          <div className="row gap center">
            <label className="check"><input type="radio" checked={verdicts[d.id]?.resolved} onChange={() => setVerdicts({ ...verdicts, [d.id]: { ...verdicts[d.id], resolved: true } })} /> Resolved</label>
            <label className="check"><input type="radio" checked={!verdicts[d.id]?.resolved} onChange={() => setVerdicts({ ...verdicts, [d.id]: { ...verdicts[d.id], resolved: false } })} /> Not resolved</label>
            <input className="grow" placeholder="Remarks on this item" value={verdicts[d.id]?.remarks || ''} onChange={(e) => setVerdicts({ ...verdicts, [d.id]: { ...verdicts[d.id], remarks: e.target.value } })} />
          </div>
        </div>
      ))}
      {action === 'assign_route' && (
        <div className="field"><label>Route</label>
          <select value={routeCode} onChange={(e) => setRouteCode(e.target.value)}>
            {app.assignable_routes.map((r) => <option key={r.code} value={r.code}>{r.name} ({r.source})</option>)}
          </select></div>
      )}
      {action === 'revert' && (
        <div className="field"><label>Revert to</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {app.revert_targets.map((c) => <option key={c} value={c}>{app.route_detail.stages.find((s) => s.code === c)?.name}</option>)}
          </select></div>
      )}
      {action === 'reassign' && (
        <div className="field"><label>New assignee</label>
          <select value={assignee} onChange={(e) => setAssignee(e.target.value)} required>
            <option value="">Select</option>
            {(officers || []).map((o) => <option key={o.id} value={o.id}>{o.name}, {o.designation}</option>)}
          </select></div>
      )}
      {(action === 'approve' || action === 'reject') && <>
        <div className="field"><label>Order / letter reference no.</label><input value={decisionRef} onChange={(e) => setDecisionRef(e.target.value)} placeholder="e.g. F.No. Northern/1-4630.../2027/EOA" required /></div>
        <FileInput label="Signed order (optional for demo)" onUploaded={setFileIds} />
      </>}
    </ActionForm>
  )
}

function DeficiencyReview({ app }) {
  if (!app.deficiencies.length) return null
  return (
    <section className="card">
      <div className="card-head"><h2>Deficiency review</h2><span className="muted small">Finding, institution's correction, re-scrutiny verdict (APH cl. 1.8)</span></div>
      <table className="table">
        <thead><tr><th>#</th><th>Finding recorded by scrutiny</th><th>Institution's response</th><th>Re-scrutiny verdict</th></tr></thead>
        <tbody>
          {app.deficiencies.map((d) => (
            <tr key={d.id}>
              <td className="num">{d.seq}</td>
              <td><strong>{d.finding}</strong>{d.reference && <div className="muted small">{d.reference}</div>}{d.correction_requested && <div className="small">Requested: {d.correction_requested}</div>}</td>
              <td>{d.response_text ? <>{d.response_text}<div className="muted small">{fmtDateTime(d.responded_at)}{d.response_file_ids.map((f) => <button key={f} className="link small" onClick={() => api.download(`/files/${f}`, `evidence-${f}`)}> · evidence #{f}</button>)}</div></> : <span className="muted">Awaiting response</span>}</td>
              <td><StatusBadge status={d.status} />{d.verified_by && <div className="muted small">{d.verified_by}, {fmtDate(d.verified_at)}</div>}{d.verify_remarks && <div className="small">“{d.verify_remarks}”</div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export default function ApplicationDetail() {
  const { id } = useParams()
  const { user } = useApp()
  const { data: app, error, loading } = useFetch(`/applications/${id}`)
  const [action, setAction] = useState(null)
  const [showSystem, setShowSystem] = useState(false)
  if (error) return <ErrorBox error={error} />
  if (loading && !app) return <Loading />
  const openObs = app.obligations.filter((o) => o.state !== 'CLOSED')
  const events = app.audit.filter((e) => showSystem || !['OBLIGATION_OPENED', 'OBLIGATION_CLOSED', 'STAGE_STARTED', 'FILE_DOWNLOADED'].includes(e.action))
  const rt = app.rule_trace

  return (
    <div>
      <PageHeader title="Applications" crumbs={[{ to: '/applications', label: 'List' }, <span className="mono">{app.application_no}</span>]}
        actions={app.allowed_actions.length > 0 && app.allowed_actions.map((a) => <button key={a} className={`btn ${ACTION_META[a].tone}`} onClick={() => setAction(a)}>{ACTION_META[a].label}</button>)} />
      <section className="card summary-card">
        <div className="summary-main">
          <h2 className="summary-title">{app.type_label} <StatusBadge status={app.status} />
            {app.status === 'READY_FOR_DECISION' && <Badge tone={app.recommendation === 'RECOMMENDED' ? 'good' : 'warning'}>{app.recommendation === 'RECOMMENDED' ? 'Committees: recommended' : 'Committees: not recommended'}</Badge>}</h2>
          <div className="summary-meta">
            <span><span className="meta-k">Application</span><span className="mono">{app.application_no}</span></span>
            <span><span className="meta-k">Institution</span>{app.institution}</span>
            <span><span className="meta-k">Region</span>{app.region}</span>
            <span><span className="meta-k">Processing year</span>{app.processing_academic_year}</span>
            {app.programme && <span><span className="meta-k">Programme</span>{app.programme}{app.intake_requested && `, intake ${app.intake_requested}`}</span>}
          </div>
        </div>
      </section>
      {app.parent_application_id && <p className="hint">Appeal against <Link to={`/applications/${app.parent_application_id}`}>the decided application</Link>.</p>}

      <section className="card">
        <div className="card-head"><h2>Route: {app.route_detail.name}</h2><span className="muted small">{app.route_detail.aph_reference}</span></div>
        <RouteStepper app={app} />
        <div className="trace">
          <span><Icon name="sliders" size={14} /> Ruleset <strong>{rt.ruleset}</strong>{rt.ruleset_status === 'RETIRED' && ' (pinned; since superseded)'}</span>
          <span>Category: {rt.chapter === 'I' ? 'Chapter I' : rt.chapter === 'REG' ? 'Regulations (outside Table 2.3)' : rt.table_row ? `Table 2.3 row ${rt.table_row}` : 'Not mapped in Table 2.3'}</span>
          <span>Submission: {rt.notice_category === 'PUBLIC_NOTICE' ? 'public-notice window' : rt.notice_category === 'ODL_CYCLE' ? 'ODL twice-yearly cycle' : 'year-round (cl. 2.22)'}{!rt.notice_verified && ' (Table 2.2 placement to verify)'}</span>
          <a href={`${rt.source_url}#page=46`} target="_blank" rel="noreferrer">Open APH Table 2.3</a>
        </div>
      </section>

      <DeficiencyReview app={app} />

      <div className="grid-2 wide-left">
        <div>
          <section className="card">
            <div className="card-head"><h2>Open deadlines</h2></div>
            {openObs.length === 0 ? <p className="muted">No open deadlines.</p> : (
              <ul className="watch">
                {openObs.map((o) => (
                  <li key={o.id} className="row between gap">
                    <div><div className="row gap center"><Kind kind={o.kind} /><EscBadge level={o.escalation_level} /></div>
                      <div className="watch-title">{o.title}</div>
                      <div className="muted small">Owner: {o.owner || ROLE_SHORT[o.owner_role]}, due {fmtDateTime(o.due_at)}{o.source_reference && `. ${o.source_reference}`}</div></div>
                    <DueBadge state={o.state} days={o.days_left} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          {app.checklist.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Document checklist</h2><span className="muted small">{app.checklist[0].source}</span></div>
              <table className="table compact">
                <tbody>{app.checklist.map((c) => (
                  <tr key={c.id}><td>{c.label}{!c.mandatory && <span className="muted small"> (if any)</span>}</td>
                    <td><StatusBadge status={c.status} /></td>
                    <td className="num">{c.file_id ? <button className="link small" onClick={() => api.download(`/files/${c.file_id}`, `${c.doc_code}.pdf`)}>Open</button> : <span className="muted small">{c.status === 'UPLOADED' ? 'seeded' : ''}</span>}</td></tr>
                ))}</tbody>
              </table>
            </section>
          )}

          {app.evc_visits.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Expert Visit Committee</h2><span className="muted small">APH cl. 1.9</span></div>
              {app.evc_visits.map((v) => (
                <div key={v.id} className="evc-box">
                  <div className="row gap center wrap"><StatusBadge status={v.status} />{v.priority_new_institution && <Badge tone="info" icon={false}>New institution, priority</Badge>}
                    {v.scheduled_on && <span>Visit on <strong>{fmtDate(v.scheduled_on)}</strong> ({v.mode.toLowerCase()})</span>}</div>
                  {v.panel?.length > 0 && <div className="small">Panel: {v.panel.map((p) => `${p.name} (${p.expertise}, ${p.home_state})`).join('; ')}</div>}
                  {v.report_outcome && <div className="small">Report by {v.report_submitted_by}: <strong>{v.report_outcome === 'CLEAR' ? 'Clear' : 'Deficiency found'}</strong>, {v.report_remarks}{v.video_minutes && ` Video: ${v.video_minutes} min.`}</div>}
                </div>
              ))}
            </section>
          )}

          {app.undertakings.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Time-bound requirements after approval</h2><Link to="/compliance?tab=undertakings" className="small">Compliance</Link></div>
              <table className="table compact"><tbody>
                {app.undertakings.map((u) => <tr key={u.id}><td>{u.title}<div className="muted small">{u.aph_reference}</div></td><td className="td-date">{fmtDate(u.due_on)}</td><td><StatusBadge status={u.status} /></td></tr>)}
              </tbody></table>
            </section>
          )}

          <section className="card">
            <div className="card-head"><h2>Case summary</h2><Badge tone="info" icon={false}>Advisory, system-generated</Badge></div>
            <pre className="summary">{app.summary}</pre>
            {app.decision_reason && <p><strong>Decision ({app.decision_ref}):</strong> {app.decision_reason}</p>}
          </section>
        </div>

        <section className="card">
          <div className="card-head">
            <h2>Audit trail</h2>
            <label className="check small"><input type="checkbox" checked={showSystem} onChange={(e) => setShowSystem(e.target.checked)} /> Show deadline bookkeeping</label>
          </div>
          {user.role !== 'INSTITUTION' && <p className="muted small">Append-only and hash-chained. Each entry's hash covers the previous one.</p>}
          <ol className="timeline">
            {events.slice().reverse().map((e) => (
              <li key={e.seq} className={`tl tl-${e.action.toLowerCase()}`}>
                <div className="tl-head"><strong>{ACTION_LABEL[e.action] || e.action}</strong><span className="muted small">{fmtDateTime(e.ts)}</span></div>
                <div className="small">{e.actor}</div>
                {e.reason && <div className="tl-reason">“{e.reason}”</div>}
                {e.detail && Object.keys(e.detail).length > 0 && (
                  <div className="tl-detail small muted">
                    {Object.entries(e.detail).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && !v.length)).slice(0, 5)
                      .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v).replace(/T\d\d:\d\d:\d\d(\+05:30)?/, '')}`).join(' · ')}
                  </div>
                )}
                {user.role !== 'INSTITUTION' && <div className="mono tiny muted" title={e.hash}>#{e.seq} · {e.hash.slice(0, 12)}…</div>}
              </li>
            ))}
          </ol>
        </section>
      </div>
      {action && <ActionDialog action={action} app={app} onClose={() => setAction(null)} />}
    </div>
  )
}
