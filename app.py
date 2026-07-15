"""OpenPlantDB showcase site + JSON API.

Serves the CC0 OpenPlantDB dataset (github.com/cwfrazier1/openplantdb) as a
browsable website and a read-only JSON API. Data is loaded from the git clone
at /opt/openplantdb and refreshed on startup (a nightly cron pulls + restarts).
"""
import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

DATA_DIR = Path("/opt/openplantdb/data")
PLANTS_PATH = DATA_DIR / "plants.json"
ZONES_PATH = DATA_DIR / "zones.json"

app = FastAPI(title="OpenPlantDB API", version="1.0", docs_url="/api/docs", redoc_url=None)

# --- Social platform (accounts, plantings, feed, requests) -------------------
try:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )
    import auth as _auth
    import social as _social
    app.include_router(_auth.router)
    app.include_router(_social.router)

    from fastapi.responses import StreamingResponse
    import storage as _storage

    @app.get("/media/{key:path}")
    def _media(key: str):
        try:
            body, ctype, length = _storage.get_stream(key)
        except Exception:
            raise HTTPException(404, "Not found")
        headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        return StreamingResponse(body, media_type=ctype, headers=headers)

    import webui as _webui
    _SITE_URL = os.environ.get("OPDB_SITE_URL", "https://whatcaniplantnow.com")

    @app.get("/app.js")
    def _app_js():
        return Response(_webui.app_js(_SITE_URL), media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})

    @app.get("/social.css")
    def _social_css():
        return Response(_webui.SOCIAL_CSS, media_type="text/css",
                        headers={"Cache-Control": "public, max-age=300"})

    @app.get("/community", response_class=HTMLResponse)
    def _community():
        return HTMLResponse(_webui.COMMUNITY_HTML)

    SOCIAL_ENABLED = True
except Exception as _e:  # keep the base site alive even if social deps are missing
    import logging as _logging
    _logging.getLogger("opdb").warning("social platform disabled: %s", _e)
    SOCIAL_ENABLED = False

STATE = {"plants": [], "by_slug": {}, "zones": [], "zones_about": "", "loaded": None}


def load_data():
    plants = json.loads(PLANTS_PATH.read_text())
    zdoc = json.loads(ZONES_PATH.read_text())
    STATE["plants"] = plants
    STATE["by_slug"] = {p["slug"]: p for p in plants}
    STATE["zones"] = zdoc.get("zones", [])
    STATE["zones_about"] = zdoc.get("_about", "")
    STATE["loaded"] = dt.datetime.utcnow().isoformat() + "Z"


load_data()

MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _parse_frost(s, year):
    if not s:
        return None
    mon, day = s.split()
    return dt.date(year, MONTHS[mon], int(day))


def _zone_num(z):
    m = re.match(r"(\d+)", str(z))
    return int(m.group(1)) if m else None


def _zone_record(zone_str):
    zn = _zone_num(zone_str)
    return next((x for x in STATE["zones"] if _zone_num(x["zone"]) == zn), None)


def _window_dates(plant, zrec):
    """Return (start_date, end_date) for a plant's sow window in a zone, or None."""
    p = plant.get("planting") or {}
    anchor = p.get("anchor")
    wfa = p.get("weeks_from_anchor") or {}
    wmin, wmax = wfa.get("min"), wfa.get("max")
    year = dt.date.today().year
    spring = _parse_frost(zrec.get("last_spring_frost"), year)
    fall = _parse_frost(zrec.get("first_fall_frost"), year)
    if anchor in ("last_frost", "soil_workable", "spring"):
        base = spring
    elif anchor in ("first_frost", "fall"):
        base = fall
    else:
        base = spring or fall
    if base is None or wmin is None:
        return None
    start = base + dt.timedelta(weeks=wmin)
    end = base + dt.timedelta(weeks=wmax if wmax is not None else wmin)
    return start, end


def compute_planting(plant, zone_str):
    """Return an approximate sow/plant window for a plant in a given USDA zone."""
    z = _zone_record(zone_str)
    if z is None:
        return None
    p = plant.get("planting") or {}
    wd = _window_dates(plant, z)
    if wd is None:
        return {"anchor": p.get("anchor"), "zone": zone_str, "window": None,
                "note": p.get("note"), "reason": "frost-free zone or no anchor offset"}
    fmt = "%b %-d"
    return {
        "anchor": p.get("anchor"),
        "zone": zone_str,
        "window": {"start": wd[0].strftime(fmt), "end": wd[1].strftime(fmt)},
        "note": p.get("note"),
    }


# ---- "what can I plant now" support -------------------------------------
TREE_SUBCATS = {"pome fruit", "stone fruit", "nut", "nut / stone fruit",
                "nut / drupe", "citrus", "tropical tree", "tropical fruit",
                "subtropical fruit", "syconium fruit"}


def plant_group(p):
    """Coarse group used by the 'plant now' filters."""
    cat = p.get("category")
    sub = (p.get("subcategory") or "").strip()
    if cat == "fruit" and sub in TREE_SUBCATS:
        return "tree"
    return cat  # vegetable, fruit, berry, herb, flower, cover-crop


# A spot with more light can grow plants needing that light *or less demanding*;
# a shady spot can't grow sun-lovers. So filtering is tolerance-based, not exact.
SUN_INCLUDES = {
    "full": {"full", "partial"},
    "partial": {"partial", "shade"},
    "shade": {"shade"},
}


def sun_ok(plant, want):
    if not want:
        return True
    return plant.get("sun") in SUN_INCLUDES.get(want, {want})


def _dtm(plant):
    d = plant.get("days_to_maturity") or {}
    return d.get("max") or d.get("min")


