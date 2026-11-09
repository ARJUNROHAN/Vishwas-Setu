import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

const Ctx = createContext(null)

export function AppProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!getToken())
  const [clock, setClock] = useState(null)
  const [version, setVersion] = useState(0) // bump to make pages refetch
  const [toast, setToast] = useState(null)

  const refreshClock = useCallback(() => api.get('/clock').then(setClock).catch(() => {}), [])

  useEffect(() => {
    refreshClock()
    if (getToken()) {
      api.get('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setLoading(false))
    }
  }, [refreshClock])

  useEffect(() => {
    const expire = () => { setUser(null); setToken(null) }
    window.addEventListener('auth:expired', expire)
    return () => window.removeEventListener('auth:expired', expire)
  }, [])

  const login = async (username, password) => {
    const res = await api.post('/auth/login', { username, password })
    setToken(res.token)
    setUser(res.user)
    return res.user
  }
  const logout = () => { setToken(null); setUser(null) }
  const bump = () => { setVersion((v) => v + 1); refreshClock() }
  const notify = (msg, tone = 'good') => {
    setToast({ msg, tone, id: Date.now() })
    setTimeout(() => setToast((t) => (t && Date.now() - t.id >= 3900 ? null : t)), 4000)
  }

  return (
    <Ctx.Provider value={{ user, loading, login, logout, clock, refreshClock, version, bump, notify, toast }}>
      {children}
    </Ctx.Provider>
  )
}

export const useApp = () => useContext(Ctx)

export function useFetch(path, deps = []) {
  const { version } = useApp()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    if (!path) return
    setLoading(true)
    api.get(path).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message)).finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, version, ...deps])
  useEffect(() => { load() }, [load])
  return { data, error, loading, reload: load, setData }
}
