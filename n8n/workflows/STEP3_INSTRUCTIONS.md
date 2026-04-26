# Step 3 — Wire N8N to Read FinBuddy Memory

## Part A: Restart N8N with the new volume mount

On the server:
```bash
cd /home/ubuntu/var/www/html/trade/n8n
git pull origin master

# Restart N8N with the new finbuddy_memory volume
docker compose down
docker compose up -d

# Verify the mount is working
docker exec n8n ls /data/finbuddy_memory/
# Should show: CONTEXT.md  SERVER_SETUP.md  regimes/  research/  scripts/  signals/  strategies/
```

---

## Part B: Update the workflow in N8N UI

Open `n8n.star7gaurav.in` → open the **trading_loop_v3** workflow.

### Add 2 new Code nodes before the Groq HTTP Request node:

**Node 1 — "Read FinBuddy Memory"**
- Type: Code
- Language: JavaScript
- Mode: Run Once For All Items
- Paste contents of: `context_reader_node.js`

**Node 2 — "Build Groq Prompt"**
- Type: Code
- Language: JavaScript
- Mode: Run Once For All Items
- Paste contents of: `groq_prompt_with_memory.js`
- ⚠️ Check the field names match your v3 workflow output (`rsi`, `macd`, `price`, `tradeOpen`, `pnl`)
  If your v3 uses different names, update them at the top of the script.

### Update the Groq HTTP Request node:
- In the request body, change the prompt field to use `{{ $json.groq_prompt }}`
  instead of whatever hardcoded or previous expression it used.

### Wire the nodes:
```
[Existing nodes] → [Read FinBuddy Memory] → [Build Groq Prompt] → [Groq HTTP Request] → [rest of workflow]
```

---

## Part C: Test it
1. Manually trigger the workflow once
2. Check the output of "Build Groq Prompt" node — you should see `finbuddy_memory` 
   content injected into the prompt
3. Check `finbuddy_memory/signals/log.md` — if you also wire the signal logger,
   each Groq response will be logged there automatically

---

## Optional: Auto-log signals back to memory
After the Groq response node, add another Code node that calls:
```bash
python3 /home/ubuntu/var/www/html/trade/finbuddy_memory/scripts/memory_writer.py signal \
  --signal {{ $json.signal }} \
  --regime {{ $json.regime }} \
  --rsi {{ $json.rsi }} \
  --macd {{ $json.macd }} \
  --reason "{{ $json.reason }}"
```
This closes the loop — every signal gets written back to memory.
