// ============================================================
// FinBuddy Groq Prompt Builder — N8N Code Node (v4 workflow)
// Place this node AFTER the context reader and BEFORE the Groq HTTP Request.
// Replaces (or wraps) your existing prompt builder code node.
// Node type: Code | Language: JavaScript | Mode: Run Once For All Items
// ============================================================

const items = $input.all();
const item = items[0].json;

// --- Pull in existing market data (adjust field names to match your v3 workflow) ---
const symbol      = item.symbol      || 'BTC/USDT';
const rsi         = item.rsi         || 'N/A';
const macd        = item.macd        || 'N/A';
const price       = item.price       || 'N/A';
const tradeOpen   = item.tradeOpen   || false;
const pnl         = item.pnl         || null;
const memory      = item.finbuddy_memory || '[memory not available]';

// --- Build trade context section ---
let tradeContext = '';
if (tradeOpen && pnl !== null) {
  tradeContext = `Open Trade: YES | Current P&L: ${pnl}%`;
} else {
  tradeContext = 'Open Trade: NO | Flat position';
}

// --- Build the full prompt ---
const prompt = `You are FinBuddy, an autonomous crypto trading AI.

${memory}

=== Current Market Data ===
Symbol : ${symbol}
Price  : ${price}
RSI    : ${rsi}
MACD   : ${macd}
${tradeContext}

=== Your Task ===
Based on your memory (regime, recent research, risk flags) AND the current market data above, decide:
- Signal: BUY, SELL, or HOLD
- Confidence: LOW, MEDIUM, or HIGH
- Reason: 1-2 sentences explaining why

Reply in this exact JSON format:
{
  "signal": "BUY|SELL|HOLD",
  "confidence": "LOW|MEDIUM|HIGH",
  "reason": "..."
}`;

return [{
  json: {
    ...item,
    groq_prompt: prompt
  }
}];
