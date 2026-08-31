"""
Build a custom OG card for medicaid-work-requirements using the sankey
screenshot as the main visual, with a branded title bar overlay.
Output: public/og/medicaid-work-requirements.png (1200x630).

Prereq: place a 1920x1080 screenshot of the sankey at /tmp/sankey_full.png
(captured from /gizmo/medicaid-work-requirements scrolled to the
"Where the projected losses come from" section). Crop bounds below
assume that source resolution.
"""
from PIL import Image, ImageDraw, ImageFont
import os

FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", ".fonts-cache")
# Also handle being run from project root vs /tmp:
for cand in [FONTS, "tools/.fonts-cache", "/tmp/fonts"]:
    if os.path.exists(os.path.join(cand, "SourceSerif4-Bold.ttf")):
        FONTS = cand; break

COBALT = (31, 31, 214)
CAROLINA = (33, 168, 224)
CHARCOAL = (59, 59, 59)
WHITE = (255, 255, 255)

W, H = 1200, 630
TITLE_H = 200    # top band for title
CHART_H = H - TITLE_H

# 1. Crop sankey from the screenshot — chart bounds in 1920x1080 source
src = Image.open("/tmp/sankey_full.png").convert("RGB")
# Sankey chart region (approx, includes left "5.20M" label and right category labels)
crop = src.crop((345, 410, 1640, 1030))  # ~1295 x 620
# Resize/fit into chart area (1200 x 430), maintain aspect
target_w, target_h = W, CHART_H
cw, ch = crop.size
scale = min(target_w / cw, target_h / ch)
nw, nh = int(cw * scale), int(ch * scale)
chart = crop.resize((nw, nh), Image.LANCZOS)

# Compose
img = Image.new("RGB", (W, H), WHITE)
# Chart area centered horizontally, anchored to bottom of card with small bottom pad
chart_x = (W - nw) // 2
chart_y = TITLE_H + (CHART_H - nh) // 2
img.paste(chart, (chart_x, chart_y))

d = ImageDraw.Draw(img)

# Left cobalt accent bar
d.rectangle([(0, 0), (18, H)], fill=COBALT)

# Title band background (soft separator under title)
serif_bold = ImageFont.truetype(f"{FONTS}/SourceSerif4-Bold.ttf", 54)
sans_semi = ImageFont.truetype(f"{FONTS}/SourceSans3-Semibold.ttf", 22)
sans_reg = ImageFont.truetype(f"{FONTS}/SourceSans3-Regular.ttf", 20)

# Category pills
PAD_L = 60
y = 36
pills = [("Healthcare Policy", COBALT), ("State Government", CAROLINA)]
x = PAD_L
for label, color in pills:
    bbox = d.textbbox((0,0), label, font=sans_semi)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    pad_x, pad_y = 14, 7
    bw, bh = tw + pad_x*2, th + pad_y*2 + 4
    d.rounded_rectangle([(x,y),(x+bw,y+bh)], radius=bh//2, fill=color)
    d.text((x+pad_x, y+pad_y-2), label, font=sans_semi, fill=WHITE)
    x += bw + 10

# Title
title = "These 5 Million People Are About to Lose Medicaid"
# wrap to two lines
words = title.split()
line1, line2 = "", ""
for i in range(len(words), 0, -1):
    cand = " ".join(words[:i])
    if d.textbbox((0,0), cand, font=serif_bold)[2] <= W - 2*PAD_L:
        line1 = cand
        line2 = " ".join(words[i:])
        break
ty = 88
d.text((PAD_L, ty), line1, font=serif_bold, fill=CHARCOAL)
if line2:
    d.text((PAD_L, ty + 60), line2, font=serif_bold, fill=CHARCOAL)

# Footer strip (bottom): brand + url, on right of chart area
foot_y = H - 32
d.text((PAD_L, foot_y - 4), "GIZMO WAREHOUSE", font=sans_semi, fill=COBALT)
url_text = "gizmowarehouse.org"
url_bbox = d.textbbox((0,0), url_text, font=sans_reg)
d.text((W - PAD_L - (url_bbox[2]-url_bbox[0]), foot_y - 3), url_text, font=sans_reg, fill=CHARCOAL)

# Bottom accent
d.rectangle([(W-120, H-6),(W, H)], fill=CAROLINA)

out = "public/og/medicaid-work-requirements.png"
img.save(out, "PNG", optimize=True)
print("wrote", out)
