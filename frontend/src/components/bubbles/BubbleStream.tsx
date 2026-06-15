import { useState, useEffect } from 'react'
import type { TreeNode, Layer, JumpAnchor } from '../../types'
import { api } from '../../api/client'
import DepthToggle from './DepthToggle'
import BubbleCard from './BubbleCard'

const LAYER_STYLE: Record<number, { bar: string; pad: string; ml: string; mb: string; bg: string }> = {
  1: { bar: 'border-l-4 border-slate-600', pad: 'pl-3', ml: '',  mb: 'mb-3', bg: 'bg-slate-50/40' },
  2: { bar: 'border-l-2 border-slate-400', pad: 'pl-2', ml: 'ml-2', mb: 'mb-2', bg: 'bg-white' },
  3: { bar: 'border-l border-slate-300',   pad: 'pl-2', ml: 'ml-3', mb: 'mb-1', bg: 'bg-white' },
  4: { bar: '',                             pad: 'pl-1', ml: 'ml-4', mb: '',     bg: 'bg-slate-50/20' },
}

interface Props {
  bookId: number
  onJumpToReader: (bookId: number, anchor: JumpAnchor) => void
}

export default function BubbleStream({ bookId, onJumpToReader }: Props) {
  const [tree, setTree] = useState<TreeNode[]>([])
  const [depth, setDepth] = useState<Layer>(2)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const loadTree = async () => {
    setLoading(true)
    const { tree } = await api.getTree(bookId)
    setTree(tree)
    setExpanded(new Set())
    setLoading(false)
  }

  useEffect(() => { loadTree() }, [bookId])

  const toggleExpand = (nodeId: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId)
      return next
    })
  }

  const handleDepthChange = (d: Layer) => {
    setDepth(d)
    setExpanded(new Set())
  }

  const handleRightClick = (nodeId: number) => {
    setExpanded(prev => { const n = new Set(prev); n.delete(nodeId); return n })
  }

  const isExpanded = (node: TreeNode) => {
    if (node.layer >= 4) return false
    if (node.children.length === 0) return false
    return node.layer < depth || expanded.has(node.id)
  }

  const handleNodeClick = (node: TreeNode) => {
    // L4 点击 → 跳转原文位置
    if (node.layer === 4 && node.jump_anchor) {
      onJumpToReader(bookId, node.jump_anchor)
      return
    }
    // 有子节点 → 展开/收起
    if (node.children.length > 0) {
      toggleExpand(node.id)
    }
  }

  const renderNode = (node: TreeNode) => {
    const s = LAYER_STYLE[node.layer] || LAYER_STYLE[3]
    const showChildren = isExpanded(node)

    return (
      <div key={node.id} className={`${s.ml} ${s.mb}`}>
        <div className={s.pad}>
          <BubbleCard
            bubble={{
              id: node.id, layer: node.layer, title: node.title,
              content: showChildren ? '' : node.content,
              importance: node.importance,
              compress_state: 'detail',
              story_time_label: node.story_time_label,
              child_count: node.child_count,
              has_cross_refs: node.has_cross_refs,
            }}
            onClick={() => handleNodeClick(node)}
            onRightClick={() => handleRightClick(node.id)}
          />
        </div>

        {showChildren && node.children.length > 0 && (
          <div className={`mt-1 ${s.bar} ${s.bg} rounded-r`}>
            {node.children.map(child => renderNode(child))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)]">
        <span className="text-xs text-[var(--text-secondary)]">{tree.length} 个根节点</span>
        <DepthToggle current={depth} onChange={handleDepthChange} />
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading
          ? <div className="text-center text-sm text-[var(--text-secondary)] py-8">加载中...</div>
          : tree.length === 0
            ? <div className="text-center text-sm text-[var(--text-secondary)] py-8">
                {depth === 1 ? '暂无概括级内容' : '暂无内容'}
              </div>
            : tree.map(node => renderNode(node))}
      </div>
    </div>
  )
}
