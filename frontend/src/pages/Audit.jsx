import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useFetch } from '../app-context'
import { Badge, ErrorBox, Loading, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { ACTION_LABEL, fmtDateTime } from '../util'

export default function Audit() {
  const [action, setAction] = useState('')
  const { data, error, loading } = useFetch(`/audit?limit=300${action ? `&action=${action}` : ''}`)
  const [check, setCheck] = useState(null)
  const [busy, setBusy] = useState(false)
  const verify = async () => { setBusy(true); try { setCheck(await api.get('/audit/verify')) } finally { setBusy(false) } }
  return (
    <div>
      <PageHeader title="Audit trail" crumbs={['Events']} actions={<>
          {check && (check.valid ? <Badge tone="good">Chain intact · {check.events_checked} events</Badge> : <Badge tone="critical">Chain broken at #{check.broken_at_seq}</Badge>)}
          <button className="btn primary" onClick={verify} disabled={busy}><Icon name="shield" size={14} /> {busy ? 'Verifying…' : 'Verify hash chain'}</button>
        </>}>Append-only and hash-chained: editing or deleting any past entry breaks the chain.</PageHeader>
      <ErrorBox error={error} />
      <section className="card flush list-card">
      <div className="card-toolbar">
        <span className="toolbar-label">Filter</span>
        <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action">
          <option value="">All actions</option>{Object.entries(ACTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {loading && !data ? <Loading /> : (
          <table className="table compact">
            <thead><tr><th className="num">#</th><th>When</th><th>Action</th><th>By</th><th>Details</th><th>Hash</th></tr></thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.seq}>
                  <td className="num mono">{e.seq}</td>
                  <td className="small nowrap">{fmtDateTime(e.ts)}</td>
                  <td>{ACTION_LABEL[e.action] || e.action}{e.application_id && <div><Link className="small" to={`/applications/${e.application_id}`}>application</Link></div>}</td>
                  <td className="small">{e.actor}</td>
                  <td className="small">{e.reason && <div>“{e.reason}”</div>}
                    <div className="muted">{Object.entries(e.detail || {}).slice(0, 4).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')}</div></td>
                  <td className="mono tiny muted" title={`prev ${e.prev_hash}`}>{e.hash.slice(0, 10)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        
      )}
      </section>
    </div>
  )
}
