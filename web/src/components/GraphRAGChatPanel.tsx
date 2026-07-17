import { Suspense, lazy, useState, useRef, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { fetchChatSession, fetchChatSessions, streamGraphRAGChat } from '@/api/client'
import type { ChatSessionSummary } from '@/api/client'
import { activateChatSession, getChatIdentity, startNewChatSession } from '@/lib/chatIdentity'
import type { EvidenceItem, GraphRAGChatMessage, GraphRAGDebugInfo, GraphData } from '@/types'
import EvidenceList from '@/components/EvidenceList'
import { ArrowDown, ArrowUp, BrainCircuit, ChevronRight, GitBranch, History, Loader2, MessageSquarePlus, Network, Route, X } from 'lucide-react'

const MarkdownAnswer = lazy(() => import('@/components/MarkdownAnswer'))

interface Props {
  onResponse: (msg: GraphRAGChatMessage) => void
  onSessionReset?: () => void
}

const SUGGESTIONS = [
  { label: '共病关系', question: '糖尿病和高血压有什么共同并发症？' },
  { label: '症状推理', question: '头痛、恶心和发热可能关联哪些疾病？' },
  { label: '用药饮食', question: '糖尿病患者用药和饮食有哪些注意点？' },
]

function formatSessionDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function GraphRAGChatPanel({ onResponse, onSessionReset }: Props) {
  const [messages, setMessages] = useState<GraphRAGChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showScrollToBottom, setShowScrollToBottom] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [activeSessionId, setActiveSessionId] = useState(() => getChatIdentity().session_id)
  const loadingRef = useRef(false)
  const scrollViewportRef = useRef<HTMLDivElement>(null)
  const followOutputRef = useRef(true)

  useEffect(() => {
    const sessionId = getChatIdentity().session_id
    let cancelled = false

    fetchChatSession(sessionId)
      .then(turns => {
        if (cancelled || getChatIdentity().session_id !== sessionId || turns.length === 0) return
        setMessages(turns.flatMap(turn => [
          { role: 'user' as const, content: turn.question },
          { role: 'assistant' as const, content: turn.answer },
        ]))
      })
      .catch(() => {
        // History is an enhancement; a temporarily unavailable backend should not block a new chat.
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!followOutputRef.current) return
    const viewport = scrollViewportRef.current
    if (!viewport) return

    const frame = requestAnimationFrame(() => {
      viewport.scrollTop = viewport.scrollHeight
    })
    return () => cancelAnimationFrame(frame)
  }, [messages])

  const handleConversationScroll = () => {
    const viewport = scrollViewportRef.current
    if (!viewport) return
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
    const isNearBottom = distanceFromBottom < 72
    followOutputRef.current = isNearBottom
    setShowScrollToBottom(!isNearBottom)
  }

  const scrollToConversationBottom = () => {
    const viewport = scrollViewportRef.current
    if (!viewport) return
    followOutputRef.current = true
    setShowScrollToBottom(false)
    viewport.scrollTo({ top: viewport.scrollHeight, behavior: 'smooth' })
  }

  const loadSessions = useCallback(async () => {
    setHistoryLoading(true)
    setHistoryError('')
    try {
      setSessions(await fetchChatSessions())
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : '历史会话加载失败')
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  const handleToggleHistory = () => {
    const nextOpen = !historyOpen
    setHistoryOpen(nextOpen)
    if (nextOpen) void loadSessions()
  }

  const handleOpenSession = async (sessionId: string) => {
    if (loadingRef.current) return
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const turns = await fetchChatSession(sessionId)
      activateChatSession(sessionId)
      setActiveSessionId(sessionId)
      setMessages(turns.flatMap(turn => [
        { role: 'user' as const, content: turn.question },
        { role: 'assistant' as const, content: turn.answer },
      ]))
      setInput('')
      followOutputRef.current = true
      setShowScrollToBottom(false)
      setHistoryOpen(false)
      onSessionReset?.()
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : '历史会话读取失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  const handleNewSession = () => {
    if (loadingRef.current) return
    const identity = startNewChatSession()
    setActiveSessionId(identity.session_id)
    followOutputRef.current = true
    setShowScrollToBottom(false)
    setMessages([])
    setInput('')
    setHistoryOpen(false)
    if (scrollViewportRef.current) scrollViewportRef.current.scrollTop = 0
    onSessionReset?.()
  }

  const handleSend = useCallback(async (question?: string) => {
    const q = (question ?? input).trim()
    if (!q || loadingRef.current) return

    const userMsg: GraphRAGChatMessage = { role: 'user', content: q }
    loadingRef.current = true
    followOutputRef.current = true
    setShowScrollToBottom(false)
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    const botIdx = { current: -1 }
    setMessages(prev => {
      botIdx.current = prev.length
      return [...prev, { role: 'assistant', content: '' }]
    })

    let debugInfo: GraphRAGDebugInfo | undefined
    let graphData: GraphData | undefined
    let evidence: EvidenceItem[] | undefined
    let mode: string | undefined

    try {
      await streamGraphRAGChat(q, {
        onRetrieval(data) {
          debugInfo = data.debug as GraphRAGDebugInfo
          graphData = data.graph_data
          evidence = data.evidence
          mode = data.mode
          setMessages(prev => {
            const updated = [...prev]
            const msg = updated[botIdx.current]
            if (msg) updated[botIdx.current] = { ...msg, mode, debug: debugInfo, graph_data: graphData, evidence }
            return updated
          })
          onResponse({ role: 'assistant', content: '', debug: debugInfo, graph_data: graphData, evidence, mode })
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
                evidence,
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
      loadingRef.current = false
      setLoading(false)
    }
  }, [input, onResponse])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="relative flex h-full min-h-0 w-full flex-col bg-white">
      <div className="relative z-40 flex min-h-[4.3rem] shrink-0 items-center justify-between gap-4 border-b border-[#e0e7e3] bg-[#fbfcfb] px-5 sm:px-7">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#18231f]">
            <BrainCircuit className="size-4 text-[#397b6b]" strokeWidth={1.8} />
            知脉助手
          </div>
          <p className="mt-0.5 hidden truncate text-xs text-[#7a8781] sm:block">
            当前会话 · 子图检索与生成
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 text-[0.7rem] font-medium text-[#66756f] md:flex">
            <Route className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
            <span>实体提取</span>
            <ChevronRight className="size-3 text-[#acb8b3]" />
            <span>子图召回</span>
            <ChevronRight className="size-3 text-[#acb8b3]" />
            <span>回答生成</span>
          </div>
          <button
            type="button"
            onClick={handleToggleHistory}
            className={`flex size-8 shrink-0 items-center justify-center rounded-md border transition-colors ${
              historyOpen
                ? 'border-[#98b5ab] bg-[#e8f1ed] text-[#174f43]'
                : 'border-[#d5dfda] bg-white text-[#607069] hover:bg-[#eef4f1] hover:text-[#174f43]'
            }`}
            title="历史会话"
            aria-label="历史会话"
            aria-expanded={historyOpen}
          >
            <History className="size-3.5" strokeWidth={1.8} />
          </button>
          <button
            type="button"
            onClick={handleNewSession}
            disabled={loading}
            className="flex size-8 shrink-0 items-center justify-center rounded-md border border-[#d5dfda] bg-white text-[#607069] transition-colors hover:bg-[#eef4f1] hover:text-[#174f43] disabled:cursor-not-allowed disabled:opacity-45"
            title="新建会话"
            aria-label="新建会话"
          >
            <MessageSquarePlus className="size-3.5" strokeWidth={1.8} />
          </button>
        </div>
      </div>

      {historyOpen && (
        <>
          <button
            type="button"
            className="absolute inset-x-0 bottom-0 top-[4.3rem] z-20 cursor-default bg-[#12211b]/10 backdrop-blur-[1px]"
            onClick={() => setHistoryOpen(false)}
            aria-label="关闭历史会话"
          />
          <aside className="absolute bottom-0 left-0 top-[4.3rem] z-30 flex w-full flex-col border-r border-[#d9e3df] bg-[#fbfcfb] shadow-[16px_0_40px_rgba(31,65,55,0.12)] sm:w-[21rem]">
            <div className="flex min-h-16 shrink-0 items-center justify-between border-b border-[#dfe7e3] px-5">
              <div>
                <h2 className="text-sm font-semibold text-[#18231f]">历史会话</h2>
                <p className="mt-0.5 text-[0.68rem] text-[#84918b]">
                  {historyLoading ? '正在同步…' : `${sessions.length} 个会话`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setHistoryOpen(false)}
                className="flex size-8 items-center justify-center rounded-md text-[#687770] transition-colors hover:bg-[#eaf1ee] hover:text-[#174f43]"
                title="关闭"
                aria-label="关闭历史会话"
              >
                <X className="size-4" strokeWidth={1.8} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              {historyLoading && sessions.length === 0 && (
                <div className="space-y-2 px-2 py-1" aria-live="polite">
                  {[0, 1, 2].map(item => (
                    <div key={item} className="border-b border-[#e4eae7] px-2 py-4">
                      <div className="h-3 w-3/4 animate-pulse rounded-sm bg-[#e3eae7]" />
                      <div className="mt-3 h-2 w-2/5 animate-pulse rounded-sm bg-[#edf1ef]" />
                    </div>
                  ))}
                </div>
              )}

              {historyError && (
                <div className="mx-2 border-l-2 border-rose-400 bg-rose-50 px-3 py-2.5 text-xs leading-5 text-rose-800">
                  {historyError}
                </div>
              )}

              {!historyLoading && !historyError && sessions.length === 0 && (
                <div className="px-5 py-12 text-center">
                  <History className="mx-auto size-5 text-[#9caaa4]" strokeWidth={1.6} />
                  <p className="mt-3 text-xs font-medium text-[#53635d]">还没有历史会话</p>
                  <p className="mt-1 text-[0.68rem] leading-5 text-[#8a9791]">完成一次问答后会自动保存在这里</p>
                </div>
              )}

              {sessions.length > 0 && (
                <div className="divide-y divide-[#e3eae6]">
                  {sessions.map(session => {
                    const isActive = session.session_id === activeSessionId
                    return (
                      <button
                        key={session.session_id}
                        type="button"
                        onClick={() => void handleOpenSession(session.session_id)}
                        disabled={historyLoading}
                        className={`group w-full px-3 py-3.5 text-left transition-colors disabled:cursor-wait disabled:opacity-60 ${
                          isActive ? 'bg-[#eaf2ee]' : 'hover:bg-[#f0f5f2]'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <span className={`mt-1 block size-1.5 shrink-0 rounded-full ${isActive ? 'bg-[#2f7665]' : 'bg-[#bdc9c4]'}`} />
                          <span className="min-w-0 flex-1">
                            <span className={`block truncate text-xs font-medium ${isActive ? 'text-[#174f43]' : 'text-[#2e3d37]'}`}>
                              {session.title || '未命名会话'}
                            </span>
                            <span className="mt-2 flex items-center justify-between gap-3 text-[0.65rem] text-[#8b9892]">
                              <span>{formatSessionDate(session.updated_at)}</span>
                              <span className="shrink-0">{session.turn_count} 轮</span>
                            </span>
                          </span>
                          <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-[#a1ada8] transition-transform group-hover:translate-x-0.5 group-hover:text-[#397b6b]" />
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </aside>
        </>
      )}

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollViewportRef}
          onScroll={handleConversationScroll}
          className="h-full overflow-y-auto overscroll-contain"
        >
          <div className="mx-auto flex min-h-full w-full max-w-[57rem] flex-col px-5 py-6 sm:px-8 sm:py-8">
          {messages.length === 0 && (
            <div className="flex flex-1 items-center py-8 sm:py-12">
              <div className="w-full max-w-[46rem] animate-[workspace-enter_420ms_ease-out_both]">
                <div className="mb-6 flex size-11 items-center justify-center rounded-lg bg-[#e7f0ec] text-[#276255]">
                  <Network className="size-5" strokeWidth={1.7} />
                </div>
                <p className="text-xs font-semibold text-[#397b6b]">新查询</p>
                <h2 className="mt-2 max-w-[24ch] text-2xl font-semibold leading-[1.22] text-[#17201d] text-balance sm:text-[2rem]">
                  从一个具体的医学关系问题开始
                </h2>

                <div className="mt-8 border-y border-[#dce5e1]">
                  {SUGGESTIONS.map((item, index) => (
                    <button
                      key={item.question}
                      type="button"
                      onClick={() => handleSend(item.question)}
                      className="group grid w-full grid-cols-[2.25rem_minmax(0,1fr)_1.5rem] items-center gap-3 border-b border-[#e4eae7] py-4 text-left transition-colors last:border-b-0 hover:bg-[#f3f7f5] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#5d9487] active:bg-[#ebf2ef]"
                    >
                      <span className="font-mono text-xs text-[#96a39e]">0{index + 1}</span>
                      <span className="min-w-0">
                        <span className="block text-[0.68rem] font-semibold text-[#397b6b]">{item.label}</span>
                        <span className="mt-1 block text-sm leading-5 text-[#34443e]">{item.question}</span>
                      </span>
                      <ChevronRight className="size-4 text-[#9eaaa5] transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-[#276255]" />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.length > 0 && (
            <div className="flex flex-col gap-8 pb-3">
              {messages.map((msg, i) => {
                if (!msg.content) return null
                const isUser = msg.role === 'user'
                const isError = !isUser && msg.content.startsWith('请求失败：')

                return (
                  <article
                    key={i}
                    className={`flex animate-[workspace-enter_320ms_ease-out_both] ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {isUser ? (
                      <div className="max-w-[82%] sm:max-w-[72%]">
                        <p className="mb-1.5 text-right text-[0.68rem] font-medium text-[#89968f]">你</p>
                        <div className="rounded-[8px_8px_2px_8px] bg-[#174f43] px-4 py-3 text-sm leading-6 text-white shadow-[0_8px_24px_rgba(23,79,67,0.15)]">
                          {msg.content}
                        </div>
                      </div>
                    ) : (
                      <div className={`w-full max-w-[52rem] border-l-2 pl-4 sm:pl-5 ${isError ? 'border-rose-400' : 'border-[#5d9487]'}`}>
                        <div className="mb-2 flex items-center gap-2">
                          <span className="text-[0.7rem] font-semibold text-[#33443e]">GraphRAG</span>
                          {msg.mode && (
                            <span className={`rounded-[3px] px-1.5 py-0.5 text-[0.65rem] font-medium ${
                              msg.mode === 'graphrag'
                                ? 'bg-[#e7f0ec] text-[#276255]'
                                : 'bg-amber-50 text-amber-800'
                            }`}>
                              {msg.mode === 'graphrag' ? '图谱增强' : '后端兜底'}
                            </span>
                          )}
                        </div>
                        <Suspense
                          fallback={(
                            <p className={`max-w-[65ch] whitespace-pre-wrap text-[0.94rem] leading-7 text-pretty ${isError ? 'text-rose-800' : 'text-[#2f3d38]'}`}>
                              {msg.content}
                            </p>
                          )}
                        >
                          <MarkdownAnswer content={msg.content} isError={isError} />
                        </Suspense>
                        <EvidenceList evidence={msg.evidence} />
                      </div>
                    )}
                  </article>
                )
              })}

              {loading && (
                <div className="flex justify-start" aria-live="polite">
                  <div className="w-full max-w-[34rem] border-l-2 border-[#b7cbc3] pl-4 sm:pl-5">
                    <div className="flex items-center gap-2 text-xs font-medium text-[#52635c]">
                      <Loader2 className="size-3.5 animate-spin text-[#397b6b]" />
                      正在检索子图并生成回答
                    </div>
                    <div className="mt-3 space-y-2">
                      <div className="h-2 w-[86%] animate-pulse rounded-sm bg-[#e6ece9]" />
                      <div className="h-2 w-[64%] animate-pulse rounded-sm bg-[#edf1ef]" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          </div>
        </div>

        {showScrollToBottom && (
          <button
            type="button"
            onClick={scrollToConversationBottom}
            className="absolute bottom-4 right-5 flex size-9 items-center justify-center rounded-md border border-[#cad8d2] bg-white text-[#52635c] shadow-[0_8px_24px_rgba(31,65,55,0.14)] transition-all hover:border-[#91afa5] hover:text-[#276255] active:translate-y-px sm:right-7"
            title="回到最新回复"
            aria-label="回到最新回复"
          >
            <ArrowDown className="size-4" />
          </button>
        )}
      </div>

      <div className="shrink-0 border-t border-[#dce5e1] bg-[#fbfcfb] px-4 pb-3 pt-3 sm:px-7 sm:pb-4">
        <div className="mx-auto max-w-[57rem]">
          <div className="flex items-end gap-2 rounded-lg border border-[#cedbd5] bg-white p-1.5 shadow-[0_10px_30px_rgba(31,65,55,0.07)] transition-shadow focus-within:border-[#6d9d91] focus-within:shadow-[0_10px_30px_rgba(31,65,55,0.11),0_0_0_3px_rgba(71,128,113,0.09)]">
            <label htmlFor="graphrag-question" className="sr-only">输入医学问题</label>
            <textarea
              id="graphrag-question"
              value={input}
              onChange={event => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入医学关系问题…"
              disabled={loading}
              rows={1}
              className="max-h-28 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-5 text-[#26342f] outline-none placeholder:text-[#9aa6a1] disabled:cursor-not-allowed disabled:opacity-60"
            />
            <Button
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              size="icon"
              aria-label="发送问题"
              className="size-10 shrink-0 rounded-md bg-[#174f43] text-white shadow-none transition-all hover:bg-[#276255] active:translate-y-px disabled:bg-[#b8c6c0]"
            >
              {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" strokeWidth={2} />}
            </Button>
          </div>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-[0.65rem] text-[#89958f]">
            <GitBranch className="size-3" strokeWidth={1.7} />
            回答用于知识检索参考，不能替代专业诊断
          </p>
        </div>
      </div>
    </div>
  )
}
