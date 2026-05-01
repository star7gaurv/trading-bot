# FinBuddy — Collaboration & Autonomy Contract

**Owner:** Gaurav (star7gaurv)  
**Actors:** Perplexity AI (this assistant), Claude Code (Anthropic Sonnet agent), Future agents (Gemini, DeepSeek, etc.)  
**Last Updated:** 2026-05-01 ~16:20 IST

---

## 1. Roles — Who Does What

### 1.1 Perplexity AI — "Architect & Repo Maintainer"

You can treat Perplexity as:
- 🧠 **Architect & strategist** — designs phases, model stack, and trading brain behavior.
- 🛠️ **Repo maintainer** — writes and updates all code, scripts, and docs in GitHub.
- 📚 **Research brain** — reads Freqtrade/FreqAI docs + external resources and proposes improvements.

Perplexity **can**:
- Edit and commit any file in this repo (strategies, FreqAI models, scripts, docs).
- Design new phases (HMM regime engine, Karpathy loop, etc.).
- Keep project memory and tasks in sync (`FINBUDDY_PROJECT_MEMORY.md`, `tasks/*.md`, `CLAUDE_HANDOFF.md`, `finbuddy_memory/*`).
- Propose concrete changes to improve Sharpe / PF / robustness, grounded in real backtests.

Perplexity **cannot**:
- SSH to the server, restart Docker, or run backtests.
- See live logs or real-time PnL.
- Store or access secrets (API keys, passwords).

### 1.2 Claude Code — "DevOps & Runtime Executor"

You can treat Claude Code as:
- 🧑‍💻 **DevOps engineer** — pulls code, deploys changes, manages Docker/cron.
- 📈 **Runtime executor** — runs backtests, hyperopt, and scripts.
- 🕵️ **Live monitor** — watches logs, health, and can rollback if needed.

Claude Code **can**:
- SSH into the Oracle server and run shell commands.
- `git pull` the `gaurav` branch and sync local files.
- Restart Docker containers and inspect logs.
- Run `scripts/run_backtest.sh`, `scripts/tune_stoploss.sh`, hyperopt, and cron setup scripts.
- Update status in task files and memory vault based on actual execution results.

Claude Code **cannot**:
- Change the high-level architecture alone (that is driven by Perplexity + you).
- Decide the project roadmap — it follows `CLAUDE_HANDOFF.md` and tasks.

---

## 2. Task Boundaries — Who Finishes What

### 2.1 Perplexity owns

For each feature / phase:
1. **Design** — architecture, parameters, acceptance criteria.
2. **Implementation in repo** — code, configs, scripts, docs.
3. **Handoff definition** — what Claude Code must run, in what order.

Deliverables Perplexity is responsible for:
- Strategy logic (`FinBuddyFreqAI.py`, future variants).
- FreqAI models (`FinBuddyLLMModel.py`, future models).
- Backtest + robustness tooling (`scripts/run_backtest.sh`, `parse_backtest.py`, `tune_stoploss.sh`, hyperopt files).
- Phase 2/3/4/5/6/7 scripts.
- Documentation: `FINBUDDY_PROJECT_MEMORY.md`, `tasks/*.md`, `CLAUDE_HANDOFF.md`, `finbuddy_memory/*`.

### 2.2 Claude Code owns

For each feature / phase:
1. **Execution** — run the scripts / commands defined by Perplexity.
2. **Verification** — check that results meet criteria (metrics, logs, health).
3. **State updates** — mark tasks ✅/⚠️/❌ and add metrics to memory vault.

Claude Code is responsible for:
- Deploying strategies and models into the live Freqtrade container.
- Running backtests and hyperopt jobs.
- Installing and verifying cron jobs for Phase 2 + Phase 4.
- Watching Freqtrade + FreqAI logs and rolling back if something breaks.

---

## 3. Trigger Points — How Claude Code Knows What To Do

Claude Code should **not** wait for ad-hoc instructions in chat. Instead, it should always:

1. **On session start (or after usage reset):**
   - `git pull origin gaurav`.
   - Read `CLAUDE_HANDOFF.md` from top to bottom.
   - Read `FINBUDDY_PROJECT_MEMORY.md` to understand current phase + model stack.
   - Read the relevant `tasks/phase-X-*.md` file for detailed criteria.

