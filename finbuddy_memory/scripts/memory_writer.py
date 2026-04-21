#!/usr/bin/env python3
"""
FinBuddy Memory Writer
Appends a research cycle entry to today's research log.
Called by the Karpathy research loop after each cycle.

Usage:
  python3 memory_writer.py --theme "BTC consolidating" --insight "RSI divergence reliable" --risk "Altcoin liquidation risk" --action "Tighten SL on small caps"
  python3 memory_writer.py --signal BUY --regime BULL --rsi 58.2 --macd 0.003 --reason "Bullish crossover confirmed"
  python3 memory_writer.py --regime-change --from NEUTRAL --to BULL --confidence 0.78
"""

import argparse
import os
from datetime import datetime

# Paths (relative to repo root)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
MEMORY_ROOT = os.path.join(REPO_ROOT, "finbuddy_memory")
RESEARCH_DIR = os.path.join(MEMORY_ROOT, "research")
SIGNALS_LOG = os.path.join(MEMORY_ROOT, "signals", "log.md")
REGIME_CURRENT = os.path.join(MEMORY_ROOT, "regimes", "current.md")
REGIME_HISTORY = os.path.join(MEMORY_ROOT, "regimes", "history.md")
CONTEXT_FILE = os.path.join(MEMORY_ROOT, "CONTEXT.md")


def write_research_entry(theme, insight, risk, action, cycle_num=None):
    """Append a research cycle digest to today's research file."""
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(RESEARCH_DIR, f"{today}.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Create file with header if new
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(f"# Research Log — {today}\n")
            f.write(f"→ [[../CONTEXT]]  |  [[README]]\n\n")

    cycle_label = f"Cycle #{cycle_num}" if cycle_num else "Manual entry"
    entry = f"""
## {timestamp} | {cycle_label}
- **Market theme:** {theme}
- **Strategy insight:** {insight}
- **Risk flag:** {risk}
- **Action taken:** {action}
"""
    with open(filepath, "a") as f:
        f.write(entry)

    print(f"✅ Research entry written to {filepath}")


def write_signal_entry(signal, regime, rsi, macd, reason):
    """Append a signal log entry."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"""
### {timestamp} | Signal: {signal.upper()}
- **Regime at time:** {regime}
- **RSI:** {rsi} | **MACD:** {macd}
- **AI reasoning:** "{reason}"
- **Action taken:** FreqTrade notified
"""
    with open(SIGNALS_LOG, "a") as f:
        f.write(entry)

    print(f"✅ Signal entry written: {signal.upper()} at {timestamp}")


def update_regime(from_regime, to_regime, confidence):
    """Update current regime file and append to history."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    today = datetime.now().strftime("%Y-%m-%d")

    # Update current.md
    current_content = f"""# Current Market Regime
> Auto-updated by the HMM engine on every regime change.
> N8N reads this file as the single source of truth for current regime.
> Part of → [[../CONTEXT]]

---

## Status
```
Regime     : {to_regime}
Confidence : {confidence}
Detected   : {timestamp}
Previous   : {from_regime}
```

## Regime Guide
| Regime    | Meaning                        | Strategy Posture          |
|-----------|--------------------------------|---------------------------|
| CRASH     | Sharp rapid decline            | Exit all, hold cash       |
| BEAR      | Sustained downtrend            | Reduce exposure, short    |
| NEUTRAL   | Sideways, no clear trend       | Small positions, tight SL |
| BULL      | Sustained uptrend              | Full exposure, trail SL   |
| EUPHORIA  | Parabolic / overextended       | Take profits, reduce risk  |

## Full History
→ [[history]]

---
*Updated automatically by the HMM engine. Do not edit manually.*
"""
    with open(REGIME_CURRENT, "w") as f:
        f.write(current_content)

    # Append to history.md — find the header row and insert after
    history_row = f"| {today} | {from_regime} | {to_regime} | {confidence} | Auto-detected by HMM |\n"
    with open(REGIME_HISTORY, "r") as f:
        lines = f.readlines()

    # Replace the placeholder row if still there, otherwise append before the footer
    new_lines = []
    inserted = False
    for line in lines:
        if "HMM engine not yet wired" in line and not inserted:
            new_lines.append(history_row)
            inserted = True
        else:
            new_lines.append(line)
    if not inserted:
        # append before the last --- line
        for i in range(len(new_lines) - 1, -1, -1):
            if new_lines[i].strip() == "---":
                new_lines.insert(i, history_row)
                break

    with open(REGIME_HISTORY, "w") as f:
        f.writelines(new_lines)

    print(f"✅ Regime updated: {from_regime} → {to_regime} (confidence: {confidence})")


def main():
    parser = argparse.ArgumentParser(description="FinBuddy Memory Writer")
    subparsers = parser.add_subparsers(dest="command")

    # Research entry
    research = subparsers.add_parser("research", help="Write a research cycle entry")
    research.add_argument("--theme", required=True)
    research.add_argument("--insight", required=True)
    research.add_argument("--risk", required=True)
    research.add_argument("--action", required=True)
    research.add_argument("--cycle", type=int, help="Cycle number")

    # Signal entry
    signal = subparsers.add_parser("signal", help="Log a trade signal")
    signal.add_argument("--signal", required=True, choices=["BUY", "SELL", "HOLD"])
    signal.add_argument("--regime", required=True)
    signal.add_argument("--rsi", required=True)
    signal.add_argument("--macd", required=True)
    signal.add_argument("--reason", required=True)

    # Regime change
    regime = subparsers.add_parser("regime", help="Update current regime")
    regime.add_argument("--from", dest="from_regime", required=True)
    regime.add_argument("--to", dest="to_regime", required=True)
    regime.add_argument("--confidence", required=True)

    args = parser.parse_args()

    if args.command == "research":
        write_research_entry(args.theme, args.insight, args.risk, args.action, args.cycle)
    elif args.command == "signal":
        write_signal_entry(args.signal, args.regime, args.rsi, args.macd, args.reason)
    elif args.command == "regime":
        update_regime(args.from_regime, args.to_regime, args.confidence)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
