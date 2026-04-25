import axios from 'axios'

const api = axios.create({ baseURL: '/' })

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.response) {
      // Network error — backend is unreachable (connection refused, DNS failure, etc.)
      window.dispatchEvent(new CustomEvent('tracea:connection-error'))
    }
    return Promise.reject(error)
  }
)

export default api
