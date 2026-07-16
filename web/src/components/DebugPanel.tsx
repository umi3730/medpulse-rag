import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { DebugInfo } from '@/types'
import { Activity, Braces, GitBranch, SearchCheck } from 'lucide-react'

interface Props {
  debug: DebugInfo | null
}

const LEVEL_LABELS: Record<number, { text: string; color: string; tone: string }> = {
  0: { text: '无检索', color: 'bg-slate-100 text-slate-700 border-slate-200', tone: 'text-slate-500' },
  1: { text: 'Level 1 · 全 LLM', color: 'bg-emerald-50 text-emerald-800 border-emerald-200', tone: 'text-emerald-700' },
  2: { text: 'Level 2 · 实体 + 关键词', color: 'bg-amber-50 text-amber-800 border-amber-200', tone: 'text-amber-700' },
  3: { text: 'Level 3 · 词典降级', color: 'bg-rose-50 text-rose-800 border-rose-200', tone: 'text-rose-700' },
}

const INTENT_LABELS: Record<string, string> = {
  disease_symptom: '疾病 → 症状',
  symptom_disease: '症状 → 疾病',
  disease_cause: '疾病 → 病因',
  disease_acompany: '疾病 → 并发症',
  disease_do_food: '疾病 → 宜食',
  disease_not_food: '疾病 → 忌口',
  disease_drug: '疾病 → 药品',
  disease_check: '疾病 → 检查',
  disease_prevent: '疾病 → 预防',
  disease_lasttime: '疾病 → 周期',
  disease_cureway: '疾病 → 治疗',
  disease_cureprob: '疾病 → 治愈率',
  disease_easyget: '疾病 → 易感',
  disease_desc: '疾病 → 描述',
  check_disease: '检查 → 疾病',
  drug_disease: '药品 → 疾病',
  food_do_disease: '食物 → 有益疾病',
  food_not_disease: '食物 → 有害疾病',
}

export default function DebugPanel({ debug }: Props) {
  if (!debug) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <div>
          <div className="mx-auto mb-3 flex size-11 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
            <SearchCheck className="size-5" />
          </div>
          <p className="text-sm font-medium text-slate-700">还没有调试信息</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">发送问题后，这里会显示实体识别、意图和 Cypher 查询。</p>
        </div>
      </div>
    )
  }

  const level = LEVEL_LABELS[debug.level] || LEVEL_LABELS[0]
  const entityTotal = Object.values(debug.entities).reduce((sum, names) => sum + names.length, 0)

  return (
    <ScrollArea className="h-full p-4">
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          <Card className="rounded-xl border-slate-200 bg-white py-3 ring-slate-200">
            <CardContent className="px-3">
              <p className="text-[11px] font-medium text-slate-500">意图</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-950">{debug.intents.length}</p>
            </CardContent>
          </Card>
          <Card className="rounded-xl border-slate-200 bg-white py-3 ring-slate-200">
            <CardContent className="px-3">
              <p className="text-[11px] font-medium text-slate-500">实体</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-950">{entityTotal}</p>
            </CardContent>
          </Card>
          <Card className="rounded-xl border-slate-200 bg-white py-3 ring-slate-200">
            <CardContent className="px-3">
              <p className="text-[11px] font-medium text-slate-500">结果</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-950">{debug.result_count}</p>
            </CardContent>
          </Card>
        </div>

        <Card className="rounded-xl border-slate-200 bg-white ring-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className={`size-4 ${level.tone}`} />
              降级等级
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="outline" className={level.color}>{level.text}</Badge>
          </CardContent>
        </Card>

        <Card className="rounded-xl border-slate-200 bg-white ring-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <GitBranch className="size-4 text-emerald-700" />
              识别意图
            </CardTitle>
          </CardHeader>
          <CardContent>
            {debug.intents.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {debug.intents.map(i => (
                  <Badge key={i} variant="outline" className="border-emerald-700/20 bg-emerald-50 text-xs text-emerald-800">
                    {INTENT_LABELS[i] || i}
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-slate-500">无</span>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl border-slate-200 bg-white ring-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <SearchCheck className="size-4 text-teal-700" />
              提取实体
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(debug.entities).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(debug.entities).map(([type, names]) => (
                  <div key={type}>
                    <span className="text-xs font-medium text-slate-500">{type}</span>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {names.map(n => (
                        <Badge key={n} variant="secondary" className="bg-slate-100 text-xs text-slate-700">{n}</Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-sm text-slate-500">无</span>
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl border-slate-200 bg-white ring-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Braces className="size-4 text-slate-700" />
              Cypher 查询
            </CardTitle>
          </CardHeader>
          <CardContent>
            {debug.cypher_queries.length > 0 ? (
              <div className="space-y-2">
                {debug.cypher_queries.map((q, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 bg-slate-950 p-3 text-xs text-slate-100 shadow-inner">
                    <div className="font-mono leading-5 text-emerald-100">{q.cypher}</div>
                    <div className="mt-2 border-t border-white/10 pt-2 font-mono text-slate-400">
                      params: {JSON.stringify(q.params)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-sm text-slate-500">无</span>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  )
}
