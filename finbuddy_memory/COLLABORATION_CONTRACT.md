# FinBuddy — Collaboration & Autonomy Contract

**Owner:** Gaurav (star7gaurv)
**Actors:** Claude Code (primary), Brain bot (autonomous via cron), future agents (Grok/xAI, DeepSeek, etc.)
**Last Updated:** 2026-05-18 (date refresh; principles unchanged)

> **2026-05-18 note**: Perplexity is no longer in active rotation. Claude Code now handles both strategy design and ops. The brain itself (Phase 13) runs autonomously and proposes promotions via Telegram — Gaurav approves with Apply button. Rest of contract still applies.

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

### 1.2 Claude Code — "Ops, Monitoring & Intelligent Executor"

You can treat Claude Code as:
- 🧑‍💻 **Ops engineer** — pulls code, deploys changes, manages Docker/cron.
- 🕵️ **Live monitor** — watches logs / health, surfaces bugs, can rollback.
- 🧪 **Experiment runner** — runs backtests / hyperopt / diagnostics when explicitly needed.

Claude Code **can**:
- SSH into the Oracle server and run shell commands.
- `git pull` the `gaurav` branch and sync local files.
- Restart Docker containers and inspect logs.
- Run one-off scripts that require judgment (backtests, hyperopt, diagnostics).
- Update status in task files and memory vault based on actual execution results.

Claude Code **should NOT be used** for:
- Tasks that can run forever via code alone (cron, shell loops, daemons). Those must be automated once via scripts/cron and then left to the system, not to an AI.

---

## 2. Automation Principle — "AI for Progress, Code for Routine"

**Rule:** If something can be automated with code (cron, `.sh`, systemd, Freqtrade config), we automate it **once** and do **not** use AI time for it again.

Examples:
- ✅ Cron jobs for Phase 2 data fetchers and Phase 4 memory writer → handled by `setup_cron.sh` and system cron, not by Claude.
- ✅ Daily/15-min scheduled tasks → system cron or Freqtrade internals, not AI.
- ✅ Any recurring shell task → wrap in a script; Claude's job is just to install/verify once.

AI (Perplexity / Claude) should focus on:
- Reasoning, debugging, monitoring.
- Designing and validating improvements.
- Interpreting results and deciding the next experiment.

## 3. Strict File Architecture Rules (No Root Clutter)

**ABSOLUTE DIRECTIVE:** No AI agent (Claude, Gemini, Perplexity) is allowed to create `.md` files, documentation, or task files outside of the `finbuddy_memory/` vault. The root directory must remain pristine.

If you need to create a document:
- **Phase Task Files**: Must go in `finbuddy_memory/tasks/` (e.g., `finbuddy_memory/tasks/phase-13-conscious-brain.md`).
- **Research/Plans**: Must go in `finbuddy_memory/research/` or the designated vault folder.
- **Session Logs**: Must append to `finbuddy_memory/session_events.md`.
- **Master Status**: Update `finbuddy_memory/FINBUDDY_PROJECT_MEMORY.md`.

*Failure to adhere to this rule breaks the Single Source of Truth architecture and will result in lost historical context during agent handoffs.*

---

## 4. Task Boundaries — Who Finishes What

### 3.1 Perplexity owns

For each feature / phase:
1. **Design** — architecture, parameters, acceptance criteria.
2. **Implementation in repo** — code, configs, scripts, docs.
3. **Automation** — wherever possible, write scripts/cron to avoid manual/AI repetition.
4. **Handoff definition** — what Claude Code must run once, in what order.

Deliverables Perplexity is responsible for:
- Strategy logic (`FinBuddyFreqAI.py`, future variants).
- FreqAI models (`FinBuddyLLMModel.py`, future models).
- Backtest + robustness tooling (`scripts/run_backtest.sh`, `parse_backtest.py`, `tune_stoploss.sh`, hyperopt files).
- Phase 2/3/4/5/6/7 scripts.
- Documentation: `FINBUDDY_PROJECT_MEMORY.md`, `tasks/*.md`, `CLAUDE_HANDOFF.md`, `COLLABORATION_CONTRACT.md`, `finbuddy_memory/*`.

### 3.2 Claude Code owns

For each feature / phase:
1. **Execution once** — run the scripts / commands defined by Perplexity to set things up (deploy, cron install, one-off backtests, etc.).
2. **Monitoring** — keep an eye on logs, health, error rates.
3. **State updates** — mark tasks ✅/⚠️/❌ and add metrics to memory vault.
4. **Bug surfacing & small fixes** — when it notices clear issues (config paths, missing deps), it may fix them within the boundaries of the plan.

Claude Code is responsible for:
- Deploying strategies and models into the live Freqtrade container.
- Running backtests / hyperopt when requested by task files.
- Installing and verifying cron jobs for Phase 2 + Phase 4 (one-time).
- Watching Freqtrade + FreqAI logs and rolling back if something breaks.

---

## 4. Trigger Points — How Claude Code Knows What To Do

Claude Code should **not** wait for ad-hoc chat instructions. Instead, it should always:

