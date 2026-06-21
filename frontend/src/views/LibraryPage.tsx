import { useState, useEffect, useRef, useMemo } from 'react'
import { api } from '../api/client'
import { useToast } from '../components/common/Toast'
import { BookCardSkeleton } from '../components/common/Skeleton'
import type { Book } from '../types'

interface Props { onBookSelect: (bookId: number) => void }

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'var(--text-tertiary)' },
  processing: { text: '处理中', color: 'var(--accent)' },
  complete: { text: '已完成', color: 'var(--success)' },
  failed: { text: '失败', color: 'var(--error)' },
}


const GENRE_COLORS: Record<string, string> = {
  '悬疑': '#6B5E53', '情感': '#C4523A', '战争': '#8B4513', '历史': '#B8954A', '武侠': '#2E5C4E',
  '玄幻': '#5B3A8C', '科幻': '#3A6B8C', '都市': '#5A5A5A', '青春': '#C47A5A', '冒险': '#4A7C5A',
  '推理': '#4A4A6B', '恐怖': '#8B3A3A',
}

export default function LibraryPage({ onBookSelect }: Props) {
  const [books, setBooks] = useState<Book[]>([])
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [search, setSearch] = useState('')
  const [progressLabels, setProgressLabels] = useState<Record<number, string>>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const loadBooks = async () => {
    try { setBooks(await api.listBooks()) } catch { /* ok */ }
    setLoading(false)
  }
  useEffect(() => { loadBooks() }, [])
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const filtered = useMemo(() =>
    search ? books.filter(b => b.title.includes(search) || (b.author && b.author.includes(search))) : books,
    [books, search]
  )

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setImporting(true)
    try {
      const result = await api.importBookFile(f)
      await loadBooks()
      startPolling(result.book_id)
      onBookSelect(result.book_id)
    } catch (e: any) {
      toast(e.message, 'error')
      setImporting(false)
    }
  }

  const startPolling = (bookId: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getProcessingStatus(bookId)
        if (status.step_label) {
          setProgressLabels(prev => ({ ...prev, [bookId]: `${status.step_label} · ${Math.round(status.progress_pct || 0)}%` }))
        }
        if (status.overall_status === 'complete' || status.overall_status === 'failed') {
          clearInterval(pollRef.current!); pollRef.current = null
          setImporting(false)
          setProgressLabels(prev => { const n = { ...prev }; delete n[bookId]; return n })
          if (status.overall_status === 'complete') toast(`分析完成 — 可打开阅读 #${bookId}`, 'success')
          else toast('分析失败，可进入阅读页续传', 'error')
          loadBooks()
        }
      } catch { /* retry next tick */ }
    }, 2000)
  }

  const handleExport = async (bookId: number, title: string) => {
    try {
      const data = await api.exportBook(bookId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url
      a.download = `${title || 'book'}_${data.run?.label || '默认'}.hltz`
      a.click(); URL.revokeObjectURL(url)
      toast('导出成功', 'success')
    } catch (e: any) { toast(e.message, 'error') }
  }

  const handleRetry = (bookId: number) => { api.retryProcessing(bookId); startPolling(bookId) }

  const handleDelete = async (bookId: number) => {
    if (!confirm('确定删除此书？所有分析数据将被清除。')) return
    setBooks(prev => prev.filter(b => b.id !== bookId))
    try { await api.deleteBook(bookId); toast('已删除', 'info') }
    catch { loadBooks(); toast('删除失败', 'error') }
  }

  const handleImportHltz = () => {
    const input = document.createElement('input'); input.type = 'file'; input.accept = '.hltz'
    input.onchange = async () => {
      const file = input.files?.[0]; if (!file) return
      setImporting(true)
      try {
        const result = await api.importHltz(file)
        setImporting(false); await loadBooks()
        toast(`导入成功（#${result.book_id}）`, 'success')
      } catch (e: any) { setImporting(false); toast(e.message, 'error') }
    }
    input.click()
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-10 pb-6">
        <h1 className="text-2xl font-bold tracking-wide mb-1" style={{ fontFamily: 'var(--font-display)', color: 'var(--text-primary)' }}>
          书架
        </h1>
        <p className="text-sm" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
          导入小说，AI 自动生成情节档案
        </p>
      </div>

      {/* Import area */}
      <div className="px-8 pb-6 space-y-3">
        <div className="flex gap-2 max-w-lg">
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.epub"
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="px-5 py-2.5 text-sm font-medium rounded-[var(--radius-md)] transition-all duration-150
                       bg-[#C4523A] text-white hover:bg-[#A8432E] disabled:opacity-50"
            style={{ fontFamily: 'var(--font-ui)' }}
          >
            {importing ? '导入中...' : '选择 TXT / EPUB 文件'}
          </button>
          <button
            onClick={handleImportHltz}
            disabled={importing}
            className="px-4 py-2.5 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
                       text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-primary)]
                       transition-all duration-150 disabled:opacity-50"
            style={{ fontFamily: 'var(--font-ui)' }}
          >
            导入 .hltz
          </button>
        </div>

        {/* Search */}
        {books.length > 1 && (
          <input
            type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="搜索书名或作者..."
            className="w-full max-w-lg px-3 py-2 text-sm rounded-[var(--radius-md)] border border-[var(--border)]
                       bg-[var(--bg-surface)] outline-none focus:border-[var(--border-focus)] transition-colors"
            style={{ fontFamily: 'var(--font-ui)' }}
          />
        )}
      </div>

      {/* Book list */}
      <div className="flex-1 px-8 pb-8">
        {loading ? (
          <div className="max-w-2xl space-y-3 stagger">
            {[1,2,3].map(i => <BookCardSkeleton key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
            <div className="text-5xl mb-4 opacity-20">📚</div>
            <p className="text-sm mb-2" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
              {search ? '没有匹配的书籍' : '书架空空'}
            </p>
            <p className="text-xs" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
              {search ? '换个关键词试试' : '选择 TXT 或 EPUB 文件开始阅读'}
            </p>
          </div>
        ) : (
          <div className="max-w-2xl space-y-2 stagger">
            {filtered.map(book => (
              <div
                key={book.id}
                onClick={() => onBookSelect(book.id)}
                className="group p-4 rounded-[var(--radius-md)] border transition-all duration-150
                           bg-[var(--bg-surface)] border-[var(--border-light)] hover:border-[var(--border)]
                           hover:shadow-[var(--shadow-sm)] cursor-pointer"
                  style={{ opacity: book.processing_status === 'processing' || book.processing_status === 'pending' ? 0.55 : 1 }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-base font-semibold truncate" style={{ fontFamily: 'var(--font-display)' }}>
                        {book.title === '未命名' ? `📖 书籍 #${book.id}` : book.title}
                      </h3>
                      {book.processing_status && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded-full font-medium shrink-0"
                              style={{ fontFamily: 'var(--font-ui)', color: STATUS_LABEL[book.processing_status].color, backgroundColor: 'var(--bg-hover)' }}>
                          {progressLabels[book.id] || STATUS_LABEL[book.processing_status].text}
                        </span>
                      )}
                    </div>
                    {book.author && (
                      <p className="text-xs mb-1" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
                        {book.author}
                      </p>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
                        {book.chapter_count} 章 · {(book.total_chars || 0).toLocaleString()} 字
                      </span>
                      {book.genre_tags?.map(tag => (
                        <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded-full"
                              style={{ fontFamily: 'var(--font-ui)', color: GENRE_COLORS[tag] || 'var(--text-secondary)', backgroundColor: 'var(--bg-hover)' }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {book.processing_status === 'complete' && (
                      <button onClick={e => { e.stopPropagation(); handleExport(book.id, book.title) }}
                        className="text-[11px] px-2 py-1 rounded-[var(--radius-sm)] hover:bg-[var(--bg-hover)] transition-colors"
                        style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-ui)' }}>导出</button>
                    )}
                    {(book.processing_status === 'processing' || book.processing_status === 'pending') && (
                      <span onClick={e => { e.stopPropagation(); api.cancelProcessing(book.id).then(() => loadBooks()) }}
                        className="text-[11px] px-2 py-1 rounded-[var(--radius-sm)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                        style={{ color: 'var(--warning)', fontFamily: 'var(--font-ui)' }}>暂停</span>
                    )}
                    {book.processing_status === 'failed' && (
                      <span onClick={e => { e.stopPropagation(); handleRetry(book.id) }}
                        className="text-[11px] px-2 py-1 rounded-[var(--radius-sm)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
                        style={{ color: 'var(--accent)', fontFamily: 'var(--font-ui)' }}>重试</span>
                    )}
                    <button onClick={e => { e.stopPropagation(); handleDelete(book.id) }}
                      className="text-[11px] px-2 py-1 rounded-[var(--radius-sm)] hover:bg-[var(--accent-soft)] transition-colors"
                      style={{ color: 'var(--error)', fontFamily: 'var(--font-ui)' }}>删除</button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
