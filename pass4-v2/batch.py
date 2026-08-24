# -*- coding: utf-8 -*-
"""pass4-v1 批量调度器（无人值守）。

- asyncio 信号量并发跑多篇（同进程共享 bge-m3 与 litellm 连接池）
- 失败隔离：单篇崩溃不影响队列；失败篇在后续 sweep 自动重试
- 产物级断点续跑：重启 batch.py 即从各篇已完成产物继续
- 每阶段超时由 runner 控制；本层另加单篇总闸与全局 --max-hours 总闸
- run_manifest.json 原子更新；REPORT.md 持续重写，供研究者早晨直读
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import runner
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
        "schema": "pass4-v1-manifest",
        "created_utc": now(),
        "papers": {k: {"status": "pending", "attempts": 0, "error": None} for k in queue_keys},
    }


def save_state(st: dict) -> None:
    st["updated_utc"] = now()
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MANIFEST)


def write_report(st: dict, queue_by_key: dict) -> None:
    rows = []
    counts = {"done": 0, "failed": 0, "pending": 0, "running": 0, "deferred": 0}
    for key, rec in st["papers"].items():
        s = rec["status"]
        counts[s] = counts.get(s, 0) + 1
        meta = queue_by_key.get(key, {})
        title = (meta.get("title") or "")[:58]
        secs = rec.get("seconds")
        err = (rec.get("error") or "")[:60].replace("|", "/").replace("\n", " ")
        rows.append(f"| {key} | {', '.join(meta.get('sections', []))} | {title} | {s} | {rec.get('attempts', 0)} | {secs if secs else ''} | {err} |")
    total = len(rows)
    body = "\n".join(rows)
    REPORT.write_text(
        "# pass4-v1 批量运行报告\n\n"
        f"更新时间：{now()}\n\n"
        f"总计 {total} 篇：done={counts.get('done', 0)} failed={counts.get('failed', 0)} "
        f"pending={counts.get('pending', 0)} running={counts.get('running', 0)} deferred={counts.get('deferred', 0)}\n\n"
        "| Key | Section | Title | Status | Attempts | Seconds | Error |\n"
        "|---|---|---|---|---|---|---|\n" + body + "\n",
        encoding="utf-8",
    )


async def worker(key: str, entry: dict, sem: asyncio.Semaphore, st: dict,
                 per_paper_timeout: float, deadline: float | None,
                 zotero_index: bool = False) -> None:
    async with sem:
        rec = st["papers"][key]
        if deadline and time.time() > deadline:
            if rec["status"] in ("pending",):
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
                        update_index=zotero_index),
                timeout=per_paper_timeout
            )
            if zotero_index:
                import zotero_index
                zotero_index.write_index(key)
            rec["status"] = "done"
            rec["error"] = None
            rec["seconds"] = round(time.time() - t0, 1)
            log("batch", f"{key} DONE in {rec['seconds']}s")
        except asyncio.TimeoutError:
            rec["status"] = "failed"
            rec["error"] = f"per-paper timeout {per_paper_timeout}s"
            log("batch", f"{key} FAILED (timeout)")
        except Exception as exc:
            rec["status"] = "failed"
            rec["error"] = str(exc)[:400]
            log("batch", f"{key} FAILED: {exc}")
        rec["finished_utc"] = now()
        save_state(st)


async def amain(args) -> int:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    by_key = {p["zotero_key"]: p for p in queue["papers"]}
    include = set(args.include) if args.include else None
    keys = [k for k in [p["zotero_key"] for p in queue["papers"]] if not include or k in include]

    # 专著永远排最后执行
    keys.sort(key=lambda k: 0 if k == args.pilot_first else (2 if k in args.book_last.split(",") else 1))

    st = load_state(keys)
    st["papers"].update({k: st["papers"].get(k) or {"status": "pending"} for k in keys})
    write_report(st, by_key)

    sem = asyncio.Semaphore(args.concurrency)
    deadline = time.time() + args.max_hours * 3600 if args.max_hours else None

    for sweep in range(1, args.sweeps + 1):
        targets = [
            k for k in keys
            if st["papers"][k]["status"] in ("pending",)
            or (sweep > 1 and st["papers"][k]["status"] == "failed" and st["papers"][k].get("attempts", 0) < sweep)
        ]
        if not targets:
            break
        log("batch", f"sweep {sweep}: {len(targets)} papers, concurrency={args.concurrency}")
        tasks = [asyncio.create_task(worker(k, by_key[k], sem, st, args.per_paper_timeout, deadline,
                                            zotero_index=args.zotero_index))
                 for k in targets]
        await asyncio.gather(*tasks)
        write_report(st, by_key)

    write_report(st, by_key)
    final = {s: sum(1 for r in st["papers"].values() if r["status"] == s) for s in ("done", "failed", "deferred")}
    log("batch", f"ALL SWEEPS COMPLETE: {final}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="pass4-v1 batch orchestrator")
    p.add_argument("--concurrency", type=int, default=int(__import__("os").environ.get("P4_CONCURRENCY", "4")))
    p.add_argument("--sweeps", type=int, default=3)
    p.add_argument("--max-hours", type=float, default=11.0)
    p.add_argument("--per-paper-timeout", type=float, default=5400)
    p.add_argument("--include", nargs="*", help="restrict to these zotero keys")
    p.add_argument("--pilot-first", default="", help="key to schedule first")
    p.add_argument("--book-last", default="YMBIMQR9")
    p.add_argument("--zotero-index", action="store_true",
                   help="after each successful paper, write/update its pass4-v2 Zotero index note")
    args = p.parse_args(sys.argv[1:])
    return asyncio.run(amain(args))


if __name__ == "__main__":
    sys.exit(main())
