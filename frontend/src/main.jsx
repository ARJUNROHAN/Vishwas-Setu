import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppProvider, useApp } from './app-context'
import Layout from './components/Layout'
import Login from './pages/Login'
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/inter/latin-800.css'
import './styles.css'
import './dashboard-theme.css'
import './template-match.css'

const Router = import.meta.env.VITE_PAGES === 'true' ? HashRouter : BrowserRouter
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Applications = lazy(() => import('./pages/Applications'))
const ApplicationDetail = lazy(() => import('./pages/ApplicationDetail'))
const EvcQueue = lazy(() => import('./pages/EvcQueue'))
const Compliance = lazy(() => import('./pages/Compliance'))
const Deadlines = lazy(() => import('./pages/Deadlines'))
const Alerts = lazy(() => import('./pages/Alerts'))
const Reports = lazy(() => import('./pages/Reports'))
const Audit = lazy(() => import('./pages/Audit'))
const Config = lazy(() => import('./pages/Config'))
const InstitutionHome = lazy(() => import('./pages/InstitutionHome'))

function Guard() {
  const { user, loading } = useApp()
  if (loading) return <div className="loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Layout />
}

function Home() {
  const { user } = useApp()
  return user.role === 'INSTITUTION' ? <InstitutionHome /> : <Dashboard />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppProvider>
      <Router>
        <Suspense fallback={<div className="loading" role="status">Loading…</div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Guard />}>
            <Route path="/" element={<Home />} />
            <Route path="/applications" element={<Applications />} />
            <Route path="/applications/:id" element={<ApplicationDetail />} />
            <Route path="/evc" element={<EvcQueue />} />
            <Route path="/compliance" element={<Compliance />} />
            <Route path="/deadlines" element={<Deadlines />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/config" element={<Config />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
        </Suspense>
      </Router>
    </AppProvider>
  </React.StrictMode>,
)
