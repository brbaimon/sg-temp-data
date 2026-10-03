import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIVE = Path("data/live")
LIVE.mkdir(parents=True, exist_ok=True)
KEEP_DAYS = 7

STATION_COLS = ["ts", "id", "station_name", "latitude", "longitude",
                "value", "reading_type", "reading_unit"]
PM25_COLS = ["ts", "id", "updated_ts", "date", "latitude", "longitude",
             "reading_key", "value"]
WBGT_COLS = ["ts", "id", "station_name", "town_center", "latitude", "longitude",
             "wbgt", "heat_stress", "is_station_data", "record_type", "updated_ts"]


def rows_station(path):
    d = json.load(open(path)).get("data", {})
    meta = {}
    for s in d.get("stations", []):
        loc = s.get("location") or {}
        meta[s["id"]] = (s.get("name", ""), loc.get("latitude", ""), loc.get("longitude", ""))
    rtype = d.get("readingType", "")
    runit = d.get("readingUnit", "")
    out = []
    for r in d.get("readings", []):
        for i in r["data"]:
            sid = i["stationId"]
            name, lat, lon = meta.get(sid, ("", "", ""))
            out.append([r["timestamp"], sid, name, lat, lon, i.get("value", ""), rtype, runit])
    return out


def rows_pm25(path):
    d = json.load(open(path)).get("data", {})
    meta = {}
    for m in d.get("regionMetadata", []):
        loc = m.get("labelLocation") or {}
        meta[m["name"]] = (loc.get("latitude", ""), loc.get("longitude", ""))
    out = []
    for it in d.get("items", []):
        for key, regions in (it.get("readings") or {}).items():
            for region, v in regions.items():
                lat, lon = meta.get(region, ("", ""))
                out.append([it["timestamp"], region, it.get("updatedTimestamp", ""),
                            it.get("date", ""), lat, lon, key, v])
    return out


def append(name, cols, rows):
    by_month = {}
    for r in rows:
        by_month.setdefault(r[0][:7], []).append(r)
    for month, rs in by_month.items():
        f = LIVE / f"{name}_{month}.csv"
        seen = set()
        if f.exists():
            with open(f, newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                if header != cols:
                    print("WARN:", f, "has an old header, delete it:", header)
                    continue
                seen = {(row[0], row[1]) for row in reader if len(row) > 1}
        new = [r for r in rs if (r[0], str(r[1])) not in seen]
        if not new:
            continue
        is_new = not f.exists()
        with open(f, "a", newline="") as fh:
            w = csv.writer(fh)
            if is_new:
                w.writerow(cols)
            w.writerows(new)

def rows_wbgt(path):
    d = json.load(open(path)).get("data", {})
    out = []
    for rec in d.get("records", []):
        item = rec.get("item") or {}
        ts = rec.get("datetime") or rec.get("timestamp", "")
        for r in item.get("readings", []):
            st = r.get("station") or {}
            loc = r.get("location") or {}
            out.append([ts, st.get("id", ""), st.get("name", ""),
                        st.get("townCenter", ""), loc.get("latitude", ""),
                        loc.get("longitude", ""), r.get("wbgt", ""),
                        r.get("heatStress", ""), item.get("isStationData", ""),
                        item.get("type", ""), rec.get("updatedTimestamp", "")])
    return out


def prune():
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    for f in LIVE.glob("*.csv"):
        with open(f, newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            keep = []
            for row in reader:
                try:
                    if datetime.fromisoformat(row[0]) >= cutoff:
                        keep.append(row)
                except (ValueError, IndexError):
                    keep.append(row)
        if not keep:
            f.unlink()
            print("pruned empty file", f)
            continue
        with open(f, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(keep)


for name, path, cols, fn in [
    ("air_temp", "data/air_temp.json", STATION_COLS, rows_station),
    ("rainfall", "data/rainfall.json", STATION_COLS, rows_station),
    ("pm25", "data/pm25.json", PM25_COLS, rows_pm25),
    ("wbgt", "data/wbgt.json", WBGT_COLS, rows_wbgt),
]:
    try:
        rows = fn(path)
        print(name, "rows:", len(rows), "sample:", rows[0] if rows else None)
        append(name, cols, rows)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print("WARN:", name, e)

prune()
