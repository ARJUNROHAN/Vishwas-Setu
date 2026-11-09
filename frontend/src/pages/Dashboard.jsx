import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApp, useFetch } from '../app-context'
import Icon from '../components/Icon'
import { DueBadge, ErrorBox, EscBadge, Kind, Loading, PageHeader } from '../components/ui'
import { fmtDate, ROLE_SHORT, STAGE_LABEL } from '../util'

const C = {
  primary: '#3454d1', overdue: '#ea4d4d', dueSoon: '#ffa21d', onTrack: '#3454d1', success: '#17c666',
  grid: '#eef0f4', base: '#e5e7eb', axis: '#9ca3af', ink: '#283c50',
  age: ['#c3cdf3', '#8fa2e6', '#5a74db', '#2c46b5'],
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const wk = (iso) => `${Number(iso.slice(8, 10))} ${MONTHS[Number(iso.slice(5, 7)) - 1]}`

function ChartTip({ active, payload, label, labelFmt }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tip">
      <div className="chart-tip-title">{labelFmt ? labelFmt(label) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="row gap small"><span className="swatch" style={{ background: p.color || p.fill }} />{p.name}<strong className="tnum">{p.value}</strong></div>
      ))}
    </div>
  )
}

function Legend({ items }) {
  return <div className="chart-legend">{items.map(([l, c]) => <span key={l}><span className="swatch" style={{ background: c }} />{l}</span>)}</div>
}

function StatCard({ icon, value, total, title, caption, tone, onClick }) {
  const pct = total ? Math.round((value / total) * 100) : 0
  return (
    <button className="stat" onClick={onClick}>
      <div className="stat-top">
        <span className="stat-icon"><Icon name={icon} size={20} /></span>
        <span><span className="stat-value tnum">{value}<span className="stat-total">/{total}</span></span><span className="stat-title">{title}</span></span>
      </div>
      <div className="stat-foot">
        <div className="row between small"><span className="muted">{caption}</span><span className="tnum"><strong>{pct}%</strong></span></div>
        <div className="progress"><span style={{ width: `${pct}%`, background: `var(--${tone})` }} /></div>
      </div>
    </button>
  )
}

