import json, os, sys, re, time
import chess, chess.pgn, chess.engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_tactics as F

MAX_GAMES = 60
TARGET = 2
pool = json.load(open("pool_wi.json"))
os.makedirs("walk3/results", exist_ok=True)
engine = chess.engine.SimpleEngine.popen_uci(F.STOCKFISH)
engine.configure({"Threads": F.THREADS, "Hash": F.HASH})

def norm(s):
    return re.sub("[^a-z]", "", (s or "").lower())[:8]

seen = set()
analyzed = 0
found = 0
print("pool size", len(pool), flush=True)
for g in pool:
    h = g["h"]
    key = (norm(h.get("White")), norm(h.get("Black")), h.get("Date", ""), h.get("Result"))
    if key in seen:
        continue
    seen.add(key)
    with open(g["path"], encoding="utf-8", errors="ignore") as f:
        f.seek(g["pos"])
        game = chess.pgn.read_game(f)
    moves = list(game.mainline_moves())
    if len(moves) < 30:
        continue
    t0 = time.time()
    try:
        winner, mv, chains, flagged, ndeep = F.process(engine, game)
    except Exception as e:
        print("error", e, flush=True)
        continue
    analyzed += 1
    b = game.board()
    san = []
    for m in moves:
        san.append(b.san(m))
        b.push(m)
    out = {"file": g["path"], "headers": dict(game.headers), "plies": len(moves),
           "san_moves": san, "uci_moves": [m.uci() for m in moves], "chains": chains}
    with open("walk3/results/%03d.json" % analyzed, "w") as fh:
        json.dump(out, fh, default=str)
    best = max(chains, key=lambda c: (c["length"], c["jump"])) if chains else None
    print("%03d list#%s %s (%s) vs %s (%s) %s %s plies=%d chains=%d best_len=%s best_jump=%s secs=%d" % (
        analyzed, g["best"], h.get("White"), h.get("WhiteElo"), h.get("Black"), h.get("BlackElo"),
        h.get("Result"), h.get("Date"), len(moves), len(chains),
        best["length"] if best else "-", best["jump"] if best else "-", time.time() - t0), flush=True)
    if best and best["length"] >= 3:
        found += 1
    if found >= TARGET or analyzed >= MAX_GAMES:
        break
engine.quit()
print("WALK DONE analyzed", analyzed, "with tactics", found, flush=True)
