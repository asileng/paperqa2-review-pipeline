# -*- coding: utf-8 -*-
"""model_router — 跨 provider 模型路由器（pass4-v2，GLUE v2-dev 登记）。

背景（2026-08-26 实测）：Go 套餐 5 小时限额为【账号级共享桶】——六个模型家族返回
同一递减 retry-after，换模型不能绕限额。故路由目标不是"绕限额"，而是：
1. 省桶：retrieve 用弱模型（deepseek-v4-flash），extract 用强模型（qwen3.7-plus）；
2. 故障转移：Go 桶空 → 整篇论文切 DashScope 链继续跑；
3. 论文原子性：一篇论文一旦选定 provider，三角色（retrieve/extract/vision）同源且
   中途绝不切换；撞 429 即断点落盘，该篇挂起等原 provider 重置后续跑（同模型续跑
   不触发配置指纹变化，已完成 pass 产物直接复用）。

切换信号纪律（研究者裁定）：
- 仅明确限额信号触发切换：HTTP 429 / retry-after 头 / quota 字样错误；
- 401/403 认证类：不切换，直接上抛停批报错；
- 超时/网络瞬态：交给 litellm num_retries 既有重试，不切换。
"""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

# ---------- 链配置（角色 → 有序备选，越靠前越优先） ----------
# openai/* 经全局 OPENAI_API_BASE(launch_go.ps1 设定)路由至 Go 网关；
# dashscope/* 经 DASHSCOPE_API_KEY 路由至阿里云。两套 provider 天然同进程共存。

CHAIN_CONFIG = {
    "retrieve": [
        {"provider": "go", "model": "openai/deepseek-v4-flash"},
        {"provider": "dashscope", "model": "dashscope/qwen-turbo"},
    ],
    "extract": [
        {"provider": "go", "model": "openai/qwen3.7-plus"},
        {"provider": "dashscope", "model": "dashscope/qwen3.7-plus-2026-05-26"},
    ],
    "vision": [
        {"provider": "go", "model": "openai/deepseek-v4-flash-vision-exp"},
        {"provider": "dashscope", "model": "dashscope/qwen-vl-plus"},
    ],
}

PROVIDER_ORDER = ["go", "dashscope"]

_QUOTA_MSG_RE = re.compile(
    r"(429|too many requests|rate.?limit|quota|insufficient|usage limit|5-hour)", re.IGNORECASE
)
_PROVIDER_FATAL_RE = re.compile(
    r"(access denied|not in good standing|account.{0,20}(suspended|blocked)|"
    r"401|403|unauthorized|forbidden|invalid.{0,12}key|authentication|arrearage|欠费)",
    re.IGNORECASE,
)
_RETRY_AFTER_RE = re.compile(r"retry[- ]after\D{0,5}(\d+)", re.IGNORECASE)
# Go 网关消息形如 "Resets in 3hr 9min" / "Resets in 45min" / "Resets in 30s"
_RESETS_IN_RE = re.compile(
    r"resets?\s+in\s+(?:(\d+)\s*h(?:r|our)s?\s*)?(?:(\d+)\s*m(?:in)?s?\s*)?(?:(\d+)\s*s(?:ec)?onds?)?",
    re.IGNORECASE,
)

QUOTA_FALLBACK_SECONDS = 1800        # 解析不到重置时间时的保守兜底
PROVIDER_FATAL_COOLDOWN_SECONDS = 6 * 3600  # provider 级故障（欠费/拒绝访问）默认冷却


class QuotaExhausted(Exception):
    """某 provider 进入限额冷却。携带 provider 名与重置纪元秒。"""

    def __init__(self, provider: str, reset_epoch: float) -> None:
        super().__init__(
            f"provider '{provider}' quota exhausted, resets at "
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reset_epoch))} "
            f"(in {int(reset_epoch - time.time())}s)"
        )
        self.provider = provider
        self.reset_epoch = reset_epoch


class AllProvidersDown(Exception):
    """所有 provider 均在冷却中。"""

    def __init__(self, cooldowns: dict) -> None:
        detail = "; ".join(
            f"{p}: reset {time.strftime('%H:%M:%S', time.localtime(t))}" for p, t in sorted(cooldowns.items())
        )
        super().__init__(f"all providers in cooldown — {detail}")
        self.cooldowns = dict(cooldowns)


