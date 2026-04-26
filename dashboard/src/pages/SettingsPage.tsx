import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import yaml from 'js-yaml'
import { Settings as SettingsIcon, Loader2, BrainCircuit } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { YamlEditor } from '@/components/settings/YamlEditor'
import { RuleTemplates } from '@/components/settings/RuleTemplates'
import { RulesHelpPanel } from '@/components/settings/RulesHelpPanel'
import { AlertsHelpPanel } from '@/components/settings/AlertsHelpPanel'
import api from '@/lib/api'

interface RCAConfig {
  backend: string
  model: string
  base_url: string
  max_tokens: number
  api_key_present: boolean
  api_key?: string
}

function validateYaml(content: string): { valid: boolean; error?: string } {
  try {
    yaml.load(content)
    return { valid: true }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    const lineMatch = msg.match(/line (\d+)/i)
    const detail = lineMatch ? `${msg} (line ${lineMatch[1]})` : msg
    return { valid: false, error: detail }
  }
}

type TabId = 'alerts' | 'rules' | 'rca'

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

  const [rcaConfig, setRcaConfig] = useState<RCAConfig>({
    backend: 'disabled',
    model: '',
    base_url: '',
    max_tokens: 2048,
    api_key_present: false,
  })
  const [rcaLoading, setRcaLoading] = useState(false)
  const [rcaSaving, setRcaSaving] = useState(false)

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
        loaded: true,
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
        loaded: true,
        loading: false,
        error: `Failed to load: ${msg}`,
      }))
    }
  }, [])

  const loadRca = useCallback(async () => {
    setRcaLoading(true)
    try {
      const res = await api.get<RCAConfig>('/api/v1/config/rca')
      setRcaConfig(res.data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(`Failed to load RCA config: ${msg}`)
    } finally {
      setRcaLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'alerts' && !alertsState.loaded && !alertsState.loading) {
      loadAlerts()
    }
    if (activeTab === 'rules' && !rulesState.loaded && !rulesState.loading) {
      loadRules()
    }
    if (activeTab === 'rca') {
      loadRca()
    }
  }, [activeTab, alertsState.loaded, alertsState.loading, rulesState.loaded, rulesState.loading, loadAlerts, loadRules, loadRca])

  const saveRca = async () => {
    setRcaSaving(true)
    try {
      await api.put('/api/v1/config/rca', rcaConfig)
      toast.success('RCA config saved')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(`Save failed: ${msg}`)
    } finally {
      setRcaSaving(false)
    }
  }

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

  const appendToRules = (yamlBlock: string) => {
    setRulesState((s) => {
      const current = s.content.trimEnd()
      // If empty or just a comment, start fresh with boilerplate
      if (!current || current === '# No content loaded yet') {
        return { ...s, content: `rules:\n${yamlBlock}\n` }
      }
      // If content doesn't start with "rules:", prepend it
      let next = current
      if (!next.includes('rules:')) {
        next = `rules:\n${next}`
      }
      // Append with a blank line separator
      return { ...s, content: `${next}\n\n${yamlBlock}\n` }
    })
  }

  return (
    <div className="h-full flex flex-col space-y-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="h-5 w-5 text-zinc-500" />
        <h2 className="text-xl font-semibold">Settings</h2>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as TabId)} className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="alerts">alerts.yaml</TabsTrigger>
            <TabsTrigger value="rules">detection_rules.yaml</TabsTrigger>
            <TabsTrigger value="rca">RCA Config</TabsTrigger>
          </TabsList>
          <div className="flex items-center gap-2">
            {activeTab === 'rules' && (
              <RuleTemplates onAppend={appendToRules} />
            )}
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
            {activeTab === 'rca' && (
              <Button
                size="sm"
                onClick={saveRca}
                disabled={rcaSaving}
              >
                {rcaSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
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
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-full">
              <div className="lg:col-span-2 h-full min-h-[300px]">
                <YamlEditor
                  value={alertsState.content}
                  onChange={(v) => setAlertsState((s) => ({ ...s, content: v }))}
                  error={alertsState.error}
                />
              </div>
              <div className="h-full min-h-[200px]">
                <AlertsHelpPanel />
              </div>
            </div>
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
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-full">
              <div className="lg:col-span-2 h-full min-h-[300px]">
                <YamlEditor
                  value={rulesState.content}
                  onChange={(v) => setRulesState((s) => ({ ...s, content: v }))}
                  error={rulesState.error}
                />
              </div>
              <div className="h-full min-h-[200px]">
                <RulesHelpPanel />
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="rca" className="flex-1 min-h-0 mt-2">
          {rcaLoading ? (
            <div className="flex items-center justify-center h-64 text-zinc-400">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : (
            <div className="max-w-xl space-y-6">
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <BrainCircuit className="h-4 w-4" />
                <span>Configure the LLM backend for automated root-cause analysis.</span>
              </div>

              <div className="space-y-4 bg-white border border-zinc-200 rounded-lg p-6">
                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">Backend</label>
                  <select
                    value={rcaConfig.backend}
                    onChange={(e) => setRcaConfig({ ...rcaConfig, backend: e.target.value })}
                    className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  >
                    <option value="disabled">Disabled</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="ollama">Ollama</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">Model</label>
                  <input
                    type="text"
                    value={rcaConfig.model}
                    onChange={(e) => setRcaConfig({ ...rcaConfig, model: e.target.value })}
                    placeholder={rcaConfig.backend === 'openai' ? 'gpt-4o' : rcaConfig.backend === 'anthropic' ? 'claude-sonnet-4' : 'llama3'}
                    className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">Base URL</label>
                  <input
                    type="text"
                    value={rcaConfig.base_url}
                    onChange={(e) => setRcaConfig({ ...rcaConfig, base_url: e.target.value })}
                    placeholder={rcaConfig.backend === 'ollama' ? 'http://localhost:11434' : ''}
                    className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <p className="text-[10px] text-zinc-400 mt-1">Only needed for Ollama or custom proxies.</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-500 mb-1">Max Tokens</label>
                  <input
                    type="number"
                    value={rcaConfig.max_tokens}
                    onChange={(e) => setRcaConfig({ ...rcaConfig, max_tokens: parseInt(e.target.value) || 2048 })}
                    className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>

                {rcaConfig.backend !== 'disabled' && rcaConfig.backend !== 'ollama' && (
                  <div>
                    <label className="block text-xs font-medium text-zinc-500 mb-1">
                      API Key {rcaConfig.api_key_present && <span className="text-emerald-600">(already set)</span>}
                    </label>
                    <input
                      type="password"
                      value={rcaConfig.api_key_present ? '' : ''}
                      onChange={(e) => setRcaConfig({ ...rcaConfig, api_key: e.target.value })}
                      placeholder={rcaConfig.api_key_present ? '••••••••' : 'sk-...'}
                      className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                    <p className="text-[10px] text-zinc-400 mt-1">Leave blank to keep existing key.</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
