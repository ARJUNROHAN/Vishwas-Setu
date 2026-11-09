import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp, useFetch } from '../app-context'
import { ActionForm, Empty, ErrorBox, EscBadge, FileInput, Loading, StatusBadge, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { daysText, fmtDate } from '../util'

function EvidenceDialog({ u, onClose }) {
  const [ids, setIds] = useState([])
  return (
    <ActionForm title={`Submit evidence — ${u.title}`} submitLabel="Submit for verification" onClose={onClose}
      remarksLabel="Describe the evidence" extraValid={ids.length > 0}
      onSubmit={(remarks, key) => api.post(`/undertakings/${u.id}/evidence`, { remarks, file_ids: ids }, key)}>
      <p className="hint">{u.condition_text}</p>
      <FileInput onUploaded={setIds} />
    </ActionForm>
  )
}

function VerifyDialog({ title, path, onClose, children }) {
  const [accept, setAccept] = useState(true)
  return (
    <ActionForm title={title} submitLabel={accept ? 'Mark verified' : 'Reject with remarks'} tone={accept ? 'primary' : 'danger'}
      onClose={onClose} onSubmit={(remarks, key) => api.post(path, { accept, remarks }, key)}>
      {children}
      <div className="row gap">
        <label className="check"><input type="radio" checked={accept} onChange={() => setAccept(true)} /> Verified against originals</label>
        <label className="check"><input type="radio" checked={!accept} onChange={() => setAccept(false)} /> Not acceptable</label>
      </div>
    </ActionForm>
  )
}

function DocDialog({ d, onClose, today }) {
  const isNew = !d.id
  const [from, setFrom] = useState(today)
  const [until, setUntil] = useState('')
  const [issuer, setIssuer] = useState('')
  const [ref, setRef] = useState('')
  const [ids, setIds] = useState([])
  return (
    <ActionForm title={isNew ? `Upload ${d.title}` : `Submit renewed ${d.title}`} submitLabel="Submit for verification" requireRemarks={false}
      remarksLabel="Remarks (optional)" onClose={onClose} extraValid={ids.length > 0 && !!until}
      onSubmit={(remarks, key) => isNew
        ? api.post('/documents', { doc_type: d.doc_type, valid_from: from, valid_until: until, file_id: ids[0], issuer_name: issuer, reference_no: ref }, key)
        : api.post(`/documents/${d.id}/renew`, { valid_from: from, valid_until: until, file_id: ids[0], remarks, issuer_name: issuer, reference_no: ref }, key)}>
      {d.doc_type === 'LAND_LEASE' && <p className="hint">APH cl. 2.1(e): EoA is not issued once the live lease equals the longest course duration. A renewal should extend the lease by 30 years with at least 25 years live.</p>}
      {d.doc_type === 'STABILITY_CERT' && <p className="hint">Required for buildings older than 30 years (Annexure 2). Validity is 5 years from issue (Ch. VI).</p>}
      <div className="row gap">
        <div className="field grow"><label>{d.doc_type === 'LAND_LEASE' ? 'Lease start' : 'Issue date'}</label><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} required /></div>
        <div className="field grow"><label>{d.doc_type === 'LAND_LEASE' ? 'Lease end' : 'Valid until'}</label><input type="date" value={until} min={d.valid_until || from} onChange={(e) => setUntil(e.target.value)} required /></div>
      </div>
      <div className="row gap">
        <div className="field grow"><label>Issuer</label><input value={issuer} onChange={(e) => setIssuer(e.target.value)} placeholder="e.g. Sub-Registrar / Fire Services" /></div>
        <div className="field grow"><label>Reference / registration no.</label><input value={ref} onChange={(e) => setRef(e.target.value)} /></div>
      </div>
      <FileInput label="Document" onUploaded={setIds} />
    </ActionForm>
  )
}

