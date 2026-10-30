#!/usr/bin/env python3
"""Daily refresh for Lore Ledger.
1. Pulls every Enchanted / Iconic / Promo Lorcana card from JustTCG with 1y daily history (paced for the free tier).
2. Merges the new history onto the existing data.json so history accumulates beyond the API window.
3. Downloads card art for any new cards into img/.
Run from the repo root:  JUSTTCG_KEY=tcg_... python3 scripts/refresh.py
"""
import json, os, sys, time, io, glob, shutil, tempfile, concurrent.futures, urllib.request, urllib.parse
try:
    from PIL import Image
except ImportError:
    Image = None

KEY = os.environ.get("JUSTTCG_KEY")
if not KEY:
    raise SystemExit("JUSTTCG_KEY is not set")
BASE = "https://api.justtcg.com/v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = tempfile.mkdtemp(prefix="lorcana-raw-")
PACE = 6.6  # seconds between requests (free tier: 10/min)
DAY = 86400
KEEP_RARITY = {"Enchanted": "E", "Iconic": "I", "Promo": "P"}
PRINT_PREF = ["Holofoil", "Cold Foil", "Normal"]

QUERIES = [
    ("enchanted", {"q": "Enchanted"}),
    ("iconic", {"q": "Iconic"}),
    ("promo", {"set": "disney-lorcana-promo-cards-disney-lorcana"}),
    ("d23", {"set": "d23-promos-disney-lorcana"}),
    ("d100", {"set": "disney100-promos-disney-lorcana"}),
]

_last = [0.0]
def api(path, params):
    wait = PACE - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-api-key": KEY})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print("HTTP", e.code, body, flush=True)
            if e.code == 429: time.sleep(40); continue
            raise
        except Exception as e:
            print("ERR", e, flush=True); time.sleep(15)
    raise SystemExit("request failed repeatedly")

# ---------- fetch ----------
raw = {}
meta = {}
for name, p in QUERIES:
    offset = 0
    while True:
        d = api("/cards", dict(p, game="disney-lorcana", limit=20, offset=offset,
                               include_price_history="true", priceHistoryDuration="1y"))
        for c in d.get("data", []): raw[c["id"]] = c
        m = d.get("meta", {}); meta = d.get("_metadata", meta)
        print(f"{name} offset={offset} got={len(d.get('data', []))} total={m.get('total')} dailyLeft={meta.get('apiDailyRequestsRemaining')}", flush=True)
        if not m.get("hasMore"): break
        offset += 20
sets_resp = api("/sets", {"game": "disney-lorcana"})
sets = {s["id"]: {"id": s["id"], "name": s["name"], "rel": (s.get("release_date") or "")[:10]} for s in sets_resp.get("data", [])}
print("fetched cards:", len(raw), "sets:", len(sets), flush=True)

# ---------- process ----------
def pick_variant(variants, cond, printing):
    for v in variants:
        if v["condition"] == cond and v["printing"] == printing: return v
    return None

def prefer_printing(variants):
    prints = {v["printing"] for v in variants if "Japanese" not in v["printing"]}
    for p in PRINT_PREF:
        if p in prints: return p
    return next(iter(prints), None)

def hist_to_series(ph):
    if not ph: return None, []
    pts = sorted(((int(round(x["t"] / DAY)), x["p"]) for x in ph), key=lambda a: a[0])
    d0 = pts[0][0]; d1 = pts[-1][0]
    arr = [None] * (d1 - d0 + 1)
    for d, p in pts: arr[d - d0] = round(p, 2)
    return d0, arr

def merge_series(old_d0, old_arr, new_d0, new_arr):
    if old_d0 is None or not old_arr: return new_d0, new_arr
    if new_d0 is None or not new_arr: return old_d0, old_arr
    d0 = min(old_d0, new_d0)
    d1 = max(old_d0 + len(old_arr), new_d0 + len(new_arr)) - 1
    arr = [None] * (d1 - d0 + 1)
    for i, p in enumerate(old_arr):
        if p is not None: arr[old_d0 + i - d0] = p
    for i, p in enumerate(new_arr):
        if p is not None: arr[new_d0 + i - d0] = p
    return d0, arr

