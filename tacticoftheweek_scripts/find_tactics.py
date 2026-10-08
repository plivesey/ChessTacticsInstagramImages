import sys, json, glob, os, time
import chess, chess.pgn, chess.engine

STOCKFISH = "/usr/games/stockfish"
FAST_DEPTH = 12
DEEP_DEPTH = 20
THREADS = 1
HASH = 256
BEST_MIN = 250
SECOND_MAX = 120
GAP_MIN = 250
JUMP_MIN = 250
LOOSE_BEST = 100
LOOSE_SECOND = 300
LOOSE_JUMP = 100
SKIP_PLIES = 10
CAP = 10000
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}

def material(board, color):
    total = 0
    for pt, v in VALUES.items():
        total += v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color)))
    return total

def score_cp(info, color):
    return info["score"].pov(color).score(mate_score=CAP)

def analyse_pos(engine, board, mv, ply, depth, token=None):
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2, game=token)
    first = infos[0]
    turn = board.turn
    s1 = score_cp(first, turn)
    s2 = score_cp(infos[1], turn) if len(infos) > 1 else None
    best = first["pv"][0].uci() if first.get("pv") else None
    return {"ply": ply, "turn": turn, "s1": s1, "s2": s2, "best": best,
            "played": mv.uci(), "san": board.san(mv), "fen": board.fen()}

def ok(p):
    return (p["s2"] is not None and p["s1"] >= BEST_MIN and p["s2"] <= SECOND_MAX
            and p["s1"] - p["s2"] >= GAP_MIN and p["best"] == p["played"])

def process(engine, game):
    result = game.headers.get("Result")
    winner = chess.WHITE if result == "1-0" else chess.BLACK
    moves = list(game.mainline_moves())
    boards = []
    b = game.board()
    for mv in moves:
        boards.append(b.copy())
        b.push(mv)
    boards.append(b.copy())
    n = len(moves)
    token = object()
    fast = {}
    for ply in range(SKIP_PLIES - 1, n):
        fast[ply] = analyse_pos(engine, boards[ply], moves[ply], ply, FAST_DEPTH, token)
    deep = {}
    def get_deep(ply):
        if ply not in deep:
            deep[ply] = analyse_pos(engine, boards[ply], moves[ply], ply, DEEP_DEPTH, token)
        return deep[ply]
    chains = []
    flagged = 0
    ply = SKIP_PLIES
    while ply < n:
        f = fast.get(ply)
        fp = fast.get(ply - 1)
        if f is not None and fp is not None and f["turn"] == winner:
            fast_jump = f["s1"] + fp["s1"]
            if f["s1"] >= LOOSE_BEST and f["s2"] is not None and f["s2"] <= LOOSE_SECOND and fast_jump >= LOOSE_JUMP:
                flagged += 1
                d = get_deep(ply)
                dp = get_deep(ply - 1)
                e_prev = -dp["s1"]
                jump = d["s1"] - e_prev
                if ok(d) and jump >= JUMP_MIN:
                    chain = [ply]
                    j = ply + 2
                    while j < n and ok(get_deep(j)):
                        chain.append(j)
                        j += 2
                    last = chain[-1]
                    end_ply = min(last + 2, n)
                    chains.append({
                        "start_ply": ply,
                        "length": len(chain),
                        "winner": "white" if winner == chess.WHITE else "black",
                        "e_prev": e_prev,
                        "s1_start": d["s1"],
                        "s2_start": d["s2"],
                        "jump": jump,
                        "s1_end": deep[last]["s1"],
                        "start_fen": d["fen"],
                        "chain_plies": chain,
                        "chain_san": [deep[c]["san"] for c in chain],
                        "chain_uci": [deep[c]["played"] for c in chain],
                        "last_ply": last,
                        "end_ply": end_ply,
                        "material_start": material(boards[ply], winner),
                        "material_end": material(boards[end_ply], winner),
                    })
                    ply = last + 1
                    continue
        ply += 1
    return winner, moves, chains, flagged, len(deep)

def main():
    files = sys.argv[1:] or sorted(glob.glob("games/selected/*.pgn"))
    os.makedirs("results", exist_ok=True)
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH)
    engine.configure({"Threads": THREADS, "Hash": HASH})
    lines = []
    for path in files:
        t0 = time.time()
        with open(path, encoding="utf-8", errors="ignore") as f:
            game = chess.pgn.read_game(f)
        winner, moves, chains, flagged, ndeep = process(engine, game)
        b = game.board()
        san = []
        for mv in moves:
            san.append(b.san(mv))
            b.push(mv)
        out = {"file": path, "headers": dict(game.headers), "plies": len(moves),
               "san_moves": san, "uci_moves": [m.uci() for m in moves], "chains": chains}
        name = os.path.basename(path).replace(".pgn", "")
        with open("results/%s.json" % name, "w") as fh:
            json.dump(out, fh, default=str)
        best = max(chains, key=lambda c: (c["length"], c["jump"])) if chains else None
        h = game.headers
        line = "%s %s vs %s %s plies=%d flagged=%d deep=%d chains=%d best_len=%s best_jump=%s seconds=%d" % (
            name, h.get("White"), h.get("Black"), h.get("Result"), len(moves), flagged, ndeep, len(chains),
            best["length"] if best else "-", best["jump"] if best else "-", time.time() - t0)
        print(line, flush=True)
        lines.append(line)
    engine.quit()
    with open("results/summary.txt", "w") as fh:
        fh.write(chr(10).join(lines))
    print("ALL DONE", flush=True)

if __name__ == "__main__":
    main()
