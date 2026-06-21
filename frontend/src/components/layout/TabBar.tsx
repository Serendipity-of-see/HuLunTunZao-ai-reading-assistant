import type { Tab } from '../../App'

const tabs: { key: Tab; label: string }[] = [
  { key: 'library', label: '书架' },
  { key: 'reader', label: '阅读' },
  { key: 'archive', label: '档案' },
  { key: 'settings', label: '设置' },
]

interface Props { activeTab: Tab; onTabChange: (t: Tab) => void; hasBook: boolean }

export default function TabBar({ activeTab, onTabChange, hasBook }: Props) {
  return (
    <nav className="flex items-center h-11 px-6 gap-1 border-b border-[var(--border)] bg-[var(--bg-surface)] select-none">
      <span
        className="text-sm font-semibold mr-4 tracking-wide"
        style={{ fontFamily: 'var(--font-display)', color: 'var(--accent)' }}
      >
        囫囵吞枣
      </span>
      {tabs.map(({ key, label }) => {
        const disabled = (key === 'reader' || key === 'archive') && !hasBook
        return (
          <button
            key={key}
            onClick={() => !disabled && onTabChange(key)}
            disabled={disabled}
            className={`relative px-3 py-1.5 text-[13px] rounded-[var(--radius-md)] transition-all duration-150
              ${activeTab === key
                ? 'text-[var(--accent)] font-medium bg-[var(--accent-soft)]'
                : disabled
                  ? 'text-[var(--text-tertiary)] cursor-not-allowed'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)]'
              }`}
            style={{ fontFamily: 'var(--font-ui)' }}
          >
            {label}
          </button>
        )
      })}
    </nav>
  )
}
