import { useState, useCallback, createContext, useContext } from 'react'

type ToastType = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

interface ToastCtx {
  toast: (msg: string, type?: ToastType) => void
}

const ToastContext = createContext<ToastCtx>({ toast: () => {} })
export const useToast = () => useContext(ToastContext)

let nextId = 0

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = nextId++
    setItems(prev => [...prev, { id, message, type }])
    setTimeout(() => setItems(prev => prev.filter(i => i.id !== id)), 3500)
  }, [])

  const colors: Record<ToastType, string> = {
    success: 'bg-[var(--success)]',
    error: 'bg-[var(--error)]',
    info: 'bg-[var(--text-secondary)]',
  }

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none">
        {items.map((item, i) => (
          <div
            key={item.id}
            className={`${colors[item.type]} text-[var(--text-inverse)] px-4 py-2.5 rounded-[var(--radius-md)] text-sm font-medium shadow-[var(--shadow-md)] pointer-events-auto animate-slide-up`}
            style={{ fontFamily: 'var(--font-ui)', animationDelay: `${i * 30}ms` }}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
