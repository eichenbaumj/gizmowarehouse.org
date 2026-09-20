"""
Generate branded 1200x630 Open Graph cards for gizmo detail pages.

Output: public/og/<slug>.png — referenced by tools/prerender.ts which
bakes them into per-route <meta og:image> tags at build time.

Run:  python3 tools/generate-og-cards.py

To add a new gizmo card, append to the GIZMOS list below. Fonts are
downloaded on first run to tools/.fonts-cache/ (gitignored).
"""
from PIL import Image, ImageDraw, ImageFont
import os, urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(REPO_ROOT, "tools", ".fonts-cache")
OUT = os.path.join(REPO_ROOT, "public", "og")
os.makedirs(OUT, exist_ok=True)
os.makedirs(FONTS, exist_ok=True)

FONT_URLS = {
    "SourceSerif4-Bold.ttf":     "https://github.com/adobe-fonts/source-serif/raw/release/TTF/SourceSerif4-Bold.ttf",
    "SourceSans3-Semibold.ttf":  "https://github.com/adobe-fonts/source-sans/raw/release/TTF/SourceSans3-Semibold.ttf",
    "SourceSans3-Regular.ttf":   "https://github.com/adobe-fonts/source-sans/raw/release/TTF/SourceSans3-Regular.ttf",
}
for name, url in FONT_URLS.items():
    p = os.path.join(FONTS, name)
    if not os.path.exists(p):
        print(f"fetching {name}")
        urllib.request.urlretrieve(url, p)

COBALT = (31, 31, 214)
CAROLINA = (33, 168, 224)
CHARCOAL = (59, 59, 59)
STEEL = (120, 120, 130)
WHITE = (255, 255, 255)
SOFT = (245, 247, 252)

W, H = 1200, 630

# Keep in sync with src/data/gizmos.ts. Only listed gizmos get a card;
# the others fall back to the sitewide og:image in index.html.
#
# medicaid-work-requirements is deliberately NOT listed: its card is a custom
# build (sankey visual) from tools/build-medicaid-og-card.py, and a run of
# this generic script must never overwrite it.
GIZMOS = [
    ("daf-yomi", "Introducing Daf Yomi Dot Dev",
     ["Using AI"]),
    ("gospel-of-claude-code", "Music Theory with LLMs",
     ["Music", "Using AI"]),
    ("data-center-restriction-cost", "Pricing the Fear of Data Centers",
     ["State Government", "City Government"]),
    ("nyc-public-grocery-new-math", "The New Math on NYC's Public Grocery Stores",
     ["City Government"]),
    ("microsoft-copilot", "How to Save the Government from Microsoft Copilot",
     ["Using AI", "City Government"]),
    ("nyc-property-tax-map", "NYC Property Tax: Who Pays, Who Doesn't",
     ["City Government", "State Government", "Using AI"]),
    ("nyc-public-grocery-math", "The Math on NYC's Public Grocery Plan",
     ["City Government"]),
]

serif_bold = lambda s: ImageFont.truetype(f"{FONTS}/SourceSerif4-Bold.ttf", s)
sans_semi = lambda s: ImageFont.truetype(f"{FONTS}/SourceSans3-Semibold.ttf", s)
sans_reg = lambda s: ImageFont.truetype(f"{FONTS}/SourceSans3-Regular.ttf", s)

def text_w(draw, txt, font):
    bbox = draw.textbbox((0,0), txt, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

def wrap_to_width(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if text_w(draw, trial, font)[0] <= max_w:
            cur = trial
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def render(slug, title, cats):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    # Left accent bar
    d.rectangle([(0,0),(18,H)], fill=COBALT)

    PAD_L = 80
    PAD_R = 80
    content_w = W - PAD_L - PAD_R

    # Category pills (top)
    pill_font = sans_semi(22)
    x = PAD_L
    y = 80
    for i, cat in enumerate(cats):
        tw, th = text_w(d, cat, pill_font)
        pad_x, pad_y = 16, 8
        bw, bh = tw + pad_x*2, th + pad_y*2 + 4
        color = COBALT if i % 2 == 0 else CAROLINA
        d.rounded_rectangle([(x,y),(x+bw,y+bh)], radius=bh//2, fill=color)
        d.text((x+pad_x, y+pad_y-2), cat, font=pill_font, fill=WHITE)
        x += bw + 12

    # Title
    # pick size that fits in ~4 lines
    for size in (76, 68, 60, 54, 48):
        tf = serif_bold(size)
        lines = wrap_to_width(d, title, tf, content_w)
        if len(lines) <= 4:
            break
    title_font = tf
    line_h = int(size * 1.12)
    ty = 180
    for line in lines:
        d.text((PAD_L, ty), line, font=title_font, fill=CHARCOAL)
        ty += line_h

    # Footer
    foot_font = sans_semi(26)
    foot_label = "GIZMO WAREHOUSE"
    d.text((PAD_L, H - 90), foot_label, font=foot_font, fill=COBALT)
    url_font = sans_reg(22)
    d.text((PAD_L, H - 55), "gizmowarehouse.org  ·  Joe Eichenbaum, 17A", font=url_font, fill=STEEL)

    # Bottom right tick mark
    d.rectangle([(W-120, H-18),(W, H)], fill=CAROLINA)

    path = f"{OUT}/{slug}.png"
    img.save(path, "PNG", optimize=True)
    print("wrote", path)

for slug, title, cats in GIZMOS:
    render(slug, title, cats)
