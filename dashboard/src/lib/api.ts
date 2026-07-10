class ApiClient {
  private getAuthHeaders(): Record<string, string> {
    const apiKey = typeof localStorage !== 'undefined'
      ? localStorage.getItem('tracea_api_key')
      : null
    if (apiKey) {
      return { Authorization: `Bearer ${apiKey}` }
    }
    return {}
  }

  private async request<T = any>(url: string, options: RequestInit = {}): Promise<{ data: T }> {
    try {
      const headers = { ...this.getAuthHeaders(), ...(options.headers as Record<string, string>) }
      const resp = await fetch(url, { ...options, headers })
      if (!resp.ok) {
        // Construct an error that behaves like AxiosError
        const error = new Error(`Request failed with status ${resp.status}`) as any
        error.response = {
          status: resp.status,
          data: await resp.text(),
        }
        throw error
      }
      const text = await resp.text()
      let data: any = null
      if (text) {
        try {
          data = JSON.parse(text)
        } catch {
          data = text
        }
      }
      return { data: data as T }
    } catch (err: any) {
      if (!err.response) {
        // Network error — backend is unreachable (connection refused, DNS failure, etc.)
        window.dispatchEvent(new CustomEvent('tracea:connection-error'))
      }
      throw err
    }
  }

  async get<T = any>(url: string): Promise<{ data: T }> {
    return this.request<T>(url, { method: 'GET' })
  }

  async post<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return this.request<T>(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: data !== undefined ? JSON.stringify(data) : undefined,
    })
  }

  async put<T = any>(url: string, data?: any): Promise<{ data: T }> {
    return this.request<T>(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: data !== undefined ? JSON.stringify(data) : undefined,
    })
  }

  async delete<T = any>(url: string): Promise<{ data: T }> {
    return this.request<T>(url, { method: 'DELETE' })
  }
}

const api = new ApiClient()
export default api
