import csv, json, re, os, io, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
USER = os.environ["CELLARTRACKER_USER"]
PASSWORD = os.environ["CELLARTRACKER_PASSWORD"]

def fetch(table, extra=None):
    params = {"User": USER, "Password": PASSWORD, "Format": "csv", "Table": table}
    if extra:
        params.update(extra)
    url = "https://www.cellartracker.com/xlquery.asp?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (wine-analytics-bot)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    # CellarTracker declares ISO-8859-1
    return raw.decode("ISO-8859-1")

def fnum(v, default=0.0):
    try: return float(v) if v not in (None,'') else default
    except: return default
def inum(v, default=0):
    try: return int(float(v)) if v not in (None,'') else default
    except: return default

CRITICS = ["WA","WS","IWC","BH","AG","WE","JR","RH","JG","GV","JK","LD","CW","WFW","PR","SJ","WD","RR","JH","MFW","WWR","IWR","CHG","TT","TWF","DR","FP","JM","PG","WAL","JS"]
CRITIC_NAMES = {
    "WA":"Wine Advocate","WS":"Wine Spectator","IWC":"Vinous (IWC)","BH":"Burghound","AG":"Vinous (AG)",
    "WE":"Wine Enthusiast","JR":"Jancis Robinson","RH":"For the Love of Port","JG":"View From the Cellar",
    "GV":"WineLibraryTV","JK":"Vintage Tastings","LD":"NY Cork Report","CW":"Champagne Warrior",
    "WFW":"World of Fine Wine","PR":"PinotReport","SJ":"Sommelier Journal","WD":"Winedoctor","RR":"Robert Parker",
    "JH":"Halliday Wine Companion","MFW":"Mosel Fine Wines","WWR":"Washington Wine Report","IWR":"i-WineReview",
    "CHG":"ChampagneGuide.net","TT":"Terry Theise","TWF":"The WineFront","DR":"Decanter","FP":"Full Pull",
    "JM":"Inside Burgundy","PG":"PG","WAL":"WineAlign","JS":"James Suckling",
}

print("Fetching List table...")
list_csv = fetch("List", {"Location": "1"})
wines = list(csv.DictReader(io.StringIO(list_csv)))
print(f"  {len(wines)} rows")

print("Fetching Purchase table...")
purchase_csv = fetch("Purchase")
purchases = list(csv.DictReader(io.StringIO(purchase_csv)))
print(f"  {len(purchases)} rows")

print("Fetching Notes table...")
notes_csv = fetch("Notes")
if "No results returned" in notes_csv:
    raw_notes = []
else:
    raw_notes = list(csv.DictReader(io.StringIO(notes_csv)))
print(f"  {len(raw_notes)} rows")

def style_label(type_str):
    t = (type_str or "").lower()
    if "sparkling" in t: return "Sparkling"
    if "dessert" in t or "sweet" in t: return "Dessert / Sweet"
    if "fortified" in t: return "Fortified"
    if "ros" in t: return "Rosé"
    if "red" in t: return "Red"
    if "white" in t: return "White"
    return type_str or "Unknown"

clean_wines = []
for w in wines:
    qty = inum(w.get("Quantity"))
    if qty <= 0: continue
    price = fnum(w.get("Price")); val = fnum(w.get("Valuation"))
    critic_scores = []
    critic_scores_by_source = {}
    for c in CRITICS:
        sc = w.get(c,"")
        if sc:
            m = re.search(r"[\d.]+", sc)
            if m:
                v = float(m.group())
                critic_scores.append(v)
                critic_scores_by_source[c] = v
    ct = fnum(w.get("CT",""), None) if w.get("CT") else None
    my = fnum(w.get("MY",""), None) if w.get("MY") else None
    all_scores = critic_scores + ([ct] if ct else [])
    avg_score = round(sum(all_scores)/len(all_scores),1) if all_scores else None
    clean_wines.append({
        "iWine": w.get("iWine",""), "wine": w.get("Wine",""), "vintage": w.get("Vintage",""), "producer": w.get("Producer",""),
        "country": w.get("Country") or "Unknown", "region": w.get("Region") or "Unknown", "subregion": w.get("SubRegion") or "",
        "appellation": w.get("Appellation") or "", "color": w.get("Color") or "Unknown", "style": style_label(w.get("Type")),
        "varietal": w.get("MasterVarietal") or w.get("Varietal") or "Unknown", "location": w.get("Location") or "Unknown",
        "quantity": qty, "price_paid_bottle": round(price,2), "value_bottle": round(val,2),
        "total_paid": round(price*qty,2), "total_value": round(val*qty,2),
        "avg_critic_score": avg_score, "my_score": my, "critic_scores": critic_scores_by_source,
        "begin_consume": inum(w.get("BeginConsume",""), None), "end_consume": inum(w.get("EndConsume",""), None),
    })

def parse_date(s):
    if not s: return None
    parts = s.split("/")
    if len(parts) != 3: return None
    try:
        a,b,y = int(parts[0]), int(parts[1]), int(parts[2])
    except: return None
    try:
        if a > 12: return datetime(y, b, a)
        elif b > 12: return datetime(y, a, b)
        else: return datetime(y, b, a)  # ambiguous -> UK d/m/Y
    except: return None

