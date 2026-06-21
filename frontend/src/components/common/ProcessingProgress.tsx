import { useEffect, useRef, useState } from 'react'
import type { ProgressEvent, TreeNode } from '../../types'
import { createProgressStream } from '../../api/sse'
import { api } from '../../api/client'

interface Props {
  bookId: number
  bookTitle?: string
  onComplete: () => void
  onError: (message: string) => void
  collapsed?: boolean
  onToggleCollapse?: () => void
  onTreeRefresh?: () => void
  onNodeAdd?: (parentId: number, node: TreeNode) => void
  onNodeDelete?: (nodeId: number) => void
}

// ── 步骤定义 ────────────────────────────────────────────────
const STEPS = [
  { key: 'parse', short: '解析', label: '章节解析' },
  { key: 'l4', short: '分组', label: '语义分组' },
  { key: 'l3', short: '场景', label: '场景聚合' },
  { key: 'l2_global', short: '聚合', label: '跨章聚合' },
  { key: 'l1_merge', short: '叙事', label: '宏观叙事' },
] as const

type StepKey = (typeof STEPS)[number]['key']

// ── 步骤图标 SVG ────────────────────────────────────────────
const StepIcon = ({ step, active }: { step: StepKey; active: boolean }) => {
  const color = active ? 'var(--accent)' : 'var(--text-tertiary)'
  const paths: Record<StepKey, JSX.Element> = {
    parse: <path d="M4 6h16M4 12h16M4 18h12" stroke={color} strokeWidth="1.5" strokeLinecap="round" fill="none"/>,
    l4: <><rect x="3" y="3" width="7" height="7" rx="1" stroke={color} strokeWidth="1.2" fill="none"/><rect x="14" y="3" width="7" height="7" rx="1" stroke={color} strokeWidth="1.2" fill="none"/><rect x="3" y="14" width="7" height="7" rx="1" stroke={color} strokeWidth="1.2" fill="none"/><rect x="14" y="14" width="7" height="7" rx="1" stroke={color} strokeWidth="1.2" fill="none"/></>,
    l3: <><circle cx="12" cy="6" r="2" stroke={color} strokeWidth="1.2" fill="none"/><circle cx="6" cy="18" r="2" stroke={color} strokeWidth="1.2" fill="none"/><circle cx="18" cy="18" r="2" stroke={color} strokeWidth="1.2" fill="none"/><line x1="11" y1="8" x2="7" y2="16" stroke={color} strokeWidth="0.8"/><line x1="13" y1="8" x2="17" y2="16" stroke={color} strokeWidth="0.8"/></>,
    l2_global: <><circle cx="12" cy="6" r="2" stroke={color} strokeWidth="1.2" fill="none"/><circle cx="12" cy="18" r="2" stroke={color} strokeWidth="1.2" fill="none"/><line x1="12" y1="8" x2="12" y2="16" stroke={color} strokeWidth="1" strokeLinecap="round"/><line x1="12" y1="16" x2="16" y2="20" stroke={color} strokeWidth="0.8" strokeLinecap="round"/><line x1="12" y1="16" x2="8" y2="20" stroke={color} strokeWidth="0.8" strokeLinecap="round"/></>,
    l1_merge: <><polygon points="12,3 15,9 21,9 16.5,13 18,19 12,16 6,19 7.5,13 3,9 9,9" stroke={color} strokeWidth="1.2" fill="none" strokeLinejoin="round"/></>,
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
      style={{ display: 'block', opacity: active ? 1 : 0.5, transition: 'opacity 300ms var(--ease-out)' }}>
      {paths[step]}
    </svg>
  )
}

