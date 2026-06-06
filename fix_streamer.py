import re
import os

with open("dashboard/streamer.py", "r") as f:
    code = f.read()

# Add imports
if "from walk_forward import parse_fold, aggregate" not in code:
    imports = """
import httpx
import jwt

# Add scripts directory to path to import walk_forward logic
import sys
sys.path.append("/home/ubuntu/var/www/html/trade/scripts")
from walk_forward import parse_fold, aggregate
"""
    code = code.replace("import httpx\nimport jwt", imports)

# 1. Env vars
code = code.replace('FT_USER = "bot"', 'FT_USER = os.environ.get("FT_USER", "bot")')
code = code.replace('FT_PASS = "REDACTED-FREQTRADE__API_SERVER__PASSWORD"', 'FT_PASS = os.environ.get("FT_PASS", "REDACTED-FREQTRADE__API_SERVER__PASSWORD")')

# 2. _preflight
preflight_old = """    if not os.environ.get("DASHBOARD_SECRET_KEY"):
        missing.append("DASHBOARD_SECRET_KEY")"""
preflight_new = """    if not os.environ.get("DASHBOARD_SECRET_KEY"):
        missing.append("DASHBOARD_SECRET_KEY")
    if not os.environ.get("FT_USER") or not os.environ.get("FT_PASS"):
        pass # Optional fallback"""
code = code.replace(preflight_old, preflight_new)

# 3. CORS
code = code.replace('allow_origins=["*"]', 'allow_origins=["https://trade.star7gaurav.in", "http://localhost:5173", "http://REDACTED-SERVER_IP:5173"]')

# 4. Regex
code = code.replace('re.compile(r"^.+_\\d{8}T\\d{6}$")', 're.compile(r"^[A-Za-z0-9_-]+_\\d{8}T\\d{6}$")')

# 5. /api/wf/running-folds
running_api = """
@app.get("/api/wf/running-folds")
async def wf_running_folds(_: dict = Depends(require_auth)):
    runs = _wf_runs_sorted()
    active_run = None
    for run in runs:
        if not (run / "summary.json").exists():
            age_s = __import__('time').time() - run.stat().st_mtime
            if age_s < ACTIVE_STALE_S:
                active_run = run
                break
                
    if not active_run:
        return {"available": False}
        
    folds_data = []
    fold_results = []
    
    for f in sorted(active_run.glob("fold_*_result.json")):
        parts = f.name.split('_')
        if len(parts) >= 2 and parts[1].isdigit():
            fold_num = int(parts[1])
            log_files = list(active_run.glob(f"fold_{fold_num:02d}_*.log"))
            if not log_files:
                continue
            
            try:
                log_name = log_files[0].stem
                dates = log_name.split('_')[-1]
                ts_str, te_str = dates.split('-')
                from datetime import datetime
                test_start = datetime.strptime(ts_str, "%Y%m%d")
                test_end = datetime.strptime(te_str, "%Y%m%d")
                
                fr = parse_fold(f, fold_num, test_start, test_end)
                if fr:
                    fold_results.append(fr)
                    from dataclasses import asdict
                    folds_data.append(asdict(fr))
            except Exception as e:
                print(f"Error parsing running fold {f.name}: {e}")
                
    if not fold_results:
        return {"available": False, "active_run_name": active_run.name}
        
    agg = aggregate(fold_results)
    
    return {
        "available": True,
        "name": active_run.name,
        "folds": folds_data,
        "aggregate": agg
    }

"""
if "/api/wf/running-folds" not in code:
    code = code.replace('@app.get("/api/wf/history")', running_api + '\n@app.get("/api/wf/history")')

# fix wf_latest to return target_folds
old_latest = """        try:
            with open(summary_path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        return {"available": True, "name": latest.name, "summary": data, "active_run_name": active_run_name}"""

new_latest = """        try:
            with open(summary_path) as f:
                data = json.load(f)
            max_fold = 21
            active_run = None
            if active_run_name:
                active_run = next((r for r in runs if r.name == active_run_name), None)
            try:
                logs = list(active_run.glob("fold_*.log")) if active_run else list(latest.glob("fold_*.log"))
                if logs:
                    max_fold = max([int(p.stem.split('_')[1]) for p in logs if p.stem.split('_')[1].isdigit()], default=21)
            except Exception:
                pass
            return {"available": True, "name": latest.name, "summary": data, "active_run_name": active_run_name, "target_folds": max_fold}
        except (OSError, json.JSONDecodeError):
            continue"""
code = code.replace(old_latest, new_latest)

# 6. WebSocket auth
old_ws1 = """@app.websocket("/ws/brain")
async def websocket_brain(websocket: WebSocket):
    await websocket.accept()"""
new_ws1 = """@app.websocket("/ws/brain")
async def websocket_brain(websocket: WebSocket, token: str = Query(None)):
    if not token or not verify_token(token):
        await websocket.close(code=1008)
        return
    await websocket.accept()"""
code = code.replace(old_ws1, new_ws1)

old_ws2 = """@app.websocket("/ws/memory")
async def websocket_memory(websocket: WebSocket):
    await websocket.accept()"""
new_ws2 = """@app.websocket("/ws/memory")
async def websocket_memory(websocket: WebSocket, token: str = Query(None)):
    if not token or not verify_token(token):
        await websocket.close(code=1008)
        return
    await websocket.accept()"""
code = code.replace(old_ws2, new_ws2)

with open("dashboard/streamer.py", "w") as f:
    f.write(code)

print("done streamer")
