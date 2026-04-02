export interface CypherQuery {
  cypher: string
  params: Record<string, unknown>
}

export interface DebugInfo {
  level: number
  intents: string[]
  entities: Record<string, string[]>
  cypher_queries: CypherQuery[]
  result_count: number
}

export interface GraphNode {
  id: string
  label: string
}

export interface GraphEdge {
  source: string
  target: string
  label: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ChatResponse {
  answer: string
  debug: DebugInfo
  graph_data: GraphData
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  debug?: DebugInfo
  graph_data?: GraphData
}

// ---- GraphRAG ----
export interface GraphRAGDebugInfo {
  entities_raw: Array<{ name: string; type: string }>
  entities_normalized: Record<string, string[]>
  subgraph_stats: {
    total_nodes: number
    total_edges: number
    retrieval_time_ms: number
  }
  context_preview: string
  context_char_count: number
  generation_time_ms: number
  model_used: string
  total_time_ms: number
}

export interface GraphRAGChatResponse {
  answer: string
  mode: string
  debug: GraphRAGDebugInfo
  graph_data: GraphData
}

export interface GraphRAGChatMessage {
  role: 'user' | 'assistant'
  content: string
  debug?: GraphRAGDebugInfo
  graph_data?: GraphData
  mode?: string
}
