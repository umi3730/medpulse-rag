import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { sendGraphRAGChat } from '@/api/client'
import type { GraphRAGChatMessage } from '@/types'
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

  const handleSend = async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg: GraphRAGChatMessage = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await sendGraphRAGChat(q)
      const botMsg: GraphRAGChatMessage = {
        role: 'assistant',
        content: res.answer,
        debug: res.debug,
        graph_data: res.graph_data,
        mode: res.mode,
      }
      setMessages(prev => [...prev, botMsg])
      onResponse(botMsg)
    } catch (e) {
      const errMsg: GraphRAGChatMessage = {
        role: 'assistant',
        content: `请求失败: ${e instanceof Error ? e.message : '未知错误'}`,
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }

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

      <ScrollArea className="flex-1 p-4">
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
