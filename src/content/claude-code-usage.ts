export default `
I tracked my Claude Code usage over four weeks (March 6 \u2013 April 3, 2026) to understand where my time is actually going. Not just AI usage specifically, but my own working days \u2014 what am I spending time on, and how does the tool fit into that? The numbers surprised me.

## The headline numbers

- **~95 estimated hours** of usage (wall-clock, capped at 3 hrs/session; real active time is probably 60\u201370% of this)
- **81 sessions** across the period
- **5,700+ prompts**

## Where the time went

| Project | Est. Hours | Sessions | What |
|---|---|---|---|
| Transit Client | 28 hrs | 35 | Stakeholder matrices, kickoff decks, operations planning |
| Crime Data Pipeline | 19 hrs | 13 | Multi-city crime explorer, live app debugging, data pipelines |
| CPAL | 11 hrs | 8 | Council briefing materials, crisis response memos, crime analysis |
| County IT | 7 hrs | 5 | EHS proposals, digital payments transition docs |
| CPAL sub-projects | 7 hrs | 4 | App hub, council district reports, eviction briefing |
| National Poverty Explorer | 6 hrs | 4 | Map UI improvements, data layer updates |
| 17A Internal | 5 hrs | 3 | Brand assets, grant applications, talent pipeline |
| Other | 12 hrs | 9 | Newsletter, 311 explorer, misc |

## The split

- **~65%** client delivery (transit, CPAL, county IT)
- **~20%** product and tools (crime explorer, poverty explorer, 311 app)
- **~10%** firm operations (brand, grants, hiring)
- **~5%** personal/misc

## What's interesting about this

The heaviest single engagement (Transit Client, ~30% of all usage) wasn't a software project \u2014 it was stakeholder analysis, kickoff decks, and operations planning. The work product was PowerPoint, Word docs, and Excel, not code.

That's the thing about AI coding tools at a consulting firm: the "coding" is often generating structured documents, analyzing data, and building things that aren't traditionally "software." React apps and data pipelines are in the mix, but they share time with memos, briefing materials, and slide decks.

The tool doesn't replace the thinking. It compresses the execution time between having a clear idea and having a finished deliverable. For a lean organization serving government clients, that compression is the whole value proposition.

## Do it yourself

The best part: generating this analysis took about five minutes. Claude Code stores your session history locally as \`.jsonl\` files under \`~/.claude/projects/\`. You can ask Claude to read its own logs and summarize them.

Here's the exact prompt I used:

\`\`\`
Review my Claude Code session history from the last 4 weeks. Session files
are stored as .jsonl files under ~/.claude/projects/. Each file contains
timestamped entries with a type field \u2014 "user" entries are my prompts,
"assistant" entries are Claude's responses. Timestamps are ISO 8601 strings.
Ignore files in subagents/ subdirectories.

For each project directory, count sessions, user prompts, and tool calls.
Estimate active time as wall-clock duration between first and last message
per session (cap at 3 hours). Group by project, sort by time spent, and
include a few sample prompts per project so I can see what the work
actually was.

Present the results as a clean summary table.
\`\`\`

Paste that into Claude Code and you'll get your own usage breakdown in a few minutes. Adjust the time window, output format, or grouping however you like.

### Notes on methodology

- This only captures usage on the machine you run it on. If you use Claude Code on multiple machines, run it on each.
- Time estimates are upper bounds \u2014 they include idle time between messages. Real active time is probably 60\u201370% of the reported figure.
- Session files accumulate over time; swap "4 weeks" for any window you want.
`;

