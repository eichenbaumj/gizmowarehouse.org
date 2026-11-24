export const meta = {
  name: 'date-sites-r3',
  description: 'Round 3 dating: capped-search lookups per batch, then the session model opens every cited page before anything is applied',
  phases: [
    { title: 'Lookup', detail: 'one lookup agent per batch, capped web searches' },
    { title: 'Verify', detail: 'session model, WebFetch only, every claim' },
  ],
}

// How to run (docs/DECISIONS.md D-15, HANDOVER.md "The web-search limit"):
//   python3 -I pipeline/facilities/make_date_worklist.py        (add --retry for the retry batches)
//   Workflow({ scriptPath: <this file>, args: {
//     dir: "<absolute path>/data/interim/r3",
//     cap: 23,                       // web searches per lookup agent (a batch may carry its own "cap");
//                                    // the caps must sum under the session's search limit (HANDOVER.md)
//     lookupModel: "<model id>",     // omit to use the session model
//     batches: <one tranche from data/interim/r3/batches.json> } })
// One tranche per turn. Results come back as [{k, lookup, verify}]; write them to
// pipeline/facilities/verified/batch_r3_<k>.json with only verified facts in the active fields.

const DIR = args.dir
const CAP = args.cap

const LOOKUP_ITEM = {
  type: 'object',
  properties: {
    fid: { type: 'string' },
    site_name: { type: 'string', description: 'operator campus or building name plus street address' },
    operator: { type: 'string' },
    state: { type: 'string' },
    operating_status: { type: 'string', enum: ['operating', 'not_yet_operating', 'not_a_data_center', 'crypto_mine', 'unknown'] },
    status_source_url: { type: ['string', 'null'], description: 'for not_yet_operating, not_a_data_center or crypto_mine: the non-directory page that says so' },
    status_as_of: { type: ['string', 'null'], description: 'date of that page, YYYY-MM-DD or YYYY-MM' },
    energized_year: { type: ['integer', 'null'], description: 'year the FIRST building at this site began operating; null if not found' },
    energized_year_source_url: { type: ['string', 'null'] },
    year_confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    year_basis: { type: 'string', enum: ['operator_statement', 'utility_or_regulator_filing', 'government_record_operating_or_opened', 'government_record_year_built_or_construction_complete', 'trade_press_opening', 'local_news_opening', 'two_pages_bracket_the_year', 'reference_work', 'inferred', 'not_found'] },
    year_evidence_quote: { type: ['string', 'null'], description: 'copied word for word from the cited page, 40 words or fewer' },
    source_opened: { type: 'boolean', description: 'true only if you opened the cited page with WebFetch and read the quoted words on it' },
    other_urls: { type: 'array', items: { type: 'string' }, description: 'other non-directory pages that bear on the date' },
    phases: { type: 'array', items: { type: 'object', properties: { label: { type: 'string' }, year: { type: 'integer' }, mw: { type: ['number', 'null'] }, source_url: { type: ['string', 'null'] } }, required: ['label', 'year'] } },
    notes: { type: 'string' },
  },
  required: ['fid', 'site_name', 'operator', 'state', 'operating_status', 'status_source_url', 'status_as_of', 'energized_year', 'energized_year_source_url', 'year_confidence', 'year_basis', 'year_evidence_quote', 'source_opened', 'other_urls', 'phases', 'notes'],
}
const LOOKUP_SCHEMA = {
  type: 'object',
  properties: {
    items: { type: 'array', items: LOOKUP_ITEM },
    searches_used: { type: 'integer' },
    search_refused: { type: 'boolean', description: 'true if a WebSearch call was refused or rate-limited' },
  },
  required: ['items', 'searches_used', 'search_refused'],
}
const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          fid: { type: 'string' },
          verdict: { type: 'string', enum: ['verified_year', 'verified_not_yet_operating', 'not_verified'] },
          year: { type: ['integer', 'null'] },
          source_url: { type: ['string', 'null'], description: 'the exact non-directory page you opened that carries the evidence' },
          confidence: { type: ['string', 'null'], enum: ['high', 'medium', null] },
          basis: { type: 'string', enum: ['operator_statement', 'utility_or_regulator_filing', 'government_record_operating_or_opened', 'government_record_year_built_or_construction_complete', 'trade_press_opening', 'local_news_opening', 'two_pages_bracket_the_year', 'reference_work', 'none'] },
          quote: { type: ['string', 'null'], description: 'word for word from the page, 40 words or fewer' },
          page_date: { type: ['string', 'null'] },
          site_match: { type: 'string' },
          pages_opened: { type: 'array', items: { type: 'string' } },
          comment: { type: 'string' },
        },
        required: ['fid', 'verdict', 'year', 'source_url', 'confidence', 'basis', 'quote', 'page_date', 'site_match', 'pages_opened', 'comment'],
      },
    },
  },
  required: ['results'],
}

