import { Link } from 'react-router-dom'
import { useApp, useFetch } from '../app-context'
import { DueBadge, Empty, Kind, Kpi, Loading, StatusBadge, PageHeader } from '../components/ui'
import Icon from '../components/Icon'
import { fmtDate } from '../util'

export default function InstitutionHome() {
  const { user } = useApp()
  const { data: obs } = useFetch('/obligations?mine=true')
  const { data: apps } = useFetch('/applications')
  const { data: docs } = useFetch('/documents')
  if (!obs || !apps || !docs) return <Loading />
  const overdue = obs.filter((o) => o.state === 'OVERDUE')
  const active = apps.filter((a) => ['IN_PROGRESS', 'RETURNED', 'READY_FOR_DECISION'].includes(a.status))
  return (
    <div>
      <PageHeader title="Overview" crumbs={[user.institution]} actions={<Link className="btn primary" to="/applications"><Icon name="file" size={14} /> My applications</Link>}>
        Your pending actions, applications and compliance at a glance.</PageHeader>
      <div className="kpis">
        <Kpi label="Actions due from you" value={obs.length} tone={overdue.length ? 'critical' : undefined} sub={`${overdue.length} overdue`} />
        <Kpi label="Applications in process" value={active.length} sub={`${apps.filter((a) => a.status === 'RETURNED').length} awaiting your reply`} />
        <Kpi label="Documents needing renewal" value={docs.filter((d) => ['MISSING', 'EXPIRED', 'LEASE_REVIEW_REQUIRED', 'EXPIRING_SOON'].includes(d.status)).length} sub={`${docs.filter((d) => d.status === 'MISSING').length} required but missing`} />
      </div>
      <section className="card">
        <div className="card-head"><h2>What you need to do</h2></div>
        {!obs.length ? <Empty>Nothing pending. You will be alerted before any deadline.</Empty> : (
          <ul className="watch">
            {obs.map((o) => (
              <li key={o.id} className="row between gap">
                <div><Kind kind={o.kind} />
                  <div className="watch-title">{o.application_id ? <Link to={`/applications/${o.application_id}`}>{o.title}</Link> :
                    <Link to={o.subject_type === 'document' ? '/compliance?tab=documents' : '/compliance?tab=undertakings'}>{o.title}</Link>}</div>
                  <div className="muted small">Due {fmtDate(o.due_at)}, 17:30 IST{o.source_reference && ` · ${o.source_reference}`}</div></div>
                <DueBadge state={o.state} days={o.days_left} />
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card flush">
        <div className="card-head pad"><h2>Applications</h2></div>
        {!apps.length ? <Empty>No applications yet. Start one from My applications.</Empty> : <table className="table">
          <tbody>
            {apps.slice().reverse().map((a) => (
              <tr key={a.id}><td><Link className="mono" to={`/applications/${a.id}`}>{a.application_no}</Link></td><td>{a.type_label}</td>
                <td><StatusBadge status={a.status} /></td><td className="small">{a.stage_name || ''}</td></tr>
            ))}
          </tbody>
        </table>}
      </section>
    </div>
  )
}
