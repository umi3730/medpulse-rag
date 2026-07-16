import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { fetchNeighbors } from '@/api/client'
import type { GraphData } from '@/types'
import {
  ChevronDown,
  Eye,
  EyeOff,
  Expand,
  Loader2,
  Maximize2,
  Network,
  RotateCcw,
  Search,
} from 'lucide-react'

interface Props {
  graphData: GraphData | null
  focusNodeIds?: string[]
}

type DensityMode = 'focused' | 'balanced' | 'expanded'
type LabelMode = 'auto' | 'all' | 'off'

interface DensityConfig {
  label: string
  maxNodes: number
  maxLinks: number
  maxComponents: number
  charge: number
  linkDistance: number
  nodeRelSize: number
}

const DENSITY_CONFIG: Record<DensityMode, DensityConfig> = {
  focused: {
    label: '核心',
    maxNodes: 30,
    maxLinks: 54,
    maxComponents: 1,
    charge: -430,
    linkDistance: 92,
    nodeRelSize: 6.2,
  },
  balanced: {
    label: '均衡',
    maxNodes: 54,
    maxLinks: 120,
    maxComponents: 1,
    charge: -330,
    linkDistance: 72,
    nodeRelSize: 5.8,
  },
  expanded: {
    label: '全景',
    maxNodes: 90,
    maxLinks: 220,
    maxComponents: 3,
    charge: -240,
    linkDistance: 58,
    nodeRelSize: 5.3,
  },
}

const LABEL_COLORS: Record<string, string> = {
  Disease: '#be123c',
  Symptom: '#d97706',
  Drug: '#2563eb',
  Food: '#059669',
  Check: '#7c3aed',
  Department: '#0891b2',
  Producer: '#64748b',
  center: '#0f766e',
}

const LABEL_NAMES: Record<string, string> = {
  Disease: '疾病',
  Symptom: '症状',
  Drug: '药品',
  Food: '食物',
  Check: '检查',
  Department: '科室',
  Producer: '生产商',
  center: '查询实体',
}

