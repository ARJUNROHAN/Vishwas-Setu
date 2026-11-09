import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp, useFetch } from '../app-context'
import { fmtDateTime } from '../util'
import { Mark } from './Brand'
import Icon from './Icon'

const NAV = {
  official: [
    { group: 'Overview', items: [
      { to: '/', label: 'Dashboard', icon: 'dashboard' },
      { to: '/deadlines', label: 'Deadlines & escalations', icon: 'clock' },
      { to: '/alerts', label: 'Alerts', icon: 'bell' },
    ] },
    { group: 'Approval workflow', items: [
      { to: '/applications', label: 'Applications', icon: 'file' },
      { to: '/evc', label: 'EVC queue', icon: 'calendar', roles: ['EVC_COORDINATOR', 'EVC_MEMBER', 'REGIONAL_HEAD', 'BUREAU', 'ADMIN', 'SCRUTINY_OFFICER', 'COMPETENT_AUTHORITY'] },
      { to: '/compliance', label: 'Compliance', icon: 'shield', roles: ['SCRUTINY_OFFICER', 'RESCRUTINY_OFFICER', 'REGIONAL_HEAD', 'BUREAU', 'ADMIN', 'COMPETENT_AUTHORITY', 'EVC_COORDINATOR'] },
    ] },
    { group: 'Governance', items: [
      { to: '/reports', label: 'Reports', icon: 'download', roles: ['SCRUTINY_OFFICER', 'RESCRUTINY_OFFICER', 'REGIONAL_HEAD', 'BUREAU', 'ADMIN', 'COMPETENT_AUTHORITY', 'EVC_COORDINATOR', 'RULE_ADMIN', 'SHC_MEMBER'] },
      { to: '/audit', label: 'Audit trail', icon: 'chain' },
      { to: '/config', label: 'Rules & timelines', icon: 'sliders' },
    ] },
  ],
  institution: [
    { group: 'My institution', items: [
      { to: '/', label: 'Overview', icon: 'home' },
      { to: '/applications', label: 'My applications', icon: 'file' },
      { to: '/compliance', label: 'Undertakings & documents', icon: 'shield' },
      { to: '/alerts', label: 'Alerts', icon: 'bell' },
    ] },
  ],
}

function ClockControl() {
  const { clock, bump, notify } = useApp()
  const [busy, setBusy] = useState(false)
  if (!clock) return null
  const jump = async (days) => {
    setBusy(true)
    try {
      const r = await api.post('/clock/advance', { days })
      const t = r.tick
      notify(`Clock +${days}d: ${t.reminders} reminders, ${t.overdue} newly overdue, ${t.escalations} escalations`, 'info')
      bump()
    } catch (e) { notify(e.message, 'critical') } finally { setBusy(false) }
  }
  return (
    <div className="clock" title="Simulated clock for demonstration">
      <span className="clock-label">{clock.offset_days ? 'Simulated' : 'Today'}</span>
      <span className="clock-now">{fmtDateTime(clock.now)}</span>
      {clock.demo_mode && (
        <span className="clock-btns">
          {[1, 5, 10].map((d) => <button key={d} className="btn tiny" disabled={busy} onClick={() => jump(d)} aria-label={`Advance clock ${d} days`}>+{d}d</button>)}
        </span>
      )}
    </div>
  )
}

