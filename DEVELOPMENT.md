# 开发计划（Development Roadmap）

> 本文档记录已识别但尚未实施的改进项。按优先级排列。
> 研究者批准后逐项实施，每项完成后在此标记状态。

---

## P1：batch.py 冷却默认等待重试

- **现状**：`--wait-reset` 默认 False，冷却时进程退场，需手动重发
- **改进**：改为默认 True；新增 `--no-wait-reset` 供需要立即退出的场景
- **实现**：
  ```python
  p.add_argument("--wait-reset", action=argparse.BooleanOptionalAction, default=True)
  ```
- **影响**：冷却期自动续跑，消除"九批次"式反复手动发射
- **状态**：☐ 待实施

## P2：交互式发射前参数确认

- **现状**：并发数、模型分配由代码默认值或命令行参数决定，agent 操作流程中无用户确认环节
- **改进**：新建 `launch_interactive.py`，发射前依次询问：
  1. 并发数（建议值 + 解释）
  2. retrieve 与 extract 是否分模型（是→分别选择）
  3. vision 模型选择（含 none 哨兵说明）
  4. 确认摘要后发射
- **实现**：Python `input()` 循环 + 参数校验 → 构建路由 JSON → subprocess 调用 batch.py
- **影响**：消除"擅自选模型"类违规的结构性风险
- **状态**：☐ 待实施

## P3：预检探针升级为非空生成断言

- **现状**：preflight 用 `max_tokens=8` 的 ping 探针，Go 桶耗尽期可返回 HTTP 200 但 content 为空——导致误判"可用"
- **改进**：`_probe_one()` 断言 `len(content.strip()) > 0` 而非仅检查 HTTP 状态码
- **影响**：消除"200 空回复"假阳性，避免向不可用通道发射批次
- **来源案例**：2026-08-26 On Verbs 首轮点火即中招
- **状态**：☐ 待实施

## P4：概念解析器多格式兼容

- **现状**：e3 输出中 Core Concepts 段的格式因模型/温度不同产生至少三种变体：
  - A：`- **Concept**: X`（guide 模板风格）
  - B：`#### Concept N: X`（标题风格）
  - C：`**Concept N: X**`（加粗段落风格）
  当前解析器只覆盖部分变体，漏检率 ~50%
- **改进**：统一正则匹配所有已知变体 + 对新变体做防御性兜底
- **影响**：概念回填步骤不再随机跳过
- **来源案例**：DJICIQIL 三轮调试 + On Verbs 批次多篇跳过回填
- **状态**：✅ 已部分实现（三风格正则），待补充测试用例覆盖

## P5：Zotero 密钥缓存文件加密存储

- **现状**：密钥明文存储于 `%APPDATA%\opencode\zotero_local_api.key`
- **改进**：使用 Windows DPAPI 或 keyring 库加密；文件仅作 fallback
- **影响**：降低密钥泄露风险
- **优先级**：低（本机单用户场景，风险可控）
- **状态**：☐ 待实施

---

## 已完成项

| 项 | 完成日期 | 说明 |
|---|---|---|
| agent_llm 钉定修复 | 2026-08-25 | paperqa 默认 gpt-4o 槽位指向 Go 网关不支持模型，致索引阶段 AuthenticationError |
| 概念解析器三风格兼容 | 2026-08-26 | 修复 P4 的三种已知变体 |
| runner.py 路径拼接修复 | 2026-08-25 | pools 子目录相对路径 bug |
| Zotero 密钥缓存驱动 | 2026-08-26 | 零弹窗批量写入 |
