# Lore Ledger

A phone-first price screener for Disney Lorcana Enchanted, Iconic and promo cards.
TCGplayer market prices via the [JustTCG](https://justtcg.com) API, candlestick charts,
technical indicators, and preset screens for finding cards trading well below where they have been.

The site is static: `index.html` is the whole app, `data.json` holds every card with up to
a year of daily prices (and grows past that as refreshes accumulate), and `img/` holds the card art.

## Hosting (GitHub Pages)

1. **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`, folder `/ (root)` → Save.
   The site appears at `https://<you>.github.io/<repo>/` within a minute or two.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   name `JUSTTCG_KEY`, value: your JustTCG API key.
3. **Actions** tab → *Refresh prices* → *Run workflow* once to confirm it works.
   After that it runs every day at 10:23 UTC and commits the new `data.json` (and any new card images).

On your phone, open the site in Safari → Share → **Add to Home Screen**. It installs as a standalone
app with its own icon and works offline from the last data it loaded.

## Refreshing

- **Automatic**: the GitHub Action above (about 29 API requests a day on the free tier's 100/day).
- **Manual, from the phone**: About tab → paste your API key → *Refresh prices now*. Takes about
  three minutes because the free tier allows 10 requests a minute. The key and all price history stay
  in the phone's browser storage; nothing is sent anywhere but JustTCG.

Both paths merge new history onto old, so the chart window keeps growing.

## Local refresh

```
pip install pillow
JUSTTCG_KEY=tcg_... python3 scripts/refresh.py
```

## Notes on the data

- Prices are Near Mint, foil printing where one exists. Lightly Played and other printings show on each card page.
- The source records one price per day. Daily candles open at the previous close; weekly candles are true OHLC.
- All-time high and low come from the full sales record even for cards older than the chart window.
- Charts use [Lightweight Charts](https://github.com/tradingview/lightweight-charts) by TradingView (Apache 2.0).
