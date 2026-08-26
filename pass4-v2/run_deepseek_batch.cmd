@echo off
cd /d "D:\task\??\HCI+\litereature review\paperqa2\integration-tests\pass4-v2"
"D:\anaconda\miniconda3\envs\paperqa\python.exe" batch.py --queue queue/user_targets_queue.json --router-config router_deepseek_full.json --concurrency 4 --max-hours 16 --zotero-index --wait-reset >> logs\batch_deepseek.log 2>&1
