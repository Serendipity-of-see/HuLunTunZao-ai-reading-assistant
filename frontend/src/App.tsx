import { useState } from 'react'
import TabBar from './components/layout/TabBar'
import BottomBar from './components/layout/BottomBar'
import LibraryPage from './views/LibraryPage'
import ReaderPage from './views/ReaderPage'
import ArchivePage from './views/ArchivePage'
import SettingsPage from './views/SettingsPage'
import type { JumpAnchor } from './types'

export type Tab = 'library' | 'reader' | 'archive' | 'settings'

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
    <div className="h-screen flex flex-col bg-[var(--bg-primary)]">
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 overflow-hidden">
        {activeTab === 'library' && (
          <LibraryPage
            onBookSelect={(id) => { setCurrentBookId(id); setActiveTab('reader') }}
          />
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
      <BottomBar
        onImport={() => setActiveTab('library')}
        onSettings={() => setActiveTab('settings')}
      />
    </div>
  )
}

export default App
