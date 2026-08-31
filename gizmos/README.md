# gizmos/

One folder per gizmo. The contents of each subfolder is the *source material* — build scripts, exploration notebooks, raw notes, draft data — that produced the gizmo.

The deployed parts of each gizmo live elsewhere:

- **Markdown**: `src/content/<slug>.ts`
- **Metadata** (title, summary, categories, links): `src/data/gizmos.ts`
- **Served files** (downloads, images, PDFs): `public/assets/`

If a gizmo's source code is also its deliverable (e.g. `fakebook-maker`'s `build.py`), the canonical copy stays in `public/assets/` and the per-gizmo folder just points to it.

To add a new gizmo, run `python tools/new-gizmo.py` from the repo root. It scaffolds the folder, the markdown stub, a mirror-manifest stanza, and a `PUBLISH_CHECKLIST.md` — as a **draft**: nothing is wired into the site, so a draft on `main` is not live and not mirrored. When it's ready, `python tools/new-gizmo.py --publish <slug>` wires it into `src/data/gizmos.ts` + `src/content/index.ts`; push, click Publish in Lovable, and the public mirror (`eichenbaumj/gizmowarehouse.org`) picks it up automatically once it's live.

## Gizmos that need to ship more than ~25 MB of data

Lovable's per-asset cap is around 25 MB. Anything larger (PMTiles, big GeoJSON, large CSVs, downloadable model files) gets hosted on Cloudflare R2 and served through the custom domain `https://data.gizmowarehouse.org/<gizmo-slug>/<file>`. The pattern — bucket, custom domain, upload script, why we don't use `pub-*.r2.dev` — is in `tools/HOSTING_DATA.md`. Read it before standing up R2 for a new gizmo.
