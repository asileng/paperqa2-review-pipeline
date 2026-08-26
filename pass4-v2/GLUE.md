# GLUE — 拆分与装配决策登记（pass4-v1）

本文件登记 4-Pass 工作流中所有**非逐字**的工程决策。提示词本体全部逐字来自
`important-guide-for-paperQA2.md`（行号区间见下表），由 `split_prompts.py` 机械切分。

## 一、提示词切分映射（逐字区间）

| 文件 | guide 行号 | 内容 |
|---|---|---|
| prompts/00_global_rules.md | 3–38 | 全局规则块（14 条铁律），运行时注入每个 Extraction/Gate/Backfill 的 user message 头部 |
| prompts/r1a.md | 50–60 | Retrieval 1A（前研究状况与局限） |
| prompts/r1b.md | 66–74 | Retrieval 1B（本文问题/RQ 定位） |
| prompts/e1.md | 78–172 | Extraction 1 |
| prompts/r2a.md | 180–236 | Retrieval 2A（方法设计，含标题头） |
| prompts/r2b.md | 242–336 | Retrieval 2B（材料/数据） |
| prompts/e2.md | 340–711 | Extraction 2 |
| prompts/r3a.md | 715–746 | Retrieval 3A（thesis/main argument） |
| prompts/r3b.md | 749–768 | Retrieval 3B（主要 findings） |
| prompts/e3.md | 771–1060 | Extraction 3（末节产出核心概念清单） |
| prompts/gate.md | 1064–1087 | PASS 4 Gate |
| prompts/r4a.md | 1093–1131 | Retrieval 4A（设计/intended effect） |
| prompts/r4b.md | 1135–1165 | Retrieval 4B（evaluation/observed effect） |
| prompts/e4.md | 1168–1478 | Extraction 4 |

未纳入任何提示词文件的 guide 行：L1「接」（粘贴残留）、L42–44（Pass 结构中文导语）、
L48/L64（"首先/随后你需要 Retrieve："引导语）、L76（合并指示语）、L1484 起的架构说明——
这些是给建造者的元指令，已由 runner 的程序逻辑承担，语义无丢失。

## 二、构造件（guide 委托细节、最小化构造）

- **prompts/backfill_r.md / backfill_e.md**：guide 只定义了 backfill 流程
  （L1513–1515「针对选中的核心概念逐个 retrieval → definition extraction」），
  未给出两个提示词原文。backfill_r 为检索查询模板（`{concept}` 运行时替换）；
  backfill_e 复用全局规则 + 与其他 Extraction 一致的三件套输出契约。
- **Gate 输入**：gate 原文要求「根据目前已经获得的论文信息」判断 → 输入为
  Pool 1–3 全部证据摘录 + gate.md。若判 C：按 guide「进行一次轻量 retrieval」→ 用 r4a
  文本做一次 probe retrieval，将新证据并入后重判一次。
  **重判仍为 C 时取 A（执行 PASS 4）**：假阳性只多耗 token，假阴性会永久丢失数据。此裁决无 guide 先例，特此登记。

## 三、跨 Pass 数据流（程序化装配）

```
e1.answer ──(作为 REFERENCE 注入 e2 user message)──▶ Extraction 2 §7 RQ 操作化
pools 1–3 ──▶ Gate
e3 §6 Core Concepts（≤5 个）──▶ backfill 逐概念检索+提取
全部产物 ──▶ structured_record.md + <KEY>.record.json (schema pass4-v2)
```

Extraction user message 统一结构：

```
{00_global_rules}
=== RETRIEVED EVIDENCE (PASS n POOL) ===
{pool}
[仅 e2 额外] === REFERENCE: PASS 1 EXTRACTION OUTPUT === {e1 全文}
=== EXTRACTION TASK ===
{eN 逐字原文}
```

## 四、Retrieval 实现绑定