def plantable_ranges(plant, zrec):
    """Realistic in-ground planting windows for a plant in a zone this year.

    Unlike the dataset's narrow 'ideal sow band', this reflects how gardeners
    actually decide: warm crops go in any time there are enough frost-free days
    left to mature before first frost; cool crops get spring AND fall windows;
    perennials plant in the dormant cool season. Returns [(start, end), ...].
    """
    year = dt.date.today().year
    lsf = _parse_frost(zrec.get("last_spring_frost"), year)
    fff = _parse_frost(zrec.get("first_fall_frost"), year)
    season = plant.get("season")
    ft = plant.get("frost_tolerance")
    sow = plant.get("sow_method")
    W = lambda d: dt.timedelta(days=d)
    jan1, dec31 = dt.date(year, 1, 1), dt.date(year, 12, 31)

    # Frost-free zone: annuals plantable essentially year-round.
    if lsf is None or fff is None:
        if season in ("warm", "cool", None):
            return [(jan1, dec31)]
        return [(jan1, dec31)]

    ranges = []
    if season == "warm":
        d = _dtm(plant) or 90
        tender_buf = 14 if ft == "tender" else 0
        start = lsf - W(35) if sow in ("start-indoors", "transplant") else lsf
        end = fff - W(d + tender_buf)
        ranges.append((start, end))
    elif season == "cool":
        d = _dtm(plant) or 60
        frost_ext = W(21) if ft in ("hardy", "very hardy", "half-hardy") else W(0)
        ranges.append((lsf - W(42), lsf + W(21)))          # spring
        fall_mat = fff + frost_ext
        ranges.append((fall_mat - W(d) - W(21), fall_mat - W(d) + W(14)))  # fall
    elif season == "perennial":
        # Container perennials/trees/berries go in across the whole active
        # season (just water them in summer heat); only the hard-frost dead of
        # winter is off-limits in cold zones. Ideal timing lives in directions.
        ranges.append((lsf - W(28), fff + W(28)))
    else:  # biennial / unknown -> cool-ish
        d = _dtm(plant) or 70
        ranges.append((lsf - W(28), fff - W(d)))

    return [(s, e) for (s, e) in ranges if s and e and e >= s]


ZIPCACHE = Path("/opt/openplantdb-site/zipcache.json")


def _load_zipcache():
    try:
        return json.loads(ZIPCACHE.read_text())
    except Exception:
        return {}


def zip_to_zone(zipcode):
    """US ZIP -> USDA hardiness zone (e.g. '9a'), via phzmapi.org, cached to disk."""
    zipcode = str(zipcode).strip()[:5]
    if not zipcode.isdigit():
        return None
    zc = _load_zipcache()
    if zipcode in zc:
        return zc[zipcode]
    try:
        req = urllib.request.Request(f"https://phzmapi.org/{zipcode}.json",
                                     headers={"User-Agent": "openplantdb"})
        with urllib.request.urlopen(req, timeout=8) as r:
            zone = json.loads(r.read()).get("zone")
        if zone:
            zc[zipcode] = zone
            try:
                ZIPCACHE.write_text(json.dumps(zc))
            except Exception:
                pass
        return zone
    except Exception:
        return None


LATLNGCACHE = Path("/opt/openplantdb-site/latlngcache.json")


def zip_to_latlng(zipcode):
    """US ZIP -> (lat, lng) centroid via zippopotam.us, cached to disk."""
    zipcode = str(zipcode).strip()[:5]
    if not zipcode.isdigit():
        return None
    try:
        cache = json.loads(LATLNGCACHE.read_text())
    except Exception:
        cache = {}
    if zipcode in cache:
        return tuple(cache[zipcode])
    try:
        req = urllib.request.Request(f"https://api.zippopotam.us/us/{zipcode}",
                                     headers={"User-Agent": "openplantdb"})
        with urllib.request.urlopen(req, timeout=8) as r:
            place = json.loads(r.read())["places"][0]
        latlng = [float(place["latitude"]), float(place["longitude"])]
        cache[zipcode] = latlng
        try:
            LATLNGCACHE.write_text(json.dumps(cache))
        except Exception:
            pass
        return tuple(latlng)
    except Exception:
        return None


# ---------------------------------------------------------------- API

@app.get("/health")
def health():
    return {"ok": True, "plants": len(STATE["plants"]), "loaded": STATE["loaded"]}


@app.get("/api/stats")
def stats():
    cats = {}
    for p in STATE["plants"]:
        cats[p.get("category")] = cats.get(p.get("category"), 0) + 1
    return {"total": len(STATE["plants"]), "categories": cats,
            "zones": len(STATE["zones"]), "loaded": STATE["loaded"],
            "source": "https://github.com/cwfrazier1/openplantdb", "license": "CC0-1.0"}


@app.get("/api/categories")
def categories():
    cats = {}
    for p in STATE["plants"]:
        c = p.get("category")
        cats[c] = cats.get(c, 0) + 1
    return {"categories": [{"name": k, "count": v} for k, v in sorted(cats.items())]}


@app.get("/api/zones")
def zones():
    return {"about": STATE["zones_about"], "zones": STATE["zones"]}


@app.get("/api/plants")
def list_plants(
    q: str = Query(None, description="text search over name/scientific/directions"),
    category: str = Query(None),
    sun: str = Query(None),
    season: str = Query(None),
    zone: int = Query(None, description="USDA zone number; filters to plants hardy in it"),
    limit: int = Query(60, le=1000),
    offset: int = Query(0, ge=0),
):
    items = STATE["plants"]
    if category:
        items = [p for p in items if p.get("category") == category]
    if sun:
        items = [p for p in items if sun_ok(p, sun)]
    if season:
        items = [p for p in items if p.get("season") == season]
    if zone is not None:
        def hardy(p):
            uz = p.get("usda_zones") or {}
            lo, hi = uz.get("min"), uz.get("max")
            return lo is not None and hi is not None and lo <= zone <= hi
        items = [p for p in items if hardy(p)]
    if q:
        ql = q.lower()
        def match(p):
            return any(ql in str(p.get(f, "")).lower()
                       for f in ("common_name", "scientific_name", "directions",
                                 "slug", "category", "subcategory"))
        items = [p for p in items if match(p)]
    total = len(items)
    page = items[offset:offset + limit]
    return {"total": total, "count": len(page), "offset": offset, "limit": limit,
            "results": [{"slug": p["slug"], "common_name": p.get("common_name"),
                         "scientific_name": p.get("scientific_name"),
                         "category": p.get("category"), "subcategory": p.get("subcategory"),
                         "season": p.get("season"), "sun": p.get("sun"),
                         "water": p.get("water"), "frost_tolerance": p.get("frost_tolerance"),
                         "usda_zones": p.get("usda_zones"),
                         "days_to_maturity": p.get("days_to_maturity")} for p in page]}


