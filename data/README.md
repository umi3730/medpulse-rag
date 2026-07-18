# 数据目录

仓库只跟踪知脉维护的结构化权威证据样例：

- `evidence/hypertension.jsonl`：国家卫生健康委员会高血压资料的结构化摘编。

本地运行时生成的 SQLite、Qdrant、模型缓存和旧医学数据均不提交到 Git。

## 可选旧知识图谱数据

兼容知识图谱仍可使用 `liuhuanyong/QASystemOnMedicalKG` 的历史 `medical.json`，但该数据来自历史互联网采集，默认标记为 `legacy_unverified`，不能当作临床指南。

按需下载并校验：

```powershell
.\.venv\Scripts\python.exe scripts\download_legacy_data.py
```

下载完成后可运行 `knowledge_graph/main.py` 导入 Neo4j。正式医学场景应逐步使用 `EvidenceClaim` 权威证据替代旧字段。