- `Docs.aget_evidence(rX_text, settings)` 只积累证据不生成答案（paperqa v2026.8.12，
  PQASession.contexts；Context{id, context, question, text, score}）。
- Evidence Pool 条目格式：`[E##] score | anchor=text.name | source_citation=formatted_citation`
  + query-conditioned summary。锚点诚实性沿用 pilot-v1 纪律：doc-key+页码范围据实派生
  citation_scheme，pqac-* 内部块 id 计数告警，绝不伪称页码。
- 同篇内 A/B 及所有轮次共享 seen-set 去重（Context.id）。
- Settings 单例共享（llm=summary_llm=qwen3.7-plus 快照, embedding=bge-m3 hybrid,
  temperature=0, parsing.enrichment_llm=qwen-vl-plus）；其余参数一律默认
  （evidence_k=10 等），不做检索参数实验——沿袭 pilot-v2 边界声明。

## 五、队列构建规则（研究者裁决记录）

- 语料权威源 = Zotero group 6583681 / literature-review(5R4LM6BY) 三集合；
- 已有 note 的条目照常分析（研究者明确：「忽略他有 note 依旧照常生成」）；
- SHA-256 文件级去重：drop 32IL3QY6（保留 2DIGX7WK）、YSVT33CD（保留 6QFXQUNA）；
- 无本地 PDF 排除：7AZF8PYR、HDIGJHQA、RUMMCDNC、YCNDU995；
- YMBIMQR9（White 2008 专著）保留但排序最后；
- **Zotero 零写入**：本轮一切产物只落本地 results/；
- metadata（题名/作者/年份/DOI/venue/publisher/itemType）直接取 Zotero 条目字段写入
  record 元数据块——满足 guide L9 的 metadata 要求且零虚构。

## 六、record schema（直接升级，无适配层）

`<KEY>.record.json`：schema="reviewBricks-analysis-pass4-v2"，含 metadata（Zotero 来源）、
passes{passN: {pool_path, extraction_path, seconds, resumed}}、gate{choice, evidence_quote,
location, probe_used}、backfill[{concept, path}]、sections（各 Extraction 输出的 H2 切分）、
citation_audit、provenance（模型指纹/prompts_sha256/timings）、warnings。
modules/relations 保持空数组（仓库铁律：不自动推断 roadmap 归属）。

## 七、并发与无人值守

batch.py：asyncio 信号量并发（默认 4 篇同进程，共享 bge-m3 与 litellm 连接池）、
失败隔离（单篇崩溃不影响队列）、失败自动二扫重试、每阶段 asyncio.wait_for 超时、
manifest/report 原子更新、--max-hours 总闸。断点续跑 = 产物级（存在+meta 匹配+prompt 哈希一致才跳过）。

## 八、v2-dev 偏差登记（提示词优化，2026-08-24）

研究者反思两处提示词缺陷，经授权对 pass4-v2 做最小偏离母本改造（v1 冻结不动）：

1. **元数据重复浪费（问题 2）**
   - 根因：`00_global_rules.md` 原 L7 要求"每次都收集 metadata"，且 GLOBAL 块注入到
     每一次 Extraction/Gate/Backfill 的 user message；更隐蔽的是 `fmt_contexts` 给**每条
     证据**都附 `anchor=<docname pages>` + `source=<完整格式化引用>`，同一篇论文 ×
     evidence_k × 8+ 池次全量重复。
   - 修复：
     - `00_global_rules.md` L7 改为"metadata 由系统在记录头部记录一次，输出不重复；
       仅 PASS 1 在文献定位叙事确需时陈述一次"。
     - `fmt_contexts` 去掉每条目 `source=` 行；新增 `pool_header()` 在合并池头部印一次
       完整 citation + docname；条目保留 `[E##] score | anchor`（anchor 含 docname+页码，
       定位能力不损）。所有调用点（pass 池 / gate probe / pass4 / backfill）均改为
       `pool_header(ctxs) + fmt_contexts(ctxs)`。