def stats(v):
    g = v.get
    return {
        "c1": g("priceChange24hr"), "c7": g("priceChange7d"), "c30": g("priceChange30d"), "c90": g("priceChange90d"),
        "a30": g("avgPrice30d"), "a90": g("avgPrice90d"),
        "mn7": g("minPrice7d"), "mx7": g("maxPrice7d"), "mn30": g("minPrice30d"), "mx30": g("maxPrice30d"),
        "mn90": g("minPrice90d"), "mx90": g("maxPrice90d"), "mn1y": g("minPrice1y"), "mx1y": g("maxPrice1y"),
        "cov30": g("covPrice30d"), "cov90": g("covPrice90d"),
        "sl7": g("trendSlope7d"), "sl30": g("trendSlope30d"), "sl90": g("trendSlope90d"),
        "n7": g("priceChangesCount7d"), "n30": g("priceChangesCount30d"), "n90": g("priceChangesCount90d"),
        "rr30": g("priceRelativeTo30dRange"), "rr90": g("priceRelativeTo90dRange"),
        "ath": g("maxPriceAllTime"), "athd": (g("maxPriceAllTimeDate") or "")[:10],
        "atl": g("minPriceAllTime"), "atld": (g("minPriceAllTimeDate") or "")[:10],
    }

PREV = os.path.join(ROOT, "data.json")
prev, prev_sets = {}, {}
if os.path.exists(PREV):
    try:
        pj = json.load(open(PREV))
        prev = {c["i"]: c for c in pj["cards"]}
        prev_sets = {s["id"]: s for s in pj.get("sets", [])}
    except Exception as e:
        print("previous data.json unreadable:", e)
if not sets: sets = prev_sets
for sid, s in prev_sets.items(): sets.setdefault(sid, s)

today = int(time.time() // DAY)
cards = []
for cid, c in raw.items():
    r = KEEP_RARITY.get(c.get("rarity"))
    if not r or c.get("number") in (None, "N/A"): continue
    variants = c["variants"]
    if any(v["condition"] == "Sealed" for v in variants): continue
    pr = prefer_printing(variants)
    if not pr: continue
    prim = pick_variant(variants, "Near Mint", pr); cond = "NM"
    if prim is None:
        prim = pick_variant(variants, "Lightly Played", pr); cond = "LP"
    if prim is None: continue
    lpv = pick_variant(variants, "Lightly Played", pr) if cond == "NM" else None
    d0, arr = hist_to_series(prim.get("priceHistory"))
    old = prev.get(cid)
    if old and old.get("h"):
        d0, arr = merge_series(old.get("h0"), old["h"], d0, arr)
    if d0 is not None and prim.get("price") is not None:
        if d0 + len(arr) - 1 < today: arr += [None] * (today - (d0 + len(arr) - 1))
        arr[-1] = round(prim["price"], 2)
    alts = [{"pr": v["printing"], "p": v["price"]} for v in variants
            if v["condition"] == "Near Mint" and v["printing"] != pr and "Japanese" not in v["printing"]]
    cards.append({
        "i": cid, "n": c["name"].replace(" (Enchanted)", "").replace(" (Iconic)", ""),
        "s": c["set_name"], "sc": c["set"], "no": c.get("number"), "r": r, "t": c.get("tcgplayerId"),
        "c": cond, "pr": pr, "p": prim.get("price"), "upd": prim.get("lastUpdated"), "st": stats(prim),
        "lp": ({"p": lpv["price"], "c7": lpv.get("priceChange7d"), "c30": lpv.get("priceChange30d"), "c90": lpv.get("priceChange90d")} if lpv else None),
        "alt": alts, "h0": d0, "h": arr,
    })

seen = {c["i"] for c in cards}
for cid, old in prev.items():
    if cid not in seen:
        old = dict(old); old["stale"] = True; cards.append(old)
cards.sort(key=lambda c: -(c["p"] or 0))
out = {"generated": int(time.time()), "sets": sorted(sets.values(), key=lambda s: s["rel"]), "cards": cards}
json.dump(out, open(PREV, "w"), separators=(",", ":"))
print("wrote data.json:", len(cards), "cards", flush=True)

# ---------- images for new cards ----------
IMG = os.path.join(ROOT, "img"); os.makedirs(IMG, exist_ok=True)
def fetch_img(c):
    t = c.get("t")
    if not t or Image is None: return None
    fn = os.path.join(IMG, f"{t}.webp")
    if os.path.exists(fn): return None
    try:
        with urllib.request.urlopen(f"https://tcgplayer-cdn.tcgplayer.com/product/{t}_in_1000x1000.jpg", timeout=30) as r: data = r.read()
        im = Image.open(io.BytesIO(data)).convert("RGB"); w, h = im.size
        if w > 420: im = im.resize((420, round(h * 420 / w)), Image.LANCZOS)
        im.save(fn, "WEBP", quality=68, method=6); return t
    except Exception as e:
        return f"ERR {t} {e}"
with concurrent.futures.ThreadPoolExecutor(8) as ex:
    res = [r for r in ex.map(fetch_img, cards) if r]
print("new images:", len([r for r in res if not str(r).startswith("ERR")]), "errors:", [r for r in res if str(r).startswith("ERR")][:5])
shutil.rmtree(RAW, ignore_errors=True)
