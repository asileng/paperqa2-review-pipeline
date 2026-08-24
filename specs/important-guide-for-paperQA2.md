接

Use only the evidence retrieved from the current paper. Do not use external knowledge.

Your task is extraction and faithful compression, not research synthesis.

You will always deliver your output in Chinese.

You will always gather the meta data of the paper you are dealing with. metadata incudes: The topic, publication institution(which conference or journal), the author's name,  the year it was published.

Rules:

1. Only report information supported by the retrieved evidence.
2. Do not evaluate whether the paper is important, convincing, novel, rigorous, useful, or worth citing.
3. Do not infer research implications, design recommendations, future research questions, or meanings for the user's own project.
4. Preserve the authors' epistemic tone and attribution.
   Distinguish, when relevant:
   - the authors propose / conceptualize / argue
   - the authors find / observe / report
   - the evidence suggests / indicates
   - the authors speculate / hypothesize
   - the authors cite prior work as evidence
5. Never convert a theoretical proposition into an empirical finding.
6. Never convert an intended effect into an observed effect.
7. Never treat a method, finding, or experiment cited from prior work as something conducted in the current paper.
8. "未找到明确证据" means only:
   "the evidence retrieved in this pass does not provide explicit support."
   It must never be rewritten as:
   "the paper does not contain this information."
9. For every important extracted fact, output three independent elements:
   - Claim: a concise factual compression
   - Evidence Quote: the relevant original wording
   - Location: the PaperQA2 source anchor / page / section / table / figure
10. Evidence Quote must remain in the original wording. Do not paraphrase it.
11. Keep Claim concise and factual. Do not turn the output into literature-review prose.
12. If several distinct claims or gaps exist, preserve them separately rather than merging them into one general statement.
13. Retrieval keywords or rhetorical phrases are hints only. Their presence is not required for identifying evidence.
14. Do not force a field to be filled when retrieved evidence is insufficient.



接下来我们的文献分析将分为四个Pass。

第一个pass中，我们主要关心Research Positon & Gap。相关信息将主要出现在Related work，Introduction，literature review，previews studies之类的章节，主要阐述作者研究的rationale，exigence。不要在这里检索最终 results。



首选你需要Retrieve：

Retrieve evidence showing how the authors describe the state and limitations of prior research most directly related to the current paper.

Focus on:

- what prior studies, theories, approaches, or explanations have already addressed;
- what the authors say remains missing, limited, unclear, unresolved, conceptually ambiguous, methodologically inadequate, or insufficiently studied;
- explicit contrasts between existing research and the problem addressed by the present paper.

Prioritize evidence from the Introduction, Background, Related Work, or Literature Review when available, but do not restrict retrieval by section name.

Possible lexical cues such as "however", "little is known", "remains unclear", "limited", "lack", "previous studies", "prior work", "existing approaches", and "fail to" are retrieval hints only, not requirements.



随后你需要Retrieve：

Retrieve evidence showing what research problem, question, aim, purpose, or objective the authors say the present paper addresses, and how they position their own work as a response to the limitations of prior research.

Focus on explicit author framing such as:

- research question / aim / purpose;
- "we address", "we examine", "we propose", "we extend", "we distinguish", "we investigate";
- statements describing how the present work differs from, extends, refines, challenges, integrates, or applies prior work.

Retrieve author positioning, not the paper's later results or conclusions.

**把 1A + 1B evidence 合并后，再运行下面的 extraction prompt。**

Using only the evidence retrieved for PASS 1, reconstruct the authors' research positioning.

Do not independently decide what the "real" gap is. Summarize the problem, deficiency, importance, and relationship to prior work only as attributed by the authors.

Output:

## Research context

Extract and concisely summarize only the research context explicitly constructed by the authors in the retrieved evidence. Focus on background statements that the authors themselves use to introduce, frame, or motivate the research problem addressed in the present paper. **Do not supplement the authors' framing with external knowledge.**

## Relevant prior research

Extract prior research only when the authors explicitly use it to construct the research problem, establish a gap, motivate the present study, or position the present study relative to existing work.

For each important item or line of work:

- **Prior research / position**: what the cited work is described as studying, proposing, finding, or assuming;Evidence Quote
- **Role in the authors' argument**: how the authors explicitly use this prior work in constructing the present research problem or positioning;
- **Evidence Quote**: the original wording;
- **Location**: source anchor / page / section.

