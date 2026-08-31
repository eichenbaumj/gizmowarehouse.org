export default `
I love to play piano and sing. I was raised on the great American songbook (Gershwin, Cole Porter, Irving Berlin), and I play as often as I can. When I can't get a gig at the Copacabana, I play a monthly show at the neighborhood retirement community. For years I used a mix of printed lead sheets, Real Book pages, and Ultimate Guitar tabs — all in different formats, different keys, and scattered across folders.

So I built a tool that turns plain-text chord charts into a single, clean PDF fake book. You write charts in a simple format (chords over lyrics, section headers in brackets), run a Python script, and get a PDF with an alphabetical table of contents, PDF bookmarks for each tune, and one song per page in a monospace font designed for reading on a laptop propped on a piano stand.

## How it works

The input format is dead simple:

\`\`\`
Fly Me to the Moon - Bart Howard
Key: C | Tempo: Medium Swing

[Verse]
Am7       Dm7        G7        Cmaj7
Fly me to the moon,  let me play among the stars
\`\`\`

The script auto-detects which lines are chords vs. lyrics (based on token analysis), preserves the exact spacing so chords align over the right syllables, and renders everything in Courier so the alignment holds.

## What made this a good AI project

The entire thing — the parser, the PDF renderer, the TOC builder — was built with Claude Code in a few hours. The regex for detecting chord lines vs. lyric lines took a few iterations to get right (handling things like slash chords, parenthetical chords, and lines that mix chords with annotations). But the core loop of "describe what I want → get working code → test on real charts → refine" was exactly the kind of task where an AI coding assistant shines: well-defined output, fast iteration, and a human in the loop who knows what "correct" looks like.

Since then the project has kept growing: the naive regex became a real chord grammar, the book grew a lint-and-test QC layer, and lately Claude has been writing chords, not just code — that story is in [The Gospel of Claude Code](/gizmo/gospel-of-claude-code).

## The book

Currently has 70 tunes — standards, bossa novas, ballads, and a few gospel reharmonizations. Adding a new song takes about two minutes: paste a chart from Ultimate Guitar, clean up the formatting, run the build script.

The output is designed for a specific use case (14" laptop screen, piano stand, dim lighting), which turns out to be a design constraint that makes everything simpler. No fancy layout, no images, no multi-column — just readable chords and lyrics.

## Make your own

The code is on GitHub: [github.com/eichenbaumj/fakebook-maker](https://github.com/eichenbaumj/fakebook-maker) — the build script, the chord-grammar QC tools, the tests, and two demo charts. Clone it, \`pip install reportlab\`, drop your own \`.txt\` charts in \`charts/\`, and run \`python3 fakebook/build.py\`.

You can also **download my fakebook** (link above) to see what the output looks like. That copy is the public-domain edition: the full book's lyrics are mostly still under copyright, so the public one carries the nine tunes old enough to share.

If you play from a laptop or tablet, this will change your life. If you play from paper, it'll at least make your binder more organized.
`;
