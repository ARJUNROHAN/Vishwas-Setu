import { useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, newKey } from '../api'
import { useApp, useFetch } from '../app-context'
import { DueBadge, Empty, ErrorBox, EscBadge, FileInput, Loading, Modal, StatusBadge, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { fmtDate, STAGE_LABEL } from '../util'

function NewApplication({ onClose }) {
  const { notify, bump } = useApp()
  const nav = useNavigate()
  const { data } = useFetch('/application-types')
  const [code, setCode] = useState('EOA_SELF_DISCLOSURE')
  const [programme, setProgramme] = useState('')
  const [intake, setIntake] = useState('')
  const [docs, setDocs] = useState({})
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const key = useRef(newKey())
  if (!data) return <Modal title="New application" onClose={onClose}><Loading /></Modal>
  const types = data.types.filter((t) => t.initiated_by === 'INSTITUTION')
  const t = types.find((x) => x.code === code) || types[0]
  const missing = (t.checklist || []).filter((c) => c.mandatory && !docs[c.doc_code])
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await api.post('/applications', { application_type: t.code, programme, intake_requested: intake ? Number(intake) : null, documents: docs }, key.current)
      notify(`Application ${r.application_no} submitted for ${r.processing_academic_year}`); bump(); onClose(); nav(`/applications/${r.id}`)
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <Modal title="New application (AY 2027-28)" onClose={onClose} width={680}>
      <form onSubmit={submit}>
        <div className="field"><label>Category</label>
          <select value={t.code} onChange={(e) => { setCode(e.target.value); setDocs({}) }}>
            <optgroup label="Chapter I">{types.filter((x) => x.chapter === 'I').map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}</optgroup>
            <optgroup label="Chapter II, Table 2.3">{types.filter((x) => x.table_row).sort((x, y) => x.table_row - y.table_row).map((x) => <option key={x.code} value={x.code}>{x.table_row}. {x.label}</option>)}</optgroup>
            <optgroup label="Not mapped in Table 2.3">{types.filter((x) => x.chapter === 'II' && !x.table_row).map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}</optgroup>
          </select></div>
        <div className="hint">
          <strong>Route: {t.route.name}</strong>{' '}({t.route.stages.map((s) => s.name + (s.conditional ? ' if applicable' : '')).join(' → ')}).
          <div className="small">{t.route.source}. Submission: {t.notice_category === 'PUBLIC_NOTICE' ? 'within the public-notice window' : t.notice_category === 'ODL_CYCLE' ? 'within an ODL cycle' : 'year-round (cl. 2.22)'}.{t.note && ` ${t.note}.`}</div>
        </div>
        {['INCREASE_INTAKE', 'NEW_PROGRAMME_LEVEL', 'INTEGRATED_DUAL_DEGREE', 'DIPLOMA_DEGREE_CONVERSION', 'NEW_INSTITUTION'].includes(t.code) && (
          <div className="row gap">
            <div className="field grow"><label>Programme / course</label><input value={programme} onChange={(e) => setProgramme(e.target.value)} /></div>
            {t.code === 'INCREASE_INTAKE' && <div className="field"><label>Intake sought</label><input type="number" min="1" value={intake} onChange={(e) => setIntake(e.target.value)} /></div>}
          </div>
        )}
        {(t.checklist || []).length > 0 && (
          <div className="checklist-up">
            <div className="small muted">Document checklist: {t.checklist[0].source}</div>
            {t.checklist.map((c) => (
              <div key={c.doc_code} className="checklist-row">
                <span>{c.label}{!c.mandatory && <span className="muted"> (if any)</span>}</span>
                <FileInput label="" onUploaded={(ids) => setDocs((d) => ({ ...d, [c.doc_code]: ids[ids.length - 1] }))} />
              </div>
            ))}
          </div>
        )}
        {err && <div className="error">{err}</div>}
        <div className="row end gap"><button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || missing.length > 0} title={missing.length ? `${missing.length} mandatory document(s) missing` : ''}>Submit application</button></div>
      </form>
    </Modal>
  )
}