## Research gaps

Identify each distinct gap separately.

For each gap output:

### Gap [n]

**Existing state**
What do the authors say prior research has already done or assumed?

**Deficiency**
What exactly do the authors say is missing, limited, unresolved, unclear, conceptually confused, methodologically inadequate, or insufficient?

**Author tone**
Preserve how strongly the authors frame the deficiency, e.g.:

- has not addressed
- remains unclear
- is limited
- may not explain
- lacks conceptual clarity

Do not strengthen or weaken the wording.

** Significance and Exigence*

Extract only what the authors explicitly state about:

- why this gap matters;
- what theoretical, empirical, methodological, practical, or conceptual consequence follows from the gap;
- what limitation, unresolved problem, or research need the gap creates;
- why the authors present further investigation as necessary or warranted.
- Do not independently explain why the gap is important or why it should be addressed.
  If the retrieved evidence does not explicitly state the significance or exigence of the gap, write:
  "本轮检索证据中未找到明确证据。"

**Evidence Quote**
Verbatim original evidence.

**Location**
Source anchor / page / section.

Do not merge separate theoretical, empirical, methodological, contextual, or conceptual gaps merely for brevity.

#### Research Questions

Extract every research question explicitly stated by the authors.

Preserve the authors' original numbering, wording, and hierarchy whenever available.

Do not merge multiple research questions into a single generalized question.
Do not infer a research question that the authors themselves do not explicitly formulate.

### Research Question 1

**The Author's Original Statement**
Quote the research question as explicitly formulated by the authors.

**Relevant Surrounding Statements**
Preserve short statements immediately surrounding the RQ when they explicitly explain:

- why this question is asked;
- which gap or unresolved issue it addresses;
- how the authors frame the question.
  Do not add contextual explanation that is not explicitly present in the retrieved evidence.

**Location**
Provide the source anchor / page / section.

### Research Question 2

**The Author's Original Statement**
......





PASS2 - # PASS 2 — Methodology / Material / Data & Evidence

## # Retrieval 2A — Methodology / Research Design

检索本文**实际采用的整体研究设计与方法论结构**。重点不是具体的数据内容或实施参数，而是恢复作者如何设计研究、组织方法，以及如何说明这些方法选择。

## 1. Research Design and Methodological Components

识别本文实际采用的主要方法及其在研究中的功能，包括：

- 数据如何被获得或引出；
- 研究对象如何被测量、观察、编码或表征；
- 数据最终通过什么分析方法被处理。

例如，thematic analysis,深度访谈，民族志，量表等。许多时候，质性研究的方法展开依赖某一个明确的操作框架，如果能够找到，请明确引用出这个操作框架。

不需要展开具体 sample、coding category、measurement item、variable value 或模型参数；重点是识别这些方法作为 research design 的组成部分。

## 2. Methodological Organization / Framework

检索这些方法之间是否形成明确的整体结构。

重点关注：

- 不同方法之间的先后、组合或分工关系；
- 作者是否将研究明确组织为若干阶段、分析层次或 methodological framework；
- 不同方法是否分别承担数据获取、测量、编码、建模或解释等不同功能。

如果作者有明确的 framework 或 workflow，尽量保留作者自己的组织方式，而不是重新概括一套新的结构。



## 3. Methodological Choice

同时寻找作者明确讨论**为什么采用、修改、保留或放弃某种方法**的文本。

这包括正向的方法选择，也包括负向的方法选择。

例如：

> “We use X because it allows us to capture…”

> “X has been validated in previous research…”

> “We adapt X framework for the present context…”

也包括：

> “We did not use X because…”

> “Existing approaches based on X are unsuitable for…”

> “Unlike previous studies using X, we…”

这些 passage 都属于本轮需要召回的 methodology evidence。

本轮停留在 **research design / methodological architecture** 层面。

具体的 material、sample、data content、operational details、coding scheme、measurement specification、model setting 和 numerical results 留给 Retrieval 2B。





## Retrieval 2B — Material / Data

检索本文实际处理的研究材料，以及由这些材料产生并进入分析的数据。

重点检索：

### Material

- participants / sample；

- corpus；

- interviews；

- documents；

- posts；

- videos / images；

- stimuli；

- datasets；

