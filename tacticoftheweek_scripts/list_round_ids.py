import json, time
now = time.time() * 1000
week = 7 * 24 * 3600 * 1000
for line in open("/tmp/lichess_bc.ndjson"):
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    for r in d.get("rounds", []):
        s = r.get("startsAt")
        if s and now - week <= s <= now and r.get("finished"):
            print(r["id"])
