import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api/client'
import BubbleStream from '../components/bubbles/BubbleStream'
import { BubbleSkeleton } from '../components/common/Skeleton'
import ProcessingProgress from '../components/common/ProcessingProgress'
import type { Book, JumpAnchor, TreeNode } from '../types'

interface Props { bookId: number; onJumpToReader: (bookId: number, anchor: JumpAnchor) => void }

const GENRE_COLORS: Record<string, string> = {
  '悬疑':'#6B5E53','情感':'#C4523A','战争':'#8B4513','历史':'#B8954A','武侠':'#2E5C4E',
  '玄幻':'#5B3A8C','科幻':'#3A6B8C','都市':'#5A5A5A','青春':'#C47A5A','冒险':'#4A7C5A',
  '推理':'#4A4A6B','恐怖':'#8B3A3A',
}

export default function ArchivePage({ bookId, onJumpToReader }: Props) {
  const [book, setBook] = useState<Book | null>(null)
  const [showNarrative, setShowNarrative] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)  // 活跃处理中（有 SSE 流）
  const [isPaused, setIsPaused] = useState(false)          // 已暂停/未完成
  const [cancelling, setCancelling] = useState(false)
  const [progressKey, setProgressKey] = useState(0)
  const [treeKey, setTreeKey] = useState(0)
  const [progressCollapsed, setProgressCollapsed] = useState(false)
  const treeHandlersRef = useRef<{ addNode: (pid: number, n: TreeNode) => void; removeNode: (nid: number) => void } | null>(null)
  const handleTreeRefresh = useCallback(() => setTreeKey(k => k + 1), [])
  const [splitPct, setSplitPct] = useState(40)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    api.getBook(bookId).then(b => {
      if (cancelled) return
      setBook(b)
      setIsProcessing(b.processing_status === 'processing')
      setIsPaused(b.processing_status === 'pending' || b.processing_status === 'failed')
    }).catch(() => {})
    return () => { cancelled = true }
  }, [bookId])

  const handleProcessingComplete = () => {
    setIsProcessing(false)
    setIsPaused(false)
    setTreeKey(k => k + 1) // 刷新树
    api.getBook(bookId).then(setBook).catch(() => {})
  }

  const handleRetry = async () => {
    setCancelling(true)
    try {
      await api.retryProcessing(bookId)
      setIsProcessing(true)
      setIsPaused(false)
      setProgressKey(k => k + 1)
    } catch { /* ignore */ }
    setCancelling(false)
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-surface)] shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-wide" style={{ fontFamily: 'var(--font-display)' }}>
              {book?.title === '未命名' ? `📖 书籍 #${bookId}` : book?.title || '加载中...'}
            </h2>
            {book?.author && (
              <p className="text-xs mt-0.5" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
                {book.author}
              </p>
            )}
            {/* 处理统计 */}
            {book?.processing_time != null && book.processing_time > 0 && (
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}
                  title="AI 处理耗时">
                  ⏱ {(book.processing_time! < 60)
                    ? `${book.processing_time!}秒`
                    : `${Math.floor(book.processing_time! / 60)}分${book.processing_time! % 60}秒`}
                </span>
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}
                  title={`输入约 ${(book.tokens_in! / 1000).toFixed(1)}K tokens`}>
                  📥 {((book.tokens_in ?? 0) / 1000).toFixed(1)}K
                </span>
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}
                  title={`输出约 ${(book.tokens_out! / 1000).toFixed(1)}K tokens`}>
                  📤 {((book.tokens_out ?? 0) / 1000).toFixed(1)}K
                </span>
                {book.model_used && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
                    fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)',
                    background: 'var(--bg-hover)',
                  }} title="解析使用的模型">
                    {book.model_used}
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* 活跃处理中 */}
            {isProcessing && (
              <span className="text-[10px] px-2 py-0.5 rounded-full animate-progress-pulse"
                style={{ fontFamily: 'var(--font-ui)', color: 'var(--accent)', backgroundColor: 'var(--accent-soft)' }}>
                AI 解析中...
              </span>
            )}
            {/* 暂停/失败 → 恢复按钮 */}
            {isPaused && (
              <button onClick={handleRetry} disabled={cancelling}
                className="text-[10px] px-3 py-1 rounded-[var(--radius-sm)] text-white transition-colors"
                style={{ fontFamily: 'var(--font-ui)', background: 'var(--accent)' }}>
                {cancelling ? '...' : '继续处理'}
              </button>
            )}
            {book?.genre_tags?.map(tag => (
              <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full"
                style={{ fontFamily: 'var(--font-ui)', color: GENRE_COLORS[tag] || 'var(--text-secondary)', backgroundColor: 'var(--bg-hover)' }}>
                {tag}
              </span>
            ))}
          </div>
        </div>

        {/* Narrative summary */}
        {book?.narrative_summary && (
          <div className="mt-3">
            <button onClick={() => setShowNarrative(!showNarrative)}
              className="text-xs flex items-center gap-1 transition-colors"
              style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                className={`transition-transform ${showNarrative ? 'rotate-90' : ''}`}>
                <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2"/>
              </svg>
              全书概括
            </button>
            {showNarrative && (
              <p className="mt-2 text-sm leading-relaxed animate-expand-in"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--text-body)' }}>
                {book.narrative_summary}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Processing / Paused / Tree */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {!book ? <BubbleSkeleton /> : isProcessing ? (
          <>
            {/* 可调节进度面板 */}
            {!progressCollapsed && (
              <div className="shrink-0 overflow-hidden border-b" style={{ borderColor: 'var(--border)', height: `${splitPct}%` }}>
                <div className="h-full overflow-y-auto">
                  <ProcessingProgress
                    key={progressKey}
                    bookId={bookId}
                    bookTitle={book.title}
                    onComplete={handleProcessingComplete}
                    onError={() => {}}
                    onToggleCollapse={() => setProgressCollapsed(true)}
                    onTreeRefresh={handleTreeRefresh}
                    onNodeAdd={(pid, n) => treeHandlersRef.current?.addNode(pid, n)}
                    onNodeDelete={(nid) => treeHandlersRef.current?.removeNode(nid)}
                  />
                </div>
                {/* 拖动调节手柄 */}
                <div
                  className="h-1.5 cursor-row-resize hover:bg-[var(--accent-soft)] transition-colors shrink-0"
                  onMouseDown={e => {
                    e.preventDefault()
                    const startY = e.clientY
                    const startPct = splitPct
                    const container = e.currentTarget.parentElement?.parentElement
                    const containerH = container?.clientHeight || 1
                    const onMove = (ev: MouseEvent) => {
                      const delta = ev.clientY - startY
                      const newPct = Math.max(15, Math.min(80, startPct + (delta / containerH) * 100))
                      setSplitPct(Math.round(newPct))
                    }
                    const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp) }
                    document.addEventListener('mousemove', onMove)
                    document.addEventListener('mouseup', onUp)
                  }}
                />
              </div>
            )}
            {progressCollapsed && (
              <ProcessingProgress
                key={progressKey}
                bookId={bookId}
                bookTitle={book.title}
                onComplete={handleProcessingComplete}
                onError={() => {}}
                collapsed
                onToggleCollapse={() => setProgressCollapsed(false)}
                onTreeRefresh={handleTreeRefresh}
                onNodeAdd={(pid, n) => treeHandlersRef.current?.addNode(pid, n)}
                onNodeDelete={(nid) => treeHandlersRef.current?.removeNode(nid)}
              />
            )}
            {/* 树始终可见 */}
            <div className="flex-1 overflow-hidden">
              <BubbleStream bookId={bookId} onJumpToReader={onJumpToReader} onRegisterHandlers={h => { treeHandlersRef.current = h }} />
            </div>
          </>
        ) : isPaused ? (
          <div className="h-full flex flex-col">
            {/* 暂停提示 */}
            <div className="shrink-0 flex items-center justify-center gap-3 px-4 py-2 border-b"
              style={{ backgroundColor: 'var(--gold-soft)', borderColor: 'var(--gold)' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="var(--gold)" strokeWidth="2"/>
                <path d="M12 8v4M12 16h.01" stroke="var(--gold)" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <span className="text-xs" style={{ fontFamily: 'var(--font-ui)', color: 'var(--gold)' }}>
                处理已暂停，可继续解析
              </span>
              <button onClick={handleRetry} disabled={cancelling}
                className="text-[11px] px-3 py-1 rounded-[var(--radius-sm)] text-white transition-colors"
                style={{ fontFamily: 'var(--font-ui)', background: 'var(--accent)' }}>
                {cancelling ? '...' : '继续处理'}
              </button>
            </div>
            {/* 部分树 */}
            <div className="flex-1 overflow-hidden">
              <BubbleStream bookId={bookId} onJumpToReader={onJumpToReader} onRegisterHandlers={h => { treeHandlersRef.current = h }} />
            </div>
          </div>
        ) : (
          <BubbleStream bookId={bookId} onJumpToReader={onJumpToReader} />
        )}
      </div>
    </div>
  )
}