export default function Dashboard() {
  const { user } = useApp()
  const nav = useNavigate()
  const allIndia = ['BUREAU', 'ADMIN'].includes(user.role)
  const [region, setRegion] = useState('')
  const { data, error, loading } = useFetch(`/dashboard${region ? `?region_id=${region}` : ''}`)
  const { data: meta } = useFetch('/meta')
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const k = data.kpis
  const h = data.headline
  const pend = data.pendency_by_stage.map((p) => ({
    stage: STAGE_LABEL[p.stage] || p.stage, overdue: p.overdue, dueSoon: p.due_soon,
    onTrack: p.count - p.overdue - p.due_soon, raw: p.stage, total: p.count,
  }))
  const totalOverdue = pend.reduce((n, p) => n + p.overdue, 0)
  const worst = pend.slice().sort((x, y) => y.total - x.total)[0]
  const ageing = data.ageing.map((a) => ({ ...a, label: `${a.bucket.replace('-', '–')} days` }))
  const olderThan15 = data.ageing.filter((a) => a.bucket === '16-30' || a.bucket === '30+').reduce((n, a) => n + a.count, 0)
  const weekly = data.weekly
  const submitted10 = weekly.reduce((n, w) => n + w.submitted, 0)
  const thisWeek = weekly[weekly.length - 1]
  const scope = allIndia ? (region ? `${meta?.regions.find((r) => String(r.id) === region)?.name} Region` : 'All India') : `${user.region} Region`

  return (
    <div>
      <PageHeader title="Dashboard" crumbs={[scope]} actions={allIndia && meta && (
          <select className="select-sm" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region filter">
            <option value="">All Regions</option>
            {meta.regions.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.office_city})</option>)}
          </select>
        )} />

      <div className="stats">
        <StatCard icon="file" value={h.on_track.value} total={h.on_track.total} title="Applications on track"
          caption={`${h.on_track.total - h.on_track.value} with a missed deadline`} tone="primary" onClick={() => nav('/applications?status=ACTIVE')} />
        <StatCard icon="calendar" value={h.evc_scheduled.value} total={h.evc_scheduled.total} title="EVCs scheduled"
          caption={`${h.evc_scheduled.total - h.evc_scheduled.value} waiting to be scheduled`} tone="warning-c" onClick={() => nav('/evc')} />
        <StatCard icon="shield" value={h.undertakings_verified.value} total={h.undertakings_verified.total} title="Undertakings verified"
          caption={`${k.undertakings_overdue} overdue`} tone="success-c" onClick={() => nav('/compliance?tab=undertakings')} />
        <StatCard icon="alert" value={h.docs_valid.value} total={h.docs_valid.total} title="Documents in validity"
          caption={`${k.docs_overdue} past renewal date`} tone="danger-c" onClick={() => nav('/compliance?tab=documents')} />
      </div>

      <div className="grid-main">
        <section className="card">
          <div className="card-head"><h2>Pendency by stage</h2><span className="muted small">Select a bar to open those applications</span></div>
          <div className="card-body">
            <p className="chart-finding"><strong className="tnum">{totalOverdue}</strong> of {k.active} active applications have a missed deadline{worst ? <>; the largest backlog is at <strong>{worst.stage}</strong>.</> : '.'}</p>
            <Legend items={[['Overdue', C.overdue], ['Due within 3 days', C.dueSoon], ['On track', C.onTrack]]} />
            <ResponsiveContainer width="100%" height={pend.length * 40 + 34}>
              <BarChart data={pend} layout="vertical" margin={{ left: 4, right: 40, top: 4, bottom: 0 }} barSize={14}
                onClick={(e) => { const s = e?.activePayload?.[0]?.payload?.raw; if (s) nav(s === 'RETURNED' ? '/applications?status=RETURNED' : s === 'DECISION' ? '/applications?status=READY_FOR_DECISION' : `/applications?stage=${s}`) }}>
                <CartesianGrid horizontal={false} stroke={C.grid} />
                <XAxis type="number" allowDecimals={false} tick={{ fill: C.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="stage" width={110} tick={{ fill: C.ink, fontSize: 12.5, fontWeight: 500 }} axisLine={{ stroke: C.base }} tickLine={false} />
                <Tooltip content={<ChartTip />} cursor={{ fill: 'rgba(52,84,209,0.05)' }} />
                <Bar dataKey="overdue" name="Overdue" stackId="a" fill={C.overdue} stroke="#fff" strokeWidth={2} style={{ cursor: 'pointer' }} />
                <Bar dataKey="dueSoon" name="Due within 3 days" stackId="a" fill={C.dueSoon} stroke="#fff" strokeWidth={2} style={{ cursor: 'pointer' }} />
                <Bar dataKey="onTrack" name="On track" stackId="a" fill={C.onTrack} stroke="#fff" strokeWidth={2} radius={[0, 4, 4, 0]} style={{ cursor: 'pointer' }}>
                  <LabelList dataKey="total" position="right" offset={8} style={{ fill: C.ink, fontSize: 12.5, fontWeight: 700 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card hero-card">
          <div className="hero-top">
            <div className="row between">
              <div><div className="hero-value tnum">{submitted10}</div><div className="hero-label">Applications received, last 10 weeks</div></div>
              <span className="hero-pill">{thisWeek.submitted} this week</span>
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <AreaChart data={weekly} margin={{ left: 0, right: 0, top: 16, bottom: 0 }}>
                <defs><linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ffffff" stopOpacity={0.45} /><stop offset="100%" stopColor="#ffffff" stopOpacity={0.05} /></linearGradient></defs>
                <Tooltip content={<ChartTip labelFmt={(l) => `Week of ${wk(l)}`} />} cursor={{ stroke: 'rgba(255,255,255,0.5)' }} />
                <XAxis dataKey="week" hide />
                <Area type="monotone" dataKey="submitted" name="Received" stroke="#ffffff" strokeWidth={2} fill="url(#hero-fill)" activeDot={{ r: 4, fill: '#fff' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <ul className="hero-list">
            {[
              ['Awaiting decision', k.ready_for_decision, 'Placed before the competent authority', '/applications?status=READY_FOR_DECISION'],
              ['With institutions', k.returned, 'Returned for compliance', '/applications?status=RETURNED'],
              ['Escalations not acknowledged', k.escalations_unacknowledged ?? 0, `${k.escalated} escalated deadlines in all`, '/deadlines?tab=escalations'],
              ['Verifications pending', k.verifications_pending, 'Evidence and renewed documents', '/compliance'],
            ].map(([t, v, d, to]) => (
              <li key={t}><Link to={to}><span><strong>{t}</strong><span className="muted small">{d}</span></span><span className="hero-list-value tnum">{v}</span></Link></li>
            ))}
          </ul>
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <div className="card-head"><h2>Application ageing</h2><span className="muted small">Days since submission</span></div>
          <div className="card-body">
            <p className="chart-finding"><strong className="tnum">{olderThan15}</strong> of {k.active} active applications were submitted more than 15 days ago.</p>
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={ageing} margin={{ left: 0, right: 8, top: 22, bottom: 0 }} barSize={44}>
                <CartesianGrid vertical={false} stroke={C.grid} />
                <XAxis dataKey="label" tick={{ fill: C.ink, fontSize: 12 }} axisLine={{ stroke: C.base }} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fill: C.axis, fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip content={<ChartTip />} cursor={{ fill: 'rgba(52,84,209,0.05)' }} />
                <Bar dataKey="count" name="Applications" radius={[4, 4, 0, 0]}>
                  {ageing.map((d, i) => <Cell key={d.bucket} fill={C.age[i]} />)}
                  <LabelList dataKey="count" position="top" offset={6} style={{ fill: C.ink, fontSize: 12.5, fontWeight: 700 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="card">
          <div className="card-head"><h2>Received and decided per week</h2><span className="muted small">Last 10 weeks</span></div>
          <div className="card-body">
            <p className="chart-finding"><strong className="tnum">{weekly.reduce((n, w) => n + w.decided, 0)}</strong> decisions recorded against {submitted10} applications received.</p>
            <Legend items={[['Received', C.primary], ['Decided', C.success]]} />
            <ResponsiveContainer width="100%" height={206}>
              <BarChart data={weekly} margin={{ left: 0, right: 8, top: 8, bottom: 0 }} barGap={3} barSize={10}>
                <CartesianGrid vertical={false} stroke={C.grid} />
                <XAxis dataKey="week" tickFormatter={wk} tick={{ fill: C.axis, fontSize: 11 }} axisLine={{ stroke: C.base }} tickLine={false} interval={1} />
                <YAxis allowDecimals={false} tick={{ fill: C.axis, fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                <Tooltip content={<ChartTip labelFmt={(l) => `Week of ${wk(l)}`} />} cursor={{ fill: 'rgba(52,84,209,0.05)' }} />
                <Bar dataKey="submitted" name="Received" fill={C.primary} radius={[3, 3, 0, 0]} />
                <Bar dataKey="decided" name="Decided" fill={C.success} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      {data.by_region.length > 0 && !region && (
        <section className="card">
          <div className="card-head"><h2>Region-wise processing performance</h2><span className="muted small">Select a Region to filter the dashboard</span></div>
          <table className="table">
            <thead><tr><th>Region</th><th className="num">Active</th><th className="num">Avg age (days)</th><th className="num">Overdue (officials)</th><th className="num">Escalated</th><th className="num">EVC pending</th><th className="num">Compliance overdue</th></tr></thead>
            <tbody>
              {data.by_region.map((r) => (
                <tr key={r.region} className="clickable" onClick={() => setRegion(String(r.region_id))}>
                  <td><strong>{r.region}</strong></td><td className="num">{r.active}</td><td className="num">{r.avg_age_days}</td>
                  <td className="num">{r.overdue ? <span className="txt-critical">{r.overdue}</span> : 0}</td>
                  <td className="num">{r.escalated}</td><td className="num">{r.evc_pending}</td><td className="num">{r.compliance_overdue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <div className="card-head"><h2>Needs attention</h2><Link to="/deadlines" className="small">All deadlines</Link></div>
          <ul className="watch card-body">
            {data.watchlist.map((o) => (
              <li key={o.id}>
                <div className="row between gap">
                  <div className="grow">
                    <div className="row gap center"><Kind kind={o.kind} /><EscBadge level={o.escalation_level} /></div>
                    <div className="watch-title">{o.application_id ? <Link to={`/applications/${o.application_id}`}>{o.title}</Link> : o.title}</div>
                    <div className="muted small">Owner: {o.owner || ROLE_SHORT[o.owner_role]}, due {fmtDate(o.due_at)}</div>
                  </div>
                  <DueBadge state={o.state} days={o.days_left} />
                </div>
              </li>
            ))}
            {!data.watchlist.length && <li className="muted">Nothing overdue or due soon.</li>}
          </ul>
        </section>
        <section className="card">
          <div className="card-head"><h2>Workload by official</h2><span className="muted small">Open deadlines owned</span></div>
          <table className="table compact">
            <thead><tr><th>Official</th><th>Role</th>{allIndia && <th>Region</th>}<th className="num">Open</th><th className="num">Overdue</th><th>Load</th></tr></thead>
            <tbody>
              {data.workload.slice(0, 10).map((w) => {
                const max = Math.max(...data.workload.map((x) => x.open), 1)
                return (
                  <tr key={w.officer + w.region}>
                    <td className="nowrap"><strong>{w.officer}</strong></td><td className="muted nowrap">{ROLE_SHORT[w.role]}</td>{allIndia && <td className="muted">{w.region}</td>}
                    <td className="num">{w.open}</td>
                    <td className="num">{w.overdue ? <span className="txt-critical">{w.overdue}</span> : 0}</td>
                    <td className="loadcell"><div className="progress"><span style={{ width: `${(w.open / max) * 100}%`, background: w.overdue ? 'var(--danger-c)' : 'var(--primary)' }} /></div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  )
}