// ── 主组件 ──────────────────────────────────────────────────
export default function ProcessingProgress({ bookId, bookTitle, onComplete, onError, collapsed, onToggleCollapse, onTreeRefresh, onNodeAdd, onNodeDelete }: Props) {
  const [phase, setPhase] = useState<'connecting' | 'processing' | 'disconnected' | 'error'>('connecting')
  const [currentStep, setCurrentStep] = useState<StepKey | null>(null)
  const [completedSteps, setCompletedSteps] = useState<Set<StepKey>>(new Set())
  const [stepLabel, setStepLabel] = useState('')
  const [progressCurrent, setProgressCurrent] = useState(0)
  const [progressTotal, setProgressTotal] = useState(0)
  const [progressPct, setProgressPct] = useState(0)
  const [recentTitles, setRecentTitles] = useState<{ title: string; isNew: boolean; id: number }[]>([])
  const [errorMsg, setErrorMsg] = useState('')
  const [isIndeterminate, setIsIndeterminate] = useState(false)
  const [tokensIn, setTokensIn] = useState(0)
  const [tokensOut, setTokensOut] = useState(0)
  const [cancelling, setCancelling] = useState(false)
  const [streamText, setStreamText] = useState("")
  const [reasoningText, setReasoningText] = useState("")
  const [showReasoning, setShowReasoning] = useState(false)
  const [stats, setStats] = useState<{ elapsed: number; tokensIn: number; tokensOut: number } | null>(null)

  // 重置思考文本（key 变化时清空）
  useEffect(() => {
    setReasoningText("")
    setShowReasoning(false)
    setStreamText("")
    setStats(null)
  }, [bookId])

  const titleIdRef = useRef(0)
  const [totalChapters, setTotalChapters] = useState<number | null>(null)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError
  const onTreeRefreshRef = useRef(onTreeRefresh)
  onTreeRefreshRef.current = onTreeRefresh
  const onNodeAddRef = useRef(onNodeAdd)
  onNodeAddRef.current = onNodeAdd
  const onNodeDeleteRef = useRef(onNodeDelete)
  onNodeDeleteRef.current = onNodeDelete

  // ── 处理事件 ──────────────────────────────────────────────
  const handleEvent = (ev: ProgressEvent) => {
    switch (ev.type) {
      case 'context':
        if (ev.total_chapters != null) setTotalChapters(ev.total_chapters)
        break

      case 'snapshot': {
        if (ev.overall_status === 'complete') { onCompleteRef.current(); return }
        if (ev.overall_status === 'failed') {
          setPhase('error')
          setErrorMsg('处理失败，请重试')
          return
        }
        setPhase('processing')
        if (ev.current_step) setCurrentStep(ev.current_step as StepKey)
        if (ev.step_label) setStepLabel(ev.step_label)
        if (ev.step_progress_current != null) setProgressCurrent(ev.step_progress_current)
        if (ev.step_progress_total != null) setProgressTotal(ev.step_progress_total)
        if (ev.progress_pct != null) setProgressPct(ev.progress_pct)
        if (ev.recent_details) {
          setRecentTitles(ev.recent_details.map(d => ({ title: d.title, isNew: d.is_new, id: ++titleIdRef.current })))
        }
        if (ev.steps_completed) setCompletedSteps(new Set(ev.steps_completed as StepKey[]))
        break
      }

      case 'step_start': {
        setPhase('processing')
        const step = (ev.step || ev.label) as StepKey
        if (step) setCurrentStep(step)
        setStepLabel(ev.label || '')
        setProgressCurrent(0)
        if (ev.total != null) { setProgressTotal(ev.total); setIsIndeterminate(false) }
        else if (step === 'l2_global' || step === 'l1_merge') { setIsIndeterminate(true) }
        break
      }

      case 'l3_progress': {
        setPhase('processing')
        if (ev.current != null) setProgressCurrent(ev.current)
        if (ev.total != null) setProgressTotal(ev.total)
        setIsIndeterminate(false)
        const title = ev.scene_title || ''
        if (title) {
          const newId = ++titleIdRef.current
          setRecentTitles(prev => {
            const next = [...prev, { title, isNew: ev.is_new ?? false, id: newId }]
            return next.length > 8 ? next.slice(-8) : next
          })
        }
        // 进度百分比估算
        if (ev.current != null && ev.total != null && ev.total > 0) {
          setProgressPct(15 + (ev.current / ev.total) * 70)
          if (ev.tokens_in != null) setTokensIn(ev.tokens_in)
          if (ev.tokens_out != null) setTokensOut(ev.tokens_out)
        }
        break
      }

      case 'progress': {
        if (ev.current != null && ev.total != null && ev.total > 0) {
          setProgressCurrent(ev.current)
          setProgressTotal(ev.total)
          if (ev.step === 'l4') {
            setProgressPct(5 + (ev.current / ev.total) * 10)
          }
        }
        break
      }

      case 'step_complete': {
        const step = ev.step as StepKey
        if (step) {
          setCompletedSteps(prev => new Set([...prev, step]))
          // 估算百分比
          const idx = STEPS.findIndex(s => s.key === step)
          if (idx >= 0) {
            const weights = [5, 10, 70, 7, 5]
            let pct = 0
            for (let i = 0; i <= idx; i++) pct += weights[i]
            setProgressPct(Math.min(pct, 99.9))
          }
        }
        break
      }

      case 'complete':
        onCompleteRef.current()
        break

      case 'stream':
        if (ev.text) setStreamText(ev.text)
        break
      case 'reasoning':
        if (ev.text) setReasoningText(prev => prev + ev.text!)
        break
      case 'tree_refresh':
        onTreeRefreshRef.current?.()
        break
      case 'node_add':
        if (ev.parent_id != null && ev.node) onNodeAddRef.current?.(ev.parent_id, ev.node)
        break
      case 'node_delete':
        if (ev.node_id != null) onNodeDeleteRef.current?.(ev.node_id)
        break
      case 'tokens':
        if (ev.tokens_in != null) setTokensIn(ev.tokens_in)
        if (ev.tokens_out != null) setTokensOut(ev.tokens_out)
        break

      case 'stats':
        if (ev.total_elapsed != null) {
          setStats({ elapsed: ev.total_elapsed, tokensIn: ev.total_tokens_in ?? 0, tokensOut: ev.total_tokens_out ?? 0 })
        }
        break

      case 'error':
        setPhase('error')
        setErrorMsg(ev.message || '处理失败')
        onErrorRef.current(ev.message || '处理失败')
        break
    }
  }

  // ── SSE 生命周期 ──────────────────────────────────────────
  useEffect(() => {
    const controller = new AbortController()

    const { close } = createProgressStream(
      bookId,
      {
        onEvent: handleEvent,
        onDisconnect: () => setPhase('disconnected'),
      },
      controller.signal,
    )

    return () => {
      controller.abort()
      close()
    }
  }, [bookId])

  // ── 步骤指示器渲染 ───────────────────────────────────────
  const currentStepIdx = currentStep ? STEPS.findIndex(s => s.key === currentStep) : -1

  const renderStepDots = () => (
    <div className="flex items-center justify-center gap-0" style={{ fontFamily: 'var(--font-ui)' }}>
      {STEPS.map((s, i) => {
        const done = completedSteps.has(s.key)
        const active = s.key === currentStep
        const pending = !done && !active

        return (
          <div key={s.key} className="flex items-center">
            {i > 0 && (
              <div className="w-6 h-px mx-1 transition-colors"
                style={{ background: done || (i <= currentStepIdx) ? 'var(--accent)' : 'var(--border-light)' }} />
            )}
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex items-center justify-center rounded-full transition-all ${active ? 'animate-progress-pulse' : ''}`}
                style={{
                  width: 28, height: 28,
                  background: done ? 'var(--success)' : active ? 'var(--accent)' : 'var(--bg-hover)',
                  border: pending ? '1.5px solid var(--border)' : 'none',
                  animation: active ? undefined : undefined, // handled by class
                }}
              >
                {done ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M5 13l4 4L19 7" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                ) : (
                  <span style={{
                    fontSize: 10, fontWeight: 500,
                    color: active ? 'white' : 'var(--text-tertiary)',
                  }}>
                    {i + 1}
                  </span>
                )}
              </div>
              <span style={{
                fontSize: 11, fontWeight: active ? 500 : 400,
                color: active ? 'var(--accent)' : done ? 'var(--text-secondary)' : 'var(--text-tertiary)',
                transition: 'color 300ms var(--ease-out)',
              }}>
                {s.short}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )

  // ── 折叠模式 ────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="shrink-0 flex items-center gap-3 px-4 py-1.5 border-b cursor-pointer"
        style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border)' }}
        onClick={onToggleCollapse}
      >
        {currentStep && <StepIcon step={currentStep} active />}
        <span className="text-[11px] font-medium" style={{ fontFamily: 'var(--font-ui)', color: 'var(--accent)' }}>
          {stepLabel || '解析中...'}
        </span>
        <div className="flex-1 h-1 rounded-full" style={{ backgroundColor: 'var(--border-light)' }}>
          <div className="h-full rounded-full transition-all duration-500"
            style={{ width: `${Math.max(progressPct || 1, 1)}%`, backgroundColor: 'var(--accent)' }} />
        </div>
        <span className="text-[10px] shrink-0" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
          {isIndeterminate ? '···' : `${Math.round(progressPct)}%`}
        </span>
        {stats && (
          <span className="text-[9px] shrink-0" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
            {(tokensIn + tokensOut) > 0 ? ` ${((tokensIn + tokensOut)/1000).toFixed(0)}K tok` : ''}
          </span>
        )}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
          <path d="M6 9l6 6 6-6" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </div>
    )
  }

  // ── 连接中状态 ────────────────────────────────────────────
  if (phase === 'connecting') {
    return (
      <div style={{ maxWidth: 420, margin: '60px auto 0', textAlign: 'center' }}>
        <div className="animate-connecting" style={{ marginBottom: 16, color: 'var(--text-tertiary)' }}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" style={{ margin: '0 auto', opacity: 0.6 }}>
            <circle cx="12" cy="12" r="3" stroke="var(--accent)" strokeWidth="1.5"/>
            <path d="M12 1v4M12 19v4M1 12h4M19 12h4" stroke="var(--text-tertiary)" strokeWidth="1" strokeLinecap="round"/>
          </svg>
        </div>
        <p style={{ fontFamily: 'var(--font-display)', fontSize: 15, color: 'var(--text-secondary)', margin: 0 }}>
          正在连接处理服务...
        </p>
      </div>
    )
  }

  // ── 处理中 / 断连 / 错误状态 ─────────────────────────────
  return (
    <div style={{ maxWidth: 420, margin: '40px auto 0', textAlign: 'center' }}>
      {/* ── 标题 ── */}
      <div className="animate-fade-in" style={{ marginBottom: 28 }}>
        <div className="flex items-center justify-center gap-2">
          <h2 style={{
            fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 600,
            color: 'var(--text-primary)', margin: 0, letterSpacing: '0.02em',
          }}>
            {bookTitle ? `《${bookTitle}》` : '文本解析中'}
          </h2>
          {onToggleCollapse && (
            <button onClick={onToggleCollapse} className="p-1 rounded hover:bg-[var(--bg-hover)] transition-colors"
              title="收起面板" style={{ border: 'none', background: 'none', cursor: 'pointer' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M6 15l6-6 6 6" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>
        <p style={{ fontFamily: 'var(--font-ui)', fontSize: 12, color: 'var(--text-tertiary)', margin: 0 }}>
          {totalChapters ? `共 ${totalChapters} 章 · ` : ''}AI 正在逐句理解文本结构
        </p>
      </div>

      {/* ── 统计摘要 ── */}
      {stats && (
        <div className="animate-fade-in flex items-center justify-center gap-4" style={{ marginBottom: 18 }}>
          <span style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-tertiary)' }}>
            ⏱ {stats.elapsed < 60 ? `${stats.elapsed}秒` : `${Math.floor(stats.elapsed / 60)}分${stats.elapsed % 60}秒`}
          </span>
          <span style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-tertiary)' }}>
            📥 {(stats.tokensIn / 1000).toFixed(1)}K
          </span>
          <span style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-tertiary)' }}>
            📤 {(stats.tokensOut / 1000).toFixed(1)}K
          </span>
        </div>
      )}

      {/* ── 步骤指示器 ── */}
      <div className="animate-slide-up" style={{ marginBottom: 24 }}>
        {renderStepDots()}
      </div>

      {/* ── 当前步骤 ── */}
      <div className="animate-fade-in" style={{ marginBottom: 16 }}>
        <div className="flex items-center justify-center gap-2">
          {currentStep && <StepIcon step={currentStep} active />}
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 500,
            color: 'var(--text-body)',
          }}>
            {phase === 'error' ? '处理中断' : stepLabel || '准备中...'}
          </span>
        </div>
      </div>

      {/* ── 进度条 ── */}
      <div className="animate-slide-up" style={{ marginBottom: 12 }}>
        <div className="flex items-center gap-3" style={{ maxWidth: 340, margin: '0 auto' }}>
          <div style={{
            flex: 1, height: 4, borderRadius: 2,
            background: 'var(--border-light)',
            overflow: 'hidden',
          }} className={isIndeterminate ? 'progress-shimmer' : ''}>
            <div style={{
              height: '100%',
              width: isIndeterminate ? '50%' : `${Math.max(progressPct, 1)}%`,
              borderRadius: 2,
              background: phase === 'error' ? 'var(--error)' : 'var(--accent)',
              transition: 'width 400ms var(--ease-out)',
            }}
            className={!isIndeterminate && progressPct > 0 && progressPct < 100 ? 'animate-bar-glow' : ''}
            />
          </div>
          <span style={{
            fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 500,
            color: 'var(--text-secondary)', minWidth: 36, textAlign: 'right',
          }}>
            {isIndeterminate ? '···' : `${Math.round(progressPct)}%`}
          </span>
        </div>
        {/* 进度数字 */}
        {!isIndeterminate && progressTotal > 0 && (
          <p style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-tertiary)', margin: '6px 0 0' }}>
            第 {progressCurrent} / {progressTotal} 组
          </p>
        )}
      </div>

      {/* ── 场景标题流 ── */}
      {recentTitles.length > 0 && (
        <div className="animate-slide-up" style={{
          maxWidth: 360, margin: '20px auto 0',
          textAlign: 'left',
          borderLeft: '1.5px solid var(--border-light)',
          paddingLeft: 14,
        }}>
          <div style={{
            fontFamily: 'var(--font-ui)', fontSize: 10, fontWeight: 500,
            color: 'var(--text-tertiary)', textTransform: 'uppercase',
            letterSpacing: '0.08em', marginBottom: 8,
          }}>
            正在生成的场景
          </div>
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {recentTitles.map((item) => (
              <div
                key={item.id}
                className="animate-ink-reveal"
                style={{
                  fontSize: 13, fontFamily: 'var(--font-body)',
                  color: item.isNew ? 'var(--accent)' : 'var(--gold)',
                  padding: '4px 6px', marginBottom: 2,
                  borderRadius: 3,
                  display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <span style={{
                  fontSize: 11, fontWeight: 600, flexShrink: 0,
                  color: item.isNew ? 'var(--accent)' : 'var(--gold)',
                }}>
                  {item.isNew ? '+' : '~'}
                </span>
                <span style={{
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {item.title.length > 30 ? item.title.slice(0, 30) + '…' : item.title}
                </span>
                {item.isNew && (
                  <span style={{
                    fontSize: 9, fontWeight: 500, flexShrink: 0,
                    color: 'var(--accent)', opacity: 0.7,
                    border: '1px solid var(--accent-soft)', borderRadius: 3,
                    padding: '0 4px', lineHeight: '16px',
                  }}>
                    新场景
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 错误状态 ── */}
      {phase === 'error' && (
        <div className="animate-slide-up" style={{ marginTop: 20 }}>
          <p style={{
            fontFamily: 'var(--font-ui)', fontSize: 13,
            color: 'var(--error)', margin: '0 0 12px',
          }}>
            {errorMsg}
          </p>
          <button
            className="btn-base"
            onClick={() => onErrorRef.current(errorMsg)}
            style={{
              fontFamily: 'var(--font-ui)', fontSize: 13, fontWeight: 500,
              padding: '8px 20px', borderRadius: 'var(--radius-md)',
              border: 'none', cursor: 'pointer',
              color: 'white', background: 'var(--accent)',
              transition: 'background var(--duration-fast) var(--ease-out)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--accent)')}
          >
            重试
          </button>
        </div>
      )}

      {/* ── 断连徽章 ── */}
      {phase === 'disconnected' && (
        <div className="animate-badge-slide-in" style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          marginTop: 8, padding: '3px 10px', borderRadius: 10,
          background: 'var(--gold-soft)', border: '1px solid var(--gold)',
          fontFamily: 'var(--font-ui)', fontSize: 11,
          color: 'var(--gold)',
        }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="var(--gold)" strokeWidth="2"/>
            <path d="M12 8v4M12 16h.01" stroke="var(--gold)" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          已切换到轮询模式
        </div>
      )}

      {/* ── 思考过程 ── */}
      {reasoningText && (
        <div className="animate-slide-up" style={{ maxWidth: 400, margin: '12px auto 0', textAlign: 'left' }}>
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex items-center gap-1 w-full text-left"
            style={{ fontFamily: 'var(--font-ui)', fontSize: 10, color: 'var(--accent)', cursor: 'pointer',
              border: 'none', background: 'none', padding: '2px 0' }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
              style={{ transform: showReasoning ? 'rotate(90deg)' : 'none', transition: 'transform 200ms' }}>
              <path d="M9 18l6-6-6-6" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            思考过程 ({reasoningText.length.toLocaleString()} 字符)
          </button>
          {showReasoning && (
            <pre className="animate-expand-in" style={{
              margin: '6px 0 0', fontFamily: 'var(--font-body)', fontSize: 10,
              color: 'var(--text-tertiary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              lineHeight: 1.5, maxHeight: 180, overflowY: 'auto',
              background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-light)', padding: '6px 8px',
            }}>
              {reasoningText.slice(-3000)}
            </pre>
          )}
        </div>
      )}

      {/* ── 思考流 ── */}
      {streamText && (
        <div className="animate-fade-in" style={{
          maxWidth: 400, margin: '12px auto 0', textAlign: 'left',
          background: 'var(--bg-hover)', borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border-light)',
          padding: '8px 10px', maxHeight: 80, overflow: 'hidden',
        }}>
          <div style={{ fontFamily: 'var(--font-ui)', fontSize: 9, color: 'var(--text-tertiary)', marginBottom: 4 }}>
            AI 思考中...
          </div>
          <pre style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 10, color: 'var(--text-secondary)',
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: 1.4 }}>
            {streamText}
          </pre>
        </div>
      )}

      {/* ── Token 消耗 + 取消 ── */}
      <div className="animate-fade-in flex items-center justify-center gap-4" style={{ marginTop: 16 }}>
        {(tokensIn > 0 || tokensOut > 0) && (
          <span style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-tertiary)' }}>
            token: {(tokensIn + tokensOut).toLocaleString()}
          </span>
        )}
        <button
          onClick={async () => {
            setCancelling(true)
            try { await api.cancelProcessing(bookId); setPhase('error'); setErrorMsg('已暂停，可从断点继续') }
            catch { setCancelling(false) }
          }}
          disabled={cancelling}
          className="text-[10px] px-2 py-0.5 rounded border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors disabled:opacity-40"
          style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}
        >
          {cancelling ? '暂停中...' : '暂停'}
        </button>
      </div>

      {/* ── 底部说明 ── */}
      <p style={{
        fontFamily: 'var(--font-ui)', fontSize: 12,
        color: 'var(--text-tertiary)', marginTop: 16,
        lineHeight: 1.6, maxWidth: 300, margin: '16px auto 0',
      }}>
        分析过程中可离开本页面，完成后自动加载内容。
        中断后从断点继续，无需重新开始。
      </p>
    </div>
  )
}
