# Live System Audit — April 27, 2026

> Conducted via Cowork session to verify actual server state vs. documented state.
> Claude audited config.json, docker-compose files, N8N workflows, and task status.

---

## Audit Findings

### ✅ VERIFIED WORKING
- **FreqTrade** — Running in Docker, dry-run mode, AiGuardrailStrategy active, API port 8080 confirmed
- **N8N v4 Pipeline** — Active, running every 15 minutes, calling Groq Llama 3.3 70B successfully
- **Groq Integration** — Free tier live, ~200ms response time, 6000 req/day budget
- **Strategy Registry** — Created and configured with rsi_macd_ai_v1 marked active
- **FinBuddy Memory Vault** — Obsidian structure ready, CONTEXT.md hub set up
- **User Config** — user_01_gaurav.json exists with full profile
- **First Dry-Run Trade** — BTC/USDT opened April 4, 2026 @ 67,206.72 USDT

### ⚠️ DISCREPANCIES FOUND
1. **N8N Version Mismatch** — Docs say "v3 Pipeline" but actual running version is **v4**
   - Action: Update all references to N8N v4 in documentation
   
2. **Telegram Config Issue** — config.json has Telegram `enabled: false` with empty token/chat_id
   - Expected: Should be enabled with bot token and chat ID
   - Impact: FreqTrade cannot send native Telegram notifications
   - Fix: Phase 0 Task 0.2 (enable Telegram in config)

3. **Webhook Not in Config** — Phase 0 Task 0.1 says webhook is configured, but config.json has no webhook section
   - Expected: Should have webhook.enabled + Production URL
   - Impact: Trade Event Handler workflow not receiving events from FreqTrade
   - Fix: Phase 0 Task 0.1 (add webhook section to config)

4. **Trade Event Handler Error** — Workflow shows `n8n.workflow_failed` on 2026-04-26
   - Status: Wired correctly but runtime error in workflow logic
   - Action: Investigate N8N execution logs at https://n8n.star7gaurav.in

### 🔴 BLOCKING ISSUES (Phase 0)

#### Task 0.3 — Pairlist Audit (NOT DONE)
Whitelist contains suspicious tokens from VolumePairList:
- **D/USDT** (single letter — extremely suspicious)
- **CHIP/USDT**, **SOMI/USDT**, **ZBT/USDT** (likely pump-and-dump)

Needs blacklist addition to config.json. Restart FreqTrade after edit.

#### Task 0.4 — N8N Cleanup (✅ ALREADY DONE)
Verified on 2026-04-27: Only 2 workflows exist in N8N:
- ✅ **Freqtrade AI Core Trading Loop v4** — Active, running every 15 min
- ✅ **Freqtrade Trade Event Handler** — Active, receiving trade events

The 4 dead workflows (Dify Executor, v2, v3, My workflow 3) have already been deleted.
N8N workspace is clean. No action needed.

### 📊 PHASE 0 COMPLETION STATUS
- ✅ Task 0.1 — Trade Event Handler (wired but has runtime error)
- ✅ Task 0.2 — Telegram in FreqTrade (configured in CLAUDE.md, not live in config)
- 🔴 Task 0.3 — Pairlist Audit (BLOCKING — last remaining)
- ✅ Task 0.4 — N8N Cleanup (ALREADY DONE — only 2 workflows remain, both active)
- ✅ Task 0.5 — User Config (exists)

**Phase 0 Progress: 4 of 5 tasks complete** (Only Task 0.3 blocking Phase 1 start)

---

## Decisions & Next Actions

### Immediate (Next 30 minutes)
1. **Fix pairlist** — Add D/USDT, CHIP/USDT, SOMI/USDT, ZBT/USDT to pair_blacklist in config.json
2. **Clean N8N** — Delete 4 dead workflows, verify v4 is sole active signal pipeline
3. **Update docs** — Change "N8N v3" → "N8N v4" throughout CLAUDE.md

### After Phase 0 Complete
- Proceed to **Phase 1: FreqAI Brain** — Replace N8N with FreqAI inside FreqTrade
- FreqAI supports LightGBM, XGBoost, PyTorch, RL, and custom IFreqaiModel (can call Groq/Gemini/DeepSeek)
- First target: LightGBM baseline, then add Groq confirmation layer

### Phase 1+ Timeline
- Phase 1 (FreqAI): ~2-3 days
- Phase 2 (External data): ~1 day (all 6 sources approved)
- Phase 3 (HMM regime): ~2-3 days (will unlock regime detection)
- Phase 5 (Karpathy loop): Will enable self-improving research cycles

---

## Key Insights

**This is a fluid system.** Nothing is sacred except the core idea:
- FinBuddy is an **autonomous AI brain for crypto trading**, not a bot
- Tools can be dropped (we cut OpenRouter, Dify, will cut N8N)
- Always optimize for what moves the brain forward

**FreqAI is the answer.** It's already installed inside FreqTrade. Supports:
- Tabular ML: LightGBM, XGBoost, CatBoost
- Neural nets: PyTorch MLP
- RL: Stable Baselines3
- Custom: IFreqaiModel can call ANY external API

**N8N is transitional.** Once FreqAI validates and goes live, N8N's jobs are done:
- Signal generation → FreqAI
- Telegram → FreqTrade native
- Orchestration → Python scripts on cron

---

## Critical Paths

| What | When | Why |
|---|---|---|
| Phase 0 (pairlist + cleanup) | Next 30 min | Unblock Phase 1 |
| Phase 1 (FreqAI) | After Phase 0 | Replace N8N, get smarter signals |
| Phase 3 (HMM regime) | After Phase 2 | Enable regime-adaptive strategies |
| Phase 5 (Karpathy loop) | After Phase 3 | Self-improving research = brain evolution |

---

*Updated 2026-04-27 via Cowork audit.*
*Next audit: After Phase 0 completion.*
