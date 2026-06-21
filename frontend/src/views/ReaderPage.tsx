import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api/client'
import ReaderView from '../components/reader/ReaderView'
import { ReaderSkeleton } from '../components/common/Skeleton'
import type { Chapter, Atom, JumpAnchor } from '../types'

interface Props { bookId: number; jumpTarget: JumpAnchor | null; onJumpConsumed: () => void }

type Theme = 'light' | 'sepia' | 'dark'

export default function ReaderPage({ bookId, jumpTarget, onJumpConsumed }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [currentChapterId, setCurrentChapterId] = useState<number | null>(null)
  const [atoms, setAtoms] = useState<Atom[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scrollToAtomId, setScrollToAtomId] = useState<number | null>(null)
  const [fontSize, setFontSize] = useState(16)
  const [theme, setTheme] = useState<Theme>('light')
  const [showToc, setShowToc] = useState(false)
  const [scrollPercent, setScrollPercent] = useState(0)
  const loadedRef = useRef(false)
  const currentChapterIdx = chapters.findIndex(c => c.id === currentChapterId)

  const themeBg: Record<Theme, string> = {
    light: 'var(--bg-page)',
    sepia: '#F4ECD8',
    dark: '#1A1410',
  }
  const themeText: Record<Theme, string> = {
    light: 'var(--text-body)',
    sepia: '#4A3520',
    dark: '#D8CFC0',
  }

  useEffect(() => {
    let cancelled = false
    loadedRef.current = false
    api.getChapters(bookId).then(({ chapters: chs }) => {
      if (cancelled) return
      setChapters(chs)
      if (!loadedRef.current && !jumpTarget) {
        api.getProgress(bookId).then(progress => {
          if (cancelled) return
          const targetId = progress.chapter_id || chs[0]?.id
          if (targetId) { setCurrentChapterId(targetId); loadAtoms(targetId) }
          else setLoading(false)
        }).catch(() => { if (!cancelled) setLoading(false) })
      }
    }).catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [bookId])

  useEffect(() => {
    if (!jumpTarget || chapters.length === 0) return
    loadedRef.current = true
    const targetCh = chapters.find(ch => ch.index_num === jumpTarget.chapter_index)
    if (targetCh) {
      setCurrentChapterId(targetCh.id); setScrollToAtomId(jumpTarget.atom_id)
      loadAtoms(targetCh.id)
    }
    onJumpConsumed()
  }, [jumpTarget, chapters])

  const loadAtoms = async (chapterId: number) => {
    setLoading(true); setError('')
    try {
      const { atoms: atm } = await api.getAtoms(bookId, chapterId, 0, 9999)
      setAtoms(atm); setScrollPercent(0)
    } catch (e: any) { setError(e.message) }
    setLoading(false)
  }

  const handlePositionChange = useCallback((atomIndex: number) => {
    if (currentChapterId && atoms[atomIndex]) {
      api.updateProgress(bookId, currentChapterId, atoms[atomIndex].id)
    }
  }, [bookId, currentChapterId, atoms])

  const handleScrollProgress = useCallback((pct: number) => { setScrollPercent(pct) }, [])

  const goChapter = (dir: 'prev' | 'next') => {
    const idx = currentChapterIdx + (dir === 'prev' ? -1 : 1)
    if (idx >= 0 && idx < chapters.length) {
      setCurrentChapterId(chapters[idx].id); loadAtoms(chapters[idx].id)
    }
  }

  const ThemeIcon = () => {
    if (theme === 'light') return <path d="M12 3v1m0 16v1m9-9h-1m-16 0H3m15.32-6.32l-.71-.71M5.38 18.38l-.71-.71M18.32 18.32l-.71-.71M5.38 5.38l-.71-.71M12 7a5 5 0 100 10 5 5 0 000-10z" stroke="currentColor" strokeWidth="1.5" fill="none"/>
    if (theme === 'sepia') return <><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" fill="none"/><path d="M12 3a9 9 0 019 9" stroke="currentColor" strokeWidth="1.5" fill="none"/></>
    return <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" strokeWidth="1.5" fill="currentColor" opacity="0.8"/>
  }

  // ── 子视图 ────────────────────────────────────────────────
  const ErrorView = () => (
    <div className="flex flex-col items-center justify-center h-full gap-3 animate-fade-in">
      <p className="text-sm" style={{ color: 'var(--error)', fontFamily: 'var(--font-ui)' }}>{error}</p>
      {currentChapterId && (
        <button onClick={() => loadAtoms(currentChapterId!)}
          className="text-xs px-4 py-1.5 rounded-[var(--radius-md)] border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors"
          style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>重试加载</button>
      )}
    </div>
  )

  const EmptyProcessingView = () => (
    <div className="flex flex-col items-center justify-center h-full gap-4 animate-fade-in">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" style={{ opacity: 0.4 }}>
        <circle cx="12" cy="12" r="10" stroke="var(--accent)" strokeWidth="1.2" strokeDasharray="4 2"
          className="animate-connecting" />
      </svg>
      <div className="text-center">
        <p className="text-sm" style={{ fontFamily: 'var(--font-display)', color: 'var(--text-secondary)' }}>
          AI 正在解析文本结构
        </p>
        <p className="text-xs mt-1" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
          前往<span className="font-medium" style={{ color: 'var(--accent)' }}>档案</span>查看解析进度
        </p>
      </div>
    </div>
  )

  return (
    <div className="h-full flex flex-col" style={{ backgroundColor: themeBg[theme], transition: 'background-color 0.4s ease' }}>
      {/* Top bar */}
      <div className="flex items-center justify-between h-11 px-4 border-b shrink-0" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-surface)' }}>
        <div className="flex items-center gap-2">
          <select
            value={currentChapterId ?? ''}
            onChange={e => { const id = Number(e.target.value); setCurrentChapterId(id); loadAtoms(id) }}
            className="text-xs px-2 py-1 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--bg-surface)] cursor-pointer"
            style={{ fontFamily: 'var(--font-ui)', maxWidth: 160 }}
          >
            {chapters.map(ch => (
              <option key={ch.id} value={ch.id}>{ch.title || `第${ch.index_num}章`}</option>
            ))}
          </select>
          <button onClick={() => goChapter('prev')} disabled={currentChapterIdx <= 0}
            className="p-1 rounded disabled:opacity-30 hover:bg-[var(--bg-hover)] transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="var(--text-secondary)" strokeWidth="2"/></svg>
          </button>
          <button onClick={() => goChapter('next')} disabled={currentChapterIdx >= chapters.length - 1}
            className="p-1 rounded disabled:opacity-30 hover:bg-[var(--bg-hover)] transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M9 18l6-6-6-6" stroke="var(--text-secondary)" strokeWidth="2"/></svg>
          </button>
        </div>

        <div className="flex items-center gap-3">
          {/* Font size */}
          <button onClick={() => setFontSize(s => Math.max(12, s - 1))} className="text-xs px-2 py-0.5 rounded border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors"
            style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>A-</button>
          <span className="text-[11px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)', minWidth: 20, textAlign: 'center' }}>{fontSize}</span>
          <button onClick={() => setFontSize(s => Math.min(22, s + 1))} className="text-xs px-2 py-0.5 rounded border border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors"
            style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>A+</button>

          {/* Theme toggle */}
          <button onClick={() => setTheme(t => t === 'light' ? 'sepia' : t === 'sepia' ? 'dark' : 'light')}
            className="p-1.5 rounded hover:bg-[var(--bg-hover)] transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24"><ThemeIcon /></svg>
          </button>

          {/* TOC toggle */}
          <button onClick={() => setShowToc(!showToc)}
            className={`p-1.5 rounded transition-colors ${showToc ? 'bg-[var(--accent-soft)]' : 'hover:bg-[var(--bg-hover)]'}`}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M4 6h16M4 12h16M4 18h16" stroke="var(--text-secondary)" strokeWidth="2"/></svg>
          </button>
        </div>
      </div>

      {/* Reading progress bar */}
      <div className="h-0.5 shrink-0" style={{ backgroundColor: 'var(--border-light)' }}>
        <div className="h-full transition-all duration-300" style={{ width: `${scrollPercent}%`, backgroundColor: 'var(--accent)' }} />
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* TOC sidebar */}
        {showToc && (
          <div className="w-56 shrink-0 overflow-y-auto border-r p-3 space-y-1 animate-slide-up" style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-surface)' }}>
            <p className="text-xs font-medium mb-2 px-1" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>目录</p>
            {chapters.map(ch => (
              <button key={ch.id}
                onClick={() => { setCurrentChapterId(ch.id); loadAtoms(ch.id); setShowToc(false) }}
                className={`w-full text-left text-xs px-2 py-1.5 rounded-[var(--radius-sm)] transition-colors truncate
                  ${currentChapterId === ch.id ? 'bg-[var(--accent-soft)] font-medium' : 'hover:bg-[var(--bg-hover)]'}`}
                style={{ fontFamily: 'var(--font-ui)', color: currentChapterId === ch.id ? 'var(--accent)' : 'var(--text-secondary)' }}>
                {ch.title || `第${ch.index_num}章`}
              </button>
            ))}
          </div>
        )}

        {/* Reader */}
        <div className="flex-1">
          {loading
            ? <ReaderSkeleton />
            : error
            ? <ErrorView />
            : atoms.length === 0 && !loading
            ? <EmptyProcessingView />
            : <ReaderView atoms={atoms} onPositionChange={handlePositionChange} scrollToAtomId={scrollToAtomId}
                onScrolled={() => setScrollToAtomId(null)} onScrollProgress={handleScrollProgress}
                fontSize={fontSize} textColor={themeText[theme]} />
          }
        </div>
      </div>
    </div>
  )
}
