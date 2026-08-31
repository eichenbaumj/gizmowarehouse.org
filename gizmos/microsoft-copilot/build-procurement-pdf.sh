#!/usr/bin/env bash
# Regenerate the procurement-guide PDF from its markdown source.
#
# Run from the repo root:
#   bash gizmos/microsoft-copilot/build-procurement-pdf.sh           # HTML + PDF
#   bash gizmos/microsoft-copilot/build-procurement-pdf.sh --html-only  # HTML only (fast CSS iteration)
#
# Requirements:
#   - pandoc (brew install pandoc)
#   - weasyprint (pip3 install weasyprint) + pango/cairo (brew install pango cairo)
#   - BRAND_ROOT env var pointing at the 17A brand-assets directory
#     (needs fonts/, logos/svg/, patterns/svg/)
#
# Outputs:
#   - gizmos/microsoft-copilot/preview.html              (intermediate, gitignored)
#   - gizmos/microsoft-copilot/preview-styles.css        (intermediate, gitignored)
#   - gizmos/microsoft-copilot/assets/pattern-02-white.svg  (recolored brand pattern, gitignored)
#   - public/assets/government-ai-procurement-guide.pdf  (final, committed)
#
# Style: 17A brand system. Cobalt #1F1FD6 / Carolina #21A8E0 / Charcoal #3B3B3B.
# Source Serif 4 (headings) and Source Sans 3 (body) loaded by @font-face from
# $BRAND_ROOT/fonts/ (pdf-styles.css carries __BRAND_ROOT__ placeholders that
# this script resolves into preview-styles.css). The cover band uses a
# white-recolored copy of brand Pattern 02 and the white solid 17A logo. All
# composed via pdf-template.html + pdf-styles.css.

set -euo pipefail

HTML_ONLY=0
if [[ "${1:-}" == "--html-only" ]]; then
  HTML_ONLY=1
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BRAND_ROOT="${BRAND_ROOT:?Set BRAND_ROOT to your brand-assets directory (fonts/, logos/svg/, patterns/svg/)}"
SRC_MD="$REPO_ROOT/public/assets/government-ai-procurement-guide.md"
OUT_PDF="$REPO_ROOT/public/assets/government-ai-procurement-guide.pdf"
TEMPLATE="$SCRIPT_DIR/pdf-template.html"
STYLES="$SCRIPT_DIR/pdf-styles.css"
PREVIEW_STYLES="$SCRIPT_DIR/preview-styles.css"
PREVIEW_HTML="$SCRIPT_DIR/preview.html"
ASSETS_DIR="$SCRIPT_DIR/assets"
PATTERN_SRC="$BRAND_ROOT/patterns/svg/Pattern 02 Dots.svg"
PATTERN_OUT="$ASSETS_DIR/pattern-02-white.svg"

for f in "$SRC_MD" "$TEMPLATE" "$STYLES" "$PATTERN_SRC"; do
  if [[ ! -f "$f" ]]; then
    echo "Required file not found: $f" >&2
    exit 1
  fi
done

mkdir -p "$ASSETS_DIR"

# Regenerate the white-dot Pattern 02 (brand SVG ships with #1a00f3 fills).
sed 's/#1a00f3/#ffffff/g' "$PATTERN_SRC" > "$PATTERN_OUT"

# Resolve the __BRAND_ROOT__ placeholders in the stylesheet (the committed CSS
# stays machine-independent; the resolved copy is what preview.html links).
sed "s|__BRAND_ROOT__|$BRAND_ROOT|g" "$STYLES" > "$PREVIEW_STYLES"

# Strip the leading "N. " from H2 headings so the CSS numbered-circle counter
# doesn't double up the section number. The markdown source keeps the numbers
# so the .md download reads naturally; the PDF renders just the title text
# alongside the circle.
TMP_MD="$(mktemp -t procurement-guide.XXXXXX.md)"
trap 'rm -f "$TMP_MD"' EXIT
sed -E 's/^(## )[0-9]+\. /\1/' "$SRC_MD" > "$TMP_MD"

# 1. Render the markdown to standalone HTML using the 17A pandoc template.
pandoc "$TMP_MD" \
  --from gfm \
  --to html5 \
  --standalone \
  --template "$TEMPLATE" \
  --metadata title="Buying AI for a Government Agency" \
  --metadata pagetitle="Buying AI for a Government Agency — 17A" \
  --metadata author="Joe Eichenbaum, 17A" \
  --output "$PREVIEW_HTML"

# Resolve the template's __BRAND_ROOT__ placeholder (cover logo path).
sed -i '' "s|__BRAND_ROOT__|$BRAND_ROOT|g" "$PREVIEW_HTML"

echo "Wrote $PREVIEW_HTML"

if [[ "$HTML_ONLY" == "1" ]]; then
  exit 0
fi

# 2. Render HTML to PDF via WeasyPrint, loading brew-provided pango/cairo libs.
DYLD_FALLBACK_LIBRARY_PATH="${DYLD_FALLBACK_LIBRARY_PATH:-/opt/homebrew/lib}" \
  python3 - "$PREVIEW_HTML" "$SCRIPT_DIR" "$OUT_PDF" <<'PY'
import sys
from weasyprint import HTML
src, base, out = sys.argv[1], sys.argv[2], sys.argv[3]
HTML(filename=src, base_url=base).write_pdf(out)
print("Wrote", out)
PY
