import json, glob
for p in sorted(glob.glob("results/[0-9]*.json")):
    d = json.load(open(p))
    h = d["headers"]
    print("==", p, h.get("White"), h.get("WhiteElo"), "vs", h.get("Black"), h.get("BlackElo"), h.get("Result"), h.get("Date"), "plies", d["plies"])
    for c in d["chains"]:
        print("  chain: winner", c["winner"], "start_ply", c["start_ply"], "len", c["length"], "e_prev", c["e_prev"], "s1_start", c["s1_start"], "s2_start", c["s2_start"], "jump", c["jump"], "s1_end", c["s1_end"], "material", c["material_start"], "->", c["material_end"], "moves", c["chain_san"])