2. **Determine work queue:**
   - Look for any task marked `⚠️ NEEDS REVIEW` or `⬜ PENDING` where the steps explicitly say "Claude Code must".
   - Execute tasks **in order** (Phase 1 before Phase 2, etc.).

3. **After completing each step:**
   - Update the corresponding task file (`tasks/phase-X-*.md`) from ⚠️ → ✅ if criteria are met.
   - Update memory files (`finbuddy_memory/*`, `FINBUDDY_PROJECT_MEMORY.md`) with metrics and notes.
   - Commit and push changes so Perplexity sees updated state.

4. **On usage reset or restart:**
   - Repeat step 1 (pull + read) and continue where it left off.

> In other words: **`CLAUDE_HANDOFF.md` + `tasks/*.md` + `FINBUDDY_PROJECT_MEMORY.md` are the single source of truth** for what Claude Code should do next.

---

## 4. Autonomy Patterns for Claude Code

To make Claude Code more autonomous and not require manual prompts every time:

1. **Routine on login / after reset**
   - Always:
     ```bash
     cd /home/ubuntu/var/www/html/trade/freqtrade
     git pull origin gaurav
     ```
   - Then:
     - Read `CLAUDE_HANDOFF.md` → execute the next unresolved steps.

2. **Cron-like behavior (logical, not system cron)**
   - On each session, if there is nothing urgent in handoff:
     - Check for TODOs in `tasks/phase-2-data-enrichment.md`, `phase-4-obsidian-memory.md`, etc.
     - Pick the topmost `⚠️` or `⬜` task that only needs execution.

3. **Error handling & local decisions**
   - If a command fails because of missing dependency (e.g., `pytrends` not installed):
     - Claude Code may decide to install it inside the container:
       ```bash
       docker exec freqtrade pip install pytrends
       ```
     - Then retry the script.
   - If backtest metrics fail criteria:
     - Do **not** tweak strategy code on its own.
     - Instead, record metrics + logs in `finbuddy_memory/strategies/graveyard.md` and leave Task as ❌ or ⚠️ for Perplexity to adjust code.

4. **Resource & usage awareness**
   - Prefer short, focused runs:
     - Run one backtest, one hyperopt, or one cron installation at a time.
     - Avoid long-running experiments without explicit tasks.
   - When API usage is close to limits (Claude or external APIs), prioritize finishing high-value tasks (deployment, backtest) over exploration.

---

## 5. Current Focus — Task 1.3 Robustness & Hyperopt

### 5.1 What Perplexity has already done

- Tuned `FinBuddyFreqAI.py` stoploss from -3% to -3.5% for better Sharpe in Task 1.3.[see commit history]
- Created `scripts/tune_stoploss.sh` to run multiple backtests with different stoploss values and log metrics to CSV.[scripts/tune_stoploss.sh]
- Documented acceptance criteria and backtest workflow in `scripts/README.md` and `tasks/phase-1-freqai-brain.md`.

### 5.2 What Claude Code should do next (autonomously)

1. **Rerun Task 1.3** with the updated stoploss:
   - `./scripts/run_backtest.sh`.
   - If metrics meet criteria → mark Task 1.3 ✅ and update registry + memory.

2. **If metrics are borderline or still bad:**
   - Run `./scripts/tune_stoploss.sh` to test `-0.03`, `-0.035`, `-0.04`.
   - Save and commit `_tune_stoploss_results.csv` and mention best stoploss in `finbuddy_memory/strategies/winners.md` or a new note.
   - Leave strategy code change (choosing final stoploss) to Perplexity.

3. **Later (Hyperopt phase):**
   - When Perplexity adds a hyperopt space file (e.g., `hyperopts/finbuddy_freqai_space.py`):
     - Claude runs hyperopt commands according to that file.
     - Writes final metrics + chosen parameters to memory.

---

## 6. How You (Gaurav) Should Think About Us

- **Perplexity AI** = "Head of Research + Lead Engineer"
  - Designs the system, writes the code, maintains documentation, and proposes improvements.
- **Claude Code** = "Senior DevOps + Operator"
  - Makes sure the code actually runs on the server, meets criteria, and stays healthy.

Your job becomes:
- Decide priorities (which phase, which objective: Sharpe, PF, DD, automation).
- Review high-level outcomes (metrics, PnL, and safety).
- Occasionally mediate when Perplexity suggests changes that affect your risk appetite.

---

*This contract is a living document. Any time roles or triggers change, Perplexity will update this file and ping you to review.*
