import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import type { TreeNode, Layer, JumpAnchor } from '../../types'
import { api } from '../../api/client'
import DepthToggle from './DepthToggle'
import BubbleCard from './BubbleCard'

interface Props { bookId: number; onJumpToReader: (bookId: number, anchor: JumpAnchor) => void
  onRegisterHandlers?: (handlers: { addNode: (pid: number, n: TreeNode) => void; removeNode: (nid: number) => void }) => void
}

export default function BubbleStream({ bookId, onJumpToReader, onRegisterHandlers }: Props) {
  const [tree, setTree] = useState<TreeNode[]>([])
  const [depth, setDepth] = useState<Layer>(2)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const lastFocusedRef = useRef<number | null>(null)
  const treeRef = useRef(tree)
  treeRef.current = tree
  const containerRef = useRef<HTMLDivElement>(null)
  const LS_KEY = `hltz-last-expand-${bookId}`

  const addNode = useCallback((parentId: number, newNode: TreeNode) => {
    setTree(prev => {
      const clone = (nodes: TreeNode[]): TreeNode[] => nodes.map(n => {
        if (n.id === parentId && !n.children.some(c => c.id === newNode.id)) {
          return { ...n, children: [...n.children, newNode], child_count: n.child_count + 1 }
        }
        return n.children.length ? { ...n, children: clone(n.children) } : n
      })
      return clone(prev)
    })
  }, [])

  const removeNode = useCallback((nodeId: number) => {
    setTree(prev => {
      const clone = (nodes: TreeNode[]): TreeNode[] =>
        nodes.filter(n => n.id !== nodeId).map(n =>
          n.children.length ? { ...n, children: clone(n.children) } : n
        )
      return clone(prev)
    })
    if (lastFocusedRef.current === nodeId) {
      const findParent = (nodes: TreeNode[], target: number): number | null => {
        for (const n of nodes) {
          if (n.children.some(c => c.id === target)) return n.id
          const p = findParent(n.children, target)
          if (p !== null) return p
        }
        return null
      }
      const parent = findParent(treeRef.current, nodeId)
      lastFocusedRef.current = parent
    }
  }, [])

  useEffect(() => {
    onRegisterHandlers?.({ addNode, removeNode })
  }, [addNode, removeNode, onRegisterHandlers])

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    api.getTree(bookId).then(({ tree }) => {
      if (cancelled) return
      setTree(tree)
      // 恢复上次展开位置
      let savedId: number | null = null
      try { const v = localStorage.getItem(LS_KEY); if (v) savedId = parseInt(v) } catch {}
      if (savedId) {
        const ancestors: number[] = []
        const findPath = (nodes: TreeNode[], target: number): boolean => {
          for (const n of nodes) {
            if (n.id === target || n.children.some(c => c.id === target) || findPath(n.children, target)) {
              ancestors.push(n.id); return true
            }
          }
          return false
        }
        if (findPath(tree, savedId) || tree.some(n => n.id === savedId)) {
          setExpanded(new Set(ancestors))
          lastFocusedRef.current = savedId
          setTimeout(() => {
            document.getElementById(`bubble-${savedId}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
          }, 200)
        }
      }
    }).catch(e => { if (!cancelled) setError(e.message || '加载失败') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [bookId, LS_KEY])

  const visibleRoots = useMemo(() => {
    if (!search.trim()) return tree
    const q = search.toLowerCase()
    const matchNode = (n: TreeNode): boolean =>
      n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q) || n.children.some(matchNode)
    return tree.filter(matchNode)
  }, [tree, search])

  const toggleExpand = (nodeId: number) => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(nodeId)) { next.delete(nodeId) }
    else { next.add(nodeId); lastFocusedRef.current = nodeId }
    return next
  })
  // 持久化最后展开位置
  useEffect(() => {
    if (lastFocusedRef.current) {
      try { localStorage.setItem(LS_KEY, String(lastFocusedRef.current)) } catch {}
    }
  }, [expanded, LS_KEY])

  const isExpanded = (node: TreeNode) => {
    if (node.layer >= 4 || !node.children.length) return false
    return node.layer < depth || expanded.has(node.id)
  }

  const handleClick = (node: TreeNode) => {
    if (node.layer === 4 && node.jump_anchor) { onJumpToReader(bookId, node.jump_anchor); return }
    if (node.children.length) toggleExpand(node.id)
  }

  const renderNode = (node: TreeNode) => {
    const showChildren = isExpanded(node)
    const expandable = node.layer < 4 && node.children.length > 0
    return (
      <BubbleCard
        key={node.id}
        bubble={{ id: node.id, layer: node.layer, title: node.title,
          content: showChildren ? '' : node.content, importance: node.importance, compress_state: 'detail',
          story_time_label: node.story_time_label, child_count: node.child_count, has_cross_refs: node.has_cross_refs }}
        expanded={showChildren} expandable={expandable}
        crossRefs={node.cross_refs || []} onClick={() => handleClick(node)}
      >
        {showChildren && node.children.map(child => renderNode(child))}
      </BubbleCard>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-[var(--border)]">
        <span className="text-xs shrink-0" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>
          {visibleRoots.length} 根节点
        </span>
        <input type="text" value={search} onChange={e => setSearch(e.target.value)}
          placeholder="搜索..." className="flex-1 text-xs px-2 py-1 rounded-[var(--radius-sm)] border border-[var(--border)]
            bg-[var(--bg-surface)] outline-none focus:border-[var(--border-focus)] transition-colors"
          style={{ fontFamily: 'var(--font-ui)' }} />
        <DepthToggle current={depth} onChange={d => { setDepth(d); setExpanded(new Set()) }} />
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {loading
            ? <div className="text-center text-sm py-8 animate-pulse-soft" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-secondary)' }}>加载中...</div>
            : error
              ? <div className="text-center text-sm py-8" style={{ fontFamily: 'var(--font-ui)', color: 'var(--error)' }}>{error}</div>
              : visibleRoots.length === 0
                ? <div className="text-center text-sm py-8" style={{ fontFamily: 'var(--font-ui)', color: 'var(--text-tertiary)' }}>
                    {search ? '无匹配结果' : depth === 1 ? '暂无概括级内容' : '暂无内容'}
                  </div>
                : visibleRoots.map(node => renderNode(node))}
        </div>
      </div>
    </div>
  )
}
