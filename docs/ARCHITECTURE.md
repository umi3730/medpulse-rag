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

## 容器部署拓扑

```text
Browser :5173
    |
    v
Nginx frontend -- /api --> FastAPI backend :8000 --> Neo4j :7687
                              |
                              +--> SQLite + embedded Qdrant (/app/runtime)
                              +--> host or remote LLM API
```

Nginx 保持前后端同源并关闭 API 响应缓冲，以支持 SSE 流式回答。Compose 使用健康检查控制启动依赖；Neo4j、SQLite/Qdrant 分别使用命名卷持久化。权威证据文件保留在应用镜像中，运行时卷只挂载 `/app/runtime`，避免覆盖仓库内的 `data/evidence`。

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

### 旧图谱元数据兼容

旧版 Neo4j 节点和关系不一定包含 `source_name`、`source_url`、`updated_at`、`evidence_level` 等可选元数据。检索层通过 `properties(entity)['key']` 动态读取这些字段，避免属性令牌尚不存在时产生 Neo4j 警告；缺失值只归一化为 `legacy`、`unknown`、`legacy_unverified` 等明确默认值，不在检索过程中回写或虚构来源。由当前系统维护的 `EvidenceClaim` 则继续使用显式字段结构。

- 当前规模不引入 Kafka；同步写 SQLite，Qdrant 仅承担语义记忆。
- 高风险加减量、停药等问题使用确定性兜底，不允许模型自由给出可执行建议。
- 意图过滤后的关系只检索一跳，避免症状或药物节点继续扩散为高密度子图。
- 保留旧数据兼容能力，但不将 46MB 上游数据直接提交到面试仓库。
