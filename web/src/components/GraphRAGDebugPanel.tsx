import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { GraphRAGDebugInfo } from '@/types'

interface Props {
  debug: GraphRAGDebugInfo | null
}

const TYPE_COLORS: Record<string, string> = {
  disease: 'bg-red-50 text-red-700 border-red-200',
  drug: 'bg-blue-50 text-blue-700 border-blue-200',
  food: 'bg-green-50 text-green-700 border-green-200',
  check: 'bg-purple-50 text-purple-700 border-purple-200',
  symptom: 'bg-orange-50 text-orange-700 border-orange-200',
  department: 'bg-cyan-50 text-cyan-700 border-cyan-200',
}

const TYPE_LABELS: Record<string, string> = {
  disease: '疾病',
  drug: '药品',
  food: '食物',
  check: '检查',
  symptom: '症状',
  department: '科室',
}

export default function GraphRAGDebugPanel({ debug }: Props) {
  if (!debug) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        发送问题后查看调试信息
      </div>
    )
  }

  const stats = debug.subgraph_stats || {}

  return (
    <ScrollArea className="h-full p-4">
      <div className="space-y-4">
        {/* LLM 原始实体 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">LLM 提取实体</CardTitle>
          </CardHeader>
          <CardContent>
            {debug.entities_raw.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {debug.entities_raw.map((e, i) => (
                  <Badge
                    key={i}
                    variant="outline"
                    className={`text-xs ${TYPE_COLORS[e.type] || ''}`}
                  >
                    {e.name}
                    <span className="ml-1 opacity-60">{TYPE_LABELS[e.type] || e.type}</span>
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无</span>
            )}
          </CardContent>
        </Card>

        {/* 归一化实体 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">归一化实体（图谱匹配）</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(debug.entities_normalized).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(debug.entities_normalized).map(([type, names]) => (
                  <div key={type}>
                    <span className="text-xs text-muted-foreground">
                      {TYPE_LABELS[type] || type}:
                    </span>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {names.map(n => (
                        <Badge key={n} variant="secondary" className="text-xs">{n}</Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无匹配</span>
            )}
          </CardContent>
        </Card>

        {/* 子图统计 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">子图检索统计</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-2xl font-bold text-blue-600">
                  {stats.total_nodes ?? 0}
                </div>
                <div className="text-xs text-muted-foreground">节点数</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-green-600">
                  {stats.total_edges ?? 0}
                </div>
                <div className="text-xs text-muted-foreground">边数</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-orange-600">
                  {stats.retrieval_time_ms != null
                    ? `${Math.round(stats.retrieval_time_ms)}`
                    : '—'}
                </div>
                <div className="text-xs text-muted-foreground">检索耗时(ms)</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 生成信息 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">LLM 生成信息</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">模型</span>
                <Badge variant="outline" className="text-xs font-mono">{debug.model_used}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">上下文长度</span>
                <span>{debug.context_char_count.toLocaleString()} 字符</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">生成耗时</span>
                <span>{Math.round(debug.generation_time_ms)} ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">总耗时</span>
                <span className="font-medium">{Math.round(debug.total_time_ms)} ms</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 上下文预览 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              上下文预览（传给 LLM）
            </CardTitle>
          </CardHeader>
          <CardContent>
            {debug.context_preview ? (
              <div className="bg-muted rounded p-3 text-xs font-mono whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">
                {debug.context_preview}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无上下文</span>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
