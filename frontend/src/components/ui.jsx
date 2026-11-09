import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from './Icon'
import { api, newKey } from '../api'
import { useApp } from '../app-context'
import { daysText, KIND_LABEL, stateTone, STATUS_LABEL } from '../util'

/* Soft badges as in the template: tinted background, coloured text.
   A status glyph is opt-in (icon={true}); the template shows none by default. */
const STATE_ICON = { critical: 'alert', warning: 'clock', good: 'check', paused: 'pause', neutral: 'circle', info: 'info' }

export function Badge({ tone = 'neutral', children, icon = false }) {
  return (
    <span className={`badge badge-${tone}`}>
      {icon && <Icon name={STATE_ICON[tone] || 'circle'} size={12} className="badge-icon" />}
      {children}
    </span>
  )
}

/* Template page header: "Title | Home > Crumb" on the left, actions on the right (65px bar).
   An optional description renders as a muted line at the top of the page body. */
export function PageHeader({ title, crumbs = [], actions, children }) {
  return (
    <>
      <div className="page-head">
        <div className="page-head-left">
          <h1>{title}</h1>
          <ol className="crumbs" aria-label="Breadcrumb">
            <li><Link to="/">Home</Link></li>
            {crumbs.map((c, i) => (
              <Fragment key={i}>
                <li className="crumb-sep" aria-hidden="true"><Icon name="chevron" size={12} /></li>
                <li>{c && c.to ? <Link to={c.to}>{c.label}</Link> : c}</li>
              </Fragment>
            ))}
          </ol>
        </div>
        {actions && <div className="page-head-right">{actions}</div>}
      </div>
      {children && <div className="page-desc">{children}</div>}
    </>
  )
}

export function DueBadge({ state, days }) {
  const label = { OVERDUE: 'Overdue', DUE_SOON: 'Due soon', UPCOMING: 'On track', PAUSED: 'Clock paused', CLOSED: 'Closed' }[state] || state
  return <Badge tone={stateTone(state)}>{label}{days != null && state !== 'PAUSED' && state !== 'CLOSED' ? ` · ${daysText(days)}` : ''}</Badge>
}

export function StatusBadge({ status }) {
  const tone = { APPROVED: 'good', REJECTED: 'critical', RETURNED: 'warning', READY_FOR_DECISION: 'info',
    UNDER_APPEAL: 'warning', VERIFIED: 'good', SUBMITTED: 'info', OPEN: 'neutral', LAPSED: 'critical',
    MISSING: 'critical', LEASE_REVIEW_REQUIRED: 'critical', RENEWAL_SUBMITTED: 'info', RESPONDED: 'info', RESOLVED: 'good',
    NOT_RESOLVED: 'critical', UPLOADED: 'good', CLEAR: 'good', DEFICIENCY_FOUND: 'warning', ACTIVE: 'good', RETIRED: 'neutral',
    AWAITING_VERIFICATION: 'info', EXPIRED: 'critical', RENEWAL_OVERDUE: 'critical', EXPIRING_SOON: 'warning',
    VALID: 'good', SUPERSEDED: 'neutral', QUEUED: 'warning', SCHEDULED: 'info', REPORT_SUBMITTED: 'good' }[status] || 'neutral'
  const label = STATUS_LABEL[status] || status.replaceAll('_', ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())
  return <Badge tone={tone}>{label}</Badge>
}

export function EscBadge({ level }) {
  if (!level) return null
  return <span className="esc" title={`Escalated to level ${level}`}>L{level}</span>
}

export function Kind({ kind }) { return <span className="kind">{KIND_LABEL[kind] || kind}</span> }

export function Modal({ title, onClose, children, width = 560 }) {
  const ref = useRef(null)
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    ref.current?.querySelector('textarea, input, select, button')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: width }} ref={ref} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head"><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" size={18} /></button></div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

export function FileInput({ onUploaded, label = 'Attach document (PDF/JPG/PNG, max 10 MB)' }) {
  const [busy, setBusy] = useState(false)
  const [files, setFiles] = useState([])
  const [err, setErr] = useState(null)
  const pick = async (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setBusy(true); setErr(null)
    try {
      const r = await api.upload(f)
      const next = [...files, r]
      setFiles(next); onUploaded(next.map((x) => x.id))
    } catch (ex) { setErr(ex.message) } finally { setBusy(false); e.target.value = '' }
  }
  return (
    <div className="field">
      <label>{label}</label>
      <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={pick} disabled={busy} />
      {busy && <div className="muted small">Uploading and scanning…</div>}
      {files.map((f) => <div key={f.id} className="file-chip"><Icon name="file" size={14} /> {f.name} <span className="muted mono">sha256 {f.sha256.slice(0, 10)}…</span></div>)}
      {err && <div className="error small">{err}</div>}
    </div>
  )
}

export function ActionForm({ title, submitLabel, onSubmit, onClose, children, requireRemarks = true,
  remarksLabel = 'Remarks (recorded in the audit trail)', tone = 'primary', extraValid = true }) {
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const key = useRef(newKey())
  const { notify, bump } = useApp()
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try { await onSubmit(remarks, key.current); bump(); notify('Saved'); onClose() } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit}>
        {children}
        <div className="field">
          <label>{remarksLabel}</label>
          <textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} required={requireRemarks} />
        </div>
        {err && <div className="error">{err}</div>}
        <div className="row end gap">
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className={`btn ${tone}`} disabled={busy || !extraValid}>{busy ? 'Saving…' : submitLabel}</button>
        </div>
      </form>
    </Modal>
  )
}

export function Empty({ children }) { return <div className="empty">{children}</div> }

export function Loading() { return <div className="loading">Loading…</div> }

export function ErrorBox({ error }) { return error ? <div className="error">{error}</div> : null }

export function Kpi({ label, value, tone, sub, onClick }) {
  return (
    <button className={`kpi ${tone ? `kpi-${tone}` : ''} ${onClick ? 'clickable' : ''}`} onClick={onClick} disabled={!onClick}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </button>
  )
}