@app.get("/api/plants/{slug}")
def get_plant(slug: str):
    p = STATE["by_slug"].get(slug)
    if not p:
        raise HTTPException(404, f"no plant with slug '{slug}'")
    return p


@app.get("/api/plants/{slug}/planting")
def plant_planting(slug: str, zone: str = Query(..., description="USDA zone, e.g. 9a or 9")):
    p = STATE["by_slug"].get(slug)
    if not p:
        raise HTTPException(404, f"no plant with slug '{slug}'")
    res = compute_planting(p, zone)
    if res is None:
        raise HTTPException(400, f"unknown zone '{zone}'")
    return res


# --- season / anytime planning ---------------------------------------
SEASON_LABEL = {"spring": "Spring", "summer": "Summer", "fall": "Fall",
                "winter": "Winter", "anytime": "Anytime this year"}


def _season_targets(when, year):
    """Target date interval(s) a plant window must overlap for the mode.

    Northern-hemisphere meteorological seasons; winter wraps the year so it
    is expressed as two intervals. 'anytime' spans the whole calendar year.
    """
    if when == "anytime":
        return [(dt.date(year, 1, 1), dt.date(year, 12, 31))]
    if when == "spring":
        return [(dt.date(year, 3, 1), dt.date(year, 5, 31))]
    if when == "summer":
        return [(dt.date(year, 6, 1), dt.date(year, 8, 31))]
    if when == "fall":
        return [(dt.date(year, 9, 1), dt.date(year, 11, 30))]
    if when == "winter":
        return [(dt.date(year, 1, 1), dt.date(year, 2, 28)),
                (dt.date(year, 12, 1), dt.date(year, 12, 31))]
    return None


def _pick_range(ranges, targets, today):
    """Choose the most relevant plantable range that overlaps the targets.

    Prefer one active today, else the soonest upcoming, else the most recent.
    """
    hits = [(s, e) for (s, e) in ranges
            if any(s <= te and e >= ts for (ts, te) in targets)]
    if not hits:
        return None
    active = [r for r in hits if r[0] <= today <= r[1]]
    if active:
        return active[0]
    upcoming = sorted((r for r in hits if r[0] > today), key=lambda r: r[0])
    if upcoming:
        return upcoming[0]
    return max(hits, key=lambda r: r[1])


@app.get("/api/whatnow")
def whatnow(
    zip: str = Query(None, description="US ZIP code; resolved to a USDA zone"),
    zone: str = Query(None, description="USDA zone (overrides zip), e.g. 9a"),
    sun: str = Query(None),
    groups: str = Query(None, description="comma list: vegetable,fruit,berry,herb,flower,tree,cover-crop"),
    horizon: int = Query(60, ge=0, le=240, description="also include windows opening within N days"),
    when: str = Query("now", description="now | anytime | spring | summer | fall | winter"),
):
    resolved_zip = None
    if zone is None and zip:
        zone = zip_to_zone(zip)
        resolved_zip = zip
        if zone is None:
            raise HTTPException(400, f"could not resolve ZIP '{zip}' to a hardiness zone")
    if zone is None:
        raise HTTPException(400, "provide a zip or a zone")
    zrec = _zone_record(zone)
    if zrec is None:
        raise HTTPException(400, f"unknown zone '{zone}'")

    gset = {g.strip() for g in groups.split(",") if g.strip()} if groups else None
    today = dt.date.today()
    year = today.year
    fmt = "%b %-d"

    def passes(p):
        return sun_ok(p, sun) and not (gset and plant_group(p) not in gset)

    def item_for(p, s, e, status):
        return {
            "slug": p["slug"], "common_name": p.get("common_name"),
            "scientific_name": p.get("scientific_name"),
            "category": p.get("category"), "group": plant_group(p),
            "sun": p.get("sun"), "water": p.get("water"),
            "days_to_maturity": p.get("days_to_maturity"),
            "sow_method": p.get("sow_method"), "status": status,
            "window": {"start": s.strftime(fmt), "end": e.strftime(fmt)},
            "days_until_open": max(0, (s - today).days), "_start": s.toordinal(),
        }

    frost = {"last_spring": zrec.get("last_spring_frost"),
             "first_fall": zrec.get("first_fall_frost")}

    # --- season / anytime mode: one list of everything plantable then ---
    if when and when != "now":
        targets = _season_targets(when, year)
        if targets is None:
            raise HTTPException(400, f"unknown 'when' value '{when}'")
        items = []
        for p in STATE["plants"]:
            if not passes(p):
                continue
            pick = _pick_range(plantable_ranges(p, zrec), targets, today)
            if pick is None:
                continue
            s, e = pick
            status = "now" if s <= today <= e else ("soon" if s > today else "window")
            items.append(item_for(p, s, e, status))
        items.sort(key=lambda x: (x["_start"], x["common_name"] or ""))
        for it in items:
            it.pop("_start", None)
        return {
            "zone": zone, "zip": resolved_zip, "today": today.isoformat(),
            "mode": when, "mode_label": SEASON_LABEL.get(when, when), "frost": frost,
            "now_count": len(items), "soon_count": 0, "now": items, "soon": [],
        }

    # --- default: what's plantable today, plus what opens within horizon ---
    hz = today + dt.timedelta(days=horizon)
    now_list, soon_list = [], []
    for p in STATE["plants"]:
        if not passes(p):
            continue
        ranges = plantable_ranges(p, zrec)
        if not ranges:
            continue
        cur = next(((s, e) for (s, e) in ranges if s <= today <= e), None)
        upcoming = sorted((r for r in ranges if today < r[0] <= hz), key=lambda r: r[0])
        chosen, status = (cur, "now") if cur else ((upcoming[0], "soon") if upcoming else (None, None))
        if chosen is None:
            continue
        s, e = chosen
        (now_list if status == "now" else soon_list).append(item_for(p, s, e, status))

    for lst in (now_list, soon_list):
        for it in lst:
            it.pop("_start", None)
    now_list.sort(key=lambda x: x["common_name"] or "")
    soon_list.sort(key=lambda x: x["days_until_open"])
    return {
        "zone": zone, "zip": resolved_zip, "today": today.isoformat(),
        "mode": "now", "horizon_days": horizon, "frost": frost,
        "now_count": len(now_list), "soon_count": len(soon_list),
        "now": now_list, "soon": soon_list,
    }


