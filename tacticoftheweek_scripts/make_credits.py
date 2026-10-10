import json, os

M = "🎵 Music: %s by %s → %s"
data = {
    "blackbird.mp3": ("Blackbird", "Toberton", "https://open.spotify.com/track/17Fy3U9aF8yQtvN7welMB5"),
    "beautiful_dreamer.mp3": ("Beautiful Dreamer", "Toberton", "https://open.spotify.com/track/1ZP8WV93hfgJIlVD15QAFr"),
    "driving_ambition.mp3": ("Driving Ambition", "Ahjay Stelino", "https://mixkit.co/free-stock-music/driving-ambition-32/"),
    "motivating_mornings.mp3": ("Motivating Mornings", "Ahjay Stelino", "https://mixkit.co/free-stock-music/motivating-mornings-33/"),
    "raising_me_higher.mp3": ("Raising Me Higher", "Ahjay Stelino", "https://mixkit.co/free-stock-music/raising-me-higher-34/"),
    "gimme_that_groove.mp3": ("Gimme That Groove", "Michael Ramir C.", "https://mixkit.co/free-stock-music/gimme-that-groove-872/"),
}
out = {k: {"title": v[0], "artist": v[1], "url": v[2], "line": M % v} for k, v in data.items()}
path = os.path.expanduser("~/chess-tactics/tacticoftheday/music/credits.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print("wrote", path, len(out), "tracks")
