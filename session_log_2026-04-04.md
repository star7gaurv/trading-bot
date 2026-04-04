# AI Crypto Trading Bot — Session Log
**Date:** April 4, 2026
**Server:** ubuntu@gaurav-instance (Oracle Free Tier, REDACTED-SERVER_IP)

## What Was Done
- Confirmed Groq API working (llama-3.3-70b-versatile, ~200ms)
- Added OpenClaw to crontab for reboot survival
- Wiped old FreqTrade trade history (SQLite reset)
- Removed db_url MySQL reference from config.json
- Built N8N v3 pipeline with full context-aware AI logic
- Fixed indicator calculation (Merge Context node)
- Fixed Groq payload (Build Groq Payload code node)
- AI now receives open trade P&L + entry price
- AI adapts prompt: BUY/HOLD when no trade, SELL/HOLD when trade open
- Telegram notifications working with real RSI/MACD/P&L data
- First dry run trade opened: BTC/USDT @ 67206.72 USDT

## Key Decisions
- Dropped OpenRouter — too unreliable on free tier
- Using Groq directly (6000 req/day free, ~200ms latency)
- N8N workflow: v2 archived, v3 active
- Confidence threshold: 65%

## Pending
- Trade Event Handler webhook workflow (import + FreqTrade config)
- FreqTrade webhook config in config.json
