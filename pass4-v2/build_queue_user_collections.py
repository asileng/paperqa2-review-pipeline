# -*- coding: utf-8 -*-
"""build_queue_user_collections.py — 从 Zotero 个人库目标分类构建 pass4-v2 队列。

用法（示例）：
  python build_queue_user_collections.py \
    --collections "及物性 + NLP;LLM-enactment-多模态;VLM 词汇学习;On Verbs" \
    --library users/0 --out queue/user_targets_queue.json

规则沿袭 GLUE §五：SHA-256 文件级去重（首见保留）；无本地 PDF 显式列入 excluded；
绝不虚构 pdf_path。输出 schema 与 papers_queue.json 对齐（batch.py 直接可用）。
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent.parent.parent))  # litereature review/
from review_bricks_workspace import ZoteroLocalApi  # noqa: E402

STORAGE_ROOT = Path(r"C:\Users\ieltsbro\Zotero\storage")
PDF_TYPES = {"journalArticle", "book", "bookSection", "conferencePaper", "report",
             "thesis", "preprint", "document", "webpage"}


def norm_name(s: str) -> str:
    return "".join(s.lower().split()).replace("＋", "+")


def sha_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collections", required=True, help="';' separated target collection names")
    ap.add_argument("--library", default="users/0")
    ap.add_argument("--out", default=str(BASE / "queue" / "user_targets_queue.json"))
    args = ap.parse_args()

    wanted = [c.strip() for c in args.collections.split(";") if c.strip()]
    wanted_norm = {norm_name(w): w for w in wanted}

    api = ZoteroLocalApi(timeout=30)
    api.status()
    prefix = api.prefix_for_library(args.library)

    cols, _ = api.request(f"{prefix}/collections", query={"format": "json", "limit": "100"})
    col_map = {}  # norm_name -> (key, real_name)
    for c in cols if isinstance(cols, list) else []:
        d = api._data(c)
        n = norm_name(d.get("name", ""))
        if n in wanted_norm:
            col_map[n] = (d.get("key"), d.get("name"))
    missing = [wanted_norm[n] for n in wanted_norm if n not in col_map]
    if missing:
        raise SystemExit(f"[builder] 目标分类未在 {args.library} 找到: {missing}")
    print(f"[builder] matched collections: {[v[1] for v in col_map.values()]}")

    papers, excluded, seen_sha = [], [], {}
    for norm, (ckey, cname) in col_map.items():
        items, _ = api.request(f"{prefix}/collections/{ckey}/items/top",
                               query={"format": "json", "limit": "100"})
        for it in items if isinstance(items, list) else []:
            d = api._data(it)
            if d.get("itemType") not in PDF_TYPES:
                excluded.append({"key": it.get("key"), "title": (d.get("title") or "")[:60],
                                 "reason": f"itemType={d.get('itemType')}"})
                continue
            ikey = it.get("key")
            children, _ = api.request(f"{prefix}/items/{ikey}/children",
                                      query={"format": "json"})
            pdf_att = None
            for ch in children if isinstance(children, list) else []:
                cd = api._data(ch)
                fn = cd.get("filename") or ""
                if cd.get("contentType") == "application/pdf" or fn.lower().endswith(".pdf"):
                    pdf_att = (ch.get("key"), fn)
                    break
            if not pdf_att:
                excluded.append({"key": ikey, "title": (d.get("title") or "")[:60],
                                 "reason": "no local pdf attachment"})
                continue
            att_key, fname = pdf_att
            pdf_path = STORAGE_ROOT / att_key / fname
            if not pdf_path.exists():
                excluded.append({"key": ikey, "title": (d.get("title") or "")[:60],
                                 "reason": f"pdf file missing on disk: {pdf_path}"})
                continue
            sha = sha_of(pdf_path)
            if sha in seen_sha:
                excluded.append({"key": ikey, "title": (d.get("title") or "")[:60],
                                 "reason": f"duplicate of {seen_sha[sha]} (sha256)"})
                continue
            seen_sha[sha] = ikey
            creators = d.get("creators") or []
            papers.append({
                "zotero_key": ikey,
                "sections": [cname],
                "item_type": d.get("itemType"),
                "title": d.get("title"),
                "authors": [f"{c.get('lastName','')}{' ' if c.get('firstName') else ''}{c.get('firstName','')}".strip()
                            if c.get("name") is None else c.get("name") for c in creators],
                "year": d.get("date", ""),
                "doi": d.get("DOI", ""),
                "venue": (d.get("proceedingsTitle") or d.get("publicationTitle") or ""),
                "publisher": d.get("publisher", ""),
                "pdf_path": str(pdf_path),
                "pdf_sha256": sha,
                "priority": 1,
            })
        print(f"[builder] {cname}: cumulative papers={len(papers)} excluded={len(excluded)}")

    out = {
        "schema": "pass4-v2-user-targets-queue",
        "built_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_collections": [v[1] for v in col_map.values()],
        "dedup_rule": "sha256-first-wins",
        "count": len(papers),
        "papers": papers,
        "excluded": excluded,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[builder] WROTE {args.out}: {len(papers)} papers, {len(excluded)} excluded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
