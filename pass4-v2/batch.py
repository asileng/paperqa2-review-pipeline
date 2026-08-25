# -*- coding: utf-8 -*-
"""pass4-v2 批量调度器（无人值守，跨 provider 路由版）。

- asyncio 信号量并发跑多篇（同进程共享 bge-m3 与 litellm 连接池）
- 失败隔离：单篇崩溃不影响队列；失败篇在后续 sweep 自动重试
- 产物级断点续跑：重启 batch.py 即从各篇已完成产物继续
- 跨 provider 路由（GLUE v2-dev §九）：Go 账号桶 429 → 该篇挂 cooldown 等【原
  provider】重置续跑（同模型指纹不变）；全新论文自动切 DashScope 链；
  --wait-reset 让进程休眠到最早重置点后继续清队列
- 每阶段超时由 runner 控制；本层另加单篇总闸与全局 --max-hours 总闸
- run_manifest.json 原子更新；REPORT.md 持续重写，供研究者早晨直读
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import runner
from model_router import ModelRouter, QuotaExhausted, AllProvidersDown, load_router_config
from runner import log, run_one

BASE = Path(__file__).resolve().parent
QUEUE_PATH = BASE / "queue" / "papers_queue.json"
MANIFEST = BASE / "run_manifest.json"
REPORT = BASE / "REPORT.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(queue_keys: list[str]) -> dict:
    if MANIFEST.exists():
        try:
            st = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if set(st.get("papers", {}).keys()) >= set(queue_keys):
                return st
        except Exception:
            pass
    return {
        "schema": "pass4-v2-manifest",
        "created_utc": now(),
        "papers": {k: {"status": "pending", "attempts": 0, "error": None} for k in queue_keys},
    }


def save_state(st: dict) -> None:
    st["updated_utc"] = now()
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MANIFEST)


def _fmt_epoch(t) -> str:
    if not t:
        return ""
    try:
        return datetime.fromtimestamp(float(t)).strftime("%m-%d %H:%M")
    except Exception:
        return ""


def write_report(st: dict, queue_by_key: dict) -> None:
    rows = []
    counts = {"done": 0, "failed": 0, "pending": 0, "running": 0, "deferred": 0, "cooldown": 0}
    for key, rec in st["papers"].items():
        s = rec["status"]
        counts[s] = counts.get(s, 0) + 1
        meta = queue_by_key.get(key, {})
        title = (meta.get("title") or "")[:58]
        secs = rec.get("seconds")
        err = (rec.get("error") or "")[:60].replace("|", "/").replace("\n", " ")
        prov = rec.get("provider") or ""
        cd = _fmt_epoch(rec.get("cooldown_until"))
        rows.append(
            f"| {key} | {', '.join(meta.get('sections', []))} | {title} | {s} | {prov} "
            f"| {cd} | {rec.get('attempts', 0)} | {secs if secs else ''} | {err} |"
        )
    total = len(rows)
    body = "\n".join(rows)
    REPORT.write_text(
        "# pass4-v2 批量运行报告（跨 provider 路由）\n\n"
        f"更新时间：{now()}\n\n"
        f"总计 {total} 篇：done={counts.get('done', 0)} failed={counts.get('failed', 0)} "
        f"pending={counts.get('pending', 0)} running={counts.get('running', 0)} "
        f"deferred={counts.get('deferred', 0)} cooldown={counts.get('cooldown', 0)}\n\n"
        "| Key | Section | Title | Status | Provider | Cooldown至 | Attempts | Seconds | Error |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + body + "\n",
        encoding="utf-8",
    )


async def worker(key: str, entry: dict, sem: asyncio.Semaphore, st: dict,
                 per_paper_timeout: float, deadline: float | None,
                 zotero_index: bool, router: ModelRouter) -> None:
    async with sem:
        rec = st["papers"][key]
        if deadline and time.time() > deadline:
            if rec["status"] in ("pending", "cooldown"):
                rec["status"] = "deferred"
                log("batch", f"{key} deferred (max-hours reached)")
            return
        rec["status"] = "running"
        rec["started_utc"] = now()
        rec["attempts"] = rec.get("attempts", 0) + 1
        save_state(st)
        t0 = time.time()
        try:
            await asyncio.wait_for(
                run_one(entry, resume=True, archive=True,
                        update_index=False, router=router),  # 回写统一在下方隔离执行
                timeout=per_paper_timeout
            )
            # 先落盘 done：回写任何故障都不得污染分析结果的状态
            rec["status"] = "done"
            rec["error"] = None
            rec["cooldown_until"] = None
            rec["seconds"] = round(time.time() - t0, 1)
            save_state(st)
            log("batch", f"{key} DONE in {rec['seconds']}s")
            if zotero_index:
                # 回写隔离（研究者裁定：回写故障绝不拖累文献工作）：
                # to_thread 防阻塞事件循环 + 120s 硬闸防悬挂 + 捕获 SystemExit/Exception，
                # 失败仅记 zotero_error 字段，状态保持 done，批次继续。
                try:
                    import zotero_index
                    note_key = await asyncio.wait_for(
                        asyncio.to_thread(zotero_index.write_index, key), timeout=120
                    )
                    rec["zotero_note"] = note_key
                    log("batch", f"{key} zotero index ok: {note_key}")
                except SystemExit as se:
                    rec["zotero_error"] = str(se)[:220]
                    log("batch", f"{key} ZOTERO-SKIP (SystemExit): {str(se)[:120]}")
                except asyncio.TimeoutError:
                    rec["zotero_error"] = "zotero writeback timeout >120s"
                    log("batch", f"{key} ZOTERO-TIMEOUT (>120s) — paper stays done")
                except Exception as exc:
                    rec["zotero_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
                    log("batch", f"{key} ZOTERO-FAIL (non-blocking): {exc}")
        except asyncio.TimeoutError:
            rec["status"] = "failed"
            rec["error"] = f"per-paper timeout {per_paper_timeout}s"
            log("batch", f"{key} FAILED (timeout)")
        except QuotaExhausted as qe:
            rec["status"] = "cooldown"
            rec["provider"] = qe.provider
            rec["cooldown_until"] = qe.reset_epoch
            rec["error"] = f"quota: {qe}"
            log("batch", f"{key} COOLDOWN on '{qe.provider}' until "
                         f"{time.strftime('%H:%M:%S', time.localtime(qe.reset_epoch))}")
        except AllProvidersDown as apd:
            earliest = min(apd.cooldowns.values()) if apd.cooldowns else time.time() + 300
            rec["status"] = "cooldown"
            rec["cooldown_until"] = earliest
            rec["error"] = f"all providers down: {apd}"
            log("batch", f"{key} COOLDOWN (all providers) until "
                         f"{time.strftime('%H:%M:%S', time.localtime(earliest))}")
        except Exception as exc:
            rec["status"] = "failed"
            rec["error"] = str(exc)[:400]
            log("batch", f"{key} FAILED: {exc}")
        rec["finished_utc"] = now()
        save_state(st)


def _cooldown_ready(rec: dict) -> bool:
    until = rec.get("cooldown_until")
    return (not until) or time.time() >= float(until)


async def amain(args) -> int:
    chains, order = load_router_config(Path(args.router_config) if args.router_config else None)
    router = ModelRouter(chains, order)

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    by_key = {p["zotero_key"]: p for p in queue["papers"]}
    include = set(args.include) if args.include else None
    keys = [k for k in [p["zotero_key"] for p in queue["papers"]] if not include or k in include]

    # 专著永远排最后执行
    keys.sort(key=lambda k: 0 if k == args.pilot_first else (2 if k in args.book_last.split(",") else 1))

    st = load_state(keys)
    st["papers"].update({k: st["papers"].get(k) or {"status": "pending"} for k in keys})
    write_report(st, by_key)

    if not args.no_probe:
        log("batch", "preflight probing all chain entries (primes cooldown state)...")
        try:
            await runner.preflight(router)
        except SystemExit:
            pass
        except Exception as exc:
            log("batch", f"preflight errored (non-fatal): {exc}")

    sem = asyncio.Semaphore(args.concurrency)
    deadline = time.time() + args.max_hours * 3600 if args.max_hours else None

    def pick_targets() -> list[str]:
        out = []
        for k in keys:
            rec = st["papers"][k]
            s = rec["status"]
            if s == "pending":
                out.append(k)
            elif s == "cooldown" and _cooldown_ready(rec):
                out.append(k)
            elif (s == "failed" and rec.get("attempts", 0) < args.sweeps):
                out.append(k)
        # 冷却刚解除的优先（同模型断点最省额度），其余保持队列顺序
        out.sort(key=lambda k: 0 if st["papers"][k]["status"] == "cooldown" else 1)
        return out

    while True:
        targets = pick_targets()
        if not targets:
            cds = [st["papers"][k] for k in keys if st["papers"][k]["status"] == "cooldown"]
            if cds and args.wait_reset:
                earliest = min(float(r.get("cooldown_until") or time.time() + 300) for r in cds)
                wait_s = max(30.0, earliest - time.time() + 30)
                if deadline and time.time() + wait_s > deadline:
                    log("batch", "cooldown reset beyond --max-hours; stopping")
                    break
                log("batch", f"all actionable papers cooling; sleeping {int(wait_s)}s until earliest reset")
                await asyncio.sleep(min(wait_s, 3600))
                continue
            break
        log("batch", f"sweep: {len(targets)} papers actionable, concurrency={args.concurrency}, "
                     f"cooldowns={sum(1 for k in keys if st['papers'][k]['status'] == 'cooldown')}")
        tasks = [asyncio.create_task(worker(k, by_key[k], sem, st, args.per_paper_timeout, deadline,
                                            args.zotero_index, router))
                 for k in targets]
        await asyncio.gather(*tasks)
        write_report(st, by_key)
        if deadline and time.time() > deadline:
            log("batch", "--max-hours reached; stopping")
            break

    write_report(st, by_key)
    final = {s: sum(1 for r in st["papers"].values() if r["status"] == s)
             for s in ("done", "failed", "deferred", "cooldown")}
    log("batch", f"BATCH COMPLETE: {final}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="pass4-v2 batch orchestrator (cross-provider routing)")
    p.add_argument("--concurrency", type=int, default=int(os.environ.get("P4_CONCURRENCY", "4")))
    p.add_argument("--sweeps", type=int, default=3)
    p.add_argument("--max-hours", type=float, default=11.0)
    p.add_argument("--per-paper-timeout", type=float, default=5400)
    p.add_argument("--include", nargs="*", help="restrict to these zotero keys")
    p.add_argument("--pilot-first", default="", help="key to schedule first")
    p.add_argument("--book-last", default="YMBIMQR9")
    p.add_argument("--zotero-index", action="store_true",
                   help="after each successful paper, write/update its pass4-v2 Zotero index note")
    p.add_argument("--router-config", default="", help="optional JSON overriding chains/provider order")
    p.add_argument("--no-probe", action="store_true",
                   help="skip startup chain probing (cooldown then discovered at runtime)")
    p.add_argument("--wait-reset", action="store_true",
                   help="sleep in-process until provider cooldown resets instead of exiting with cooldown papers")
    args = p.parse_args(sys.argv[1:])
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
