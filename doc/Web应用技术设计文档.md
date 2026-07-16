# Web 应用技术设计文档

## 1. 概述

本模块为医药知识图谱问答系统提供 Web 界面，包含：

- **FastAPI 后端**（`server/`）：提供 RESTful API，封装 `ChatBot` 问答能力
- **React 前端**（`web/`）：Vite + React + TypeScript + shadcn/ui + 知识图谱可视化

## 2. 系统架构

```
┌─────────────────┐        ┌──────────────────────┐        ┌─────────┐
│   React 前端     │  HTTP  │   FastAPI 后端         │  Bolt  │  Neo4j  │
│  (Vite + shadcn) │ ────→ │  (server/app.py)       │ ────→ │ 图数据库 │
│   :5173 (dev)    │        │    :8000               │        └─────────┘
│   /dist (prod)   │        │                        │
└─────────────────┘        │  ChatBot (qa_system/)  │        ┌─────────┐
                            │   ↳ LLM 分析           │  HTTP  │ Ollama  │
                            │   ↳ 实体归一化          │ ────→ │ qwen3:8b│
                            │   ↳ Cypher 生成/执行    │        └─────────┘
                            │   ↳ 答案格式化          │
                            └──────────────────────┘
```

## 3. 后端设计

### 3.1 文件结构

```
server/
├── __init__.py
├── app.py           # FastAPI 应用、路由、CORS、静态文件
└── models.py        # Pydantic 请求/响应模型
```

### 3.2 API 接口

| 方法 | 路径 | 说明 | 请求体/参数 | 响应 |
|------|------|------|-------------|------|
| POST | `/api/chat` | 智能问答 | `{"question": "..."}` | `ChatResponse` |
| GET | `/api/graph/neighbors/{name}` | 节点邻居查询 | `?limit=50` | `NeighborResponse` |
| GET | `/api/health` | 健康检查 | 无 | `HealthResponse` |

### 3.3 核心改造：`ChatBot.chat_detail()`

原有 `chat()` 方法仅返回答案字符串。新增 `chat_detail()` 返回完整信息：

```python
{
    "answer": "糖尿病的症状包括：多饮；多尿；...",
    "debug": {
        "level": 1,                       # 降级等级 (1=全LLM, 2=LLM+关键词, 3=词典)
        "intents": ["disease_symptom"],    # 识别到的意图
        "entities": {"disease": ["糖尿病"]}, # 提取的实体
        "cypher_queries": [...],           # 生成的 Cypher 查询
        "result_count": 15                 # 查询结果条数
    },
    "graph_data": {
        "nodes": [{"id": "糖尿病", "label": "Disease"}, ...],
        "edges": [{"source": "糖尿病", "target": "多饮", "label": "has_symptom"}, ...]
    }
}
```

**graph_data 提取逻辑**：从 Cypher 查询结果中识别 `m.name`/`n.name` 关系型字段，
根据 `question_type` 映射节点标签（Disease、Symptom、Drug、Food 等），构建力导向图数据。

### 3.4 ChatBot 单例管理

使用 FastAPI `lifespan` 事件管理 ChatBot 生命周期：
- 启动时创建单例（连接 Neo4j、初始化 LLM）
- 关闭时释放资源
- 通过 `app.state.bot_config` 传入配置参数

### 3.5 静态文件托管

生产模式下，FastAPI 自动挂载 `web/dist/` 为静态文件：
```python
app.mount("/", StaticFiles(directory="web/dist", html=True))
```

## 4. 前端设计

### 4.1 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vite | 8.x | 构建工具 |
| React | 19.x | UI 框架 |
| TypeScript | 5.9 | 类型安全 |
| shadcn/ui | 4.x | Radix UI + Tailwind CSS 组件库 |
| Tailwind CSS | 4.x | 原子化 CSS |
| react-force-graph-2d | 1.29 | 力导向图可视化 |
| Lucide React | 1.x | 图标库 |

### 4.2 页面布局

