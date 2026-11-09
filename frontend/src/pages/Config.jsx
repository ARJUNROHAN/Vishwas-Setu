import { useState } from 'react'
import { api } from '../api'
import { useFetch } from '../app-context'
import { ActionForm, Badge, ErrorBox, Loading, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { fmtDate, KIND_LABEL, ROLE_SHORT } from '../util'

const SRC_TONE = { APH: 'success', REGULATION: 'info', DESIGN: 'neutral' }
const Src = ({ t }) => <Badge tone={SRC_TONE[t] || 'neutral'} icon={false}>{t === 'DESIGN' ? 'Design default' : t}</Badge>

const DEF_LABEL = (r) => !r ? '—' : r === 'RETURN' ? 'Return to institution, same stage again'
  : r.startsWith('RETURN_THEN:') ? `Return to institution, then ${r.split(':')[1].replace('_', '-')}`
    : r.startsWith('GOTO:') ? `Go to ${r.split(':')[1]}` : 'Place for decision, not recommended'

function StageEdit({ s, onClose }) {
  const [sla, setSla] = useState(s.sla_days)
  return (
    <ActionForm title={`Time limit: ${s.name}`} submitLabel="Publish new ruleset version" remarksLabel="Reason / authority for change (e.g. circular no.)"
      onClose={onClose} onSubmit={(reason) => api.put(`/config/stages/${s.id}`, { sla_days: Number(sla), reason })}>
      <div className="field"><label>Calendar days</label><input type="number" min="1" max="120" value={sla} onChange={(e) => setSla(e.target.value)} /></div>
      <p className="hint">Saving publishes a new ruleset version. Applications already submitted stay pinned to the version they were submitted under; only new submissions use the new value.</p>
    </ActionForm>
  )
}

function PolicyEdit({ p, onClose }) {
  const [rem, setRem] = useState(p.reminder_offsets_days.join(', '))
  const [steps, setSteps] = useState(p.escalation_steps)
  return (
    <ActionForm title={`Alerts & escalation — ${p.name}`} submitLabel="Save" remarksLabel="Reason / authority for change" onClose={onClose}
      onSubmit={(reason, key) => api.put(`/config/policies/${p.id}`, { reminder_offsets_days: rem.split(',').map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x)), escalation_steps: steps, reason })}>
      <div className="field"><label>Reminder offsets (days before due, comma-separated)</label><input value={rem} onChange={(e) => setRem(e.target.value)} /></div>
      {steps.map((st, i) => (
        <div key={i} className="row gap">
          <div className="field"><label>Level</label><input value={st.level} disabled /></div>
          <div className="field grow"><label>Days after due</label><input type="number" min="0" value={st.after_days}
            onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, after_days: Number(e.target.value) } : x))} /></div>
          <div className="field grow"><label>Escalate to</label>
            <select value={st.to_role} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, to_role: e.target.value } : x))}>
              {Object.entries(ROLE_SHORT).filter(([k]) => k !== 'INSTITUTION').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
        </div>
      ))}
    </ActionForm>
  )
}

const COND = { always: 'Always', optional: 'Optional', building_over_30: 'If building > 30 years old', land_leased: 'If land is leased' }

