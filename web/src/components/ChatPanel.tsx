import { useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { streamChat } from '@/api/client'
import type { ChatMessage, DebugInfo, GraphData } from '@/types'
import { Loader2, MessageCircle, Search, Send, ShieldCheck, Sparkles } from 'lucide-react'

interface Props {
  onResponse: (msg: ChatMessage) => void
}

const SUGGESTIONS = [
  '糖尿病有什么常见症状？',
  '头痛可能和哪些疾病有关？',
  '高血压患者不适合吃什么？',
]

export default function ChatPanel({ onResponse }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async (question?: string) => {
    const q = (question ?? input).trim()
    if (!q || loading) return

    const userMsg: ChatMessage = { role: 'user', content: q }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

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
              content: `请求失败：${err.message}`,
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
          content: `请求失败：${e instanceof Error ? e.message : '未知错误'}`,
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
    <div className="flex h-full flex-col bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.10),transparent_32%),#ffffff]">
      <div className="border-b border-slate-200/80 px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <MessageCircle className="size-4 text-emerald-700" />
              基础知识图谱问答
            </div>
            <p className="mt-1 text-xs text-slate-500">
              适合单疾病、单症状、药品和检查类的结构化问答
            </p>
          </div>
          <div className="hidden items-center gap-1.5 rounded-lg border border-emerald-800/15 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 md:flex">
            <ShieldCheck className="size-3.5" />
            图谱检索
          </div>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1 p-5">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex min-h-[52vh] flex-col justify-center py-10">
              <div className="max-w-2xl">
                <div className="mb-4 inline-flex items-center gap-2 rounded-lg border border-emerald-800/15 bg-white px-3 py-1.5 text-xs font-medium text-emerald-800 shadow-sm">
                  <Sparkles className="size-3.5" />
                  医疗实体识别 + Cypher 查询
                </div>
                <h2 className="text-3xl font-semibold leading-tight text-slate-950 text-balance">
                  从一个症状或疾病开始，快速定位图谱里的医学关系。
                </h2>
                <p className="mt-3 max-w-xl text-sm leading-6 text-slate-600">
                  系统会识别问题里的医学实体，生成图谱查询，并把答案、检索过程和相关子图放到右侧检查面板里。
                </p>
                <div className="mt-6 grid gap-2 sm:grid-cols-3">
                  {SUGGESTIONS.map(item => (
                    <button
                      key={item}
                      type="button"
                      onClick={() => handleSend(item)}
                      className="rounded-xl border border-slate-200 bg-white p-3 text-left text-sm text-slate-700 shadow-sm transition-all hover:-translate-y-0.5 hover:border-emerald-700/30 hover:shadow-md active:translate-y-0"
                    >
                      <Search className="mb-2 size-4 text-emerald-700" />
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <Card className={`max-w-[82%] rounded-2xl px-4 py-3 shadow-sm ${
                msg.role === 'user'
                  ? 'border-emerald-800/20 bg-emerald-900 text-white ring-0'
                  : 'border-slate-200 bg-white text-slate-800 ring-slate-200'
              }`}>
                <p className="whitespace-pre-wrap text-sm leading-7">{msg.content}</p>
              </Card>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <Card className="w-72 rounded-2xl border-slate-200 bg-white px-4 py-3 shadow-sm ring-slate-200">
                <div className="flex items-center gap-3 text-sm text-slate-600">
                  <Loader2 className="size-4 animate-spin text-emerald-700" />
                  正在检索图谱并组织回答
                </div>
                <div className="mt-3 space-y-2">
                  <div className="h-2 rounded-full bg-slate-100" />
                  <div className="h-2 w-2/3 rounded-full bg-slate-100" />
                </div>
              </Card>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="border-t border-slate-200/80 bg-white/90 p-4">
        <div className="mx-auto flex max-w-4xl gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_12px_35px_rgba(15,63,55,0.08)]">
          <Input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入医疗问题，例如：糖尿病有什么症状？"
            disabled={loading}
            className="h-10 flex-1 border-0 bg-transparent px-3 shadow-none focus-visible:ring-0"
          />
          <Button onClick={() => handleSend()} disabled={loading || !input.trim()} size="icon" className="size-10 bg-emerald-900 hover:bg-emerald-800">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
