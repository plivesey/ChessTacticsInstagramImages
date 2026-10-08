import json, re, sys, time, urllib.request, urllib.parse, urllib.error

UA = "tactic-of-the-week/1.0 (chess tactics app)"
CC_HINTS = {
    "carlsen": ["MagnusCarlsen"], "nakamura": ["Hikaru"], "caruana": ["FabianoCaruana"],
    "abdusattorov": ["ChessWarrior7197"], "so": ["GMWSO"], "giri": ["AnishGiri"],
    "firouzja": ["Firouzja2003"], "gukesh": ["GukeshDommaraju"], "praggnanandhaa": ["rpragchess"],
    "keymer": ["VincentKeymer2004"], "erigaisi": ["ArjunErigaisi"], "duda": ["Jan-KrzysztofDuda"],
    "aronian": ["LevonAronian"], "dominguez": ["LeinierDominguez"],
}
LI_HINTS = {"carlsen": ["DrNykterstein"], "firouzja": ["alireza2003"]}

def get(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(40)
                continue
            return None
        except Exception:
            time.sleep(3)
    return None

def norm(s):
    return re.sub("[^a-z]", "", (s or "").lower())

html = open("/tmp/fide_men.html", encoding="utf-8", errors="ignore").read()
text = " ".join(re.sub("<[^>]+>", " ", html).split())
rows = re.findall("([0-9]+) ([A-Za-z .,-]+?) ([A-Z]{3}) ([0-9]{4}) ([0-9]{4}) ", text)
players = []
for r in rows:
    rank = int(r[0])
    if rank > 20:
        continue
    name = r[1].strip()
    if "," in name:
        last, first = [x.strip() for x in name.split(",", 1)]
    else:
        parts = name.split()
        last, first = parts[0], " ".join(parts[1:])
    players.append({"rank": rank, "name": name, "rating": int(r[3]), "last": last, "first": first})
print("players:", len(players), flush=True)

gm_data = get("https://api.chess.com/pub/titled/GM")
gms = gm_data.get("players", []) if gm_data else []
print("chess.com GMs:", len(gms), flush=True)

result = []
for p in players:
    ln = norm(p["last"])
    fn = norm(p["first"])
    cands = list(CC_HINTS.get(ln, []))
    for u in gms:
        ul = u.lower()
        if len(ln) >= 5:
            ok = ln in ul
        else:
            ok = ln in ul and fn[:4] in ul
        if ok and u not in cands:
            cands.append(u)
    cc = []
    for c in cands[:8]:
        prof = get("https://api.chess.com/pub/player/%s" % c.lower())
        time.sleep(0.25)
        if not prof:
            continue
        pname = prof.get("name", "")
        if ln in norm(pname):
            cc.append({"username": prof.get("username", c), "name": pname, "title": prof.get("title"),
                       "verified": prof.get("verified"), "followers": prof.get("followers"),
                       "last_online": prof.get("last_online")})
    li = []
    seen = set()
    terms = [p["last"]]
    if fn:
        terms.append(norm(p["first"].split()[0]) + ln)
    ids = list(LI_HINTS.get(ln, []))
    for t in terms:
        data = get("https://lichess.org/api/player/autocomplete?term=%s&object=true&nb=10" % urllib.parse.quote(t))
        time.sleep(1.1)
        if data and isinstance(data, dict):
            for u in data.get("result", []):
                if u.get("title") and u.get("id") not in ids:
                    ids.append(u["id"])
    for uid in ids[:6]:
        if uid.lower() in seen:
            continue
        seen.add(uid.lower())
        prof = get("https://lichess.org/api/user/%s" % uid.lower())
        time.sleep(1.1)
        if not prof:
            continue
        pr = prof.get("profile", {}) or {}
        real = ((pr.get("firstName") or "") + " " + (pr.get("lastName") or "")).strip() or pr.get("realName", "")
        li.append({"id": prof.get("id"), "username": prof.get("username"), "title": prof.get("title"),
                   "real_name": real, "name_matches": ln in norm(real), "games": prof.get("count", {}).get("all")})
    entry = {"rank": p["rank"], "name": p["name"], "rating": p["rating"], "chesscom": cc, "lichess": li}
    result.append(entry)
    print(p["rank"], p["name"], "| chess.com:", [(c["username"], c["verified"]) for c in cc], "| lichess:", [(l["username"], l["name_matches"]) for l in li], flush=True)
    with open("handles.json", "w") as fh:
        json.dump(result, fh, indent=1)
print("HANDLES DONE", flush=True)
