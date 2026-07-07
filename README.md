# openplantdb-site

Showcase website + read-only JSON API for [OpenPlantDB](https://github.com/cwfrazier1/openplantdb),
the CC0 public-domain garden-plant dataset.

**Live:** <https://whatcaniplantnow.com> (also <https://plants.fairbrook.org>)

## What it does

- Serves the dataset (`/opt/openplantdb/data/plants.json`) as a browsable,
  dark-themed catalog with search, category/zone/sun filters, and a per-plant
  detail modal with zone-aware planting windows.
- **"What can I plant now?"** — enter a US ZIP, it resolves your USDA hardiness
  zone (via phzmapi.org) and shows what's ready to sow/transplant today plus
  what's coming up. A **When** selector switches between *Right now*,
  *Anytime this year*, and planning ahead for *spring / summer / fall / winter*.
- A CORS-open, no-auth JSON API. See `/api/docs` or the API section on the home
  page.

### Key API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/plants` | list/filter (`q`, `category`, `zone`, `sun`, `season`, `limit`, `offset`) |
| `GET /api/plants/{slug}` | full record |
| `GET /api/plants/{slug}/planting?zone=9a` | computed sow window for a zone |
| `GET /api/whatnow?zip=39564` | zone-aware "what to plant"; `when=now\|anytime\|spring\|summer\|fall\|winter`, plus `sun`, `groups`, `horizon` |
| `GET /api/categories` · `/api/zones` · `/api/stats` | metadata |
| `GET /openplantdb.json` | entire dataset in one file |

## Architecture

- Single-file FastAPI app (`app.py`), served by uvicorn under systemd on
  **CT 226 (192.168.1.68:8000)** in the homelab.
- nginx on **CT 200** reverse-proxies `whatcaniplantnow.com` (+ `www`) and
  `plants.fairbrook.org` to it, with Let's Encrypt TLS.
- The dataset is a *separate* git repo (`cwfrazier1/openplantdb`) cloned at
  `/opt/openplantdb`; it grows nightly via an unattended expansion job.
  `deploy/refresh.sh` (cron `15 3 * * *`) pulls the dataset and restarts the
  service when it changes.
- The frontend uses `location.origin`, so it is host-agnostic and works under
  any domain pointed at it.

## Deploy

```bash
# on CT 226
cd /opt/openplantdb-site
git pull            # or copy app.py in
python3 -m py_compile app.py
systemctl restart openplantdb-site
```

`deploy/` holds the systemd unit, the dataset-refresh script, and the nginx
vhost template. TLS is issued with:

```bash
certbot --nginx -d whatcaniplantnow.com -d www.whatcaniplantnow.com --redirect
```

## License

Code: MIT. Data (fetched from OpenPlantDB at runtime): CC0-1.0.
