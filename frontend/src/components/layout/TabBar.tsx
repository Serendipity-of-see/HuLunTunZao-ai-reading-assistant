import type { Tab } from '../../App'

const tabs: { key: Tab; label: string }[] = [
  { key: 'library', label: '书架' },
  { key: 'reader', label: '阅读' },
  { key: 'archive', label: '档案' },
  // settings 不显示为顶栏 Tab，仅通过底部"设置"按钮访问
]

interface Props {
  activeTab: Tab
  onTabChange: (tab: Tab) => void
}

export default function TabBar({ activeTab, onTabChange }: Props) {
  return (
    <nav className="flex items-center h-12 px-6 gap-8 border-b border-[var(--border)] bg-[var(--bg-surface)]">
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onTabChange(key)}
          className={`text-sm font-medium transition-colors duration-150
            ${activeTab === key
              ? 'text-[var(--text-primary)] border-b-2 border-[var(--text-primary)] -mb-[1px] pb-[11px]'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
            }`}
        >
          {label}
        </button>
      ))}
    </nav>
  )
}
