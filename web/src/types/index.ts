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
