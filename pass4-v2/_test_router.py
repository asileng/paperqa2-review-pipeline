# -*- coding: utf-8 -*-
"""model_router 离线单测（无网络、无重依赖）——错误分类 + 冷却状态机 + 链解析。"""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_router import (  # noqa: E402
    ModelRouter, QuotaExhausted, AllProvidersDown, classify_llm_error,
)


class FakeErr(Exception):
    def __init__(self, msg, status_code=None, headers=None):
        super().__init__(msg)
        self.status_code = status_code
        self.response = type("R", (), {"status_code": status_code, "headers": headers or {}})()


fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# --- 分类 ---
k, r = classify_llm_error(FakeErr("Error code: 429 - Too Many Requests", 429,
                                  {"retry-after": "3600"}))
check("429+header -> quota with reset≈now+3600", k == "quota" and abs(r - time.time() - 3600) < 30)

k, r = classify_llm_error(FakeErr("429 Too Many Requests retry after: 1200"))
check("msg-based quota+retry-after", k == "quota" and abs(r - time.time() - 1200) < 30)

k, r = classify_llm_error(FakeErr("Error code: 401 - Unauthorized", 401))
check("401 -> fatal with 6h cooldown", k == "fatal" and 3600 * 5.9 <= r - time.time() <= 3600 * 6.1)

# 真实 Go 网关消息（litellm RateLimitError 文本，headers 为空）
go_msg = ("litellm.RateLimitError: OpenAIException - 5-hour usage limit reached. "
          "Resets in 3hr 9min. To continue using this model now, enable usage from your "
          "available balance: https://opencode.ai/workspace/wrk_x/go")
k, r = classify_llm_error(FakeErr(go_msg, 429))
check("Go 'Resets in 3hr 9min' parsed", k == "quota" and abs(r - time.time() - (3 * 3600 + 9 * 60)) < 60)

k, r = classify_llm_error(FakeErr("DashscopeException - Access denied, please make sure "
                                  "your account is in good standing.", 400))
check("dashscope denied -> fatal", k == "fatal" and abs(r - time.time() - 6 * 3600) < 60)

k, _ = classify_llm_error(FakeErr("Request timeout: connection timed out"))
check("timeout -> transient", k == "transient")

k, r = classify_llm_error(FakeErr("Error code: 402 - insufficient balance", 402))
check("402 balance -> quota(兜底1800s)", k == "quota" and 1750 <= r - time.time() <= 1850)

# --- 状态机（注入自定义链，与全局 CHAIN_CONFIG 解耦） ---
CUSTOM_CHAINS = {
    "retrieve": [
        {"provider": "go", "model": "openai/retrieve-a"},
        {"provider": "bk", "model": "bk/ret-x"},
    ],
    "extract": [
        {"provider": "go", "model": "openai/extract-a"},
        {"provider": "bk", "model": "bk/ext-x"},
    ],
    "vision": [
        {"provider": "go", "model": "openai/vision-a"},
        {"provider": "bk", "model": "bk/vis-x"},
    ],
}

rt = ModelRouter(CUSTOM_CHAINS, ["go", "bk"])
rt.mark_quota("go", time.time() + 5000)
check("go cooling -> pick bk", rt.pick_provider() == "bk")
check("model_for retrieve/bk", rt.model_for("retrieve", "bk") == "bk/ret-x")
check("model_for extract/go", rt.model_for("extract", "go") == "openai/extract-a")
rt.mark_quota("bk", time.time() + 5000)
try:
    rt.pick_provider()
    check("both down -> AllProvidersDown", False)
except AllProvidersDown as e:
    check("both down -> AllProvidersDown", set(e.cooldowns) == {"go", "bk"})

# --- provider_for 三元组反查 ---
p = rt.provider_for({"retrieve": "openai/retrieve-a",
                     "extract": "openai/extract-a",
                     "vision": "openai/vision-a"})
check("triple -> go", p == "go")
p = rt.provider_for({"retrieve": "x", "extract": "y", "vision": "z"})
check("unknown triple -> None", p is None)

# --- note_error 行为 ---
rt2 = ModelRouter()
try:
    rt2.note_error(FakeErr("401 Unauthorized", 401), "go")
    check("fatal -> QuotaExhausted(6h)", False)
except QuotaExhausted as qe:
    check("fatal -> QuotaExhausted(6h)", qe.provider == "go"
          and 3600 * 5.9 <= qe.reset_epoch - time.time() <= 3600 * 6.1)

before = time.time()
try:
    rt2.note_error(FakeErr("Error code: 429 - rate limit", 429), "go")
    check("quota -> QuotaExhausted", False)
except QuotaExhausted as qe:
    check("quota -> QuotaExhausted(provider=go)", qe.provider == "go")
    check("cooldown registered", rt2.cooldown_remaining("go") > 200)

kind = rt2.note_error(FakeErr("socket timeout"), "go")
check("transient returned, no cooldown", kind == "transient" and rt2.provider_for is not None)

print("\n" + ("ALL TESTS PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(0 if not fails else 1)
