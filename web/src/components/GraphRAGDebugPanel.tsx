import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { GraphRAGDebugInfo } from '@/types'
import {
  BrainCircuit,
  ChevronDown,
  Clock3,
  FileText,
  Filter,
  Gauge,
  GitBranch,
  SearchCheck,
} from 'lucide-react'

interface Props {
  debug: GraphRAGDebugInfo | null
}

const TYPE_COLORS: Record<string, string> = {
  disease: 'bg-rose-50 text-rose-800 border-rose-200',
  drug: 'bg-blue-50 text-blue-800 border-blue-200',
  food: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  check: 'bg-violet-50 text-violet-800 border-violet-200',
  symptom: 'bg-amber-50 text-amber-800 border-amber-200',
  department: 'bg-cyan-50 text-cyan-800 border-cyan-200',
}

const TYPE_LABELS: Record<string, string> = {
  disease: '疾病',
  drug: '药品',
  food: '食物',
  check: '检查',
  symptom: '症状',
  department: '科室',
}

const INTENT_LABELS: Record<string, string> = {
  drug: '用药',
  food: '饮食',
  check: '检查',
  symptom: '症状',
  department: '科室',
  prevent: '注意/预防',
  general: '综合',
  lifestyle: '作息/生活方式',
}

const RELATION_LABELS: Record<string, string> = {
  common_drug: '常用药',
  recommand_drug: '推荐药',
  drugs_of: '生产药品',
  do_eat: '宜吃',
  no_eat: '忌口',
  recommand_eat: '推荐饮食',
  need_check: '检查项目',
  has_symptom: '症状',
  acompany_with: '并发症',
  belongs_to: '所属科室',
  dept_belongs_to: '上级科室',
}

const RETRIEVAL_MODE_LABELS: Record<string, string> = {
  intent_filtered: '意图过滤',
  fallback_broad: '过滤无结果，已放宽',
  broad: '宽检索',
  none: '未检索',
  lifestyle_memory: '生活方式记忆',
}

