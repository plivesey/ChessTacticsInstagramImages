import argparse, datetime, json, os, re, shutil, subprocess, sys, time
import chess, chess.pgn, chess.engine

ROOT = os.path.expanduser("~/chess-tactics/tacticoftheweek")
REPO = os.path.expanduser("~/chess-tactics/tacticoftheday/repo")
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import find_tactics as F

MAX_GAMES = 100
MIN_LEN = 3
STOP_AFTER = 2
RAW = "https://raw.githubusercontent.com/plivesey/ChessTacticsInstagramImages/main/weekly_videos/"
HASHTAGS = "#chess #chesstactics #tacticoftheweek #chesspuzzle #chessplayer #chesstraining #learnchess #chesslovers"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def norm(s):
    return re.sub("[^a-z]", "", (s or "").lower())[:8]


def nice_surname(n):
    n = (n or "").strip()
    if "," in n:
        return n.split(",", 1)[0].strip()
    return n


def nice_date(d):
    try:
        dt = datetime.datetime.strptime(d, "%Y.%m.%d")
        return dt.strftime("%b %d").replace(" 0", " ")
    except Exception:
        return d or ""


def tour_names():
    out = {}
    try:
        for line in open("/tmp/lichess_bc.ndjson"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            for r in d.get("rounds", []):
                out[r["id"]] = d.get("tour", {}).get("name")
    except Exception:
        pass
    return out


def event_name(h):
    site = h.get("Site", "") or ""
    if "lichess.org/broadcast" in site:
        m = re.search("round-[0-9]+/([A-Za-z0-9]+)/", site)
        name = tour_names().get(m.group(1)) if m else None
        if name:
            return name.split(" | ")[0].strip()
        try:
            return site.split("/broadcast/")[1].split("/")[0].replace("-", " ").title()
        except Exception:
            return "Lichess"
    if "chess.com" in site.lower():
        return "Chess.com"
    if "lichess.org" in site.lower():
        return "Lichess"
    return (h.get("Event") or "").strip()


def build_caption(h, chain):
    white_won = chain["winner"] == "white"
    w = h.get("White") if white_won else h.get("Black")
    l = h.get("Black") if white_won else h.get("White")
    ev = event_name(h)
    if ev in ("Chess.com", "Lichess"):
        where = "on " + ev
    else:
        where = "at the " + ev if ev else "over the board"
    lines = [
        "♟️ TACTIC OF THE WEEK: %s vs %s" % (nice_surname(w), nice_surname(l)),
        "",
        "%s to move and win! Pause the video and find it before the solution plays." % chain["winner"].capitalize(),
        "",
        "Played %s %s." % (nice_date(h.get("Date")), where),
        "",
        "Want more? Download Chess Tactics & Lessons from the Apple App Store for unlimited free tactics → link in bio",
        "",
        HASHTAGS,
    ]
    return chr(10).join(lines)


def git_publish(msg):
    for attempt in range(2):
        for c in (["git", "-C", REPO, "pull", "--rebase", "--autostash", "origin", "main"],
                  ["git", "-C", REPO, "add", "weekly_videos"],
                  ["git", "-C", REPO, "commit", "-m", msg]):
            r = subprocess.run(c, capture_output=True, text=True)
            log(" ".join(c[3:5]), r.returncode, (r.stdout + r.stderr).strip()[-150:])
        r = subprocess.run(["git", "-C", REPO, "push", "origin", "main"], capture_output=True, text=True)
        log("push", r.returncode, (r.stdout + r.stderr).strip()[-150:])
        if r.returncode == 0:
            return True
    return False


def write_meta(label, meta):
    os.makedirs(REPO + "/weekly_videos", exist_ok=True)
    with open("%s/weekly_videos/totw_%s.json" % (REPO, label), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)


def run(label):
    os.makedirs("week_run/results", exist_ok=True)
    engine = chess.engine.SimpleEngine.popen_uci(F.STOCKFISH)
    engine.configure({"Threads": F.THREADS, "Hash": F.HASH})
    seen = set()
    found = []
    state = {"analyzed": 0}

    def do_game(game):
        h = game.headers
        key = (norm(h.get("White")), norm(h.get("Black")), h.get("Date", ""), h.get("Result"))
        if key in seen:
            return False
        moves = list(game.mainline_moves())
        if len(moves) < 30:
            return False
        seen.add(key)
        winner, mv, chains, flagged, ndeep = F.process(engine, game)
        state["analyzed"] += 1
        b = game.board()
        san = []
        for m in moves:
            san.append(b.san(m))
            b.push(m)
        out = {"file": "", "headers": dict(h), "plies": len(moves), "san_moves": san,
               "uci_moves": [m.uci() for m in moves], "chains": chains}
        path = "week_run/results/%03d.json" % state["analyzed"]
        with open(path, "w") as fh:
            json.dump(out, fh, default=str)
        best = max([c["length"] for c in chains]) if chains else 0
        log("game %d: %s vs %s %s plies=%d chains=%d best_len=%d" % (state["analyzed"], h.get("White"), h.get("Black"), h.get("Result"), len(moves), len(chains), best))
        for i, c in enumerate(chains):
            if c["length"] >= MIN_LEN:
                found.append((c["length"], c["jump"], path, i))
        return True

    for i in range(1, 6):
        p = "games/picked_wi/%02d.pgn" % i
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8", errors="ignore") as f:
            game = chess.pgn.read_game(f)
        if game is not None:
            do_game(game)
    log("stage 1 (top five, no repeated players) done, tactics of %d+ moves: %d" % (MIN_LEN, len(found)))
    if not found and os.path.exists("pool_wi.json"):
        pool = json.load(open("pool_wi.json"))
        for g in pool:
            if state["analyzed"] >= MAX_GAMES or len(found) >= STOP_AFTER:
                break
            with open(g["path"], encoding="utf-8", errors="ignore") as f:
                f.seek(g["pos"])
                game = chess.pgn.read_game(f)
            if game is not None:
                do_game(game)
        log("stage 2 (down the ranked list, repeats allowed) done, analyzed %d, tactics: %d" % (state["analyzed"], len(found)))
    engine.quit()

    if not found:
        write_meta(label, {"status": "none", "date": label, "games_analyzed": state["analyzed"],
                           "reason": "No tactic of %d or more moves in %d games." % (MIN_LEN, state["analyzed"])})
        git_publish("Tactic of the Week %s: no tactic found" % label)
        log("RESULT none")
        return 0

    found.sort(reverse=True)
    length, jump, path, idx = found[0]
    data = json.load(open(path))
    h = data["headers"]
    chain = data["chains"][idx]
    caption = build_caption(h, chain)
    os.makedirs("/tmp/totw", exist_ok=True)
    out_mp4 = "/tmp/totw/week_%s.mp4" % label
    if os.path.exists(out_mp4):
        os.remove(out_mp4)
    log("rendering", path, "chain", idx, "length", length)
    r = subprocess.run([sys.executable, "render_game_video.py", path, "--chain", str(idx), "--out", out_mp4], capture_output=True, text=True)
    log("render", r.returncode, (r.stdout + r.stderr).strip()[-300:])
    if not os.path.exists(out_mp4):
        write_meta(label, {"status": "error", "date": label, "reason": "The video render failed.", "games_analyzed": state["analyzed"]})
        git_publish("Tactic of the Week %s: render failed" % label)
        log("RESULT error")
        return 1
    os.makedirs(REPO + "/weekly_videos", exist_ok=True)
    shutil.copy(out_mp4, "%s/weekly_videos/totw_%s.mp4" % (REPO, label))
    white_won = chain["winner"] == "white"
    meta = {"status": "ready", "date": label, "video_url": RAW + "totw_%s.mp4" % label, "caption": caption,
            "winner": h.get("White") if white_won else h.get("Black"),
            "loser": h.get("Black") if white_won else h.get("White"),
            "winner_color": chain["winner"], "fen": chain["start_fen"], "start_ply": chain["start_ply"],
            "solution_uci": chain["chain_uci"], "solution_san": chain["chain_san"], "tactic_length": chain["length"],
            "game_url": h.get("Link") or h.get("GameURL") or h.get("Site"), "event": event_name(h),
            "game_date": h.get("Date"), "games_analyzed": state["analyzed"],
            "created": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}
    write_meta(label, meta)
    ok = git_publish("Tactic of the Week %s" % label)
    log("RESULT ready" if ok else "RESULT push_failed")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    args = ap.parse_args()
    label = args.date
    if not label:
        from zoneinfo import ZoneInfo
        label = datetime.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    try:
        sys.exit(run(label))
    except Exception as e:
        log("RESULT error", repr(e))
        try:
            write_meta(label, {"status": "error", "date": label, "reason": repr(e)})
            git_publish("Tactic of the Week %s: error" % label)
        except Exception:
            pass
        sys.exit(1)
