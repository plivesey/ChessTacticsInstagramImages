#!/usr/bin/env python3
import argparse, datetime, glob, json, os, subprocess, sys, wave
import numpy as np
import chess
from PIL import Image, ImageDraw, ImageFont

DAY_DIR = os.path.expanduser("~/chess-tactics/tacticoftheday")
sys.path.insert(0, DAY_DIR)
import render_tactic_video as R

SR = 44100
FPS = R.FPS
PLAYERS_Y = R.BOARD_Y + R.BOARD_PX + 20
COPY_GAP = 20
TITLE_GAP = 8
COPY_Y = 0
FAST_VOL = 0.45
FAST_HOLD_AVG = 0.15


def fast_hold(p):
    return 4 if p % 2 == 0 else 5
MAX_EXTEND = 8
CAPTION_MIN_GAP = 8
PIECE_VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
PIECE_NAME = {chess.QUEEN: "queen", chess.ROOK: "rook", chess.BISHOP: "bishop", chess.KNIGHT: "knight", chess.PAWN: "pawn"}
ORDER = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]


def nice_name(n):
    n = (n or "").strip()
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
        return (first + " " + last).strip()
    return n


def nice_date(d):
    try:
        dt = datetime.datetime.strptime(d, "%Y.%m.%d")
        return dt.strftime("%b %d, %Y").replace(" 0", " ")
    except Exception:
        return d or ""


def short_name(raw):
    raw = (raw or "").strip()
    if "," in raw:
        return raw.split(",", 1)[0].strip()
    toks = raw.split()
    if len(toks) >= 2:
        return toks[0] if len(toks[-1]) <= 2 else toks[-1]
    return raw


def counts_diff(board, color):
    d = {}
    for pt in PIECE_VAL:
        d[pt] = len(board.pieces(pt, color)) - len(board.pieces(pt, not color))
    return d


def material_pts(board, color):
    d = counts_diff(board, color)
    return sum(PIECE_VAL[pt] * d[pt] for pt in d)


def piece_phrase(n, pt):
    name = PIECE_NAME[pt]
    if n == 1:
        return "a " + name
    return "%d %ss" % (n, name)


def join_phrases(items):
    parts = [piece_phrase(n, pt) for pt, n in items]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def material_text(color_name, diff):
    pos = [(pt, diff[pt]) for pt in ORDER if diff[pt] > 0]
    neg = [(pt, -diff[pt]) for pt in ORDER if diff[pt] < 0]
    if not pos and not neg:
        return "Material is level"
    if pos and not neg:
        return "%s is up %s" % (color_name, join_phrases(pos))
    if pos and neg:
        return "%s is up %s for %s" % (color_name, join_phrases(pos), join_phrases(neg))
    return "%s is down %s" % (color_name, join_phrases(neg))


def tactic_text(color, opp, net, captured, mate):
    if mate:
        return "%s delivers checkmate with this combination" % color
    if chess.QUEEN in captured and net >= 1:
        return "%s wins %s%ss queen with this combination" % (color, opp, chr(39))
    if chess.ROOK in captured and net >= 2:
        return "%s wins a rook with this combination" % color
    if net >= 3:
        return "%s wins %d points of material with this combination" % (color, net)
    if net >= 1:
        return "%s wins material with this combination" % color
    return "%s gets a winning position with this combination" % color


def lines_overlay(lines, width, height, size):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(R.FONT_PATH, size)
    heights = []
    for ln in lines:
        bb = draw.textbbox((0, 0), ln, font=font)
        heights.append(bb[3] - bb[1])
    total = sum(heights) + 14 * (len(lines) - 1)
    y = (height - total) // 2
    for ln, h in zip(lines, heights):
        bb = draw.textbbox((0, 0), ln, font=font)
        x = (width - (bb[2] - bb[0])) // 2
        draw.text((x, y), ln, font=font, fill=R.BANNER_FG)
        y += h + 14
    return img


