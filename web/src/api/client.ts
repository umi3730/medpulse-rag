import type { ChatResponse, GraphData } from '@/types'

const BASE = '/api'

export async function sendChat(question: string): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

export async function fetchNeighbors(name: string, limit = 50): Promise<{ center: string; graph_data: GraphData }> {
  const res = await fetch(`${BASE}/graph/neighbors/${encodeURIComponent(name)}?limit=${limit}`)
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}