function SectionTitle({ icon: Icon, children }: { icon: typeof GitBranch; children: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-[#31423c]">
      <Icon className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
      {children}
    </div>
  )
}

export default function GraphRAGDebugPanel({ debug }: Props) {
  if (!debug) {
    return (
      <div className="flex h-full items-center justify-center px-8 text-center">
        <div className="max-w-[17rem]">
          <div className="mx-auto mb-4 flex size-11 items-center justify-center rounded-lg bg-[#e8efec] text-[#668078]">
            <BrainCircuit className="size-5" strokeWidth={1.7} />
          </div>
          <p className="text-sm font-semibold text-[#34423d]">等待一次 GraphRAG 查询</p>
          <p className="mt-1.5 text-xs leading-5 text-[#84918b]">检索完成后，链路数据会出现在这里。</p>
        </div>
      </div>
    )
  }

  const stats = debug.subgraph_stats || {}
  const workflow = debug.workflow || 'legacy'
  const intents = debug.intents?.length ? debug.intents : debug.intent ? debug.intent.split('+') : []
  const relationFilters = debug.relation_filters || []
  const requestedFields = debug.requested_fields || []
  const memoryEntities = Object.entries(debug.memory_entities || {})

  return (
    <ScrollArea className="h-full">
      <div className="min-h-full bg-[#f7f9f8]">
        <div className="grid grid-cols-3 border-b border-[#dce4e0] bg-[#fbfcfb]">
          {[
            { label: '节点', value: stats.total_nodes ?? 0, unit: '' },
            { label: '关系', value: stats.total_edges ?? 0, unit: '' },
            { label: '总耗时', value: Math.round(debug.total_time_ms), unit: 'ms' },
          ].map((item, index) => (
            <div key={item.label} className={`px-4 py-4 ${index < 2 ? 'border-r border-[#e1e7e4]' : ''}`}>
              <p className="text-[0.65rem] font-medium text-[#829089]">{item.label}</p>
              <p className="mt-1 font-mono text-[1.35rem] font-semibold leading-none text-[#1d2a25]">
                {item.value}
                {item.unit && <span className="ml-1 text-[0.62rem] font-medium text-[#8a9791]">{item.unit}</span>}
              </p>
            </div>
          ))}
        </div>

        {debug.error && (
          <div className="border-b border-rose-200 bg-rose-50 px-5 py-3 text-xs leading-5 text-rose-800">
            {debug.error}
          </div>
        )}

        <section className="border-b border-[#dce4e0] px-5 py-5">
          <SectionTitle icon={GitBranch}>LangGraph 路由</SectionTitle>

          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
            <div className="rounded-[5px] border border-[#d9e3df] bg-white px-3 py-2.5">
              <p className="text-[0.62rem] text-[#87938e]">工作流</p>
              <p className="mt-1 truncate font-mono text-xs font-medium text-[#30413b]">{workflow}</p>
            </div>
            <div className="h-px w-3 bg-[#afc0b9]" />
            <div className="rounded-[5px] border border-[#bdd4cc] bg-[#edf4f1] px-3 py-2.5">
              <p className="text-[0.62rem] text-[#71847d]">检索模式</p>
              <p className="mt-1 truncate text-xs font-medium text-[#276255]">
                {RETRIEVAL_MODE_LABELS[debug.retrieval_mode] || debug.retrieval_mode}
              </p>
            </div>
          </div>

          <div className="mt-4">
            <p className="text-[0.65rem] font-medium text-[#7b8983]">问题意图</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {intents.length > 0 ? intents.map(intent => (
                <Badge key={intent} variant="secondary" className="rounded-[3px] bg-[#e5efeb] px-2 text-[0.68rem] font-medium text-[#276255]">
                  {INTENT_LABELS[intent] || intent}
                </Badge>
              )) : <span className="text-xs text-[#8a9791]">无</span>}
            </div>
          </div>

          <div className="mt-4">
            <div className="flex items-center gap-1.5 text-[0.65rem] font-medium text-[#7b8983]">
              <Filter className="size-3" strokeWidth={1.8} />
              关系过滤
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {relationFilters.length > 0 ? relationFilters.map(relation => (
                <Badge key={relation} variant="outline" className="rounded-[3px] border-[#d9e2de] bg-white px-2 text-[0.68rem] font-medium text-[#53645d]">
                  {RELATION_LABELS[relation] || relation}
                </Badge>
              )) : <span className="text-xs text-[#8a9791]">未限制关系类型</span>}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 divide-x divide-[#e0e7e4] border-y border-[#e0e7e4] bg-white">
            <div className="col-span-2 grid grid-cols-3 border-b border-[#e0e7e4]">
              <div className="px-3 py-2.5">
                <p className="text-[0.62rem] text-[#84918b]">回答粒度</p>
                <p className="mt-0.5 text-xs font-semibold text-[#30413b]">{debug.detail_level || 'standard'}</p>
              </div>
              <div className="border-x border-[#e0e7e4] px-3 py-2.5">
                <p className="text-[0.62rem] text-[#84918b]">风险等级</p>
                <p className="mt-0.5 text-xs font-semibold text-[#30413b]">{debug.risk_level || 'low'}</p>
              </div>
              <div className="px-3 py-2.5">
                <p className="text-[0.62rem] text-[#84918b]">需要澄清</p>
                <p className="mt-0.5 text-xs font-semibold text-[#30413b]">{debug.needs_clarification ? '是' : '否'}</p>
              </div>
            </div>
            <div className="px-3 py-2.5">
              <p className="text-[0.62rem] text-[#84918b]">会话记忆</p>
              <p className="mt-0.5 text-xs font-semibold text-[#30413b]">{debug.memory_turn_count ?? 0} 轮已加载</p>
            </div>
            <div className="px-3 py-2.5">
              <p className="text-[0.62rem] text-[#84918b]">Qdrant 召回</p>
              <p className="mt-0.5 text-xs font-semibold text-[#30413b]">{debug.vector_hit_count ?? 0} 条命中</p>
              <p className="mt-1 truncate font-mono text-[0.58rem] text-[#87948e]" title={debug.embedding_model}>
                {debug.embedding_provider || 'none'} · {debug.embedding_dimension || 0}d
              </p>
            </div>
          </div>

          <p className="mt-2 text-[0.62rem] leading-5 text-[#7b8983]">
            记忆用途：{debug.memory_scope || 'conversation_only'} · 医学证据：{debug.evidence_scope || 'neo4j_subgraph'} · 证据条目：{debug.evidence_count ?? 0}
          </p>
          <p className="mt-1 truncate font-mono text-[0.61rem] text-[#84918b]" title={debug.embedding_model}>
            embedding: {debug.embedding_provider || 'none'} / {debug.embedding_model || 'none'} / {debug.embedding_dimension || 0}d
          </p>

          {requestedFields.length > 0 && (
            <div className="mt-3">
              <p className="text-[0.65rem] font-medium text-[#7b8983]">请求字段</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {requestedFields.map(field => (
                  <Badge key={field} variant="outline" className="rounded-[3px] border-[#d9e2de] bg-white px-2 font-mono text-[0.65rem] text-[#53645d]">
                    {field}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {memoryEntities.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {memoryEntities.flatMap(([type, names]) => names.map(name => (
                <Badge key={`${type}-${name}`} variant="secondary" className="rounded-[3px] bg-[#e9eeec] px-2 text-[0.67rem] font-normal text-[#57665f]">
                  {TYPE_LABELS[type] || type}: {name}
                </Badge>
              )))}
            </div>
          )}
        </section>

        <section className="border-b border-[#dce4e0] px-5 py-5">
          <SectionTitle icon={SearchCheck}>实体解析</SectionTitle>

          <div>
            <p className="text-[0.65rem] font-medium text-[#7b8983]">LLM 提取</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {debug.entities_raw.length > 0 ? debug.entities_raw.map((entity, index) => (
                <Badge key={`${entity.name}-${index}`} variant="outline" className={`rounded-[3px] px-2 text-[0.68rem] ${TYPE_COLORS[entity.type] || 'border-slate-200 bg-slate-50 text-slate-700'}`}>
                  {entity.name}
                  <span className="ml-1 opacity-55">{TYPE_LABELS[entity.type] || entity.type}</span>
                </Badge>
              )) : <span className="text-xs text-[#8a9791]">无提取实体</span>}
            </div>
          </div>

          <div className="mt-4 border-t border-[#e1e7e4] pt-4">
            <div className="flex items-center gap-1.5 text-[0.65rem] font-medium text-[#7b8983]">
              <Gauge className="size-3" strokeWidth={1.8} />
              图谱匹配
            </div>
            {Object.keys(debug.entities_normalized).length > 0 ? (
              <div className="mt-2.5 space-y-3">
                {Object.entries(debug.entities_normalized).map(([type, names]) => (
                  <div key={type} className="grid grid-cols-[3.5rem_minmax(0,1fr)] gap-2">
                    <span className="pt-1 text-[0.65rem] font-medium text-[#829089]">{TYPE_LABELS[type] || type}</span>
                    <div className="flex flex-wrap gap-1.5">
                      {names.map(name => (
                        <Badge key={name} variant="secondary" className="rounded-[3px] bg-white px-2 text-[0.68rem] font-medium text-[#53645d] ring-1 ring-[#dce4e0]">
                          {name}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : <p className="mt-2 text-xs text-[#8a9791]">没有匹配到图谱实体</p>}
          </div>
        </section>

        <section className="border-b border-[#dce4e0] px-5 py-5">
          <SectionTitle icon={Clock3}>生成性能</SectionTitle>
          <dl className="divide-y divide-[#e2e8e5] border-y border-[#e2e8e5] text-xs">
            <div className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-[#7a8882]">模型</dt>
              <dd className="max-w-[14rem] truncate font-mono text-[0.68rem] font-medium text-[#33433d]">{debug.model_used}</dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-[#7a8882]">上下文长度</dt>
              <dd className="font-mono font-medium text-[#33433d]">{debug.context_char_count.toLocaleString()} 字符</dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-[#7a8882]">子图检索</dt>
              <dd className="font-mono font-medium text-[#33433d]">{Math.round(stats.retrieval_time_ms ?? 0)} ms</dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-[#7a8882]">答案生成</dt>
              <dd className="font-mono font-medium text-[#33433d]">{Math.round(debug.generation_time_ms)} ms</dd>
            </div>
          </dl>
        </section>

        <section className="px-5 py-5">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-xs font-semibold text-[#31423c] outline-none focus-visible:ring-2 focus-visible:ring-[#5d9487] [&::-webkit-details-marker]:hidden">
              <span className="flex items-center gap-2">
                <FileText className="size-3.5 text-[#397b6b]" strokeWidth={1.8} />
                上下文预览
              </span>
              <ChevronDown className="size-4 text-[#84918b] transition-transform duration-200 group-open:rotate-180" />
            </summary>
            <div className="mt-3">
              {debug.context_preview ? (
                <pre className="max-h-80 overflow-auto rounded-[5px] bg-[#17231f] p-3 font-mono text-[0.68rem] leading-5 text-[#dbe6e1] whitespace-pre-wrap shadow-inner">
                  {debug.context_preview}
                </pre>
              ) : <p className="text-xs text-[#8a9791]">无上下文</p>}
            </div>
          </details>
        </section>
      </div>
    </ScrollArea>
  )
}
