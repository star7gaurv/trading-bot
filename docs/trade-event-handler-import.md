# Finishing the Trade Event Handler N8N Import

**Status:** In progress — picked up from prior session
**Time to complete:** ~10–15 minutes
**Prereq:** Termius SSH access OR laptop access to `n8n.star7gaurav.in`

This closes out the loose end from the last session so we have a clean baseline before starting the Phase 1 refactor in ADR-001.

---

## What we're finishing

A Trade Event Handler workflow was being imported into N8N to receive webhook events from FreqTrade (on trade open, trade close, etc.) and forward them for logging / Telegram notification. The import stalled because the FreqTrade Webhook node's **Production URL** was never retrieved and pasted into FreqTrade's config.

We need to:
1. Get the Production URL of the Webhook node inside the Trade Event Handler workflow in N8N.
2. Paste it into FreqTrade's config under `webhook.url`.
3. Restart FreqTrade.
4. Verify an event flows end-to-end.

---

## Step 1 — Open the Trade Event Handler workflow in N8N

From your phone or laptop:

1. Open `https://n8n.star7gaurav.in`.
2. Log in.
3. In the left sidebar, navigate to **Workflows**.
4. Open the workflow named **Trade Event Handler** (exact name may vary — it's the one imported last session that still says "Production URL missing" or similar on its Webhook node).

If you can't find it:
- It may be inside an N8N "Project" rather than the default workspace. Check the project switcher at the top.
- Or search the workflow list by keyword `webhook` or `trade`.

---

## Step 2 — Copy the Production URL from the Webhook node

1. Click on the **Webhook** node (the first node in the workflow).
2. In the node's settings panel on the right, you'll see two URLs: **Test URL** and **Production URL**.
3. Copy the **Production URL**. It looks like:

   ```
   https://n8n.star7gaurav.in/webhook/<uuid>/trade-event
   ```

   (The exact path depends on how the workflow was built — whatever N8N shows is what you copy.)

**Important:** Use the Production URL, NOT the Test URL. The Test URL only works while you have the workflow open in the N8N editor; Production URL works once the workflow is active.

---

## Step 3 — Activate the workflow

In the top-right of the N8N workflow editor, flip the **Active** toggle to ON.

The workflow is now listening at the Production URL. Until this toggle is on, POSTs to the URL will fail with a 404.

---

## Step 4 — Paste the URL into FreqTrade's config

SSH into the server via Termius:

```bash
ssh ubuntu@REDACTED-SERVER_IP
cd /home/ubuntu/var/www/html/trade/
```

Edit the FreqTrade config:

```bash
nano freqtrade/user_data/config.json
```

Find the `webhook` section. If it doesn't exist, add one. It should look like:

```json
{
  "webhook": {
    "enabled": true,
    "url": "https://n8n.star7gaurav.in/webhook/<uuid>/trade-event",
    "format": "json",
    "retries": 3,
    "retry_delay": 0.2,
    "webhookbuy": {
      "type": "webhookbuy",
      "pair": "{pair}",
      "exchange": "{exchange}",
      "market_cap": "{market_cap}",
      "limit": "{limit}",
      "amount": "{amount}",
      "open_date": "{open_date}",
      "stake_amount": "{stake_amount}",
      "stake_currency": "{stake_currency}",
      "fiat_currency": "{fiat_currency}",
      "order_type": "{order_type}",
      "current_rate": "{current_rate}"
    },
    "webhooksell": {
      "type": "webhooksell",
      "pair": "{pair}",
      "gain": "{gain}",
      "limit": "{limit}",
      "amount": "{amount}",
      "open_rate": "{open_rate}",
      "current_rate": "{current_rate}",
      "profit_amount": "{profit_amount}",
      "profit_ratio": "{profit_ratio}",
      "sell_reason": "{sell_reason}"
    },
    "webhookstatus": {
      "type": "webhookstatus",
      "status": "{status}"
    }
  }
}
```

Paste in the Production URL from Step 2. Save and exit nano (`Ctrl+O`, `Enter`, `Ctrl+X`).

(If a `webhook` section already exists, just replace the `url` value.)

---

## Step 5 — Restart FreqTrade

```bash
cd /home/ubuntu/var/www/html/trade/
docker compose restart freqtrade
```

Watch the logs for errors:

```bash
docker compose logs -f freqtrade
```

You should see FreqTrade start up cleanly. Look specifically for any line mentioning "webhook" — it should say the webhook is enabled and the URL is configured. If it fails to start, the usual cause is a JSON syntax error in `config.json` (extra comma, missing quote). Fix and restart.

`Ctrl+C` to stop following the logs once startup is clean.

---

## Step 6 — Verify end-to-end

Two ways to confirm events flow:

**Option A — wait for a real dry-run trade.**
FreqTrade is in dry-run mode trading on the 15m cycle. Next time it opens or closes a position, an event will fire. Watch N8N's execution log for Trade Event Handler — you should see an execution appear within seconds of the trade.

**Option B — force a test trade from FreqTrade.**

```bash
docker compose exec freqtrade freqtrade forcebuy BTC/USDT
```

This triggers a buy event immediately. Go to N8N → Trade Event Handler → Executions tab. You should see a new execution with the webhook payload from FreqTrade (pair, amount, rate, etc.).

If nothing arrives in N8N after ~30 seconds:
- Check FreqTrade logs for webhook errors (`docker compose logs freqtrade | grep -i webhook`).
- Check that the Trade Event Handler workflow is **Active** (toggle top-right of N8N editor).
- Check that the URL you pasted into FreqTrade matches the Production URL exactly.
- Check that `n8n.star7gaurav.in` resolves and is reachable from inside the FreqTrade container.

---

## Step 7 — Commit

On the server:

```bash
cd /home/ubuntu/var/www/html/trade/
git add freqtrade/user_data/config.json
git commit -m "Enable FreqTrade webhook -> N8N Trade Event Handler"
git push
```

---

## Definition of done

- [ ] Trade Event Handler workflow is **Active** in N8N.
- [ ] FreqTrade `config.json` has the Production URL set.
- [ ] FreqTrade has been restarted and started cleanly.
- [ ] At least one real or forced trade event has appeared in the N8N execution log.
- [ ] Changes committed to `star7gaurav/trading-bot` on the `main` branch.

Once all five are ticked, this loose end is closed and we can start on the signal-generator / trade-executor split.