- artifacts / systems；

- experimental materials；

- 其他实际研究对象。

同时检索：

- **What**：材料具体是什么；

- **Source**：材料来自哪里；

- **Scale**：规模、样本量或数量；

- **When**：采集或研究发生时间；

- **Where**：地点、平台或研究环境；

- **Selection**：sampling / recruitment / inclusion / exclusion；

- **Why**：作者明确说明的材料选择理由。

### Data

检索从 Material 中实际产生并进入分析的：

- observations；

- measurements；

- responses；

- transcripts；

- annotations；

- coded units；

- variables；

- behavioral records；

- extracted features；

- model outputs；

- 其他实际分析数据。

同时检索：

- Material 如何转化为 Data；

- preprocessing；

- cleaning；

- transcription；

- coding；

- annotation；

- measurement；

- feature extraction；

- aggregation；

- 最终 analysis。

本轮主要定位研究实施和 evidence construction，不以检索最终 thesis 或主要 findings 为目标。

---

# Extraction 2 — Methodology / Material / Data & Evidence

只依据 PASS 2 retrieved evidence 回答。

你的任务是**忠实恢复作者实际怎样开展研究、怎样获得和处理材料与数据，以及这些过程形成了什么 evidence**。

不要评价：

- 方法是否优秀；

- 方法是否合理；

- 方法是否真正适合 RQ；

- 数据是否充分；

- evidence 是否足以证明 claim。

关于方法选择的意义、价值或优势，只允许总结**作者自己明确陈述的 rationale**。

---

## 1. Research Design / Study Structure

首先保留论文实际的研究结构。

例如：

- theoretical / conceptual study；

- experiment；

- survey；

- interview；

- corpus study；

- computational study；

- design study；

- mixed methods。

如果包含多个研究，保持作者原始结构：

### 

不要为了简化而合并作者明确区分的研究。

对于每个研究：

- **Research Design**

- **Evidence Quote**

- **Location**

---

## 2. Methodology and Complete Procedure

按照作者实际实施的顺序，尽可能完整地恢复研究流程。

重点包括：

- 材料 / participant 获取；

- sampling / recruitment；

- experimental manipulation；

- task / procedure；

- measurement；

- coding / annotation；

- preprocessing；

- analysis。

不要只列出方法名称。

对于每一个主要步骤：

- **Method / Procedure Step**

- **What the Authors Actually Did**

- **Evidence Quote**

- **Location**

如果某一步只是前人研究做过、本文没有实施，不得列入本文 procedure。

---

## 3. Methodological Source / Reference

如果本文实际使用的方法、framework、measure、scale、coding scheme 或 analysis 明确来源于 prior work，提取其方法论来源。

对于每一项：

- **Method / Framework / Measure**

- **Source Author(s)**

- **Year**

- **Source / Title**：仅在论文明确提供时填写

- **Relationship to the Present Study**：
  
  - adopted
  
  - adapted
  
  - modified
  
  - extended
  
  - replicated
  
  - based on

- **Evidence Quote**

- **Location**





不得根据外部知识补全论文没有给出的来源信息。

---

## 4. Author-Stated Methodological Rationale

提取作者**明确说明**为什么采用某个方法、measurement、material selection 或 analytic strategy。

可能包括作者声称该选择能够：

- 捕捉某种现象；

- 测量某个 construct；

- 克服某种既有方法限制；

- 区分某些情况；

- 提供某种特定类型的 evidence。

对于每一项：

- **Methodological Choice**

- **The Author's Stated Rationale**

- **Author Tone**

- **Evidence Quote**

- **Location**

只总结作者自己的归因。

不得自行解释：

> “这个方法之所以适合，是因为……”

除非作者明确这样说明。

---

## 5. Material

提取作者实际处理的研究材料。

根据 retrieved evidence，尽可能保留：

- **What**

- **Source**

- **Scale**

- **When**

- **Where / Platform**

- **Sampling / Recruitment**

- **Inclusion / Exclusion**

- **Author-Stated Selection Rationale**

对于重要事实分别提供：

- **Claim**

- **Evidence Quote**

- **Location**

不要因为某项信息在当前 evidence 中没有出现，就声称全文没有该信息。

---

## 6. Data

严格区分 **Material** 与 **Data**：

