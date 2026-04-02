# GraphRAG 技术设计文档

## 1. 概述

GraphRAG（Graph Retrieval-Augmented Generation）是对基础问答系统的升级版本。基础问答依赖固定意图分类 + Cypher 模板 + 模板答案；GraphRAG 则通过 **动态子图检索 + LLM 生成** 处理更复杂的多实体、开放性医学问题。

### 1.1 基础问答 vs GraphRAG

| 维度 | 基础问答 | GraphRAG |
|------|---------|----------|
| 意图识别 | 18 种固定分类 | 不需要 — LLM 自行理解 |
| Cypher 查询 | 固定模板（每种意图对应一个） | 动态多跳邻居遍历 |
| 答案生成 | 模板拼接字符串 | LLM 基于图谱上下文自由生成 |
| 适用场景 | 单意图单实体 | 多实体、多跳、复合问题 |
| 示例 | "糖尿病有什么症状" | "糖尿病和高血压有什么共同的并发症和用药" |

## 2. 管线架构

```
用户问题
  ↓
[1] LLM 实体抽取 (entity_extractor.py)
  ↓  提取实体名+类型，不做意图分类
[2] 实体归一化 (复用 qa_system/entity_normalizer.py)
  ↓  模糊匹配到知识图谱中的标准名称
[3] 多跳子图检索 (subgraph_retriever.py)
  ↓  1-2 跳邻居遍历 + Disease 属性查询
[4] 上下文组装 (context_builder.py)
  ↓  子图 → 结构化文本，限 6000 字符
[5] LLM 答案生成 (generator.py)
  ↓  问题 + 图谱上下文 → 自然语言回答
返回 {answer, debug, graph_data}
```

## 3. 模块说明

### 3.1 文件结构

```
graphrag/
├── __init__.py              # 导出 GraphRAGBot
├── config.py                # 配置参数 + 提示词模板
├── entity_extractor.py      # LLM 实体抽取
├── subgraph_retriever.py    # 多跳子图检索
├── context_builder.py       # 子图 → 文本上下文
├── generator.py             # LLM 答案生成
└── graphrag_bot.py          # 编排器
```

### 3.2 config.py

复用 `qa_system/config.py` 的共享配置（Neo4j 连接、Ollama 地址、词典路径），新增：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_HOPS` | 2 | 最大跳数 |
| `HOP1_LIMIT` | 50 | 第一跳每实体最多邻居数 |
| `HOP2_LIMIT` | 20 | 第二跳每节点最多邻居数 |
| `HOP2_CANDIDATES` | 15 | 第二跳候选节点数（优先 Disease） |
| `MAX_CONTEXT_CHARS` | 6000 | 上下文最大字符数 |
| `LLM_NUM_PREDICT_GENERATION` | 1024 | 生成阶段最大 token 数 |

包含两个提示词模板：
- **ENTITY_EXTRACT_PROMPT**: 指导 LLM 从问题中提取实体（仅名称+类型）
- **GENERATION_SYSTEM_PROMPT**: 指导 LLM 基于知识图谱上下文生成医学回答

### 3.3 entity_extractor.py

`EntityExtractor` 类接收共享的 `ChatOllama` 实例：

- 使用简化提示词（只提取实体，不分类意图）
- 输出格式: `[{"name": "糖尿病", "type": "disease"}, {"name": "高血压", "type": "disease"}]`
- `_parse()` 方法清理 `<think>` 标签，用正则提取 JSON 数组

### 3.4 subgraph_retriever.py

`SubgraphRetriever` 类接收共享的 `py2neo.Graph` 实例：

**Hop 1**: 对每个归一化实体执行邻居查询
```cypher
MATCH (n)-[r]-(m) WHERE n.name=$name
RETURN labels(n)[0], n.name, type(r), labels(m)[0], m.name
LIMIT 50
```

**Hop 2**: 从 Hop1 结果中选择最多 15 个重要节点（优先 Disease 标签），每个再扩展 20 个邻居。

**属性查询**: 对检索到的 Disease 节点，额外查询 8 个属性字段（desc, cause, prevent, cure_way, symptom 等）。

### 3.5 context_builder.py

`ContextBuilder` 将子图转化为 LLM 可理解的结构化文本：

```
【疾病】糖尿病
  简介: 糖尿病是一种以高血糖为特征的代谢性疾病...
  病因: 遗传因素、环境因素...
  症状: 多饮 / 多尿 / 体重下降
  常用药: 二甲双胍 / 格列本脲

