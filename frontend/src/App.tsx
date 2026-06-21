import { useState, Component, ErrorInfo, ReactNode } from 'react'
import { ToastProvider } from './components/common/Toast'
import TabBar from './components/layout/TabBar'
import LibraryPage from './views/LibraryPage'
import ReaderPage from './views/ReaderPage'
import ArchivePage from './views/ArchivePage'
import SettingsPage from './views/SettingsPage'
import type { JumpAnchor } from './types'

export type Tab = 'library' | 'reader' | 'archive' | 'settings'

// Error boundary to show runtime errors on screen
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Crash:', error, info) }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, fontFamily: 'monospace', color: '#C4523A', background: '#FFFCF5', minHeight: '100vh' }}>
          <h1>Runtime Error</h1>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginTop: 16 }}>
            {this.state.error.message}
          </pre>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, color: '#6B5E53', marginTop: 8 }}>
            {this.state.error.stack}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('library')
  const [currentBookId, setCurrentBookId] = useState<number | null>(null)
  const [jumpTarget, setJumpTarget] = useState<JumpAnchor | null>(null)

  const handleJumpToReader = (bookId: number, anchor: JumpAnchor) => {
    setCurrentBookId(bookId)
    setJumpTarget(anchor)
    setActiveTab('reader')
  }

  return (
    <ErrorBoundary>
      <ToastProvider>
        <div className="h-screen flex flex-col bg-[var(--bg-page)]">
        <TabBar activeTab={activeTab} onTabChange={setActiveTab} hasBook={!!currentBookId} />
        <main className="flex-1 overflow-hidden">
          {activeTab === 'library' && (
            <LibraryPage onBookSelect={(id) => { setCurrentBookId(id); setActiveTab('reader') }} />
          )}
          {activeTab === 'reader' && currentBookId && (
            <ReaderPage bookId={currentBookId} jumpTarget={jumpTarget} onJumpConsumed={() => setJumpTarget(null)} />
          )}
          {activeTab === 'archive' && currentBookId && (
            <ArchivePage bookId={currentBookId} onJumpToReader={handleJumpToReader} />
          )}
          {activeTab === 'settings' && (
            <SettingsPage />
          )}
        </main>
      </div>
    </ToastProvider>
    </ErrorBoundary>
  )
}

export default App
