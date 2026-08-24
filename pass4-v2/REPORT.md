# pass4-v1 夜间批量运行报告（晨报）

生成时间：2026-08-24 09:05 (Asia/Shanghai)

## 结论速览

- **44 篇目标：**14 篇完成（含试点篇 DJICIQIL）✅** / 27 篇被欠费阻断 ⛔ / 3 篇待重跑 🔧（依赖已修复，仅等 API）**
- 阻断根因：**DashScope 账户欠费（overdue payment）**——批量完成第 14 篇后 API 全面拒绝服务
- 恢复条件全部就绪：产物级断点续跑有效；**18 篇已存索引检查点**（续跑每篇省约 8 分钟）
- 你只需：给阿里云百炼账户充值 → 跑下面一条命令 → 约 3–4 小时全部完成

## 恢复命令（充值后执行）

```powershell
cd "D:\task\科研\HCI+\litereature review\paperqa2\integration-tests\pass4-v1"
powershell -ExecutionPolicy Bypass -File launch_batch.ps1 4 8
```

- 自动跳过已完成篇；欠费失败篇自动重试；AES 加密 PDF 的 cryptography 50.0.0 已装好
- 充值后可先验证：`D:\anaconda\miniconda3\envs\paperqa\python.exe runner.py --preflight`（5 项全 PASS 再发射）

## 夜间时间线

- 22:28–22:53 试点篇 DJICIQIL 干净端到端验证通过（金样本，0 警告，3 概念回填完整）
- 22:56 批量发射（并发 4）
- ~23:00–00:53 完成 13 篇后 DashScope 余额耗尽，其余条目快速失败
- 08:59 复盘：cryptography 已装；preflight 确认 LLM/VLM 探针仍因欠费 FAIL

## 已完成 13 篇

| Key | Title | Seconds |
|---|---|---|
|---|---|---|
| 86CXZH5B | (PDF) Trans-Parasocial Relation Between Influencers  | 2247.9 |
| 8LSDKF8A | A Game of Love for Women: Social Support in Otome Ga | 1973.3 |
| AQPKMIGX | A Grounded Theory Study of Player Identification and | 1379.3 |
| E23L3VHP | Avatar and Real Me: Identity Anxiety of Chinese Mobi | 893.6 |
| FXB2NCHM | Bridging AI and Humanitarianism: An HCI-Informed Fra | 2158.0 |
| J37889TF | Collective Day-Dreaming and the Purchase of Parasoci | 964.8 |
| JS7DDANC | Exploring Influencer Burnout through Trans-Parasocia | 861.4 |
| UHKIUAAB | Embodied Character Companionship: Exploring the Emot | 1950.0 |
| USUVR386 | Artificial Intelligence and the Psychology of Human  | 1886.2 |
| UUTBWC67 | Collective Creation of Intimacy: Exploring the Cospl | 1114.2 |
| VZCYMTY5 | Digital Companionship: Overlapping Uses of AI Compan | 1901.5 |
| XAD76IGP | Artificial Intimacy: Exploring Normativity and Perso | 2552.8 |
| XM7ZLXBT | Does Care Lead to Bonds? Exploring the Relationship  | 2055.0 |

## 被欠费阻断的 27 篇（索引检查点已保存的部分自动复用）

