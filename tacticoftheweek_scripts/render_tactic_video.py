#!/usr/bin/env python3
"""
Usage:
  render_tactic_video.py <FEN> <output.mp4> --solution e2e4,e7e5,... \
      [--last-move d2d3] [--orientation white|black] \
      [--pause-text "Pause now to solve it yourself"] [--title-text "Mate in 4"]

Renders a vertical (1080x1920) MP4:
  - Phase 1: starting position + a quick title above the board + pause text
    below the board (both on the same background color as the rest of the
    frame, no boxed-in look), held ~3s.
  - Phase 2: for each solution move, the moving piece slides from its start
    square to its end square (eased). A captured piece stays on the board
    until just before the mover arrives, instead of vanishing immediately.
    After an opponent reply (every 2nd move) the hold is longer so the
    viewer has time to follow the response before the next player move.
    A sound effect plays the instant each piece lands (round-robin through
    a folder of short CC0 chess-move sounds).
  - Phase 3: final position held for ~2.5s.

Known limitations (v1):
  - The slide is a straight pixel-space interpolation, so a knight move cuts
    across the board rather than hopping in an L shape.
  - Castling slides only the king; the rook snaps into place at the hold frame.
  - Coordinate labels are always off (chess.svg coordinates=False).
"""
import argparse
import datetime
import glob
import os
import shutil
import subprocess
import sys
import io

import chess
import chess.svg
import cairosvg
from PIL import Image, ImageDraw, ImageFont

SQUARE_SIZE_SVG = 45
FULL_SIZE_SVG = 8 * SQUARE_SIZE_SVG

CANVAS_W = 1080
CANVAS_H = 1920
BOARD_PX = 960
BANNER_H = 300
FPS = 30
PAUSE_SECONDS = 4.0
SLIDE_SECONDS = 0.6
HOLD_SECONDS_PLAYER = 0.3
HOLD_SECONDS_OPPONENT = 0.9
END_HOLD_SECONDS = 5.5
CAPTURE_HOLD_FRACTION = 0.85
BG_COLOR = (18, 18, 18, 255)
BANNER_FG = (255, 255, 255, 255)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SFX_DIR = os.path.join(SCRIPT_DIR, "sfx")
DEFAULT_MUSIC_DIR = os.path.join(SCRIPT_DIR, "music")
MUSIC_VOLUME = 0.22
MUSIC_FADE_IN = 0.6
MUSIC_FADE_OUT = 1.8

SCALE = BOARD_PX / FULL_SIZE_SVG
SQUARE_PX = SQUARE_SIZE_SVG * SCALE

BOARD_X = (CANVAS_W - BOARD_PX) // 2
BOARD_Y = (CANVAS_H - BANNER_H - BOARD_PX) // 2
TITLE_H = BOARD_Y
TURN_H = 100
PAUSE_H = 100
TURN_GAP = 20
PAUSE_GAP = 70
TITLE_GAP = 8


def ease(t):
    return t * t * (3 - 2 * t)


def square_topleft_px(square, orientation):
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    x = (file_index if orientation else 7 - file_index) * SQUARE_SIZE_SVG
    y = (7 - rank_index if orientation else rank_index) * SQUARE_SIZE_SVG
    return x * SCALE, y * SCALE