function Bell() {
  const { data, reload } = useFetch('/notifications?limit=12')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const nav = useNavigate()
  useEffect(() => {
    const id = setInterval(reload, 30000)
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => { clearInterval(id); document.removeEventListener('mousedown', close) }
  }, [reload])
  const unread = data?.unread || 0
  const go = async (n) => {
    setOpen(false)
    await api.post(`/notifications/${n.id}/read`).catch(() => {})
    reload()
    if (n.link) nav(n.link)
  }
  return (
    <div className="bell" ref={ref}>
      <button className="icon-btn bell-btn" onClick={() => setOpen(!open)} aria-label={`${unread} unread alerts`}>
        <Icon name="bell" size={20} />{unread > 0 && <span className="bell-count">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="bell-menu">
          <div className="row between bell-head">
            <strong>Alerts</strong>
            <button className="link" onClick={async () => { await api.post('/notifications/read-all'); reload() }}>Mark all read</button>
          </div>
          {(data?.items || []).map((n) => (
            <button key={n.id} className={`bell-item ${n.read ? '' : 'unread'}`} onClick={() => go(n)}>
              <span className={`dot dot-${n.category.toLowerCase()}`} />
              <span><span className="bell-subj">{n.subject}</span><span className="muted small">{fmtDateTime(n.created_at)}</span></span>
            </button>
          ))}
          {!data?.items?.length && <div className="empty small">No alerts</div>}
          <button className="link bell-all" onClick={() => { setOpen(false); nav('/alerts') }}>View all alerts</button>
        </div>
      )}
    </div>
  )
}

function initials(name) {
  return name.replace(/^(Dr\.|Prof\.|Ms\.|Mr\.)\s*/, '').split(/[\s.,]+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
}

function UserMenu({ user, logout }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  const scope = user.region ? `${user.region} Region` : user.role !== 'INSTITUTION' ? 'All India' : ''
  return (
    <div className="usermenu" ref={ref}>
      <button className="avatar" onClick={() => setOpen(!open)} aria-label="Account menu" aria-expanded={open}>{initials(user.name)}</button>
      {open && (
        <div className="usermenu-pop">
          <div className="usermenu-head">
            <span className="avatar static">{initials(user.name)}</span>
            <div><div className="who-name">{user.name}</div><div className="who-role">{user.role_label}{scope && `, ${scope}`}</div></div>
          </div>
          <button className="usermenu-item" onClick={logout}><Icon name="logout" size={16} /> Sign out</button>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, logout, toast } = useApp()
  const [collapsed, setCollapsed] = useState(false)
  const [q, setQ] = useState('')
  const nav = useNavigate()
  const groups = user.role === 'INSTITUTION' ? NAV.institution : NAV.official
  return (
    <div className={`app ${collapsed ? 'collapsed' : ''}`}>
      <aside className="sidebar">
        <Link to="/" className="logo"><Mark size={34} /><span className="logo-text"><strong>Vishwas Setu</strong><small>Workflow &amp; compliance</small></span></Link>
        <nav className="sidenav" aria-label="Main">
          {groups.map((g) => (
            <div key={g.group} className="sidenav-group">
              <div className="sidenav-caption">{g.group}</div>
              {g.items.filter((i) => !i.roles || i.roles.includes(user.role)).map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === '/'} className={({ isActive }) => `sidelink ${isActive ? 'active' : ''}`} title={i.label}>
                  <Icon name={i.icon} /><span>{i.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-card">
          <Icon name="shield" size={24} />
          <strong>Prototype</strong>
          <p>Built for SIH problem statement 26262. Not an official AICTE service; all data is fictional.</p>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="row center gap">
            <button className="icon-btn" onClick={() => setCollapsed(!collapsed)} aria-label="Toggle sidebar" aria-expanded={!collapsed}><Icon name="menu" size={22} /></button>
            <form className="topsearch" onSubmit={(e) => { e.preventDefault(); nav(`/applications?status=&q=${encodeURIComponent(q)}`) }}>
              <Icon name="search" size={16} />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search application no. or institution" aria-label="Search applications" />
            </form>
          </div>
          <div className="row center gap topbar-right">
            <ClockControl />
            <Bell />
            <UserMenu user={user} logout={logout} />
          </div>
        </header>
        <main className="content" id="main" tabIndex={-1}><Outlet /></main>
        <footer className="footbar">
          <span>Vishwas Setu prototype, SIH 26262. Rules: APH 2024-25 to 2026-27.</span>
          <span>Not an official AICTE service. All institutions and people shown are fictional.</span>
        </footer>
      </div>
      {toast && <div className={`toast toast-${toast.tone}`} role="status">{toast.msg}</div>}
    </div>
  )
}
