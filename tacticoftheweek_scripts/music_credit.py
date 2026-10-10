import json, os, re, sys

DIR = os.path.expanduser("~/chess-tactics/tacticoftheday/music")
text = open(sys.argv[1], encoding="utf-8", errors="ignore").read() if len(sys.argv) > 1 else sys.stdin.read()
m = re.search("(?:Using music track|music) (/[^ ]+[.]mp3)", text)
if m:
    name = os.path.basename(m.group(1))
    credits = json.load(open(os.path.join(DIR, "credits.json"), encoding="utf-8"))
    entry = credits.get(name)
    if entry:
        print(entry["line"])
