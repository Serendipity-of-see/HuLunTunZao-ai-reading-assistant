interface Props {
  onImport: () => void
  onSettings: () => void
}

export default function BottomBar({ onImport, onSettings }: Props) {
  return (
    <footer className="flex items-center justify-center h-10 gap-8 border-t border-[var(--border)] bg-[var(--bg-surface)]">
      <button
        onClick={onImport}
        className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        title="导入书籍"
      >
        + 导入
      </button>
      <button
        onClick={onSettings}
        className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
        title="设置"
      >
        设置
      </button>
    </footer>
  )
}
