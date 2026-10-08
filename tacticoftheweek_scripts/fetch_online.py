import json, os, time, urllib.request, urllib.error

UA = "tactic-of-the-week/1.0 (chess tactics app)"
CC = ["magnuscarlsen", "hikaru", "fabianocaruana", "javokhir_sindarov05", "chesswarrior7197", "gmwso",
      "rpragchess", "vincentkeymer", "firouzja2003", "anishgiri", "arjunerigaisi", "amintabatabaei", "levonaronian"]
LI = ["DrNykterstein", "VincentKeymer2004", "alireza2003", "AnishGiri", "Anand"]

def get(url, accept):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(60)
                continue
            return None
        except Exception:
            time.sleep(3)
    return None

now = time.time()
since = now - 7 * 24 * 3600
months = sorted(set([time.strftime("%Y/%m", time.gmtime(since)), time.strftime("%Y/%m", time.gmtime(now))]))
for u in CC:
    out = []
    for m in months:
        raw = get("https://api.chess.com/pub/player/%s/games/%s" % (u, m), "application/json")
        time.sleep(1)
        if not raw:
            continue
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        for g in data.get("games", []):
            if g.get("end_time", 0) < since:
                continue
            if not g.get("rated") or g.get("rules") != "chess":
                continue
            if g.get("time_class") not in ("blitz", "rapid"):
                continue
            w = g["white"]["result"]
            b = g["black"]["result"]
            if w != "win" and b != "win":
                continue
            if w == "abandoned" or b == "abandoned":
                continue
            out.append(g.get("pgn", ""))
    with open("games/online/cc_%s.pgn" % u, "w") as fh:
        fh.write((chr(10) + chr(10)).join(out) + chr(10))
    print("chess.com", u, len(out), flush=True)
for u in LI:
    url = "https://lichess.org/api/games/user/%s?since=%d&until=%d&rated=true&perfType=blitz,rapid,classical&max=400&tags=true&moves=true" % (u, int(since * 1000), int(now * 1000))
    raw = get(url, "application/x-chess-pgn")
    time.sleep(2)
    text = raw.decode("utf-8", errors="ignore") if raw else ""
    with open("games/online/li_%s.pgn" % u, "w") as fh:
        fh.write(text)
    print("lichess", u, text.count("[Event "), flush=True)
print("FETCH DONE", flush=True)