【药品】二甲双胍
  适用疾病: 糖尿病 / 2型糖尿病
```

- 查询实体优先排列
- 关系按类型分组，中文标签展示
- 截断至 `MAX_CONTEXT_CHARS`（默认 6000 字符）

### 3.6 generator.py

`GraphRAGGenerator` 类接收共享的 `ChatOllama` 实例（`num_predict=1024`）：

- 将 `question + context_text` 填入系统提示词
- 清理 `<think>` 标签
- 返回 `{answer, generation_time_ms, model_used}`

### 3.7 graphrag_bot.py — 编排器

`GraphRAGBot` 初始化时创建共享实例：
- 1 个 `ChatOllama`（实体抽取和答案生成共用）
- 1 个 `py2neo.Graph`
- 1 个 `EntityNormalizer`（复用 qa_system）

`chat_detail(question)` 按序执行 5 阶段管线，返回：

```python
{
    "answer": "...",
    "debug": {
        "entities_raw": [{"name": "糖尿病", "type": "disease"}],
        "entities_normalized": {"disease": ["糖尿病"]},
        "subgraph_stats": {
            "total_nodes": 45,
            "total_edges": 68,
            "retrieval_time_ms": 120.5
        },
        "context_preview": "前500字符...",
        "context_char_count": 4500,
        "generation_time_ms": 3200.0,
        "model_used": "qwen3:8b",
        "total_time_ms": 3800.0
    },
    "graph_data": {
        "nodes": [{"id": "糖尿病", "label": "Disease"}, ...],
        "edges": [{"source": "糖尿病", "target": "多饮", "label": "has_symptom"}, ...]
    }
}
```

## 4. 后端 API

### POST `/api/graphrag/chat`

请求:
```json
{"question": "糖尿病和高血压有什么共同的并发症和用药？"}
```

响应:
```json
{
    "answer": "糖尿病和高血压共同的并发症包括...",
    "mode": "graphrag",
    "debug": { ... },
    "graph_data": { "nodes": [...], "edges": [...] }
}
```

`mode` 字段:
- `"graphrag"` — 正常 GraphRAG 模式
- `"fallback_basic"` — Ollama 不可用时降级到基础问答

### GET `/api/health`

新增 `graphrag` 字段表示 GraphRAGBot 是否可用。

## 5. 前端集成

### 5.1 模式切换

顶部 Header 添加模式切换按钮（基础问答 / GraphRAG），两个模式维护独立的状态（聊天历史、调试信息、图谱数据）。

### 5.2 GraphRAG 聊天面板

`GraphRAGChatPanel.tsx` — 与基础版 ChatPanel 结构类似，区别：
- 调用 `/api/graphrag/chat` API
- 消息气泡上显示 mode Badge（`GraphRAG` / `降级到基础问答`）
- 加载提示为"检索子图 + 生成回答中"

### 5.3 GraphRAG 调试面板

`GraphRAGDebugPanel.tsx` 展示 5 个信息卡片：

1. **LLM 提取实体** — 原始实体列表，按类型着色
2. **归一化实体** — 图谱匹配结果，按类型分组
3. **子图检索统计** — 节点数、边数、检索耗时
4. **LLM 生成信息** — 模型名、上下文长度、生成耗时、总耗时
5. **上下文预览** — 可滚动区域展示传给 LLM 的结构化文本

### 5.4 知识图谱面板

复用 `GraphPanel.tsx`，两个模式共享同一个力导向图组件。

## 6. 复用关系

| 复用组件 | 来源 | 用途 |
|---------|------|------|
| `EntityNormalizer` | `qa_system/entity_normalizer.py` | 实体名模糊匹配到图谱标准名 |
| Neo4j/Ollama 配置 | `qa_system/config.py` | 连接参数、词典路径 |
| `GraphPanel` | `web/src/components/` | 力导向图可视化 |
| `GraphData` 类型 | `server/models.py` + `types/index.ts` | nodes/edges 数据结构 |

## 7. 降级策略

1. **Ollama 不可用**: GraphRAGBot 标记 `available=False`，API 自动降级到基础问答，前端显示"降级到基础问答"Badge
2. **Neo4j 不可用**: 初始化时捕获异常，返回空答案
3. **实体抽取失败**: 返回空实体列表，子图检索无结果，LLM 基于空上下文回答（效果类似纯 LLM）
4. **子图为空**: LLM 仍会尝试回答，但会在答案中说明未找到相关图谱信息
