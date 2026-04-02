import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { streamGraphRAGChat } from '@/api/client'
import type { GraphRAGChatMessage, GraphRAGDebugInfo, GraphData } from '@/types'
import { Send, Loader2 } from 'lucide-react'

interface Props {
  onResponse: (msg: GraphRAGChatMessage) => void
}

export default function GraphRAGChatPanel({ onResponse }: Props) {
  const [messages, setMessages] = useState<GraphRAGChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg: GraphRAGChatMessage = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // 先插入空的 assistant 消息
    const botIdx = { current: -1 }
    setMessages(prev => {
      botIdx.current = prev.length
      return [...prev, { role: 'assistant', content: '' }]
    })

    let debugInfo: GraphRAGDebugInfo | undefined
    let graphData: GraphData | undefined
    let mode: string | undefined

    try {
      await streamGraphRAGChat(q, {
        onRetrieval(data) {
          debugInfo = data.debug as GraphRAGDebugInfo
          graphData = data.graph_data
          mode = data.mode
          // 立即更新 mode 标签 + 推送 debug/graph
          setMessages(prev => {
            const updated = [...prev]
            const msg = updated[botIdx.current]
            if (msg) updated[botIdx.current] = { ...msg, mode, debug: debugInfo, graph_data: graphData }
            return updated
          })
          onResponse({ role: 'assistant', content: '', debug: debugInfo, graph_data: graphData, mode })
        },
        onDelta(chunk) {
          setMessages(prev => {
            const updated = [...prev]
            const msg = updated[botIdx.current]
            if (msg) updated[botIdx.current] = { ...msg, content: msg.content + chunk }
            return updated
          })
        },
        onDone(data) {
          setMessages(prev => {
            const updated = [...prev]
            const msg = updated[botIdx.current]
            if (msg) {
              updated[botIdx.current] = {
                ...msg,
                content: data.answer || msg.content,
                debug: debugInfo,
                graph_data: graphData,
                mode,
              }
            }
            return updated
          })
        },
        onError(err) {
          setMessages(prev => {
            const updated = [...prev]
            updated[botIdx.current] = {
              role: 'assistant',
              content: `请求失败: ${err.message}`,
            }
            return updated
          })
        },
      })
    } catch (e) {
      setMessages(prev => {
        const updated = [...prev]
        updated[botIdx.current] = {
          role: 'assistant',
          content: `请求失败: ${e instanceof Error ? e.message : '未知错误'}`,
        }
        return updated
      })
    } finally {
      setLoading(false)
    }
  }, [input, loading, onResponse])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b font-semibold text-lg flex items-center gap-2">
        GraphRAG 问答
        <Badge variant="outline" className="text-xs font-normal">子图检索 + LLM 生成</Badge>
      </div>

      <ScrollArea className="flex-1 min-h-0 p-4">
        <div className="space-y-3">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground py-20">
              <p className="text-xl mb-2">🧠 GraphRAG 智能问答</p>
              <p className="text-sm">基于知识图谱子图检索 + LLM 生成，支持复杂多实体问题</p>
              <p className="text-sm mt-1 text-muted-foreground/60">
                试试：糖尿病和高血压有什么共同的并发症和用药？
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <Card className={`max-w-[80%] px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary'
              }`}>
                {msg.role === 'assistant' && msg.mode && (
                  <div className="mb-1">
                    <Badge
                      variant="outline"
                      className={`text-xs ${
                        msg.mode === 'graphrag'
                          ? 'bg-blue-50 text-blue-700 border-blue-200'
                          : 'bg-yellow-50 text-yellow-700 border-yellow-200'
                      }`}
                    >
                      {msg.mode === 'graphrag' ? 'GraphRAG' : '降级到基础问答'}
                    </Badge>
                  </div>
                )}
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p>
              </Card>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <Card className="bg-secondary px-4 py-2.5 flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-xs text-muted-foreground">检索子图 + 生成回答中...</span>
              </Card>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="p-4 border-t flex gap-2">
        <Input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，如：糖尿病有什么症状？吃什么药？"
          disabled={loading}
          className="flex-1"
        />
        <Button onClick={handleSend} disabled={loading || !input.trim()} size="icon">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  )
}
