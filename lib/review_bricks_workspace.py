"""Roadmap-first Zotero bridge and durable queue for the local Viewer.

Live Zotero data is accessed only through Zotero 10's Local API. Project
imports are previewed first and remain unclassified until the researcher maps
them in the roadmap.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PAPERS_PATH = ROOT / "papers.json"
NLM_ROOT = ROOT / "notebooklm"
BRICKS_ROOT = NLM_ROOT / "review_bricks"
STATE_PATH = BRICKS_ROOT / "state.json"
QUEUE_PATH = BRICKS_ROOT / "queue.json"
NOTES_INDEX_PATH = NLM_ROOT / "notes_index.json"
GLOBAL_SCISPACE_WORKFLOW_SKILL = Path(r"C:\Users\ieltsbro\.codex\skills\literature-scispace-workflow\SKILL.md")
ZOTERO_BASE_URL = "http://127.0.0.1:23119/api/"
ZOTERO_KEYRING_SERVICE = "reviewBricks.zotero-local-api"


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else default


def state() -> dict:
    return load_json(STATE_PATH, {"schema_version": 1, "zotero": {}, "imports": []})


def queue_document() -> dict:
    return load_json(QUEUE_PATH, {"schema_version": 1, "updated_at": None, "records": []})


def zotero_year(value: object) -> str | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return match.group(0) if match else None


class ZoteroLocalApiError(RuntimeError):
    pass


def _zotero_keyring_account(base_url: str) -> str:
    """Keep the credential identity stable without storing its token in the project."""
    digest = hashlib.sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()[:16]
    return f"endpoint:{digest}"


def _load_zotero_api_key(base_url: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(ZOTERO_KEYRING_SERVICE, _zotero_keyring_account(base_url)) or None
    except Exception:
        return None


def _store_zotero_api_key(base_url: str, api_key: str) -> bool:
    try:
        import keyring
        keyring.set_password(ZOTERO_KEYRING_SERVICE, _zotero_keyring_account(base_url), api_key)
        return True
    except Exception:
        return False


def _delete_zotero_api_key(base_url: str) -> None:
    try:
        import keyring
        keyring.delete_password(ZOTERO_KEYRING_SERVICE, _zotero_keyring_account(base_url))
    except Exception:
        pass


class ZoteroLocalApi:
    """Small client for the documented localhost Zotero 10 API."""

    def __init__(self, base_url: str = ZOTERO_BASE_URL, timeout: int = 8):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.server_id: str | None = None
        self.api_key: str | None = _load_zotero_api_key(self.base_url)
        # A cache is an optional convenience only. Zotero itself owns the durable
        # permission granted by its "Always Allow" dialog.
        self.credential_cache_available = self.api_key is not None
        self.authorization_persistent = self.api_key is not None

    def request(self, suffix: str, *, query: dict | None = None, method: str = "GET", payload: object | None = None, extra_headers: dict | None = None, allow_text: bool = False) -> tuple[object, dict]:
        url = self.base_url + suffix.lstrip("/")
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json"}
        if self.server_id:
            headers["Zotero-Server-ID"] = self.server_id
        if extra_headers:
            headers.update(extra_headers)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=self.timeout) as response:
                raw, response_headers = response.read().decode("utf-8"), dict(response.headers.items())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ZoteroLocalApiError(f"Zotero API HTTP {error.code}: {detail[:500]}") from error
        except (urllib.error.URLError, OSError) as error:
            raise ZoteroLocalApiError(f"Zotero Local API unavailable: {error}") from error
        self.server_id = response_headers.get("Zotero-Server-ID", self.server_id)
        try:
            return json.loads(raw) if raw else {}, response_headers
        except json.JSONDecodeError as error:
            if allow_text:
                return raw, response_headers
            raise ZoteroLocalApiError("Zotero Local API returned non-JSON data") from error

    def status(self) -> dict:
        payload, headers = self.request("", allow_text=True)
        return {"ok": True, "server_id": headers.get("Zotero-Server-ID"), "api_version": headers.get("Zotero-API-Version"), "schema_version": headers.get("Zotero-Schema-Version"), "payload": payload}

    def authorize_write(self) -> str:
        """Get a key from Zotero; remembered grants can be retrieved without a new dialog."""
        if self.api_key:
            return self.api_key
        if not self.server_id:
            self.status()
        payload = None
        last_error = None
        for attempt in range(3):
            try:
                payload, _ = self.request("local/authorize", method="POST", payload={"appName": "reviewBricks"})
                break
            except ZoteroLocalApiError as error:
                last_error = error
                if "timed out" not in str(error).casefold() or attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        if payload is None and last_error:
            raise last_error
        key = payload.get("key") if isinstance(payload, dict) else None
        if not key:
            raise ZoteroLocalApiError("Zotero write authorization was denied or returned no key")
        self.api_key = key
        self.authorization_persistent = payload.get("remember") is True
        if self.authorization_persistent:
            # Some non-interactive Windows sessions cannot write Credential
            # Manager (WinError 1312). That must not invalidate Zotero's own
            # durable grant: a later call to local/authorize retrieves a key
            # again without prompting.
            self.credential_cache_available = _store_zotero_api_key(self.base_url, key)
        else:
            # Zotero documents non-remembered keys as single-use. Never cache one
            # across processes and accidentally treat it as a permanent grant.
            _delete_zotero_api_key(self.base_url)
        return key

    @staticmethod
    def _data(item: object) -> dict:
        return item.get("data", item) if isinstance(item, dict) else {}

    @staticmethod
    def _analysis_index(notes: list[dict], item_key: str) -> tuple[dict | None, str | None]:
        """Extract only the owned compact index; malformed indexes stay visible."""
        for note in notes:
            body = note.get("note", "")
            if "reviewBricks-analysis-index" not in body:
                continue
            match = re.search(r"<pre[^>]*>([\s\S]*?)</pre>", body, flags=re.IGNORECASE)
            if not match:
                return {"status": "malformed", "reason": "missing_json_pre"}, note.get("key")
            try:
                payload = json.loads(html.unescape(match.group(1)).strip())
            except json.JSONDecodeError:
                return {"status": "malformed", "reason": "invalid_json"}, note.get("key")
            if payload.get("zotero_item_key") != item_key:
                return {"status": "malformed", "reason": "item_key_mismatch"}, note.get("key")
            return payload, note.get("key")
        return None, None

    def libraries(self) -> list[dict]:
        libraries = [{"id": "user:0", "prefix": "users/0", "label": "我的文献库"}]
        groups, _ = self.request("users/0/groups", query={"format": "json"})
        for group in groups if isinstance(groups, list) else []:
            data = self._data(group)
            group_id = data.get("id") or (group.get("id") if isinstance(group, dict) else None)
            if group_id is not None:
                libraries.append({"id": f"group:{group_id}", "prefix": f"groups/{group_id}", "label": data.get("name") or f"群组 {group_id}"})
        return libraries

    def collections(self) -> list[dict]:
        result = []
        for library in self.libraries():
            payload, _ = self.request(f"{library['prefix']}/collections", query={"format": "json"})
            for raw in payload if isinstance(payload, list) else []:
                data = self._data(raw)
                key = data.get("key") or (raw.get("key") if isinstance(raw, dict) else None)
                if key:
                    result.append({"library": library["id"], "library_label": library["label"], "key": key, "name": data.get("name", key), "parent": data.get("parentCollection")})
        return result

    @staticmethod
    def prefix_for_library(library: str) -> str:
        if library == "user:0":
            return "users/0"
        match = re.fullmatch(r"group:(\d+)", library or "")
        if not match:
            raise ValueError("invalid Zotero library identifier")
        return f"groups/{match.group(1)}"

    def collection_items(self, library: str, collection_key: str) -> list[dict]:
        prefix = self.prefix_for_library(library)
        payload, _ = self.request(f"{prefix}/collections/{collection_key}/items", query={"format": "json", "include": "data"})
        records = []
        for raw in payload if isinstance(payload, list) else []:
            data = self._data(raw)
            if data.get("itemType") in {"attachment", "note", "annotation"}:
                continue
            key = data.get("key") or (raw.get("key") if isinstance(raw, dict) else None)
            if not key:
                continue
            children, _ = self.request(f"{prefix}/items/{key}/children", query={"format": "json", "include": "data"})
            child_data = [self._data(child) for child in children if isinstance(children, list)]
            attachments = [child for child in child_data if child.get("itemType") == "attachment"]
            notes = [child for child in child_data if child.get("itemType") == "note"]
            analysis_index, index_note_key = self._analysis_index(notes, key)
            records.append({
                "zotero_item_key": key, "item_type": data.get("itemType"), "title": data.get("title") or "[无题名]",
                "authors": [" ".join(part for part in [creator.get("firstName"), creator.get("lastName")] if part).strip() for creator in data.get("creators", [])],
                "year": zotero_year(data.get("date")), "doi": data.get("DOI") or None,
                "publication": data.get("publicationTitle") or data.get("proceedingsTitle") or None,
                "has_pdf": any((attachment.get("contentType") or "").casefold() == "application/pdf" for attachment in attachments),
                "attachment_count": len(attachments), "has_analysis_index": analysis_index is not None,
                "analysis_index": analysis_index, "analysis_index_note_key": index_note_key,
                "version": data.get("version") or (raw.get("version") if isinstance(raw, dict) else None),
            })
        return records


def zotero_status() -> dict:
    api = ZoteroLocalApi()
    try:
        info = api.status()
    except ZoteroLocalApiError as error:
        return {"ok": False, "error": str(error), "base_url": ZOTERO_BASE_URL}
    current = state()
    current["zotero"] = {"base_url": ZOTERO_BASE_URL, "server_id": info.get("server_id"), "last_seen_at": now()}
    write_json(STATE_PATH, current)
    return info


def list_collections() -> dict:
    api = ZoteroLocalApi()
    api.status()
    return {"ok": True, "server_id": api.server_id, "collections": api.collections()}


def collection_preview(library: str, collection_key: str) -> dict:
    if not re.fullmatch(r"[A-Z0-9]{8}", collection_key or ""):
        raise ValueError("invalid Zotero collection key")
    api = ZoteroLocalApi()
    api.status()
    records = api.collection_items(library, collection_key)
    imported = {entry.get("zotero_item_key"): entry for entry in state().get("imports", []) if entry.get("server_id") == api.server_id}
    for record in records:
        existing = imported.get(record["zotero_item_key"])
        record["workbench_status"] = "already_imported" if existing else "new"
        if existing:
            record["paper_id"] = existing.get("paper_id")
    token_source = json.dumps({"server_id": api.server_id, "library": library, "collection_key": collection_key, "keys": [r["zotero_item_key"] for r in records]}, ensure_ascii=False, sort_keys=True)
    return {"ok": True, "server_id": api.server_id, "library": library, "collection_key": collection_key, "items": records, "preview_token": hashlib.sha256(token_source.encode("utf-8")).hexdigest(), "previewed_at": now()}


def _next_paper_number(papers: list[dict]) -> int:
    return max([int(entry["paper_id"][1:]) for entry in papers if re.fullmatch(r"P\d{3,}", entry.get("paper_id", ""))] or [0]) + 1


def import_preview(preview: dict) -> dict:
    if not preview.get("server_id") or not isinstance(preview.get("items"), list):
        raise ValueError("a valid collection preview is required")
    manifest = load_json(PAPERS_PATH, {"schema_version": 1, "revision": 1, "papers": []})
    existing_by_key = {entry.get("zotero", {}).get("item_key"): entry for entry in manifest.get("papers", []) if entry.get("origin") == "zotero"}
    workbench = state(); imports = workbench.setdefault("imports", [])
    imported_by_key = {entry.get("zotero_item_key"): entry for entry in imports if entry.get("server_id") == preview["server_id"]}
    next_id, created, skipped, refreshed = _next_paper_number(manifest["papers"]), [], [], False
    for item in preview["items"]:
        key = item.get("zotero_item_key")
        if not key: continue
        already = imported_by_key.get(key) or existing_by_key.get(key)
        if already:
            index = item.get("analysis_index") or {}
            first_round = index.get("first_round") if isinstance(index, dict) else None
            if already in imports:
                already.update({"analysis_index_state": index.get("status", "present" if index else "missing") if isinstance(index, dict) else "missing", "analysis_provider": (first_round or {}).get("provider") or index.get("analysis_provider") if isinstance(index, dict) else None, "provider_record_url": (first_round or {}).get("provider_record_url"), "notebook_id": index.get("notebook_id") if isinstance(index, dict) else None, "markdown_destination": (first_round or {}).get("markdown_path"), "analysis_json_destination": (first_round or {}).get("analysis_json_path"), "analysis_json_pointer": (first_round or {}).get("analysis_json_pointer"), "raw_output_destination": (first_round or {}).get("raw_output_path"), "raw_output_anchor": (first_round or {}).get("raw_output_anchor"), "markdown_heading": (first_round or {}).get("heading"), "markdown_rounds": index.get("rounds", []) if isinstance(index, dict) else [], "zotero_index_note_key": item.get("analysis_index_note_key"), "refreshed_at": now()})
                refreshed = True
            skipped.append({"zotero_item_key": key, "paper_id": already.get("paper_id"), "reason": "already_imported"}); continue
        paper_id = f"P{next_id:03d}"; next_id += 1
        paper = {"paper_id": paper_id, "title": item.get("title") or "[无题名]", "authors": item.get("authors") or [], "year": item.get("year"), "doi": item.get("doi"), "files": {"pdf": None, "text": None, "markdown": None}, "sha256": None, "aliases": [], "decision": "pending", "reading_status": "unread", "writing_status": "unmapped", "metadata_status": "zotero_import", "origin": "zotero", "zotero": {"server_id": preview["server_id"], "library": preview["library"], "item_key": key, "collection_key": preview["collection_key"], "has_pdf": bool(item.get("has_pdf")), "version": item.get("version")}}
        manifest["papers"].append(paper)
        index = item.get("analysis_index") or {}
        first_round = index.get("first_round") if isinstance(index, dict) else None
        imports.append({"paper_id": paper_id, "zotero_item_key": key, "server_id": preview["server_id"], "library": preview["library"], "collection_key": preview["collection_key"], "imported_at": now(), "analysis_index_state": index.get("status", "present" if index else "missing") if isinstance(index, dict) else "missing", "analysis_provider": (first_round or {}).get("provider") or index.get("analysis_provider") if isinstance(index, dict) else None, "provider_record_url": (first_round or {}).get("provider_record_url"), "notebook_id": index.get("notebook_id") if isinstance(index, dict) else None, "markdown_destination": (first_round or {}).get("markdown_path"), "analysis_json_destination": (first_round or {}).get("analysis_json_path"), "analysis_json_pointer": (first_round or {}).get("analysis_json_pointer"), "raw_output_destination": (first_round or {}).get("raw_output_path"), "raw_output_anchor": (first_round or {}).get("raw_output_anchor"), "markdown_heading": (first_round or {}).get("heading"), "markdown_rounds": index.get("rounds", []) if isinstance(index, dict) else [], "zotero_index_note_key": item.get("analysis_index_note_key")})
        created.append({"paper_id": paper_id, "zotero_item_key": key, "title": paper["title"], "has_pdf": paper["zotero"]["has_pdf"]})
    if created:
        manifest["papers"].sort(key=lambda item: item["paper_id"]); manifest["revision"] = manifest.get("revision", 1) + 1; manifest["updated_at"] = now()
        write_json(PAPERS_PATH, manifest)
    if created or refreshed:
        workbench["updated_at"] = now(); write_json(STATE_PATH, workbench)
    return {"ok": True, "created": created, "skipped": skipped, "unclassified": True}


def _paper_and_analysis(paper_id: str) -> tuple[dict, dict | None]:
    paper = next((record for record in load_json(PAPERS_PATH, {"papers": []}).get("papers", []) if record.get("paper_id") == paper_id), None)
    if not paper: raise ValueError(f"unknown paper_id: {paper_id}")
    notes = load_json(NOTES_INDEX_PATH, {"notes": []}).get("notes", [])
    note = next((record for record in notes if record.get("paper_id") == paper_id), None)
    imported = next((record for record in state().get("imports", []) if record.get("paper_id") == paper_id), None)
    return paper, note or imported


def structured_analysis_for_paper(paper_id: str) -> dict | None:
    """Load a normalized analysis only when its indexed JSON stays in this workspace."""
    imported = next((record for record in state().get("imports", []) if record.get("paper_id") == paper_id), None)
    path_value = (imported or {}).get("analysis_json_destination")
    if not path_value:
        return None
    candidate = Path(path_value).resolve()
    if ROOT not in candidate.parents or candidate.suffix.lower() != ".json" or not candidate.is_file():
        return None
    try:
        document = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if document.get("schema_version") != 1:
        return None
    if document.get("kind") == "reviewBricks-analysis-batch":
        item_key = imported.get("zotero_item_key")
        expected_pointer = f"/papers/{item_key}/analysis"
        if imported.get("analysis_json_pointer") != expected_pointer:
            return None
        record = (document.get("papers") or {}).get(item_key)
        document = (record or {}).get("analysis")
        if not isinstance(document, dict):
            return None
    if document.get("kind") != "reviewBricks-analysis":
        return None
    paper = next((record for record in load_json(PAPERS_PATH, {"papers": []}).get("papers", []) if record.get("paper_id") == paper_id), {})
    if document.get("paper", {}).get("zotero_item_key") != imported.get("zotero_item_key"):
        return None
    return {"paper_id": paper_id, "title": paper.get("title"), "analysis_json_path": str(candidate), "analysis": document}


def stage_question(paper_id: str, question: str) -> dict:
    if not re.fullmatch(r"P\d{3,}", paper_id or "") or not question.strip(): raise ValueError("paper_id and a non-empty question are required")
    paper, analysis = _paper_and_analysis(paper_id)
    record = {"run_id": f"followup_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}", "status": "queued", "provider": (analysis or {}).get("analysis_provider") or "scispace_chat_pdf", "provider_record_url": (analysis or {}).get("provider_record_url"), "paper_id": paper_id, "zotero_item_key": (analysis or {}).get("zotero_key") or (analysis or {}).get("zotero_item_key") or paper.get("zotero", {}).get("item_key"), "zotero_library": (analysis or {}).get("library") or paper.get("zotero", {}).get("library"), "zotero_index_note_key": (analysis or {}).get("zotero_index_note_key"), "notebook_id": (analysis or {}).get("notebook_id"), "question": question.strip(), "markdown_destination": (analysis or {}).get("raw_output_destination") or (analysis or {}).get("markdown_destination") or (analysis or {}).get("source_document"), "markdown_heading": (analysis or {}).get("markdown_heading"), "created_at": now(), "updated_at": now(), "execution": {"state": "not_started"}}
    document = queue_document(); document["records"].append(record); document["updated_at"] = now(); write_json(QUEUE_PATH, document)
    return record


def queue_for_paper(paper_id: str) -> list[dict]:
    return [record for record in queue_document().get("records", []) if record.get("paper_id") == paper_id]


def scispace_migrated() -> bool:
    return GLOBAL_SCISPACE_WORKFLOW_SKILL.exists() and "one-scispace-record-per-zotero-item-v1" in GLOBAL_SCISPACE_WORKFLOW_SKILL.read_text(encoding="utf-8")


def _append_followup_markdown(record: dict, answer: str) -> str:
    destination = Path(record["markdown_destination"])
    if not destination.is_absolute() or not destination.is_file():
        raise ValueError("indexed Markdown destination does not resolve to an existing absolute file")
    count = 2
    for existing in queue_document().get("records", []):
        if existing.get("paper_id") == record["paper_id"] and existing.get("status") in {"completed", "completed_index_pending"}:
            count += 1
    heading = f"### Follow-up {count} — {record['zotero_item_key']}"
    content = "\n\n" + heading + "\n\n- 用户追问：" + record["question"] + "\n\n#### NotebookLM 回答\n\n" + answer.strip() + "\n"
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(content)
    return heading


def _update_zotero_index(record: dict, heading: str) -> None:
    """Update only the owned index note after a successful explicit execution."""
    library = record.get("zotero_library")
    note_key = record.get("zotero_index_note_key")
    if not library or not note_key:
        raise ValueError("analysis index lacks Zotero library or index-note key")
    api = ZoteroLocalApi(); api.status(); prefix = api.prefix_for_library(library)
    note_item, _ = api.request(f"{prefix}/items/{note_key}", query={"format": "json", "include": "data"})
    note_data = api._data(note_item)
    index, _ = api._analysis_index([note_data], record["zotero_item_key"])
    if not index or index.get("status") == "malformed":
        raise ValueError("owned Zotero analysis index is missing or malformed")
    rounds = list(index.get("rounds") or [])
    rounds.append({"round": len(rounds) + 2, "kind": "follow_up", "markdown_path": record["markdown_destination"], "heading": heading, "created_at": now(), "status": "completed"})
    index["rounds"] = rounds
    note_html = "<p><strong>reviewBricks-analysis-index</strong></p><pre>" + html.escape(json.dumps(index, ensure_ascii=False, indent=2)) + "</pre>"
    version = note_data.get("version") or (note_item.get("version") if isinstance(note_item, dict) else None)
    if version is None:
        raise ValueError("Zotero index note has no object version")
    api_key = api.authorize_write()
    api.request(f"{prefix}/items/{note_key}", method="PUT", payload={"itemType": "note", "parentItem": record["zotero_item_key"], "note": note_html}, extra_headers={"Zotero-API-Key": api_key, "If-Unmodified-Since-Version": str(version)})


def _ask_notebooklm(record: dict) -> str:
    config = load_json(NLM_ROOT / "config.json", {})
    auth_home = (config.get("notebooklm") or {}).get("auth_home")
    run_dir = BRICKS_ROOT / "runs" / record["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = run_dir / "followup_prompt.md"
    prompt_path.write_text("请只回答下列单篇论文追问。严格根据该 Notebook 的 source；避免未解释的抽象概念，并按“论文中的内容、用户追问、回答、证据链、可继续追问点”组织。\n\n用户追问：\n" + record["question"] + "\n", encoding="utf-8")
    env = os.environ.copy()
    if auth_home:
        env["NOTEBOOKLM_HOME"] = auth_home
    result = subprocess.run(["notebooklm", "ask", "--prompt-file", str(prompt_path), "-n", record["notebook_id"]], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=600)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "NotebookLM ask failed").strip()[:2000])
    answer = result.stdout.strip()
    if not answer:
        raise RuntimeError("NotebookLM returned an empty answer")
    (run_dir / "answer.md").write_text(answer + "\n", encoding="utf-8")
    return answer


def execute_question(run_id: str) -> dict:
    document = queue_document(); record = next((entry for entry in document.get("records", []) if entry.get("run_id") == run_id), None)
    if not record: raise ValueError("unknown run_id")
    if record.get("status") != "queued": raise ValueError(f"run is not queued: {record.get('status')}")
    if not scispace_migrated(): record["execution"] = {"state": "blocked_integration_mismatch", "message": "Global SciSpace workflow skill has not completed one-paper migration."}
    elif record.get("provider") != "scispace_chat_pdf":
        record["execution"] = {"state": "blocked_legacy_provider", "message": "New follow-ups use SciSpace only; this is a historical NotebookLM record."}
    else:
        missing = [field for field in ("zotero_item_key", "zotero_library", "zotero_index_note_key", "provider_record_url", "markdown_destination") if not record.get(field)]
        if missing:
            record["execution"] = {"state": "blocked_index_incomplete", "message": "Analysis index lacks " + ", ".join(missing)}
        else:
            record["execution"] = {"state": "queued_for_schispace_playwright", "message": "SciSpace execution is performed by the attached Playwright MCP session; no NotebookLM fallback is permitted."}
    record["updated_at"] = now(); document["updated_at"] = now(); write_json(QUEUE_PATH, document)
    return record