def tight_lines_overlay(lines, width, size):
    probe = Image.new("RGBA", (width, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(R.FONT_PATH, size)
    boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    gap = 14
    total = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1)
    img = Image.new("RGBA", (width, total), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img)
    y = 0
    for ln, b in zip(lines, boxes):
        x = (width - (b[2] - b[0])) // 2 - b[0]
        d2.text((x, y - b[1]), ln, font=font, fill=R.BANNER_FG)
        y += (b[3] - b[1]) + gap
    return img


def tight_wrapped_overlay(text, width, max_text_width, size):
    probe = Image.new("RGBA", (width, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(R.FONT_PATH, size)
    lines = []
    cur = ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        bb = draw.textbbox((0, 0), trial, font=font)
        if bb[2] - bb[0] <= max_text_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    gap = 10
    total = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1)
    img = Image.new("RGBA", (width, total), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img)
    y = 0
    for ln, b in zip(lines, boxes):
        x = (width - (b[2] - b[0])) // 2 - b[0]
        d2.text((x, y - b[1]), ln, font=font, fill=R.BANNER_FG)
        y += (b[3] - b[1]) + gap
    return img


class Writer:
    def __init__(self, path):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "%dx%d" % (R.CANVAS_W, R.CANVAS_H), "-r", str(FPS), "-i", "-",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "2",
               "-x264-params", "threads=2:lookahead_threads=1", "-pix_fmt", "yuv420p", path]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        self.frames = 0

    def write(self, img, repeat=1):
        data = img.convert("RGB").tobytes()
        for _ in range(repeat):
            self.p.stdin.write(data)
        self.frames += repeat

    def close(self):
        self.p.stdin.close()
        self.p.wait()


BASE = None
WRITER = None
EVENTS = []


def compose(board_img, banner_img):
    c = BASE.copy()
    c.paste(board_img, (R.BOARD_X, R.BOARD_Y), board_img)
    if banner_img is not None:
        c.paste(banner_img, (0, COPY_Y), banner_img)
    return c


def animate(board, move, orientation, slide_frames, hold_frames, banner, vol):
    moving = board.piece_at(move.from_square)
    castling = board.is_castling(move)
    cap_sq = None
    if board.is_en_passant(move):
        cap_sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    elif (not castling) and board.piece_at(move.to_square) is not None:
        cap_sq = move.to_square
    backdrop = board.copy()
    backdrop.remove_piece_at(move.from_square)
    movers = [(R.render_piece_png(moving), move.from_square, move.to_square)]
    if castling:
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
        rf = chess.square(7 if kingside else 0, rank)
        rt = chess.square(5 if kingside else 3, rank)
        rook = board.piece_at(rf)
        backdrop.remove_piece_at(rf)
        movers.append((R.render_piece_png(rook), rf, rt))
    cap_img = None
    cap_px = None
    if cap_sq is not None:
        cap_piece = backdrop.piece_at(cap_sq)
        backdrop.remove_piece_at(cap_sq)
        cap_img = R.render_piece_png(cap_piece)
        cap_px = R.square_topleft_px(cap_sq, orientation)
    base_img = R.render_board_png(backdrop, orientation, lastmove=None)
    spans = []
    for img, f, t in movers:
        sx, sy = R.square_topleft_px(f, orientation)
        ex, ey = R.square_topleft_px(t, orientation)
        spans.append((img, sx, sy, ex, ey))
    for i in range(slide_frames):
        t = R.ease((i + 1) / slide_frames)
        fb = base_img.copy()
        if cap_img is not None and t < R.CAPTURE_HOLD_FRACTION:
            fb.paste(cap_img, (int(round(cap_px[0])), int(round(cap_px[1]))), cap_img)
        for img, sx, sy, ex, ey in spans:
            fb.paste(img, (int(round(sx + (ex - sx) * t)), int(round(sy + (ey - sy) * t))), img)
        WRITER.write(compose(fb, banner))
    EVENTS.append((WRITER.frames / float(FPS), vol))
    board.push(move)
    if hold_frames > 0:
        final = R.render_board_png(board, orientation, lastmove=move)
        WRITER.write(compose(final, banner), repeat=hold_frames)


def decode(path):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], stdout=subprocess.PIPE)
    return np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).copy()


