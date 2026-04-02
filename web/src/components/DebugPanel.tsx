import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { DebugInfo } from '@/types'

interface Props {
  debug: DebugInfo | null
}

const LEVEL_LABELS: Record<number, { text: string; color: string }> = {
  0: { text: '无', color: 'bg-gray-200 text-gray-700' },
  1: { text: 'Level 1: 全 LLM', color: 'bg-green-100 text-green-800' },
  2: { text: 'Level 2: LLM实体+关键词', color: 'bg-yellow-100 text-yellow-800' },
  3: { text: 'Level 3: 词典降级', color: 'bg-red-100 text-red-800' },
}

const INTENT_LABELS: Record<string, string> = {
  disease_symptom: '疾病→症状',
  symptom_disease: '症状→疾病',
  disease_cause: '疾病→病因',
  disease_acompany: '疾病→并发症',
  disease_do_food: '疾病→宜食',
  disease_not_food: '疾病→忌口',
  disease_drug: '疾病→药品',
  disease_check: '疾病→检查',
  disease_prevent: '疾病→预防',
  disease_lasttime: '疾病→周期',
  disease_cureway: '疾病→治疗',
  disease_cureprob: '疾病→治愈率',
  disease_easyget: '疾病→易感',
  disease_desc: '疾病→描述',
  check_disease: '检查→疾病',
  drug_disease: '药品→疾病',
  food_do_disease: '食物→有益',
  food_not_disease: '食物→有害',
}

export default function DebugPanel({ debug }: Props) {
  if (!debug) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        发送问题后查看调试信息
      </div>
    )
  }

  const level = LEVEL_LABELS[debug.level] || LEVEL_LABELS[0]

  return (
    <ScrollArea className="h-full p-4">
      <div className="space-y-4">
        {/* 降级等级 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">降级等级</CardTitle>
          </CardHeader>
          <CardContent>
            <Badge className={level.color}>{level.text}</Badge>
          </CardContent>
        </Card>

        {/* 意图 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">识别意图 ({debug.intents.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {debug.intents.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {debug.intents.map(i => (
                  <Badge key={i} variant="outline" className="text-xs">
                    {INTENT_LABELS[i] || i}
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无</span>
            )}
          </CardContent>
        </Card>

        {/* 实体 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">提取实体</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(debug.entities).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(debug.entities).map(([type, names]) => (
                  <div key={type}>
                    <span className="text-xs text-muted-foreground">{type}:</span>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {names.map(n => (
                        <Badge key={n} variant="secondary" className="text-xs">{n}</Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无</span>
            )}
          </CardContent>
        </Card>

        {/* Cypher 查询 */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Cypher 查询 ({debug.cypher_queries.length}) · 结果 {debug.result_count} 条
            </CardTitle>
          </CardHeader>
          <CardContent>
            {debug.cypher_queries.length > 0 ? (
              <div className="space-y-2">
                {debug.cypher_queries.map((q, i) => (
                  <div key={i} className="bg-muted rounded p-2 text-xs font-mono break-all">
                    <div>{q.cypher}</div>
                    <div className="text-muted-foreground mt-1">
                      参数: {JSON.stringify(q.params)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">无</span>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
