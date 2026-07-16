import { useMemo, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import GraphPanel from '@/components/GraphPanel'
import GraphRAGChatPanel from '@/components/GraphRAGChatPanel'
import GraphRAGDebugPanel from '@/components/GraphRAGDebugPanel'
import type { GraphData, GraphRAGChatMessage, GraphRAGDebugInfo } from '@/types'
import { Database, Network, PanelRightClose, PanelRightOpen, Stethoscope, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

function App() {
  const [ragDebug, setRagDebug] = useState<GraphRAGDebugInfo | null>(null)
  const [ragGraph, setRagGraph] = useState<GraphData | null>(null)
  const [panelOpen, setPanelOpen] = useState(() => (
    typeof window === 'undefined' ? true : window.matchMedia('(min-width: 1280px)').matches
  ))

  const handleRagResponse = (msg: GraphRAGChatMessage) => {
    if (msg.debug) setRagDebug(msg.debug)
    if (msg.graph_data) setRagGraph(msg.graph_data)
  }

  const handleSessionReset = () => {
    setRagDebug(null)
    setRagGraph(null)
  }

  const nodeCount = ragGraph?.nodes.length ?? 0
  const edgeCount = ragGraph?.edges.length ?? 0
  const focusNodeIds = useMemo(
    () => Object.values(ragDebug?.entities_normalized || {}).flat(),
    [ragDebug],
  )

  return (
    <div className="h-dvh overflow-hidden bg-[#e9eeeb] text-[#17201d]">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-white px-3 py-2 text-sm font-medium text-slate-900 focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        跳到主要内容
      </a>

      <div className="mx-auto flex h-full max-w-[1800px] flex-col bg-[#f8faf9] shadow-[0_0_0_1px_rgba(26,57,48,0.07)]">
        <header className="relative z-40 shrink-0 border-b border-[#d9e2de] bg-[#fbfcfb]/95 px-4 backdrop-blur-md sm:px-6">
          <div className="flex h-[4.5rem] items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[#174f43] text-white shadow-[0_8px_24px_rgba(23,79,67,0.2)]">
                <Stethoscope className="size-[1.15rem]" strokeWidth={1.8} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2.5">
                  <h1 className="truncate text-[0.95rem] font-semibold text-[#17201d] sm:text-base">
                    知脉 <span className="font-medium text-[#65746e]">MedPulse</span>
                  </h1>
                  <span className="hidden rounded-[4px] bg-[#e4eee9] px-2 py-0.5 text-[0.68rem] font-semibold text-[#276255] sm:inline-flex">
                    GraphRAG
                  </span>
                </div>
                <p className="mt-0.5 hidden truncate text-xs text-[#708079] md:block">
                  医疗知识图谱智能问答
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              <div
                className="hidden h-9 items-center divide-x divide-[#dce4e0] border-x border-[#dce4e0] text-xs text-[#65746e] lg:flex"
                aria-label={`${nodeCount} 个节点，${edgeCount} 条关系`}
              >
                <div className="flex min-w-[6.5rem] items-center justify-center gap-2 px-4">
                  <Database className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
                  <span><strong className="font-semibold text-[#1c2925]">{nodeCount}</strong> 节点</span>
                </div>
                <div className="flex min-w-[6.5rem] items-center justify-center gap-2 px-4">
                  <Network className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
                  <span><strong className="font-semibold text-[#1c2925]">{edgeCount}</strong> 关系</span>
                </div>
              </div>
              <Button
                variant="outline"
                size="icon"
                onClick={() => setPanelOpen(open => !open)}
                title={panelOpen ? '收起检查面板' : '展开检查面板'}
                aria-label={panelOpen ? '收起检查面板' : '展开检查面板'}
                aria-expanded={panelOpen}
                className="size-9 rounded-md border-[#d5dfda] bg-white text-[#3f514a] shadow-none transition-colors hover:bg-[#eef4f1] hover:text-[#174f43] active:translate-y-px"
              >
                {panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
              </Button>
            </div>
          </div>
        </header>

        <main
          id="main-content"
          className={`relative grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)] overflow-hidden ${panelOpen ? 'xl:grid-cols-[minmax(0,1fr)_minmax(25rem,29rem)]' : ''}`}
        >
          <section className={`flex h-full min-h-0 min-w-0 overflow-hidden bg-white ${panelOpen ? 'xl:border-r xl:border-[#d9e2de]' : ''}`}>
            <GraphRAGChatPanel onResponse={handleRagResponse} onSessionReset={handleSessionReset} />
          </section>

          {panelOpen && (
            <>
              <button
                type="button"
                className="absolute inset-0 z-20 bg-[#10251f]/20 backdrop-blur-[2px] xl:hidden"
                onClick={() => setPanelOpen(false)}
                aria-label="关闭检查面板"
              />
              <aside className="absolute inset-y-0 right-0 z-30 flex min-h-0 w-[min(92vw,29rem)] bg-[#f7f9f8] shadow-[-18px_0_50px_rgba(23,55,46,0.14)] xl:static xl:h-full xl:w-auto xl:shadow-none">
                <Tabs defaultValue="debug" className="flex h-full w-full flex-col gap-0">
                  <div className="flex min-h-[4.3rem] items-center justify-between gap-3 border-b border-[#d9e2de] bg-[#fbfcfb] px-4">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[#1b2824]">检查面板</p>
                      <p className="mt-0.5 truncate text-xs text-[#78867f]">检索链路与图谱上下文</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <TabsList className="h-8 shrink-0 rounded-md bg-[#e9efec] p-0.5">
                        <TabsTrigger value="debug" className="h-7 gap-1.5 rounded-[4px] px-2.5 text-xs data-[state=active]:bg-white data-[state=active]:text-[#174f43] data-[state=active]:shadow-sm">
                          <Database className="size-3.5" strokeWidth={1.8} />
                          调试
                        </TabsTrigger>
                        <TabsTrigger value="graph" className="h-7 gap-1.5 rounded-[4px] px-2.5 text-xs data-[state=active]:bg-white data-[state=active]:text-[#174f43] data-[state=active]:shadow-sm">
                          <Network className="size-3.5" strokeWidth={1.8} />
                          图谱
                        </TabsTrigger>
                      </TabsList>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setPanelOpen(false)}
                        className="size-8 rounded-md xl:hidden"
                        aria-label="关闭检查面板"
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  </div>
                  <TabsContent value="debug" className="m-0 min-h-0 flex-1 overflow-hidden">
                    <GraphRAGDebugPanel debug={ragDebug} />
                  </TabsContent>
                  <TabsContent value="graph" className="m-0 min-h-0 flex-1 overflow-hidden" keepMounted>
                    <GraphPanel graphData={ragGraph} focusNodeIds={focusNodeIds} />
                  </TabsContent>
                </Tabs>
              </aside>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

export default App
