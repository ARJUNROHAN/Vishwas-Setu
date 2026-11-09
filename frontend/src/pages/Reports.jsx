import { useState } from 'react'
import { api } from '../api'
import { PageHeader } from '../components/ui'
import Icon from '../components/Icon'

const REPORTS = [
  ['pendency', 'Application pendency', 'Every active application with stage, assignee, age and next deadline.'],
  ['evc', 'EVC status', 'Queued, scheduled and completed Expert Visit Committees with outcomes.'],
  ['undertakings', 'Undertaking compliance', 'Time-bound undertakings with due dates, status and escalation level.'],
  ['documents', 'Document validity', 'Leases and certificates with renewal dates and status.'],
  ['overdue', 'Overdue cases', 'All overdue deadlines with owner and escalation level.'],
  ['regions', 'Region-wise performance', 'Active load, ageing, overdue and escalations per Region (Bureau view).'],
]

export default function Reports() {
  const [err, setErr] = useState(null)
  const stamp = new Date().toISOString().slice(0, 10)
  return (
    <div>
      <PageHeader title="Reports" crumbs={['Exports']}>Consolidated CSV exports, scoped to what your role can see.</PageHeader>
      {err && <div className="error">{err}</div>}
      <div className="report-grid">
        {REPORTS.map(([k, title, desc]) => (
          <section key={k} className="card report">
            <div className="report-heading"><span className="report-icon"><Icon name={{ pendency: 'file', evc: 'calendar', undertakings: 'shield', documents: 'file', overdue: 'clock', regions: 'trend' }[k]} size={22} /></span><h2>{title}</h2></div><p className="muted small">{desc}</p>
            <button className="btn ghost" onClick={() => api.download(`/reports/${k}.csv`, `${k}_${stamp}.csv`).catch((e) => setErr(e.message))}><Icon name="download" size={16} /> Download CSV</button>
          </section>
        ))}
      </div>
    </div>
  )
}
