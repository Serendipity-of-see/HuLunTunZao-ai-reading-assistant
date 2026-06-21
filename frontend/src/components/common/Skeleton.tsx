interface SkeletonProps {
  className?: string
  style?: React.CSSProperties
}

export function Skeleton({ className = 'h-4 w-full rounded', style }: SkeletonProps) {
  return <div className={`animate-shimmer ${className}`} style={style} />
}

export function BookCardSkeleton() {
  return (
    <div className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-surface)] border border-[var(--border-light)] space-y-2">
      <Skeleton className="h-4 w-3/4 rounded" />
      <Skeleton className="h-3 w-1/2 rounded" />
      <div className="flex gap-2 mt-2">
        <Skeleton className="h-5 w-12 rounded-full" />
        <Skeleton className="h-5 w-12 rounded-full" />
      </div>
    </div>
  )
}

export function BubbleSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="p-3 rounded-[var(--radius-md)] bg-[var(--bg-surface)] border border-[var(--border-light)]"
             style={{ marginLeft: `${(i % 3) * 16}px` }}>
          <div className="flex items-center gap-2">
            <Skeleton className="h-1 w-1 rounded-full" />
            <Skeleton className="h-4 w-2/3 rounded" />
          </div>
          <Skeleton className="h-3 w-full rounded mt-2" />
          <Skeleton className="h-3 w-5/6 rounded mt-1" />
        </div>
      ))}
    </div>
  )
}

export function ReaderSkeleton() {
  return (
    <div className="max-w-2xl mx-auto px-8 py-12 space-y-3">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton key={i} className="h-4 rounded" style={{ width: `${85 + Math.random() * 15}%` }} />
      ))}
    </div>
  )
}
