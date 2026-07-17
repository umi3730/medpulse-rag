import type { ChatResponse, EvidenceItem, GraphData, GraphRAGChatResponse } from '@/types'
import { getChatIdentity } from '@/lib/chatIdentity'

const BASE = '/api'

export interface ChatSessionSummary {
  session_id: string
  title: string
  last_question: string
  turn_count: number
  created_at: string
  updated_at: string
}

export interface ChatSessionTurn {
  question: string
  answer: string
  intents: string[]
  entities: Record<string, string[]>
  created_at: string
}

export async function sendChat(question: string): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...getChatIdentity() }),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

export async function sendGraphRAGChat(question: string): Promise<GraphRAGChatResponse> {
  const res = await fetch(`${BASE}/graphrag/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...getChatIdentity() }),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

export async function fetchNeighbors(name: string, limit = 50): Promise<{ center: string; graph_data: GraphData }> {
  const res = await fetch(`${BASE}/graph/neighbors/${encodeURIComponent(name)}?limit=${limit}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

export async function fetchChatSessions(limit = 30): Promise<ChatSessionSummary[]> {
  const { user_id } = getChatIdentity()
  const params = new URLSearchParams({ user_id, limit: String(limit) })
  const res = await fetch(`${BASE}/graphrag/sessions?${params}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const data = await res.json() as { sessions: ChatSessionSummary[] }
  return data.sessions
}

export async function fetchChatSession(sessionId: string): Promise<ChatSessionTurn[]> {
  const { user_id } = getChatIdentity()
  const params = new URLSearchParams({ user_id })
  const res = await fetch(`${BASE}/graphrag/sessions/${encodeURIComponent(sessionId)}?${params}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  const data = await res.json() as { turns: ChatSessionTurn[] }
  return data.turns
}

// ---------------------------------------------------------------------------
// SSE 流式接口
// ---------------------------------------------------------------------------
export interface SSECallbacks {
  onRetrieval?: (data: { debug: unknown; graph_data: GraphData; evidence?: EvidenceItem[]; mode?: string }) => void
  onDelta?: (chunk: string) => void
  onDone?: (data: { answer: string; total_time_ms: number }) => void
  onError?: (err: Error) => void
}

async function consumeSSE(url: string, question: string, cb: SSECallbacks) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...getChatIdentity() }),
  })
  if (!res.ok) {
    cb.onError?.(new Error(`请求失败: ${res.status}`))
    return
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    // 按双换行切分 SSE 事件
    const parts = buf.split('\n\n')
    buf = parts.pop()!
    for (const part of parts) {
      let event = ''
      let data = ''
      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data = line.slice(6)
      }
      if (!event || !data) continue
      try {
        const parsed = JSON.parse(data)
        if (event === 'retrieval') cb.onRetrieval?.(parsed)
        else if (event === 'delta') cb.onDelta?.(parsed.chunk)
        else if (event === 'done') cb.onDone?.(parsed)
      } catch { /* ignore parse errors */ }
    }
  }
}

export function streamChat(question: string, cb: SSECallbacks) {
  return consumeSSE(`${BASE}/chat/stream`, question, cb)
}

export function streamGraphRAGChat(question: string, cb: SSECallbacks) {
  return consumeSSE(`${BASE}/graphrag/chat/stream`, question, cb)
}
