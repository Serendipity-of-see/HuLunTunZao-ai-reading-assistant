import type { Bubble, CrossRef } from '../../types'

const IMPORTANCE_BAR: Record<number, { width: string; color: string }> = {
  1: { width: '3px', color: 'var(--border)' },
  2: { width: '3px', color: 'var(--border)' },
  3: { width: '3px', color: 'var(--border)' },
  4: { width: '3px', color: 'var(--text-tertiary)' },
  5: { width: '3px', color: 'var(--text-tertiary)' },
  6: { width: '3px', color: 'var(--text-tertiary)' },
  7: { width: '4px', color: 'var(--text-secondary)' },
  8: { width: '4px', color: 'var(--text-secondary)' },
  9: { width: '4px', color: 'var(--accent)' },
  10: { width: '4px', color: 'var(--accent)' },
}

const LAYER_BORDER: Record<number, string> = {
  1: 'var(--gold)',
  2: 'var(--border)',
  3: 'var(--border-light)',
  4: 'transparent',
}

interface Props {
  bubble: Bubble
  onClick: () => void
  expanded?: boolean
  expandable?: boolean
  crossRefs?: CrossRef[]
  children?: React.ReactNode
}

export default function BubbleCard({ bubble, onClick, expanded = false, expandable = false, crossRefs = [], children }: Props) {
  const bar = IMPORTANCE_BAR[bubble.importance] ?? IMPORTANCE_BAR[5]
  const compact = expanded && expandable
  const isPlaceholder = !bubble.title
  const borderColor = LAYER_BORDER[bubble.layer] ?? LAYER_BORDER[3]

  return (
    <div
      id={`bubble-${bubble.id}`}
      className="relative rounded-[var(--radius-md)]"
      style={{
        border: `1px solid ${borderColor}`,
        backgroundColor: isPlaceholder ? 'var(--accent-soft)' : 'var(--bg-surface)',
        cursor: 'default',
        transitionProperty: 'border-color, box-shadow, background-color',
        transitionDuration: '200ms',
        transitionTimingFunction: 'var(--ease-out)',
      }}
    >
      {/* Left importance bar */}
      <div className="absolute left-0 top-0 bottom-0 rounded-l-[var(--radius-md)]"
        style={{ width: bar.width, backgroundColor: bar.color }} />

      <div style={{
        paddingLeft: 20, paddingRight: 12,
        paddingTop: compact ? 6 : 10,
        paddingBottom: compact ? 6 : 10,
        transitionProperty: 'padding',
        transitionDuration: '200ms',
        transitionTimingFunction: 'var(--ease-out)',
      }}>
        {/* ── Header row (click to toggle) ── */}
        {bubble.layer !== 4 && (
          <div
            className="flex items-center gap-2"
            style={{
              minHeight: compact ? 20 : 28,
              cursor: expandable ? 'pointer' : 'default',
              userSelect: 'none',
            }}
            onClick={expandable ? onClick : undefined}
          >
            {expandable && (
              <span
                className={`shrink-0 ${expanded ? 'rotate-90' : ''}`}
                style={{
                  color: 'var(--text-tertiary)',
                  transitionProperty: 'transform, color',
                  transitionDuration: '200ms',
                  transitionTimingFunction: 'var(--ease-out)',
                }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
                </svg>
              </span>
            )}
            <span
              className="font-medium truncate flex-1"
              style={{
                fontFamily: bubble.layer === 1 ? 'var(--font-display)' : 'var(--font-ui)',
                fontSize: compact ? 12 : 14,
                fontWeight: compact ? 400 : 500,
                color: compact ? 'var(--text-tertiary)' : 'var(--text-primary)',
                transitionProperty: 'font-size, color, font-weight',
                transitionDuration: '200ms',
                transitionTimingFunction: 'var(--ease-out)',
              }}
            >
              {bubble.title || (bubble.layer === 3 && bubble.child_count === 0 ? '待分组' : '待解析')}
            </span>
            <span className="text-[10px] shrink-0 px-1.5 py-0.5 rounded-full"
              style={{
                fontFamily: 'var(--font-ui)',
                color: 'var(--text-tertiary)',
                backgroundColor: compact ? 'transparent' : 'var(--bg-hover)',
              }}>
              L{bubble.layer}
            </span>
            <span className="text-[10px] shrink-0"
              style={{
                fontFamily: 'var(--font-ui)',
                color: bar.color,
                fontWeight: 600,
                minWidth: 16, textAlign: 'center',
                fontVariantNumeric: 'tabular-nums',
              }}>
              {bubble.importance}
            </span>
          </div>
        )}

        {/* ── Body: content (hidden when compact) ── */}
        {!compact && (
          <div className="animate-fade-in"
            onClick={bubble.layer === 4 ? onClick : (expandable ? onClick : undefined)}
            style={{ cursor: (bubble.layer === 4 || expandable) ? 'pointer' : 'default' }}
          >
            {bubble.layer === 4 && bubble.content && (
              <p className="text-xs leading-relaxed"
                style={{ fontFamily: 'var(--font-body)', color: 'var(--text-body)' }}>
                {bubble.content}
              </p>
            )}
            {bubble.layer !== 4 && bubble.content && (
              <p className="mt-1 text-xs line-clamp-2"
                style={{
                  fontFamily: 'var(--font-ui)',
                  color: 'var(--text-secondary)',
                  textWrap: 'pretty',
                }}>
                {bubble.content}
              </p>
            )}
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              {bubble.story_time_label && (
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
                  {bubble.story_time_label}
                </span>
              )}
              {bubble.child_count > 0 && !expandable && (
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
                  {bubble.child_count} 子节点
                </span>
              )}
              {crossRefs.length > 0 && (
                <span className="text-[10px]" style={{ fontFamily: 'var(--font-ui)', color: 'var(--gold)' }}>
                  {crossRefs.length} 关联
                </span>
              )}
            </div>
          </div>
        )}

        {/* ── Children boards (only visible when expanded) ── */}
        {compact && children && (
          <div className="animate-expand-in mt-2"
            style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {children}
          </div>
        )}
      </div>
    </div>
  )
}