export default function Compliance() {
  const { user, clock } = useApp()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'undertakings'
  const { data: unds, error: e1 } = useFetch('/undertakings')
  const { data: docs, error: e2 } = useFetch('/documents')
  const [dlg, setDlg] = useState(null)
  const [filter, setFilter] = useState('attention')
  const inst = user.role === 'INSTITUTION'
  const officer = user.role === 'SCRUTINY_OFFICER'
  const today = clock?.now?.slice(0, 10)

  const undRows = (unds || []).filter((u) => filter === 'all' || (filter === 'attention' ? u.status !== 'VERIFIED' : u.status === filter))
  const docRows = (docs || []).filter((d) => filter === 'all' || (filter === 'attention' ? !['VALID', 'SUPERSEDED'].includes(d.status) : d.status === filter))

  return (
    <div>
      <PageHeader title={inst ? 'Undertakings & documents' : 'Compliance'} crumbs={[tab === 'documents' ? 'Lease & documents' : 'Undertakings']}>
        Time-bound requirements attached to approvals, and validity of prescribed documents.</PageHeader>
      <div className="tabs">
        <button className={tab === 'undertakings' ? 'active' : ''} onClick={() => setParams({ tab: 'undertakings' })}>Undertakings {unds && `(${unds.filter((u) => u.status !== 'VERIFIED').length})`}</button>
        <button className={tab === 'documents' ? 'active' : ''} onClick={() => setParams({ tab: 'documents' })}>Lease &amp; documents {docs && `(${docs.filter((d) => !['VALID', 'SUPERSEDED'].includes(d.status)).length})`}</button>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter" className="tabs-filter">
          <option value="attention">Needs attention</option><option value="all">All</option>
          {tab === 'undertakings' ? ['OPEN', 'SUBMITTED', 'LAPSED', 'VERIFIED', 'REJECTED'].map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)
            : ['MISSING', 'AWAITING_VERIFICATION', 'EXPIRED', 'LEASE_REVIEW_REQUIRED', 'EXPIRING_SOON', 'VALID'].map((s) => <option key={s} value={s}>{s.replaceAll('_', ' ').toLowerCase()}</option>)}
        </select>
      </div>
      <ErrorBox error={e1 || e2} />
      {tab === 'undertakings' && (!unds ? <Loading /> : undRows.length === 0 ? <Empty>Nothing here.</Empty> : (
        <section className="card flush">
          <table className="table">
            <thead><tr>{!inst && <th>Institution</th>}<th>Requirement</th><th>Due</th><th>Status</th><th /></tr></thead>
            <tbody>
              {undRows.map((u) => (
                <tr key={u.id}>
                  {!inst && <td>{u.institution}<div className="muted small">{u.region} Region</div></td>}
                  <td><strong>{u.title}</strong><div className="muted small">{u.aph_reference}{u.source_document && `. Source: ${u.source_document}`}{u.application_id && <> · <Link to={`/applications/${u.application_id}`}>application</Link></>}</div>
                    {u.remarks && <div className="small">“{u.remarks}”</div>}</td>
                  <td>{fmtDate(u.due_on)}<div className={`small ${u.days_left < 0 && !['VERIFIED', 'SUBMITTED'].includes(u.status) ? 'txt-critical' : 'muted'}`}>{['VERIFIED'].includes(u.status) ? '' : daysText(u.days_left)}</div></td>
                  <td><div className="row gap center"><StatusBadge status={u.status} /><EscBadge level={u.escalation_level} />{u.was_late && <span className="badge badge-warning">Late</span>}</div></td>
                  <td className="num">
                    {inst && ['OPEN', 'REJECTED', 'LAPSED'].includes(u.status) && <button className="btn primary small" onClick={() => setDlg({ t: 'evidence', u })}>Submit evidence</button>}
                    {officer && u.status === 'SUBMITTED' && <button className="btn primary small" onClick={() => setDlg({ t: 'verifyU', u })}>Verify</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {tab === 'documents' && (!docs ? <Loading /> : docRows.length === 0 ? <Empty>Nothing here.</Empty> : (
        <section className="card flush">
          <table className="table">
            <thead><tr>{!inst && <th>Institution</th>}<th>Document</th><th>Valid until</th><th>Renew by</th><th>Status</th><th /></tr></thead>
            <tbody>
              {docRows.map((d) => (
                <tr key={d.id ?? `m-${d.institution_id}-${d.doc_type}`}>
                  {!inst && <td>{d.institution}<div className="muted small">{d.region} Region</div></td>}
                  <td><strong>{d.title}</strong><div className="muted small">{d.status === 'MISSING' ? 'Required but not on record' : `Version ${d.version}`}{d.source && ` · ${d.source}`}</div></td>
                  <td className="td-date">{d.valid_until ? fmtDate(d.valid_until) : '—'}</td>
                  <td className="td-date">{d.renew_by ? fmtDate(d.renew_by) : '—'}<div className={`small ${d.days_to_renew_by < 0 ? 'txt-critical' : 'muted'}`}>{['AWAITING_VERIFICATION', 'RENEWAL_SUBMITTED', 'MISSING'].includes(d.status) ? '' : daysText(d.days_to_renew_by)}</div></td>
                  <td><div className="row gap center"><StatusBadge status={d.status} /><EscBadge level={d.escalation_level} /></div></td>
                  <td className="num">
                    {inst && d.status === 'MISSING' && <button className="btn primary small" onClick={() => setDlg({ t: 'renew', d })}>Upload document</button>}
                    {inst && ['EXPIRED', 'LEASE_REVIEW_REQUIRED', 'EXPIRING_SOON', 'VALID'].includes(d.status) && <button className={`btn ${d.status === 'VALID' ? 'ghost' : 'primary'} small`} onClick={() => setDlg({ t: 'renew', d })}>Upload renewal</button>}
                    {officer && d.status === 'AWAITING_VERIFICATION' && <button className="btn primary small" onClick={() => setDlg({ t: 'verifyD', d })}>Verify</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      {dlg?.t === 'evidence' && <EvidenceDialog u={dlg.u} onClose={() => setDlg(null)} />}
      {dlg?.t === 'verifyU' && <VerifyDialog title={`Verify evidence — ${dlg.u.institution}`} path={`/undertakings/${dlg.u.id}/verify`} onClose={() => setDlg(null)}>
        <p className="hint">{dlg.u.condition_text}</p>
        {dlg.u.evidence_file_ids.map((f) => <button type="button" key={f} className="link" onClick={() => api.download(`/files/${f}`, `evidence-${f}`)}><Icon name="file" size={14} /> Open evidence #{f}</button>)}
      </VerifyDialog>}
      {dlg?.t === 'renew' && <DocDialog d={dlg.d} today={today} onClose={() => setDlg(null)} />}
      {dlg?.t === 'verifyD' && <VerifyDialog title={`Verify renewed ${dlg.d.title}`} path={`/documents/${dlg.d.id}/verify`} onClose={() => setDlg(null)}>
        <p className="muted small">{dlg.d.institution} · valid {fmtDate(dlg.d.valid_from)} to {fmtDate(dlg.d.valid_until)}</p>
        {dlg.d.file_id && <button type="button" className="link" onClick={() => api.download(`/files/${dlg.d.file_id}`, `document-${dlg.d.id}`)}><Icon name="file" size={14} /> Open submitted document</button>}
        {dlg.d.checks && (
          <div className="checks"><div className="small muted">Advisory checks (the decision is yours):</div>
            {dlg.d.checks.map((c) => <div key={c.check} className={`check-row ${c.ok ? 'ok' : 'bad'}`}><Icon name={c.ok ? 'check' : 'x'} size={14} /> {c.check}: {c.value} <span className="muted">({c.source})</span></div>)}</div>
        )}
      </VerifyDialog>}
    </div>
  )
}
