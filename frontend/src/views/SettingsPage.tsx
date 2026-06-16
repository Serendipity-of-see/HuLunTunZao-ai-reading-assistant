import { useState, useEffect } from 'react'
import { api } from '../api/client'

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState('')
  const [masked, setMasked] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    api.getSettings().then(s => {
      if (s.api_key_configured) setMasked(s.api_key_masked)
    })
  }, [])

  const handleSave = async () => {
    if (!apiKey.trim()) return
    setSaving(true)
    setMessage(null)
    try {
      await api.updateSettings(apiKey.trim())
      setMasked(apiKey.trim().length > 8
        ? apiKey.slice(0, 4) + '*'.repeat(apiKey.length - 8) + apiKey.slice(-4)
        : apiKey.slice(0, 2) + '*'.repeat(apiKey.length - 2))
      setApiKey('')
      setMessage({ type: 'success', text: '已保存' })
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setMessage(null)
    try {
      const r = await api.validateApiKey()
      setMessage({ type: r.valid ? 'success' : 'error', text: r.message })
    } catch (e: any) {
      setMessage({ type: 'error', text: e.message })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex flex-col items-center h-full gap-6 p-8 overflow-y-auto">
      <h1 className="text-xl font-medium text-[var(--text-primary)]">设置</h1>

      {/* API Key */}
      <div className="w-full max-w-md space-y-3">
        <div>
          <label className="text-sm text-[var(--text-secondary)]">DeepSeek API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder={masked ? `当前: ${masked}` : 'sk-...'}
            className="w-full mt-1 px-3 py-2 text-sm border border-[var(--border)] rounded bg-[var(--bg-surface)] outline-none focus:border-[var(--emphasis)]"
          />
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleSave}
            disabled={saving || !apiKey.trim()}
            className="flex-1 px-4 py-2 text-sm bg-[var(--text-primary)] text-white rounded hover:opacity-80 disabled:opacity-40 transition-opacity"
          >
            {saving ? '保存中...' : '保存'}
          </button>
          <button
            onClick={handleTest}
            disabled={testing}
            className="flex-1 px-4 py-2 text-sm border border-[var(--border)] rounded hover:bg-[var(--bg-hover)] disabled:opacity-40 transition-colors"
          >
            {testing ? '测试中...' : '测试连接'}
          </button>
        </div>

        {message && (
          <p className={`text-sm ${message.type === 'success' ? 'text-emerald-600' : 'text-red-500'}`}>
            {message.text}
          </p>
        )}

        <p className="text-xs text-[var(--text-tertiary)]">
          API Key 保存在本地 <code>~/.huluntunzao/config.json</code>，不会上传到任何服务器。
        </p>
      </div>
    </div>
  )
}
