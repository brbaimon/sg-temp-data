import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = "https://api-open.data.gov.sg/v2/real-time/api/"
HEADERS = {"x-api-key": os.environ["DATAGOV_KEY"]}
# api path -> (folder name, kind)
DATASETS = {
    "air-temperature": ("air_temp", "station_mean"),
    "rainfall": ("rainfall", "station_sum"),
    "pm25": ("pm25", "region_mean"),
}


def get(api, params, tries=12):
    for _ in range(tries):
        r = requests.get(ROOT + api, params=params, headers=HEADERS, timeout=30)
        if r.status_code != 429:
            r.raise_for_status()
            return r.json()
        time.sleep(int(r.headers.get("Retry-After", 5)))
    raise RuntimeError("still rate limited")


def fetch_day(api, d):
    rows, token = [], None
    while True:
        params = {"date": d}
        if token:
            params["paginationToken"] = token
        body = get(api, params)
        data = body.get("data", {})
        rows += data.get("readings") or data.get("items") or []
        token = data.get("paginationToken") or body.get("paginationToken")
        if not token:
            return rows


def flatten(rows, kind):
    """Return a long table: ts, id, value."""
    out = []
    if kind == "region_mean":  # pm25: one dict of regions per timestamp
        for it in rows:
            rd = it.get("readings", {})
            key = next((k for k in rd if "pm25" in k), None)
            for region, v in (rd.get(key) or {}).items():
                out.append((it["timestamp"], region, v))
    else:  # temperature and rainfall: list of stations per timestamp
        for r in rows:
            for i in r["data"]:
                out.append((r["timestamp"], i["stationId"], i["value"]))
    return pd.DataFrame(out, columns=["ts", "id", "value"])


def day_to_daily(rows, kind):
    idcol = "region" if kind == "region_mean" else "station_id"
    df = flatten(rows, kind)
    if df.empty:
        return pd.DataFrame(columns=["date", idcol])
    df["ts"] = pd.to_datetime(df["ts"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = df["ts"].dt.date
    g = df.groupby(["date", "id"])["value"]
    if kind == "station_sum":  # rainfall: total and peak per day
        res = g.agg(total_mm="sum", max_reading="max", count="count")
    else:
        res = g.agg(mean="mean", min="min", max="max", count="count")
    return res.reset_index().rename(columns={"id": idcol})


def backfill(start, end, names):
    d = start
    while d <= end:
        for api, (folder, kind) in DATASETS.items():
            if folder not in names:
                continue
            out = Path("data/daily") / folder
            out.mkdir(parents=True, exist_ok=True)
            f = out / f"{d}.csv"
            if f.exists():
                continue
            t0 = time.time()
            daily = day_to_daily(fetch_day(api, d.isoformat()), kind)
            daily.to_csv(f, index=False)
            print(folder, d, len(daily), "rows,", round(time.time() - t0), "s",
                  flush=True)
        d += timedelta(days=1)


if __name__ == "__main__":
    names = sys.argv[3].split(",") if len(sys.argv) > 3 else [v[0] for v in DATASETS.values()]
    backfill(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), names)
