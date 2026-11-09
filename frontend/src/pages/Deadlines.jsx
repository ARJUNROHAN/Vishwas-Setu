import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useFetch } from '../app-context'
import { ActionForm, Badge, DueBadge, Empty, ErrorBox, EscBadge, Kind, Loading, PageHeader } from '../components/ui'
import { fmtDateTime, KIND_LABEL, ROLE_SHORT } from '../util'

function Escalations() {
  const [openOnly, setOpenOnly] = useState(true)
  const [mine, setMine] = useState(false)
  const { data, error, loading, reload } = useFetch(`/escalations?open_only=${openOnly}&mine=${mine}`)
  const [ack, setAck] = useState(null)
  return (
    <>
      <div className="filters">
        <label className="check"><input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Unresolved only</label>
        <label className="check"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} /> Escalated to my role</label>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : !data.length ? <Empty>No escalations.</Empty> : (
        <section className="card flush">
          <table className="table">
            <thead><tr><th>Level</th><th>Deadline</th><th>Escalated to</th><th>Raised</th><th>Acknowledged</th><th /></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id}>
                  <td><EscBadge level={e.level} /></td>
                  <td>{e.obligation.application_id ? <Link to={`/applications/${e.obligation.application_id}`}>{e.obligation.title}</Link> : e.obligation.title}
                    <div className="muted small"><Kind kind={e.obligation.kind} /> due {fmtDateTime(e.obligation.due_at)}{e.obligation.source_reference && ` · ${e.obligation.source_reference}`}</div></td>
                  <td className="small">{ROLE_SHORT[e.target_role] || e.target_role}</td>
                  <td className="small td-date">{fmtDateTime(e.created_at)}</td>
                  <td className="small">{e.acknowledged_at ? <>{fmtDateTime(e.acknowledged_at)}{e.ack_note && <div className="muted">{e.ack_note}</div>}</>
                    : e.resolved_at ? <Badge tone="neutral" icon={false}>Resolved</Badge> : <Badge tone="critical">Pending</Badge>}</td>
                  <td className="num">{e.can_acknowledge && <button className="btn primary small" onClick={() => setAck(e)}>Acknowledge</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {ack && <ActionForm title={`Acknowledge escalation L${ack.level}`} submitLabel="Acknowledge" remarksLabel="Action being taken"
        onClose={() => { setAck(null); reload() }} onSubmit={(note, key) => api.post(`/escalations/${ack.id}/acknowledge`, { note }, key)}>
        <p className="hint">Acknowledging records that you have taken ownership. The deadline itself stays open until the underlying work is done.</p>
      </ActionForm>}
    </>
  )
}

export default function Deadlines() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'deadlines'
  const state = params.get('state') || ''
  const kind = params.get('kind') || ''
  const escalated = params.get('escalated') === '1'
  const mine = params.get('mine') === '1'
  const qs = new URLSearchParams({ ...(state && { state }), ...(kind && { kind }), ...(escalated && { escalated: 'true' }), ...(mine && { mine: 'true' }) })
  const { data, error, loading } = useFetch(`/obligations?${qs}`)
  const set = (k, v) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p) }
  return (
    <div>
      <PageHeader title="Deadlines" crumbs={[tab === 'escalations' ? 'Escalations' : 'Open deadlines']}>
        Every open deadline across stages, EVCs, undertakings and documents, from one engine.</PageHeader>
      <div className="tabs">
        <button className={tab === 'deadlines' ? 'active' : ''} onClick={() => set('tab', '')}>Deadlines</button>
        <button className={tab === 'escalations' ? 'active' : ''} onClick={() => set('tab', 'escalations')}>Escalations</button>
      </div>
      {tab === 'escalations' ? <Escalations /> : <>
      <ErrorBox error={error} />
      <section className="card flush list-card">
      <div className="card-toolbar">
        <span className="toolbar-label">Filter</span>
        <select value={state} onChange={(e) => set('state', e.target.value)} aria-label="State">
          <option value="">All open</option><option value="OVERDUE">Overdue</option><option value="DUE_SOON">Due soon</option>
          <option value="UPCOMING">On track</option><option value="DUE_TODAY">Due today</option><option value="PAUSED">Clock paused</option>
        </select>
        <select value={kind} onChange={(e) => set('kind', e.target.value)} aria-label="Kind">
          <option value="">All kinds</option>{Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label className="check"><input type="checkbox" checked={escalated} onChange={(e) => set('escalated', e.target.checked ? '1' : '')} /> Escalated only</label>
        <label className="check"><input type="checkbox" checked={mine} onChange={(e) => set('mine', e.target.checked ? '1' : '')} /> Mine</label>
      </div>
      {loading && !data ? <Loading /> : !data.length ? <Empty>No deadlines match.</Empty> : (
          <table className="table">
            <thead><tr><th>Kind</th><th>What</th><th>Owner</th><th>Due (IST)</th><th>State</th></tr></thead>
            <tbody>
              {data.map((o) => (
                <tr key={o.id}>
                  <td><Kind kind={o.kind} /></td>
                  <td>{o.application_id ? <Link to={`/applications/${o.application_id}`}>{o.title}</Link> :
                    <Link to={o.subject_type === 'document' ? '/compliance?tab=documents' : '/compliance?tab=undertakings'}>{o.title}</Link>}
                    {o.source_reference && <div className="muted small">{o.source_reference}</div>}</td>
                  <td className="small">{o.owner || ROLE_SHORT[o.owner_role]}</td>
                  <td className="small td-date">{fmtDateTime(o.due_at)}</td>
                  <td><div className="row gap center"><DueBadge state={o.state} days={o.days_left} /><EscBadge level={o.escalation_level} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        
      )}
      </section>
      </>}
    </div>
  )
}