2. **prior work 无法查询（问题 1）**
   - 根因：`e1.md` "Relevant prior research" 四字段缺"被引文献身份标识"，模型可泛述
     "先前研究表明 X" 而不点名，记录后无从回查。
   - 修复（经研究者二次澄清，走最简最稳路径）：
     - **直接确定性抽取本文末尾参考文献表的全部 APA 整条**——不依赖 e1 夹注、不做
       脆弱的"夹注→书目"匹配。研究者原话："直接从文章最后的参考文献查整条的 APA"。
     - `runner.py` 新增 `resolve_references(docs)`（无 LLM）：从 `docs.texts` 定位
       References 区 → 按 `[N]`/`N.`/`N)` 切分条目 → `_clean_bib_entry` 修复 PDF 抽取
       导致的连字符换行断词（Brid- gette→Bridgette）与多余空白 → 产出 `e1.references.md`
       （全部 APA 条目表，含题名）+ 写入 `structured_record.md` 末节
       "REFERENCES — FULL APA (deterministic extraction)" + record.json
       `resolved_references_md_path`。
     - `e1.md` 仍保留 **Cited reference** 字段（要求原样摘录文中夹注身份），作为 e1 自身
       的可读性增强；但**可查询性的真正来源是上面的整条 APA 书目**，二者互补不冲突。
     - 研究者明确：title 一定 given、references 表检索要做、这部分"甚至可以用固定脚本做"
       ——故走确定性脚本而非 LLM，零幻觉风险。

3. **续跑影响（诚实披露）**
   - 上述两处提示词改动使 `prompts_sha256` 全变 → 已完成的 14 篇若续跑会被 `ResumeBook`
     判为配置不匹配而**重跑**；未跑的 27+3 篇正好用新提示词，无影响；14 篇旧产物保持
     不动（不重跑即不碰）。此为预期代价，研究者已知情。

## 九、跨 provider 模型路由（2026-08-26，研究者六问裁定）

### 实证前提（推翻初始设想）

- Go 套餐 5 小时限额是 **workspace 账号级共享桶**：六个模型家族返回同一递减 retry-after；
  litellm 异常消息明示 "5-hour usage limit reached. Resets in Xhr Ymin"，headers 为空。
  → "限额时换模型绕行"不成立；路由目标改为**省桶 + 跨 provider 故障转移**。
- Go 网关提供付费溢出选项（enable usage from balance），是否开通由研究者决定。

### 架构（model_router.py）

```
角色链：retrieve [go/deepseek-v4-flash → dashscope/qwen-turbo]
        extract  [go/qwen3.7-plus   → dashscope/qwen3.7-plus-2026-05-26]
        vision   [go/deepseek-v4-flash-vision-exp → dashscope/qwen-vl-plus]
论文 = 原子分配单位：整篇单 provider 三角色同源，中途绝不切换。
```

### 研究者裁定记录

| 决策点 | 裁定 |
|---|---|
| 绑定粒度 | 固定配对（retrieve 弱/extract 强，论文内各自不变） |
| 中断处置 | 同模型断点续跑（指纹三元组不变→已完成 pass 复用）；换源才需整篇重跑 |
| 切换信号 | 仅 quota(429/usage limit)与 provider-fatal(denied/欠费/认证) 触发；transient 走既有重试 |
| fatal 语义 | 单 provider 故障→该 provider 冷却 6h 继续批次；**不**全批停摆 |
| VLM | 纳入第三链同样路由 |
| 生效范围 | runner(--provider 强制/auto) 与 batch(probe 预热+cooldown+--wait-reset) 双入口 |

### 实现要点

- meta.json 指纹改三元组 (retrieve_model, extract_model, vlm)；旧单值 meta 视为 fresh。
- preflight 逐链 ping 并**预热冷却状态**（从真实异常解析 "Resets in Xhr Ymin"，
  解析不到时兜底 1800s）；存在三角色全健康的 provider 才 exit 0。
