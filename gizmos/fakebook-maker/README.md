# Jazz Fakebook Maker — source

The tool is public at **https://github.com/eichenbaumj/fakebook-maker** (its own
repo, fresh history, MIT): build script, chord-grammar QC toolkit, tests, and two
demo charts. The gizmo page links there — to edit the tool, work in that repo
(source of truth is the private `~/Projects/personal/sheet-music` repo; sync via
its `tools/export_public.sh`).

[`public/assets/build.py`](../../public/assets/build.py) is now just a pointer
stub kept so the old download URL keeps resolving (Lovable persists removed
assets, so replacing beats deleting).

[`public/assets/fakebook.pdf`](../../public/assets/fakebook.pdf) is the
**public-domain edition** (9 tunes verified first-published ≤1930; the
classification with sources is `charts/PUBLIC_DOMAIN.md` in the private
sheet-music repo). The full ~70-tune book is copyright-adjacent and must never
be published — build the PD edition with:

```
python3 fakebook/build.py --include-list charts/public_domain_list.txt \
    --output fakebook/fakebook-public-domain.pdf --title "Joe's Fake Book — Public Domain Edition"
```
