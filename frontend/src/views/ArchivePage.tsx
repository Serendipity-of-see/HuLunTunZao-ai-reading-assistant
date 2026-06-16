import BubbleStream from '../components/bubbles/BubbleStream'
import type { JumpAnchor } from '../types'

interface Props {
  bookId: number
  onJumpToReader: (bookId: number, anchor: JumpAnchor) => void
}

export default function ArchivePage({ bookId, onJumpToReader }: Props) {
  return (
    <div className="h-full">
      <BubbleStream bookId={bookId} onJumpToReader={onJumpToReader} />
    </div>
  )
}
