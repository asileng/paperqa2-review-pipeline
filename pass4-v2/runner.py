# -*- coding: utf-8 -*-
"""pass4-v1 单篇管线 runner。

忠实执行 important-guide-for-paperQA2.md 的 4-Pass 结构：
每 Pass = Retrieval A/B（aget_evidence 只积累证据）→ 合并池 → 单次 Extraction 生成。
PASS 3 后 Design Gate（YES/NO/C，C 走一次轻量探针后重判），YES 才进 PASS 4；
随后对 e3 §6 核心概念（≤5）做 definition backfill；最终产出 structured_record.md +
<KEY>.record.json（schema reviewBricks-analysis-pass4-v2）。

所有提示词逐字来自 prompts/*.md（见 GLUE.md 切分映射）；本文件只做装配。
Zotero 零写入。断点续跑 = 产物级（文件存在 + meta 匹配 + prompt 哈希一致）。
"""
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
for _k in list(os.environ):
    if _k.lower() in _COLLIDING:
        del os.environ[_k]

import litellm
import paperqa
from paperqa import Docs, Settings

import zotero_index as zi
from model_router import (
    ModelRouter,
    QuotaExhausted,
    AllProvidersDown,
    classify_llm_error,
    load_router_config,
)

BASE = Path(__file__).resolve().parent
PROMPTS = BASE / "prompts"
RESULTS = BASE / "results"
ARCHIVE = BASE / "results-archive"

MODEL = os.environ.get("PILOT_LLM", "dashscope/qwen3.7-plus-2026-05-26")
VLM = os.environ.get("PILOT_VLM", "dashscope/qwen-vl-plus")
EMBED = "hybrid-st-BAAI/bge-m3"

ALL_PROMPTS = (
    ["00_global_rules", "r1a", "r1b", "e1", "r2a", "r2b", "e2",
     "r3a", "r3b", "e3", "gate", "r4a", "r4b", "e4", "backfill_r", "backfill_e"]
)
_META_MATCH_FIELDS = ("retrieve_model", "extract_model", "vlm", "embed", "paperqa_version")

T_INDEX = float(os.environ.get("P4_T_INDEX", "2700"))
T_RETRIEVE = float(os.environ.get("P4_T_RETRIEVE", "900"))
T_GENERATE = float(os.environ.get("P4_T_GENERATE", "480"))
BACKFILL_CAP = int(os.environ.get("P4_BACKFILL_CAP", "5"))

_PAGE_CITATION_RE = re.compile(r"pages?\s+\d+([-–—]\d+)?")
_CHUNK_ID_RE = re.compile(r"\bpqac-[0-9a-f]+\b")
_CITATION_SCHEME_BASE = "paperqa_doc_keys_author_year"


# ---------- 基础工具（沿袭 pilot-v2 模式） ----------

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
    return {n: sha256_text((PROMPTS / f"{n}.md").read_bytes().decode("utf-8")) for n in ALL_PROMPTS}


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


def synth_usage(resp) -> dict:
    usage = {"model": None, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    try:
        usage["model"] = resp.model
        u = getattr(resp, "usage", None)
        if u is not None:
            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[field] = _jsonable(getattr(u, field, None))
    except Exception:
        pass
    return usage


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def log(key: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}][{key}] {msg}", flush=True)


# ---------- LLM 生成与证据检索 ----------

async def gen(prompt_text: str, model: str) -> tuple[str, dict, float]:
    t = time.time()
    resp = await asyncio.wait_for(
        litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.0,
            num_retries=2,
            timeout=420,
        ),
        timeout=T_GENERATE,
    )
    text = resp.choices[0].message.content or ""
    return text, synth_usage(resp), round(time.time() - t, 1)


class EvidenceTracker:
    """同篇内跨轮次 Context 去重；aget_evidence 只积累不生成答案。"""

    def __init__(self) -> None:
        self._seen = set()

    @staticmethod
    def _key(c):
        cid = getattr(c, "id", None)
        if cid is not None:
            return ("id", str(cid))
        text = getattr(c, "text", None)
        name = getattr(text, "name", repr(text)[:60])
        return ("k", name, c.question)

    async def retrieve(self, docs: Docs, settings: Settings, query: str, key: str, label: str) -> tuple[list, float]:
        t = time.time()
        session = await asyncio.wait_for(
            docs.aget_evidence(query, settings=settings), timeout=T_RETRIEVE
        )
        ctxs = [c for c in session.contexts if c.context and self._key(c) not in self._seen]
        for c in ctxs:
            self._seen.add(self._key(c))
        secs = round(time.time() - t, 1)
        log(key, f"{label}: +{len(ctxs)} new contexts in {secs}s")
        return ctxs, secs


