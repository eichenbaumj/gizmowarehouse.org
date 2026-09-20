export default `
Jews have been reading the Babylonian Talmud for 1,400 to 1,500 years. Some study it all day, every day. There is a mitzvah in Judaism, a literal one, to study Torah, and a persistent ethic that treats study as devotion: not a substitute for worship but a form of it, carried out by arguing with a text. I am proud of what that says about our faith. We are prone to arcane abstraction, contract law, and debate.

I have never read the Babylonian Talmud in its entirety. One common modern practice is Daf Yomi ("page of the day"): one double-sided page every day. It takes 2,711 days to get through the Talmud's roughly 5,400 pages.

This Yom Kippur I made a flimsy, non-guaranteed, best-effort promise to God that I would try to read the Babylonian Talmud one page at a time. I suspect I won't manage every day. The goal is to read a little more Talmud than the zero I read now.

The existing resources for Daf Yomi are limited. The tech offerings for Christian Bible study, by contrast, are fantastic and varied. Before Claude could code, [daf-yomi.dev](https://daf-yomi.dev) would have taken a person months of evenings. This was a morning. I hope it's useful.

[Daf-yomi.dev](https://daf-yomi.dev) is an AI gizmo, but it does not live at the Gizmo Warehouse. This is just a post celebrating its birth.

The fun part was designing exactly how the Talmud meets the AI. The first build of the site was done with Claude Code running Claude Fable 5.1, and that is still how I work on it. The nightly notes are written by Claude Opus 5 through Anthropic's API. I tried to give the process principles, rules, and tests, including:

- Each night Claude writes three sentences and one question about the day's page.
- The model gets the English text of that daf, which is Rabbi Steinsaltz's translation with his explanation woven in, and nothing else. No web, no Rashi, no outside commentaries. Nothing but the Talmud itself, in Rabbi Steinsaltz's edition.
- Every quoted phrase must appear verbatim in the source. No later authorities, no halacha stated as practice, no sermon, exactly one question. Fail twice and the page shows no note rather than a wrong one.
- Every note says an AI wrote it, above the words, every day.

The rest is one Cloudflare Worker, Sefaria's open API, and a cron. It costs a few cents a day.
`;
