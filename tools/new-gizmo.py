#!/usr/bin/env python3
"""Scaffold a new gizmo (draft-safe), and publish it when it's ready.

Scaffold (default) — run from the repo root:

    python tools/new-gizmo.py

Prompts for slug, title, categories, summary, and optional links, then:

  1. Creates gizmos/<slug>/README.md
  2. Creates src/content/<slug>.ts (markdown stub)
  3. Appends a draft stanza to tools/mirror/manifest.ts
  4. Writes gizmos/<slug>/PUBLISH_CHECKLIST.md holding the exact gizmos.ts +
     index.ts blocks for the eventual publish

It does NOT touch src/data/gizmos.ts or src/content/index.ts — a draft on
main is therefore not in the site bundle, not live, and not mirrored, and its
slug is auto-screened by the mirror sync (see tools/mirror/MIRROR.md).

Publish — when the gizmo should go live:

    python tools/new-gizmo.py --publish <slug>

Wires the stored blocks into src/data/gizmos.ts (top of the array —
newest-first) and src/content/index.ts, then prints the go-live checklist.
`hidden: true` on a gizmos.ts entry means live-but-unlisted (still public,
still mirrored) — it is NOT a draft state.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent
GIZMOS_DIR = REPO_ROOT / "gizmos"
CONTENT_DIR = REPO_ROOT / "src" / "content"
CONTENT_INDEX = CONTENT_DIR / "index.ts"
GIZMOS_TS = REPO_ROOT / "src" / "data" / "gizmos.ts"
MANIFEST_TS = REPO_ROOT / "tools" / "mirror" / "manifest.ts"
STANZA_SENTINEL = "  // <new-gizmo:stanza-insertion-point>"

# Mirrors the Category type in src/data/gizmos.ts. If a new category is added,
# update both this list and the Category type + CategoryBadge.tsx color map.
KNOWN_CATEGORIES = [
    "Public Safety",
    "Music",
    "Using AI",
    "City Government",
    "State Government",
    "Healthcare Policy",
    "NYC",
]


def slug_to_camel(slug: str) -> str:
    parts = slug.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def prompt(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  (required)")


def prompt_categories() -> list[str]:
    print("\nCategories (pick one or more):")
    for i, c in enumerate(KNOWN_CATEGORIES, 1):
        print(f"  {i}. {c}")
    print("  n. New category (will require manual edits — see tools/README.md)")
    while True:
        raw = input("Comma-separated numbers (e.g. 1,3): ").strip()
        if not raw:
            print("  (required)")
            continue
        if "n" in raw.lower():
            print(
                "\n  New categories require updating the Category type in src/data/gizmos.ts\n"
                "  AND the colorMap in src/components/CategoryBadge.tsx before the site will\n"
                "  render. Add those first, then re-run this script.\n"
            )
            sys.exit(1)
        try:
            picks = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if not picks:
                raise ValueError
            chosen = [KNOWN_CATEGORIES[i - 1] for i in picks]
            return chosen
        except (ValueError, IndexError):
            print(f"  Pick numbers between 1 and {len(KNOWN_CATEGORIES)}, comma-separated.")


def prompt_links() -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    print("\nLinks (optional). Empty label to stop.")
    while True:
        label = input("  Link label (or blank to finish): ").strip()
        if not label:
            return links
        url = input("  Link URL:  ").strip()
        if not url:
            print("  (skipping — URL was empty)")
            continue
        links.append((label, url))


def manifest_slugs() -> list[str]:
    return re.findall(r'slug: "([a-z0-9-]+)"', MANIFEST_TS.read_text())


def validate_slug(slug: str) -> None:
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        print(
            f"\nInvalid slug: {slug!r}. Use lowercase letters, digits, and single hyphens "
            "(e.g. nyc-property-tax-map)."
        )
        sys.exit(1)
    if slug in manifest_slugs():
        print(f"\nSlug {slug!r} already has a stanza in tools/mirror/manifest.ts.")
        sys.exit(1)


def build_gizmos_entry(
    slug: str, title: str, categories: list[str], date: str, summary: str, links: list[tuple[str, str]]
) -> str:
    cats_str = ", ".join(f'"{c}"' for c in categories)
    safe_summary = summary.replace("\\", "\\\\").replace('"', '\\"')
    lines = [
        "  {",
        f'    slug: "{slug}",',
        f'    title: "{title}",',
        f"    categories: [{cats_str}],",
        f'    date: "{date}",',
        f'    summary: "{safe_summary}",',
    ]
    if links:
        lines.append("    links: [")
        for label, url in links:
            safe_label = label.replace("\\", "\\\\").replace('"', '\\"')
            safe_url = url.replace("\\", "\\\\").replace('"', '\\"')
            lines += ["      {", f'        label: "{safe_label}",', f'        url: "{safe_url}",', "      },"]
        lines.append("    ],")
    lines.append("  },")
    return "\n".join(lines)


def insert_into_index(import_line: str, map_line: str) -> None:
    text = CONTENT_INDEX.read_text()
    import_re = re.compile(r"^import .+;\n", flags=re.MULTILINE)
    matches = list(import_re.finditer(text))
    if not matches:
        print("Could not find import block in src/content/index.ts. Aborting.")
        sys.exit(1)
    last_import_end = matches[-1].end()
    text = text[:last_import_end] + import_line + text[last_import_end:]

    closing = re.search(r"\n\};", text)
    if not closing:
        print("Could not find closing brace of gizmoContent in src/content/index.ts. Aborting.")
        sys.exit(1)
    insert_at = closing.start() + 1
    text = text[:insert_at] + map_line + text[insert_at:]
    CONTENT_INDEX.write_text(text)


def insert_into_gizmos_ts(entry_block: str) -> None:
    """Insert at the TOP of the gizmos array — the file is ordered newest-first."""
    text = GIZMOS_TS.read_text()
    m = re.search(r"export const gizmos: Gizmo\[\] = \[\n", text)
    if not m:
        print("Could not find the gizmos array opener in src/data/gizmos.ts. Aborting.")
        sys.exit(1)
    text = text[: m.end()] + entry_block + "\n" + text[m.end() :]
    GIZMOS_TS.write_text(text)


def append_manifest_stanza(slug: str) -> None:
    text = MANIFEST_TS.read_text()
    if STANZA_SENTINEL not in text:
        print("Could not find the stanza insertion sentinel in tools/mirror/manifest.ts. Aborting.")
        sys.exit(1)
    stanza = (
        "  {\n"
        f'    slug: "{slug}",\n'
        "    include: [\n"
        f'      "gizmos/{slug}/",\n'
        f'      "src/content/{slug}.ts",\n'
        f'      "public/og/{slug}.png",\n'
        "      // Add config/component/data paths as the gizmo grows, e.g.:\n"
        f'      // "src/config/{slug_to_camel(slug)}.ts", "src/components/<dir>/", "public/data/{slug}/",\n'
        "    ],\n"
        "  },\n"
    )
    text = text.replace(STANZA_SENTINEL, stanza + STANZA_SENTINEL)
    MANIFEST_TS.write_text(text)


def scaffold() -> None:
    print("Scaffolding a new gizmo (draft — not live, not mirrored).\n")

    slug = prompt("Slug (kebab-case, e.g. nyc-property-tax-map)")
    validate_slug(slug)

    content_path = CONTENT_DIR / f"{slug}.ts"
    gizmo_dir = GIZMOS_DIR / slug
    if content_path.exists():
        print(f"\nRefusing to overwrite: {content_path.relative_to(REPO_ROOT)} already exists.")
        sys.exit(1)

    title = prompt("Title")
    categories = prompt_categories()
    today_ym = dt.date.today().strftime("%Y-%m")
    date = prompt("Date (YYYY-MM)", default=today_ym)
    summary = prompt("One-line summary")
    links = prompt_links()

    var_name = slug_to_camel(slug)

    # 1. gizmos/<slug>/README.md
    gizmo_dir.mkdir(parents=True, exist_ok=True)
    readme = gizmo_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            dedent(
                f"""\
                # {title} — source

                Source materials for [the gizmo](../../src/content/{slug}.ts).

                <!-- TODO: describe what's in this folder -->
                """
            )
        )

    # 2. src/content/<slug>.ts (orphan until --publish wires it up)
    content_path.write_text("export default `\n<!-- TODO: write the gizmo's markdown here -->\n`;\n")

    # 3. Draft stanza in the mirror manifest
    append_manifest_stanza(slug)

    # 4. PUBLISH_CHECKLIST.md with the stored wiring blocks
    entry_block = build_gizmos_entry(slug, title, categories, date, summary, links)
    checklist = GIZMOS_DIR / slug / "PUBLISH_CHECKLIST.md"
    header = dedent(
        f"""\
        # Publish checklist — {slug}

        This gizmo is a DRAFT: not in `src/data/gizmos.ts`, so not in the site
        bundle, not live, and not mirrored. When it's ready:

        1. `python tools/new-gizmo.py --publish {slug}` (wires the blocks below)
        2. `npm run dev` — review http://localhost:8080/gizmo/{slug}
        3. Review the mirror stanza in `tools/mirror/manifest.ts` — add any
           config/component/data paths the gizmo grew.
        4. Commit + push to main.
        5. Lovable syncs the push, but production needs **Publish → Publish
           changes** in the Lovable editor. Verify
           https://gizmowarehouse.org/gizmo/{slug} live.
        6. The mirror-sync Action (same push) polls the live site and mirrors
           the gizmo automatically once it's live. Nothing else to do.

        `hidden: true` = live-but-unlisted (still public, still mirrored). It
        is not a draft state.
        """
    )
    checklist.write_text(
        header
        + "\n## gizmos.ts entry\n\n"
        + "```ts gizmos-entry\n" + entry_block + "\n```\n"
        + "\n## index.ts wiring\n\n"
        + "```ts index-import\n" + f'import {var_name} from "./{slug}";\n' + "```\n"
        + "\n```ts index-entry\n" + f'  "{slug}": {var_name},\n' + "```\n"
    )

    print("\nDone. Files created (draft only — nothing wired into the site):")
    for p in [readme, content_path, checklist, MANIFEST_TS]:
        print(f"  {p.relative_to(REPO_ROOT)}")
    print(
        "\nNext steps:\n"
        f"  1. Write the markdown in src/content/{slug}.ts\n"
        f"  2. Drop downloads/images in public/assets/, data in public/data/{slug}/\n"
        f"  3. Source code/notebooks go in gizmos/{slug}/\n"
        f"  4. When it's ready to go live: python tools/new-gizmo.py --publish {slug}\n"
    )


def publish(slug: str) -> None:
    checklist = GIZMOS_DIR / slug / "PUBLISH_CHECKLIST.md"
    if not checklist.exists():
        print(f"No {checklist.relative_to(REPO_ROOT)} — scaffold the gizmo first.")
        sys.exit(1)
    text = checklist.read_text()

    def fenced(tag: str) -> str:
        m = re.search(rf"```ts {tag}\n(.*?)```", text, flags=re.DOTALL)
        if not m:
            print(f"Could not find the ```ts {tag}``` block in PUBLISH_CHECKLIST.md. Aborting.")
            sys.exit(1)
        return m.group(1)

    entry_block = fenced("gizmos-entry").rstrip("\n")
    import_line = fenced("index-import").strip("\n") + "\n"
    map_line = fenced("index-entry").rstrip("\n") + "\n"

    if f'slug: "{slug}"' in GIZMOS_TS.read_text():
        print(f"{slug!r} is already in src/data/gizmos.ts — nothing to do.")
        sys.exit(1)

    insert_into_index(import_line, map_line)
    insert_into_gizmos_ts(entry_block)

    print(
        f"\nWired {slug} into src/data/gizmos.ts (top of array) and src/content/index.ts.\n"
        "\nGo-live checklist:\n"
        f"  1. npm run dev — review http://localhost:8080/gizmo/{slug}\n"
        "  2. Commit + push to main.\n"
        "  3. Lovable syncs the push; production needs Publish → Publish changes\n"
        f"     in the Lovable editor. Verify https://gizmowarehouse.org/gizmo/{slug}\n"
        "  4. The mirror-sync Action polls the live site and mirrors this gizmo\n"
        "     automatically once it's live. Nothing else to do.\n"
    )


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--publish":
        if len(args) != 2:
            print("Usage: python tools/new-gizmo.py --publish <slug>")
            sys.exit(1)
        publish(args[1])
    elif args:
        print("Usage: python tools/new-gizmo.py [--publish <slug>]")
        sys.exit(1)
    else:
        scaffold()


if __name__ == "__main__":
    main()
