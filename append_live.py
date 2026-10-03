import json
from pathlib import Path

LIVE = Path("data/live")
LIVE.mkdir(parents=True, exist_ok=True)


def rows_station(path):
    d = json.load(open(path)).get("data", {})
    return [(r["timestamp"], i["stationId"], i["value"])
            for r in d.get("readings", []) for i in r["data"]]


def rows_pm25(path):
    d = json.load(open(path)).get("data", {})
    out = []
    for it in d.get("items", []):
        rd = it.get("readings", {})
        key = next((k for k in rd if "pm25" in k), None)
        for region, v in (rd.get(key) or {}).items():
            out.append((it["timestamp"], region, v))
    return out


def append(name, rows):
    by_month = {}
    for r in rows:
        by_month.setdefault(r[0][:7], []).append(r)
    for month, rs in by_month.items():
        f = LIVE / f"{name}_{month}.csv"
        seen = set()
        if f.exists():
            with open(f) as fh:
                next(fh, None)
                seen = {tuple(line.rstrip("\n").split(",")[:2]) for line in fh}
        new = [r for r in rs if (r[0], str(r[1])) not in seen]
        if not new:
            continue
        write_header = not f.exists()
        with open(f, "a") as fh:
            if write_header:
                fh.write("ts,id,value\n")
            for r in new:
                fh.write(f"{r[0]},{r[1]},{r[2]}\n")


for name, path, fn in [
    ("air_temp", "data/air_temp.json", rows_station),
    ("rainfall", "data/rainfall.json", rows_station),
    ("pm25", "data/pm25.json", rows_pm25),
]:
    try:
        append(name, fn(path))
    except (FileNotFoundError, ValueError, KeyError) as e:
        print("WARN:", name, e)