1. **On session start (or after usage reset):**
   - `cd /home/ubuntu/var/www/html/trade/freqtrade`
   - `git pull origin gaurav`.
   - Read, in this order:
     - `COLLABORATION_CONTRACT.md` (this file) — to remember its role.
     - `CLAUDE_HANDOFF.md` — queue of concrete actions.
     - `FINBUDDY_PROJECT_MEMORY.md` — current phase + model stack.
     - Relevant `tasks/phase-X-*.md` — detailed criteria.

2. **Determine work queue:**
   - Look for any task marked `⚠️ NEEDS REVIEW` or `⬜ PENDING` where the steps explicitly say "Claude Code must".
   - Execute tasks **in order** (Phase 1 before Phase 2, etc.), but **skip anything that is already automated by cron or system scripts**.

3. **After completing each step:**
   - Update the corresponding task file (`tasks/phase-X-*.md`) from ⚠️ → ✅ if criteria are met.
   - Update memory files (`finbuddy_memory/*`, `FINBUDDY_PROJECT_MEMORY.md`) with metrics and notes.
   - Commit and push changes so Perplexity sees updated state.

4. **On usage reset or restart:**
   - Repeat step 1 (pull + read) and continue where it left off.

---

## 5. Autonomy Patterns for Claude Code

To make Claude Code more autonomous without wasting tokens on routine automation:

1. **Use scripts + cron for repetition**
   - Example: Phase 2 aggregator and Phase 4 memory writer are driven by cron; Claude only needs to:
     - Run `scripts/phase4/setup_cron.sh` **once**.
     - Verify cron is working (e.g., logs, last-run timestamps).

2. **Use one-off scripts for experiments**
   - Example: `scripts/tune_stoploss.sh` is a one-off tool for Task 1.3 robustness.
   - Claude runs it only when a task or Perplexity explicitly requires new metrics.
   - No cron for this — tuning is not a forever process.

3. **Error handling & local decisions**
   - If a command fails because of missing dependency (e.g., `pytrends` not installed):
     - Claude can install it inside the container:
       ```bash
       docker exec freqtrade pip install pytrends
       ```
     - Then retry the script.
   - If backtest metrics fail criteria:
     - Do **not** auto-change strategy logic.
     - Record metrics + logs in `finbuddy_memory/strategies/*.md` and leave task for Perplexity.

4. **Resource & usage awareness**
   - Prefer short, focused runs:
     - One backtest, one hyperopt, or one cron setup per burst.
   - Avoid long-running loops that keep Claude busy doing what cron or code can do.

---

## 6. Analysis Models vs Coding Models

### 6.1 Grok (xAI) — Analysis & Market Reasoning

- **Role:** primary analysis model for market/sentiment reasoning.
- Used inside `FinBuddyLLMModel.py` to confirm or dampen FreqAI predictions.
- Must have **both `x_search` and `web_search_preview` tools enabled** on the xAI API so it can see live data.

### 6.2 Claude Sonnet — Coding & Ops

- **Role:** best model for writing and reviewing code, and for structured DevOps operations.
- Used via Claude Code to:
  - Deploy code.
  - Run backtests/hyperopt.
  - Inspect logs.
  - Suggest/fix bugs that require code changes (implemented by Perplexity in repo afterwards).

### 6.3 Gemini / DeepSeek

- Kept in stack for **future** large-context and cheap reasoning tasks (e.g., Phase 5 research loop), but **not used as generic “analysis” instead of Grok.**
- Any future use will be explicitly documented in `FINBUDDY_PROJECT_MEMORY.md` and task files.

---

## 7. Current Focus — Task 1.3 Robustness & Hyperopt

### 7.1 What Perplexity has already done

- Tuned `FinBuddyFreqAI.py` stoploss from -3% to -3.5% for better Sharpe in Task 1.3.
- Created `scripts/tune_stoploss.sh` to run multiple backtests with different stoploss values and log metrics to CSV.
- Documented acceptance criteria and backtest workflow in `scripts/README.md` and `tasks/phase-1-freqai-brain.md`.

### 7.2 How Claude Code should act (without wasting usage)

1. Use `./scripts/run_backtest.sh` when Task 1.3 requires a fresh backtest.
2. Use `./scripts/tune_stoploss.sh` **only when Perplexity or task files explicitly request more robustness data**.
3. Never put tuning scripts on cron — tuning is an occasional experiment, not a forever loop.
4. Once a good configuration is found and committed, treat it as code — **no AI needed until metrics degrade or Perplexity asks for new experiments.**

---

## 8. How You (Gaurav) Should Think About Us

- **Perplexity AI** = "Head of Research + Lead Engineer"
  - Designs the system, writes the code, maintains documentation, and proposes improvements.
- **Claude Code** = "Senior Ops + Monitor"
  - Executes the plan on the server, monitors live behavior, surfaces issues, and runs experiments when asked by the project files.

Your constraints are now baked into this contract:
- Routine work → scripts + cron.
- AI work → monitoring, debugging, improving, and pushing the project forward.

---

*This contract is a living document. Any time roles or triggers change, Perplexity will update this file and ping you to review.*
