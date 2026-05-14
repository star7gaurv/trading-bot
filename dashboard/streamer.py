import asyncio
import os
import re
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import aiofiles

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_FILE = "/home/ubuntu/var/www/html/trade/freqtrade/user_data/logs/freqtrade.log"
CONTEXT_FILE = "/home/ubuntu/var/www/html/trade/finbuddy_memory/CONTEXT.md"

@app.websocket("/ws/brain")
async def websocket_brain(websocket: WebSocket):
    await websocket.accept()
    
    # Fetch historical logs instantly on connection
    try:
        import subprocess
        tail_output = subprocess.check_output(['tail', '-n', '5000', LOG_FILE]).decode('utf-8', errors='replace')
        hist_lines = [l.strip() for l in tail_output.split('\n') if "FinBuddyLLMModel" in l and "[" in l]
        for line in hist_lines[-50:]:
            await websocket.send_json({"type": "brain_log", "log": line})
    except Exception as e:
        print(f"Error fetching history: {e}")

    # We will use a simple aiofiles tailing logic
    try:
        async with aiofiles.open(LOG_FILE, 'r') as f:
            # Seek to end
            await f.seek(0, os.SEEK_END)
            while True:
                line = await f.readline()
                if not line:
                    await asyncio.sleep(0.5)
                    continue
                
                # Check if it's a FinBuddyLLMModel line
                if "FinBuddyLLMModel" in line and "[" in line:
                    await websocket.send_json({"type": "brain_log", "log": line.strip()})
    except Exception as e:
        print(f"Error in brain streamer: {e}")
        await websocket.close()

@app.websocket("/ws/memory")
async def websocket_memory(websocket: WebSocket):
    await websocket.accept()
    last_mtime = 0
    try:
        while True:
            if os.path.exists(CONTEXT_FILE):
                mtime = os.path.getmtime(CONTEXT_FILE)
                if mtime > last_mtime:
                    async with aiofiles.open(CONTEXT_FILE, 'r') as f:
                        content = await f.read()
                    
                    # Parse the simple markdown format
                    regime = "UNKNOWN"
                    fear_greed = "UNKNOWN"
                    for line in content.split('\n'):
                        if line.startswith("Regime:"):
                            regime_match = re.search(r'\*\*(.*?)\*\*', line)
                            if regime_match:
                                regime = regime_match.group(1)
                        elif line.startswith("Fear & Greed:"):
                            fear_greed = line.replace("Fear & Greed:", "").strip()

                    await websocket.send_json({
                        "type": "memory_update",
                        "regime": regime,
                        "fear_greed": fear_greed
                    })
                    last_mtime = mtime
            
            await asyncio.sleep(1)
    except Exception as e:
        print(f"Error in memory streamer: {e}")
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)