clean_purchases = []
for p in purchases:
    d = parse_date(p.get("PurchaseDate"))
    if d is None: continue
    if (p.get("StoreName") or "").strip().lower() == "taste": continue  # CellarTracker tasting-log entries, not real purchases
    clean_purchases.append({
        "date": d.strftime("%Y-%m-%d"), "year": d.year, "month": d.strftime("%Y-%m"),
        "store": p.get("StoreName") or "Unknown", "wine": p.get("Wine") or "", "producer": p.get("Producer") or "",
        "country": p.get("Country") or "Unknown", "region": p.get("Region") or "Unknown",
        "quantity": inum(p.get("Quantity")), "price_bottle": fnum(p.get("Price")),
        "total": round(fnum(p.get("Price")) * inum(p.get("Quantity")), 2),
        "color": p.get("Color") or "Unknown", "varietal": p.get("MasterVarietal") or p.get("Varietal") or "Unknown",
        "iWine": p.get("iWine",""), "vintage": p.get("Vintage",""),
    })

# ---- Cellar consumption / turnover (uses CellarTracker's per-purchase-lot "Remaining" field) ----
consumption_by_year = defaultdict(lambda: {"purchased": 0, "remaining": 0})
total_purchased_ever = 0
total_remaining_ever = 0
for p in purchases:
    if (p.get("StoreName") or "").strip().lower() == "taste": continue
    qty = inum(p.get("Quantity"))
    if qty <= 0: continue
    rem = inum(p.get("Remaining"), qty)
    rem = max(0, min(rem, qty))
    total_purchased_ever += qty
    total_remaining_ever += rem
    d = parse_date(p.get("PurchaseDate"))
    if d:
        consumption_by_year[d.year]["purchased"] += qty
        consumption_by_year[d.year]["remaining"] += rem

total_consumed_ever = total_purchased_ever - total_remaining_ever
cum_purchased = 0; cum_remaining = 0
turnover_series = []
for y in sorted(consumption_by_year.keys()):
    cum_purchased += consumption_by_year[y]["purchased"]
    cum_remaining += consumption_by_year[y]["remaining"]
    turnover_series.append({"year": y, "cumulative_purchased": cum_purchased, "cumulative_remaining": cum_remaining})

consumption = {
    "total_purchased_ever": total_purchased_ever,
    "total_remaining_ever": total_remaining_ever,
    "total_consumed_ever": total_consumed_ever,
    "consumed_pct": round(total_consumed_ever/total_purchased_ever*100, 1) if total_purchased_ever else None,
    "turnover_series": turnover_series,
}

CURRENT_YEAR = datetime.now(timezone.utc).year
total_bottles = sum(w["quantity"] for w in clean_wines)
total_wines = len(clean_wines)
total_value = round(sum(w["total_value"] for w in clean_wines),2)
total_paid = round(sum(w["total_paid"] for w in clean_wines),2)
countries = sorted(set(w["country"] for w in clean_wines))
scored = [w["avg_critic_score"] for w in clean_wines if w["avg_critic_score"]]
avg_score = round(sum(scored)/len(scored),1) if scored else None

by_country = defaultdict(lambda: {"bottles":0,"value":0.0,"wines":0})
by_region = defaultdict(lambda: {"bottles":0,"value":0.0,"wines":0})
by_varietal = defaultdict(lambda: {"bottles":0,"value":0.0,"wines":0})
by_color = defaultdict(lambda: {"bottles":0,"value":0.0})
by_style = defaultdict(lambda: {"bottles":0,"value":0.0})
by_producer = defaultdict(lambda: {"bottles":0,"value":0.0,"wines":0})
by_location = defaultdict(lambda: {"bottles":0,"value":0.0})
drink_now, drink_soon, hold, past_peak, unknown_window = [],[],[],[],[]

for w in clean_wines:
    by_country[w["country"]]["bottles"] += w["quantity"]; by_country[w["country"]]["value"] += w["total_value"]; by_country[w["country"]]["wines"] += 1
    by_region[w["region"]]["bottles"] += w["quantity"]; by_region[w["region"]]["value"] += w["total_value"]; by_region[w["region"]]["wines"] += 1
    by_varietal[w["varietal"]]["bottles"] += w["quantity"]; by_varietal[w["varietal"]]["value"] += w["total_value"]; by_varietal[w["varietal"]]["wines"] += 1
    by_color[w["color"]]["bottles"] += w["quantity"]; by_color[w["color"]]["value"] += w["total_value"]
    by_style[w["style"]]["bottles"] += w["quantity"]; by_style[w["style"]]["value"] += w["total_value"]
    by_producer[w["producer"]]["bottles"] += w["quantity"]; by_producer[w["producer"]]["value"] += w["total_value"]; by_producer[w["producer"]]["wines"] += 1
    by_location[w["location"]]["bottles"] += w["quantity"]; by_location[w["location"]]["value"] += w["total_value"]
    b, e = w["begin_consume"], w["end_consume"]
    entry = {"iWine": w["iWine"], "wine": w["wine"], "vintage": w["vintage"], "producer": w["producer"], "quantity": w["quantity"], "begin": b, "end": e}
    if b is None and e is None: unknown_window.append(entry)
    elif e is not None and e < CURRENT_YEAR: past_peak.append(entry)
    elif b is not None and b <= CURRENT_YEAR and (e is None or e >= CURRENT_YEAR): drink_now.append(entry)
    elif b is not None and b <= CURRENT_YEAR + 2: drink_soon.append(entry)
    else: hold.append(entry)

