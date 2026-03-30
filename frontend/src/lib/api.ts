// src/lib/api.ts
import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ────────────────────────────────────────────────────────
export const authApi = {
  login:    (email: string, password: string) =>
    api.post('/api/auth/login', new URLSearchParams({ username: email, password })),
  register: (email: string, name: string, password: string) =>
    api.post('/api/auth/register', { email, name, password }),
  me:       () => api.get('/api/auth/me'),
}

// ── Portfolios ──────────────────────────────────────────────────
export const portfolioApi = {
  list:        () => api.get('/api/portfolios'),
  create:      (name: string, description?: string) => api.post('/api/portfolios', { name, description }),
  delete:      (id: string) => api.delete(`/api/portfolios/${id}`),
  addStock:    (pid: string, stock: any) => api.post(`/api/portfolios/${pid}/stocks`, stock),
  removeStock: (pid: string, sid: string) => api.delete(`/api/portfolios/${pid}/stocks/${sid}`),
}

// ── Market ──────────────────────────────────────────────────────
export const marketApi = {
  quotes:    (pid: string) => api.get(`/api/market/quotes/${pid}`),
  analysis:  (code: string, market: string) => api.get(`/api/market/stock/${code}/analysis`, { params: { market } }),
  predict:   (code: string, market: string) => api.post(`/api/market/stock/${code}/predict`, null, { params: { market } }),
  search:    (q: string, market: string) => api.get('/api/search', { params: { q, market } }),
}

// ── Accuracy ────────────────────────────────────────────────────
export const accuracyApi = {
  summary: () => api.get('/api/accuracy'),
  history: (code: string) => api.get(`/api/accuracy/history/${code}`),
}
