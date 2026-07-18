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

export interface EvidenceItem {
  id: string
  kind: 'property' | 'relation' | 'claim'
  subject: string
  predicate: string
  object: string
  citation_index: number
  source_name: string
  source_url: string
  updated_at: string
  evidence_level: string
  publisher?: string
  document_title?: string
  section?: string
  locator?: string
  review_status?: string
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
  workflow: string
  intent: string
  intents: string[]
  query_plan: Record<string, unknown>
  requested_fields: string[]
  relation_filters: string[]
  detail_level: 'brief' | 'standard' | 'detailed'
  needs_clarification: boolean
  risk_level: 'low' | 'medium' | 'high'
  retrieval_mode: string
  memory_turn_count: number
  memory_scope: string
  evidence_scope: string
  evidence_count: number
  memory_context_preview: string
  memory_entities: Record<string, string[]>
  vector_hit_count: number
  embedding_provider: string
  embedding_model: string
  embedding_dimension: number
  embedding_fallback_reason: string
  vector_context_preview: string
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
  error?: string
}

export interface GraphRAGChatResponse {
  answer: string
  mode: string
  debug: GraphRAGDebugInfo
  graph_data: GraphData
  evidence: EvidenceItem[]
}

export interface GraphRAGChatMessage {
  role: 'user' | 'assistant'
  content: string
  debug?: GraphRAGDebugInfo
  graph_data?: GraphData
  evidence?: EvidenceItem[]
  mode?: string
}
