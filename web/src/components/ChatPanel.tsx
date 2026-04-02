import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { streamChat } from '@/api/client'
import type { ChatMessage, DebugInfo, GraphData } from '@/types'
import { Send, Loader2 } from 'lucide-react'

interface Props {
  onResponse: (msg: ChatMessage) => void
}

export default function ChatPanel({ onResponse }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg: ChatMessage = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // 先插入空的 assistant 消息，后续流式追加
    const botIdx = { current: -1 }
    setMessages(prev => {
      botIdx.current = prev.length
      return [...prev, { role: 'assistant', content: '' }]
    })

    let debugInfo: DebugInfo | undefined
    let graphData: GraphData | undefined

    try {
      await streamChat(q, {
        onRetrieval(data) {
          debugInfo = data.debug as DebugInfo
          graphData = data.graph_data
          // 立即推送 debug + graph_data
          onResponse({ role: 'assistant', content: '', debug: debugInfo, graph_data: graphData })
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
      <div className="px-4 py-3 border-b font-semibold text-lg">
        医药知识图谱问答
      </div>

      <ScrollArea className="flex-1 min-h-0 p-4">
        <div className="space-y-3">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground py-20">
              <p className="text-xl mb-2">🏥 医药知识图谱智能问答</p>
              <p className="text-sm">支持疾病、症状、药品、食物等 18 类问题</p>
              <p className="text-sm mt-1 text-muted-foreground/60">
                试试：糖尿病有什么症状？/ 头痛可能是什么病？
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
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{msg.content}</p>
              </Card>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <Card className="bg-secondary px-4 py-2.5">
                <Loader2 className="h-4 w-4 animate-spin" />
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
          placeholder="输入医疗问题，如：糖尿病有什么症状？"
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
