"""Letterbox a capture onto a 1200x675 white canvas (Reddit / OG preview aspect).

    python3 tools/social-letterbox.py in.png [out.png]
"""
import sys
from PIL import Image

src = sys.argv[1]
dst = sys.argv[2] if len(sys.argv) > 2 else src
W, H = 1200, 675
im = Image.open(src).convert("RGB")
scale = min(W / im.width, H / im.height)
rw, rh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
im = im.resize((rw, rh), Image.LANCZOS)
canvas = Image.new("RGB", (W, H), "white")
canvas.paste(im, ((W - rw) // 2, (H - rh) // 2))
canvas.save(dst, "PNG", optimize=True)
print(f"wrote {dst} ({W}x{H})")
