# -*- coding: utf-8 -*-
"""pass4-v2 Zotero 索引写回层。

规范（研究者批准）：
- 一（条目 × provider×管线版本）一笔记：标签 [reviewBricks:pass4-v2][provider:paperqa2_docs_local]
- 只存指针不存答案正文；SciSpace/pilot 既有笔记零接触
- 安全门：remember:true 强制；同标签损坏笔记→报告停止，绝不静默覆写
- 溯源字段以 meta.json 运行时真值为准（旧结果重建场景与当前常量不同）
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ZOTERO_LIBRARY = "group:6583681"
NOTE_TAG = "[reviewBricks:pass4-v2][provider:paperqa2_docs_local]"
INDEX_FIELDS = (
    "provider", "pipeline", "llm", "vision_llm", "embedding", "citation_scheme",
    "record_json_path", "record_md_path", "raw_output_anchor",
    "metadata_title", "metadata_year", "metadata_doi",
    "gate_choice", "prompts_sha256", "run_utc", "pdf_sha256",
)


def _zotero_client():
    """复用项目已评审的 Zotero Local API 客户端。"""
    root = BASE.parent.parent.parent  # litereature review/
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from review_bricks_workspace import ZoteroLocalApi
    except Exception as exc:
        raise RuntimeError(f"无法导入 review_bricks_workspace.ZoteroLocalApi: {exc}") from exc
    return ZoteroLocalApi(timeout=30)


def build_index_note_text(key: str, *, record: dict, record_path: Path,
                          record_md_path: Path, fingerprints: dict,
                          annotations: dict | None = None) -> str:
    annotations = annotations or {}
    md = record.get("metadata") or {}

    def fp_entry(name: str) -> str:
        suffix = f" ({annotations[name]})" if name in annotations else ""
        return f"{name}: {fingerprints[name]}{suffix}"

    fp_line = ", ".join(fp_entry(n) for n in fingerprints)
    lines = [
        f"{NOTE_TAG} {key}",
        "",
        "provider: paperqa2_docs_local",
        f"pipeline: {record.get('pipeline')}",
        f"llm: {record.get('llm')}",
        f"retrieve_llm: {record.get('retrieve_llm') or ''}",
        f"vision_llm: {record.get('vision_llm') or ''}",
        f"embedding: {record.get('embedding_model')}",
        f"citation_scheme: {record.get('citation_scheme')}",
        f"record_json_path: {record_path.resolve()}",
        f"record_md_path: {record_md_path.resolve()}",
        f"raw_output_anchor: paper-{key.lower()}",
        f"metadata_title: {(md.get('title') or '')[:200]}",
        f"metadata_year: {md.get('year') or ''}",
        f"metadata_doi: {md.get('doi') or ''}",
        f"gate_choice: {(record.get('gate') or {}).get('choice', '')}",
        f"prompts_sha256: {{{fp_line}}}",
        f"run_utc: {record.get('run_started_utc')}",
        f"pdf_sha256: {record.get('pdf_sha256')}",
    ]
    return "\n".join(lines)


def find_existing_note(api, prefix: str, key: str):
    children, _ = api.request(f"{prefix}/items/{key}/children",
                              query={"format": "json", "include": "data"})
    if not isinstance(children, list):
        raise RuntimeError(f"[{key}] unexpected children payload from Zotero")
    for item in children:
        data = api._data(item)
        body = data.get("note", "")
        if NOTE_TAG in body[:200]:
            missing = [f for f in INDEX_FIELDS
                       if not re.search(rf"^{f}:", body, re.MULTILINE)]
            if missing:
                raise SystemExit(
                    f"[{key}] existing pass4-v2 index note {item.get('key')} is malformed "
                    f"(missing fields: {missing}); refusing to overwrite silently"
                )
            return item.get("key"), item.get("version")
    return None, None


def write_index(key: str, *, results_root: Path | None = None) -> str:
    results = (results_root or BASE / "results") / key
    record_path = results / f"{key}.record.json"
    record_md = results / "structured_record.md"
    meta_path = results / "meta.json"
    missing = [p.name for p in (record_path, record_md) if not p.exists()]
    if missing:
        raise SystemExit(f"[{key}] index prerequisites missing: {missing}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    prior_meta = {}
    if meta_path.exists():
        try:
            prior_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            prior_meta = {}
    annotations = prior_meta.get("_prompts_sha256_annotations")
    if not record.get("vision_llm") and prior_meta.get("vlm"):
        record["vision_llm"] = prior_meta["vlm"]  # 旧 record 缺字段时以 meta 运行时真值补齐
    fingerprints = {
        n: entry["sha256"]
        for n, entry in (record.get("provenance", {}).get("prompts_sha256") or {}).items()
    } or (prior_meta.get("prompts_sha256") or {})
    if not fingerprints:
        raise SystemExit(f"[{key}] no prompts_sha256 available in record/meta")

    text = build_index_note_text(
        key, record=record, record_path=record_path, record_md_path=record_md,
        fingerprints=fingerprints, annotations=annotations,
    )

    api = _zotero_client()
    api.status()
    prefix = api.prefix_for_library(ZOTERO_LIBRARY)
    existing_key, existing_version = find_existing_note(api, prefix, key)

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
    payload_item = {"itemType": "note", "parentItem": key, "note": text}
    if mode == "update":
        headers["If-Unmodified-Since-Version"] = str(existing_version)
        resp, _ = api.request(f"{prefix}/items/{existing_key}", method="PUT",
                              payload=payload_item, extra_headers=headers)
    else:
        if library_version:
            headers["If-Unmodified-Since-Version"] = str(library_version)
        resp, _ = api.request(f"{prefix}/items", method="POST",
                              payload=[payload_item], extra_headers=headers)

    note_key = None
    if isinstance(resp, dict):
        successful = resp.get("successful")
        note_key = resp.get("key") or (
            successful.get("0", {}).get("key") if isinstance(successful, dict) else None
        )
    if mode == "update" and not note_key and not resp:
        note_key = existing_key  # Zotero PUT 单条目返回 204 空体即成功
    if not note_key:
        raise SystemExit(f"[{key}] unexpected Zotero response: {str(resp)[:200]}")

    back, _ = api.request(f"{prefix}/items/{note_key}", query={"format": "json"})
    stored = api._data(back).get("note", "")
    lost = [f for f in INDEX_FIELDS if not re.search(rf"^{f}:", stored, re.MULTILINE)]
    if lost or NOTE_TAG not in stored[:200]:
        raise SystemExit(f"[{key}] read-back verification failed; missing: {lost}")
    print(f"[{key}] zotero index note ready: {note_key} (read-back verified)")
    return note_key