def fmt_contexts(ctxs: list, start_idx: int = 1) -> str:
    # 元数据去重（GLUE v2-dev）：完整 citation 只在合并池头部出现一次，
    # 条目内不再重复 source= 行；anchor 自带 docname+页码，定位能力不损。
    lines = []
    for i, c in enumerate(ctxs, start_idx):
        text = getattr(c, "text", None)
        anchor = getattr(text, "name", "")
        score = getattr(c, "score", None)
        lines.append(f"[E{i:02d}] score={score} | anchor={anchor}\n{c.context}\n")
    return "\n".join(lines)


def pool_header(ctxs: list) -> str:
    """合并池头部：完整 citation 与 docname 仅此处出现一次。"""
    for c in ctxs:
        text = getattr(c, "text", None)
        cite, docname = "", ""
        try:
            cite = text.doc.formatted_citation
            docname = getattr(text.doc, "docname", "")
        except Exception:
            pass
        if cite or docname:
            return f"[pool source] {cite} | docname={docname}\n"
    return ""


# ---------- 产物级 resume ----------

def current_meta(fingerprints: dict, models: dict) -> dict:
    return {
        "retrieve_model": models["retrieve"],
        "extract_model": models["extract"],
        "vlm": models["vision"],
        "embed": EMBED,
        "paperqa_version": paperqa.__version__,
        "prompts_sha256": dict(fingerprints),
    }


def load_meta(out_dir: Path) -> dict:
    p = out_dir / "meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


class ResumeBook:
    def __init__(self, out_dir: Path, cur_meta: dict, enabled: bool) -> None:
        self.out_dir = out_dir
        self.cur = cur_meta
        self.enabled = enabled
        self.prior = load_meta(out_dir)

    def cfg_ok(self) -> bool:
        pr = self.prior
        if not pr:
            return False
        if not all(pr.get(f) == self.cur[f] for f in _META_MATCH_FIELDS):
            return False
        ph = pr.get("prompts_sha256") or {}
        return all(ph.get(n) == self.cur["prompts_sha256"][n] for n in ALL_PROMPTS)

    def usable(self, *names: str) -> bool:
        if not self.enabled:
            return False
        if not self.cfg_ok():
            pr = self.prior
            ph = pr.get("prompts_sha256") or {}
            diff = [n for n in self.cur["prompts_sha256"] if ph.get(n) != self.cur["prompts_sha256"][n]]
            mf = [f for f in _META_MATCH_FIELDS if pr.get(f) != self.cur[f]]
            print(
                f"[resume] cfg mismatch: meta_fields={mf} prompt_hash_diff={diff} "
                f"(prior_empty={not pr})",
                flush=True,
            )
            return False
        missing = [n for n in names if not (self.out_dir / n).exists()]
        if missing:
            print(f"[resume] missing artifacts: {missing}", flush=True)
            return False
        return True

    def mark_current(self) -> None:
        write_json(self.out_dir / "meta.json", self.cur)


# ---------- 解析辅助 ----------

