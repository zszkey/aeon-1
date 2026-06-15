import os, re, glob as g, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aeon_runner import score_output

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
for f in sorted(g.glob(os.path.join(OUTPUT_DIR, "*_*.md")), key=os.path.getmtime):
    with open(f, "r", encoding="utf-8") as fp:
        c = fp.read()
    tc = int(re.search(r"Tool calls: (\d+)", c).group(1)) if re.search(r"Tool calls: (\d+)", c) else 0
    dur = float(re.search(r"Time: ([\d.]+)s", c).group(1)) if re.search(r"Time: ([\d.]+)s", c) else 60
    body = c.split("---\n", 2)[-1] if "---\n" in c else c
    s = score_output(body, tc, dur)
    print(f"{s:3d}  {os.path.basename(f):40s} {len(c):5d} chars  {tc} tools  {int(dur)}s")