```
┌──────────────────────────────────────────────────┐
│  Header: 🏥 医药知识图谱智能问答系统    [折叠按钮] │
├────────────────────────┬─────────────────────────┤
│                        │  右侧面板 (可折叠, 480px) │
│   聊天面板              │  ┌─ Tab: 调试信息 ─────┐ │
│   ┌─────────────────┐  │  │ 降级等级 Badge       │ │
│   │ 消息气泡列表      │  │  │ 意图 Badge 列表     │ │
│   │ （用户/助手）     │  │  │ 实体分类展示        │ │
│   └─────────────────┘  │  │ Cypher 代码块        │ │
│                        │  └─────────────────────┘ │
│   ┌─ 输入框 ────────┐  │  ┌─ Tab: 知识图谱 ─────┐ │
│   │ 请输入...   [发送]│  │  │ 力导向图 + 图例     │ │
│   └─────────────────┘  │  │ 节点可点击展开      │ │
└────────────────────────┴─────────────────────────┘
```

### 4.3 组件结构

```
web/src/
├── main.tsx                # 入口
├── index.css               # Tailwind + shadcn 全局样式
├── App.tsx                 # 主布局：Header + 左右分栏
├── api/client.ts           # fetch 封装 (sendChat, fetchNeighbors)
├── types/index.ts          # TypeScript 类型定义
├── lib/utils.ts            # cn() 工具函数
└── components/
    ├── ChatPanel.tsx        # 聊天面板：消息列表 + 输入框
    ├── DebugPanel.tsx       # 调试面板：Level/意图/实体/Cypher
    ├── GraphPanel.tsx       # 图谱面板：力导向图 + 节点探索
    └── ui/                  # shadcn/ui 组件
        ├── button.tsx
        ├── input.tsx
        ├── card.tsx
        ├── tabs.tsx
        ├── badge.tsx
        └── scroll-area.tsx
```

### 4.4 关键交互

| 交互 | 描述 |
|------|------|
| 发送问题 | Enter 或点击发送 → POST /api/chat → 显示回答 + 更新调试/图谱 |
| 右侧面板折叠 | 点击 Header 按钮切换面板显隐 |
| 调试/图谱切换 | Tab 组件切换视图 |
| 图谱节点点击 | 点击节点 → GET /api/graph/neighbors/{name} → 增量加载邻居 |
| 图谱缩放拖拽 | 鼠标滚轮缩放、拖拽画布 |

### 4.5 节点颜色映射

| 节点类型 | 颜色 | 色值 |
|----------|------|------|
| Disease（疾病） | 红色 | #ef4444 |
| Symptom（症状） | 橙色 | #f97316 |
| Drug（药品） | 蓝色 | #3b82f6 |
| Food（食物） | 绿色 | #22c55e |
| Check（检查） | 紫色 | #a855f7 |
| Department（科室） | 青色 | #06b6d4 |
| Producer（药企） | 灰色 | #6b7280 |

## 5. 开发模式

```bash
# 终端 1：启动后端
cd medpulse-rag
python3 -m server.app --port 8000

# 终端 2：启动前端 (Vite dev server)
cd medpulse-rag/web
npm run dev
# → http://localhost:5173  (自动代理 /api → :8000)
```

## 6. 生产部署

```bash
# 1. 构建前端
cd web && npm run build

# 2. 启动后端（自动托管 web/dist 静态文件）
cd .. && python3 -m server.app --port 8000
# → http://localhost:8000
```

## 7. 依赖清单

### Python 依赖（新增）

| 包名 | 版本 | 用途 |
|------|------|------|
| fastapi | >= 0.115.0 | Web API 框架 |
| uvicorn[standard] | >= 0.30.0 | ASGI 服务器 |

### Node.js 依赖

详见 `web/package.json`，主要包括：
- react / react-dom 19.x
- tailwindcss 4.x
- shadcn 4.x (Radix UI)
- react-force-graph-2d 1.29
- lucide-react（图标）
- vite 8.x（构建）
- typescript 5.9（类型检查）
