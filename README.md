# paperqa2-review-pipeline

基于 PaperQA2 的学术文献结构化分析管线。当前且唯一维护的实现位于 `pass4-v2/`：它对 Zotero 本地 PDF 运行证据驱动的 4-Pass 分析，生成可追溯的 Markdown/JSON 记录，并可将索引指针安全写回 Zotero。

## 能力

- Pass 1：研究定位、研究空白与研究问题
- Pass 2：方法、材料、数据与证据
- Pass 3：中心论点、主要结论、贡献与核心概念
- Design Gate：仅在论文存在设计内容时执行 Pass 4
- Pass 4：设计选择、机制、预期和观察到的效果
- 概念定义回填、参考文献确定性抽取、引用审计
- 产物级断点续跑、批量并发、供应商冷却与失败隔离
- 可选的 Zotero 索引笔记创建/更新与回读校验

## 快速开始

前置条件：Python 3.11+；Zotero Desktop 10+ 仅在构建队列或写回索引时需要。

```powershell
git clone https://github.com/asileng/paperqa2-review-pipeline.git
cd paperqa2-review-pipeline

conda create -n paperqa python=3.11 -y
conda activate paperqa
pip install -r requirements.txt

python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
Copy-Item .env.example .env
```

在 `pass4-v2/` 下先创建或提供符合队列 schema 的 JSON 队列。队列中的每篇论文至少要包含 `zotero_key` 和可访问的 `pdf_path`。

```powershell
cd pass4-v2

# 检查模型、嵌入和运行环境
python runner.py --preflight

# 单篇分析
python runner.py <ZOTERO_KEY> --queue <QUEUE_JSON>

# 批量分析
python batch.py --queue <QUEUE_JSON> --concurrency 3 --max-hours 12 --wait-reset

# 将已有分析产物写回 Zotero 索引
python runner.py <ZOTERO_KEY> --zotero-index-only
```

## 运行产物

运行时数据均不提交到 Git：

```text
pass4-v2/
├── results/<ZOTERO_KEY>/
│   ├── <KEY>.record.json
│   ├── structured_record.md
│   ├── e1-e4.answer.md
│   ├── pools/
│   ├── backfill/
│   └── docs.pkl
├── logs/
├── queue/
├── REPORT.md
└── run_manifest.json
```

## 关键文件

- `pass4-v2/runner.py`：单篇分析与产物装配
- `pass4-v2/batch.py`：批量调度、恢复和报告
- `pass4-v2/model_router.py`：模型路由和冷却状态
- `pass4-v2/zotero_index.py`：Zotero 索引写回
- `pass4-v2/build_queue_user_collections.py`：从 Zotero collection 构建队列
- `pass4-v2/prompts/`：分析提示词
- `pass4-v2/GLUE.md`：当前工程约束与数据流
- `specs/important-guide-for-paperQA2.md`：分析协议母本

## 数据边界

- `results/`、PDF、索引检查点、日志、队列和批量状态都不进入仓库。
- Zotero 索引笔记只保存产物指针和溯源字段，不复制完整分析正文。
- `modules` 与 `relations` 保持空数组，不自动推断研究 roadmap 归属。
