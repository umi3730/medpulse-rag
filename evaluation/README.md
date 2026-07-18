# MedPulse GraphRAG 评估

该目录提供不依赖裁判模型的第一版确定性评估，用于在修改 Prompt、检索策略或 Embedding 前后进行同口径比较。

## 数据格式

`cases.jsonl` 每行是一个独立 JSON 对象：

- `id`：稳定且唯一的样例标识。
- `category`：样例所属测试维度，例如基础事实、安全性、多轮追问或澄清。
- `question`：发送到 `/api/graphrag/chat` 的问题。
- `history`：可选；在同一隔离会话中预先发送的问题，用于测试代词追问。
- `expected.intents`：期望命中的意图。
- `expected.entities`：按类型列出的期望实体。
- `expected.relation_filters`：期望使用的关系过滤器。
- `expected.requested_fields`：问题规划器应请求的属性或关系字段。
- `expected.answer_keywords`：回答至少应覆盖的关键词。
- `expected.forbidden_terms`：回答中不应出现的高风险表述。
- `expected.detail_level`：可选；期望的回答详细程度（`brief`、`standard`、`detailed`）。
- `expected.risk_level`：可选；期望的风险等级（`low`、`medium`、`high`）。
- `expected.needs_clarification`：可选；缺少明确疾病时是否应先追问。
- `expected.requires_evidence`：可选；设为 `false` 时不要求返回图谱证据，适合澄清类样例。

未填写的指标不会进入该样例的总分。

## 使用方式

只校验测试集格式，不需要启动服务：

```powershell
cd D:\medpulse-rag
.\.venv\Scripts\python.exe -m evaluation.run_evaluation --validate-only
```

用户自行启动后端后运行完整评估：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation
```

默认结果写入 `evaluation/results/latest.json`。也可以通过 `--dataset`、`--base-url`、`--output` 和 `--timeout` 覆盖默认值。

只重跑指定的失败样例时，可重复使用 `--case-id`：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_evaluation `
  --case-id drug-dose-high-risk `
  --case-id drug-stop-high-risk
```

## 当前指标

- `intent_recall`：预期意图召回率。
- `entity_recall`：预期实体召回率。
- `relation_recall`：预期关系过滤召回率。
- `requested_field_recall`：结构化问题计划的字段召回率。
- `answer_keyword_recall`：回答关键词覆盖率。
- `forbidden_term_pass`：高风险禁用表述检查。
- `style_template_pass`：检查“您好”“根据知识图谱”和固定免责声明等模板化措辞。
- `evidence_present`：要求证据的样例是否返回至少一条证据。
- `evidence_metadata_complete`：证据来源、更新时间和等级字段的完整率。
- `citation_validity`：回答中的引用编号是否都能映射到实际返回的证据。
- `citation_completeness`：医学事实句中带有行内引用的比例。
- `citation_faithfulness`：引用句与对应证据是否具有最基本的文本支持关系（工程代理指标）。
- `unsupported_claim_pass`：是否不存在未附引用的医学事实句。
- `detail_level_match`：回答详细程度是否符合问题中的“简单”或“详细”要求。
- `risk_level_match`：用药、治疗及危险行为是否被正确识别为相应风险等级。
- `clarification_match`：指代不明时是否正确追问，以及有会话实体时是否避免重复追问。

## 测试集构成

当前主测试集共 33 条，覆盖基础事实、症状、病因、检查、用药、科室、并发症、饮食、预防、治疗、疗程、预后、易感人群、费用、多意图、表达控制、多轮追问、澄清和高风险行为。它用于回归比较，不代表临床题库；医学结论仍需结合可靠来源和人工审核。

这些是可重复的工程代理指标，不等同于临床正确性。`citation_faithfulness` 使用文本重叠启发式，只能发现明显错引；正式评估仍需要自然语言推断模型与人工医学审核。

2026-07-18 完整回归：33/33 请求成功，总分 `0.9951`；四项引用与无依据断言指标均为 `1.0000`。

## Embedding 对比

使用小型中文改写检索集比较真实语义模型与哈希回退：

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_embedding_evaluation --provider sentence_transformers
.\.venv\Scripts\python.exe -m evaluation.run_embedding_evaluation --provider hash
```

输出 `Recall@1`、MRR、模型名称、维度和每条查询的排名。