- **Material**：研究者最初收集、观察、操纵或处理的对象。

- **Data**：从这些对象中产生、测量、转录、编码、标注、计算或提取，并实际进入分析的信息。

提取：

### Data Type

实际进入分析的数据是什么？

### Unit of Analysis

论文的分析单位是什么？

### Data Generation

Material 如何转化成 Data？

### Data Processing

是否进行了：

- preprocessing；

- cleaning；

- transcription；

- segmentation；

- coding；

- annotation；

- feature extraction；

- aggregation。

### Measurement

实际测量了什么？使用了什么 measure / variable / scale / coding category？

### Analysis

最终使用什么方法分析这些 Data？

对于每项重要信息：

- **Claim**

- **Evidence Quote**

- **Location**

---

## 7. RQ → Methodological Operationalization

使用 PASS 1 已经提取出的 Research Question(s) 作为参照。

这一部分不重新解释或总结 RQ，而是根据 PASS 2 的方法证据，说明作者**实际上如何把每一个 RQ 转化为研究设计**。

如果存在：

### Research Question 1

**The Author's Original Statement**  
沿用 PASS 1 提取的原始 RQ，不重新改写。

**Operationalization Through Methodology**  
根据本文明确的方法信息提取：

- 使用哪个 Study / Experiment / Analysis 回答该 RQ；

- 使用什么 Material / participants / corpus；

- 涉及哪些 variables / measures / categories / observations；

- 使用什么 comparison / procedure；

- 使用什么 analysis。

**Evidence Quote**  
支持上述 methodological operationalization 的方法原文。

**Location**

### Research Question 2

同上。

### Research Question 3

同上。

如果作者没有明确建立某个 RQ 与具体方法之间的对应关系，但可以确认某项 Study / Analysis 用于回答该 RQ，只在 retrieved evidence 足够明确时进行最小程度的对应。

不得仅根据“方法看起来可以回答这个 RQ”而建立映射。

若本轮 evidence 无法支持某个 RQ 的 operationalization：

> 本轮检索证据中未找到明确证据。

---

## 8. Evidence Produced

最后简洁提取上述研究过程实际产生了哪些**证据形式**。

例如：

- statistical estimates / comparisons；

- participant responses；

- behavioral observations；

- qualitative themes；

- interview excerpts；

- corpus patterns；

- computational metrics；

- model outputs；

- theoretical comparison / conceptual reasoning。

这一部分只回答：

> **本文实际产生或使用了什么 evidence。**

不要在这一轮详细总结 evidence 得出了什么主要结论；主要 findings 和 thesis 留给 PASS 3。

对于每类 Evidence：

- **Evidence Type**

- **What It Consists Of**

- **Source / How It Was Produced**

- **Evidence Quote**

- **Location**

如果是理论 / 概念论文，也不要强行填写 empirical data。应根据 evidence 忠实记录作者实际使用的：

- theoretical reasoning；

- conceptual comparison；

- synthesis of prior literature；

并严格区分这些 evidence 与本文新产生的 empirical evidence。



# PASS 3 — Thesis / Main Claims / Results

## Retrieval 3A — Thesis / Main Argument

检索能够直接体现本文 **central thesis、main argument 和主要 claims** 的 evidence。

重点寻找：

- 作者如何明确概括本文最核心的主张；

- 作者提出、论证、概念化、区分或重新定义了什么；

- 作者如何回答前文提出的 Research Question / Aim；

- 作者明确声称本文相对于 prior work 做出了什么改变、扩展、修正或区别；

- 作者在 Abstract、Discussion、Conclusion 或核心理论/分析部分对全文主要论证的集中表述。

特别保留作者原始的 epistemic tone，例如：

- propose / argue / conceptualize；

- find / observe / report；

- suggest / indicate；

- demonstrate / show；

- speculate / hypothesize。

不要把 theoretical proposition、author interpretation 和 empirical finding 混为同一种 claim。

本轮重点寻找能够组织全文主要论证的 claims，不以召回所有局部 findings 为目标。

---

## Retrieval 3B — Main Results / Findings

检索作者用于回答 Research Question、支撑主要 claims 或形成论文结论的核心 results / findings evidence。

根据论文实际研究类型，重点召回：

- quantitative results 及其具体数值、比较、统计信息和表 / 图位置；

- qualitative themes、patterns、representative quotations 或 observations；