export default function Applications() {
  const { user } = useApp()
  const [params, setParams] = useSearchParams()
  const [showNew, setShowNew] = useState(false)
  const status = params.get('status') ?? (user.role === 'INSTITUTION' ? '' : 'ACTIVE')
  const stage = params.get('stage') || ''
  const type = params.get('type') || ''
  const overdue = params.get('overdue') === '1'
  const mine = params.get('mine') === '1'
  const [q, setQ] = useState(params.get('q') || '')
  const qs = new URLSearchParams({ ...(status && { status }), ...(stage && { stage }), ...(type && { app_type: type }), ...(overdue && { overdue: 'true' }), ...(mine && { mine: 'true' }) })
  const { data, error, loading } = useFetch(`/applications?${qs}`)
  const { data: meta } = useFetch('/meta')
  const set = (k, v) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); if (k === 'status' && !v) p.set('status', ''); setParams(p) }
  const rows = useMemo(() => (data || []).filter((r) => !q || `${r.application_no} ${r.institution}`.toLowerCase().includes(q.toLowerCase())), [data, q])

  return (
    <div>
      <PageHeader title={user.role === 'INSTITUTION' ? 'My applications' : 'Applications'} crumbs={[`List (${rows.length})`]}
        actions={user.role === 'INSTITUTION' && meta && <button className="btn primary" onClick={() => setShowNew(true)}><Icon name="plus" size={14} /> New application</button>} />
      <ErrorBox error={error} />
      <section className="card flush list-card">
      <div className="card-toolbar">
        <div className="toolbar-search"><Icon name="search" size={15} /><input placeholder="Search application no. or institution" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select value={status} onChange={(e) => set('status', e.target.value)} aria-label="Status">
          <option value="">All statuses</option><option value="ACTIVE">Active (all)</option>
          <option value="IN_PROGRESS">In processing</option><option value="RETURNED">Returned to institution</option>
          <option value="READY_FOR_DECISION">Awaiting decision</option><option value="APPROVED">Approved</option>
          <option value="REJECTED">Not approved</option><option value="UNDER_APPEAL">Under appeal</option>
        </select>
        <select value={stage} onChange={(e) => set('stage', e.target.value)} aria-label="Stage">
          <option value="">All stages</option>
          {['SELF_DISCLOSURE', 'SCRUTINY', 'RE_SCRUTINY', 'EVC', 'SHC', 'SAC', 'RULE_REVIEW'].map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
        </select>
        {meta && (
          <select value={type} onChange={(e) => set('type', e.target.value)} aria-label="Type">
            <option value="">All types</option>
            {Object.entries(meta.application_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        )}
        <label className="check"><input type="checkbox" checked={overdue} onChange={(e) => set('overdue', e.target.checked ? '1' : '')} /> Overdue only</label>
        {user.role !== 'INSTITUTION' && <label className="check"><input type="checkbox" checked={mine} onChange={(e) => set('mine', e.target.checked ? '1' : '')} /> Assigned to me</label>}
      </div>
      {loading && !data ? <Loading /> : rows.length === 0 ? <Empty>No applications match these filters.</Empty> : (
          <table className="table">
            <thead><tr><th>Application</th><th>Institution</th><th>Type · route</th><th>Status</th><th>Current stage</th><th className="num">Age</th><th>Next deadline</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><Link to={`/applications/${r.id}`} className="mono">{r.application_no}</Link><div className="muted small">{fmtDate(r.submitted_at)}</div></td>
                  <td>{r.institution}<div className="muted small">{r.region} Region</div></td>
                  <td>{r.type_label}<div className="muted small">{r.route}</div></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{r.stage_name || '—'}{r.assignee && <div className="muted small">{r.assignee}</div>}</td>
                  <td className="num">{r.age_days} d</td>
                  <td>{r.next_due_state ? <div className="row gap center"><DueBadge state={r.next_due_state} /><EscBadge level={r.escalation_level} /></div> : <span className="muted">—</span>}
                    {r.next_due_at && r.next_due_state !== 'PAUSED' && <div className="muted small">{fmtDate(r.next_due_at)}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
      )}
      </section>
      {showNew && <NewApplication onClose={() => setShowNew(false)} />}
    </div>
  )
}