const RULES = `WHAT COUNTS. We want the year the FIRST building at the site began operating: opened, commissioned, went live, delivered to its tenant, serving traffic.
- confidence "high": a page you opened states outright that this site or its first building opened, began operating, was commissioned, was completed and delivered, or is online, at a date in that year. A dated press release or article saying it "is now open" or "has completed" counts, with the year taken from the page date.
- confidence "medium": (a) a government record for the matching address or named facility giving a year built, a construction-completion date on a finished project, or "operating since" (EPA ENERGY STAR certified data centers registry, a state air-permit page, a state project registration marked closed, a county assessor page); or (b) two pages you opened that bracket the start to within one year (not yet open on one date, operating on a date at most a year later); or (c) a reference work or vendor write-up that states the opening year for the named site.
- NOT a start year: forward-looking statements ("will open", "expected to be operational", "customer installations will begin"), groundbreaking or construction start, announcements, land purchases, permits, a planned or target completion date, and any page that cannot be tied to THIS address or campus. Operators often run several campuses in one town; a statement about "a data center in Boydton" does not date a second campus there.
- Directory sites (baxtel.com, datacentermap.com, datacenters.com, cleanview.co, datacenterhawk.com) may suggest a site's name. They are never evidence and never the cited URL.
- Do not work around access controls. A page that refuses automated access is unavailable.`

function lookupPrompt(b) {
  return `You are dating large U.S. data center sites for a public-data study of electricity bills. Find a fact, cite a page you opened. Do not edit any files.

Read ${DIR}/in_batch_${b.k}.json. It holds ${b.n} items, each one permitted site: address, operator, company named on the backup-generator permit, coordinates, a rough load estimate, and sometimes a campus name or leads from an earlier pass (leads are unconfirmed; several earlier citations turned out not to say what was claimed).

For EACH item find the start year, and where the campus grew in phases list each phase in "phases".

${RULES}

If the site is still planned or under construction, set operating_status "not_yet_operating" and cite a non-directory page dated 2025 or later that says so (status_source_url, status_as_of), leaving the year null. If you cannot tell, use "unknown".

An earlier pass got about half its citations wrong, in four ways. Do not repeat them: (1) citing a directory site; (2) quoting words that were not on the page; (3) citing a plan or groundbreaking as an opening; (4) citing a page about a sibling campus. Every citation you return will be opened and read by a second checker. If you did not open the page, source_opened is false and confidence is at most medium. If you found nothing solid, say so: year null, year_basis "not_found". A missing year costs nothing; a wrong one corrupts the study.

SEARCH BUDGET: at most ${b.cap || CAP} WebSearch calls in total for the whole batch. Count them and report searches_used. WebFetch of a URL you already know does NOT count, so lean on fetches: operator press-release pages, datacenterdynamics.com, datacenterknowledge.com, datacenterfrontier.com, local newspapers, city and county economic-development pages, the EPA ENERGY STAR certified data centers registry (https://www.energystar.gov/buildings/certified-data-centers), state air-permit pages, and for Texas the TDLR project registry. Several items share a campus or an operator and town; plan searches so one serves several items. If a WebSearch call is refused or rate-limited, do not retry it: set search_refused true and finish with WebFetch only.

Return one record per item, same fid, same order as the file. Keep notes to three or four sentences: what you found, how you tied the page to this site, what you could not find. Put any other useful non-directory pages in other_urls.`
}

function verifyPrompt(claims) {
  return `You are the verification layer for a public-data study. A research pass proposed start years (or "not yet operating") for large U.S. data center sites. Decide, item by item, what a page you have actually opened supports. Use WebFetch only. Do NOT use WebSearch at all. Do not edit any files.

For each claim below, open the cited URL if it is not a directory site, then the other URLs in the record, and, if useful, pages reachable from those or the operator's own press-release pages.

${RULES}

verdict "verified_year": a page you opened supports the year at high or medium confidence as defined above. If the page supports a different year than claimed, report the year the page supports and say so in comment.
verdict "verified_not_yet_operating": a non-directory page you opened, dated 2025 or later, says the site has not started operating. Put its date in page_date; year stays null.
verdict "not_verified": anything else. Default to this whenever you are unsure. A wrong year is worse than a missing one.

Quote the deciding passage word for word. In site_match say what on the page ties it to this address or campus. One result per claim, same fid.

Claims:
${JSON.stringify(claims, null, 1)}`
}

const results = await pipeline(
  args.batches,
  b => agent(lookupPrompt(b), { label: `lookup:${b.k}`, phase: 'Lookup', schema: LOOKUP_SCHEMA, ...(args.lookupModel ? { model: args.lookupModel } : {}) }),
  async (lookup, b) => {
    if (!lookup) return { k: b.k, lookup: null, verify: null }
    const claims = lookup.items.filter(i => i.energized_year !== null || i.operating_status === 'not_yet_operating').map(i => ({
      fid: i.fid, site: i.site_name, operator: i.operator, state: i.state,
      claims_not_yet_operating: i.operating_status === 'not_yet_operating',
      status_url: i.status_source_url, status_as_of: i.status_as_of,
      claimed_start_year: i.energized_year, cited_url: i.energized_year_source_url,
      researcher_confidence: i.year_confidence, researcher_basis: i.year_basis,
      researcher_quote: i.year_evidence_quote, other_urls: i.other_urls, phases: i.phases, researcher_notes: i.notes,
    }))
    log(`batch ${b.k}: ${claims.length}/${lookup.items.length} items carry a claim, ${lookup.searches_used} searches${lookup.search_refused ? ' (a search was refused)' : ''}`)
    if (!claims.length) return { k: b.k, lookup, verify: { results: [] } }
    const verify = await agent(verifyPrompt(claims), { label: `verify:${b.k}`, phase: 'Verify', schema: VERIFY_SCHEMA })
    return { k: b.k, lookup, verify }
  },
)
return results