- batch 启动默认 probe；worker 捕 QuotaExhausted/AllProvidersDown → status=cooldown
  （记 provider+reset_epoch）；--wait-reset 使进程休眠至最早重置点继续清队列。
- record.json 新增 models{provider,retrieve,extract,vision}+provenance.router_snapshot；
  Zotero 索引注记追加 retrieve_llm 行（INDEX_FIELDS 不变，旧笔记兼容）。
- gen() num_retries 4→2（429 在账号桶下无意义重试，快速上抛转冷却）。

### 已知限制（研究者待办）

- DashScope 当前 "Access denied / not in good standing"（三模型全拦）→ 充值后仍被拒，
  需研究者核查阿里云账户状态（结算/实名）；未解决前故障转移链为死路，批次将纯 Go 运行。

### 兜底切换：dashscope → deepseek（2026-08-26 晚，研究者裁定）

### 全量 deepseek 执行（2026-08-26 午后，范围纠正后发射）

- **范围纠正（研究者点破的项目级错误）**：真实目标 = 研究者**个人库 users/0** 四分类
  及物性+NLP / LLM-enactment-多模态 / VLM 词汇学习 / On Verbs；此前整夜的 44 篇队列
  属于群库另一语料（otome/companionship/relationship++），17 篇完成全部不命中目标。
- 新构建器 `build_queue_user_collections.py`：模糊匹配分类名 → top items → 子附件解析
  本地 PDF（storage\<attKey>\文件名）→ sha256 首见去重 → excluded[] 显式上报。
  实测：**95 篇入选 / 24 排除**。
- `router_deepseek_full.json`：三角色全 deepseek/deepseek-chat。**vision 为占位**——
  deepseek 平台无视觉模型，moonshot key 实测 Invalid Authentication；扫描版 PDF 的图像
  增强会显式失败（诚实报错），数字文本论文不受影响。后续可换真视觉模型只需改此文件。
- batch.py 新增 --queue；发射走 CIM Win32_Process.Create（句柄脐带禁令执行样本），
  密钥经环境变量继承、不落盘。
- 发射即遇瞬时 429 → 分类器 30min 兜底冷却 → 12:31 自愈开跑（自愈路径实战验证）。

- 实测事件链：dashscope 全链 "Access denied"（充值后仍拒）→ 研究者裁定兜底换 DeepSeek
  并充值 ¥50 → 复测仍 "Insufficient Balance"。
- **关键发现①**：`openai/ox-alpha-free` 不占 workspace 共享桶（Go 全链冷却时独立可用），
  曾验证 OK——双角色方案曾立项后被研究者取消，此事实留档备用。
- **关键发现②**：DeepSeek 的 **App 余额与 API 余额是两本账**；key `...a2d1` 认证通过
  （非 401）但 API 余额为 0，等待研究者核实 platform.deepseek.com「API 充值」入账。
- 链配置变更（CHAIN_CONFIG）：retrieve/extract 兜底 = `deepseek/deepseek-chat`
  （chat 而非 reasoner：结构化提取任务无需推理链，成本与延迟更优）；
  **deepseek 无视觉模型**，vision 兜底暂留 `dashscope/qwen-vl-plus` 占位，
  moonshot 视觉备选未测（研究者中止了该探测）。
- PROVIDER_ORDER 更新为 ["go", "deepseek"]；单测改为注入自定义链，与全局配置解耦（17/17）。

### 附：run_deepseek_batch.cmd 编码缺陷（Momus 审查前自纠）

- 初版以 ASCII 写入含中文路径的 cd /d 行 → 路径乱码为 ??，CIM 发射时 cd 必失败。
- 已修复：UTF-8 无 BOM 重写并回写正确中文路径。教训：生成含非 ASCII 路径的 .cmd
  一律 UTF-8 无 BOM（或 OEM/GBK 视控制台代码页），写后必须回读验证关键字段。