@app.get("/api/geo/zip")
def geo_zip(zip: str = Query(..., description="US ZIP code")):
    """Resolve a ZIP to lat/lng + USDA zone — used to center the community feed."""
    ll = zip_to_latlng(zip)
    if not ll:
        raise HTTPException(404, f"could not resolve ZIP '{zip}'")
    return {"zip": zip[:5], "lat": ll[0], "lng": ll[1], "zone": zip_to_zone(zip)}


@app.get("/openplantdb.json")
def full_dump():
    return JSONResponse(STATE["plants"],
                        headers={"Content-Disposition": "attachment; filename=openplantdb.json"})


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)


@app.get("/api", response_class=HTMLResponse)
def api_page():
    return HTMLResponse(API_HTML)


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return HTMLResponse(PRIVACY_HTML)


# ---------------------------------------------------------------- frontend
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What can I plant now? — find your USDA zone &amp; what to sow today</title>
<meta name="description" content="Enter your ZIP code to find your USDA hardiness zone and see exactly what you can plant right now — plus what's coming up. Powered by OpenPlantDB, a free CC0 dataset of 300+ garden plants.">
<style>
:root{
  --bg:#0e1512; --bg2:#131e19; --card:#17241d; --line:#25382e;
  --ink:#e8f0ea; --dim:#93a89a; --accent:#7bc47f; --accent2:#d9b25f; --chip:#1e3128;
}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--accent)}
header{padding:54px 20px 30px;text-align:center;background:radial-gradient(1200px 400px at 50% -120px,#1c3327 0%,var(--bg) 70%);border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:clamp(30px,6vw,52px);letter-spacing:-.02em}
header h1 .leaf{color:var(--accent)}
header p{margin:14px auto 0;max-width:640px;color:var(--dim);font-size:17px}
.hero-controls{justify-content:center;margin:26px auto 0;max-width:760px}
.browse-h{margin:8px 0 4px;font-size:clamp(20px,4vw,26px)}
.browse-sub{color:var(--dim);margin:0 0 20px;max-width:720px}
.badges{margin-top:22px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.badge{background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;color:var(--dim)}
.badge b{color:var(--accent);font-weight:700}
.wrap{max-width:1120px;margin:0 auto;padding:26px 18px 80px}
.controls{position:sticky;top:0;z-index:5;background:rgba(14,21,18,.92);backdrop-filter:blur(8px);padding:16px 0;border-bottom:1px solid var(--line);margin-bottom:22px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
input,select{background:var(--bg2);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:11px 13px;font-size:15px;outline:none}
input:focus,select:focus{border-color:var(--accent)}
#q{flex:1;min-width:220px}
.count{color:var(--dim);font-size:14px;margin-left:auto}
.cats{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.cat{cursor:pointer;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:6px 13px;font-size:13px;color:var(--dim);user-select:none}
.cat.active{background:var(--accent);color:#08130c;border-color:var(--accent);font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;cursor:pointer;transition:.14s;display:flex;flex-direction:column;gap:8px}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card h3{margin:0;font-size:17px}
.card .sci{color:var(--dim);font-style:italic;font-size:13px}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}
.tag{font-size:11px;background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:3px 8px;color:var(--dim)}
.tag.cat{color:var(--accent2)}
.meta{display:flex;gap:14px;color:var(--dim);font-size:12.5px;margin-top:auto;padding-top:6px}
.meta b{color:var(--ink);font-weight:600}
/* modal */
.modal{position:fixed;inset:0;background:rgba(0,0,0,.66);display:none;align-items:flex-start;justify-content:center;padding:40px 16px;z-index:20;overflow:auto}
.modal.open{display:flex}
.sheet{background:var(--bg2);border:1px solid var(--line);border-radius:16px;max-width:680px;width:100%;padding:26px}
.sheet h2{margin:0 0 2px;font-size:26px}
.sheet .sci{color:var(--dim);font-style:italic;margin-bottom:14px}
.sheet .directions{color:var(--ink);line-height:1.65;margin:14px 0}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:14px 0}
.kv div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.kv span{display:block;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.kv b{font-size:15px}
.plant-zone{margin:16px 0;padding:14px;background:var(--card);border:1px solid var(--line);border-radius:12px}
.plant-zone .win{font-size:20px;color:var(--accent);font-weight:700;margin-top:6px}
.close{float:right;cursor:pointer;color:var(--dim);font-size:26px;line-height:1;margin:-6px -6px 0 0}
.src{color:var(--dim);font-size:12px;margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
/* what-can-I-plant-now panel */
.wn{background:linear-gradient(180deg,#13241b,var(--bg));border-bottom:1px solid var(--line)}
.wn-inner{max-width:1120px;margin:0 auto;padding:32px 18px}
.wn-inner h2{margin:0;font-size:clamp(22px,4vw,28px)}
.wn-sub{color:var(--dim);margin:6px 0 18px}
.wn-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.wn-controls #wn-zip{width:150px;letter-spacing:.06em}
.wn-controls button{background:var(--accent);color:#08130c;border:none;border-radius:10px;padding:11px 22px;font-weight:700;font-size:15px;cursor:pointer}
.wn-controls button:hover{filter:brightness(1.08)}
.wn-zone{color:var(--accent2);font-weight:600;font-size:14px}
.wn-groups{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 4px}
.wn-chip{cursor:pointer;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:6px 13px;font-size:13px;color:var(--dim);user-select:none}
.wn-chip.active{background:var(--accent2);color:#1a1206;border-color:var(--accent2);font-weight:700}
.wn-col h3{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--dim);margin:20px 0 10px;display:flex;align-items:center;gap:8px}
.wn-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.wn-item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 14px;cursor:pointer;transition:.14s}
.wn-item:hover{border-color:var(--accent);transform:translateY(-2px)}
.wn-item .n{font-weight:600}
.wn-item .w{color:var(--accent);font-size:13px;margin-top:3px}
.wn-item .s{color:var(--dim);font-size:12px;margin-top:4px}
.wn-badge{font-size:11px;font-weight:700;border-radius:6px;padding:2px 8px}
.wn-badge.now{background:var(--accent);color:#08130c}
.wn-badge.soon{background:var(--chip);color:var(--accent2);border:1px solid var(--line)}
footer{text-align:center;color:var(--dim);font-size:13px;padding:34px 16px 60px;border-top:1px solid var(--line)}
code{background:#0a120d;border:1px solid var(--line);border-radius:6px;padding:2px 6px;font-size:13px;color:var(--accent)}
.api{max-width:1120px;margin:0 auto;padding:0 18px}
.api h2{border-top:1px solid var(--line);padding-top:30px}
.ep{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:8px 0;font-family:ui-monospace,Menlo,monospace;font-size:13.5px}
.ep .m{color:var(--accent2);font-weight:700;margin-right:8px}
.ep .d{color:var(--dim);font-family:inherit;font-size:12.5px;margin-top:4px;font-family:-apple-system,sans-serif}
</style>
</head>
<body>
<header>
  <h1><span class="leaf">&#127793;</span> What can I plant now?</h1>
  <p>A free, public-domain (CC0) library of garden plants — search the catalog below, or jump to your ZIP-based planting calendar.</p>
  <div class="badges">
    <span class="badge"><b id="b-total">…</b> plants</span>
    <span class="badge"><b id="b-cats">…</b> categories</span>
    <span class="badge"><b>CC0</b> public domain</span>
    <span class="badge"><a href="#wn">Plant-by-ZIP &#8595;</a></span>
    <span class="badge"><a href="/api">JSON API &#8594;</a></span>
    <span class="badge"><a href="https://github.com/cwfrazier1/openplantdb">GitHub &#8599;</a></span>
  </div>
</header>

<div class="wrap">
  <div class="controls">
    <div class="row">
      <input id="q" placeholder="Search plants — tomato, basil, pollinator, wet soil…">
      <select id="zone"><option value="">All zones</option></select>
      <select id="sun">
        <option value="">Any sun</option><option>full</option>
        <option value="partial">partial</option><option>shade</option>
      </select>
      <span class="count" id="count"></span>
    </div>
    <div class="cats" id="cats"></div>
  </div>
  <div class="grid" id="grid"></div>
</div>

<section class="wn" id="wn">
  <div class="wn-inner">
    <h2>&#127793; What can I plant right now?</h2>
    <p class="wn-sub">Enter your ZIP code — we'll find your USDA hardiness zone and show exactly what's ready to sow or transplant today, plus what's coming up. Planning ahead? Switch to <b>Anytime</b> or pick a season.</p>
    <div class="wn-controls">
      <input id="wn-zip" inputmode="numeric" maxlength="5" placeholder="ZIP code">
      <select id="wn-when">
        <option value="now" selected>Right now</option>
        <option value="anytime">Anytime this year</option>
        <option value="spring">Plan for spring</option>
        <option value="summer">Plan for summer</option>
        <option value="fall">Plan for fall</option>
        <option value="winter">Plan for winter</option>
      </select>
      <select id="wn-sun"><option value="">Any sun</option><option>full</option><option value="partial">partial</option><option>shade</option></select>
      <select id="wn-horizon"><option value="30">Next 30 days</option><option value="60" selected>Next 60 days</option><option value="90">Next 90 days</option></select>
      <button id="wn-go">Show</button>
      <span id="wn-zone" class="wn-zone"></span>
    </div>
    <div class="wn-groups" id="wn-groups"></div>
    <div id="wn-results"></div>
  </div>
</section>

<footer>
  Powered by <a href="/api">OpenPlantDB</a> — dedicated to the public domain under <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0</a>.
  Built because the old canonical open crop database went offline and its data vanished.<br>
  Data grows nightly. Building something? See the <a href="/api">JSON API</a>. Source &amp; contributions: <a href="https://github.com/cwfrazier1/openplantdb">github.com/cwfrazier1/openplantdb</a>
</footer>

<div class="modal" id="modal"><div class="sheet" id="sheet"></div></div>

<script>
const $ = s => document.querySelector(s);
let CATS = [], activeCat = "", ZONES = [], TIMER;

const rng = o => !o ? "—" : (o.min==null&&o.max==null) ? "—" : (o.min===o.max||o.max==null) ? o.min : `${o.min}–${o.max}`;
const cap = s => s ? s[0].toUpperCase()+s.slice(1) : s;

async function boot(){
  const [stats, zdoc] = await Promise.all([
    fetch('/api/stats').then(r=>r.json()),
    fetch('/api/zones').then(r=>r.json())
  ]);
  $('#b-total').textContent = stats.total;
  $('#b-cats').textContent = Object.keys(stats.categories).length;
  ZONES = zdoc.zones;
  const zsel = $('#zone');
  ZONES.forEach(z => { const o=document.createElement('option'); o.value=z.zone; o.textContent='Zone '+z.zone; zsel.appendChild(o); });
  CATS = Object.entries(stats.categories).sort();
  const cbox = $('#cats');
  const mk = (name,count,val)=>{const el=document.createElement('span');el.className='cat'+(val===activeCat?' active':'');el.textContent=count!=null?`${cap(name)} ${count}`:name;el.onclick=()=>{activeCat=val;[...cbox.children].forEach(c=>c.classList.remove('active'));el.classList.add('active');load();};return el;};
  cbox.appendChild(mk('All',stats.total,''));
  CATS.forEach(([n,c])=>cbox.appendChild(mk(n,c,n)));
  ['q','zone','sun'].forEach(id=>$('#'+id).addEventListener('input',()=>{clearTimeout(TIMER);TIMER=setTimeout(load,180);}));
  load();

  // ---- what-can-I-plant-now ----
  wnBuildChips();
  wnSyncWhen();
  $('#wn-go').onclick = wnLoad;
  $('#wn-zip').addEventListener('keydown', e=>{ if(e.key==='Enter') wnLoad(); });
  ['wn-sun','wn-horizon'].forEach(id=>$('#'+id).addEventListener('change', wnLoad));
  $('#wn-when').addEventListener('change', ()=>{ wnSyncWhen(); wnLoad(); });
  const savedZip = localStorage.getItem('opdb_zip');
  if(savedZip){ $('#wn-zip').value = savedZip; wnLoad(); }
}

let WN = new Set();
function wnBuildChips(){
  const defs=[['','All'],['vegetable','Vegetables'],['fruit','Fruit'],['berry','Berries'],['tree','Trees'],['herb','Herbs'],['flower','Flowers'],['cover-crop','Cover crops']];
  const box=$('#wn-groups');
  defs.forEach(([val,label])=>{
    const el=document.createElement('span'); el.className='wn-chip'+(val===''?' active':''); el.textContent=label; el.dataset.val=val;
    el.onclick=()=>{
      if(val===''){ WN.clear(); }
      else { WN.has(val)?WN.delete(val):WN.add(val); }
      [...box.children].forEach(c=>c.classList.toggle('active', WN.size? WN.has(c.dataset.val) : c.dataset.val===''));
      wnLoad();
    };
    box.appendChild(el);
  });
}
function wnSyncWhen(){
  // The "next N days" horizon only applies to the live "Right now" view.
  $('#wn-horizon').style.display = $('#wn-when').value==='now' ? '' : 'none';
}
async function wnLoad(){
  const zip=$('#wn-zip').value.trim();
  const out=$('#wn-results');
  if(zip.length!==5){ out.innerHTML='<p style="color:var(--dim)">Enter a 5-digit ZIP code to see what to plant.</p>'; return; }
  localStorage.setItem('opdb_zip',zip);
  const when=$('#wn-when').value;
  const p=new URLSearchParams({zip, when});
  if(when==='now') p.set('horizon',$('#wn-horizon').value);
  if($('#wn-sun').value) p.set('sun',$('#wn-sun').value);
  if(WN.size) p.set('groups',[...WN].join(','));
  out.innerHTML='<p style="color:var(--dim)">Finding your zone…</p>';
  let d;
  try{ const r=await fetch('/api/whatnow?'+p); if(!r.ok) throw r; d=await r.json(); }
  catch(e){ out.innerHTML='<p style="color:#e0a">Couldn\'t resolve that ZIP to a zone — try another.</p>'; $('#wn-zone').textContent=''; return; }
  $('#wn-zone').textContent=`Zone ${d.zone} · last frost ${d.frost.last_spring||'—'} · first frost ${d.frost.first_fall||'—'}`;
  const card=x=>`<div class="wn-item" data-slug="${x.slug}"><div class="n">${x.common_name}</div><div class="w">${x.status==='now'?('Plant now · through '+x.window.end):(x.window.start+' – '+x.window.end)}</div><div class="s">${cap(x.group)} · ${x.sow_method||'direct'}${x.status==='soon'?(' · opens in '+x.days_until_open+'d'):''}</div></div>`;
  let html='';
  if(d.mode && d.mode!=='now'){
    const heading = d.mode==='anytime' ? 'Plantable in your zone this year' : ('Plant in '+d.mode_label);
    html+=`<div class="wn-col"><h3>${heading} <span class="wn-badge now">${d.now_count}</span></h3>`;
    html+= d.now.length?`<div class="wn-list">${d.now.map(card).join('')}</div>`:'<p style="color:var(--dim)">Nothing in the dataset fits that window for your zone yet.</p>';
    html+='</div>';
  } else {
    html+=`<div class="wn-col"><h3>Ready to plant now <span class="wn-badge now">${d.now_count}</span></h3>`;
    html+= d.now.length?`<div class="wn-list">${d.now.map(card).join('')}</div>`:'<p style="color:var(--dim)">Nothing lands squarely in today\'s window — see what\'s coming up below.</p>';
    html+='</div>';
    html+=`<div class="wn-col"><h3>Coming up · next ${d.horizon_days} days <span class="wn-badge soon">${d.soon_count}</span></h3>`;
    html+= d.soon.length?`<div class="wn-list">${d.soon.map(card).join('')}</div>`:'<p style="color:var(--dim)">Nothing new opening in this window.</p>';
    html+='</div>';
  }
  out.innerHTML=html;
  out.querySelectorAll('.wn-item').forEach(el=>el.onclick=()=>open(el.dataset.slug));
}

async function load(){
  const p = new URLSearchParams();
  if($('#q').value) p.set('q',$('#q').value);
  if(activeCat) p.set('category',activeCat);
  if($('#zone').value) p.set('zone', parseInt($('#zone').value));
  if($('#sun').value) p.set('sun',$('#sun').value);
  p.set('limit','300');
  const d = await fetch('/api/plants?'+p).then(r=>r.json());
  $('#count').textContent = `${d.total} plant${d.total===1?'':'s'}`;
  const g = $('#grid'); g.innerHTML='';
  d.results.forEach(pl=>{
    const c = document.createElement('div'); c.className='card'; c.onclick=()=>open(pl.slug);
    c.innerHTML = `<h3>${pl.common_name}</h3><div class="sci">${pl.scientific_name||''}</div>
      <div class="tags"><span class="tag cat">${cap(pl.category)}</span>
      ${pl.season?`<span class="tag">${pl.season}</span>`:''}
      ${pl.sun?`<span class="tag">&#9788; ${pl.sun}</span>`:''}
      ${pl.frost_tolerance?`<span class="tag">${pl.frost_tolerance}</span>`:''}</div>
      <div class="meta"><span>Zones <b>${rng(pl.usda_zones)}</b></span><span>Maturity <b>${rng(pl.days_to_maturity)}d</b></span></div>`;
    g.appendChild(c);
  });
  if(!d.results.length) g.innerHTML='<p style="color:var(--dim)">No plants match — try a broader search.</p>';
}

async function open(slug){
  const zone = $('#zone').value;
  const pl = await fetch('/api/plants/'+slug).then(r=>r.json());
  let plant = null;
  const zq = zone || '9a';
  try{ plant = await fetch(`/api/plants/${slug}/planting?zone=${zq}`).then(r=>r.json()); }catch(e){}
  const kv = (l,v)=>`<div><span>${l}</span><b>${v}</b></div>`;
  const hasRange = o => o && (o.min!=null || o.max!=null);
  const seedSown = hasRange(pl.days_to_germination) || hasRange(pl.germination_soil_temp_f);
  const propNote = {transplant:'nursery transplant',cutting:'cuttings',bulb:'bulbs',division:'division',tuber:'tubers'}[pl.sow_method] || 'transplant';
  const germBlock = seedSown
    ? kv('Days to germinate', rng(pl.days_to_germination)) + kv('Soil temp °F', rng(pl.germination_soil_temp_f))
    : `<div style="grid-column:1/-1"><span>Germination</span><b style="font-size:13px;color:var(--dim)">n/a — grown from ${propNote}, not seed</b></div>`;
  let win = '';
  if(plant && plant.window){ win = `<div class="plant-zone"><span style="color:var(--dim);font-size:12px;text-transform:uppercase">Plant / sow window · Zone ${zq}</span><div class="win">${plant.window.start} – ${plant.window.end}</div>${plant.note?`<div style="color:var(--dim);font-size:13px;margin-top:6px">${plant.note}</div>`:''}</div>`; }
  else if(plant){ win = `<div class="plant-zone"><span style="color:var(--dim);font-size:12px">Zone ${zq}: ${plant.reason||'perennial / no fixed window'}</span>${plant.note?`<div style="color:var(--dim);font-size:13px;margin-top:6px">${plant.note}</div>`:''}</div>`; }
  $('#sheet').innerHTML = `
    <span class="close" onclick="$('#modal').classList.remove('open')">&times;</span>
    <h2>${pl.common_name}</h2><div class="sci">${pl.scientific_name||''}</div>
    <div class="tags"><span class="tag cat">${cap(pl.category)}${pl.subcategory?' · '+pl.subcategory:''}</span>
      <span class="tag">${pl.season||''}</span><span class="tag">${pl.frost_tolerance||''}</span></div>
    ${win}
    <div class="kv">
      ${kv('USDA zones', rng(pl.usda_zones))}
      ${kv('Days to maturity', rng(pl.days_to_maturity)+ (pl.maturity_from?` (from ${pl.maturity_from})`:''))}
      ${germBlock}
      ${kv('Sun', pl.sun||'—')}
      ${kv('Water', pl.water||'—')}
      ${kv('Sow method', pl.sow_method||'—')}
      ${kv('Spacing (in)', rng(pl.spacing_in))}
      ${kv('Height (in)', rng(pl.height_in))}
      ${kv('Spread (in)', rng(pl.spread_in))}
    </div>
    <div class="directions">${pl.directions||''}</div>
    <div class="src">Sources: ${(pl.sources||[]).join(' · ')||'—'} &nbsp;·&nbsp; slug <code>${pl.slug}</code></div>`;
  $('#modal').classList.add('open');
}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')e.target.classList.remove('open');});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('#modal').classList.remove('open');});
boot();
</script>
<script src="/app.js" defer></script>
</body>
</html>"""


API_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenPlantDB JSON API — free, CC0, no auth</title>
<meta name="description" content="The OpenPlantDB JSON API: a free, read-only, CORS-open, no-auth API over 300+ CC0 garden plants with zone-aware planting windows. Endpoints, parameters and examples.">
<style>
:root{
  --bg:#0e1512; --bg2:#131e19; --card:#17241d; --line:#25382e;
  --ink:#e8f0ea; --dim:#93a89a; --accent:#7bc47f; --accent2:#d9b25f; --chip:#1e3128;
}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--accent)}
header{padding:54px 20px 30px;text-align:center;background:radial-gradient(1200px 400px at 50% -120px,#1c3327 0%,var(--bg) 70%);border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:clamp(28px,5vw,44px);letter-spacing:-.02em}
header h1 .leaf{color:var(--accent)}
header p{margin:14px auto 0;max-width:640px;color:var(--dim);font-size:17px}
.back{display:inline-block;margin-top:18px;color:var(--dim);font-size:14px}
.wrap{max-width:960px;margin:0 auto;padding:32px 18px 80px}
h2{font-size:22px;margin:34px 0 6px}
.lead{color:var(--dim);margin:0 0 18px}
.ep{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px 15px;margin:9px 0;font-family:ui-monospace,Menlo,monospace;font-size:14px}
.ep .m{color:var(--accent2);font-weight:700;margin-right:8px}
.ep .d{color:var(--dim);font-family:-apple-system,sans-serif;font-size:13px;margin-top:5px}
code{background:#0a120d;border:1px solid var(--line);border-radius:6px;padding:2px 6px;font-size:13px;color:var(--accent)}
pre{background:#0a120d;border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow:auto;font-size:13px;color:var(--ink)}
.base{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 15px;margin:6px 0 4px;font-family:ui-monospace,Menlo,monospace}
footer{text-align:center;color:var(--dim);font-size:13px;padding:34px 16px 60px;border-top:1px solid var(--line)}
</style>
</head>
<body>
<header>
  <h1><span class="leaf">&#128268;</span> OpenPlantDB JSON API</h1>
  <p>A free, read-only, CORS-open, no-auth API over the OpenPlantDB dataset — 300+ garden plants with zone-aware planting windows.</p>
  <a class="back" href="/">&#8592; Back to <b>What can I plant now?</b></a>
</header>

<div class="wrap">
  <h2>Base URL</h2>
  <p class="lead">No key, no auth, permissive CORS — call it straight from the browser.</p>
  <div class="base" id="base"></div>

  <h2>Endpoints</h2>
  <div class="ep"><span class="m">GET</span>/api/plants<div class="d">List &amp; filter plants: <code>?q=</code> <code>?category=</code> <code>?zone=9</code> <code>?sun=full</code> <code>?season=</code> <code>?limit=</code> <code>?offset=</code></div></div>
  <div class="ep"><span class="m">GET</span>/api/plants/{slug}<div class="d">Full record for one plant.</div></div>
  <div class="ep"><span class="m">GET</span>/api/plants/{slug}/planting?zone=9a<div class="d">Computed sow/plant window for a given USDA zone (letter suffix tolerated, e.g. <code>9a</code>&nbsp;&rarr;&nbsp;9).</div></div>
  <div class="ep"><span class="m">GET</span>/api/whatnow?zip=39564<div class="d">What to plant, zone-aware from a ZIP: <code>?when=now</code> (default, + <code>?horizon=30|60|90</code>) or <code>?when=anytime</code> / <code>spring</code> / <code>summer</code> / <code>fall</code> / <code>winter</code>. Also <code>?sun=</code> and <code>?groups=vegetable,herb</code>. This is the endpoint powering the home page.</div></div>
  <div class="ep"><span class="m">GET</span>/api/categories<div class="d">Category names + counts.</div></div>
  <div class="ep"><span class="m">GET</span>/api/zones<div class="d">USDA zones with typical frost dates.</div></div>
  <div class="ep"><span class="m">GET</span>/api/stats<div class="d">Dataset totals.</div></div>
  <div class="ep"><span class="m">GET</span>/openplantdb.json<div class="d">The entire dataset in one file.</div></div>

  <h2>Example</h2>
  <pre id="example">curl …</pre>

  <h2>Interactive docs</h2>
  <p class="lead">Full OpenAPI/Swagger explorer: <a href="/api/docs">/api/docs</a></p>
</div>

<footer>
  OpenPlantDB is dedicated to the public domain under <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0 1.0</a>.
  Source &amp; contributions: <a href="https://github.com/cwfrazier1/openplantdb">github.com/cwfrazier1/openplantdb</a>
</footer>

<script>
const base = location.origin;
document.getElementById('base').textContent = base;
document.getElementById('example').textContent =
  'curl "' + base + '/api/whatnow?zip=39564&when=now&horizon=60"\n' +
  'curl "' + base + '/api/plants?q=tomato&zone=9"\n' +
  'curl "' + base + '/api/plants/basil/planting?zone=9a"';
</script>
</body>
</html>"""


PRIVACY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy Policy — What Can I Plant Now</title>
<meta name="description" content="Privacy policy for the What Can I Plant Now iOS app and whatcaniplantnow.com. We do not collect, store, or share any personal information.">
<style>
:root{--bg:#0e1512;--bg2:#131e19;--card:#17241d;--line:#25382e;--ink:#e8f0ea;--dim:#93a89a;--accent:#7bc47f}
*{box-sizing:border-box}
body{margin:0;font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
a{color:var(--accent)}
header{padding:54px 20px 26px;text-align:center;background:radial-gradient(1200px 400px at 50% -120px,#1c3327 0%,var(--bg) 70%);border-bottom:1px solid var(--line)}
header h1{margin:0;font-size:clamp(26px,5vw,40px);letter-spacing:-.02em}
header p{margin:12px auto 0;max-width:640px;color:var(--dim)}
.wrap{max-width:760px;margin:0 auto;padding:36px 20px 80px}
.wrap h2{font-size:20px;margin:34px 0 8px;color:var(--accent)}
.wrap p,.wrap li{color:var(--ink)}
.wrap li{margin:6px 0}
.eff{color:var(--dim);font-size:14px}
footer{border-top:1px solid var(--line);padding:26px 20px;text-align:center;color:var(--dim);font-size:14px}
</style>
</head>
<body>
<header>
  <h1>Privacy Policy</h1>
  <p>What Can I Plant Now &middot; whatcaniplantnow.com</p>
</header>
<div class="wrap">
  <p class="eff">Effective July 14, 2026</p>

  <p><b>Short version: we do not collect, store, or share any personal
  information about you.</b> What Can I Plant Now has no accounts, no logins,
  no analytics, no advertising, and no third-party tracking.</p>

  <h2>Information we collect</h2>
  <p>None. The app does not require an account and does not ask for your name,
  email, contacts, photos, location permissions, or any other personal
  identifiers. We do not use analytics or advertising SDKs, and we do not
  track you across apps or websites.</p>

  <h2>Your ZIP code</h2>
  <p>If you enter a ZIP code, it is saved <b>only on your device</b> so the app
  can remember your USDA hardiness zone between visits. Your ZIP is sent to
  the OpenPlantDB API (whatcaniplantnow.com) solely to look up the matching
  hardiness zone and planting windows. It is not tied to your identity, is not
  used to profile you, and is not retained in association with you.</p>

  <h2>Network requests</h2>
  <p>To show plant data and planting dates, the app fetches information from
  the public OpenPlantDB API. Like any web server, our infrastructure may
  transiently log request metadata (such as IP address) for security and
  operational reliability. This information is not used to identify you, is not
  linked to your ZIP or any profile, and is never sold or shared for marketing.</p>

  <h2>Data sharing and sale</h2>
  <p>We do not sell your data and we do not share personal data with third
  parties, because we do not collect it in the first place.</p>

  <h2>Children's privacy</h2>
  <p>The app is safe for all ages and collects no personal information from
  anyone, including children under 13.</p>

  <h2>Changes to this policy</h2>
  <p>If this policy changes, the updated version will be posted at this URL with
  a new effective date.</p>

  <h2>Contact</h2>
  <p>Questions about this policy can be raised through the project's public
  repository at
  <a href="https://github.com/cwfrazier1/openplantdb">github.com/cwfrazier1/openplantdb</a>.</p>
</div>
<footer>
  <a href="/">&larr; whatcaniplantnow.com</a>
</footer>
</body>
</html>"""


# CORS for the open API
@app.middleware("http")
async def cors(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp
