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
  return (
    <div className="flex gap-1 bg-[var(--bg-hover)] rounded p-0.5">
      {LEVELS.map(({ layer, label }) => (
        <button
          key={layer}
          onClick={() => onChange(layer)}
          className={`px-3 py-1 text-xs rounded transition-colors
            ${current === layer
              ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] font-medium'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