def render_board_png(board, orientation, lastmove=None):
    svg_data = chess.svg.board(
        board=board,
        orientation=orientation,
        lastmove=lastmove,
        size=FULL_SIZE_SVG,
        coordinates=False,
    )
    png_bytes = cairosvg.svg2png(
        bytestring=svg_data.encode("utf-8"),
        output_width=BOARD_PX,
        output_height=BOARD_PX,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def render_piece_png(piece):
    svg_data = chess.svg.piece(piece, size=int(round(SQUARE_PX)))
    png_bytes = cairosvg.svg2png(
        bytestring=svg_data.encode("utf-8"),
        output_width=int(round(SQUARE_PX)),
        output_height=int(round(SQUARE_PX)),
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def wrap_and_draw(draw, text, font, max_width, box_w, box_h):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    line_heights = []
    total_h = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_h += h + 10
    y = (box_h - total_h) // 2
    for line, h in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (box_w - w) // 2
        draw.text((x, y), line, font=font, fill=BANNER_FG)
        y += h + 10


def make_text_overlay(text, width, height, font_size):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return img
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, font_size)
    wrap_and_draw(draw, text, font, width - 120, width, height)
    return img


def make_tight_line_overlay(text, width, font_size):
    probe = Image.new("RGBA", (width, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    font = ImageFont.truetype(FONT_PATH, font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    h = bbox[3] - bbox[1]
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img)
    x = (width - (bbox[2] - bbox[0])) // 2 - bbox[0]
    d2.text((x, -bbox[1]), text, font=font, fill=BANNER_FG)
    return img


def make_line_overlay(text, width, height, max_font, max_text_width):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return img
    draw = ImageDraw.Draw(img)
    size = max_font
    while size > 28:
        font = ImageFont.truetype(FONT_PATH, size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_text_width:
            break
        size -= 2
    font = ImageFont.truetype(FONT_PATH, size)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (width - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (height - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=BANNER_FG)
    return img


def compose_frame(board_img, title_img=None, banner_img=None, turn_img=None):
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_COLOR)
    if title_img is not None:
        canvas.paste(title_img, (0, BOARD_Y - TITLE_GAP - title_img.height), title_img)
    canvas.paste(board_img, (BOARD_X, BOARD_Y), board_img)
    if turn_img is not None:
        canvas.paste(turn_img, (0, BOARD_Y + BOARD_PX + TURN_GAP), turn_img)
    if banner_img is not None:
        canvas.paste(banner_img, (0, BOARD_Y + BOARD_PX + TURN_GAP + TURN_H + PAUSE_GAP), banner_img)
    return canvas


def save_frame(img, frame_dir, index):
    path = os.path.join(frame_dir, "frame_%06d.png" % index)
    img.convert("RGB").save(path)
    return index + 1


def build_audio_track(landing_events, sfx_dir, total_frames, fps, out_path):
    """landing_events: list of (time_seconds, sfx_path). Mixes them into one
    audio file the same length as the video using adelay + amix."""
    if not landing_events:
        return None
    total_seconds = total_frames / float(fps)
    cmd = ["ffmpeg", "-y"]
    filter_parts = []
    for i, (_, sfx_path) in enumerate(landing_events):
        cmd += ["-i", sfx_path]
    for i, (t, _) in enumerate(landing_events):
        delay_ms = max(0, int(round(t * 1000)))
        filter_parts.append("[%d:a]adelay=%d:all=1[a%d]" % (i, delay_ms, i))
    mix_inputs = "".join("[a%d]" % i for i in range(len(landing_events)))
    filter_parts.append(
        "%samix=inputs=%d:duration=longest:normalize=0[aout]" % (mix_inputs, len(landing_events))
    )
    filter_complex = ";".join(filter_parts)
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", str(total_seconds + 1.0),
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fen")
    parser.add_argument("output")
    parser.add_argument("--solution", required=True)
    parser.add_argument("--last-move", default=None)
    parser.add_argument("--orientation", default="white", choices=["white", "black"])
    parser.add_argument("--pause-text", default="Pause now to solve it yourself")
    parser.add_argument("--title-text", default="")
    parser.add_argument("--heading-text", default="Tactic of the Day")
    parser.add_argument("--turn-text", default="")
    parser.add_argument("--sfx-dir", default=DEFAULT_SFX_DIR)
    parser.add_argument("--no-sfx", action="store_true")
    parser.add_argument("--music-dir", default=DEFAULT_MUSIC_DIR)
    parser.add_argument("--music-file", default=None)
    parser.add_argument("--no-music", action="store_true")
    args = parser.parse_args()

    orientation = chess.WHITE if args.orientation == "white" else chess.BLACK
    board = chess.Board(args.fen)
    last_move = chess.Move.from_uci(args.last_move) if args.last_move else None
    solution_moves = [chess.Move.from_uci(u) for u in args.solution.split(",") if u]

    sfx_files = []
    if not args.no_sfx and os.path.isdir(args.sfx_dir):
        sfx_files = sorted(glob.glob(os.path.join(args.sfx_dir, "*.mp3")))

    frame_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), "_frames_tmp")
    if os.path.exists(frame_dir):
        shutil.rmtree(frame_dir)
    os.makedirs(frame_dir)

    idx = 0
    landing_events = []
    title_overlay = make_tight_line_overlay(args.heading_text, CANVAS_W, 64) if args.heading_text else None
    if args.turn_text:
        turn_text = args.turn_text
    else:
        turn_text = "White to move" if board.turn == chess.WHITE else "Black to move"
    if args.title_text:
        turn_text = turn_text + " - " + args.title_text
    turn_overlay = make_line_overlay(turn_text, CANVAS_W, TURN_H, 52, BOARD_PX - 20)
    pause_banner = make_line_overlay(args.pause_text, CANVAS_W, PAUSE_H, 48, BOARD_PX - 20)

    start_board_img = render_board_png(board, orientation, lastmove=last_move)
    pause_frame = compose_frame(start_board_img, title_overlay, pause_banner, turn_overlay)
    for _ in range(int(PAUSE_SECONDS * FPS)):
        idx = save_frame(pause_frame, frame_dir, idx)

    slide_frame_count = max(1, int(SLIDE_SECONDS * FPS))
    final_frame = pause_frame

    for move_index, move in enumerate(solution_moves):
        is_opponent_move = (move_index % 2 == 1)
        hold_seconds = HOLD_SECONDS_OPPONENT if is_opponent_move else HOLD_SECONDS_PLAYER
        hold_frame_count = max(1, int(hold_seconds * FPS))

        moving_piece = board.piece_at(move.from_square)
        if moving_piece is None:
            raise ValueError("No piece at %s for move %s" % (chess.square_name(move.from_square), move.uci()))

        is_en_passant = board.is_en_passant(move)
        captured_square = None
        if is_en_passant:
            captured_square = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        elif board.piece_at(move.to_square) is not None:
            captured_square = move.to_square

        backdrop_board = board.copy()
        backdrop_board.remove_piece_at(move.from_square)
        captured_piece_obj = None
        captured_px = None
        if captured_square is not None:
            captured_piece_obj = backdrop_board.piece_at(captured_square)
            backdrop_board.remove_piece_at(captured_square)
            captured_px = square_topleft_px(captured_square, orientation)

        backdrop_img = render_board_png(backdrop_board, orientation, lastmove=None)
        piece_img = render_piece_png(moving_piece)
        captured_img = render_piece_png(captured_piece_obj) if captured_piece_obj else None

        start_x, start_y = square_topleft_px(move.from_square, orientation)
        end_x, end_y = square_topleft_px(move.to_square, orientation)

        for i in range(slide_frame_count):
            t = ease((i + 1) / slide_frame_count)
            cur_x = start_x + (end_x - start_x) * t
            cur_y = start_y + (end_y - start_y) * t
            frame_board = backdrop_img.copy()
            if captured_img is not None and t < CAPTURE_HOLD_FRACTION:
                frame_board.paste(captured_img, (int(round(captured_px[0])), int(round(captured_px[1]))), captured_img)
            frame_board.paste(piece_img, (int(round(cur_x)), int(round(cur_y))), piece_img)
            frame = compose_frame(frame_board, title_overlay, None, turn_overlay)
            idx = save_frame(frame, frame_dir, idx)

        if sfx_files:
            sfx_path = sfx_files[move_index % len(sfx_files)]
            landing_time = idx / float(FPS)
            landing_events.append((landing_time, sfx_path))

        board.push(move)
        final_board_img = render_board_png(board, orientation, lastmove=move)
        final_frame = compose_frame(final_board_img, title_overlay, None, turn_overlay)
        for _ in range(hold_frame_count):
            idx = save_frame(final_frame, frame_dir, idx)

    for _ in range(int(END_HOLD_SECONDS * FPS)):
        idx = save_frame(final_frame, frame_dir, idx)

    total_frames = idx
    print("Wrote %d frames to %s" % (total_frames, frame_dir))

    silent_video_path = os.path.join(os.path.dirname(os.path.abspath(args.output)), "_silent_tmp.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-threads", "2",
        "-framerate", str(FPS),
        "-i", os.path.join(frame_dir, "frame_%06d.png"),
        "-c:v", "libx264",
        "-threads", "2",
        "-x264-params", "threads=2:lookahead_threads=1",
        "-pix_fmt", "yuv420p",
        silent_video_path,
    ]
    subprocess.run(cmd, check=True)
    print("Wrote silent video %s" % silent_video_path)

    total_seconds = total_frames / float(FPS)

    music_path = None
    if not args.no_music:
        if args.music_file:
            music_path = args.music_file
        elif os.path.isdir(args.music_dir):
            tracks = sorted(glob.glob(os.path.join(args.music_dir, "*.mp3")))
            if tracks:
                music_path = tracks[datetime.date.today().toordinal() % len(tracks)]
    if music_path:
        print("Using music track %s" % music_path)

    audio_path = None
    if landing_events:
        audio_path = os.path.join(os.path.dirname(os.path.abspath(args.output)), "_audio_tmp.mp3")
        build_audio_track(landing_events, args.sfx_dir, total_frames, FPS, audio_path)
        print("Wrote audio track %s (%d landing sounds)" % (audio_path, len(landing_events)))

    music_fade_in = MUSIC_FADE_IN
    if music_path and os.path.exists(music_path + ".fadein"):
        music_fade_in = float(open(music_path + ".fadein").read().strip())
    cmd = ["ffmpeg", "-y", "-i", silent_video_path]
    filter_parts = []
    mix_inputs = []
    next_idx = 1
    if audio_path:
        cmd += ["-i", audio_path]
        mix_inputs.append("[%d:a]" % next_idx)
        next_idx += 1
    if music_path:
        cmd += ["-i", music_path]
        fade_out_start = max(0.0, total_seconds - MUSIC_FADE_OUT)
        filter_parts.append(
            "[%d:a]atrim=0:%.3f,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=%.2f,afade=t=out:st=%.3f:d=%.2f,volume=%.3f[music]"
            % (next_idx, total_seconds, music_fade_in, fade_out_start, MUSIC_FADE_OUT, MUSIC_VOLUME)
        )
        mix_inputs.append("[music]")
        next_idx += 1
    if mix_inputs:
        if len(mix_inputs) == 1:
            filter_parts.append("%sanull[aout]" % mix_inputs[0])
        else:
            filter_parts.append("%samix=inputs=%d:duration=longest:normalize=0[aout]" % ("".join(mix_inputs), len(mix_inputs)))
        cmd += [
            "-filter_complex", ";".join(filter_parts),
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", "%.3f" % total_seconds,
            args.output,
        ]
    else:
        cmd += ["-c:v", "copy", args.output]
    subprocess.run(cmd, check=True)
    print("Wrote %s" % args.output)


if __name__ == "__main__":
    main()