const RELATION_NAMES: Record<string, string> = {
  common_drug: '常用药',
  recommand_drug: '推荐药',
  drugs_of: '生产药品',
  do_eat: '宜吃',
  no_eat: '忌口',
  recommand_eat: '推荐饮食',
  need_check: '检查项目',
  has_symptom: '相关症状',
  acompany_with: '并发疾病',
  belongs_to: '所属科室',
  dept_belongs_to: '上级科室',
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

interface VisibleGraph {
  nodes: FGNode[]
  links: FGEdge[]
  hiddenNodes: number
  hiddenLinks: number
  componentCount: number
}

const getNodeId = (node: string | FGNode) => typeof node === 'string' ? node : node.id

const getEdgeKey = (edge: FGEdge) => (
  `${getNodeId(edge.source)}\u0000${getNodeId(edge.target)}\u0000${edge.label}`
)

function buildDegree(nodes: FGNode[], links: FGEdge[]) {
  const nodeIds = new Set(nodes.map(node => node.id))
  const degree = new Map(nodes.map(node => [node.id, 0]))

  links.forEach(link => {
    const source = getNodeId(link.source)
    const target = getNodeId(link.target)
    if (!nodeIds.has(source) || !nodeIds.has(target)) return
    degree.set(source, (degree.get(source) ?? 0) + 1)
    degree.set(target, (degree.get(target) ?? 0) + 1)
  })

  return degree
}

function rankNodes(nodes: FGNode[], degree: Map<string, number>, focusIds: Set<string>) {
  return [...nodes].sort((a, b) => {
    if (focusIds.has(a.id) && !focusIds.has(b.id)) return -1
    if (focusIds.has(b.id) && !focusIds.has(a.id)) return 1
    if (a.label === 'center' && b.label !== 'center') return -1
    if (b.label === 'center' && a.label !== 'center') return 1
    return (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.id.localeCompare(b.id, 'zh-Hans-CN')
  })
}

function countComponents(nodeIds: string[], links: FGEdge[]) {
  const adjacency = new Map(nodeIds.map(id => [id, new Set<string>()]))
  links.forEach(link => {
    const source = getNodeId(link.source)
    const target = getNodeId(link.target)
    adjacency.get(source)?.add(target)
    adjacency.get(target)?.add(source)
  })

  const visited = new Set<string>()
  let components = 0
  nodeIds.forEach(id => {
    if (visited.has(id)) return
    components += 1
    const queue = [id]
    visited.add(id)
    while (queue.length > 0) {
      const current = queue.shift()!
      adjacency.get(current)?.forEach(neighbor => {
        if (visited.has(neighbor)) return
        visited.add(neighbor)
        queue.push(neighbor)
      })
    }
  })
  return components
}

function selectConnectedGraph(
  nodes: FGNode[],
  links: FGEdge[],
  focusNodeIds: string[],
  maxNodes: number,
  maxLinks: number,
  maxComponents: number,
): VisibleGraph {
  if (nodes.length === 0) {
    return { nodes: [], links: [], hiddenNodes: 0, hiddenLinks: 0, componentCount: 0 }
  }

  const nodeById = new Map(nodes.map(node => [node.id, node]))
  const validLinks = links.filter(link => (
    nodeById.has(getNodeId(link.source)) && nodeById.has(getNodeId(link.target))
  ))
  const requestedFocus = new Set(focusNodeIds.filter(id => nodeById.has(id)))
  const degree = buildDegree(nodes, validLinks)
  const rankedNodes = rankNodes(nodes, degree, requestedFocus)
  const fallbackSeeds = nodes.filter(node => node.label === 'center').map(node => node.id)
  const seedIds = requestedFocus.size > 0
    ? [...requestedFocus]
    : fallbackSeeds.length > 0
      ? fallbackSeeds
      : rankedNodes.slice(0, 1).map(node => node.id)

  const adjacency = new Map<string, Array<{ neighbor: string; edge: FGEdge }>>()
  nodes.forEach(node => adjacency.set(node.id, []))
  validLinks.forEach(edge => {
    const source = getNodeId(edge.source)
    const target = getNodeId(edge.target)
    adjacency.get(source)?.push({ neighbor: target, edge })
    adjacency.get(target)?.push({ neighbor: source, edge })
  })

  adjacency.forEach(entries => {
    entries.sort((a, b) => {
      if (requestedFocus.has(a.neighbor) && !requestedFocus.has(b.neighbor)) return -1
      if (requestedFocus.has(b.neighbor) && !requestedFocus.has(a.neighbor)) return 1
      return (degree.get(b.neighbor) ?? 0) - (degree.get(a.neighbor) ?? 0)
        || a.neighbor.localeCompare(b.neighbor, 'zh-Hans-CN')
    })
  })

  const selectedIds = new Set<string>()
  const selectedOrder: string[] = []
  const queue: string[] = []

  const addSeed = (id: string) => {
    if (selectedIds.has(id) || selectedIds.size >= maxNodes) return
    selectedIds.add(id)
    selectedOrder.push(id)
    queue.push(id)
  }

  seedIds.forEach(addSeed)

  const drainQueue = () => {
    while (queue.length > 0 && selectedIds.size < maxNodes) {
      const current = queue.shift()!
      for (const { neighbor } of adjacency.get(current) || []) {
        if (selectedIds.has(neighbor)) continue
        selectedIds.add(neighbor)
        selectedOrder.push(neighbor)
        queue.push(neighbor)
        if (selectedIds.size >= maxNodes) break
      }
    }
  }

  drainQueue()

  let secondaryComponents = 1
  if (maxComponents > 1 && selectedIds.size < maxNodes) {
    for (const node of rankedNodes) {
      if (secondaryComponents >= maxComponents || selectedIds.size >= maxNodes) break
      if (selectedIds.has(node.id)) continue
      addSeed(node.id)
      secondaryComponents += 1
      drainQueue()
    }
  }

  const candidateLinks = validLinks.filter(link => (
    selectedIds.has(getNodeId(link.source)) && selectedIds.has(getNodeId(link.target))
  ))
  const sortedLinks = [...candidateLinks].sort((a, b) => {
    const aSource = getNodeId(a.source)
    const aTarget = getNodeId(a.target)
    const bSource = getNodeId(b.source)
    const bTarget = getNodeId(b.target)
    const aFocus = Number(requestedFocus.has(aSource)) + Number(requestedFocus.has(aTarget))
    const bFocus = Number(requestedFocus.has(bSource)) + Number(requestedFocus.has(bTarget))
    if (aFocus !== bFocus) return bFocus - aFocus
    const aScore = (degree.get(aSource) ?? 0) + (degree.get(aTarget) ?? 0)
    const bScore = (degree.get(bSource) ?? 0) + (degree.get(bTarget) ?? 0)
    return bScore - aScore || getEdgeKey(a).localeCompare(getEdgeKey(b), 'zh-Hans-CN')
  })

  const parent = new Map(selectedOrder.map(id => [id, id]))
  const find = (id: string): string => {
    const currentParent = parent.get(id) ?? id
    if (currentParent === id) return id
    const root = find(currentParent)
    parent.set(id, root)
    return root
  }
  const union = (a: string, b: string) => {
    const aRoot = find(a)
    const bRoot = find(b)
    if (aRoot === bRoot) return false
    parent.set(bRoot, aRoot)
    return true
  }

  const backbone: FGEdge[] = []
  const supplementary: FGEdge[] = []
  sortedLinks.forEach(link => {
    const source = getNodeId(link.source)
    const target = getNodeId(link.target)
    if (union(source, target)) backbone.push(link)
    else supplementary.push(link)
  })

  const selectedLinks = [...backbone, ...supplementary].slice(0, maxLinks)
  const linkedNodeIds = new Set<string>()
  selectedLinks.forEach(link => {
    linkedNodeIds.add(getNodeId(link.source))
    linkedNodeIds.add(getNodeId(link.target))
  })
  requestedFocus.forEach(id => linkedNodeIds.add(id))

  const selectedNodes = selectedOrder
    .filter(id => linkedNodeIds.has(id))
    .map(id => ({ ...nodeById.get(id)! }))
  const finalNodeIds = new Set(selectedNodes.map(node => node.id))
  const finalLinks = selectedLinks
    .filter(link => finalNodeIds.has(getNodeId(link.source)) && finalNodeIds.has(getNodeId(link.target)))
    .map(link => ({ ...link }))

  return {
    nodes: selectedNodes,
    links: finalLinks,
    hiddenNodes: Math.max(0, nodes.length - selectedNodes.length),
    hiddenLinks: Math.max(0, links.length - finalLinks.length),
    componentCount: countComponents(selectedNodes.map(node => node.id), finalLinks),
  }
}

export default function GraphPanel({ graphData, focusNodeIds = [] }: Props) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null)
  const [containerEl, setContainerEl] = useState<HTMLDivElement | null>(null)
  const [dimensions, setDimensions] = useState({ width: 400, height: 400 })
  const [data, setData] = useState<{ nodes: FGNode[]; links: FGEdge[] }>({ nodes: [], links: [] })
  const [density, setDensity] = useState<DensityMode>('focused')
  const [labelMode, setLabelMode] = useState<LabelMode>('auto')
  const [hoverNodeId, setHoverNodeId] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [expandingNodeId, setExpandingNodeId] = useState<string | null>(null)
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set())

  const config = DENSITY_CONFIG[density]
  const focusIds = useMemo(() => new Set(focusNodeIds), [focusNodeIds])

  const containerRef = useCallback((element: HTMLDivElement | null) => {
    setContainerEl(element)
  }, [])

  useEffect(() => {
    if (!containerEl) return

    const measure = () => {
      const rect = containerEl.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setDimensions({ width: rect.width, height: rect.height })
      }
    }
    measure()
    const frame = requestAnimationFrame(measure)
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setDimensions({ width, height })
    })
    observer.observe(containerEl)
    return () => {
      observer.disconnect()
      cancelAnimationFrame(frame)
    }
  }, [containerEl])

  useEffect(() => {
    if (!graphData || graphData.nodes.length === 0) {
      setData({ nodes: [], links: [] })
    } else {
      setData({
        nodes: graphData.nodes.map(node => ({ ...node })),
        links: graphData.edges.map(edge => ({ ...edge })),
      })
    }
    setHoverNodeId(null)
    setSelectedNodeId(null)
    setExpandedNodeIds(new Set())
  }, [graphData])

  const budgets = useMemo(() => {
    const areaBudget = Math.max(18, Math.floor((dimensions.width * dimensions.height) / 6500))
    const maxNodes = Math.min(config.maxNodes, areaBudget)
    const maxLinks = Math.min(config.maxLinks, Math.max(maxNodes - 1, Math.floor(maxNodes * 2.25)))
    return { maxNodes, maxLinks }
  }, [config.maxLinks, config.maxNodes, dimensions.height, dimensions.width])

  const visibleData = useMemo(() => selectConnectedGraph(
    data.nodes,
    data.links,
    [...focusIds],
    budgets.maxNodes,
    budgets.maxLinks,
    config.maxComponents,
  ), [budgets.maxLinks, budgets.maxNodes, config.maxComponents, data.links, data.nodes, focusIds])

  const visibleDegree = useMemo(() => buildDegree(visibleData.nodes, visibleData.links), [visibleData.links, visibleData.nodes])
  const activeNodeId = hoverNodeId || selectedNodeId

  const activeNeighborhood = useMemo(() => {
    const nodeIds = new Set<string>()
    const edgeIds = new Set<string>()
    const connections: Array<{ neighbor: string; relation: string; outgoing: boolean }> = []
    if (!activeNodeId) return { nodeIds, edgeIds, connections }

    nodeIds.add(activeNodeId)
    visibleData.links.forEach(link => {
      const source = getNodeId(link.source)
      const target = getNodeId(link.target)
      if (source !== activeNodeId && target !== activeNodeId) return
      nodeIds.add(source)
      nodeIds.add(target)
      edgeIds.add(getEdgeKey(link))
      connections.push({
        neighbor: source === activeNodeId ? target : source,
        relation: link.label,
        outgoing: source === activeNodeId,
      })
    })
    connections.sort((a, b) => (
      (RELATION_NAMES[a.relation] || a.relation).localeCompare(RELATION_NAMES[b.relation] || b.relation, 'zh-Hans-CN')
      || a.neighbor.localeCompare(b.neighbor, 'zh-Hans-CN')
    ))
    return { nodeIds, edgeIds, connections }
  }, [activeNodeId, visibleData.links])

  const activeNode = activeNodeId
    ? visibleData.nodes.find(node => node.id === activeNodeId) || null
    : null

  useEffect(() => {
    const graph = fgRef.current
    if (!graph) return

    graph.d3Force?.('charge')?.strength(config.charge)
    graph.d3Force?.('link')?.distance(config.linkDistance)?.strength(0.34)
    graph.d3ReheatSimulation?.()

    const timer = window.setTimeout(() => {
      graph.zoomToFit?.(420, 72)
    }, 520)
    return () => window.clearTimeout(timer)
  }, [config.charge, config.linkDistance, visibleData.links.length, visibleData.nodes.length])

  const handleExpandNode = useCallback(async (nodeId: string) => {
    if (expandingNodeId || expandedNodeIds.has(nodeId)) return
    setExpandingNodeId(nodeId)
    try {
      const response = await fetchNeighbors(nodeId, density === 'expanded' ? 45 : 24)
      const graph = response.graph_data
      setData(previous => {
        const existingIds = new Set(previous.nodes.map(node => node.id))
        const existingEdges = new Set(previous.links.map(getEdgeKey))
        const newNodes = graph.nodes.filter(node => !existingIds.has(node.id)).map(node => ({ ...node }))
        const newLinks = graph.edges.filter(edge => !existingEdges.has(getEdgeKey(edge))).map(edge => ({ ...edge }))
        return { nodes: [...previous.nodes, ...newNodes], links: [...previous.links, ...newLinks] }
      })
      setExpandedNodeIds(previous => new Set(previous).add(nodeId))
    } finally {
      setExpandingNodeId(null)
    }
  }, [density, expandedNodeIds, expandingNodeId])

  const handleReset = () => {
    if (!graphData) return
    setData({
      nodes: graphData.nodes.map(node => ({ ...node })),
      links: graphData.edges.map(edge => ({ ...edge })),
    })
    setSelectedNodeId(null)
    setExpandedNodeIds(new Set())
  }

  const handleZoomToFit = () => {
    fgRef.current?.zoomToFit?.(350, 72)
  }

  const cycleLabelMode = () => {
    setLabelMode(current => current === 'auto' ? 'all' : current === 'all' ? 'off' : 'auto')
  }

  const shouldDrawLabel = (node: FGNode, globalScale: number) => {
    if (labelMode === 'off') return false
    if (focusIds.has(node.id) || node.id === activeNodeId || node.label === 'center') return true
    if (activeNodeId && !activeNeighborhood.nodeIds.has(node.id)) return false
    if (labelMode === 'all') return globalScale >= 0.72

    const degree = visibleDegree.get(node.id) ?? 0
    const minDegree = density === 'expanded' ? 5 : density === 'balanced' ? 3 : 2
    return globalScale >= 0.84 && degree >= minDegree
  }

  const nodeValue = (node: FGNode) => {
    const degree = visibleDegree.get(node.id) ?? 0
    const focusBoost = focusIds.has(node.id) || node.label === 'center' ? 1.5 : 0
    const activeBoost = node.id === activeNodeId ? 0.8 : 0
    return 1 + Math.min(2.2, degree * 0.16) + focusBoost + activeBoost
  }

  const labelText = (node: FGNode) => {
    const raw = String(node.id ?? '')
    if (focusIds.has(node.id) || node.id === activeNodeId || node.label === 'center') return raw
    const maxLength = density === 'expanded' ? 8 : density === 'balanced' ? 10 : 12
    return raw.length > maxLength ? `${raw.slice(0, maxLength)}…` : raw
  }

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-[#f7f9f8] p-8 text-center">
        <div className="max-w-[17rem]">
          <div className="mx-auto mb-4 flex size-11 items-center justify-center rounded-lg bg-[#e8efec] text-[#668078]">
            <Network className="size-5" strokeWidth={1.7} />
          </div>
          <p className="text-sm font-semibold text-[#34423d]">等待子图数据</p>
          <p className="mt-1.5 text-xs leading-5 text-[#84918b]">查询完成后，可在这里检查实体关系。</p>
        </div>
      </div>
    )
  }

  const hasExpandedData = data.nodes.length > graphData.nodes.length || data.links.length > graphData.edges.length

  return (
    <div ref={containerRef} className="graph-grid relative h-full w-full cursor-grab overflow-hidden bg-[#f7f9f8] active:cursor-grabbing">
      <details className="group absolute left-3 top-3 z-20 rounded-md border border-[#d8e1dd] bg-[#fbfcfb]/96 text-xs shadow-[0_8px_24px_rgba(31,65,55,0.08)] backdrop-blur-md">
        <summary className="flex h-8 cursor-pointer list-none items-center gap-1.5 px-2.5 font-medium text-[#52635c] outline-none focus-visible:ring-2 focus-visible:ring-[#6d9d91] [&::-webkit-details-marker]:hidden">
          <Search className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
          图例
          <ChevronDown className="size-3 text-[#87948e] transition-transform duration-200 group-open:rotate-180" />
        </summary>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-[#e0e7e4] px-3 pb-3 pt-2.5">
          {Object.entries(LABEL_COLORS).filter(([label]) => label !== 'center').map(([label, color]) => (
            <div key={label} className="flex items-center gap-1.5 text-[#65746e]">
              <span className="inline-block size-2.5 rounded-full" style={{ backgroundColor: color }} />
              <span>{LABEL_NAMES[label] || label}</span>
            </div>
          ))}
        </div>
      </details>

      <div className="absolute right-3 top-3 z-10 rounded-md border border-[#d8e1dd] bg-[#fbfcfb]/96 px-2.5 py-2 font-mono text-[0.67rem] text-[#73817b] shadow-[0_8px_24px_rgba(31,65,55,0.07)] backdrop-blur-md">
        <span className="font-semibold text-[#22312c]">{visibleData.nodes.length}</span> / {data.nodes.length} 节点
        <span className="mx-1.5 text-[#c3cdc9]">·</span>
        <span className="font-semibold text-[#22312c]">{visibleData.links.length}</span> / {data.links.length} 关系
        {visibleData.componentCount > 1 && (
          <><span className="mx-1.5 text-[#c3cdc9]">·</span>{visibleData.componentCount} 个簇</>
        )}
      </div>

      {activeNode && (
        <div className="absolute left-3 top-14 z-10 w-[min(16rem,calc(100%-1.5rem))] rounded-md border border-[#d4dfda] bg-[#fbfcfb]/96 p-3 shadow-[0_10px_28px_rgba(31,65,55,0.1)] backdrop-blur-md">
          <div className="flex items-start gap-2.5">
            <span
              className="mt-1 size-2.5 shrink-0 rounded-full ring-4 ring-white"
              style={{ backgroundColor: LABEL_COLORS[activeNode.label] || '#64748b' }}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-[#26352f]" title={activeNode.id}>{activeNode.id}</p>
              <p className="mt-0.5 text-[0.65rem] text-[#819088]">
                {LABEL_NAMES[activeNode.label] || activeNode.label} · {visibleDegree.get(activeNode.id) ?? 0} 条可见关系
              </p>
            </div>
          </div>
          {activeNeighborhood.connections.length > 0 && (
            <div className="mt-2.5 divide-y divide-[#e5ebe8] border-y border-[#e0e7e4]">
              {activeNeighborhood.connections.slice(0, 4).map((connection, index) => (
                <div key={`${connection.neighbor}-${connection.relation}-${index}`} className="grid grid-cols-[4.6rem_minmax(0,1fr)] items-center gap-2 py-1.5 text-[0.62rem]">
                  <span className="truncate text-[#708079]">{RELATION_NAMES[connection.relation] || connection.relation}</span>
                  <span className="truncate font-medium text-[#384a43]" title={connection.neighbor}>
                    {connection.outgoing ? '→' : '←'} {connection.neighbor}
                  </span>
                </div>
              ))}
              {activeNeighborhood.connections.length > 4 && (
                <p className="py-1.5 text-[0.6rem] text-[#89968f]">另有 {activeNeighborhood.connections.length - 4} 条关系</p>
              )}
            </div>
          )}
          {selectedNodeId === activeNode.id && (
            <button
              type="button"
              onClick={() => handleExpandNode(activeNode.id)}
              disabled={expandingNodeId === activeNode.id || expandedNodeIds.has(activeNode.id)}
              className="mt-3 inline-flex h-7 items-center gap-1.5 rounded-[4px] bg-[#174f43] px-2.5 text-[0.66rem] font-medium text-white transition-colors hover:bg-[#276255] disabled:bg-[#dfe7e3] disabled:text-[#86938d]"
            >
              {expandingNodeId === activeNode.id ? <Loader2 className="size-3 animate-spin" /> : <Expand className="size-3" />}
              {expandedNodeIds.has(activeNode.id) ? '已展开' : expandingNodeId === activeNode.id ? '展开中' : '展开邻居'}
            </button>
          )}
        </div>
      )}

      <div className="absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-1.5 rounded-lg border border-[#d8e1dd] bg-[#fbfcfb]/96 p-1.5 text-xs shadow-[0_10px_28px_rgba(31,65,55,0.1)] backdrop-blur-md">
        <div className="flex rounded-md bg-[#e9efec] p-0.5">
          {(Object.keys(DENSITY_CONFIG) as DensityMode[]).map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => setDensity(mode)}
              title={mode === 'focused' ? '只看查询实体的核心邻域' : mode === 'balanced' ? '显示更多相关关系' : '显示多个连通簇'}
              className={`h-7 rounded-[4px] px-2.5 text-[0.68rem] font-medium transition-all active:translate-y-px ${
                density === mode ? 'bg-white text-[#276255] shadow-sm' : 'text-[#718079] hover:bg-white/70 hover:text-[#33433d]'
              }`}
            >
              {DENSITY_CONFIG[mode].label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={cycleLabelMode}
          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#d8e1dd] bg-white px-2.5 text-[0.68rem] font-medium text-[#52635c] transition-all hover:border-[#91afa5] hover:text-[#276255] active:translate-y-px"
          title="切换标签显示"
        >
          {labelMode === 'off' ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
          {labelMode === 'auto' ? '关键标签' : labelMode === 'all' ? '全部标签' : '隐藏标签'}
        </button>

        <button
          type="button"
          onClick={handleZoomToFit}
          className="flex size-8 items-center justify-center rounded-md border border-[#d8e1dd] bg-white text-[#52635c] transition-all hover:border-[#91afa5] hover:text-[#276255] active:translate-y-px"
          title="适配视图"
          aria-label="适配视图"
        >
          <Maximize2 className="size-3.5" />
        </button>

        {hasExpandedData && (
          <button
            type="button"
            onClick={handleReset}
            className="flex size-8 items-center justify-center rounded-md border border-[#d8e1dd] bg-white text-[#52635c] transition-all hover:border-[#91afa5] hover:text-[#276255] active:translate-y-px"
            title="恢复检索子图"
            aria-label="恢复检索子图"
          >
            <RotateCcw className="size-3.5" />
          </button>
        )}

        {visibleData.hiddenNodes > 0 && (
          <span className="px-1.5 font-mono text-[0.62rem] text-[#7e8c86]">折叠 {visibleData.hiddenNodes} 节点</span>
        )}
      </div>

      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={visibleData}
        nodeLabel={(node: object) => {
          const graphNode = node as FGNode
          return `${graphNode.id} · ${LABEL_NAMES[graphNode.label] || graphNode.label}`
        }}
        nodeVal={(node: object) => nodeValue(node as FGNode)}
        nodeRelSize={config.nodeRelSize}
        nodeColor={(node: object) => {
          const graphNode = node as FGNode
          if (activeNodeId && !activeNeighborhood.nodeIds.has(graphNode.id)) return 'rgba(148,163,184,0.22)'
          return LABEL_COLORS[graphNode.label] || '#64748b'
        }}
        nodeCanvasObjectMode={() => 'after'}
        nodeCanvasObject={(node: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
          const graphNode = node as FGNode
          const x = graphNode.x ?? 0
          const y = graphNode.y ?? 0
          const radius = config.nodeRelSize * Math.sqrt(nodeValue(graphNode))
          const isFocus = focusIds.has(graphNode.id) || graphNode.label === 'center'
          const isActive = graphNode.id === activeNodeId

          if (isFocus || isActive) {
            ctx.beginPath()
            ctx.arc(x, y, radius + (isActive ? 3.8 : 2.8), 0, Math.PI * 2)
            ctx.strokeStyle = isActive ? '#173f36' : 'rgba(15,118,110,0.72)'
            ctx.lineWidth = (isActive ? 2.2 : 1.6) / globalScale
            ctx.stroke()
          }

          if (!shouldDrawLabel(graphNode, globalScale)) return
          const label = labelText(graphNode)
          const fontSize = isFocus || isActive ? 10.5 : density === 'expanded' ? 7.4 : 8.4
          const labelY = y + radius + fontSize * 0.8
          ctx.font = `${isFocus || isActive ? 650 : 560} ${fontSize}px Geist Variable, sans-serif`
          const textWidth = ctx.measureText(label).width
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillStyle = isFocus || isActive ? 'rgba(255,255,255,0.94)' : 'rgba(248,250,249,0.78)'
          ctx.fillRect(x - textWidth / 2 - 3, labelY - fontSize / 2 - 2, textWidth + 6, fontSize + 4)
          ctx.fillStyle = isFocus || isActive ? '#17231f' : '#53625c'
          ctx.fillText(label, x, labelY)
        }}
        linkLabel={(link: object) => {
          const graphLink = link as FGEdge
          return RELATION_NAMES[graphLink.label] || graphLink.label
        }}
        linkColor={(link: object) => {
          const graphLink = link as FGEdge
          if (!activeNodeId) return density === 'expanded' ? 'rgba(100,116,139,0.24)' : 'rgba(100,116,139,0.36)'
          return activeNeighborhood.edgeIds.has(getEdgeKey(graphLink)) ? 'rgba(39,98,85,0.82)' : 'rgba(148,163,184,0.1)'
        }}
        linkWidth={(link: object) => {
          const graphLink = link as FGEdge
          if (activeNodeId) return activeNeighborhood.edgeIds.has(getEdgeKey(graphLink)) ? 2.2 : 0.5
          return density === 'expanded' ? 0.75 : 1.05
        }}
        linkDirectionalArrowLength={density === 'expanded' ? 3.5 : 4.5}
        linkDirectionalArrowRelPos={0.96}
        linkCurvature={0.06}
        d3VelocityDecay={density === 'expanded' ? 0.4 : 0.34}
        onNodeClick={(node: object) => setSelectedNodeId((node as FGNode).id)}
        onNodeHover={(node: object | null) => setHoverNodeId(node ? (node as FGNode).id : null)}
        onBackgroundClick={() => setSelectedNodeId(null)}
        cooldownTicks={density === 'expanded' ? 170 : 120}
        enableZoomInteraction
        enablePanInteraction
      />
    </div>
  )
}