spend_by_month = defaultdict(float)
spend_by_store = defaultdict(lambda: {"total":0.0,"bottles":0,"orders":0})
for p in clean_purchases:
    spend_by_month[p["month"]] += p["total"]
    spend_by_store[p["store"]]["total"] += p["total"]; spend_by_store[p["store"]]["bottles"] += p["quantity"]; spend_by_store[p["store"]]["orders"] += 1

def top(d, n=15, key="value"):
    return sorted([{"name":k, **v} for k,v in d.items()], key=lambda x:-x[key])[:n]

# ---- Appreciation per wine ----
for w in clean_wines:
    if w["price_paid_bottle"] and w["price_paid_bottle"] > 0:
        w["appreciation_pct"] = round((w["value_bottle"] - w["price_paid_bottle"]) / w["price_paid_bottle"] * 100, 1)
    else:
        w["appreciation_pct"] = None

priced_wines = [w for w in clean_wines if w["appreciation_pct"] is not None]
top_gainers = sorted(priced_wines, key=lambda x:-x["appreciation_pct"])[:15]
top_losers = sorted(priced_wines, key=lambda x:x["appreciation_pct"])[:15]

# ---- Grape characteristics (hand-curated heuristic; used for decanting-time & pairing guidance) ----
# body/tannin are descriptive only; decant hours are a starting-point estimate, not a critic's recommendation.
GRAPE_PROFILES = {
    "Cabernet Sauvignon": {"body":"Full","tannin":"High","decant_young_hrs":2.0,"decant_mature_hrs":0.75,
        "pairings":["grilled or roast red meat","hard aged cheese (cheddar, gouda)","lamb"]},
    "Syrah": {"body":"Full","tannin":"High","decant_young_hrs":1.5,"decant_mature_hrs":0.5,
        "pairings":["peppered steak","game","barbecue"]},
    "Nebbiolo": {"body":"Full","tannin":"Very high","decant_young_hrs":3.0,"decant_mature_hrs":1.0,
        "pairings":["braised beef (brasato)","truffle dishes","aged hard cheese"]},
    "Tempranillo": {"body":"Medium-full","tannin":"Medium-high","decant_young_hrs":1.5,"decant_mature_hrs":0.5,
        "pairings":["roast lamb","chorizo & charcuterie","manchego cheese"]},
    "Sangiovese": {"body":"Medium","tannin":"Medium-high","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["tomato-based pasta","pizza","grilled poultry"]},
    "Grenache": {"body":"Medium-full","tannin":"Medium","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["roast lamb","hearty stew","spiced/North African dishes"]},
    "Mourvèdre": {"body":"Full","tannin":"High","decant_young_hrs":1.5,"decant_mature_hrs":0.5,
        "pairings":["game","roast duck","strong hard cheese"]},
    "Malbec": {"body":"Full","tannin":"Medium-high","decant_young_hrs":1.5,"decant_mature_hrs":0.5,
        "pairings":["grilled steak (asado)","empanadas","chorizo"]},
    "Montepulciano": {"body":"Medium-full","tannin":"Medium","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["braised meats","tomato ragù","hard cheese"]},
    "Pinot Noir": {"body":"Light-medium","tannin":"Low-medium","decant_young_hrs":0.5,"decant_mature_hrs":0.25,
        "pairings":["duck","salmon","mushroom dishes"]},
    "Gamay": {"body":"Light","tannin":"Low","decant_young_hrs":0.25,"decant_mature_hrs":0,
        "pairings":["charcuterie","roast chicken","light bistro fare"]},
    "Nerello Mascalese": {"body":"Medium","tannin":"Medium","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["grilled vegetables","charcuterie","tomato-based dishes"]},
    "Corvina": {"body":"Medium-full","tannin":"Medium","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["braised meat","risotto","aged cheese"]},
    "Mencía": {"body":"Medium","tannin":"Medium","decant_young_hrs":0.75,"decant_mature_hrs":0.25,
        "pairings":["roast pork","grilled vegetables","mild cheese"]},
    "Riesling": {"body":"Light","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["spicy Asian food","pork","soft cheese"]},
    "Albariño": {"body":"Light-medium","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["shellfish","grilled fish","light tapas"]},
    "Furmint": {"body":"Medium","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["foie gras","blue cheese","fruit-based desserts"]},
    "Muscat": {"body":"Light","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["fruit desserts","soft cheese","spiced cake"]},
    "Sémillon-Sauvignon Blanc Blend": {"body":"Medium","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["goat cheese","seafood","salads"]},
}
STYLE_DEFAULTS = {
    "Red": {"body":"Medium","tannin":"Medium","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["red meat","hard cheese","roasted vegetables"]},
    "White": {"body":"Light-medium","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["seafood","poultry","fresh cheese"]},
    "Rosé": {"body":"Light","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["salads","charcuterie","light seafood"]},
    "Sparkling": {"body":"Light","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["oysters","fried food","celebrations"]},
    "Dessert / Sweet": {"body":"Rich","tannin":"None","decant_young_hrs":0,"decant_mature_hrs":0,
        "pairings":["blue cheese","fruit tart","foie gras"]},
    "Fortified": {"body":"Rich","tannin":"Low","decant_young_hrs":1.0,"decant_mature_hrs":0.5,
        "pairings":["dark chocolate","nuts","blue cheese"]},
    "Unknown": {"body":"Medium","tannin":"Medium","decant_young_hrs":0.5,"decant_mature_hrs":0.25,
        "pairings":["versatile with most food"]},
}

def get_grape_profile(w):
    return GRAPE_PROFILES.get(w["varietal"]) or STYLE_DEFAULTS.get(w["style"]) or STYLE_DEFAULTS["Unknown"]

def estimate_decant(w, profile):
    years_old = CURRENT_YEAR - inum(w["vintage"], CURRENT_YEAR)
    base = profile["decant_young_hrs"] if years_old < 8 else profile["decant_mature_hrs"]
    if years_old >= 20:
        base = min(base, 0.5)  # fragile older wines: keep it gentle regardless of grape
    if base <= 0:
        return {"hours": 0, "label": "No decanting needed — drink straight from the bottle"}
    if base < 1:
        return {"hours": base, "label": f"~{int(round(base*60))} min — a short splash-decant to open it up"}
    return {"hours": base, "label": f"~{base:.2g}–{base+0.5:.2g} hrs (longer if young & tightly wound)"}

for w in clean_wines:
    profile = get_grape_profile(w)
    w["body"] = profile["body"]; w["tannin"] = profile["tannin"]
    w["pairings"] = profile["pairings"]
    w["decant"] = estimate_decant(w, profile)

# ---- Wikipedia grape-variety context (free, no key; short attributed excerpt, not per-bottle) ----
WIKI_SKIP = {"Red Blend","Red Bordeaux Blend","White Blend","Port Blend","Rosé Blend","Proprietary Blend","Unknown",""}

def fetch_wiki_summary(title):
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
        req = urllib.request.Request(url, headers={"User-Agent": "wine-analytics-dashboard/1.0 (personal cellar dashboard; contact: n/a)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("type") == "disambiguation":
            return None
        extract = (body.get("extract") or "").strip()
        if not extract:
            return None
        if len(extract) > 480:
            extract = extract[:480].rsplit(" ", 1)[0] + "…"
        return {
            "summary": extract,
            "url": (body.get("content_urls") or {}).get("desktop", {}).get("page", ""),
            "title": body.get("title", title),
        }
    except Exception:
        return None

distinct_varietals = sorted(set(w["varietal"] for w in clean_wines if w["varietal"] and w["varietal"] not in WIKI_SKIP))
print(f"Fetching Wikipedia grape summaries for {len(distinct_varietals)} varietals...")
varietal_wiki = {}
for v in distinct_varietals:
    result = fetch_wiki_summary(v)
    if result is None:
        result = fetch_wiki_summary(v + " (grape)")
    if result:
        varietal_wiki[v] = result
print(f"  Got {len(varietal_wiki)} summaries")

for w in clean_wines:
    w["wiki"] = varietal_wiki.get(w["varietal"])

# ---- Wikidata winery profiles (free, no key) ----
# Matches producer names against Wikidata via wbsearchentities, keeping only candidates whose short
# description reads like an actual winery/producer, then pulls founding year (P571), coordinates
# (P625), and an English Wikipedia link for that entity. Coverage is partial by nature — small or
# obscure producers often have no Wikidata entry at all — so this is best-effort enrichment, not a
# guaranteed field.
WIKIDATA_HEADERS = {"User-Agent": "wine-analytics-dashboard/1.0 (https://ap2073.github.io/wine-analytics/; personal cellar dashboard, non-commercial)"}
WINERY_DESC_HINTS = ["winery", "vineyard", "wine producer", "wine brand", "wine company",
                     "wine estate", "viticulture", "bodega", "domaine", "château", "chateau",
                     "wine cooperative", "wine region", "vintner", "wine label"]

def wikidata_get(url, retries=4):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=WIKIDATA_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                wait = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                time.sleep(min(wait, 20))
                continue
            raise
    raise last_err

def fetch_wikidata_producer(name):
    try:
        search_url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&search="
                       + urllib.parse.quote(name) + "&language=en&format=json&type=item&limit=5")
        results = wikidata_get(search_url).get("search", [])
        candidate = None
        for r in results:
            desc = (r.get("description") or "").lower()
            if any(h in desc for h in WINERY_DESC_HINTS):
                candidate = r
                break
        if not candidate:
            return None
        qid = candidate["id"]
        entity_url = ("https://www.wikidata.org/w/api.php?action=wbgetentities&ids=" + qid
                      + "&props=descriptions|claims|sitelinks&languages=en&format=json")
        entity = wikidata_get(entity_url).get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        founded = None
        if "P571" in claims:
            try:
                t = claims["P571"][0]["mainsnak"]["datavalue"]["value"]["time"]
                founded = int(t[1:5]) if t else None
            except Exception:
                founded = None
        lat = lon = None
        if "P625" in claims:
            try:
                coord = claims["P625"][0]["mainsnak"]["datavalue"]["value"]
                lat, lon = coord["latitude"], coord["longitude"]
            except Exception:
                lat = lon = None
        wiki_url = None
        enwiki = entity.get("sitelinks", {}).get("enwiki")
        if enwiki and enwiki.get("title"):
            wiki_url = "https://en.wikipedia.org/wiki/" + enwiki["title"].replace(" ", "_")
        return {
            "description": (candidate.get("description") or "").capitalize(),
            "founded": founded, "lat": lat, "lon": lon, "wikipedia_url": wiki_url,
        }
    except Exception as e:
        WIKIDATA_DEBUG.append(f"{name}: {type(e).__name__}: {e}")
        return None

distinct_producers = sorted(set(w["producer"] for w in clean_wines if w["producer"]))
print(f"Fetching Wikidata winery profiles for {len(distinct_producers)} producers...")
producer_wikidata = {}
WIKIDATA_DEBUG = []
WIKIDATA_NOMATCH = []
for p in distinct_producers:
    result = fetch_wikidata_producer(p)
    if result:
        producer_wikidata[p] = result
    elif not any(p in d for d in WIKIDATA_DEBUG):
        WIKIDATA_NOMATCH.append(p)
    time.sleep(0.3)
print(f"  Got {len(producer_wikidata)} winery profiles")
if WIKIDATA_DEBUG:
    print(f"  {len(WIKIDATA_DEBUG)} errors, first 5: {WIKIDATA_DEBUG[:5]}")
if WIKIDATA_NOMATCH:
    print(f"  {len(WIKIDATA_NOMATCH)} no-description-match, first 10: {WIKIDATA_NOMATCH[:10]}")

# ---- Price distribution ----
PRICE_BUCKETS = [(0,20),(20,40),(40,60),(60,100),(100,150),(150,250),(250,float("inf"))]
def bucket_label(lo,hi):
    return f"£{lo}+" if hi==float("inf") else f"£{lo}-{hi}"
price_dist = []
for lo,hi in PRICE_BUCKETS:
    bwines = [w for w in clean_wines if lo <= w["price_paid_bottle"] < hi]
    price_dist.append({"label": bucket_label(lo,hi), "wines": len(bwines), "bottles": sum(w["quantity"] for w in bwines)})

# ---- Producer deep-dive ----
producer_wines = defaultdict(list)
for w in clean_wines:
    producer_wines[w["producer"]].append(w)
producer_detail = []
for prod, ws in producer_wines.items():
    bottles = sum(w["quantity"] for w in ws)
    paid = sum(w["total_paid"] for w in ws)
    value = sum(w["total_value"] for w in ws)
    scored_w = [w["avg_critic_score"] for w in ws if w["avg_critic_score"]]
    producer_detail.append({
        "name": prod, "wines": len(ws), "bottles": bottles, "paid": round(paid,2), "value": round(value,2),
        "appreciation_pct": round((value-paid)/paid*100,1) if paid > 0 else None,
        "avg_score": round(sum(scored_w)/len(scored_w),1) if scored_w else None,
        "countries": sorted(set(w["country"] for w in ws)), "regions": sorted(set(w["region"] for w in ws)),
        "wikidata": producer_wikidata.get(prod),
    })
producer_detail.sort(key=lambda x:-x["value"])

# ---- Stats records ----
earliest_purchase_by_iwine = {}
for p in purchases:
    iw = p.get("iWine")
    d = parse_date(p.get("PurchaseDate",""))
    if iw and d:
        if iw not in earliest_purchase_by_iwine or d < earliest_purchase_by_iwine[iw]:
            earliest_purchase_by_iwine[iw] = d

today = datetime.now(timezone.utc).replace(tzinfo=None)
held = []
for w in clean_wines:
    d = earliest_purchase_by_iwine.get(w["iWine"])
    if d:
        held.append({"iWine": w["iWine"], "wine": w["wine"], "vintage": w["vintage"], "producer": w["producer"],
                      "since": d.strftime("%Y-%m-%d"), "days_held": (today-d).days})
held.sort(key=lambda x:-x["days_held"])

oldest_bottle = min(clean_wines, key=lambda w: inum(w["vintage"], 9999)) if clean_wines else None
most_expensive = max(clean_wines, key=lambda w: w["value_bottle"]) if clean_wines else None
biggest_producer_bottles = max(producer_detail, key=lambda p: p["bottles"]) if producer_detail else None
biggest_producer_value = producer_detail[0] if producer_detail else None
avg_cellar_age = round(sum((CURRENT_YEAR - inum(w["vintage"], CURRENT_YEAR)) * w["quantity"] for w in clean_wines) / total_bottles, 1) if total_bottles else None
largest_purchase = max(clean_purchases, key=lambda p: p["total"]) if clean_purchases else None
purchase_dates = [p["date"] for p in clean_purchases]
most_visited_store = max(spend_by_store.items(), key=lambda kv: kv[1]["orders"])[0] if spend_by_store else None

stats_records = {
    "oldest_bottle": oldest_bottle, "most_expensive_bottle": most_expensive,
    "biggest_producer_by_bottles": biggest_producer_bottles, "biggest_producer_by_value": biggest_producer_value,
    "avg_bottle_price_paid": round(total_paid/total_bottles,2) if total_bottles else None,
    "avg_bottle_value_now": round(total_value/total_bottles,2) if total_bottles else None,
    "avg_cellar_age_years": avg_cellar_age, "largest_single_purchase": largest_purchase,
    "first_purchase_date": min(purchase_dates) if purchase_dates else None,
    "most_recent_purchase_date": max(purchase_dates) if purchase_dates else None,
    "most_visited_store": most_visited_store, "total_orders": len(clean_purchases),
    "longest_held": held[:10],
    "total_appreciation_pct": round((total_value-total_paid)/total_paid*100,1) if total_paid else None,
}

# ---- Country geo coordinates (approximate, for map) ----
COUNTRY_COORDS = {
    "France": [46.6, 2.2], "Italy": [42.8, 12.6], "Spain": [40.3, -3.7],
    "Portugal": [39.6, -8.0], "USA": [38.0, -119.4], "Australia": [-33.9, 143.9],
    "South Africa": [-33.9, 20.0], "Argentina": [-34.6, -68.5], "Chile": [-33.4, -70.6],
    "New Zealand": [-41.5, 173.5], "Germany": [50.1, 8.0], "Austria": [47.5, 14.5],
    "Hungary": [47.2, 19.5], "Greece": [39.0, 22.0], "Georgia": [42.3, 43.4],
    "Israel": [31.5, 34.8], "Lebanon": [33.9, 35.9], "Canada": [49.3, -119.5],
    "England": [51.0, -1.0], "United Kingdom": [51.0, -1.0],
}
map_countries = []
for c in top(by_country, 50):
    coords = COUNTRY_COORDS.get(c["name"])
    if coords:
        map_countries.append({**c, "lat": coords[0], "lon": coords[1]})

# ---- Diversification (Herfindahl-based) ----
def hhi_score(dist_dict, total):
    if not total: return 0.0
    hhi = sum((v["bottles"]/total)**2 for v in dist_dict.values())
    return round((1-hhi)*100, 1)

def diversification_label(score):
    if score >= 80: return "Highly diversified"
    if score >= 60: return "Well diversified"
    if score >= 40: return "Moderately concentrated"
    return "Highly concentrated"

varietal_div_score = hhi_score(by_varietal, total_bottles)
country_div_score = hhi_score(by_country, total_bottles)

# ---- Palate gaps ----
NEW_WORLD = {"USA","Australia","New Zealand","South Africa","Chile","Argentina","Canada"}
def has_word(s, *words):
    s = (s or "").lower()
    return any(w.lower() in s for w in words)

PALATE_CATEGORIES = [
    ("Sparkling / Champagne", lambda w: has_word(w["varietal"],"Champagne","Sparkling") or has_word(w["region"],"Champagne") or has_word(w["color"],"Sparkling")),
    ("Rosé", lambda w: has_word(w["color"],"Rosé","Rose","Pink")),
    ("Fortified / Dessert", lambda w: has_word(w["color"],"Dessert","Sweet") or has_word(w["varietal"],"Port","Sherry","Madeira")),
    ("German/Austrian Riesling", lambda w: w["country"] in ("Germany","Austria") and has_word(w["varietal"],"Riesling")),
    ("White Burgundy (Chardonnay)", lambda w: has_word(w["region"],"Burgundy") and has_word(w["varietal"],"Chardonnay")),
    ("Loire Valley", lambda w: has_word(w["region"],"Loire")),
    ("Barolo / Barbaresco", lambda w: has_word(w["appellation"],"Barolo","Barbaresco")),
    ("Rioja", lambda w: has_word(w["region"],"Rioja") or has_word(w["appellation"],"Rioja")),
    ("Tuscan Sangiovese", lambda w: has_word(w["region"],"Tuscany") and has_word(w["varietal"],"Sangiovese")),
    ("New World Pinot Noir", lambda w: w["country"] in NEW_WORLD and has_word(w["varietal"],"Pinot Noir")),
    ("English / UK Wine", lambda w: w["country"] in ("England","United Kingdom")),
    ("Orange Wine", lambda w: has_word(w["varietal"],"Orange") or has_word(w["color"],"Orange")),
]
palate_gaps = []
for name, matcher in PALATE_CATEGORIES:
    matched = [w for w in clean_wines if matcher(w)]
    palate_gaps.append({"name": name, "bottles": sum(w["quantity"] for w in matched), "wines": len(matched), "covered": len(matched) > 0})

diversification = {
    "varietal_score": varietal_div_score, "country_score": country_div_score,
    "varietal_label": diversification_label(varietal_div_score), "country_label": diversification_label(country_div_score),
    "palate_gaps": palate_gaps,
    "gaps_count": sum(1 for g in palate_gaps if not g["covered"]),
    "covered_count": sum(1 for g in palate_gaps if g["covered"]),
}

# ---- Cellar maturity pressure ----
def pressure_tier(years_left):
    if years_left is None: return "unknown"
    if years_left <= 1: return "critical"
    if years_left <= 3: return "high"
    if years_left <= 6: return "moderate"
    return "low"

pressure_buckets = {"critical":{"bottles":0,"wines":0},"high":{"bottles":0,"wines":0},
                     "moderate":{"bottles":0,"wines":0},"low":{"bottles":0,"wines":0},"unknown":{"bottles":0,"wines":0}}
urgent_list = []
for w in clean_wines:
    yl = (w["end_consume"] - CURRENT_YEAR) if w["end_consume"] is not None else None
    tier = pressure_tier(yl)
    pressure_buckets[tier]["bottles"] += w["quantity"]
    pressure_buckets[tier]["wines"] += 1
    if yl is not None:
        urgent_list.append({"iWine": w["iWine"], "wine": w["wine"], "vintage": w["vintage"], "quantity": w["quantity"],
                             "end_consume": w["end_consume"], "years_left": yl, "tier": tier})
urgent_list.sort(key=lambda x: x["years_left"])

at_risk_bottles = pressure_buckets["critical"]["bottles"] + pressure_buckets["high"]["bottles"]
pressure_score = round(at_risk_bottles/total_bottles*100, 1) if total_bottles else 0.0

def pressure_label(score):
    if score >= 50: return "High pressure — significant drinking needed soon"
    if score >= 25: return "Moderate pressure — plan ahead for closing windows"
    if score >= 10: return "Low pressure — mostly comfortable"
    return "Minimal pressure — cellar has plenty of runway"

maturity_pressure = {
    "score": pressure_score, "label": pressure_label(pressure_score),
    "buckets": pressure_buckets, "urgent_list": urgent_list[:15],
}

# ---- Vintage distribution ----
vintage_bottles = defaultdict(int)
vintage_expanded = []
for w in clean_wines:
    vy = inum(w["vintage"], None)
    if vy and 1900 < vy <= CURRENT_YEAR + 1:
        vintage_bottles[vy] += w["quantity"]
        vintage_expanded.extend([vy] * w["quantity"])
vintage_expanded.sort()
median_vintage = vintage_expanded[len(vintage_expanded)//2] if vintage_expanded else None
vintage_distribution = {
    "buckets": sorted([{"vintage": y, "bottles": b} for y, b in vintage_bottles.items()], key=lambda x: x["vintage"]),
    "median_vintage": median_vintage,
}

# ---- Tasting history & taste profile (from CellarTracker Notes) ----
def parse_note_date(s):
    if not s: return None
    parts = s.split("/")
    if len(parts) != 3: return None
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(y, m, d)
    except: return None

tasting_history = []
for n in raw_notes:
    if not n.get("Name") or n["Name"].lower() != USER.lower():
        continue
    d = parse_note_date(n.get("TastingDate", ""))
    rating = fnum(n.get("Rating", ""), None) if n.get("Rating") else None
    if d is None or rating is None:
        continue
    cscore = fnum(n.get("CScore", ""), None) if n.get("CScore") else None
    tasting_history.append({
        "iWine": n.get("iWine", ""), "wine": n.get("Wine", ""), "vintage": n.get("Vintage", ""),
        "producer": n.get("Producer", ""), "country": n.get("Country") or "Unknown",
        "region": n.get("Region") or "Unknown", "varietal": n.get("MasterVarietal") or "Unknown",
        "color": n.get("Color") or "Unknown", "date": d.strftime("%Y-%m-%d"), "month": d.strftime("%Y-%m"),
        "rating": rating, "community_score": cscore,
        "delta": round(rating - cscore, 1) if cscore else None,
        "notes_text": (n.get("TastingNotes", "") or "").strip(),
    })
tasting_history.sort(key=lambda x: x["date"], reverse=True)

total_tastings = len(tasting_history)
all_ratings = [t["rating"] for t in tasting_history]
avg_personal_rating = round(sum(all_ratings)/len(all_ratings), 1) if all_ratings else None
rating_mean = avg_personal_rating or 0
rating_var = (sum((r-rating_mean)**2 for r in all_ratings)/len(all_ratings)) if all_ratings else 0
rating_std = rating_var ** 0.5

deltas = [t["delta"] for t in tasting_history if t["delta"] is not None]
avg_delta = round(sum(deltas)/len(deltas), 1) if deltas else None

def calibration_label(delta):
    if delta is None: return "Not enough consensus data yet"
    if delta >= 3: return "You rate noticeably higher than the CellarTracker community — a generous taster"
    if delta <= -3: return "You rate noticeably lower than community consensus — a tough grader"
    return "Your ratings track closely with community consensus"

tastings_by_month = defaultdict(int)
for t in tasting_history:
    tastings_by_month[t["month"]] += 1

def taste_profile_dim(dim_key, cellar_dict):
    tasting_agg = defaultdict(list)
    for t in tasting_history:
        val = t[dim_key] or "Unknown"
        tasting_agg[val].append(t["rating"])
    cellar_pcts = {k: (v["bottles"]/total_bottles*100 if total_bottles else 0) for k, v in cellar_dict.items()}
    pct_values = sorted(cellar_pcts.values())
    median_pct = pct_values[len(pct_values)//2] if pct_values else 0
    entries = []
    for val, ratings in tasting_agg.items():
        if len(ratings) < 2:
            continue
        avg_r = sum(ratings)/len(ratings)
        z = (avg_r - rating_mean) / rating_std if rating_std else 0
        cellar_pct = round(cellar_pcts.get(val, 0), 1)
        cellar_bottles = cellar_dict.get(val, {}).get("bottles", 0)
        well_stocked = cellar_pct >= median_pct
        liked = z >= 0.5
        disliked = z <= -0.5
        if liked and not well_stocked: verdict = "Underweight"
        elif disliked and well_stocked: verdict = "Overweight"
        elif liked and well_stocked: verdict = "Well matched"
        elif disliked and not well_stocked: verdict = "Rightly avoided"
        else: verdict = "Neutral"
        entries.append({
            "name": val, "avg_rating": round(avg_r, 1), "tastings": len(ratings),
            "cellar_bottles": cellar_bottles, "cellar_pct": cellar_pct, "verdict": verdict,
        })
    entries.sort(key=lambda x: -x["avg_rating"])
    return entries

taste_profile = {
    "by_varietal": taste_profile_dim("varietal", by_varietal),
    "by_country": taste_profile_dim("country", by_country),
    "by_region": taste_profile_dim("region", by_region),
    "by_color": taste_profile_dim("color", by_color),
    "by_producer": taste_profile_dim("producer", by_producer),
}


# ==================== CRITIC MATCH ====================
# Which named critics' scores best track your own scores, computed purely from wines where you've
# logged your own CellarTracker score (MY) and that critic also has a score on file — no external
# catalog/pricing data involved.
CRITIC_MATCH_MIN_WINES = 3

def pearson(pairs):
    n = len(pairs)
    mean_m = sum(m for m, c in pairs) / n
    mean_c = sum(c for m, c in pairs) / n
    var_m = sum((m - mean_m) ** 2 for m, c in pairs)
    var_c = sum((c - mean_c) ** 2 for m, c in pairs)
    if var_m <= 0 or var_c <= 0:
        return None
    cov = sum((m - mean_m) * (c - mean_c) for m, c in pairs)
    return cov / ((var_m * var_c) ** 0.5)

def match_label(corr):
    if corr is None: return "Not enough score variation to correlate"
    if corr >= 0.6: return "Strong match — tends to track your scores closely"
    if corr >= 0.3: return "Some alignment with your scores"
    if corr > -0.3: return "Little correlation with your scores"
    return "Tends to diverge from your scores"

def bias_label(avg_diff):
    if avg_diff >= 2: return "Scores you higher, on average"
    if avg_diff <= -2: return "Scores you lower, on average"
    return "Close to your own scoring, on average"

critic_match = []
for code in CRITICS:
    pairs = [(w["my_score"], w["critic_scores"][code]) for w in clean_wines
             if w["my_score"] is not None and code in w["critic_scores"]]
    n = len(pairs)
    if n < CRITIC_MATCH_MIN_WINES:
        continue
    avg_diff = round(sum(c - m for m, c in pairs) / n, 2)
    avg_abs_diff = round(sum(abs(c - m) for m, c in pairs) / n, 2)
    corr = pearson(pairs)
    critic_match.append({
        "code": code, "name": CRITIC_NAMES.get(code, code), "n": n,
        "avg_your_score": round(sum(m for m, c in pairs) / n, 1),
        "avg_critic_score": round(sum(c for m, c in pairs) / n, 1),
        "avg_diff": avg_diff, "avg_abs_diff": avg_abs_diff,
        "correlation": round(corr, 2) if corr is not None else None,
        "match_label": match_label(corr), "bias_label": bias_label(avg_diff),
    })
critic_match.sort(key=lambda c: (-(c["correlation"] if c["correlation"] is not None else -2), c["avg_abs_diff"]))
print(f"Critic match: {len(critic_match)} critics with >= {CRITIC_MATCH_MIN_WINES} overlapping scored wines")

tasting_data = {
    "total_tastings": total_tastings, "avg_personal_rating": avg_personal_rating,
    "rating_stdev": round(rating_std, 1), "avg_delta_vs_consensus": avg_delta,
    "calibration_label": calibration_label(avg_delta),
    "tastings_by_month": sorted([{"month": k, "count": v} for k, v in tastings_by_month.items()], key=lambda x: x["month"]),
    "recent": tasting_history[:40],
    "all": tasting_history,
    "taste_profile": taste_profile,
}

data = {
    "generated_at": datetime.now(timezone.utc).isoformat(), "current_year": CURRENT_YEAR,
    "summary": {"total_bottles": total_bottles, "total_wines": total_wines, "total_value": total_value,
                "total_paid": total_paid, "countries": len(countries), "avg_critic_score": avg_score},
    "by_country": top(by_country, 20), "by_varietal": top(by_varietal, 20), "by_region": top(by_region, 20),
    "by_color": [{"name":k, **v} for k,v in by_color.items()],
    "by_style": [{"name":k, **v} for k,v in by_style.items()],
    "top_producers_value": top(by_producer, 15), "by_location": [{"name":k, **v} for k,v in by_location.items()],
    "drinking_window": {
        "drink_now": sorted(drink_now, key=lambda x:-x["quantity"]),
        "drink_soon": sorted(drink_soon, key=lambda x: (x["begin"] or 9999)),
        "hold": sorted(hold, key=lambda x: (x["begin"] or 9999)),
        "past_peak": past_peak, "unknown_window": unknown_window,
    },
    "top_rated": sorted([w for w in clean_wines if w["avg_critic_score"]], key=lambda x:-x["avg_critic_score"])[:20],
    "top_value_bottles": sorted(clean_wines, key=lambda x:-x["value_bottle"])[:15],
    "spend_by_month": sorted([{"month":k,"total":round(v,2)} for k,v in spend_by_month.items()], key=lambda x:x["month"]),
    "spend_by_store": sorted([{"name":k, **v} for k,v in spend_by_store.items()], key=lambda x:-x["total"]),
    "total_purchases": len(clean_purchases), "wines": clean_wines,
    "top_gainers": top_gainers, "top_losers": top_losers, "price_distribution": price_dist,
    "producer_detail": producer_detail, "stats_records": stats_records, "map_countries": map_countries,
    "purchases": clean_purchases,
    "diversification": diversification, "maturity_pressure": maturity_pressure,
    "vintage_distribution": vintage_distribution, "tasting": tasting_data,
    "consumption": consumption, "critic_names": CRITIC_NAMES, "critic_match": critic_match,
}

with open(os.path.join(HERE, "cellar_data.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)

with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
    template = f.read()

html = template.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))
with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print(f"Done. Wines: {total_wines}, Bottles: {total_bottles}, Value: {total_value}, Paid: {total_paid}")