- computational / model-based results；

- theoretical propositions、conceptual relationships 或 distinctions；

- 作者对这些结果所作的明确 interpretation。

优先召回与 central thesis 和主要 Research Question 直接相关的 findings，而不是所有次要结果。

如果论文属于 theoretical / conceptual research，不要求存在 empirical Results section；应召回作者实际用于建立其 theoretical claims 的 propositions、conceptual distinctions 和 reasoning。

---

# Extraction 3 — Thesis / Main Claims / Results

只依据 PASS 3 retrieved evidence 进行提取。

本轮目标是忠实压缩：

> **作者最终提出什么 thesis，其主要 claims 是什么，以及论文实际得到什么 results / findings。**

不得评价：

- 哪个 claim 最有价值；

- contribution 是否真正创新；

- results 是否可信；

- evidence 是否足以证明 thesis；

- 这篇论文应该如何写入 literature review。

必须保留作者原有的 claim strength 和 attribution。

所有重要信息尽可能同时提供：

- **Claim / Extracted Information**

- **Evidence Quote**：直接支持该信息的原文

- **Location**：source anchor / page / section / table / figure

不得使用外部知识补全缺失信息。

---

## 1. Central Thesis

提取能够最集中表达全文核心论证的 central thesis。

优先依据作者自己对全文主张的明确概括，而不是由模型根据多个 findings 重新创造一个更高层次的 thesis。

输出：

**Central Thesis**  
对作者核心主张的忠实压缩。

**Author Tone / Claim Status**  
保留作者究竟是在：

- proposing；

- arguing；

- conceptualizing；

- finding；

- suggesting；

- demonstrating；

- hypothesizing；  
  或以其他方式提出该主张。

**The Author's Original Statement**  
尽可能保留作者直接表达 central thesis 的原始 statement。

**Evidence Quote**

**Location**

如果 retrieved evidence 中存在多个互补但无法安全合并的核心 thesis statement，应分别保留，而不是强行压缩成一个新的总命题。

---

## 2. Main Claims

提取承担论文主要论证功能、或直接回应 Research Question / Aim 的主要 claims。

对于每个主要 Claim：

### Claim [n]

**Claim**  
作者具体提出了什么？

**Claim Status / Author Tone**  
例如：

- theoretical proposition；

- conceptual claim；

- empirical finding；

- qualitative finding；

- methodological claim；

- design-related claim。

同时保留作者使用的 epistemic strength。

**Relation to Research Question / Aim**  
如果作者明确说明该 claim 回答某个 RQ / Aim，保留这种对应关系。

不得仅因为内容看起来相关就自行建立对应。

**Evidence Quote**

**Location**

不要为了数量而列出 minor claims。

---

## 3. Results / Findings

根据论文实际研究类型提取主要 results。

### Quantitative Results

对于每个直接服务于主要 claim 或 RQ 的重要结果，类型化保留：

- **Variable / Outcome**

- **Comparison / Condition**

- **Direction**

- **Statistic**

- **Exact Value**

- **p-value / Confidence Interval / Effect Size**：如论文报告

- **Table / Figure**

- **Author's Interpretation**：仅限作者明确提供

- **Evidence Quote**

- **Location**

凡论文提供具体数字时，不得只压缩成“显著提高”“效果更强”“存在差异”等模糊描述。

---

### Qualitative Results

对于每个主要 qualitative finding：

- **Theme / Pattern / Finding**

- **What the Authors Report**

- **Representative Evidence**：如 quotation、observation 或其他原始材料

- **Author's Interpretation**：仅限作者明确提供

- **Evidence Quote**

- **Location**

保持：

> participant / material evidence  
> ≠ 作者 interpretation  
> ≠ 模型自己的 interpretation

三者之间的区别。

---

### Theoretical / Conceptual Findings

如果本文主要为 theoretical / conceptual research，则提取：

- **Proposition / Claim**

- **涉及的核心概念**

- **作者明确提出的概念关系或区别**

- **作者用于建立该 proposition 的 reasoning**

- **Evidence Quote**

- **Location**

不得因为没有 empirical Results section 就写成“本文没有主要 findings”。

---

## 4. Claimed Contribution

只提取作者自己明确声称的 contribution。

例如作者明确表示本文：

- 提出新的 conceptualization；