| Key | Title | Error |
|---|---|---|
|---|---|---|
| 2DIGX7WK | Fictional Failures and Real-World Lessons: Ethical S | litellm.BadRequestError: DashscopeException - Access denied, |
| 6QFXQUNA | Relational AI: Facilitating Intergroup Cooperation w | litellm.BadRequestError: DashscopeException - Access denied, |
| AMYIMZZN | From Parasocial Interaction to Relationship: A Study | litellm.BadRequestError: DashscopeException - Access denied, |
| BFENLUNZ | What makes virtual intimacy...intimate? Understandin | litellm.BadRequestError: DashscopeException - Access denied, |
| BKQ7F9KB | “Tinged with Heartbreak”: An Ethnographic Account of | litellm.BadRequestError: DashscopeException - Access denied, |
| BMPCDAQJ | Parasocial Romance: A Social Exchange Perspective | litellm.BadRequestError: DashscopeException - Access denied, |
| DBBMXVEY | Movement Societies and Digital Protest: Fan Activism | litellm.BadRequestError: DashscopeException - Access denied, |
| DCFNEKN4 | Relational Dissonance in Human-AI Interactions: The  | litellm.BadRequestError: DashscopeException - Access denied, |
| DJVBG23F | “Control your emotions, Potter”: An Analysis of Grie | litellm.BadRequestError: DashscopeException - Access denied, |
| FYD6PEBJ | Exploring relationship development with social chatb | litellm.BadRequestError: DashscopeException - Access denied, |
| G89R825J | Revisiting Computer-Mediated Intimacy | litellm.BadRequestError: DashscopeException - Access denied, |
| GMW4LBQU | The lonely raccoon at the ball: designing for intima | litellm.BadRequestError: DashscopeException - Access denied, |
| HXKRUPYI | The Video Game Experience as “True” Identification:  | litellm.BadRequestError: DashscopeException - Access denied, |
| KGJ828E4 | The impact of game character identification on otome | litellm.BadRequestError: DashscopeException - Access denied, |
| LXWBZ3WM | Growing the Otome Game Market: Fan Labor and Otome G | litellm.BadRequestError: DashscopeException - Access denied, |
| MJUWZITR | Seeking Love and Companionship through Streaming: Un | litellm.BadRequestError: DashscopeException - Access denied, |
| P6XQPYEA | Trans-Parasocial Relation Dynamics: Decoding the Eff | litellm.BadRequestError: DashscopeException - Access denied, |
| REGHBDBJ | What is Love？Virtual Intimacy and Real Power in Otom | litellm.BadRequestError: DashscopeException - Access denied, |
| SKP4YTPQ | Fostering Intrinsic Motivation through Avatar Identi | litellm.BadRequestError: DashscopeException - Access denied, |
| UNEWQELR | Negotiating Digital Identities with AI Companions: M | litellm.BadRequestError: DashscopeException - Access denied, |
| V4AUKFVF | Regulating Artificial Intimacy: From Locks and Block | litellm.BadRequestError: DashscopeException - Access denied, |
| V8NWC7ZT | Virtual Intimacy, this little something between us:  | litellm.BadRequestError: DashscopeException - Access denied, |
| VBBQJZAB | Positively playful: when videogames lead to player w | litellm.BadRequestError: DashscopeException - Access denied, |
| VBUBG9BU | Restoration, Exploration and Transformation: How You | litellm.BadRequestError: DashscopeException - Access denied, |
| XVC52ZGY | (PDF) Parasocial interactions and relationships | litellm.BadRequestError: DashscopeException - Access denied, |
| XZFSJRYD | Para-Romantic Love and Para-Friendships: Development | litellm.BadRequestError: DashscopeException - Access denied, |
| YMBIMQR9 | Identity and control: how social formations emerge | litellm.BadRequestError: DashscopeException - Access denied, |

## AES 加密 PDF 3 篇（依赖已装，仅等 API 恢复）

| Key | Title | Error |
|---|---|---|
|---|---|---|
| 55BE86U9 | 女性向游戏玩家的身份认同研究——以《恋与深空》为例_刘美舫 | cryptography>=3.1 is required for AES algorithm |
| 8NQCIM4T | 编码_解码视域下的虚拟亲密关系研究——以乙女游戏《恋与深空》为例_李果庆 | cryptography>=3.1 is required for AES algorithm |
| MZ96YDPY | 乙女游戏中的虚拟亲密关系建构与玩家主体性实践——基于准社会交往理论的经验研究_钟琦 | cryptography>=3.1 is required for AES algorithm |

## 工程说明

- 提示词零改写：16 个文件逐字切分自 important-guide-for-paperQA2.md（映射见 GLUE.md）
- 架构：每 Pass = Retrieval A/B（aget_evidence 只积累证据）→ 合并池 → 单次 Extraction；
  PASS 4 Gate A/B/C 分流（C 探针后重判）；概念回填上限 5；record schema v2 直接升级
- Zotero 零写入；所有产物在 pass4-v1/results/<KEY>/
- 成本参考：DJICIQIL 全管线约 7.7 万 tokens（不含索引解析）；账单以百炼控制台为准

