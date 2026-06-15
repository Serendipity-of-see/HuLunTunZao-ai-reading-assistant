import { useRef, useEffect, useCallback } from 'react'

interface Props {
  atoms: { id: number; content: string }[]
  onPositionChange: (atomIndex: number) => void
  scrollToAtomId?: number | null
  onScrolled?: () => void
}

export default function ReaderView({ atoms, onPositionChange, scrollToAtomId, onScrolled }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop } = containerRef.current
    const approxIndex = Math.floor(scrollTop / 60)
    onPositionChange(approxIndex)
  }, [onPositionChange])

  useEffect(() => {
    const el = containerRef.current
    if (el) {
      el.addEventListener('scroll', handleScroll, { passive: true })
      return () => el.removeEventListener('scroll', handleScroll)
    }
  }, [handleScroll])

  // 滚动到指定 atom
  useEffect(() => {
    if (scrollToAtomId == null) return
    const el = document.getElementById(`atom-${scrollToAtomId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      onScrolled?.()
    }
  }, [scrollToAtomId])

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-8 py-12"
    >
      <div className="max-w-2xl mx-auto leading-8 text-base">
        {atoms.map((atom) => (
          <span key={atom.id} id={`atom-${atom.id}`} className="text-[var(--text-primary)]">
            {atom.content}
            <span className="mr-1" />
          </span>
        ))}
      </div>
    </div>
  )
}
