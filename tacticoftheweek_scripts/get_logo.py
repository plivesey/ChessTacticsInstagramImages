import json, os, urllib.request, urllib.parse, io
from PIL import Image

q = urllib.parse.quote("Chess Tactics and Lessons")
url = "https://itunes.apple.com/search?term=%s&entity=software&limit=15" % q
data = json.loads(urllib.request.urlopen(url, timeout=30).read().decode("utf-8"))
best = None
for r in data.get("results", []):
    print(r.get("trackName"), "|", r.get("sellerName"), "|", r.get("bundleId"), "|", r.get("trackViewUrl"))
    seller = ((r.get("sellerName") or "") + " " + (r.get("artistName") or "")).lower()
    if "lockwood" in seller and best is None:
        best = r
if best is None:
    print("NO_MATCH")
else:
    art = best["artworkUrl512"]
    got = None
    for u in (art.replace("512x512bb", "1024x1024bb"), art):
        try:
            got = urllib.request.urlopen(u, timeout=30).read()
            break
        except Exception as e:
            print("download failed", u, e)
    if got:
        img = Image.open(io.BytesIO(got)).convert("RGBA")
        img.save("assets/logo.png")
        print("LOGO_SAVED", best.get("trackName"), img.size)
