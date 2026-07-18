# 知脉 MedPulse

连接医学知识，生成有据可循的回答。

知脉是一个面向医疗知识问答的 GraphRAG 系统。它将医学实体提取、Neo4j 子图检索、LangGraph 工作流、LLM 回答生成和持久化对话记忆组合在一起，并在界面中展示回答所依据的图谱关系与检索过程。

> 本项目用于知识图谱与 RAG 技术研究，不提供诊断、处方或个体化医疗建议。现有医学数据包含历史互联网资料，尚未经过系统性临床审核，请勿将回答直接用于医疗决策。

## 主要能力

- 按问题意图规划需要检索的字段和关系，只回答用户所问内容。
- 从 Neo4j 检索与疾病、症状、检查、药物、食物和科室相关的子图。
- 使用 LangGraph 编排记忆加载、意图识别、实体处理、检索、生成和记忆更新。
- 使用 SQLite 保存完整会话，使用 Qdrant 与 BGE 中文向量模型检索历史问题。
- 对话记忆与医学证据分离：历史回答不会被当作新的医学事实。
- 回答使用 `[1]`、`[2]` 行内引用，并可跳转到具体图谱属性或关系证据。
- 支持多轮指代追问、历史会话恢复、Markdown 回答和图谱证据展示。
- 对自行加减量、停药和急救等高风险问题采用确定性安全兜底。
- 提供可重复的 RAG 回归测试与语义向量对比评估。

## 技术架构

```text
React / TypeScript
        │
        ▼
FastAPI ── LangGraph 工作流
        │       ├── 问题规划与实体归一化
        │       ├── Neo4j 子图检索
        │       ├── LLM 回答生成
        │       └── 安全兜底与调试信息
        │
        ├── Neo4j：医学实体、属性和关系
        ├── SQLite：会话、完整问答轮次、历史实体
        └── Qdrant + BGE：历史问题语义检索
```

前端使用 React 19、Vite 8、Tailwind CSS 4、shadcn 和 `react-force-graph-2d`。后端使用 Python、FastAPI、Neo4j、LangGraph、SQLite、Qdrant 和可配置的 LLM API。

## LangGraph 流程

```text
load_memory
  → classify_intent
  → extract_entities
  → normalize_entities
  → retrieve_subgraph
  → build_context
  → generate_answer / fallback_answer
  → update_memory
```

右侧检查面板会显示意图、请求字段、关系过滤、规范化实体、Qdrant 命中、Embedding 配置、子图统计、模型和耗时。

## 快速开始

### 1. 环境要求

- Python 3.10 或更高版本
- Node.js 20 或更高版本
- Neo4j 5.x（本地或 Aura）
- Ollama，或一个 OpenAI/Anthropic 兼容的 LLM API

### 2. 安装后端依赖

```powershell
git clone https://github.com/umi3730/medpulse-rag.git
cd medpulse-rag

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果使用 OpenAI、DeepSeek 等 OpenAI 兼容接口，还需要：

```powershell
pip install langchain-openai
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少配置 Neo4j 和一种 LLM。仓库不会提交真实密钥。

本地 Ollama 示例：

```dotenv
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

LLM_PROVIDER=ollama
LLM_MODEL=qwen3:8b
LLM_BASE_URL=http://127.0.0.1:11434
```

