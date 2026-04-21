import axios from 'axios'

const api = axios.create({ baseURL: '/' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('tracea_api_key')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.dispatchEvent(new CustomEvent('tracea:auth-error'))
    } else if (!error.response) {
      // Network error — backend is unreachable (connection refused, DNS failure, etc.)
      window.dispatchEvent(new CustomEvent('tracea:connection-error'))
    }
    return Promise.reject(error)
  }
)

export default api