def classify_llm_error(exc: Exception) -> tuple[str, float | None]:
    """把 LLM 调用异常分类为 (kind, reset_epoch)。

    kind ∈ {"quota", "fatal", "transient", "other"}
    - quota：限额冷却，附带 reset_epoch（headers retry-after → 消息 "Resets in Xhr Ymin"
      → 数字 retry-after → QUOTA_FALLBACK_SECONDS 兜底）。
    - fatal：provider 级故障（欠费/拒绝访问/认证无效），该 provider 整体不可用。
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    msg = str(exc)

    def _parse_resets_in(text: str) -> float | None:
        m = _RESETS_IN_RE.search(text)
        if not m:
            return None
        h, mi, s = m.group(1), m.group(2), m.group(3)
        if h is None and mi is None and s is None:
            return None
        return time.time() + int(h or 0) * 3600 + int(mi or 0) * 60 + int(s or 0)

    reset = None
    headers = getattr(getattr(exc, "response", None), "headers", None) or getattr(exc, "headers", None)
    if headers is not None:
        try:
            raw = headers.get("retry-after") or headers.get("Retry-After")
            if raw is not None:
                reset = time.time() + float(raw)
        except Exception:
            reset = None
    if reset is None:
        reset = _parse_resets_in(msg)
    if reset is None:
        m = _RETRY_AFTER_RE.search(msg)
        if m:
            reset = time.time() + float(m.group(1))

    if (status is not None and int(status) == 429) or _QUOTA_MSG_RE.search(msg):
        return ("quota", reset if reset is not None else time.time() + QUOTA_FALLBACK_SECONDS)
    if (status is not None and int(status) in (401, 403)) or _PROVIDER_FATAL_RE.search(msg):
        return ("fatal", time.time() + PROVIDER_FATAL_COOLDOWN_SECONDS)
    if any(k in msg.lower() for k in ("timeout", "timed out", "connection", "temporarily")):
        return ("transient", None)
    # 400 BadRequest 且消息含 denied/standing 已被 fatal 覆盖；其余原样 other
    return ("other", None)


class ModelRouter:
    """provider 冷却状态机 + 角色链解析。

    - pick_provider()：整篇论文的 provider 选择（原子单位），跳过冷却中的 provider；
    - model_for(kind, provider)：该篇内固定角色的模型串；
    - note_error(exc, provider)：分类异常；quota→登记冷却并抛 QuotaExhausted，
      auth→原样上抛（停批），其余交调用方走既有重试。
    """

    def __init__(self, chains: dict | None = None, provider_order: list | None = None) -> None:
        self.chains = chains or CHAIN_CONFIG
        self.order = provider_order or PROVIDER_ORDER
        self._cooldown: dict[str, float] = {}

    # -- 状态 --

    def cooldown_remaining(self, provider: str) -> float:
        return max(0.0, self._cooldown.get(provider, 0.0) - time.time())

    def cooldowns(self) -> dict:
        return {p: t for p, t in self._cooldown.items() if t > time.time()}

    def mark_quota(self, provider: str, reset_epoch: float) -> None:
        self._cooldown[provider] = max(self._cooldown.get(provider, 0.0), reset_epoch)

    def note_error(self, exc: Exception, provider: str) -> str:
        """分类并登记。quota→按解析出的重置时间登记冷却；fatal→provider 整体冷却
        PROVIDER_FATAL_COOLDOWN_SECONDS；两者都抛 QuotaExhausted（batch 记 cooldown）。
        transient/other→返回 kind，由调用方决定（通常走既有重试或失败）。"""
        kind, reset = classify_llm_error(exc)
        if kind in ("quota", "fatal"):
            self.mark_quota(provider, reset)
            raise QuotaExhausted(provider, reset) from exc
        return kind

    # -- 选择 --

    def pick_provider(self, prefer_first: bool = True, force: str | None = None) -> str:
        if force:
            if self.cooldown_remaining(force) > 0:
                raise QuotaExhausted(force, time.time() + self.cooldown_remaining(force))
            return force
        for p in self.order:
            if self.cooldown_remaining(p) <= 0:
                return p
        raise AllProvidersDown(self.cooldowns())

    def model_for(self, kind: str, provider: str) -> str:
        for entry in self.chains[kind]:
            if entry["provider"] == provider:
                return entry["model"]
        raise KeyError(f"chain '{kind}' has no entry for provider '{provider}'")

    def provider_for(self, triple: dict) -> str | None:
        """按 (retrieve/extract/vision) 三元组反查所属 provider；未知组合返回 None。"""
        kinds = ("retrieve", "extract", "vision")
        if not all(triple.get(k) for k in kinds):
            return None
        for p in self.order:
            try:
                if all(self.model_for(k, p) == triple[k] for k in kinds):
                    return p
            except KeyError:
                continue
        return None

    def snapshot(self) -> dict:
        """供 meta.json / record.json 记录运行时真值。"""
        return {
            "chains": {k: [dict(e) for e in v] for k, v in self.chains.items()},
            "cooldowns_at_snapshot": {p: round(self.cooldown_remaining(p), 1) for p in self.order},
        }


def load_router_config(path: Path | None = None) -> tuple[dict, list]:
    """可选外部覆盖配置（JSON：{"chains": {...}, "provider_order": [...]}）。"""
    if path and path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
        return cfg.get("chains", CHAIN_CONFIG), cfg.get("provider_order", PROVIDER_ORDER)
    return CHAIN_CONFIG, PROVIDER_ORDER
