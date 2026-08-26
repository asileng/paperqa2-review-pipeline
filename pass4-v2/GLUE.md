# pass4-v2 工程说明

本文件只记录当前管线的运行契约。提示词正文来自 `../specs/important-guide-for-paperQA2.md`；`runner.py` 负责装配，提示词文件不包含运行时代码。

## 提示词映射

| 组件 | 文件 |
|---|---|
| 全局规则 | `prompts/00_global_rules.md` |
| Pass 1 检索与提取 | `r1a.md`、`r1b.md`、`e1.md` |
| Pass 2 检索与提取 | `r2a.md`、`r2b.md`、`e2.md` |
| Pass 3 检索与提取 | `r3a.md`、`r3b.md`、`e3.md` |
| Design Gate | `gate.md` |
| Pass 4 检索与提取 | `r4a.md`、`r4b.md`、`e4.md` |
| 概念回填 | `backfill_r.md`、`backfill_e.md` |

## 数据流

```text
PDF → Docs.aadd() → Pass 1/2/3 的双检索证据池 → Extraction
                                              ↓
                                        Design Gate
                                  ┌───────────┴───────────┐
                               skip Pass 4            Pass 4
                                  └───────────┬───────────┘
                                              ↓
                         概念回填 + 参考文献确定性抽取
                                              ↓
                  structured_record.md + <KEY>.record.json
```

- Pass 2 读取 Pass 1 输出中的研究问题作为参考。
- Gate 使用 Pass 1–3 的证据池；选择 C 时做一次轻量检索后重新裁决。
- Pass 3 中最多五个核心概念进入独立检索与定义提取。
- 每篇论文内的证据按 `Context.id` 去重。

## 输出与恢复

每篇论文在 `results/<ZOTERO_KEY>/` 下生成 Markdown、JSON、证据池、概念回填和 `docs.pkl` 索引检查点。

恢复只在以下元数据一致时复用产物：retrieve/extract/vision 模型、嵌入模型、PaperQA 版本和全部提示词 SHA-256。配置或提示词改变时重新分析，避免混合不同条件下的结果。

`record.json` 的核心字段包括 metadata、模型三元组、Pass 路径、Gate、概念回填、引用审计、提示词哈希、token usage、计时和 warnings。`modules` 与 `relations` 固定为空数组。

## 批量与路由

- `batch.py` 以 asyncio semaphore 控制并发；单篇失败不会中断其他论文。
- manifest 和报告采用原子写入；写入失败时 manifest 会尝试旁路恢复文件。
- 路由在论文粒度绑定 retrieve/extract/vision 三角色；额度、认证和网络错误分别处理。
- provider 冷却时状态记录为 `cooldown`；`--wait-reset` 会等待最早的恢复时间。
- Zotero 写回与论文分析状态隔离：写回失败只记录错误，不把已完成分析标记为失败。

## Zotero 写回

每个「条目 × provider × 管线」只维护一条索引笔记。笔记只保存 record 路径、模型、提示词指纹、引用方案和 Gate 等溯源字段；写入要求持久授权，并在写入后回读验证字段完整性。