def parse_gate_choice(raw: str) -> str | None:
    m = re.search(r"Choice\s*[:：]?\s*\(?\s*(A|B|C)\b", raw, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(A|B|C)\s*[\.、]", raw)
    return m.group(1).upper() if m else None


def parse_concepts(e3_text: str) -> list[str]:
    # §6 是 e3 的最后一节（guide 固定结构）：直接切到文末，避免把 Concept 子标题误当边界
    m = re.search(r"^#+\s*\d*\.?\s*Core Concepts.*$", e3_text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return []
    block = e3_text[m.end():]
    concepts = []
    # 风格 A（guide 模板）：- **Concept**: X
    for mm in re.finditer(r"\*\*Concept\*\*\s*[:：]?\s*(.+)", block):
        v = mm.group(1).strip().strip("-*")
        if v and len(v) < 120:
            concepts.append(v)
    # 风格 B（模型实测两种变体）：### / #### Concept N: X
    for mm in re.finditer(r"#{2,6}\s*Concept\s*\d*\s*[:：]\s*(.+)", block):
        v = mm.group(1).strip()
        if v and len(v) < 120:
            concepts.append(v)
    seen, out = set(), []
    for c in concepts:
        cl = c.lower()
        if cl not in seen:
            seen.add(cl)
            out.append(c)
    return out[:BACKFILL_CAP]


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "-", s).strip("-")
    return s[:60] or "concept"


# ---------- 确定性引用解析（GLUE v2-dev，无 LLM） ----------

_YEAR_RE = re.compile(r"(\d{4}[a-z]?)")
_BIB_HEAD_RE = re.compile(r"(?im)^\s*(references|bibliography|参考文献|引用文献)\s*$")


def _collect_doc_text(docs) -> str:
    # paperqa Docs: 参考文献文本在 docs.texts（Text 对象扁平列表），
    # 不在 docs.docs（dict[dockey, DocDetails]）。
    parts = []
    try:
        for t in getattr(docs, "texts", []) or []:
            parts.append(getattr(t, "text", "") or "")
    except Exception:
        pass
    return "\n".join(parts)


_BIB_MARKER_RE = re.compile(r"^\s*\[?\d+\]?\.?\s*")
_HYPHEN_BREAK_RE = re.compile(r"-\s+([a-zàáâäéèêëíìîïóòôöúùûüñç])")


def _clean_bib_entry(raw: str) -> str:
    """修复 PDF 抽取导致的连字符换行断词与多余空白。"""
    e = _BIB_MARKER_RE.sub("", raw)
    e = _HYPHEN_BREAK_RE.sub(r"\1", e)  # Brid- gette -> Bridgette
    e = re.sub(r"\s+", " ", e).strip()
    return e


def _extract_bib_entries(full: str) -> list[str]:
    """从本文参考文献表确定性抽取全部 APA 条目（含题名）。无 LLM。"""
    m = _BIB_HEAD_RE.search(full)
    bib = full[m.end():] if m else full
    raw = re.split(r"\n\s*(?=\[\d+\]|\d{1,3}\s*[\.\)]\s)", bib)
    entries = []
    for e in raw:
        e = e.strip()
        if len(e) >= 25 and _YEAR_RE.search(e):
            entries.append(_clean_bib_entry(e))
    return entries


def resolve_references(docs, e1_text: str = "") -> str:
    """确定性抽取本文参考文献表全部 APA 条目（含题名），无 LLM。

    直接从文章末尾的参考文献区抽取整条 APA，作为可查询的 prior-work 索引。
    """
    full = _collect_doc_text(docs)
    entries = _extract_bib_entries(full)
    if not entries:
        return "_未从本文参考文献表解析到条目。_\n"
    lines = ["| # | APA 条目（含题名） |", "|---|---|"]
    for i, e in enumerate(entries, 1):
        lines.append(f"| {i} | {e} |")
    return "\n".join(lines) + "\n"


# ---------- 主流程 ----------

_KINDS = ("retrieve", "extract", "vision")


def _assign_provider(key: str, out_dir: Path, router: ModelRouter,
                     force_provider: str | None = None) -> tuple[str, dict]:
    """论文级 provider 分配（原子单位）。优先级：历史三元组钉定 > force > 自动。

    - 若 results/<key>/meta.json 已有完整三元组 → 钉死原 provider（同模型断点续跑）；
      原 provider 仍在冷却 → 抛 QuotaExhausted（batch 记 cooldown，不换源重跑）
    - 全新论文 → router.pick_provider() 取第一个健康 provider
    """
    prior = load_meta(out_dir)
    triple = {k: prior.get(f"{k}_model") if k != "vision" else prior.get("vlm") for k in _KINDS}
    if all(triple.values()):
        prov = router.provider_for(triple)
        if prov is not None:
            rem = router.cooldown_remaining(prov)
            if rem > 0:
                raise QuotaExhausted(prov, time.time() + rem)
            models = {"provider": prov, **{k: router.model_for(k, prov) for k in _KINDS}}
            log(key, f"pinned to prior provider '{prov}' for same-model resume")
            return prov, models
        log(key, "prior meta triple unknown to current chains; treating as fresh assignment")
    prov = router.pick_provider(force=force_provider)
    models = {"provider": prov, **{k: router.model_for(k, prov) for k in _KINDS}}
    log(key, f"assigned provider='{prov}' retrieve={models['retrieve']} "
             f"extract={models['extract']} vision={models['vision']}")
    return prov, models


async def run_one(entry: dict, resume: bool = True, archive: bool = True,
                  update_index: bool = False,
                  router: ModelRouter | None = None,
                  force_provider: str | None = None) -> dict:
    router = router or ModelRouter(*load_router_config())
    key = entry["zotero_key"]
    out_dir = RESULTS / key
    provider, models = _assign_provider(key, out_dir, router, force_provider)
    try:
        return await _run_one_inner(entry, resume=resume, archive=archive,
                                    update_index=update_index, models=models, router=router)
    except QuotaExhausted:
        log(key, f"QUOTA deferred on '{provider}'; partial artifacts preserved for same-provider resume")
        raise
    except Exception as exc:
        kind = router.note_error(exc, provider)  # auth→原样上抛；quota→转 QuotaExhausted
        log(key, f"FAILED ({kind}): {exc}")
        raise


async def _run_one_inner(entry: dict, *, resume: bool, archive: bool,
                         update_index: bool, models: dict, router: ModelRouter) -> dict:
    provider = models["provider"]
    r_model, x_model, v_model = models["retrieve"], models["extract"], models["vision"]
    key = entry["zotero_key"]
    pdf = Path(entry["pdf_path"])
    if not pdf.exists():
        raise FileNotFoundError(pdf)

    out_dir = RESULTS / key
    record_md = out_dir / "structured_record.md"
    if not resume and archive and record_md.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = ARCHIVE / f"{key}-{ts}" / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out_dir), str(dest))
        log(key, f"archived previous results -> {dest}")
    out_dir.mkdir(parents=True, exist_ok=True)
    pools_dir = out_dir / "pools"
    bf_dir = out_dir / "backfill"

    started = datetime.now(timezone.utc).isoformat()
    fingerprints = prompt_fingerprints()
    book = ResumeBook(out_dir, current_meta(fingerprints, models), resume)
    pdf_hash = sha256_of(pdf)
    timings: dict = {}
    usage_acc: dict = {}
    warnings: list[str] = []

    def acc_usage(stage: str, u: dict) -> None:
        usage_acc[stage] = u

    settings = build_settings(r_model, v_model)

    # ---- 索引（pickle 检查点，仅加载本目录自产文件） ----
    docs = None
    ckpt_cfg = {
        "paperqa_version": paperqa.__version__,
        "pdf_sha256": pdf_hash,
        "vlm": v_model,
        "embed": EMBED,
    }
    docs_pkl = out_dir / "docs.pkl"
    docs_meta = out_dir / "docs.meta.json"
    if docs_pkl.exists() and docs_meta.exists():
        try:
            prior = json.loads(docs_meta.read_text(encoding="utf-8"))
            if all(prior.get(k) == v for k, v in ckpt_cfg.items()):
                with open(docs_pkl, "rb") as f:
                    docs = pickle.load(f)
                log(key, "docs checkpoint reused")
        except Exception as exc:
            log(key, f"docs checkpoint load failed ({exc}); full aadd")
            docs = None
    if docs is None:
        docs = Docs()
        t0 = time.time()
        await asyncio.wait_for(docs.aadd(str(pdf), settings=settings), timeout=T_INDEX)
        timings["index_seconds"] = round(time.time() - t0, 1)
        log(key, f"indexed in {timings['index_seconds']}s")
        try:
            with open(docs_pkl, "wb") as f:
                pickle.dump(docs, f)
            docs_meta.write_text(json.dumps(ckpt_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log(key, f"WARN docs checkpoint write failed: {exc}")

    tracker = EvidenceTracker()
    GLOBAL = load_prompt("00_global_rules")

    def rel(p: Path) -> str:
        return str(p.relative_to(out_dir))

    # ---- PASS 1–3 ----
    passes = {}
    answers = {}
    plan = [
        ("pass1", [("1a", "r1a"), ("1b", "r1b")], "e1"),
        ("pass2", [("2a", "r2a"), ("2b", "r2b")], "e2"),
        ("pass3", [("3a", "r3a"), ("3b", "r3b")], "e3"),
    ]
    for pname, retrievals, ename in plan:
        ans_path = out_dir / f"{ename}.answer.md"
        pool_paths = [pools_dir / f"pool{tag}.md" for tag, _ in retrievals]
        merged_path = pools_dir / f"pool_{pname}.md"
        if book.usable(ans_path.name, *[rel(p) for p in pool_paths], rel(merged_path)):
            answers[pname] = ans_path.read_text(encoding="utf-8")
            passes[pname] = {"resumed": True, "extraction_path": str(ans_path),
                             "pool_path": str(merged_path)}
            log(key, f"{pname} resumed")
            continue
        pools_dir.mkdir(parents=True, exist_ok=True)
        parts, idx, secs, all_ctxs = [], 1, {}, []
        for tag, rname in retrievals:
            ctxs, s = await tracker.retrieve(docs, settings, load_prompt(rname), key, f"{pname}/{tag}")
            sub = fmt_contexts(ctxs, idx)
            (pools_dir / f"pool{tag}.md").write_text(sub, encoding="utf-8")
            secs[tag] = s
            idx += len(ctxs)
            parts.append(sub)
            all_ctxs.extend(ctxs)
        pool_md = pool_header(all_ctxs) + "\n".join(p for p in parts if p.strip())
        merged_path.write_text(pool_md, encoding="utf-8")
        user_msg = (
            f"{GLOBAL}\n\n=== RETRIEVED EVIDENCE ({pname.upper()} POOL) ===\n\n{pool_md}\n\n"
            f"=== EXTRACTION TASK ===\n\n{load_prompt(ename)}"
        )
        if pname == "pass2":
            ref = answers.get("pass1") or (
                (out_dir / "e1.answer.md").read_text(encoding="utf-8") if (out_dir / "e1.answer.md").exists() else ""
            )
            user_msg += (
                "\n\n=== REFERENCE: PASS 1 EXTRACTION OUTPUT (Research Questions live here; "
                "do not re-derive them) ===\n\n" + ref
            )
        text, usg, gsec = await gen(user_msg, x_model)
        ans_path.write_text(text, encoding="utf-8")
        acc_usage(pname, usg)
        timings[f"{pname}_seconds"] = gsec
        timings[f"{pname}_retrieval"] = secs
        answers[pname] = text
        passes[pname] = {"resumed": False, "extraction_path": str(ans_path),
                         "pool_path": str(merged_path), "seconds": gsec}
        book.mark_current()
        log(key, f"{pname} extracted in {gsec}s")

    # ---- PASS 1 引用解析（确定性脚本，无 LLM；GLUE v2-dev） ----
    ref_md_path = out_dir / "e1.references.md"
    e1_ans_path = out_dir / "e1.answer.md"
    if e1_ans_path.exists() and not ref_md_path.exists():
        try:
            e1_text = e1_ans_path.read_text(encoding="utf-8")
            ref_md = resolve_references(docs)
            ref_md_path.write_text(
                "# References — Full APA (deterministic extraction)\n\n"
                "> 由固定脚本直接从本文末尾参考文献区确定性抽取整条 APA，未调用 LLM。\n\n" + ref_md,
                encoding="utf-8",
            )
            log(key, "e1.references.md generated (deterministic)")
        except Exception as exc:
            log(key, f"WARN reference resolution failed: {exc}")

    # ---- GATE ----
    gate_path = out_dir / "gate.json"
    probe_pool_path = pools_dir / "pool_gate_probe.md"
    gate_info = None
    if book.usable(gate_path.name):
        gate_info = json.loads(gate_path.read_text(encoding="utf-8"))
        log(key, f"gate resumed: {gate_info['choice']}")
    else:
        def _pool_text(pname: str) -> str:
            p = Path(passes[pname]["pool_path"])
            return p.read_text(encoding="utf-8") if p.exists() else ""

        pools_digest = "\n\n".join(
            f"### evidence pool — {pname}\n\n{_pool_text(pname)}"
            for pname in ("pass1", "pass2", "pass3")
        )
        gate_prompt = f"{GLOBAL}\n\n=== ACCUMULATED EVIDENCE (POOLS 1-3) ===\n\n{pools_digest}\n\n=== TASK ===\n\n{load_prompt('gate')}"
        raw_gate, usg, gs = await gen(gate_prompt, x_model)
        acc_usage("gate", usg)
        choice = parse_gate_choice(raw_gate)
        probe_used = False
        if choice == "C":
            log(key, "gate C -> light probe retrieval")
            probe_ctxs, ps = await tracker.retrieve(docs, settings, load_prompt("r4a"), key, "gate-probe")
            probe_used = True
            probe_md = pool_header(probe_ctxs) + fmt_contexts(probe_ctxs)
            pools_dir.mkdir(parents=True, exist_ok=True)
            probe_pool_path.write_text(probe_md, encoding="utf-8")
            gate_prompt2 = gate_prompt + f"\n\n=== ADDITIONAL PROBE EVIDENCE (lightweight retrieval) ===\n\n{probe_md}"
            raw_gate, usg2, gs2 = await gen(gate_prompt2, x_model)
            acc_usage("gate_probe", usg2)
            gs += gs2
            choice = parse_gate_choice(raw_gate) or "A"
            timings["gate_probe_seconds"] = ps
        elif choice is None:
            warnings.append("gate_choice_unparsed: 输出未匹配 A/B/C，按 B(skip) 处理")
            choice = "B"
        timings["gate_seconds"] = gs
        qm = re.search(r"(?:Evidence Quote|Evidence\s+Quote)\s*[:：]?\s*(.+)", raw_gate)
        lm = re.search(r"(?:Location)\s*[:：]?\s*(.+)", raw_gate)
        gate_info = {
            "choice": choice,
            "probe_used": probe_used,
            "evidence_quote": (qm.group(1).strip()[:500] if qm else ""),
            "location": (lm.group(1).strip()[:200] if lm else ""),
            "raw": raw_gate,
        }
        write_json(gate_path, gate_info)
        book.mark_current()
        log(key, f"gate => {choice}")

    # ---- PASS 4 ----
    pass4 = {"skipped": True}
    if gate_info["choice"] in ("A", "C"):
        ans4 = out_dir / "e4.answer.md"
        pool4a, pool4b, pool4m = pools_dir / "pool4a.md", pools_dir / "pool4b.md", pools_dir / "pool_pass4.md"
        if book.usable(ans4.name, rel(pool4a), rel(pool4b), rel(pool4m)):
            answers["pass4"] = ans4.read_text(encoding="utf-8")
            pass4 = {"skipped": False, "resumed": True, "extraction_path": str(ans4), "pool_path": str(pool4m)}
            log(key, "pass4 resumed")
        else:
            parts, idx, secs, all_ctxs = [], 1, {}, []
            for tag, rname in (("4a", "r4a"), ("4b", "r4b")):
                ctxs, s = await tracker.retrieve(docs, settings, load_prompt(rname), key, f"pass4/{tag}")
                sub = fmt_contexts(ctxs, idx)
                (pools_dir / f"pool{tag}.md").write_text(sub, encoding="utf-8")
                secs[tag] = s
                idx += len(ctxs)
                parts.append(sub)
                all_ctxs.extend(ctxs)
            pool_md = pool_header(all_ctxs) + "\n".join(p for p in parts if p.strip())
            pool4m.parent.mkdir(parents=True, exist_ok=True)
            pool4m.write_text(pool_md, encoding="utf-8")
            text, usg, gsec = await gen(
                f"{GLOBAL}\n\n=== RETRIEVED EVIDENCE (PASS 4 POOL) ===\n\n{pool_md}\n\n"
                f"=== EXTRACTION TASK ===\n\n{load_prompt('e4')}", x_model)
            ans4.write_text(text, encoding="utf-8")
            acc_usage("pass4", usg)
            timings["pass4_seconds"] = gsec
            timings["pass4_retrieval"] = secs
            answers["pass4"] = text
            pass4 = {"skipped": False, "resumed": False, "extraction_path": str(ans4),
                     "pool_path": str(pool4m), "seconds": gsec}
            book.mark_current()
            log(key, f"pass4 extracted in {gsec}s")
    else:
        log(key, "gate B -> skip pass4")

    # ---- CONCEPT BACKFILL ----
    bf_dir.mkdir(parents=True, exist_ok=True)
    concepts = parse_concepts(answers.get("pass3", ""))
    backfills = []
    if not concepts:
        warnings.append("concepts_unparsed: e3 未解析出 Core Concepts 清单，跳过回填")
    for i, concept in enumerate(concepts[:BACKFILL_CAP], 1):
        slug = slugify(concept)
        bf_ans = bf_dir / f"{i:02d}_{slug}.md"
        bf_pool = bf_dir / f"{i:02d}_{slug}.pool.md"
        if book.usable(rel(bf_ans), rel(bf_pool)):
            backfills.append({"concept": concept, "path": str(bf_ans), "resumed": True})
            continue
        ctxs, s = await tracker.retrieve(
            docs, settings, load_prompt("backfill_r").replace("{concept}", concept), key, f"backfill:{slug}"
        )
        pool_md = pool_header(ctxs) + fmt_contexts(ctxs)
        bf_pool.write_text(pool_md, encoding="utf-8")
        text, usg, gsec = await gen(
            f"{GLOBAL}\n\n=== RETRIEVED EVIDENCE (CONCEPT: {concept}) ===\n\n{pool_md}\n\n"
            f"=== EXTRACTION TASK ===\n\n{load_prompt('backfill_e').replace('{concept}', concept)}",
            x_model,
        )
        bf_ans.write_text(text, encoding="utf-8")
        acc_usage(f"backfill_{i}", usg)
        timings[f"backfill_{i}_seconds"] = gsec
        backfills.append({"concept": concept, "path": str(bf_ans), "seconds": gsec})
        book.mark_current()
        log(key, f"backfill {i}/{len(concepts)} '{slug}' in {gsec}s")

    # ---- 装配 structured record ----
    audit_texts = []
    sec_blocks = []
    order = [("PASS 1 — Research Position & Gap", "pass1", "e1"),
             ("PASS 2 — Methodology / Material / Data & Evidence", "pass2", "e2"),
             ("PASS 3 — Thesis / Main Claims / Results", "pass3", "e3")]
    if not pass4.get("skipped"):
        order.append(("PASS 4 — Design & Intended Effect", "pass4", "e4"))
    fp_block = "\n".join(f"  {n}: {fingerprints[n][:12]}" for n in ALL_PROMPTS)
    front = (
        "---\n"
        "provider: paperqa2_docs_local\n"
        f"pipeline: pass4-v2\n"
        f"llm: {x_model}\n"
        f"retrieve_llm: {r_model}\n"
        f"vision_llm: {v_model}\n"
        f"routing_provider: {provider}\n"
        f"embedding: {EMBED}\n"
        f"zotero_item_key: {key}\n"
        f"sections_zotero: {', '.join(entry.get('sections', []))}\n"
        f"title: {entry.get('title', '')}\n"
        f"item_type: {entry.get('item_type', '')}\n"
        f"doi: {entry.get('doi', '')}\n"
        f"year: {entry.get('year', '')}\n"
        "ingest_method: local_pdf_from_zotero_storage\n"
        "citation_scheme: PENDING_AUDIT\n"
        f"paperqa_version: {paperqa.__version__}\n"
        f"pdf_sha256: {pdf_hash}\n"
        "prompts_sha256:\n" + fp_block + "\n"
        f"run_started_utc: {started}\n"
        "---\n\n"
    )
    body_parts = [f"# {key} — 4-PASS STRUCTURED PAPER RECORD\n"]
    for title, pname, ename in order:
        ans = answers[pname]
        audit_texts.append(ans)
        body_parts.append(f"\n---\n\n# {title}\n\n{ans.strip()}\n")
    if backfills:
        body_parts.append("\n---\n\n# CONCEPT DEFINITION BACKFILL\n")
        for b in backfills:
            body_parts.append(f"\n## {b['concept']}\n\n{Path(b['path']).read_text(encoding='utf-8').strip()}\n")
            audit_texts.append(Path(b["path"]).read_text(encoding="utf-8"))
    ref_md_path = out_dir / "e1.references.md"
    if ref_md_path.exists():
        _ref_txt = ref_md_path.read_text(encoding="utf-8").strip()
        body_parts.append(f"\n---\n\n# REFERENCES — FULL APA (deterministic extraction)\n\n{_ref_txt}\n")
        audit_texts.append(_ref_txt)
    body = "".join(body_parts)
    audit = audit_citations(body)
    scheme = derive_citation_scheme(audit)
    front = front.replace("citation_scheme: PENDING_AUDIT", f"citation_scheme: {scheme}")
    record_md.write_text(front + body, encoding="utf-8")

    if audit["internal_chunk_id_count"] > 0:
        warnings.append(
            f"internal_chunk_ids_present: {audit['internal_chunk_id_count']} 处 pqac-* 内部块 id，写作引用前需核验"
        )

    sections_by_pass = {pname: split_sections(answers[pname]) for pname in answers}
    record = {
        "schema": "reviewBricks-analysis-pass4-v2",
        "zotero_item_key": key,
        "metadata": {
            "title": entry.get("title"),
            "authors": entry.get("authors"),
            "year": entry.get("year"),
            "doi": entry.get("doi"),
            "venue": entry.get("venue"),
            "publisher": entry.get("publisher"),
            "item_type": entry.get("item_type"),
            "sections": entry.get("sections"),
        },
        "provider": "paperqa2_docs_local",
        "pipeline": "pass4-v2",
        "llm": x_model,
        "retrieve_llm": r_model,
        "models": dict(models),
        "embedding_model": EMBED,
        "citation_scheme": scheme,
        "citation_audit": {**audit, "derived_scheme": scheme},
        "pdf_sha256": pdf_hash,
        "run_started_utc": started,
        "gate": {k: v for k, v in gate_info.items() if k != "raw"},
        "passes": {**passes, "pass4": pass4},
        "sections": sections_by_pass,
        "backfill": backfills,
        "resolved_references_md_path": str(ref_md_path) if ref_md_path.exists() else None,
        "modules": [],
        "relations": [],
        "provenance": {
            "record_md_path": str(record_md),
            "routing_provider": provider,
            "router_snapshot": router.snapshot(),
            "prompts_sha256": {
                n: {"sha256": fingerprints[n], "path": str(PROMPTS / f"{n}.md")} for n in ALL_PROMPTS
            },
            "usage": usage_acc,
            "timings": timings,
        },
        "warnings": warnings,
    }
    write_json(out_dir / f"{key}.record.json", record)
    book.mark_current()
    log(key, f"DONE -> {record_md}")
    if update_index:
        zi.write_index(key)
    return {"status": "done", "key": key, "record": str(record_md)}


_SETTINGS_CACHE: dict = {}


def build_settings(retrieve_model: str, vision_model: str) -> Settings:
    """paperqa 内部调用（aget_evidence 摘要 / aadd 图像增强）按角色取模型；
    openai/* 走全局 OPENAI_API_BASE(Go 网关)，dashscope/* 走 DASHSCOPE_API_KEY。"""
    key = (retrieve_model, vision_model)
    if key not in _SETTINGS_CACHE:
        s = Settings(llm=retrieve_model, summary_llm=retrieve_model, embedding=EMBED, temperature=0.0)
        s.parsing.enrichment_llm = vision_model
        _SETTINGS_CACHE[key] = s
    return _SETTINGS_CACHE[key]


# ---------- preflight（逐链探活 + 路由冷却预热） ----------

def classify_probe_error(exc: Exception) -> str:
    kind, reset = classify_llm_error(exc)
    if kind == "quota":
        mins = int((reset - time.time()) / 60) if reset else 0
        return f"限额冷却 ~{mins}min"
    if kind == "auth":
        return f"认证失败 ({str(exc)[:120]})"
    if kind == "transient":
        return f"瞬态 ({str(exc)[:120]})"
    return str(exc)[:160]


async def _probe_one(model: str) -> tuple[bool, str, str, float | None]:
    try:
        await asyncio.wait_for(
            litellm.acompletion(model=model, messages=[{"role": "user", "content": "ping"}],
                                max_tokens=8, num_retries=0, timeout=90),
            timeout=100,
        )
        return True, "OK", "ok", None
    except Exception as exc:
        kind, reset = classify_llm_error(exc)
        return False, classify_probe_error(exc), kind, reset


async def preflight(router: ModelRouter | None = None) -> int:
    """对三条角色链的每个唯一条目做轻量 ping；quota 信号直接预热 router 冷却。

    判定：存在某 provider 使其 retrieve/extract/vision 三条全部 OK → PASS。
    """
    router = router or ModelRouter(*load_router_config())
    print("[preflight] env-strip: colliding vars stripped at import", flush=True)
    try:
        import PIL
        print(f"[preflight] pil-import: PASS (PIL {getattr(PIL, '__version__', 'unknown')})", flush=True)
    except Exception as exc:
        print(f"[preflight] pil-import: FAIL {str(exc)[:120]}", flush=True)
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        print("[preflight] embedding-import: PASS", flush=True)
    except Exception as exc:
        print(f"[preflight] embedding-import: FAIL {str(exc)[:120]}", flush=True)

    ok_by_provider: dict[str, set] = {}
    seen: set = set()
    for kind in ("retrieve", "extract", "vision"):
        for entry in router.chains[kind]:
            tag = (entry["provider"], entry["model"])
            if tag in seen:
                continue
            seen.add(tag)
            alive, detail, ekind, ereset = await _probe_one(entry["model"])
            status = "OK " if alive else "DOWN"
            print(f"[preflight] {status} [{entry['provider']}/{kind}] {entry['model']} — {detail}", flush=True)
            if alive:
                ok_by_provider.setdefault(entry["provider"], set()).add(kind)
            elif ekind in ("quota", "fatal") and ereset:
                # quota 与 fatal 都要预热冷却——否则 pick_provider 会把论文派给已知死掉的 provider
                router.mark_quota(entry["provider"], ereset)
                print(f"[preflight]   -> cooldown primed for '{entry['provider']}' "
                      f"({ekind}) until {time.strftime('%H:%M:%S', time.localtime(ereset))}", flush=True)

    healthy = [p for p in router.order if ok_by_provider.get(p, set()) >= {"retrieve", "extract", "vision"}]
    if healthy:
        print(f"[preflight] RECOMMENDED provider(s): {healthy}", flush=True)
        print("[preflight] ALL CHAINS PROBED — PASS", flush=True)
        return 0
    print("[preflight] NO fully-healthy provider across all three roles", flush=True)
    cds = router.cooldowns()
    if cds:
        for p, t in sorted(cds.items()):
            print(f"[preflight] cooldown {p}: resets {time.strftime('%H:%M:%S', time.localtime(t))}", flush=True)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="pass4-v2 single-paper runner (fused: 4-Pass + Zotero index)")
    parser.add_argument("keys", nargs="*", help="zotero item keys (resolved via queue)")
    parser.add_argument("--queue", default=str(BASE / "queue" / "papers_queue.json"))
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--update-zotero-index", action="store_true",
                        help="after a successful run, write/update the pass4-v2 Zotero index note")
    parser.add_argument("--zotero-index-only", action="store_true",
                        help="skip analysis; validate existing results/ and write the Zotero index note")
    parser.add_argument("--provider", default="auto", choices=["auto", "go", "dashscope"],
                        help="force provider for this run (default: auto with cooldown fallback)")
    args = parser.parse_args(sys.argv[1:])
    if args.preflight:
        sys.exit(asyncio.run(preflight()))
    if args.zotero_index_only:
        for k in args.keys:
            zi.write_index(k)
        return 0
    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    by_key = {p["zotero_key"]: p for p in queue["papers"]}
    missing = [k for k in args.keys if k not in by_key]
    if missing:
        raise SystemExit(f"keys not in queue: {missing}")
    router = ModelRouter(*load_router_config())
    force = None if args.provider == "auto" else args.provider
    results = []
    for k in args.keys:
        try:
            r = asyncio.run(run_one(by_key[k], resume=not args.no_resume,
                                    archive=not args.no_archive,
                                    update_index=args.update_zotero_index,
                                    router=router, force_provider=force))
            results.append(r)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            log(k, f"FAILED: {exc}")
            results.append({"status": "failed", "key": k, "error": str(exc)[:300]})
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
