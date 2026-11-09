import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApp, useFetch } from '../app-context'
import { ActionForm, Badge, DueBadge, Empty, ErrorBox, EscBadge, FileInput, Loading, StatusBadge, PageHeader } from '../components/ui'
import { fmtDate } from '../util'

function ScheduleDialog({ visit, onClose, today }) {
  const [date, setDate] = useState(today)
  const [mode, setMode] = useState('PHYSICAL')
  const [panel, setPanel] = useState(visit.panel || [])
  const [warnings, setWarnings] = useState([])
  const [err, setErr] = useState(null)
  const draw = async () => {
    setErr(null)
    try { const r = await api.get(`/evc/${visit.id}/panel?on=${date}`); setPanel(r.panel); setWarnings(r.warnings) } catch (e) { setErr(e.message) }
  }
  return (
    <ActionForm title={`Schedule EVC — ${visit.application_no}`} submitLabel="Schedule visit" requireRemarks={false}
      remarksLabel="Note to institution (optional)" onClose={onClose} extraValid={panel.length >= 3}
      onSubmit={(_, key) => api.post(`/evc/${visit.id}/schedule`, { date, panel, mode }, key)}>
      <p className="muted small">{visit.institution} · {visit.institution_state}</p>
      <div className="row gap">
        <div className="field grow"><label>Visit date</label><input type="date" min={today} value={date} onChange={(e) => { setDate(e.target.value); setPanel([]) }} required /></div>
        <div className="field grow"><label>Mode</label><select value={mode} onChange={(e) => setMode(e.target.value)}><option value="PHYSICAL">Physical</option><option value="ONLINE">Online</option></select></div>
      </div>
      <div className="field">
        <label>Expert panel (3 members)</label>
        <button type="button" className="btn ghost small" onClick={draw}>{panel.length ? 'Redraw panel' : 'Draw panel from approved experts'}</button>
        <p className="muted small">Random draw excludes experts from the institution’s state (conflict of interest) and experts with another visit that day.</p>
        {panel.map((p) => <div key={p.id} className="file-chip">👤 {p.name} — {p.expertise}, {p.organisation}</div>)}
        {warnings.map((w) => <div key={w} className="hint">{w}</div>)}
        {err && <div className="error small">{err}</div>}
      </div>
    </ActionForm>
  )
}

function ReportDialog({ visit, onClose }) {
  const [outcome, setOutcome] = useState('CLEAR')
  const [fileIds, setFileIds] = useState([])
  const [videoUrl, setVideoUrl] = useState('')
  const [minutes, setMinutes] = useState('')
  const online = visit.mode === 'ONLINE'
  return (
    <ActionForm title={`Submit EVC report: ${visit.application_no}`} submitLabel="Submit report" onClose={onClose}
      remarksLabel="Committee observations (instructional, administrative, amenities, laboratory, documents, faculty)"
      extraValid={fileIds.length > 0 && (!online || (videoUrl && Number(minutes) >= 30))}
      onSubmit={(remarks, key) => api.post(`/evc/${visit.id}/report`, { outcome, remarks, file_id: fileIds[0], video_url: online ? videoUrl : null, video_minutes: online ? Number(minutes) : null }, key)}>
      <p className="hint">Readiness is verified per APH cl. 1.9. You are submitting as an assigned panel member.</p>
      <div className="field"><label>Finding</label>
        <div className="row gap">
          <label className="check"><input type="radio" checked={outcome === 'CLEAR'} onChange={() => setOutcome('CLEAR')} /> Clear</label>
          <label className="check"><input type="radio" checked={outcome === 'DEFICIENCY_FOUND'} onChange={() => setOutcome('DEFICIENCY_FOUND')} /> Deficiency found (goes to SHC where applicable)</label>
        </div>
      </div>
      {online && (
        <div className="row gap">
          <div className="field grow"><label>Facilities video link</label><input type="url" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} placeholder="https://" required /></div>
          <div className="field"><label>Duration (min, at least 30)</label><input type="number" min="30" value={minutes} onChange={(e) => setMinutes(e.target.value)} required /></div>
        </div>
      )}
      <FileInput label="Signed EVC report (PDF)" onUploaded={setFileIds} />
    </ActionForm>
  )
}

export default function EvcQueue() {
  const { user, clock } = useApp()
  const { data, error, loading } = useFetch('/evc')
  const [dlg, setDlg] = useState(null)
  const today = clock?.now?.slice(0, 10)
  const isCoord = user.role === 'EVC_COORDINATOR'
  const isMember = user.role === 'EVC_MEMBER'
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const queued = data.filter((v) => v.status === 'QUEUED')
  const scheduled = data.filter((v) => v.status === 'SCHEDULED')

  const table = (rows, kind) => (
    <table className="table">
      <thead><tr><th>Application</th><th>Institution</th><th>Type</th>{kind === 'scheduled' && <th>Visit</th>}<th>Deadline</th>{(isCoord || isMember) && <th />}</tr></thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.id}>
            <td><Link className="mono" to={`/applications/${v.application_id}`}>{v.application_no}</Link>
              {v.priority_new_institution && <div><Badge tone="info" icon={false}>New institution</Badge></div>}</td>
            <td>{v.institution}<div className="muted small">{v.region} Region</div></td>
            <td className="small">{v.type_label}</td>
            {kind === 'scheduled' && <td><strong>{fmtDate(v.scheduled_on)}</strong><div className="muted small">{v.mode.toLowerCase()} · {v.panel.length} experts</div></td>}
            <td>{v.obligation ? <div className="row gap center"><DueBadge state={v.obligation.state} days={v.obligation.days_left} /><EscBadge level={v.obligation.escalation_level} /></div> : '—'}</td>
            {(isCoord || isMember) && <td className="num">
              {isCoord && kind === 'queued' && <button className="btn primary small" onClick={() => setDlg({ type: 'schedule', v })}>Schedule</button>}
              {isCoord && kind === 'scheduled' && <button className="btn ghost small" onClick={() => setDlg({ type: 'schedule', v })}>Reschedule</button>}
              {isMember && v.can_report && kind === 'scheduled' && <button className="btn primary small" disabled={today < v.scheduled_on} title={today < v.scheduled_on ? 'Available on or after the visit date' : ''} onClick={() => setDlg({ type: 'report', v })}>Submit report</button>}
            </td>}
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <div>
      <PageHeader title={isMember ? 'My EVC visits' : 'EVC queue'} crumbs={['Expert Visit Committee']}
        actions={<div className="row gap center"><StatusBadge status="QUEUED" /> <strong>{queued.length}</strong> <StatusBadge status="SCHEDULED" /> <strong>{scheduled.length}</strong></div>}>{isMember ? 'Visits on panels you sit on. Reports can be submitted on or after the visit date; online visits need a recording of at least 30 minutes (APH cl. 1.9).' : 'Applications enter automatically once preliminary processing completes. New institutions are prioritised.'}</PageHeader>
      {!isMember && <section className="card flush"><div className="card-head pad"><h2>To be scheduled</h2></div>
        {queued.length ? table(queued, 'queued') : <Empty>No applications waiting for an EVC.</Empty>}</section>}
      <section className="card flush"><div className="card-head pad"><h2>Scheduled — awaiting report</h2></div>
        {scheduled.length ? table(scheduled, 'scheduled') : <Empty>No scheduled visits.</Empty>}</section>
      {dlg?.type === 'schedule' && <ScheduleDialog visit={dlg.v} today={today} onClose={() => setDlg(null)} />}
      {dlg?.type === 'report' && <ReportDialog visit={dlg.v} onClose={() => setDlg(null)} />}
    </div>
  )
}
