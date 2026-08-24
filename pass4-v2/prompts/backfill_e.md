# 概念定义回填 — Extraction 胶水提示词（构造件，guide 未给出原文）

> 来源声明：guide 只规定 backfill 流程为「针对选中的核心概念逐个 retrieval → definition extraction」，
> 未给出提取模板。本文件仅复用全局规则 + 最小输出契约，格式与各 Extraction 的
> Claim / Evidence Quote / Location 三件套及「未找到明确证据」语义保持一致。
> 已在 GLUE.md 登记。

Using only the evidence retrieved for the concept "{concept}", extract the authors' definition or characterization of this concept.

Output exactly this structure:

## Concept Definition: {concept}

**Author's Definition / Characterization**

Concise faithful compression of how the authors define or characterize the concept. Preserve their epistemic tone. Do not supplement with external knowledge.

**Conceptual Lineage (if explicitly stated)**

If the authors credit a specific source, theory, or prior work for the concept, record it here; otherwise write: 本轮检索证据中未找到明确证据。

**Evidence Quote**

Verbatim original wording supporting the definition.

**Location**

Source anchor / page / section.

If no retrieved evidence supports a definition, write under every field:

本轮检索证据中未找到明确证据。
