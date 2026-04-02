import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import ChatPanel from '@/components/ChatPanel'
import DebugPanel from '@/components/DebugPanel'
import GraphPanel from '@/components/GraphPanel'
import GraphRAGChatPanel from '@/components/GraphRAGChatPanel'
import GraphRAGDebugPanel from '@/components/GraphRAGDebugPanel'
import type { ChatMessage, DebugInfo, GraphData, GraphRAGChatMessage, GraphRAGDebugInfo } from '@/types'
import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'

function App() {
  // 基础问答 state
  const [basicDebug, setBasicDebug] = useState<DebugInfo | null>(null)
  const [basicGraph, setBasicGraph] = useState<GraphData | null>(null)

  // GraphRAG state
  const [ragDebug, setRagDebug] = useState<GraphRAGDebugInfo | null>(null)
  const [ragGraph, setRagGraph] = useState<GraphData | null>(null)

  const [panelOpen, setPanelOpen] = useState(true)
  const [mode, setMode] = useState<'basic' | 'graphrag'>('basic')

  const handleBasicResponse = (msg: ChatMessage) => {
    if (msg.debug) setBasicDebug(msg.debug)
    if (msg.graph_data) setBasicGraph(msg.graph_data)
  }

  const handleRagResponse = (msg: GraphRAGChatMessage) => {
    if (msg.debug) setRagDebug(msg.debug)
    if (msg.graph_data) setRagGraph(msg.graph_data)
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 border-b flex items-center justify-between px-4 shrink-0 bg-white">
        <div className="flex items-center gap-4">
          <span className="font-semibold">🏥 医药知识图谱智能问答系统</span>
          <div className="flex bg-muted rounded-lg p-0.5">
            <button
              className={`px-3 py-1 rounded-md text-sm transition-colors ${
                mode === 'basic'
                  ? 'bg-white shadow-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setMode('basic')}
            >
              基础问答
            </button>
            <button
              className={`px-3 py-1 rounded-md text-sm transition-colors ${
                mode === 'graphrag'
                  ? 'bg-white shadow-sm font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setMode('graphrag')}
            >
              GraphRAG
            </button>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setPanelOpen(p => !p)}
          title={panelOpen ? '收起面板' : '展开面板'}
        >
          {panelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
        </Button>
      </header>

      {/* Main */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧: 聊天 */}
        <div className={`flex-1 min-w-0 ${panelOpen ? 'border-r' : ''}`}>
          {mode === 'basic' ? (
            <ChatPanel onResponse={handleBasicResponse} />
          ) : (
            <GraphRAGChatPanel onResponse={handleRagResponse} />
          )}
        </div>

        {/* 右侧: 调试 + 图谱 */}
        {panelOpen && (
          <div className="w-[480px] shrink-0 flex flex-col">
            <Tabs defaultValue="debug" className="flex flex-col h-full">
              <TabsList className="mx-4 mt-2 shrink-0">
                <TabsTrigger value="debug">调试信息</TabsTrigger>
                <TabsTrigger value="graph">知识图谱</TabsTrigger>
              </TabsList>
              <TabsContent value="debug" className="flex-1 overflow-hidden m-0">
                {mode === 'basic' ? (
                  <DebugPanel debug={basicDebug} />
                ) : (
                  <GraphRAGDebugPanel debug={ragDebug} />
                )}
              </TabsContent>
              <TabsContent value="graph" className="flex-1 overflow-hidden m-0">
                <GraphPanel graphData={mode === 'basic' ? basicGraph : ragGraph} />
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
