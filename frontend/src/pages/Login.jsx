import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../app-context'
import { Mark } from '../components/Brand'
import Icon from '../components/Icon'

const POINTS = [
  ['file', 'Routing by the handbook', 'Every application follows the stages the Approval Process Handbook prescribes for its type.'],
  ['clock', 'Every deadline watched', 'Stage limits, EVCs, undertakings and leases share one engine with reminders and escalation.'],
  ['shield', 'Officials decide', 'The system queues, times and reminds. Decisions are recorded only by the competent authority.'],
]

export default function Login() {
  const { user, login } = useApp()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const [demo, setDemo] = useState([])
  const [busy, setBusy] = useState(false)
  const [demoRole, setDemoRole] = useState('Institution')
  const [serverStatus, setServerStatus] = useState('loading')
  const loadDemo = () => {
    setServerStatus('loading')
    api.get('/demo/users').then((users) => { setDemo(users); setServerStatus('ready') })
      .catch(() => setServerStatus('error'))
  }
  useEffect(loadDemo, [])
  if (user) return <Navigate to="/" replace />

  const go = async (u, p) => {
    setBusy(true); setErr(null)
    try { await login(u, p); nav('/') } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const groups = demo.reduce((acc, d) => { (acc[d.role_label] = acc[d.role_label] || []).push(d); return acc }, {})

  return (
    <div className="auth">
      <section className="auth-cover">
        <div className="logo light"><span className="logo-text"><strong>Vishwas Setu</strong><small>Workflow &amp; compliance</small></span></div>
        <div className="auth-story">
        <div className="auth-emblem"><Mark size={220} /></div>
        <div className="auth-cover-body">
          <h1>Approval workflow and compliance monitoring for technical education</h1>
          <p>For Regional offices, the Regulation Bureau, Expert Visit Committees and institutions applying for approval.</p>
          <details className="auth-features">
          <summary>How Vishwas Setu helps</summary>
          <ul className="auth-points">
            {POINTS.map(([icon, t, d]) => (
              <li key={t}><span className="auth-point-icon"><Icon name={icon} size={18} /></span><span><strong>{t}</strong><br />{d}</span></li>
            ))}
          </ul>
          </details>
        </div>
        </div>
        <p className="auth-foot">Prototype for Smart India Hackathon problem statement 26262. Not an official AICTE service; do not enter real credentials.</p>
      </section>
      <section className="auth-form">
        <div className="auth-card">
          <h2>Login</h2>
          <p className="auth-sub">Sign in to your account</p>
          <p className="muted">Use a demo account below, or enter a username and password.</p>
          {serverStatus === 'loading' && <p className="muted" role="status">Starting the demo server. This can take about a minute.</p>}
          {serverStatus === 'error' && <p role="status">Could not reach the demo server. <button className="btn ghost" onClick={loadDemo}>Try again</button></p>}
          <form onSubmit={(e) => { e.preventDefault(); go(username, password) }}>
            <div className="field"><label htmlFor="u">Username</label><input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></div>
            <div className="field"><label htmlFor="p">Password</label><input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
            {err && <div className="error">{err}</div>}
            <button className="btn primary wide" disabled={busy}>{busy ? 'Signing in…' : 'Login'}</button>
          </form>
          {demo.length > 0 && (
            <div className="demo-users">
              <div className="demo-head">Demo accounts <span className="muted">password <code>demo123</code></span></div>
              <div className="demo-picker">
                <label htmlFor="demo-role">Role</label>
                <select id="demo-role" value={demoRole} onChange={(e) => setDemoRole(e.target.value)}>
                  {Object.entries(groups).map(([role, list]) => <option key={role} value={role}>{role} ({list.length})</option>)}
                </select>
              </div>
              <div className="demo-grid">
                {(groups[demoRole] || []).map((d) => (
                  <button key={d.username} className="demo-user" disabled={busy} onClick={() => go(d.username, 'demo123')} title={d.designation}>
                    <span className="demo-name">{d.role === 'INSTITUTION' ? d.name.replace('Principal, ', '') : d.name}</span>
                    <span className="demo-region">{d.username}{d.region ? ` · ${d.region}` : ''}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
