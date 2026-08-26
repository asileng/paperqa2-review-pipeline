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

## 快速开始（Clone → Run）

### 前置条件

- Python 3.11+（推荐 conda 管理环境）
- Zotero 桌面版 10+（仅 Zotero 写回功能需要；分析本身不需要）

### 安装

```powershell
git clone https://github.com/asileng/paperqa2-review-pipeline.git
cd paperqa2-review-pipeline

# 创建环境
conda create -n paperqa python=3.11 -y
conda activate paperqa

# 安装依赖
pip install -r requirements.txt

# 预下载嵌入模型（首次 ~2GB，之后离线可用）
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

### 配置

```powershell
# 复制环境变量模板并填入实际值
Copy-Item .env.example .env
# 编辑 .env 设置 LLM 供应商凭证（详见文件内注释）
```

支持两种 LLM 供应商：
| 供应商 | 认证方式 | 适用场景 |
|---|---|---|
| OpenCode Go 套餐 | auth.json 自动读取 | 免费/低额度测试 |
| DashScope（阿里云） | DASHSCOPE_API_KEY 环境变量 | 正式批量运行 |

### 运行

```powershell
cd pass4-v2

# 五项预检（env/PIL/LLM/VLM/embedding）
python runner.py --preflight

# 单篇分析
python runner.py <ZOTERO_KEY>

# 批量分析（并发 3，冷却自动等待重试）
python batch.py --include <KEY1> <KEY2> ... --concurrency 3 --max-hours 12

# 分析完成后写回 Zotero 索引子笔记
python runner.py <ZOTERO_KEY> --zotero-index-only
```

### 目录结构说明

首次运行会自动创建以下目录：

```
pass4-v2/
├── results/<ZOTERO_KEY>/     # 每篇论文的分析产物
│   ├── <KEY>.record.json     # 结构化记录（schema v2）
│   ├── structured_record.md  # 可读版本
│   ├── e1-e4.answer.md       # 各 Pass 提取产物
│   ├── pools/                # 证据池快照
│   ├── backfill/             # 概念定义回填
│   └── docs.pkl              # PDF 索引检查点（~1MB/篇）
├── logs/                     # 运行日志
└── queue/                    # 论文队列 JSON
```

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
