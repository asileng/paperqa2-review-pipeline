# -*- coding: utf-8 -*-
"""A 层驱动：调用仓库 pass4-v2 的 zotero_index 为已完成篇写索引笔记（带本地密钥缓存）。

用法: python zotero_index_driver.py KEY [KEY...]
结果根目录固定指向 pass4-v1/results（15 篇记录所在地），零搬动。

密钥缓存设计（Zotero Local API 每次 POST local/authorize 都会弹窗；"始终允许"
返回的密钥由客户端负责跨运行保存复用，见 pyzotero 文档）：
- 缓存文件: %APPDATA%\\opencode\\zotero_local_api.key（纯文本单行，位于 git 仓库之外）
- 启动命中缓存 → 注入预置客户端，authorize_write 直接返回已存密钥，全程零弹窗；
- 无缓存 → authorize_write() 恰好一次（研究者点一次 始终允许），随即落盘缓存；
- 自愈：写入收到 401/403 → 删除缓存 → 重新授权一次 → 重写缓存并对该篇重试一次；
- 安全：日志只输出指纹（前 4 位 + 长度），绝不打印完整密钥。
"""
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_V2 = Path(r"D:\task\科研\HCI+\litereature review\paperqa2\review-pipeline-repo\pass4-v2")
REPO_ROOT = REPO_V2.parent.parent.parent
RESULTS = Path(r"D:\task\科研\HCI+\litereature review\paperqa2\integration-tests\pass4-v1\results")
KEY_CACHE = Path(os.environ["APPDATA"]) / "opencode" / "zotero_local_api.key"
sys.path.insert(0, str(REPO_V2))
sys.path.insert(0, str(REPO_ROOT))
import zotero_index as zi  # noqa: E402
from review_bricks_workspace import ZoteroLocalApi, ZoteroLocalApiError  # noqa: E402


def key_fp(value) -> str:
    text = str(value or "")
    return f"{text[:4]}..{len(text)}" if text else "<empty>"


def load_cached_key() -> "str | None":
    try:
        raw = KEY_CACHE.read_text(encoding="utf-8").strip()
        return raw or None
    except OSError:
        return None


def store_key(value: str) -> None:
    KEY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    KEY_CACHE.write_text(value + "\n", encoding="utf-8")


def delete_cached_key() -> None:
    try:
        KEY_CACHE.unlink(missing_ok=True)
    except OSError:
        pass


def make_client(cached_key: "str | None") -> ZoteroLocalApi:
    """新建客户端并建立会话；有缓存密钥则注入为持久授权（后续写零弹窗）。"""
    api = zi._zotero_client()
    api.timeout = 120  # 授权对话框需人工点击；默认 30s 会在研究者确认前超时
    api.status()
    if cached_key:
        api.api_key = cached_key
        api.authorization_persistent = True
    return api


def ensure_durable_session(cached_key: "str | None") -> ZoteroLocalApi:
    if cached_key:
        print(f"[startup] cache hit: {KEY_CACHE} key_fp={key_fp(cached_key)} (expect ZERO dialogs)", flush=True)
        return make_client(cached_key)
    print("[startup] no cached key; ONE authorization dialog expected - 请选择 始终允许 / Always Allow", flush=True)
    api = make_client(None)
    key = api.authorize_write()
    if not getattr(api, "authorization_persistent", False):
        raise SystemExit(
            "[zotero] durable authorization missing (remember != true). "
            "请在 Zotero 中选择 始终允许 / Always Allow 后重试；不使用一次性密钥写入。"
        )
    store_key(key)
    print(f"[startup] durable key cached to {KEY_CACHE} key_fp={key_fp(key)}", flush=True)
    return api


def refresh_authorization(session: dict) -> None:
    """自愈路径：丢弃失效缓存，重新授权恰好一次并落盘新密钥。"""
    delete_cached_key()
    session["api"] = ensure_durable_session(None)


def write_one(api: ZoteroLocalApi, key: str) -> str:
    """复刻 zotero_index.write_index 的逻辑，但使用调用方预置的同一客户端实例，
    避免每篇论文各建新客户端、各自重新弹窗授权。"""
    results = RESULTS / key
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

    text = zi.build_index_note_text(
        key, record=record, record_path=record_path, record_md_path=record_md,
        fingerprints=fingerprints, annotations=annotations,
    )

    prefix = api.prefix_for_library(zi.ZOTERO_LIBRARY)
    existing_key, existing_version = zi.find_existing_note(api, prefix, key)
    _, lib_headers = api.request(f"{prefix}/items", query={"format": "json", "limit": "1"})
    library_version = lib_headers.get("Last-Modified-Version")

    api_key = api.authorize_write()  # 预置缓存密钥时立即返回，不触发对话框
    if not getattr(api, "authorization_persistent", False):
        raise SystemExit(
            "[zotero] durable authorization missing (remember != true). "
            "请在 Zotero 中选择 始终允许 / Always Allow 后重试；不使用一次性密钥写入。"
        )

    mode = "update" if existing_key else "create"
    print(f"[{key}] zotero write target: {zi.ZOTERO_LIBRARY} parent={key} mode={mode} key_fp={key_fp(api_key)}", flush=True)
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
    lost = [f for f in zi.INDEX_FIELDS if not re.search(rf"^{f}:", stored, re.MULTILINE)]
    if lost or zi.NOTE_TAG not in stored[:200]:
        raise SystemExit(f"[{key}] read-back verification failed; missing: {lost}")
    print(f"[{key}] zotero index note ready: {note_key} (read-back verified)", flush=True)
    return note_key


def main() -> int:
    def note_failure(container: list, exc: Exception, key: str, attempt: int) -> None:
        msg = repr(exc)[:160]
        print(f"[{key}] attempt {attempt} FAILED: {msg}", flush=True)
        if attempt == 3:
            container.append((key, msg))
        else:
            time.sleep(30)

    session = {"api": ensure_durable_session(load_cached_key())}
    ok, failed = [], []
    for i, key in enumerate(sys.argv[1:]):
        if i:
            time.sleep(15)  # Zotero 本地端点限流保护
        refreshed = False
        for attempt in (1, 2, 3):
            try:
                ok.append((key, write_one(session["api"], key)))
                break
            except SystemExit as exc:
                failed.append((key, f"SystemExit: {exc}"))
                print(f"[{key}] STOP: {exc}", flush=True)
                break
            except ZoteroLocalApiError as exc:
                text = str(exc)
                if ("401" in text or "403" in text) and not refreshed:
                    refreshed = True
                    print(f"[{key}] write rejected by Zotero (HTTP 401/403); refreshing cached key once", flush=True)
                    refresh_authorization(session)
                    continue
                note_failure(failed, exc, key, attempt)
            except Exception as exc:
                note_failure(failed, exc, key, attempt)

    print()
    print(f"OK {len(ok)} | FAILED {len(failed)}")
    for k, n in ok:
        print(f"  {k} -> note {n}")
    for k, e in failed:
        print(f"  {k} -> {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
