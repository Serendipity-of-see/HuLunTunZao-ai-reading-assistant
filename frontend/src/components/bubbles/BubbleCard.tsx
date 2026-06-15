import type { Bubble } from '../../types'

const IMPORTANCE_BAR: Record<number, { width: string; color: string }> = {
  1: { width: '1px', color: '#D0D0D0' },
  2: { width: '1px', color: '#D0D0D0' },
  3: { width: '1px', color: '#D0D0D0' },
  4: { width: '2px', color: '#A0A0A0' },
  5: { width: '2px', color: '#A0A0A0' },
  6: { width: '2px', color: '#A0A0A0' },
  7: { width: '3px', color: '#505050' },
  8: { width: '3px', color: '#505050' },
  9: { width: '4px', color: '#1A1A1A' },
  10: { width: '4px', color: '#1A1A1A' },
}

interface Props {
  bubble: Bubble
  onClick: (bubble: Bubble) => void
  onRightClick: (bubble: Bubble) => void
}

export default function BubbleCard({ bubble, onClick, onRightClick }: Props) {
  const bar = IMPORTANCE_BAR[bubble.importance] ?? IMPORTANCE_BAR[5]

  return (
    <div
      className="relative bg-[var(--bg-surface)] rounded-lg cursor-pointer
                 hover:bg-[var(--bg-hover)] transition-colors duration-150"
      onClick={() => onClick(bubble)}
      onContextMenu={(e) => { e.preventDefault(); onRightClick(bubble) }}
    >
      {/* 左侧重要性色条 */}
      <div
        className="absolute left-0 top-0 bottom-0 rounded-l-lg"
        style={{ width: bar.width, backgroundColor: bar.color }}
      />

      <div className="pl-4 pr-3 py-2.5">
        {/* 标题行（L4 不显示标题，只显正文） */}
        {bubble.layer !== 4 && (
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-[var(--text-primary)] truncate">
              {bubble.title}
            </span>
            {bubble.story_time_label && (
              <span className="text-[10px] text-[var(--text-tertiary)] whitespace-nowrap">
                {bubble.story_time_label}
              </span>
            )}
          </div>
        )}

        {/* 正文摘要 */}
        <p className={`text-xs text-[var(--text-secondary)] ${bubble.layer === 4 ? '' : 'mt-1'} line-clamp-2`}>
          {bubble.content}
        </p>

        {/* 底部指示器 */}
        <div className="flex items-center gap-2 mt-1.5">
          {bubble.child_count > 0 && (
            <span className="text-[10px] text-[var(--text-tertiary)]">
              {bubble.child_count} 个子节点
            </span>
          )}
          {bubble.has_cross_refs && (
            <span className="text-[10px] text-[var(--emphasis)]">
              ↗ 关联
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
