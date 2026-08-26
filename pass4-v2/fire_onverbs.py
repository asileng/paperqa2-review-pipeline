# -*- coding: utf-8 -*-
"""On Verbs 批量发射器（等待 Go 套餐窗口重置后自动点火）。"""
import json, os, subprocess, sys, time
from pathlib import Path

BASE = Path(r"D:\task\科研\HCI+\litereature review\paperqa2\review-pipeline-repo\pass4-v2")
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)
RESET_WAIT_SEC = int(sys.argv[1]) if len(sys.argv) > 1 else 0

auth = json.load(open(os.path.expanduser(r"~\.local\share\opencode\auth.json"), encoding="utf-8"))
key = auth["opencode-go"]["key"]

env = dict(os.environ)
env.update({
    "OPENAI_API_KEY": key,
    "OPENAI_API_BASE": "https://opencode.ai/zen/go/v1",
    "PILOT_LLM": "openai/ox-alpha-free",
    "PILOT_VLM": "openai/deepseek-v4-flash-vision-exp",
})

py = r"D:\anaconda\miniconda3\envs\paperqa\python.exe"
if RESET_WAIT_SEC > 0:
    print("[wait] sleeping %d s until quota reset..." % RESET_WAIT_SEC, flush=True)
    time.sleep(RESET_WAIT_SEC)

# 点火前探针：模型仍被限则每 10 分钟重试，最多再等 90 分钟
import urllib.request
def probe():
    req = urllib.request.Request(
        "https://opencode.ai/zen/go/v1/chat/completions",
        data=json.dumps({"model": "ox-alpha-free", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 pass4-v2-onverbs"},
    )
    try:
        urllib.request.urlopen(req, timeout=60)
        return True
    except urllib.error.HTTPError as e:
        print("[probe] HTTP %d" % e.code, flush=True)
        return False
    except Exception as e:
        print("[probe] %s" % type(e).__name__, flush=True)
        return False

for i in range(9):
    if probe():
        print("[probe] gateway OPEN - launching batch", flush=True)
        break
    print("[probe] still limited; retry in 600s (%d/9)" % (i + 1), flush=True)
    time.sleep(600)
else:
    print("[probe] giving up after extended wait", flush=True)
    sys.exit(2)

cmd = [py, str(BASE / "batch.py"), "--include"] + [
    p["zotero_key"] for p in json.load(open(BASE / "queue" / "papers_queue_onverbs.json", encoding="utf-8"))["papers"]
] + ["--concurrency", "3", "--max-hours", "14"]
print("[launch]", " ".join(cmd), flush=True)
with open(LOGS / "onverbs_batch.log", "w", encoding="utf-8") as fo, open(LOGS / "onverbs_batch.err.log", "w", encoding="utf-8") as fe:
    rc = subprocess.call(cmd, cwd=str(BASE), env=env, stdout=fo, stderr=fe)
print("[done] exit code:", rc, flush=True)
sys.exit(rc)
