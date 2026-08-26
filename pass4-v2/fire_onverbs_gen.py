# -*- coding: utf-8 -*-
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path
BASE = Path(r"D:\task\科研\HCI+\litereature review\paperqa2\review-pipeline-repo\pass4-v2")
WAIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0
auth = json.load(open(os.path.expanduser(r"~\.local\share\opencode\auth.json"), encoding="utf-8"))
key = auth["opencode-go"]["key"]
env = dict(os.environ); env.update({
    "OPENAI_API_KEY": key,
    "OPENAI_API_BASE": "https://opencode.ai/zen/go/v1",
    "PILOT_LLM": "openai/ox-alpha-free",
    "PILOT_VLM": "none",
})
if WAIT: time.sleep(WAIT)
def gen_ok():
    req = urllib.request.Request("https://opencode.ai/zen/go/v1/chat/completions",
        data=json.dumps({"model": "ox-alpha-free", "messages": [{"role": "user", "content": "Output exactly one word: ready"}], "max_tokens": 200}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 genprobe"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=90))
        c = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        print("[genprobe] content:", repr(c[:40]), flush=True)
        return len(c.strip()) > 0
    except Exception as e:
        print("[genprobe] FAIL:", type(e).__name__, str(e)[:100], flush=True)
        return False
for i in range(12):
    if gen_ok():
        print("[genprobe] GENERATION AVAILABLE - launching", flush=True); break
    print("[genprobe] not ready (%d/12); retry 300s" % (i+1), flush=True); time.sleep(300)
else:
    print("[genprobe] giving up", flush=True); sys.exit(2)
keys = "RQ84Y8YU TKBMAUKB TD4K2Q3K EYXXXSLT NK427LSX WYACIP72 R3SAD5NF Z8WZRFJG 4HCHQI3E".split()
cmd = [r"D:\anaconda\miniconda3\envs\paperqa\python.exe", str(BASE / "batch.py"), "--include"] + keys + ["--concurrency", "3", "--max-hours", "14", "--router-config", str(BASE / "router_config_onverbs.json")]
print("[launch]", " ".join(cmd), flush=True)
with open(BASE / "logs" / "onverbs_final.log", "w", encoding="utf-8") as fo, open(BASE / "logs" / "onverbs_final.err", "w", encoding="utf-8") as fe:
    rc = subprocess.call(cmd, cwd=str(BASE), env=env, stdout=fo, stderr=fe)
print("[done] rc:", rc, flush=True)