OpenAI 兼容接口示例：

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=your_model
LLM_BASE_URL=https://your-provider.example/v1
OPENAI_API_KEY=your_key
```

默认语义模型为 `BAAI/bge-small-zh-v1.5`。首次下载后，可设置 `EMBEDDING_LOCAL_FILES_ONLY=true` 仅使用本地缓存。

### 4. 准备 Neo4j 数据

项目保留了原始医疗数据和知识图谱构建脚本。首次使用时，请根据自己的 Neo4j 配置运行：

```powershell
.\.venv\Scripts\python.exe knowledge_graph\main.py
```

导入约 4.4 万个实体和约 29 万条关系可能需要较长时间。使用现有 Neo4j 数据库时可跳过此步。

### 5. 启动后端

```powershell
cd medpulse-rag
.\.venv\Scripts\python.exe -m server.app
```

后端默认地址：<http://127.0.0.1:8000>

### 6. 启动前端

```powershell
cd medpulse-rag\web
npm install
npm run dev
```

浏览器访问：<http://127.0.0.1:5173>

## 数据与记忆

| 存储 | 用途 | 默认位置 |
| --- | --- | --- |
| Neo4j | 医学实体、属性和关系 | 由 `.env` 配置 |
| SQLite | 会话列表、完整问答轮次、历史实体 | `data/memory.sqlite3` |
| Qdrant | 历史问题的语义向量 | `data/qdrant/` |
| Hugging Face 缓存 | BGE 模型文件 | `data/huggingface/` |

浏览器身份分为两级：`user_id` 保存在 `localStorage`，`session_id` 保存在 `sessionStorage`。后端所有 SQLite 和 Qdrant 查询同时按用户与会话隔离。

历史会话支持标题重命名、问答内容搜索和分页加载。删除会话时，后端使用同一组 `user_id + session_id` 同步删除 SQLite 中的会话元数据、完整轮次、历史实体，以及 Qdrant 中的语义记忆；相同 `session_id` 的其他用户数据不会受到影响。

相关接口：

- `GET /api/graphrag/sessions?user_id=...&q=...&limit=10&offset=0`
- `GET /api/graphrag/sessions/{session_id}?user_id=...`
- `PATCH /api/graphrag/sessions/{session_id}`
- `DELETE /api/graphrag/sessions/{session_id}?user_id=...`

### 权威医学证据

旧 `data/medical.json` 仍作为兼容知识图谱使用，但默认标记为 `legacy_unverified`。新增权威资料采用独立的 `EvidenceClaim` 与 `EvidenceSource` 节点，不覆盖旧疾病属性；同一查询字段存在已核验 claim 时，GraphRAG 优先使用 claim，并展示发布机构、文档章节、定位信息和审核状态。

统一证据记录至少包含疾病、字段、事实陈述、来源链接、发布机构、文档标题、发布日期、访问日期、证据等级和审核状态。`source_verified` 只表示来源与原文已核对，不等于临床专家审核；只有填写审核人和审核日期后才能标记为 `clinically_reviewed`。

当前提供 5 条“高血压”样例，资料来自国家卫生健康委员会的[高血压患者健康管理服务](https://www.nhc.gov.cn/jws/qta/201408/d14a4aa1c33b4577a148f7e87f8ada44.shtml)与[高血压营养和运动指导原则（2024年版）](https://www.nhc.gov.cn/ylyjs/gzdt/202407/256b4eb8398440a8811344c7be50a333.shtml)。先执行只读校验：

```powershell
.\.venv\Scripts\python.exe knowledge_graph\evidence_importer.py data\evidence\hypertension.jsonl
```

确认目标 Neo4j 配置后再幂等导入：

```powershell
.\.venv\Scripts\python.exe knowledge_graph\evidence_importer.py data\evidence\hypertension.jsonl --apply
```

证据记录是对官方资料的结构化摘编，不能替代原文、医生诊断或临床审核。

## 评估

主评估集包含 33 条问题，覆盖症状、病因、检查、用药、治疗、饮食、多意图、多轮追问、歧义澄清和高风险行为。

只校验数据集：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --validate-only
```

后端运行时执行完整评估：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation
```

仅重跑指定样例：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation `
  --case-id drug-dose-high-risk `
  --case-id drug-stop-high-risk
```

2026-07-18 工程回归结果：33/33 请求成功，完整批次得分 `0.9951`；引用有效性、引用完整率、引用忠实度代理指标和无依据事实句拦截均为 `1.0000`。这些是工程代理指标，不代表临床正确率。

BGE 与确定性哈希向量的小型改写检索对比：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_embedding_evaluation --provider sentence_transformers
.\.venv\Scripts\python.exe -m evaluation.run_embedding_evaluation --provider hash
```

当前小型测试中，BGE 的 Recall@1 为 `1.00`，哈希向量为 `0.50`。样本规模较小，仅用于验证语义检索链路。

## 测试与构建

```powershell
# 后端测试
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# 前端检查
cd web
npm run lint
npm run build
```

## 当前限制

- 原始医学知识主要来自历史互联网数据，缺少统一的来源链接、更新时间和证据等级。
- 当前证据元数据对旧数据使用 `legacy_unverified` 标记，不能等同于临床指南证据。
- 系统目前使用匿名浏览器身份，不包含账号、登录和 JWT。
- 历史会话保存文字与记忆，不保存每轮完整图谱快照。
- 评估集主要验证工程行为，仍需要医学专家审核和更大规模的临床安全评估。

## 项目来源与致谢

本项目在 [liuhuanyong/QABasedOnMedicalKnowledgeGraph](https://github.com/liuhuanyong/QABasedOnMedicalKnowledgeGraph) 的医疗知识图谱数据、词典和构建脚本基础上继续开发。原项目完成了约 4.4 万个医疗实体和约 29 万条关系的整理，并实现了基于规则的知识图谱问答。

MedPulse 在此基础上新增了 Web 界面、GraphRAG 检索、LangGraph 工作流、LLM 生成、持久化多轮记忆、BGE/Qdrant 语义检索、证据展示、安全兜底和自动化评估。感谢原作者刘焕勇及相关开源项目贡献者。

原始数据来自垂直医疗网站，仅用于学习与研究。请尊重原始数据来源和相关权益，不要直接用于商业或临床用途。