- 扩展某个 theory；

- 提供新的 empirical evidence；

- 修改已有 explanation；

- 提出新的 framework / method / design。

对于每项：

**Claimed Contribution**

**Author's Original Statement / Tone**

**Evidence Quote**

**Location**

不得由模型独立判断：

> “这是本文最大的创新。”

---

## 5. Relation to Prior Work

提取作者如何明确描述其 central thesis / main claims 与 prior work 的关系。

重点保留作者自己建立的：

- extension；

- refinement；

- distinction；

- contradiction；

- integration；

- reconceptualization；

- application；

- empirical support / challenge。

对于每一项：

**Present-Paper Position**

**Prior-Work Position**

**Relationship as Stated by the Authors**

**Author Tone**

**Evidence Quote**

**Location**

不得使用外部知识比较本文与 prior work。

---

## 6. Core Concepts for Definition Backfill

仅列出在本轮 evidence 中**直接参与 Central Thesis 或 Main Claims** 的关键概念。

不要在本轮重新定义它们，也不要列出所有出现频繁的术语。

对于每个 concept，仅记录：

- **Concept**

- **Role in the Thesis / Claim**

- **Evidence Quote**

- **Location**

这些 concept 将用于后续单独的 Definition retrieval。

---

如果某项在本轮 retrieved evidence 中没有明确支持，写：

> **本轮检索证据中未找到明确证据。**

这只表示当前 PASS 3 evidence 中没有找到明确支持，不得据此声称论文全文不存在该信息。



# PASS 4 Gate — Design Presence

根据目前已经获得的论文信息，判断本文是否包含作者自己实际提出、设计、实现、配置或系统性构建的 design。

这里的 design 可以包括：

- system / artifact / interface / prototype
- intervention
- interaction mechanism
- explicit design framework or design strategy

只回答：

A. YES — 存在作者自己的 design，需要继续执行 PASS 4
B. NO — 当前 evidence 没有显示作者自己的 design，不执行 PASS 4
C. UNCERTAIN — 当前 evidence 不足，需要进行一次轻量 retrieval 后再判断

判断依据必须来自论文 evidence，不得因为论文“可能具有设计启示”而选择 YES。

输出：

- Choice: A / B / C
- Evidence Quote
- Location



# PASS 4 — Design & Intended Effect

## Retrieval 4A — Design / Mechanism / Intended Effect

检索能够说明作者**实际设计、构造、实现、配置或明确提出了什么，以及这些设计试图产生什么效果**的 evidence。

重点寻找：

- 作者实际创建或提出的 system、artifact、interface、prototype、intervention、interaction mechanism 或其他 design object；

- 作者做出的主要 design choices；

- 不同 design components 之间明确的组织或作用关系；

- 作者明确说明某个 design choice 希望实现什么 intended effect、user experience、interaction outcome 或 behavioral outcome；

- 作者明确提供的 design rationale，包括其引用的 theory、prior work、formative findings 或其他设计依据。

例如，相关 evidence 可能表现为：

> “We designed X to enable users to…”

> “The system provides Y in order to…”

> “Based on prior findings about X, we introduced Y…”

> “This feature was intended to reduce / support / encourage…”

这些例子只用于说明应召回的 evidence 类型，不要求论文必须使用这些具体表达。

同时保留能够说明 design boundary 的文本，例如：

- 作者讨论某种可能 design，但本文没有实际实施；

- design 只作为 future work 提出；

- 某种机制来自 prior system / prior design，而不是本文自身设计。

本轮只负责检索作者实际陈述的 design logic，不根据论文 findings 自行生成新的 design implication。

如果论文并非 design-oriented study，也不要强行寻找 design。

---

## Retrieval 4B — Design Evaluation / Observed Effect / Explicit Implication

检索作者如何评价上述 design，以及作者实际观察到什么 effect。

重点寻找：

- design / system / intervention 如何被 evaluated；

- 作者报告的主要 observed effects；

- intended effect 与 observed effect 之间作者明确建立的关系；

- 作者自己明确提出的 design implication、design principle、recommendation 或 guideline；

- 作者明确说明 design 未达到预期、产生 mixed result 或存在 design limitation 的 evidence。

特别保留能够区分以下三种状态的证据：

1. **Intended Effect**  
   作者希望 design 产生什么效果。

