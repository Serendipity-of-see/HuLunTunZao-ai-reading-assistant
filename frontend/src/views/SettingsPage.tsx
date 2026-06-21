import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import { useToast } from '../components/common/Toast'

type TestResult = { valid: boolean; message: string } | null

const CardIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <rect x="3" y="5" width="18" height="14" rx="2"/>
    <path d="M3 10h18"/>
    <path d="M8 3v4"/>
    <path d="M16 3v4"/>
  </svg>
)

const KeyIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="7" cy="12" r="5"/>
    <path d="M11 12h10l-2 3h-2v2h-2l-2-3"/>
  </svg>
)

const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <circle cx="12" cy="12" r="10"/>
    <ellipse cx="12" cy="12" rx="4" ry="10"/>
    <path d="M2 12h20"/>
  </svg>
)

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState('')
  const [apiBaseUrl, setApiBaseUrl] = useState('')
  const [savedUrl, setSavedUrl] = useState('')
  const [hasKey, setHasKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TestResult>(null)
  const keyRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  useEffect(() => {
    api.getSettings().then(s => {
      if (s.api_key_configured) setHasKey(true)
      setApiBaseUrl(s.api_base_url)
      setSavedUrl(s.api_base_url)
    }).catch(() => {})
  }, [])

  const canSave = !saving && (!!apiKey.trim() || (hasKey && apiBaseUrl !== savedUrl))

  const handleSave = async () => {
    if (!apiKey.trim() && !hasKey) { toast('请输入 API Key', 'error'); return }
    setSaving(true)
    try {
      await api.updateSettings(apiKey.trim(), apiBaseUrl)
      setApiKey(''); setSavedUrl(apiBaseUrl); setHasKey(true)
      toast('已保存', 'success')
    }
    catch (e: any) { toast(e.message, 'error') }
    setSaving(false)
  }

  const handleTest = async () => {
    setTesting(true); setTestResult(null)
    try { setTestResult(await api.validateApiKey()) }
    catch (e: any) { setTestResult({ valid: false, message: e.message }) }
    setTesting(false)
  }

  const btnBase = `
    relative overflow-hidden rounded-lg
    text-[13px] font-medium tracking-wide
    transition-all duration-200 ease-out
    focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#C4523A]
    disabled:cursor-not-allowed
  `

  return (
    <div className="flex flex-col items-center h-full overflow-y-auto"
      style={{ background: 'linear-gradient(180deg, #FBF7F0 0%, #F5EDE0 100%)' }}>
      <div className="w-full max-w-lg px-8 py-14 space-y-10">

        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight"
            style={{ fontFamily: 'var(--font-display)', color: '#2E2720' }}>
            设置
          </h1>
          <div className="flex items-center gap-2">
            <div className="h-px flex-1" style={{ background: 'linear-gradient(90deg, #C4523A, transparent)' }}/>
            <span className="text-xs tracking-widest uppercase"
              style={{ fontFamily: 'var(--font-ui)', color: '#C4523A', letterSpacing: '0.15em' }}>
              Configuration
            </span>
          </div>
        </div>

        {/* API Key Card */}
        <div className="group relative rounded-xl p-6 transition-shadow duration-300 hover:shadow-lg"
          style={{
            background: '#FFFCF5',
            border: '1px solid #E0D6C8',
            boxShadow: '0 2px 4px rgba(26,20,16,0.03), 0 0 0 1px rgba(196,82,58,0)',
          }}
          onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 12px rgba(26,20,16,0.06), 0 0 0 1px rgba(196,82,58,0.15)'}
          onMouseLeave={e => e.currentTarget.style.boxShadow = '0 2px 4px rgba(26,20,16,0.03), 0 0 0 1px rgba(196,82,58,0)'}
        >
          {/* Card hole punch decoration */}
          <div className="absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full"
            style={{ background: '#FBF7F0', border: '1px solid #D8CCB8', boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.08)' }}/>

          <div className="flex items-center gap-2 mb-4">
            <span style={{ color: '#C4523A' }}><KeyIcon/></span>
            <label className="text-xs font-semibold tracking-widest uppercase"
              style={{ fontFamily: 'var(--font-ui)', color: '#6B5E53', letterSpacing: '0.12em' }}>
              API Key
            </label>
            {hasKey && (
              <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium"
                style={{ fontFamily: 'var(--font-ui)', color: '#5B8C5A', background: 'rgba(91,140,90,0.08)' }}>
                已配置
              </span>
            )}
          </div>

          <div className="relative">
            <input
              ref={keyRef}
              type="password"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder={hasKey ? '··· 留空则不修改' : 'sk-...'}
              className="w-full px-4 py-3 text-sm bg-transparent outline-none transition-all duration-200
                         rounded-lg placeholder:font-light"
              style={{
                fontFamily: 'var(--font-ui)',
                color: '#2E2720',
                border: '1px solid #E0D6C8',
                background: 'rgba(251,247,240,0.4)',
              }}
              onFocus={e => { e.target.style.borderColor = '#C4523A'; e.target.style.boxShadow = '0 0 0 3px rgba(196,82,58,0.08)' }}
              onBlur={e => { e.target.style.borderColor = '#E0D6C8'; e.target.style.boxShadow = 'none' }}
            />
          </div>
        </div>

        {/* API Endpoint Card */}
        <div className="group relative rounded-xl p-6 transition-shadow duration-300 hover:shadow-lg"
          style={{
            background: '#FFFCF5',
            border: '1px solid #E0D6C8',
            boxShadow: '0 2px 4px rgba(26,20,16,0.03), 0 0 0 1px rgba(184,149,74,0)',
          }}
          onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 12px rgba(26,20,16,0.06), 0 0 0 1px rgba(184,149,74,0.15)'}
          onMouseLeave={e => e.currentTarget.style.boxShadow = '0 2px 4px rgba(26,20,16,0.03), 0 0 0 1px rgba(184,149,74,0)'}
        >
          <div className="absolute -left-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full"
            style={{ background: '#FBF7F0', border: '1px solid #D8CCB8', boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.08)' }}/>

          <div className="flex items-center gap-2 mb-4">
            <span style={{ color: '#B8954A' }}><GlobeIcon/></span>
            <label className="text-xs font-semibold tracking-widest uppercase"
              style={{ fontFamily: 'var(--font-ui)', color: '#6B5E53', letterSpacing: '0.12em' }}>
              API 端点
            </label>
            {apiBaseUrl !== savedUrl && (
              <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium animate-fade-in"
                style={{ fontFamily: 'var(--font-ui)', color: '#C4943A', background: 'rgba(196,148,58,0.08)' }}>
                已修改
              </span>
            )}
          </div>

          <input
            type="text"
            value={apiBaseUrl}
            onChange={e => setApiBaseUrl(e.target.value)}
            className="w-full px-4 py-3 text-sm bg-transparent outline-none transition-all duration-200
                       rounded-lg font-mono placeholder:font-light"
            style={{
              color: '#2E2720',
              border: '1px solid #E0D6C8',
              background: 'rgba(251,247,240,0.4)',
              fontSize: '12px',
            }}
            onFocus={e => { e.target.style.borderColor = '#B8954A'; e.target.style.boxShadow = '0 0 0 3px rgba(184,149,74,0.08)' }}
            onBlur={e => { e.target.style.borderColor = '#E0D6C8'; e.target.style.boxShadow = 'none' }}
          />
          <p className="mt-3 text-[11px] leading-relaxed"
            style={{ fontFamily: 'var(--font-ui)', color: '#A89880' }}>
            兼容 OpenAI 接口格式。默认使用 DeepSeek 官方 API。
          </p>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={!canSave}
            className={`${btnBase} flex-1 py-3`}
            style={canSave ? {
              color: '#FFFFFF',
              backgroundColor: '#C4523A',
              boxShadow: '0 2px 4px rgba(196,82,58,0.25), 0 0 0 0 rgba(196,82,58,0)',
              fontFamily: 'var(--font-ui)',
            } : {
              color: '#A89880',
              backgroundColor: '#EDE5D8',
              fontFamily: 'var(--font-ui)',
            }}
            onMouseEnter={canSave ? e => { e.currentTarget.style.backgroundColor = '#B8452E'; e.currentTarget.style.boxShadow = '0 4px 8px rgba(196,82,58,0.3), 0 0 0 4px rgba(196,82,58,0.06)'; e.currentTarget.style.transform = 'translateY(-1px)' } : undefined}
            onMouseLeave={canSave ? e => { e.currentTarget.style.backgroundColor = '#C4523A'; e.currentTarget.style.boxShadow = '0 2px 4px rgba(196,82,58,0.25), 0 0 0 0 rgba(196,82,58,0)'; e.currentTarget.style.transform = 'translateY(0)' } : undefined}
            onMouseDown={canSave ? e => { e.currentTarget.style.transform = 'scale(0.97)' } : undefined}
            onMouseUp={canSave ? e => { e.currentTarget.style.transform = 'translateY(-1px)' } : undefined}
          >
            <span className="flex items-center justify-center gap-2">
              {saving ? (
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"/>
              ) : (
                <CardIcon/>
              )}
              {saving ? '保存中...' : '保存'}
            </span>
          </button>

          <button
            onClick={handleTest}
            disabled={testing}
            className={`${btnBase} px-6 py-3`}
            style={!testing ? {
              color: '#6B5E53',
              backgroundColor: '#FFFCF5',
              border: '1px solid #D8CCB8',
              fontFamily: 'var(--font-ui)',
            } : {
              color: '#A89880',
              backgroundColor: '#F3EDE3',
              border: '1px solid #E0D6C8',
              fontFamily: 'var(--font-ui)',
            }}
            onMouseEnter={!testing ? e => { e.currentTarget.style.color = '#2E2720'; e.currentTarget.style.borderColor = '#B8954A'; e.currentTarget.style.backgroundColor = '#FFF9F0' } : undefined}
            onMouseLeave={!testing ? e => { e.currentTarget.style.color = '#6B5E53'; e.currentTarget.style.borderColor = '#D8CCB8'; e.currentTarget.style.backgroundColor = '#FFFCF5' } : undefined}
          >
            {testing ? (
              <span className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 border-2 border-[#A89880]/30 border-t-[#A89880] rounded-full animate-spin"/>
                测试中...
              </span>
            ) : '测试连接'}
          </button>
        </div>

        {/* Test Result */}
        {testResult && (
          <div className="animate-slide-up rounded-xl p-5 transition-all duration-300"
            style={testResult.valid ? {
              background: 'rgba(91,140,90,0.06)',
              border: '1px solid rgba(91,140,90,0.15)',
            } : {
              background: 'rgba(196,82,58,0.05)',
              border: '1px solid rgba(196,82,58,0.12)',
            }}>
            <div className="flex items-start gap-3">
              <span className="mt-0.5 text-lg">
                {testResult.valid ? '✓' : '✗'}
              </span>
              <div>
                <p className="text-sm font-medium"
                  style={{ fontFamily: 'var(--font-ui)', color: testResult.valid ? '#5B8C5A' : '#C4523A' }}>
                  {testResult.valid ? '连接成功' : '连接失败'}
                </p>
                <p className="text-xs mt-1 leading-relaxed"
                  style={{ fontFamily: 'var(--font-ui)', color: '#8A7A6A' }}>
                  {testResult.message}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
