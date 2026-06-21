import { useRef, useEffect, useCallback } from 'react'

interface Props {
  atoms: { id: number; content: string }[]
  onPositionChange: (atomIndex: number) => void
  scrollToAtomId?: number | null
  onScrolled?: () => void
  onScrollProgress?: (pct: number) => void
  fontSize: number
  textColor: string
}

export default function ReaderView({ atoms, onPositionChange, scrollToAtomId, onScrolled, onScrollProgress, fontSize, textColor }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const approxIndex = Math.floor(scrollTop / (fontSize * 1.8))
    onPositionChange(approxIndex)
    onScrollProgress?.((scrollTop / (scrollHeight - clientHeight)) * 100)
  }, [onPositionChange, onScrollProgress, fontSize])

  useEffect(() => {
    const el = containerRef.current
    if (el) { el.addEventListener('scroll', handleScroll, { passive: true }); return () => el.removeEventListener('scroll', handleScroll) }
  }, [handleScroll])

  useEffect(() => {
    if (scrollToAtomId == null) return
    const el = document.getElementById(`atom-${scrollToAtomId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      const timer = setTimeout(() => {
        el.classList.add('atom-highlight')
        el.addEventListener('animationend', () => el.classList.remove('atom-highlight'), { once: true })
        onScrolled?.()
      }, 400)
      return () => clearTimeout(timer)
    }
  }, [scrollToAtomId, atoms])

  return (
    <div ref={containerRef} className="h-full overflow-y-auto px-8 py-12"
      style={{ scrollBehavior: 'smooth' }}>
      <div className="max-w-2xl mx-auto" style={{ fontSize: `${fontSize}px`, lineHeight: 1.9, color: textColor, fontFamily: 'var(--font-body)' }}>
        {atoms.map(atom => (
          <span key={atom.id} id={`atom-${atom.id}`}>
            {atom.content}
          </span>
        ))}
      </div>
    </div>
  )
}