2. **Observed Effect**  
   作者实际观察、测量或报告了什么结果。

3. **Author-Stated Design Implication**  
   作者基于研究明确提出什么 design implication。

不得因为某个 design 看起来“应该”产生某种效果，就自行建立这种关系。

不得从 findings 中生成作者没有提出的新 design recommendation。

---

# Extraction 4 — Design & Intended Effect

只依据 PASS 4 retrieved evidence 进行提取。

本轮目标是忠实恢复：

> **作者设计了什么 → 为什么这样设计 → 希望产生什么效果 → 实际观察到了什么 → 作者自己明确提出了什么设计含义。**

本轮不是 design ideation，也不是 research synthesis。

不得：

- 为用户自己的研究生成设计建议；

- 根据 findings 自行推导新的 feature、system 或 interaction mechanism；

- 把作者的 intended effect 写成已经验证的 observed effect；

- 把 prior work 中的 design 写成本文实际设计。

所有重要信息尽可能同时保留：

- **Extracted Information**

- **Evidence Quote**

- **Location**

不得使用外部知识补全缺失内容。

---

## 1. Design Presence and Scope

首先判断 retrieved evidence 是否明确支持本文存在作者自己的：

- design；

- system；

- artifact；

- interface；

- prototype；

- intervention；

- deliberately constructed mechanism。

如果存在，简要说明其范围。

如果本轮 retrieved evidence 中没有明确支持，则写：

> **本轮检索证据中未找到明确证据。**

此时不要为了完成结构而自行生成 design。

对于存在的 design：

**Design Object**  
作者实际设计、构造、实现、配置或明确提出了什么？

**The Author's Original Statement**

**Evidence Quote**

**Location**

---

## 2. Design Choices and Mechanisms

提取构成该 design 的主要 design choices / mechanisms。

只保留真正参与实现作者设计目标的主要部分，不需要机械罗列所有 feature。

对于每一项：

### Design Choice [n]

**Design Choice / Mechanism**  
作者具体做了什么？

**Function in the Design**  
作者如何描述这一 design choice 在整体设计中的作用？

**The Author's Original Statement**

**Evidence Quote**

**Location**

如果作者没有解释 mechanism，不得自行补充。

---

## 3. Intended Effect

对于主要 design choices，提取作者明确希望它们产生的效果。

效果可能涉及：

- behavior；

- interaction；

- experience；

- perception；

- decision；

- engagement；

- performance；

- social process；

- system outcome；

但只使用论文实际表达的内容，不根据这些类别自行补充。

对于每一个 intended effect：

**Design Choice / Mechanism**

**Intended Effect**

**Author Tone**  
保留作者是在：

- aims to；

- is intended to；

- is designed to；

- may support；

- is expected to；  
  或其他强度下提出该效果。

**Evidence Quote**

**Location**

不得把 intended effect 写成事实性 result。

---

## 4. Design Rationale

提取作者明确说明为什么采用这些 design choices。

重点保留作者自己建立的依据，例如：

- theory；

- prior research；

- previous design；

- formative findings；

- user needs identified in the study；

- observed problem；

- methodological or contextual constraint。

对于每一项：

**Design Choice**

**Author-Stated Rationale**

**Basis / Source**  
如果作者明确引用 theory 或 prior work，则记录论文提供的来源信息。

**Author Tone**

**Evidence Quote**

**Location**

这里只提取作者自己的 rationale。

不得自行解释：

> “这个设计之所以有效，是因为……”

除非作者明确这样论述。

---

## 5. Observed / Evaluated Effect

如果作者实际评价了 design，提取其主要 observed effects。

对于每项：

**Evaluated Design / Mechanism**

**Evaluation Context / Method**  
只保留理解结果所需要的简要 evaluation 信息；详细 methodology 已由 PASS 2 负责。

**Observed Effect / Result**

**Author Interpretation**  
只有作者明确提供时才填写。

**Evidence Quote**

**Location**

如果涉及定量结果，尽可能保留：

- variable / outcome；

- comparison / condition；

- direction；

- statistic；

- exact value；

- p-value / CI / effect size；

- table / figure。

如果涉及质性结果，尽可能保留：

- observed pattern；

- participant / user evidence；

- representative quotation；

- 作者明确给出的 interpretation。

必须严格区分：

