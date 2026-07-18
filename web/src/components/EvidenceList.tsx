import type { EvidenceItem } from '@/types'
import { ChevronDown, ExternalLink } from 'lucide-react'

interface Props {
  evidence?: EvidenceItem[]
}

const LEVEL_LABELS: Record<string, string> = {
  legacy_unverified: '历史数据 · 未核验',
  reviewed_reference: '已审核参考',
  guideline: '指南',
  systematic_review: '系统综述',
}

const PREDICATE_LABELS: Record<string, string> = {
  desc: '疾病简介',
  cause: '病因',
  prevent: '预防',
  cure_way: '治疗方式',
  cure_lasttime: '治疗周期',
  cured_prob: '治愈率',
  easy_get: '易感人群',
  cost_money: '治疗费用',
  has_symptom: '症状',
  acompany_with: '并发症',
  need_check: '检查项目',
  common_drug: '常用药物',
  recommand_drug: '推荐药物',
  do_eat: '宜吃',
  no_eat: '忌口',
  recommand_eat: '推荐食谱',
  belongs_to: '就诊科室',
  dept_belongs_to: '上级科室',
}

export default function EvidenceList({ evidence = [] }: Props) {
  if (evidence.length === 0) return null
  const legacyCount = evidence.filter((item) => item.evidence_level === 'legacy_unverified').length

  return (
    <details className="group mt-5 border-t border-[#dbe4e0] pt-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-[4px] py-1 text-xs font-medium text-[#52655e] outline-none transition-colors hover:text-[#276255] focus-visible:ring-2 focus-visible:ring-[#6d9d91] [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          <span>回答证据</span>
          <span className="rounded-[3px] bg-[#e7efec] px-1.5 py-0.5 font-mono text-[0.64rem] text-[#41685d]">
            {evidence.length}
          </span>
        </span>
        <ChevronDown className="size-3.5 transition-transform duration-200 group-open:rotate-180" strokeWidth={1.8} />
      </summary>

      <ol className="mt-3 divide-y divide-[#e1e8e5] border-y border-[#e1e8e5]">
        {evidence.map((item, index) => {
          const citationIndex = item.citation_index || index + 1
          const predicate = PREDICATE_LABELS[item.predicate] || item.predicate
          const level = LEVEL_LABELS[item.evidence_level] || item.evidence_level
          return (
            <li
              id={`evidence-${citationIndex}`}
              key={item.id}
              className="grid scroll-mt-24 grid-cols-[2.2rem_minmax(0,1fr)] gap-2 py-3 first:pt-3 target:bg-emerald-50/70"
            >
              <span className="pt-0.5 font-mono text-[0.65rem] tabular-nums text-[#91a099]">
                [{citationIndex}]
              </span>
              <div className="min-w-0">
                <p className="text-xs leading-5 text-[#32453e]">
                  <span className="font-medium">{item.subject}</span>
                  <span className="mx-1.5 text-[#9ba8a2]">—</span>
                  <span className="text-[#467366]">{predicate}</span>
                  <span className="mx-1.5 text-[#9ba8a2]">→</span>
                  <span className="break-words">{item.object}</span>
                </p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.65rem] text-[#7b8983]">
                  {item.source_url ? (
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-[#376b5d] underline decoration-[#b7cec7] underline-offset-3 hover:text-[#245548] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6d9d91]"
                    >
                      {item.source_name}
                      <ExternalLink className="size-2.5" strokeWidth={1.8} />
                    </a>
                  ) : (
                    <span>{item.source_name}</span>
                  )}
                  <span>{item.updated_at === 'unknown' ? '更新时间未知' : item.updated_at}</span>
                  <span className={item.evidence_level === 'legacy_unverified' ? 'text-amber-700' : 'text-[#397264]'}>
                    {level}
                  </span>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
      {legacyCount > 0 && (
        <p className="mt-3 rounded-[4px] border border-amber-200 bg-amber-50 px-3 py-2 text-[0.68rem] leading-5 text-amber-800">
          其中 {legacyCount} 条来自历史互联网数据，尚未经过临床审核；请勿据此自行诊断、用药或调整治疗。
        </p>
      )}
    </details>
  )
}
