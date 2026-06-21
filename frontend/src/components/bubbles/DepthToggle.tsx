import { useState, useRef } from 'react'
import type { Layer } from '../../types'

const LEVELS: { layer: Layer; label: string }[] = [
  { layer: 1, label: '概括' },
  { layer: 2, label: '标准' },
  { layer: 3, label: '详细' },
]

interface Props {
  current: Layer
  onChange: (layer: Layer) => void
}

export default function DepthToggle({ current, onChange }: Props) {
  const [hover, setHover] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const enter = () => {
    clearTimeout(timerRef.current)
    setHover(true)
  }
  const leave = () => {
    timerRef.current = setTimeout(() => setHover(false), 200)
  }

  return (
    <div
      className="relative shrink-0 flex items-center"
      onMouseEnter={enter}
      onMouseLeave={leave}
    >
      {/* Collapsed: subtle label */}
      <span
        className="text-[10px] cursor-default transition-opacity select-none"
        style={{
          fontFamily: 'var(--font-ui)',
          color: 'var(--text-secondary)',
          opacity: hover ? 0 : 1,
        }}
      >
        {LEVELS.find(l => l.layer === current)?.label}
      </span>

      {/* Expanded: three options */}
      <div
        className="flex gap-1 bg-[var(--bg-hover)] rounded p-0.5"
        style={{
          opacity: hover ? 1 : 0,
          transform: hover ? 'translateX(0)' : 'translateX(-8px)',
          transitionProperty: 'opacity, transform',
          transitionDuration: '200ms',
          transitionTimingFunction: 'var(--ease-out)',
          position: hover ? 'static' : 'absolute',
        }}
      >
        {LEVELS.map(({ layer, label }) => (
          <button
            key={layer}
            onClick={() => onChange(layer)}
            className={`px-3 py-1 text-xs rounded transition-colors cursor-pointer
              ${current === layer
                ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] font-medium'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
