import { useCallback, useRef, useEffect, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { fetchNeighbors } from '@/api/client'
import type { GraphData } from '@/types'

interface Props {
  graphData: GraphData | null
}

// 节点类型 → 颜色
const LABEL_COLORS: Record<string, string> = {
  Disease: '#ef4444',
  Symptom: '#f97316',
  Drug: '#3b82f6',
  Food: '#22c55e',
  Check: '#a855f7',
  Department: '#06b6d4',
  Producer: '#6b7280',
  center: '#eab308',
}

interface FGNode {
  id: string
  label: string
  x?: number
  y?: number
}

interface FGEdge {
  source: string | FGNode
  target: string | FGNode
  label: string
}

export default function GraphPanel({ graphData }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 400, height: 400 })
  const [data, setData] = useState<{ nodes: FGNode[]; links: FGEdge[] }>({ nodes: [], links: [] })

  // 跟踪容器尺寸
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // 图谱数据变化时更新
  useEffect(() => {
    if (!graphData || graphData.nodes.length === 0) {
      setData({ nodes: [], links: [] })
      return
    }
    setData({
      nodes: graphData.nodes.map(n => ({ ...n })),
      links: graphData.edges.map(e => ({ ...e })),
    })
  }, [graphData])

  // 点击节点 → 加载邻居
  const handleNodeClick = useCallback(async (node: FGNode) => {
    try {
      const res = await fetchNeighbors(node.id, 30)
      const gd = res.graph_data
      setData(prev => {
        const existingIds = new Set(prev.nodes.map(n => n.id))
        const newNodes = gd.nodes.filter(n => !existingIds.has(n.id)).map(n => ({ ...n }))
        const existingEdges = new Set(prev.links.map(l => {
          const s = typeof l.source === 'string' ? l.source : l.source.id
          const t = typeof l.target === 'string' ? l.target : l.target.id
          return `${s}-${t}-${l.label}`
        }))
        const newLinks = gd.edges
          .filter(e => !existingEdges.has(`${e.source}-${e.target}-${e.label}`))
          .map(e => ({ ...e }))
        return {
          nodes: [...prev.nodes, ...newNodes],
          links: [...prev.links, ...newLinks],
        }
      })
    } catch {
      // ignore
    }
  }, [])

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        发送问题后查看知识图谱可视化
      </div>
    )
  }

  return (
    <div ref={containerRef} className="h-full w-full relative">
      {/* 图例 */}
      <div className="absolute top-2 left-2 z-10 bg-white/90 rounded p-2 text-xs space-y-1 shadow">
        {Object.entries(LABEL_COLORS).filter(([k]) => k !== 'center').map(([label, color]) => (
          <div key={label} className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span>{label}</span>
          </div>
        ))}
      </div>

      <ForceGraph2D
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeLabel="id"
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        nodeColor={(node: any) => LABEL_COLORS[node.label ?? ''] || '#6b7280'}
        nodeRelSize={6}
        nodeCanvasObjectMode={() => 'after'}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
          const label = String(node.id ?? '')
          const fontSize = 12 / globalScale
          ctx.font = `${fontSize}px sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillStyle = '#333'
          ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + 10)
        }}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        linkLabel="label"
        linkColor={() => '#cbd5e1'}
        onNodeClick={(_node: object) => handleNodeClick(_node as FGNode)}
        cooldownTicks={100}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  )
}
