import argparse
import asyncio
import hashlib
import json
import os
import pickle
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("HF_HOME", r"D:\hf_cache")

_COLLIDING = {
    "agent", "llm", "summary_llm", "embedding", "temperature",
    "batch_size", "texts_index_mmr_lambda", "verbosity",
    "answer", "parsing", "citation",
}
_STRIPPED_ENV = sorted(k for k in list(os.environ) if k.lower() in _COLLIDING)
for _k in list(os.environ):
    if _k.lower() in _COLLIDING:
        del os.environ[_k]

import litellm
import paperqa
from paperqa import Docs, Settings

BASE = Path(__file__).resolve().parent
PAPERS = BASE / "papers"
PROMPTS = BASE / "prompts"
RESULTS = BASE / "results"
ARCHIVE = BASE / "results-archive"

MODEL = os.environ.get("PILOT_LLM", "dashscope/qwen3.7-plus-2026-05-26")
VLM = os.environ.get("PILOT_VLM", "dashscope/qwen-vl-plus")
EMBED = "hybrid-st-BAAI/bge-m3"
TEMPLATE_SOURCE = (
    r"C:\Users\ieltsbro\.codex\skills\literature-scispace-workflow"
    r"\references\first-round-qualitative.md"
)

PASS_NAMES = ("pass1", "pass2", "pass3")
PROMPT_FILES = PASS_NAMES + ("synth",)

# ---- Zotero 索引写回（v3）----
ZOTERO_LIBRARY = "group:6583681"
PAPERQA2_NOTE_TAG = "[reviewBricks:pilot-v1][provider:paperqa2_docs_local]"
INDEX_FIELDS = (
    "provider", "llm", "vision_llm", "embedding", "citation_scheme",
    "analysis_json_path", "analysis_json_pointer", "raw_output_path",
    "raw_output_anchor", "prompts_sha256", "run_utc", "pdf_sha256",
)

SECTIONS = [
    "文献定位",
    "研究类型与材料/方法",
    "研究对象、核心问题、主要论证",
    "Research gap",
    "概念定义与理论谱系",
    "对模块化综述的可用性",
    "对研究设计的具体启发",
    "局限与待追问",
]

_PAGE_CITATION_RE = re.compile(r"pages?\s+\d+([-–—]\d+)?")
_CHUNK_ID_RE = re.compile(r"\bpqac-[0-9a-f]+\b")
# scheme 由审计结果派生：base + 后缀拼接，不写完整字面量预设值
_CITATION_SCHEME_BASE = "paperqa_doc_keys_author_year"
_META_MATCH_FIELDS = ("model", "vlm", "embed", "paperqa_version")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def prompt_fingerprints() -> dict:
    # 按原始字节计算，保证与 certutil -hashfile 一致（不受换行符转换影响）
    return {
        name: sha256_text((PROMPTS / f"{name}.md").read_bytes().decode("utf-8"))
        for name in PROMPT_FILES
    }


def split_sections(text: str) -> dict:
    found = {}
    pattern = re.compile(r"^##\s*(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        found[title] = text[start:end].strip()
    return found


def parse_atomic_notes(final_text: str) -> list:
    notes = []
    for line in final_text.splitlines():
        m = re.match(r"^\s*[-*]?\s*\**(?:笔记|Note)\s*(\d+)\**\s*[:：]\s*(.+)$", line)
        if m:
            notes.append({"id": f"N{m.group(1)}", "text": m.group(2).strip()})
    return notes


def audit_citations(text: str) -> dict:
    return {
        "page_range_citation_count": len(_PAGE_CITATION_RE.findall(text)),
        "internal_chunk_id_count": len(_CHUNK_ID_RE.findall(text)),
    }


def derive_citation_scheme(audit: dict) -> str:
    if audit["page_range_citation_count"] > 0:
        return _CITATION_SCHEME_BASE + "_with_page_ranges"
    return _CITATION_SCHEME_BASE + "_no_page_ranges_observed"


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump())
        except Exception:
            return repr(value)
    return repr(value)


def _get_field(obj, field):
    if isinstance(obj, dict):
        return obj.get(field)
    return getattr(obj, field, None)