> **Intended Effect ≠ Observed Effect**

---

## 6. Explicit Design Implications

只提取作者自己明确提出的 design implication、design principle、recommendation 或 guideline。

不得根据 PASS 3 findings 自行生成 implication。

对于每一项：

**Author-Stated Design Implication**

**What Finding / Design It Refers To**  
仅在作者明确建立这种关系时填写。

**Scope / Target**  
作者明确说明该 implication 适用于什么对象、场景或 design context 时填写。

**Author Tone**

**Evidence Quote**

**Location**

如果作者没有明确提出 design implication：

> **本轮检索证据中未找到明确证据。**

不得自行补充。

---

## 7. Design Boundaries

如果 retrieved evidence 中存在重要的 design boundary，保留作者明确说明的范围或限制，例如：

- 某个 design 只是 proposal，尚未实现；

- 某个 mechanism 来自 prior work 而非本文；

- 某项 feature 只被讨论但没有实施；

- 某个 intended effect 尚未被 evaluation；

- 作者明确限制 design 的适用范围。

对于每项：

**Boundary / Status**

**The Author's Original Statement**

**Evidence Quote**

**Location**

不得根据“没有找到 evaluation”自行写成“该 design 未被验证”；只有 retrieved evidence 明确支持时才能做这种否定判断。

---

如果任何信息在本轮 retrieved evidence 中没有明确支持，写：

> **本轮检索证据中未找到明确证据。**

这只意味着 PASS 4 当前 evidence 中没有明确支持，不得据此声称论文全文不存在该信息。





具体的安排：

PDF
↓
PaperQA2 建索引

↓
Retrieval 1A
Retrieval 1B
→ 合并 evidence
→ Extraction 1

↓
Retrieval 2A
Retrieval 2B
→ 合并 evidence
→ Extraction 2

↓
Retrieval 3A
Retrieval 3B
→ 合并 evidence
→ Extraction 3

↓
Design gate
→ yes: Retrieval 4A + 4B → Extraction 4
→ no: skip

↓
Concept backfill
→ 针对选中的核心概念逐个 retrieval
→ definition extraction

↓

输出 structured paper record



PaperQA2 本身的标准流程就是 `search → gather evidence → generate answer`；其中 Gather Evidence 会针对**当前 query**做 embedding、top-k chunk retrieval、query-conditioned summary 和 relevance reranking。官方也明确提到，agent 可以用不同措辞多次 gather evidence，再统一生成答案。

所以你前面拆 A/B 的理解是对的。

---

## 我建议你的最终结构

不是：

```
PASS 1 → PaperQA ask()PASS 2 → PaperQA ask()PASS 3 → PaperQA ask()
```

而是：

```
                    ┌─ Retrieval 1A ─┐Paper PDF / Index ──┤                 ├─ Evidence Pool 1 ── Extraction 1                    └─ Retrieval 1B ─┘                    ┌─ Retrieval 2A ─┐                    │                │PaperQA2 Index ─────┤                ├─ Evidence Pool 2 ── Extraction 2                    └─ Retrieval 2B ─┘                    ┌─ Retrieval 3A ─┐                    │                │                    └─ Retrieval 3B ─┘                             ↓                     Evidence Pool 3                             ↓                       Extraction 3                             ↓                      Design Gate                     /      |       \                   YES   UNCERTAIN    NO                    |       |          |               Retrieval   probe       skip                 4A/4B      |                    \_______/                        ↓                   Extraction 4                             ↓            Concept-definition backfill               only for selected concepts
```

### 关键：Retrieval 和 Extraction 应该是两个真正不同的程序阶段

PaperQA2 的 `Docs.aget_evidence()` 本身就很适合承担你的 **Retrieval**。它负责检索 evidence，而 `Docs.aquery()` 则进一步执行 answer generation。当前 API 明确提供了 `aget_evidence` / `aquery` 两层接口。

因此，我反而**不建议每个 Retrieval A/B 都完整调用一次 `aquery()`**。

因为那样会变成：

```
Retrieval A→ retrieve→ summarize→ generate useless answer ARetrieval B→ retrieve→ summarize→ generate useless answer B
```

而你真正需要的是：

```
Retrieval A→ evidence ARetrieval B→ evidence Bevidence A + evidence B→ Extraction prompt→ final PASS output
```
