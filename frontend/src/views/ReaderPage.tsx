import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api/client'
import ReaderView from '../components/reader/ReaderView'
import type { Chapter, Atom, JumpAnchor } from '../types'

interface Props {
  bookId: number
  jumpTarget: JumpAnchor | null
  onJumpConsumed: () => void
}

export default function ReaderPage({ bookId, jumpTarget, onJumpConsumed }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [currentChapterId, setCurrentChapterId] = useState<number | null>(null)
  const [atoms, setAtoms] = useState<Atom[]>([])
  const [loading, setLoading] = useState(true)
  const [scrollToAtomId, setScrollToAtomId] = useState<number | null>(null)
  const loadedRef = useRef(false)

  // 初始加载
  useEffect(() => {
    api.getChapters(bookId).then(({ chapters: chs }) => {
      setChapters(chs)
      if (!loadedRef.current) {
        api.getProgress(bookId).then(progress => {
          const targetId = progress.chapter_id || chs[0]?.id
          if (targetId) {
            setCurrentChapterId(targetId)
            loadAtoms(targetId)
          } else {
            setLoading(false)
          }
        })
      }
    })
  }, [bookId])

  // 处理跳转
  useEffect(() => {
    if (!jumpTarget || chapters.length === 0) return
    loadedRef.current = true
    // 找到对应章节
    const targetCh = chapters.find(ch => ch.index_num === jumpTarget.chapter_index)
    if (targetCh) {
      setCurrentChapterId(targetCh.id)
      setScrollToAtomId(jumpTarget.atom_id)
      loadAtomsForJump(targetCh.id)
    }
    onJumpConsumed()
  }, [jumpTarget, chapters])

  const loadAtoms = async (chapterId: number) => {
    setLoading(true)
    const { atoms: atm } = await api.getAtoms(bookId, chapterId, 0, 9999)
    setAtoms(atm)
    setLoading(false)
  }

  const loadAtomsForJump = async (chapterId: number) => {
    setLoading(true)
    const { atoms: atm } = await api.getAtoms(bookId, chapterId, 0, 9999)
    setAtoms(atm)
    setLoading(false)
  }

  const handlePositionChange = useCallback((atomIndex: number) => {
    if (currentChapterId && atoms[atomIndex]) {
      api.updateProgress(bookId, currentChapterId, atoms[atomIndex].id)
    }
  }, [bookId, currentChapterId, atoms])

  const handleChapterChange = (chapterId: number) => {
    setCurrentChapterId(chapterId)
    setScrollToAtomId(null)
    loadAtoms(chapterId)
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-1 px-4 py-2 border-b border-[var(--border)] overflow-x-auto">
        {chapters.map(ch => (
          <button
            key={ch.id}
            onClick={() => handleChapterChange(ch.id)}
            className={`px-2 py-1 text-xs rounded whitespace-nowrap transition-colors
              ${currentChapterId === ch.id
                ? 'bg-[var(--text-primary)] text-white'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
          >
            {ch.title}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-full text-sm text-[var(--text-secondary)]">
          加载中...
        </div>
      ) : (
        <ReaderView
          atoms={atoms}
          onPositionChange={handlePositionChange}
          scrollToAtomId={scrollToAtomId}
          onScrolled={() => setScrollToAtomId(null)}
        />
      )}
    </div>
  )
}
