import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp, useFetch } from '../app-context'
import { Badge, Empty, ErrorBox, Loading, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { fmtDateTime } from '../util'

const TONE = { ESCALATION: 'critical', OVERDUE: 'critical', DUE_TODAY: 'warning', REMINDER: 'warning', INFO: 'info' }
const LABEL = { ESCALATION: 'Escalation', OVERDUE: 'Overdue', DUE_TODAY: 'Due today', REMINDER: 'Reminder', INFO: 'Update' }

function Outbox() {
  const { data, error, loading } = useFetch('/notifications/outbox?limit=300')
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  return (
    <>
      <p className="hint">Email delivery is simulated in this prototype: messages are written to this outbox and to the server log, not sent. A real deployment would plug an SMTP or NIC mail adapter in here.</p>
      {!data.length ? <Empty>No emails queued.</Empty> : (
        <section className="card flush">
          <table className="table">
            <thead><tr><th>To</th><th>Subject</th><th>Type</th><th>Status</th><th>Queued (IST)</th></tr></thead>
            <tbody>
              {data.map((n) => (
                <tr key={n.id}>
                  <td className="small">{n.to}</td>
                  <td><strong>{n.subject}</strong><div className="muted small">{n.body}</div></td>
                  <td><Badge tone={TONE[n.category]}>{LABEL[n.category]}</Badge></td>
                  <td><Badge tone={n.status === 'DELIVERED' ? 'success' : 'neutral'} icon={false}>{n.status === 'SIMULATED' ? 'Simulated' : n.status}</Badge></td>
                  <td className="small td-date">{fmtDateTime(n.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  )
}

export default function Alerts() {
  const [tab, setTab] = useState('inbox')
  const { data, error, loading, reload } = useFetch('/notifications?limit=300')
  const { bump } = useApp()
  const nav = useNavigate()
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  return (
    <div>
      <PageHeader title="Alerts" crumbs={[tab === 'outbox' ? 'Email outbox' : `In-app (${data.unread} unread)`]}
        actions={tab === 'inbox' && <button className="btn ghost" onClick={async () => { await api.post('/notifications/read-all'); reload(); bump() }}><Icon name="check" size={14} /> Mark all read</button>}>
        Each alert is also queued as an email.</PageHeader>
      <div className="tabs">
        <button className={tab === 'inbox' ? 'active' : ''} onClick={() => setTab('inbox')}>In-app</button>
        <button className={tab === 'outbox' ? 'active' : ''} onClick={() => setTab('outbox')}>Email outbox</button>
      </div>
      {tab === 'outbox' ? <Outbox /> : !data.items.length ? <Empty>No alerts yet.</Empty> : (
        <section className="card flush">
          <ul className="alerts">
            {data.items.map((n) => (
              <li key={n.id} className={n.read ? '' : 'unread'} onClick={async () => { await api.post(`/notifications/${n.id}/read`); bump(); if (n.link) nav(n.link); else reload() }}>
                <Badge tone={TONE[n.category]}>{LABEL[n.category]}</Badge>
                <div className="grow"><div className="alert-subj">{n.subject}</div><div className="muted small">{n.body}</div></div>
                <span className="muted small nowrap">{fmtDateTime(n.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