export default function Config() {
  const { data, error, loading } = useFetch('/config')
  const [dlg, setDlg] = useState(null)
  const [tab, setTab] = useState('routes')
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const rs = data.ruleset
  const routeName = Object.fromEntries(data.routes.map((r) => [r.code, r.name]))
  return (
    <div>
      <PageHeader title="Rules & timelines" crumbs={[`${rs.code} v${rs.version}`]}
        actions={rs.source_url && <a className="btn ghost" href={rs.source_url} target="_blank" rel="noreferrer"><Icon name="file" size={14} /> APH source</a>}>
        Active ruleset <strong>{rs.code} v{rs.version}</strong> ({rs.aph_edition}). {data.can_edit ? 'Edits publish a new version; submitted applications stay pinned to theirs.' : 'Read-only for your role. Rule administrators publish changes.'}</PageHeader>
      <p className="hint">Every value carries its source: <Src t="APH" /> from the Approval Process Handbook, <Src t="REGULATION" /> from the Approval Regulations, <Src t="DESIGN" /> a prototype default the APH does not fix. Verify page references against the official PDF.</p>
      <div className="tabs">
        {[['routes', 'Routes'], ['types', 'Table 2.3 matrix'], ['checklists', 'Checklists'], ['calendars', 'Academic calendar'], ['policies', 'Alerts & escalation'], ['settings', 'Settings'], ['versions', 'Versions']].map(([k, v]) =>
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{v}</button>)}
      </div>

      {tab === 'routes' && data.routes.map((r) => (
        <section key={r.id} className="card">
          <div className="card-head"><h2>{r.name}</h2><span className="row gap center"><Src t={r.source_type} /><span className="muted small">{r.aph_reference}</span></span></div>
          <p className="small">{r.description}</p>
          <table className="table compact">
            <thead><tr><th>#</th><th>Stage</th><th>Handled by</th><th className="num">Time limit</th><th>On deficiency</th><th /></tr></thead>
            <tbody>
              {r.stages.map((s) => (
                <tr key={s.id}>
                  <td>{s.order}</td>
                  <td>{s.name} {s.conditional && <Badge tone="neutral" icon={false}>only if deficiency</Badge>}</td>
                  <td className="small">{ROLE_SHORT[s.assignee_role] || s.assignee_role}{s.managed_by === 'evc' && ' (via EVC report)'}</td>
                  <td className="num">{s.sla_days} days</td>
                  <td className="small">{DEF_LABEL(s.on_deficiency)}</td>
                  <td className="num">{data.can_edit && <button className="btn ghost small" onClick={() => setDlg({ t: 's', s })}>Edit</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      {tab === 'types' && (
        <section className="card flush">
          <table className="table compact">
            <thead><tr><th>Chapter / row</th><th>Application type</th><th>Route</th><th>Notice (Table 2.2)</th><th>Checklist</th><th>Initiated by</th></tr></thead>
            <tbody>
              {data.application_types.map((t) => (
                <tr key={t.code}>
                  <td className="small nowrap">{t.chapter}{t.table_row ? ` · row ${t.table_row}` : ''}</td>
                  <td>{t.label}{t.note && <div className="muted small">{t.note}</div>}</td>
                  <td className="small">{routeName[t.route_code] || t.route_code}</td>
                  <td className="small">{t.notice_category || '—'} {t.notice_category && !t.notice_verified && <Badge tone="warning" icon={false}>verify</Badge>}</td>
                  <td className="small">{t.checklist_code || '—'}</td>
                  <td className="small">{t.initiated_by === 'AICTE' ? 'AICTE' : 'Institution'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'checklists' && Object.entries(data.checklists).map(([code, items]) => (
        <section key={code} className="card">
          <div className="card-head"><h2>{code}</h2><span className="muted small">{items.length} items</span></div>
          <table className="table compact"><thead><tr><th>Document</th><th>Required</th><th>Source</th></tr></thead><tbody>
            {items.map((d) => <tr key={d.doc_code}><td>{d.label}</td><td className="small">{COND[d.condition] || d.condition}</td><td className="small muted">{d.source}</td></tr>)}
          </tbody></table>
        </section>
      ))}

      {tab === 'calendars' && (
        <section className="card flush">
          <table className="table compact">
            <thead><tr><th>Academic year</th><th>Application window</th><th>ODL / Online cycles</th><th>Notice</th></tr></thead>
            <tbody>{data.calendars.map((c) => (
              <tr key={c.academic_year}>
                <td><strong>{c.academic_year}</strong></td>
                <td className="small">{fmtDate(c.application_open)} to {fmtDate(c.application_close)}</td>
                <td className="small">{(c.odl_cycles || []).map((o) => `${o.cycle}: ${fmtDate(o.open)} to ${fmtDate(o.close)}`).join('; ') || '—'}</td>
                <td className="small muted">{c.notice_ref}</td>
              </tr>))}
            </tbody>
          </table>
          <p className="hint pad">Applications are assigned the academic year whose window contains the submission date (APH cl. 2.22). Dates are illustrative and should be replaced with the notified schedule.</p>
        </section>
      )}

      {tab === 'policies' && (
        <section className="card">
          <table className="table compact">
            <thead><tr><th>Deadline kind</th><th>Reminders before due</th><th>Escalation</th><th /></tr></thead>
            <tbody>
              {data.policies.map((p) => (
                <tr key={p.id}>
                  <td>{KIND_LABEL[p.kind] || p.name}</td>
                  <td className="small">{p.reminder_offsets_days.map((d) => `T−${d}`).join(', ') || '—'}, T+0, T+1</td>
                  <td className="small">{p.escalation_steps.map((s) => `L${s.level}: ${ROLE_SHORT[s.to_role] || s.to_role} after ${s.after_days} day(s)`).join(' → ') || 'None'}</td>
                  <td className="num">{data.can_edit && <button className="btn ghost small" onClick={() => setDlg({ t: 'p', p })}>Edit</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">Deadlines are calendar days and fall due at 17:30 IST. Reminder and escalation timings are prototype defaults; the APH does not prescribe them.</p>
        </section>
      )}

      {tab === 'settings' && (
        <section className="card flush">
          <table className="table compact"><thead><tr><th>Setting</th><th className="num">Value</th><th>Source</th></tr></thead><tbody>
            {data.settings.map((s) => (
              <tr key={s.key}><td>{s.key.replaceAll('_', ' ')}</td>
                <td className="num">{Array.isArray(s.value) ? s.value.join(', ') : String(s.value)} {s.unit}</td>
                <td className="small"><Src t={s.source_type} /> <span className="muted">{s.source}</span></td></tr>))}
          </tbody></table>
        </section>
      )}

      {tab === 'versions' && (
        <section className="card flush">
          <table className="table compact"><thead><tr><th>Version</th><th>Status</th><th>Effective</th><th>Notes</th><th className="num">Applications pinned</th></tr></thead><tbody>
            {data.versions.map((v) => (
              <tr key={v.id}><td><strong>{v.label}</strong></td>
                <td><Badge tone={v.status === 'ACTIVE' ? 'success' : 'neutral'} icon={false}>{v.status}</Badge></td>
                <td className="small">{fmtDate(v.effective_from)}{v.effective_to ? ` to ${fmtDate(v.effective_to)}` : ' onward'}</td>
                <td className="small">{v.notes}</td>
                <td className="num">{v.applications_pinned}</td></tr>))}
          </tbody></table>
        </section>
      )}
      {dlg?.t === 's' && <StageEdit s={dlg.s} onClose={() => setDlg(null)} />}
      {dlg?.t === 'p' && <PolicyEdit p={dlg.p} onClose={() => setDlg(null)} />}
    </div>
  )
}
