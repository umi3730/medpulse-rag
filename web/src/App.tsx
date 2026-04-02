import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import ChatPanel from '@/components/ChatPanel'
import DebugPanel from '@/components/DebugPanel'
import GraphPanel from '@/components/GraphPanel'
import type { ChatMessage, DebugInfo, GraphData } from '@/types'
import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'

function App() {
  const [debug, setDebug] = useState<DebugInfo | null>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [panelOpen, setPanelOpen] = useState(true)

  const handleResponse = (msg: ChatMessage) => {
    if (msg.debug) setDebug(msg.debug)
    if (msg.graph_data) setGraphData(msg.graph_data)
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="h-12 border-b flex items-center justify-between px-4 shrink-0 bg-white">
        <span className="font-semibold">🏥 医药知识图谱智能问答系统</span>
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
          <ChatPanel onResponse={handleResponse} />
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
                <DebugPanel debug={debug} />
              </TabsContent>
              <TabsContent value="graph" className="flex-1 overflow-hidden m-0">
                <GraphPanel graphData={graphData} />
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
