# 知脉 MedPulse 架构说明

## 请求链路

```text
React Web
  → FastAPI SSE
  → LangGraph
      → load_memory
      → classify_intent
      → extract_entities
      → normalize_entities
      → retrieve_subgraph
      → build_context
      → generate_answer / fallback_answer
      → update_memory
```

## 数据职责

- Neo4j：医学实体、关系、`EvidenceClaim` 与 `EvidenceSource`。
- SQLite：用户会话元数据、完整问答轮次和历史实体。
- Qdrant：BGE 编码的历史问题，只用于理解对话，不作为医学证据。
- 前端：回答、行内引用、证据卡片、图谱和工作流调试信息。

## 可信回答链路

```text
查询字段/关系规划
  → 权威 claim 优先检索
  → 证据顺序编号
  → LLM 生成行内引用
  → 后端逐句检查引用
  → 前端跳转并高亮证据
```

旧互联网数据统一标记为 `legacy_unverified`。`source_verified` 仅表示已核对原始链接与内容；它不等于临床专家审核。

## 隔离边界

所有 SQLite 与 Qdrant 会话操作同时使用 `user_id + session_id`。删除会话会同步清理两种存储，但不会影响使用相同 `session_id` 的其他用户。

## 主要工程取舍

- 当前规模不引入 Kafka；同步写 SQLite，Qdrant 仅承担语义记忆。
- 高风险加减量、停药等问题使用确定性兜底，不允许模型自由给出可执行建议。
- 意图过滤后的关系只检索一跳，避免症状或药物节点继续扩散为高密度子图。
- 保留旧数据兼容能力，但不将 46MB 上游数据直接提交到面试仓库。