def pass_usage(res) -> dict:
    # PQASession.cost / .token_counts；缺失字段记 None，绝不抛异常
    usage = {"cost": None, "token_counts": None}
    try:
        usage["cost"] = _jsonable(_get_field(res, "cost"))
    except Exception:
        pass
    try:
        usage["token_counts"] = _jsonable(_get_field(res, "token_counts"))
    except Exception:
        pass
    return usage


def synth_usage(resp) -> dict:
    # litellm 合成响应的 usage；缺失字段记 None，绝不抛异常
    usage = {
        "model": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    try:
        usage["model"] = _get_field(resp, "model")
    except Exception:
        pass
    try:
        u = _get_field(resp, "usage")
        if u is not None:
            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[field] = _jsonable(_get_field(u, field))
    except Exception:
        pass
    return usage


def classify_probe_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "402" in msg or "insufficient" in low or "balance" in low:
        return f"余额不足 ({msg[:160]})"
    if "401" in msg or "auth" in low:
        return f"key 无效 ({msg[:160]})"
    return msg[:200]


def current_meta(fingerprints: dict) -> dict:
    return {
        "model": MODEL,
        "vlm": VLM,
        "embed": EMBED,
        "paperqa_version": paperqa.__version__,
        "prompts_sha256": dict(fingerprints),
    }


def load_prior_meta(out_dir: Path) -> dict:
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def meta_cfg_matches(prior: dict, cur: dict) -> bool:
    return all(prior.get(f) == cur[f] for f in _META_MATCH_FIELDS)


def pass_resumable(out_dir: Path, prior_meta: dict, cur_meta: dict, name: str) -> bool:
    if not (out_dir / f"{name}.answer.md").exists():
        return False
    if not meta_cfg_matches(prior_meta, cur_meta):
        return False
    prior_hashes = prior_meta.get("prompts_sha256") or {}
    return prior_hashes.get(name) == cur_meta["prompts_sha256"][name]


def extract_prior_final(raw_text: str, key: str) -> str:
    # 复用既有 raw.md 中 H1 标题行与附录分隔符之间的 final 文本
    h1 = re.search(rf"^#\s+{re.escape(key)}\s+首轮分析[^\n]*\n", raw_text, re.MULTILINE)
    appendix = re.search(r"^#\s*附录", raw_text, re.MULTILINE)
    if not h1 or not appendix or appendix.start() <= h1.end():
        return ""
    segment = raw_text[h1.end():appendix.start()]
    segment = re.sub(r"\n*---\s*$", "", segment)
    return segment.strip()


def appendix_block(pass_answers: dict, pass_meta: dict) -> str:
    parts = []
    for i, n in enumerate(PASS_NAMES):
        if pass_meta[n].get("resumed"):
            header = f"\n## PASS {i + 1} 原始回答（resumed，复用上次结果）\n\n"
        else:
            header = f"\n## PASS {i + 1} 原始回答（{pass_meta[n]['seconds']}s）\n\n"
        parts.append(header + pass_answers[n])
    return "".join(parts)


def _zotero_client():
    """复用项目已评审的 Zotero Local API 客户端（review_bricks_workspace.py）。"""
    root = BASE.parent.parent.parent  # litereature review/
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from review_bricks_workspace import ZoteroLocalApi
    except Exception as exc:
        raise RuntimeError(f"无法导入 review_bricks_workspace.ZoteroLocalApi: {exc}") from exc
    return ZoteroLocalApi(timeout=30)


def build_index_note_text(
    key: str,
    *,
    llm: str,
    vlm: str,
    embed: str,
    citation_scheme: str,
    analysis_path: Path,
    raw_path: Path,
    fingerprints: dict,
    run_utc: str,
    pdf_sha: str,
    annotations: dict | None = None,
) -> str:
    annotations = annotations or {}

    def fp_entry(name: str) -> str:
        suffix = f" ({annotations[name]})" if name in annotations else ""
        return f"{name}: {fingerprints[name]}{suffix}"

    lines = [
        f"{PAPERQA2_NOTE_TAG} {key}",
        "",
        "provider: paperqa2_docs_local",
        f"llm: {llm}",
        f"vision_llm: {vlm}",
        f"embedding: {embed}",
        f"citation_scheme: {citation_scheme}",
        f"analysis_json_path: {analysis_path.resolve()}",
        "analysis_json_pointer: /",
        f"raw_output_path: {raw_path.resolve()}",
        f"raw_output_anchor: paper-{key.lower()}",
        "prompts_sha256: {" + ", ".join(fp_entry(n) for n in PROMPT_FILES) + "}",
        f"run_utc: {run_utc}",
        f"pdf_sha256: {pdf_sha}",
    ]
    return "\n".join(lines)


def find_existing_paperqa2_note(api, prefix: str, key: str):
    """按标题标签检索本 provider 的既有索引笔记；格式损坏则停止，绝不静默覆写。"""
    children, _ = api.request(f"{prefix}/items/{key}/children", query={"format": "json", "include": "data"})
    if not isinstance(children, list):
        raise RuntimeError(f"[{key}] unexpected children payload from Zotero")
    for item in children:
        data = api._data(item)
        body = data.get("note", "")
        if PAPERQA2_NOTE_TAG in body[:200]:
            missing = [f for f in INDEX_FIELDS if not re.search(rf"^{f}:", body, re.MULTILINE)]
            if missing:
                raise SystemExit(
                    f"[{key}] existing paperqa2 index note {item.get('key')} is malformed "
                    f"(missing fields: {missing}); refusing to overwrite silently"
                )
            return item.get("key"), item.get("version")
    return None, None


def write_zotero_index(key: str) -> str:
    out_dir = RESULTS / key
    analysis_path = out_dir / f"{key}.analysis.json"
    raw_path = out_dir / f"{key}.raw.md"
    meta_path = out_dir / "meta.json"
    missing = [p.name for p in (analysis_path, raw_path, meta_path) if not p.exists()]
    if missing:
        raise SystemExit(f"[{key}] index prerequisites missing in results/: {missing}")
    pdf = PAPERS / f"{key}.pdf"
    pdf_sha = sha256_of(pdf)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    recorded = meta.get("pdf_sha256")
    if recorded and recorded != pdf_sha:
        raise SystemExit(f"[{key}] meta.json pdf_sha256 mismatch with current PDF")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    fingerprints = meta.get("prompts_sha256") or prompt_fingerprints()
    scheme = analysis.get("citation_scheme") or derive_citation_scheme(
        audit_citations(raw_path.read_text(encoding="utf-8"))
    )
    run_utc = analysis.get("run_utc") or datetime.now(timezone.utc).isoformat()
    text = build_index_note_text(
        key,
        # 溯源字段以 meta.json 记录的运行时真值为准（旧结果重建场景下与当前常量不同）
        llm=meta.get("model") or MODEL,
        vlm=meta.get("vlm") or VLM,
        embed=meta.get("embed") or EMBED,
        citation_scheme=scheme,
        analysis_path=analysis_path,
        raw_path=raw_path,
        fingerprints=fingerprints,
        run_utc=run_utc,
        pdf_sha=pdf_sha,
        annotations=meta.get("_prompts_sha256_annotations"),
    )

    api = _zotero_client()
    api.status()
    prefix = api.prefix_for_library(ZOTERO_LIBRARY)
    existing_key, existing_version = find_existing_paperqa2_note(api, prefix, key)

    _, lib_headers = api.request(f"{prefix}/items", query={"format": "json", "limit": "1"})
    library_version = lib_headers.get("Last-Modified-Version")
    api_key = api.authorize_write()
    if not getattr(api, "authorization_persistent", False):
        raise SystemExit(
            "[zotero] durable authorization missing (remember != true). "
            "请在 Zotero 中选择 始终允许 / Always Allow 后重试；不使用一次性密钥写入。"
        )

    mode = "update" if existing_key else "create"
    print(f"[{key}] zotero write target: {ZOTERO_LIBRARY} parent={key} mode={mode}")
    headers = {"Zotero-API-Key": api_key}
    if mode == "update":
        headers["If-Unmodified-Since-Version"] = str(existing_version)
        payload = {"itemType": "note", "parentItem": key, "note": text}
        resp, _ = api.request(
            f"{prefix}/items/{existing_key}", method="PUT", payload=payload, extra_headers=headers
        )
    else:
        if library_version:
            headers["If-Unmodified-Since-Version"] = str(library_version)
        # Zotero 写接口要求数组形式的 payload
        payload = [{"itemType": "note", "parentItem": key, "note": text}]
        resp, _ = api.request(f"{prefix}/items", method="POST", payload=payload, extra_headers=headers)

    note_key = None
    if isinstance(resp, dict):
        successful = resp.get("successful")
        note_key = resp.get("key") or (
            successful.get("0", {}).get("key") if isinstance(successful, dict) else None
        )
    if mode == "update" and not note_key and not resp:
        # Zotero 对 PUT 单条目返回 204 No Content（空体）——空响应即成功
        note_key = existing_key
    if not note_key:
        raise SystemExit(f"[{key}] unexpected Zotero response: {str(resp)[:200]}")

    back, _ = api.request(f"{prefix}/items/{note_key}", query={"format": "json"})
    stored = api._data(back).get("note", "")
    lost = [f for f in INDEX_FIELDS if not re.search(rf"^{f}:", stored, re.MULTILINE)]
    if lost or PAPERQA2_NOTE_TAG not in stored[:200]:
        raise SystemExit(f"[{key}] read-back verification failed; missing: {lost}")
    print(f"[{key}] zotero index note ready: {note_key} (read-back verified)")
    return note_key


async def run_one(
    key: str, resume: bool = False, archive: bool = True, update_index: bool = False
) -> None:
    pdf = PAPERS / f"{key}.pdf"
    if not pdf.exists():
        raise FileNotFoundError(pdf)
    out_dir = RESULTS / key
    raw_path = out_dir / f"{key}.raw.md"

    # ---- 产物归档护栏（B4）：覆盖前把旧 <KEY> 目录整体移入 results-archive ----
    if not resume and archive and raw_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = ARCHIVE / f"{key}-{ts}" / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out_dir), str(dest))
        print(f"[{key}] archived previous results -> {dest}")
    out_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    fingerprints = prompt_fingerprints()
    cur_meta = current_meta(fingerprints)
    prior_meta = load_prior_meta(out_dir) if resume else {}
    pdf_hash = sha256_of(pdf)

    resumable = {
        n: resume and pass_resumable(out_dir, prior_meta, cur_meta, n)
        for n in PASS_NAMES
    }
    need_docs = not all(resumable.values())

    settings = Settings(
        llm=MODEL,
        summary_llm=MODEL,
        embedding=EMBED,
        temperature=0.0,
    )
    settings.parsing.enrichment_llm = VLM

    docs = None
    index_seconds = 0.0
    if need_docs:
        # ---- 索引检查点（B2）----
        # pickle 检查点仅限加载本目录（results/<KEY>/）内由本脚本自己写出的 docs.pkl；
        # 绝不加载任何外部或不可信来源的 pickle 文件（反序列化可执行任意代码）。
        ckpt_cfg = {
            "paperqa_version": paperqa.__version__,
            "pdf_sha256": pdf_hash,
            "vlm": VLM,
            "embed": EMBED,
        }
        docs_pkl = out_dir / "docs.pkl"
        docs_meta_path = out_dir / "docs.meta.json"
        if docs_pkl.exists() and docs_meta_path.exists():
            try:
                prior_ckpt = json.loads(docs_meta_path.read_text(encoding="utf-8"))
                if all(prior_ckpt.get(k) == v for k, v in ckpt_cfg.items()):
                    with open(docs_pkl, "rb") as f:
                        docs = pickle.load(f)
                    print(f"[{key}] docs checkpoint reused (aadd skipped)")
                else:
                    print(f"[{key}] docs checkpoint config mismatch; full aadd")
            except Exception as exc:
                print(f"[{key}] docs checkpoint load failed ({exc}); full aadd")
                docs = None
        if docs is None:
            docs = Docs()
            print(f"[{key}] indexing {pdf.name} ...")
            t0 = time.time()
            await docs.aadd(str(pdf), settings=settings)
            index_seconds = round(time.time() - t0, 1)
            try:
                with open(docs_pkl, "wb") as f:
                    pickle.dump(docs, f)
                docs_meta_path.write_text(
                    json.dumps(ckpt_cfg, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                print(f"[{key}] WARNING: docs checkpoint write failed ({exc}); continuing")
    else:
        print(f"[{key}] all passes resumable; docs index not needed")

    # ---- 三次检索 pass（B1 断点续跑）----
    pass_answers = {}
    pass_meta = {}
    usage = {}
    for name in PASS_NAMES:
        if resumable[name]:
            pass_answers[name] = (out_dir / f"{name}.answer.md").read_text(encoding="utf-8")
            pass_meta[name] = {"seconds": None, "resumed": True}
            usage[name] = {"cost": None, "token_counts": None}
            print(f"[{key}] {name} resumed (skipped)")
            continue
        t = time.time()
        res = await docs.aquery(load_prompt(name), settings=settings)
        pass_answers[name] = str(res)
        pass_meta[name] = {"seconds": round(time.time() - t, 1), "resumed": False}
        usage[name] = pass_usage(res)
        (out_dir / f"{name}.answer.md").write_text(pass_answers[name], encoding="utf-8")
        print(f"[{key}] {name} done in {pass_meta[name]['seconds']}s")

    # ---- 合成 pass：仅当三 pass 全 resumed 且 synth 哈希一致且 raw.md 存在时复用 ----
    synth_resumed = False
    final_text = ""
    if (
        resume
        and all(resumable.values())
        and meta_cfg_matches(prior_meta, cur_meta)
        and (prior_meta.get("prompts_sha256") or {}).get("synth") == fingerprints["synth"]
        and raw_path.exists()
    ):
        final_text = extract_prior_final(raw_path.read_text(encoding="utf-8"), key)
        synth_resumed = bool(final_text)
    if synth_resumed:
        synth_seconds = None
        usage["synth"] = {
            "model": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
        print(f"[{key}] synth resumed (reused prior final)")
    else:
        synth_prompt = (
            load_prompt("synth")
            .replace("[PASS1]", pass_answers["pass1"])
            .replace("[PASS2]", pass_answers["pass2"])
            .replace("[PASS3]", pass_answers["pass3"])
        )
        t = time.time()
        resp = await litellm.acompletion(
            model=MODEL,
            messages=[{"role": "user", "content": synth_prompt}],
            temperature=0.0,
        )
        final_text = resp.choices[0].message.content or ""
        synth_seconds = round(time.time() - t, 1)
        usage["synth"] = synth_usage(resp)
        print(f"[{key}] synth done in {synth_seconds}s")

    # ---- 每轮写入 meta.json 供 resume 决策 ----
    (out_dir / "meta.json").write_text(
        json.dumps(cur_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- 引用自动审计（A1）----
    audit = audit_citations(final_text)
    citation_scheme = derive_citation_scheme(audit)

    fp_block = "\n".join(f"  {n}: {fingerprints[n][:12]}" for n in PROMPT_FILES)
    front = (
        "---\n"
        "provider: paperqa2_docs_local\n"
        f"llm: {MODEL}\n"
        f"vision_llm: {VLM}\n"
        f"embedding: {EMBED}\n"
        f"zotero_item_key: {key}\n"
        "zotero_library: group_6583681\n"
        f"citation_scheme: {citation_scheme}\n"
        "ingest_method: local_pdf_copy\n"
        "synthesis_mode: direct_llm_merge_no_retrieval\n"
        f"template_source: {TEMPLATE_SOURCE}\n"
        f"paperqa_version: {paperqa.__version__}\n"
        f"pdf_sha256: {pdf_hash}\n"
        "prompts_sha256:\n"
        f"{fp_block}\n"
        f"run_started_utc: {started}\n"
        f"index_seconds: {index_seconds}\n"
        "---\n\n"
    )
    body = (
        front
        + f"# {key} 首轮分析（PaperQA2 试点）\n\n"
        + final_text.strip()
        + "\n\n---\n\n# 附录：三次检索 pass 的完整原始回答\n"
        + appendix_block(pass_answers, pass_meta)
    )
    raw_path.write_text(body, encoding="utf-8")

    sections = split_sections(final_text)
    notes = parse_atomic_notes(final_text)
    warnings = []
    if not notes:
        warnings.append("atomic_notes_unparsed: 最终文本中未匹配到'笔记 N：'行")
    if audit["internal_chunk_id_count"] > 0:
        warnings.append(
            f"internal_chunk_ids_present: 检测到 {audit['internal_chunk_id_count']} 处 "
            "pqac- 内部块 id；写作引用前需回原始 PDF 或 paperqa 记录核验"
        )
    analysis = {
        "schema": "reviewBricks-analysis-pilot-v1",
        "zotero_item_key": key,
        "provider": "paperqa2_docs_local",
        "llm": MODEL,
        "embedding_model": EMBED,
        "citation_scheme": citation_scheme,
        "citation_audit": {**audit, "derived_scheme": citation_scheme},
        "pdf_sha256": pdf_hash,
        "run_utc": started,
        "sections": sections,
        "atomic_notes": notes,
        "modules": [],
        "relations": [],
        "provenance": {
            "template_source": TEMPLATE_SOURCE,
            "raw_md_path": str(raw_path),
            "pass_answer_paths": {
                n: str(out_dir / f"{n}.answer.md") for n in pass_answers
            },
            "prompts_sha256": {
                n: {"sha256": fingerprints[n], "path": str(PROMPTS / f"{n}.md")}
                for n in PROMPT_FILES
            },
            "usage": usage,
            "timings": {
                **{f"{n}_seconds": pass_meta[n]["seconds"] for n in pass_meta},
                "index_seconds": index_seconds,
                "synthesis_seconds": synth_seconds,
            },
        },
        "warnings": warnings,
    }
    (out_dir / f"{key}.analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[{key}] DONE -> {raw_path}")
    if update_index:
        write_zotero_index(key)


async def preflight() -> int:
    failures = 0

    def report(idx: int, name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[preflight {idx}/5] {name}: {'PASS' if ok else 'FAIL'}{suffix}")

    # 1. 报告被剥离的撞名环境变量
    stripped = ", ".join(_STRIPPED_ENV) if _STRIPPED_ENV else "(none)"
    report(1, "env-strip", True, f"stripped colliding env vars: {stripped}")

    # 2. PIL 可导入
    try:
        import PIL

        report(2, "pil-import", True, f"PIL {getattr(PIL, '__version__', 'unknown')}")
    except Exception as exc:
        report(2, "pil-import", False, str(exc)[:200])

    # 3. LLM 极小探针
    try:
        await litellm.acompletion(
            model=MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=10,
        )
        report(3, "llm-probe", True, MODEL)
    except Exception as exc:
        report(3, "llm-probe", False, classify_probe_error(exc))

    # 4. VLM 极小探针
    try:
        await litellm.acompletion(
            model=VLM,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=10,
        )
        report(4, "vlm-probe", True, VLM)
    except Exception as exc:
        report(4, "vlm-probe", False, classify_probe_error(exc))

    # 5. embedding 探针（去掉 hybrid-st- 前缀直接加载 SentenceTransformer）
    try:
        from sentence_transformers import SentenceTransformer

        st_name = EMBED.removeprefix("hybrid-st-")
        st_model = SentenceTransformer(st_name)
        vec = st_model.encode(["paperqa2 pilot preflight"])
        report(5, "embedding-probe", True, f"{st_name} dim={len(vec[0])}")
    except Exception as exc:
        report(5, "embedding-probe", False, str(exc)[:200])

    verdict = "ALL PASS" if failures == 0 else str(failures) + " check(s) FAILED"
    print(f"[preflight] {verdict}")
    return 0 if failures == 0 else 1


def parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PaperQA2 pilot runner (v2)")
    parser.add_argument("keys", nargs="*", default=["HXKRUPYI"], help="zotero item keys")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip passes whose meta.json config and prompt hash still match",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="run five preflight checks and exit (no papers required)",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="do not archive existing results/<KEY> before overwrite",
    )
    parser.add_argument(
        "--update-zotero-index",
        action="store_true",
        help="after a successful analysis run, write/update the paperqa2 Zotero index note",
    )
    parser.add_argument(
        "--zotero-index-only",
        action="store_true",
        help="skip analysis; validate existing results/ and write the paperqa2 Zotero index note",
    )
    return parser.parse_args(argv)


async def main() -> int:
    args = parse_args(sys.argv[1:])
    if args.preflight:
        return await preflight()
    if args.zotero_index_only:
        for key in args.keys:
            write_zotero_index(key)
        return 0
    for key in args.keys:
        await run_one(
            key, resume=args.resume, archive=not args.no_archive,
            update_index=args.update_zotero_index,
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
