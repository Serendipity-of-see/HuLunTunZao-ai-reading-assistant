import { useState, useEffect, useRef } from 'react'
import { api } from '../api/client'
import type { Book, ProcessingStatus } from '../types'

interface Props {
  onBookSelect: (bookId: number) => void
}

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  pending:  { text: '等待中', color: 'text-slate-400' },
  processing: { text: '处理中', color: 'text-blue-500' },
  complete: { text: '已完成', color: 'text-emerald-600' },
  failed:  { text: '失败', color: 'text-red-500' },
}

const STEP_LABEL: Record<string, string> = {
  parse: '分句',
  l4: '句组概括',
  l3: '场景聚合',
  l2_global: '全局事件',
  l1_merge: '故事弧整合',
}

export default function LibraryPage({ onBookSelect }: Props) {
  const [books, setBooks] = useState<Book[]>([])
  const [filePath, setFilePath] = useState('')
  const [importing, setImporting] = useState(false)
  const [importStatus, setImportStatus] = useState<ProcessingStatus | null>(null)
  const [error, setError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const loadBooks = async () => {
    try { const list = await api.listBooks(); setBooks(list) } catch { /* ok */ }
  }
  useEffect(() => { loadBooks() }, [])

  // 清理轮询
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleImport = async () => {
    if (!filePath.trim()) return
    setImporting(true)
    setError('')
    setImportStatus(null)
    try {
      const result = await api.importBook(filePath.trim(), 'familiar')
      startPolling(result.book_id)
    } catch (e: any) {
      setError(e.message)
      setImporting(false)
    }
  }

  const startPolling = (bookId: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getProcessingStatus(bookId)
        setImportStatus(status)
        if (status.overall_status === 'complete' || status.overall_status === 'failed') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          setImporting(false)
          loadBooks()
        }
      } catch { /* retry next tick */ }
    }, 2000)
  }

  const handleRetry = async (bookId: number) => {
    await api.retryProcessing(bookId)
    startPolling(bookId)
  }

  return (
    <div className="flex flex-col items-center h-full gap-6 p-8 overflow-y-auto">
      <h1 className="text-xl font-medium text-[var(--text-primary)]">囫囵吞枣</h1>
      <p className="text-sm text-[var(--text-secondary)]">导入小说文本，AI 自动生成情节档案</p>

      <div className="flex gap-2 w-full max-w-md">
        <input
          type="text"
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          placeholder="输入 TXT 文件路径（如 C:\novels\test.txt）"
          className="flex-1 px-3 py-2 text-sm border border-[var(--border)] rounded bg-[var(--bg-surface)] outline-none focus:border-[var(--emphasis)]"
        />
        <button
          onClick={handleImport}
          disabled={importing || !filePath.trim()}
          className="px-4 py-2 text-sm bg-[var(--text-primary)] text-white rounded hover:opacity-80 disabled:opacity-40 transition-opacity"
        >
          {importing ? '处理中...' : '导入'}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* 导入中进度卡片 */}
      {importing && importStatus && (
        <div className="w-full max-w-md p-4 rounded bg-[var(--bg-surface)] border border-[var(--border)] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">
              {importStatus.overall_status === 'processing' ? '正在处理...' : '处理中'}
            </span>
            <span className={`text-xs ${STATUS_LABEL[importStatus.overall_status]?.color || ''}`}>
              {STATUS_LABEL[importStatus.overall_status]?.text || importStatus.overall_status}
            </span>
          </div>

          {/* 逐章逐层进度 */}
          {importStatus.chapters.map(ch => {
            const steps = ch.steps || {}
            const stepEntries = Object.entries(steps)
            const doneCount = stepEntries.filter(([, s]) => s.status === 'complete').length
            const totalSteps = stepEntries.length
            return (
              <div key={ch.chapter_index} className="text-xs space-y-1">
                <div className="flex items-center justify-between text-[var(--text-secondary)]">
                  <span>第{ch.chapter_index}章</span>
                  <span>{doneCount}/{totalSteps} 步</span>
                </div>
                <div className="flex gap-1.5">
                  {['parse', 'l4', 'l3'].map(step => {
                    const s = steps[step]
                    const status = s?.status || 'pending'
                    const colors: Record<string, string> = {
                      complete: 'bg-emerald-400',
                      processing: 'bg-blue-400 animate-pulse',
                      failed: 'bg-red-400',
                      pending: 'bg-slate-200',
                    }
                    return (
                      <div key={step} className="flex-1 flex flex-col items-center gap-0.5">
                        <div className={`w-full h-1.5 rounded-full ${colors[status]}`} />
                        <span className="text-[10px] text-[var(--text-tertiary)]">{STEP_LABEL[step] || step}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}

          {/* 书级步骤 */}
          {Object.keys(importStatus.book_steps || {}).length > 0 && (
            <div className="text-xs space-y-1">
              <div className="text-[var(--text-secondary)]">全书步骤</div>
              <div className="flex gap-1.5">
                {['l2_global', 'l1_merge'].map(step => {
                  const s = importStatus.book_steps[step]
                  const status = s?.status || 'pending'
                  const colors: Record<string, string> = {
                    complete: 'bg-emerald-400',
                    processing: 'bg-blue-400 animate-pulse',
                    failed: 'bg-red-400',
                    pending: 'bg-slate-200',
                  }
                  return (
                    <div key={step} className="flex-1 flex flex-col items-center gap-0.5">
                      <div className={`w-full h-1.5 rounded-full ${colors[status]}`} />
                      <span className="text-[10px] text-[var(--text-tertiary)]">{STEP_LABEL[step] || step}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 已有书籍列表 */}
      {books.length > 0 && (
        <div className="w-full max-w-md">
          <p className="text-xs text-[var(--text-secondary)] mb-2">已有书籍</p>
          <div className="space-y-1">
            {books.map(book => (
              <button
                key={book.id}
                onClick={() => book.processing_status === 'complete' && onBookSelect(book.id)}
                className="w-full text-left px-3 py-2 rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-hover)] transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[var(--text-primary)]">
                    {book.title === '未命名' ? `书籍 #${book.id}` : book.title}
                  </span>
                  {book.processing_status && (
                    <span className={`text-xs ${STATUS_LABEL[book.processing_status]?.color || ''}`}>
                      {STATUS_LABEL[book.processing_status]?.text}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-xs text-[var(--text-secondary)]">
                    {book.chapter_count} 章 · {book.total_chars.toLocaleString()} 字
                  </span>
                  {book.processing_status === 'failed' && (
                    <span
                      onClick={(e) => { e.stopPropagation(); handleRetry(book.id) }}
                      className="text-xs text-blue-500 hover:underline cursor-pointer"
                    >
                      重试
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
