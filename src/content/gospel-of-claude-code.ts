export default `
Earlier this year I built a [fakebook maker](/gizmo/fakebook-maker) with Claude Code — a Python script that turns plain-text chord charts into a PDF fake book I read off a laptop at gigs. Since then the book has grown to 70 tunes, and lately I've been asking Claude for something beyond code: better chords.

## Making chord charts with Claude Code

The workflow hasn't changed: chords over lyrics in a text file, run the build, get a bookmarked PDF. What's new is an \`/add-tune\` command that does the whole thing — fetch a chart, format it, rebuild the book, verify the output. Adding a song takes one sentence.

## Why LLMs are natural band leaders

A chord chart is just text, and songs move through chords in patterns so conventional that musicians name them like grammar: establish the home chord, build tension, resolve it home. Gospel and jazz players decorate that skeleton the same ways every time — bass lines that climb stepwise into the next chord, a "secondary dominant" that briefly treats the next chord as home, the "amen" cadence you hear at the end of a hymn.

An LLM has read a million chord charts, and predicting the next chord in a progression is what it does all day: next-token prediction. Ask it to gospel-ify a three-chord song and it isn't improvising; it's autocompleting from a century of gospel piano. The results held up at the piano. Here's the intro to "If I Had a Hammer," before and after:

\`\`\`
C      G      F      G

C    C7/E   F    F#dim7   C/G   A7b9   Dm7   G13
\`\`\`

## The prompt

The first one was barely a prompt:

\`\`\`
just thinking out loud don't build anything yet.... is there a way
to make these chords more gospel like? jazzy transitions etc:
[Ultimate Guitar link]
\`\`\`

Claude proposed the moves, we talked them through, and one sentence added the tune to the book. By the third song the entire prompt was "do it in the way you did for accidentally in love and for i'll fly away."

## Check out the latest book

The book now has 70 tunes, including gospel arrangements of "I'll Fly Away," "If I Had a Hammer," and — forgive me — "Accidentally in Love." Those three are still under copyright, so the download above is the public-domain edition: nine tunes old enough to share, chords and lyrics included. And the toolchain is now public: [github.com/eichenbaumj/fakebook-maker](https://github.com/eichenbaumj/fakebook-maker) has the build script, the chord-grammar QC tools, and the tests. Bring your own tunes.
`;
