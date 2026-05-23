# Phase 4 — Obsidian Memory Vault (Complete Auto-Write Pipeline)

**Status:** ✅ LIVE (cron `*/15 * * * *` memory_writer + auto-commit)

> **2026-05-18 update**: Vault writes + auto-commits work. Tasks 4.3 and 4.4 ("Wire CONTEXT.md into N8N", "Append signals to log via N8N") are **dead** — N8N permanently disabled. AI agents (Claude Code + brain) read finbuddy_memory directly.

> The finbuddy_memory/ folder is the brain's living memory — readable in Obsidian.
> The server auto-writes all key brain states here and auto-commits to git.
> Gaurav pulls locally and opens in Obsidian to inspect what the brain knows.

---

## Current State
- Vault structure created ✅
- CONTEXT.md exists + auto-synced ✅
- ~~N8N reads CONTEXT.md~~ N8N dead — strategy + brain read CONTEXT.md / regime files directly ✅
- Server writes to vault ❌ (writer script not complete)
- Auto-git-commit ❌ (not set up)

---

## Vault Structure

```
finbuddy_memory/
├── CONTEXT.md                  ← Master summary, injected into every AI prompt
├── SERVER_SETUP.md             ← Server config reference
├── regimes/
│   ├── current.md              ← Current HMM regime (auto-written by Phase 3)
│   └── history.md              ← Regime transition log
├── signals/
│   └── log.md                  ← Recent signal history
├── research/
│   ├── README.md               ← Research loop status
│   └── [date]-[topic].md       ← Individual research notes (auto-generated)
├── strategies/
│   ├── winners.md              ← Promoted strategies with stats
│   └── graveyard.md            ← Retired strategies with reason
└── scripts/
    ├── memory_writer.py        ← Master auto-write script
    └── git_commit.sh           ← Auto-commit helper
```

---

## Task 4.1 — Build Memory Writer Script
**Status:** ⬜ Pending  
**Effort:** 2–3 hours  
**File:** `finbuddy_memory/scripts/memory_writer.py`

Master script that collects brain state from all sources and writes to vault files.

### What it writes

**CONTEXT.md** — master summary (re-written every 15 min)
```markdown
# FinBuddy — Master Context
Last updated: 2026-04-27 12:00 UTC

## Current Regime
Regime: BULL | Confidence: 82% | Since: 2026-04-20

## Active Strategy
rsi_macd_ai_v1 | 15m | Binance | Running

## Recent Signals (last 24h)
- BTC/USDT: BUY @ 67,234 | Confidence: 0.78 | P&L: +2.3%
- ETH/USDT: HOLD | Confidence: 0.43
- SOL/USDT: SELL @ 142.30 | P&L: -0.8%

## Risk Flags
- None

## Open Trades
- BTC/USDT: Entry 67,206 | Current 68,900 | P&L: +2.52%
```

**signals/log.md** — append each signal as it fires

**strategies/winners.md** — update when strategy is promoted

**strategies/graveyard.md** — update when strategy is retired

### Data sources the script reads
- FreqTrade API: `http://localhost:8080/api/v1/status` — open trades
- FreqTrade API: `http://localhost:8080/api/v1/profit` — overall P&L
- `finbuddy_memory/regimes/current.md` — current regime
- `strategies/registry.json` — active strategies

---

## Task 4.2 — Auto Git Commit Script
**Status:** ⬜ Pending  
**Effort:** 30 minutes  
**File:** `finbuddy_memory/scripts/git_commit.sh`

After memory_writer.py runs, auto-commit changes to git so Gaurav can pull locally.

```bash
#!/bin/bash
cd /home/ubuntu/var/www/html/trade
git add finbuddy_memory/
git diff --staged --quiet || git commit -m "chore: finbuddy memory update $(date +%Y-%m-%d\ %H:%M)"
git push origin master 2>/dev/null || true
```

### Cron (runs after memory_writer)
```
*/15 * * * * python3 /path/to/memory_writer.py && bash /path/to/git_commit.sh
```

---

## Task 4.3 — Wire CONTEXT.md into N8N Signal Prompt
**Status:** ⬜ Pending (after 4.1)  
**Effort:** 1 hour

Add an N8N node before the Groq call that reads CONTEXT.md from the server and prepends it to the AI prompt.

### N8N node: "Read FinBuddy Context"
- Type: Execute Command or HTTP Request (read local file via FreqTrade API or sidecar)
- Output: contents of CONTEXT.md
- Inject into Groq system prompt before market data

The AI will then know: current regime, recent signals, open trades, risk flags — all from memory.

---

## Task 4.4 — Signal History Auto-Logger
**Status:** ⬜ Pending (after 4.1)  
**Effort:** 1 hour

Every time N8N generates a signal, append it to `finbuddy_memory/signals/log.md`:

```markdown
## 2026-04-27 12:00 UTC
- Pair: BTC/USDT
- Signal: BUY
- Confidence: 0.78
- Regime: BULL
- RSI: 58.2 | MACD: +0.003 | ATR: 1245
- Reasoning: MACD bullish crossover, RSI neutral, regime BULL
---
```

This becomes training data for the Karpathy loop later.

---

## Phase 4 Complete When
- [ ] `memory_writer.py` runs every 15 min and updates CONTEXT.md
- [ ] All vault files update automatically
- [ ] Git auto-commits after every memory write
- [ ] Gaurav can `git pull` locally and open fresh state in Obsidian
- [ ] N8N injects CONTEXT.md into every Groq prompt
- [ ] Signals are logged to `signals/log.md` automatically

---
*← [[FINBUDDY_PROJECT_MEMORY]] · [[tasks/TASKS]]*