def build_audio(events, total_seconds, sfx_files, music_path, fade_in, out_wav):
    n = int((total_seconds + 0.5) * SR)
    mix = np.zeros((n, 2), dtype=np.float32)
    cache = {}
    for i, (t, vol) in enumerate(events):
        if not sfx_files:
            break
        path = sfx_files[i % len(sfx_files)]
        if path not in cache:
            cache[path] = decode(path)
        clip = cache[path] * vol
        s = int(t * SR)
        e = min(n, s + len(clip))
        if s < n:
            mix[s:e] += clip[:e - s]
    if music_path:
        m = decode(music_path)
        if len(m) < n:
            m = np.tile(m, (n // len(m) + 1, 1))
        m = m[:n].copy()
        fi = int(fade_in * SR)
        if fi > 0:
            m[:fi] *= np.linspace(0, 1, fi)[:, None]
        end_music = int(total_seconds * SR)
        fo = int(R.MUSIC_FADE_OUT * SR)
        m[end_music - fo:end_music] *= np.linspace(1, 0, fo)[:, None]
        m[end_music:] = 0
        mix += m * R.MUSIC_VOLUME
    mix = np.clip(mix, -1.0, 1.0)
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


LOGO_PATH = os.path.expanduser("~/chess-tactics/tacticoftheweek/assets/logo.png")
END_TEXT = "Download Chess Tactics & Lessons from the Apple App Store for unlimited free tactics"


def build_end_card():
    card = Image.new("RGBA", (R.CANVAS_W, R.CANVAS_H), R.BG_COLOR)
    size = 560
    if os.path.exists(LOGO_PATH):
        logo = Image.open(LOGO_PATH).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        big = Image.new("L", (size * 4, size * 4), 0)
        ImageDraw.Draw(big).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
        mask = big.resize((size, size), Image.Resampling.LANCZOS)
        card.paste(logo, ((R.CANVAS_W - size) // 2, 480), mask)
    text = R.make_text_overlay(END_TEXT, R.CANVAS_W, 420, 56)
    card.paste(text, (0, 1120), text)
    return card


def main():
    global BASE, WRITER, COPY_Y
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--chain", type=int, default=-1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=95.0)
    ap.add_argument("--music-file", default=None)
    ap.add_argument("--no-music", action="store_true")
    args = ap.parse_args()

    data = json.load(open(args.results))
    h = data["headers"]
    moves = [chess.Move.from_uci(u) for u in data["uci_moves"]]
    chains = data["chains"]
    if args.chain >= 0:
        chain = chains[args.chain]
    else:
        chain = max(chains, key=lambda c: (c["length"], c["jump"]))
    winner = chess.WHITE if chain["winner"] == "white" else chess.BLACK
    orientation = winner
    color = chain["winner"].capitalize()
    opp_color = "Black" if winner == chess.WHITE else "White"
    n = len(moves)
    s = chain["start_ply"]

    start_board = chess.Board(h["FEN"]) if "FEN" in h else chess.Board()
    tmp = start_board.copy()
    cap_flags, chk_flags, mats, diffs, mates = [], [], [], [], []
    for mv in moves:
        cap_flags.append(tmp.is_capture(mv))
        chk_flags.append(tmp.gives_check(mv))
        tmp.push(mv)
        mats.append(material_pts(tmp, winner))
        diffs.append(counts_diff(tmp, winner))
        mates.append(tmp.is_checkmate())

    tac_end = min(chain["last_ply"] + 1, n - 1)
    ext = 0
    while tac_end + 1 < n and ext < MAX_EXTEND and (cap_flags[tac_end + 1] or chk_flags[tac_end + 1]):
        tac_end += 1
        ext += 1
    if tac_end + 1 < n and ((tac_end % 2 == 0) == (winner == chess.WHITE)):
        tac_end += 1

    tmp = start_board.copy()
    captured = []
    for p, mv in enumerate(moves):
        if s <= p <= tac_end and tmp.turn == winner and cap_flags[p]:
            cp = tmp.piece_at(mv.to_square)
            captured.append(cp.piece_type if cp else chess.PAWN)
        tmp.push(mv)
    start_pts = mats[s - 1] if s > 0 else 0
    net = mats[tac_end] - start_pts
    ttext = tactic_text(color, opp_color, net, captured, mates[tac_end])
    print("tactic plies", s, "to", tac_end, "(extended by %d)" % ext, "net", net, "text:", ttext, flush=True)

    fixed = 0.5 + 4.0 + 3.0 + 4.0
    tac_time = 0.0
    for p in range(s, tac_end + 1):
        mover_is_winner = ((p % 2 == 0) == (winner == chess.WHITE))
        tac_time += 0.6 + (0.3 if mover_is_winner else 0.9)
    n_fast = s + max(0, n - 1 - tac_end)
    per_ply = (args.budget - fixed - tac_time) / max(1, n_fast)
    fast_seconds = max(0.12, min(0.3, per_ply - FAST_HOLD_AVG))
    fast_frames = max(3, int(round(fast_seconds * FPS)))
    print("plies", n, "fast frames per move", fast_frames, flush=True)

    wname = nice_name(h.get("White"))
    bname = nice_name(h.get("Black"))
    lines = ["White: %s (%s)" % (wname, h.get("WhiteElo", "?")),
             "Black: %s (%s)" % (bname, h.get("BlackElo", "?")),
             nice_date(h.get("Date", ""))]
    title = R.make_tight_line_overlay("Tactic of the Week", R.CANVAS_W, 64)
    players = tight_lines_overlay(lines, R.CANVAS_W, 44)
    COPY_Y = PLAYERS_Y + players.height + COPY_GAP
    print("layout: title y", R.BOARD_Y - TITLE_GAP - title.height, "board y", R.BOARD_Y, "players y", PLAYERS_Y, "players h", players.height, "copy y", COPY_Y, flush=True)
    BASE = Image.new("RGBA", (R.CANVAS_W, R.CANVAS_H), R.BG_COLOR)
    BASE.paste(title, (0, R.BOARD_Y - TITLE_GAP - title.height), title)
    BASE.paste(players, (0, PLAYERS_Y), players)

    def banner_text(text):
        return tight_wrapped_overlay(text, R.CANVAS_W, R.BOARD_PX - 20, 44)

    pause_banner = banner_text("%s to move and win. Pause now to solve it yourself" % color)
    intro_banner = banner_text("Here" + chr(39) + "s how the game started")
    result_banner = banner_text(ttext)
    winner_name = wname if winner == chess.WHITE else bname
    end_banner = banner_text("%s wins in %d moves" % (winner_name, (n + 1) // 2))

    tmp_video = args.out + ".video.mp4"
    tmp_wav = args.out + ".audio.wav"
    WRITER = Writer(tmp_video)
    board = start_board.copy()

    WRITER.write(compose(R.render_board_png(board, orientation), None), repeat=int(0.5 * FPS))
    for p in range(0, s):
        animate(board, moves[p], orientation, fast_frames, fast_hold(p), intro_banner, FAST_VOL)
    pause_img = R.render_board_png(board, orientation, lastmove=moves[s - 1] if s > 0 else None)
    WRITER.write(compose(pause_img, pause_banner), repeat=4 * FPS)
    for p in range(s, tac_end + 1):
        hold = 0.3 if board.turn == winner else 0.9
        animate(board, moves[p], orientation, int(0.6 * FPS), int(hold * FPS), None, 1.0)
    result_img = R.render_board_png(board, orientation, lastmove=moves[tac_end])
    WRITER.write(compose(result_img, result_banner), repeat=3 * FPS)

    finish_banner = banner_text("Let" + chr(39) + "s see how %s finished off the game" % short_name(h.get("White") if winner == chess.WHITE else h.get("Black")))
    current_banner = finish_banner
    reported_pts = mats[tac_end]
    last_update = tac_end + 4
    for p in range(tac_end + 1, n):
        mover_is_winner = ((p % 2 == 0) == (winner == chess.WHITE))
        animate(board, moves[p], orientation, fast_frames, fast_hold(p), current_banner, FAST_VOL)
        if p - last_update < CAPTION_MIN_GAP:
            continue
        if moves[p].promotion and mover_is_winner:
            current_banner = banner_text("%s promotes a pawn to a %s" % (color, PIECE_NAME[moves[p].promotion]))
            reported_pts = mats[p]
            last_update = p
            continue
        settled = (p + 2 >= n) or (mats[p + 1] == mats[p] and mats[p + 2] == mats[p])
        if abs(mats[p] - reported_pts) >= 2 and settled and p + 1 < n:
            current_banner = banner_text(material_text(color, diffs[p]))
            reported_pts = mats[p]
            last_update = p
    final_img = R.render_board_png(board, orientation, lastmove=moves[-1])
    WRITER.write(compose(final_img, end_banner), repeat=4 * FPS)
    last_frame = compose(final_img, end_banner)
    card = build_end_card()
    for i in range(1, FPS + 1):
        WRITER.write(Image.blend(last_frame, card, i / float(FPS)))
    WRITER.write(card, repeat=int(4.5 * FPS))
    total_seconds = WRITER.frames / float(FPS)
    WRITER.close()
    print("video frames", WRITER.frames, "seconds", round(total_seconds, 1), flush=True)

    sfx_files = sorted(glob.glob(os.path.join(DAY_DIR, "sfx", "*.mp3")))
    music_path = None
    fade_in = R.MUSIC_FADE_IN
    if not args.no_music:
        if args.music_file:
            music_path = args.music_file
        else:
            tracks = sorted(glob.glob(os.path.join(DAY_DIR, "music", "*.mp3")))
            if tracks:
                music_path = tracks[datetime.date.today().toordinal() % len(tracks)]
        if music_path and os.path.exists(music_path + ".fadein"):
            fade_in = float(open(music_path + ".fadein").read().strip())
    print("music", music_path, "sounds", len(EVENTS), flush=True)
    build_audio(EVENTS, total_seconds, sfx_files, music_path, fade_in, tmp_wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp_video, "-i", tmp_wav,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", args.out], check=True)
    os.remove(tmp_video)
    os.remove(tmp_wav)
    print("WROTE", args.out, flush=True)


main()
