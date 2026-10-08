import glob, os, re, json, collections
import chess.pgn

HANDLE = {"magnuscarlsen": ("carlsen", "m"), "drnykterstein": ("carlsen", "m"), "hikaru": ("nakamura", "h"),
          "fabianocaruana": ("caruana", "f"), "javokhir_sindarov05": ("sindarov", "j"),
          "chesswarrior7197": ("abdusattorov", "n"), "gmwso": ("so", "w"), "rpragchess": ("praggnanandhaa", "r"),
          "vincentkeymer": ("keymer", "v"), "vincentkeymer2004": ("keymer", "v"), "firouzja2003": ("firouzja", "a"),
          "alireza2003": ("firouzja", "a"), "anishgiri": ("giri", "a"), "arjunerigaisi": ("erigaisi", "a"),
          "amintabatabaei": ("tabatabaei", "m"), "levonaronian": ("aronian", "l"), "anand": ("anand", "v")}

def norm(s):
    return re.sub("[^a-z]", "", (s or "").lower())

def elo(h, k):
    try:
        return int(h.get(k, "0"))
    except Exception:
        return 0

def parse_tc(tc):
    if not tc or tc == "-":
        return None
    t = tc.strip()
    if "/" in t:
        t = t.split("/", 1)[1]
    t = t.split(":")[0]
    base, inc = t, "0"
    if "+" in t:
        base, inc = t.split("+", 1)
    try:
        b = int(base)
        i = int(inc)
    except Exception:
        return None
    if "+" in tc and b <= 120:
        b = b * 60
    return b + 60 * i

def pid(name):
    low = (name or "").strip().lower()
    if low in HANDLE:
        return HANDLE[low]
    left, _, right = (name or "").partition(",")
    if "," in (name or ""):
        return (norm(left), norm(right)[:1])
    parts = (name or "").split()
    if len(parts) >= 2 and len(parts[-1]) <= 2:
        return (norm(" ".join(parts[:-1])), norm(parts[-1])[:1])
    return (norm(name), "")

html = open("/tmp/fide_men.html", encoding="utf-8", errors="ignore").read()
text = " ".join(re.sub("<[^>]+>", " ", html).split())
rows = re.findall("([0-9]+) ([A-Za-z .,-]+?) ([A-Z]{3}) ([0-9]{4}) ([0-9]{4}) ", text)
fide = {}
for r in rows:
    rank = int(r[0])
    name = r[1].strip()
    if "," in name:
        left, right = name.split(",", 1)
    else:
        parts = name.split()
        left, right = parts[0], " ".join(parts[1:])
    fide[(norm(left), norm(right)[:1])] = (rank, name, int(r[3]))
print("FIDE list entries:", len(fide))

cands = []
counts = collections.Counter()
for path in glob.glob("games/twic/*.pgn") + glob.glob("games/lichess/*.pgn") + glob.glob("games/online/*.pgn"):
    with open(path, encoding="utf-8", errors="ignore") as f:
        while True:
            pos = f.tell()
            h = chess.pgn.read_headers(f)
            if h is None:
                break
            if h.get("Result") not in ("1-0", "0-1"):
                continue
            if "abandon" in (h.get("Termination") or "").lower():
                continue
            tcv = parse_tc(h.get("TimeControl"))
            if tcv is not None and tcv < 180:
                continue
            if "bullet" in (h.get("Event") or "").lower():
                continue
            rw = fide.get(pid(h.get("White")))
            rb = fide.get(pid(h.get("Black")))
            rkw = rw[0] if rw else 1000
            rkb = rb[0] if rb else 1000
            best = min(rkw, rkb)
            if best >= 1000:
                continue
            we = elo(h, "WhiteElo")
            be = elo(h, "BlackElo")
            opp = be if rkw <= rkb else we
            if "/online/" in path:
                label = "online (Chess.com)" if "cc_" in os.path.basename(path) else "online (Lichess)"
            elif "/twic/" in path:
                label = "online (TWIC)" if (tcv is not None and tcv < 1200) else "over the board (TWIC)"
            else:
                label = "over the board (Lichess broadcast)"
            cands.append({"best": best, "opp": opp, "tc": tcv if tcv is not None else 5400, "path": path, "pos": pos,
                          "h": dict(h), "label": label, "wid": pid(h.get("White")), "bid": pid(h.get("Black"))})
            for rk in (rkw, rkb):
                if rk < 1000:
                    counts[rk] += 1

print("candidate games (decisive, 3 minutes or slower, with a top-100 player):", len(cands))
print("games per FIDE top-30 player:")
names = {v[0]: v[1] for v in fide.values()}
for rank in range(1, 31):
    print("  %d %s: %d" % (rank, names.get(rank, "?"), counts.get(rank, 0)))

cands.sort(key=lambda g: (g["best"], -g["opp"], -g["tc"]))
used = set()
picks = []
for g in cands:
    if g["wid"] in used or g["bid"] in used:
        continue
    with open(g["path"], encoding="utf-8", errors="ignore") as f:
        f.seek(g["pos"])
        game = chess.pgn.read_game(f)
    if len(list(game.mainline_moves())) < 30:
        continue
    picks.append((g, game))
    used.add(g["wid"])
    used.add(g["bid"])
    if len(picks) == 5:
        break

for old in glob.glob("games/picked/*"):
    os.remove(old)
print()
print("THE FIVE PICKS")
summary = []
for i, (g, game) in enumerate(picks, 1):
    h = g["h"]
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
    with open("games/picked/%02d.pgn" % i, "w") as out:
        out.write(game.accept(exporter) + chr(10) + chr(10))
    line = "%d. list position %d | %s (%s) vs %s (%s) | %s | %s | %s | tc %s | %s" % (
        i, g["best"], h.get("White"), h.get("WhiteElo"), h.get("Black"), h.get("BlackElo"),
        h.get("Result"), g["label"], h.get("Date"), h.get("TimeControl"), h.get("Event"))
    print(line)
    summary.append(line)
with open("picks.txt", "w") as fh:
    fh.write(chr(10).join(summary))
