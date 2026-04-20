import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import yaml from 'js-yaml'
import { Settings as SettingsIcon, Loader2 } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { YamlEditor } from '@/components/settings/YamlEditor'
import { ApiKeyDisplay } from '@/components/settings/ApiKeyDisplay'
import api from '@/lib/api'

function validateYaml(content: string): { valid: boolean; error?: string } {
  try {
    yaml.load(content)
    return { valid: true }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    // Extract line info from yaml parse error
    const lineMatch = msg.match(/line (\d+)/i)
    const detail = lineMatch ? `${msg} (line ${lineMatch[1]})` : msg
    return { valid: false, error: detail }
  }
}

type TabId = 'alerts' | 'rules'

interface TabState {
  content: string
  loaded: boolean
  loading: boolean
  saving: boolean
  error: string | undefined
}

const DEFAULT_CONTENT = '# No content loaded yet\n'

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('alerts')

  const [alertsState, setAlertsState] = useState<TabState>({
    content: DEFAULT_CONTENT,
    loaded: false,
    loading: false,
    saving: false,
    error: undefined,
  })

  const [rulesState, setRulesState] = useState<TabState>({
    content: DEFAULT_CONTENT,
    loaded: false,
    loading: false,
    saving: false,
    error: undefined,
  })

  const loadAlerts = useCallback(async () => {
    setAlertsState((s) => ({ ...s, loading: true, error: undefined }))
    try {
      const res = await api.get<{ content: string }>('/api/v1/config/alerts')
      setAlertsState({
        content: res.data.content || '',
        loaded: true,
        loading: false,
        saving: false,
        error: undefined,
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setAlertsState((s) => ({
        ...s,
        loading: false,
        error: `Failed to load: ${msg}`,
      }))
    }
  }, [])

  const loadRules = useCallback(async () => {
    setRulesState((s) => ({ ...s, loading: true, error: undefined }))
    try {
      const res = await api.get<{ content: string }>('/api/v1/config/rules')
      setRulesState({
        content: res.data.content || '',
        loaded: true,
        loading: false,
        saving: false,
        error: undefined,
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setRulesState((s) => ({
        ...s,
        loading: false,
        error: `Failed to load: ${msg}`,
      }))
    }
  }, [])

  // Lazy load on tab selection
  useEffect(() => {
    if (activeTab === 'alerts' && !alertsState.loaded && !alertsState.loading) {
      loadAlerts()
    }
    if (activeTab === 'rules' && !rulesState.loaded && !rulesState.loading) {
      loadRules()
    }
  }, [activeTab, alertsState.loaded, alertsState.loading, rulesState.loaded, rulesState.loading, loadAlerts, loadRules])

  const saveAlerts = async (content: string) => {
    const validation = validateYaml(content)
    if (!validation.valid) {
      toast.error(`Save failed: ${validation.error}`)
      return
    }
    setAlertsState((s) => ({ ...s, saving: true }))
    try {
      await api.put('/api/v1/config/alerts', { content })
      setAlertsState((s) => ({ ...s, saving: false }))
      toast.success('Saved — hot-reload triggered')
    } catch (e: unknown) {
      setAlertsState((s) => ({ ...s, saving: false }))
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(`Save failed: ${msg}`)
    }
  }

  const saveRules = async (content: string) => {
    const validation = validateYaml(content)
    if (!validation.valid) {
      toast.error(`Save failed: ${validation.error}`)
      return
    }
    setRulesState((s) => ({ ...s, saving: true }))
    try {
      await api.put('/api/v1/config/rules', { content })
      setRulesState((s) => ({ ...s, saving: false }))
      toast.success('Saved — hot-reload triggered')
    } catch (e: unknown) {
      setRulesState((s) => ({ ...s, saving: false }))
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(`Save failed: ${msg}`)
    }
  }

  return (
    <div className="h-full flex flex-col space-y-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="h-5 w-5 text-zinc-500" />
        <h2 className="text-xl font-semibold">Settings</h2>
      </div>

      {/* API Key Display */}
      <ApiKeyDisplay />

      {/* YAML Editors */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabId)} className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="alerts">alerts.yaml</TabsTrigger>
            <TabsTrigger value="rules">detection_rules.yaml</TabsTrigger>
          </TabsList>
          <div className="flex gap-2">
            {activeTab === 'alerts' && (
              <Button
                size="sm"
                onClick={() => saveAlerts(alertsState.content)}
                disabled={alertsState.saving || !alertsState.loaded}
              >
                {alertsState.saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Save Changes
              </Button>
            )}
            {activeTab === 'rules' && (
              <Button
                size="sm"
                onClick={() => saveRules(rulesState.content)}
                disabled={rulesState.saving || !rulesState.loaded}
              >
                {rulesState.saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Save Changes
              </Button>
            )}
          </div>
        </div>

        <TabsContent value="alerts" className="flex-1 min-h-0 mt-2">
          {alertsState.loading ? (
            <div className="flex items-center justify-center h-64 text-zinc-400">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : alertsState.error ? (
            <div className="flex items-center justify-center h-64 text-red-500 text-sm">
              {alertsState.error}
            </div>
          ) : (
            <YamlEditor
              value={alertsState.content}
              onChange={(v) => setAlertsState((s) => ({ ...s, content: v }))}
              error={alertsState.error}
            />
          )}
        </TabsContent>

        <TabsContent value="rules" className="flex-1 min-h-0 mt-2">
          {rulesState.loading ? (
            <div className="flex items-center justify-center h-64 text-zinc-400">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : rulesState.error ? (
            <div className="flex items-center justify-center h-64 text-red-500 text-sm">
              {rulesState.error}
            </div>
          ) : (
            <YamlEditor
              value={rulesState.content}
              onChange={(v) => setRulesState((s) => ({ ...s, content: v }))}
              error={rulesState.error}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
