# paperqa2-review-pipeline

基于 PaperQA2 (paper-qa 2026.8.12) 的学术文献结构化分析管线。三个版本完整备案，
当前活跃版本为 **pass4-v2**（融合版）。

## 版本谱系

```
pilot-v1 ──(3-Pass+合成, 单篇隔离, Zotero 写回 v3)──┐
                                                    ├──▶ pass4-v2（融合版）
pass4-v1 ──(4-Pass 逐字提示词管线, 批量队列)────────┘
```

| 版本 | 架构 | 定位 |
|---|---|---|
| `archive/pilot-v1` | 3 检索 Pass + 1 合成 Pass；指纹/用量/引用审计/归档/续跑/检查点/preflight；Zotero 索引写回 | 单篇深读 + Zotero 联动原型 |
| `archive/pass4-v1` | 4-Pass（Retrieval A/B → 合并池 → Extraction）+ Design Gate(A/B/C) + 概念回填；asyncio 批量队列 | 提示词逐字来自 `specs/important-guide-for-paperQA2.md`，批量无人值守 |
| **`pass4-v2/`** | pass4-v1 全部能力 + Zotero 索引写回层（`zotero_index.py`） | **当前活跃** |

## 快速开始

```powershell
# 环境：conda env paperqa (python 3.11, pip install "paper-qa[local]>=5" pillow)
cd pass4-v2

# 五项预检（env/PIL/LLM/VLM/embedding）
python runner.py --preflight

# 单篇分析（+ 写回 Zotero 索引）
python runner.py <ZOTERO_KEY> --update-zotero-index

# 仅用既有产物写回索引（不重跑分析）
python runner.py <ZOTERO_KEY> --zotero-index-only

# 批量（并发 4，断点续跑，每篇完成后写回索引）
powershell -ExecutionPolicy Bypass -File launch_batch.ps1 4 8   # 或 batch.py --zotero-index
```

## Zotero 索引规范

- 一（条目 × provider×管线版本）一笔记，标题标签：
  `[reviewBricks:pass4-v2][provider:paperqa2_docs_local] <ZOTERO_KEY>`
- 笔记只存指针（record_json_path / record_md_path / prompts_sha256 / gate_choice 等
  16 字段），绝不复制答案正文
- 安全门：无 flag 零请求；`remember: true` 缺失即停；同标签损坏笔记报告停止，
  绝不静默覆写；SciSpace/pilot 既有笔记零接触
- 引用诚实性：citation_scheme 据实派生（页码范围 vs pqac-* 内部块 id 计数告警）

## 数据边界

- `results/`、PDF、docs.pkl、日志不入库（见 .gitignore）；本仓库只管代码、提示词与规范
- roadmap 归属（modules/relations）保持空数组——研究判断不自动推断
- 运行时真值记录于各 results/<KEY>/meta.json；旧结果缺失字段以 post-hoc 标注补齐

## 关键文档

- `specs/important-guide-for-paperQA2.md` — 4-Pass 提示词母本（逐字来源）
- `archive/pass4-v1/GLUE.md` — 切分映射、Gate 裁决、队列规则等工程决策登记
- `archive/pass4-v1/REPORT.md` — 首次夜间批量实战报告
