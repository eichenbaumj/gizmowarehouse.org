"""The closing register for the verification pass: one row per (site, question).

What it does. It restates what is on file for every question the pass is to be
closed on, and proposes, by fixed rules, the named avenue each unresolved row
would close under. It decides nothing; only the owner closes the pass.

Rows are the union of
  (1) every (site, question) in the pass's table of questions
      (pipeline/facilities/verified/pass_c_questions.csv), and
  (2) every (fid, question) in any state's open-question list in the
      exact-attribution driver's JSON.

Inputs, read and nothing else: the attribution JSON and CSV (paths given on the
command line), the table of questions, the log of attempts, the corrections in
force, and section 5 of the browser list. Nothing under data/ is read.

Method choices, stated so they can be checked:
  * The attribution names questions assignment / date / capacity; the table
    names them assignment / operating date / capacity coverage. Every row uses
    the table's names.
  * A browser-sitting row is matched to a site in the table of questions when
    the first cell of a row of the browser list's section 5 table carries the
    site id, or carries the site's operator (the label up to its first comma)
    as a whole word AND the first word of the site's host (on_the_list_for,
    without "City of" and the state suffix), and exactly one table site meets
    both. Rows that match no site are reported, never guessed.
  * Rule 4 (mixed filings) matches its keywords as whole words, plural allowed,
    case-insensitive, so that "airport" does not read as "IRP".
  * Rule 5's lead is "consumed" only when rule 4 matched inside the lead text.
  * The evidence summary for a site not in the table is the `why` of the
    corrections whose kind speaks to that question (assign, candidates, reopen
    -> assignment; date -> operating date; capacity_split -> capacity coverage),
    joined; blank if none.
  * "every avenue of rule 3.3 tried" is never written for a row on which no
    avenue is on file: that case raises instead of writing a false sentence.

Usage:
  python3 -I pipeline/facilities/pass_c_closing_register.py \
      --attribution X.json --attribution-csv X.csv --out PREFIX \
      [--corrections ...] [--texas-request pending|declined] [--check]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
VERIFIED = PROJECT / "pipeline" / "facilities" / "verified"

DEFAULT_QUESTIONS = VERIFIED / "pass_c_questions.csv"
DEFAULT_LOG = VERIFIED / "pass_c_log.csv"
DEFAULT_CORRECTIONS = VERIFIED / "pass_c_corrections_s13_variant.json"
DEFAULT_BROWSER_LIST = PROJECT / "docs" / "gate1" / "browser-list-2026-11-15.md"
DEFAULT_NAMED_AVENUES = VERIFIED / "pass_c_named_avenues.csv"
DEFAULT_D68 = "AR,AZ,CA,CO,GA,KS,MN,MO,NE,NM,NV,OH,OR,TX,UT,VA,WY"

QUESTION_NAMES = {"assignment": "assignment", "date": "operating date", "capacity": "capacity coverage"}
TABLE_QUESTIONS = set(QUESTION_NAMES.values())
TABLE_STATUSES = {"resolved", "resolved for part", "unresolved", "not examined"}
CORRECTION_KINDS = {"assign", "date", "candidates", "capacity_split", "reopen"}
CORRECTION_QUESTION = {"assign": "assignment", "candidates": "assignment", "reopen": "assignment",
                       "date": "operating date", "capacity_split": "capacity coverage"}
PLACES = ("comparison", "cohort", "early", "late", "neither")
PLACE_ORDER = PLACES + ("undefined",)

COVERAGE_D68 = "seventeen states of D-68"
COVERAGE_FIRST = "first run 2026-11-18, for descriptive counts only"
COVERAGE_NONE = "not in any state's check"
COVERAGE_NOT_OPEN = "not an open question in the check"

STATUS_ENTERED = "resolved (entered in the corrections in force)"

R_HOST = "kept for a listed host"
R_COMPARISON = "kept for another utility: a consequential comparison question"
R_OTHER = "kept for another utility that is not a comparison utility on the reference"
R_CEILING = "kept only by the conservative result for a utility over the search ceiling"
R_REL_NOT_KEPT = ("relevant and not kept under the place criterion: retained because the future-host "
                  "criterion is not implemented")
R_REL_NONE = ("relevant to no utility under the place criterion: retained because the future-host "
              "criterion is not implemented")
R_FIXED = "on the fixed list; not an open question in the check"
RETAINED_ORDER = (R_HOST, R_COMPARISON, R_OTHER, R_CEILING, R_REL_NOT_KEPT, R_REL_NONE, R_FIXED)

AV_NEVER_RUN = "rule 3.3's lookups, never run on this site"
AV_NOT_IN_FULL = "rule 3.3's rounds, not run in full on this site (attempts on file are in avenues_tried)"
AV_TEXAS = "the request to the Texas commission for the official certificated-area maps ({})"
AV_BROWSER = "the browser sitting's page for this site"
AV_LOAD_ONLY = "a load-only route for mixed filings"
AV_LEAD = "the lead on file: "
AV_ALL_TRIED = "unresolved with every avenue of rule 3.3 tried and no lead remaining"
AV_NO_LOOKUP = "no lookup was made in this state"
NOT_AVENUES = (AV_ALL_TRIED, AV_NO_LOOKUP)  # entries in a row's list that name no avenue

# closing_class: a partition of all rows, one value each
CC_RESOLVED = "resolved"
CC_PART_NAMED = "resolved for part; the rest closed with named avenues unpursued"
CC_PART_ALL = "resolved for part; the rest with every avenue tried"
CC_NOT_EXAMINED = "not examined: no avenue was run on this question"
CC_NEVER = "unresolved; never looked up: closed with rule 3.3's lookups unpursued"
CC_IN_PART = "unresolved; looked up in part: closed with named avenues unpursued"
CC_ALL_TRIED = "unresolved; every avenue of rule 3.3 tried and no lead remaining"
CLOSING_CLASSES = (CC_RESOLVED, CC_PART_NAMED, CC_PART_ALL, CC_NOT_EXAMINED, CC_NEVER, CC_IN_PART, CC_ALL_TRIED)
UNRESOLVED_CLASSES = (CC_NEVER, CC_IN_PART, CC_ALL_TRIED)
OWNER_PHRASE = "the class the owner's ruling calls exhausted"
AV_LEAD_KEY = "the lead on file (its text is in the row)"
UNRESOLVED_PREFIX = "unresolved; closed with these avenues unpursued: "
PART_PREFIX = "resolved for part; for the rest, closed with these avenues unpursued: "
PART_ALL_TRIED = "resolved for part; for the rest, every avenue of rule 3.3 tried and no lead remaining"
NOT_EXAMINED = "not examined: no avenue was run on this question"
NOT_EXAMINED_NOT_OPEN = " and it is not an open question in the check"

MIXED_FILING = re.compile(
    r"\b(?:docket|rate case|tariff|resource plan|IRP|filing|testimony|PUCO|commission case)s?\b",
    re.IGNORECASE)
FID = re.compile(r"\b(?:bi:\d+-\d+|osm:(?:way|node|relation)/\d+|epoch:[^|,()]+?)(?=[\s|,()]|$)")

COLUMNS = ["site", "question", "state", "label", "mw_full", "on_the_fixed_list", "coverage",
           "open_in_the_check", "kept_for_hosts", "kept_for_other_utilities",
           "kept_for_other_utilities_by_reference_place", "kept_only_by_the_conservative_result",
           "relevant_not_kept_for", "retained_because", "status", "evidence_on_file", "avenues_tried",
           "leads_that_remain", "closes_as", "closing_class"]

OPENING = ("Counts are of questions the existing check models: sites in the inventory with a size and a "
           "setting that can vary. They are not a complete count of future-host eligibility questions, and "
           "they say nothing about load that is unsized, undated or missing from the inventory. No count is "
           "a target, a set, a support count or a sample size. The register decides nothing: each unresolved "
           "row names the avenue it would close under, and only the owner closes the pass.")

# Browser-list rows the name rule cannot match, mapped by hand. Each entry is a text that appears in
# the first cell of a section-5 row, and the site it names.
#   "340 Progress Circle": the row "The Cheyenne expansion building, 340 Progress Circle (Cheyenne
#   Light)" names no operator, so the name rule leaves it unmatched; the table of questions has one
#   site on the list for Cheyenne Light, bi:1123-0 (Lunavi, Laramie County, WY).
BROWSER_EXPLICIT = {"340 Progress Circle": "bi:1123-0"}

SPLITS = ("seventeen states of D-68", "first-run states", "states not in the check")


# ----------------------------------------------------------------------------
# Names
# ----------------------------------------------------------------------------

def table_question(attribution_name: str) -> str:
    """Map the attribution's question name to the table's."""
    if attribution_name not in QUESTION_NAMES:
        raise ValueError(f"unexpected question name in the attribution: {attribution_name!r}")
    return QUESTION_NAMES[attribution_name]


# ----------------------------------------------------------------------------
# The attribution JSON
# ----------------------------------------------------------------------------

def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError("attribution JSON: " + msg)


def index_check(attr: dict) -> dict:
    """Validate the attribution JSON and index it by (site, table question).

    Returns {"questions": {(fid, tq): {"state", "keepers", "relevant"}},
             "utilities": {uid: {"method", "why", "place_key", "host", "state"}},
             "hosts": {uid: name}, "states": set}.
    Raises ValueError on any shape it does not expect.
    """
    _need(isinstance(attr, dict), "top level is not an object")
    for k in ("hosts", "exact"):
        _need(k in attr, f"missing top-level key {k!r}")
    _need(isinstance(attr["hosts"], list), "hosts is not a list")
    hosts = {}
    for h in attr["hosts"]:
        _need(isinstance(h, dict) and isinstance(h.get("utility"), str) and isinstance(h.get("name"), str),
              f"host entry has an unexpected shape: {h!r}")
        _need(h["utility"] not in hosts, f"host listed twice: {h['utility']}")
        hosts[h["utility"]] = h["name"]
    _need(isinstance(attr["exact"], dict) and attr["exact"], "exact is not a non-empty object")

    questions: dict = {}
    utilities: dict = {}
    for st, e in attr["exact"].items():
        _need(isinstance(st, str) and re.fullmatch(r"[A-Z]{2}", st) is not None, f"unexpected state key {st!r}")
        _need(isinstance(e, dict), f"{st}: not an object")
        for k in ("questions", "utilities"):
            _need(k in e, f"{st}: missing {k!r}")
        _need(isinstance(e["questions"], list), f"{st}: questions is not a list")
        _need(isinstance(e["utilities"], dict), f"{st}: utilities is not an object")
        state_q = set()
        for q in e["questions"]:
            _need(isinstance(q, dict) and isinstance(q.get("fid"), str) and isinstance(q.get("question"), str),
                  f"{st}: question entry has an unexpected shape: {q!r}")
            _need(q["question"] in QUESTION_NAMES, f"{st}: unexpected question name {q['question']!r}")
            key = (q["fid"], table_question(q["question"]))
            _need(key not in questions, f"question {key} listed twice")
            questions[key] = {"state": st, "keepers": [], "relevant": []}
            state_q.add(key)
        for uid, u in e["utilities"].items():
            _need(isinstance(uid, str) and re.fullmatch(r"\d+:[A-Z]{2}", uid) is not None,
                  f"unexpected utility id {uid!r}")
            _need(uid.split(":")[1] == st, f"utility {uid} is filed under state {st}")
            _need(uid not in utilities, f"utility {uid} appears twice")
            _need(isinstance(u, dict), f"{uid}: not an object")
            for k in ("method", "why_conservative", "reference", "relevant_questions", "kept_questions"):
                _need(k in u, f"{uid}: missing {k!r}")
            _need(u["method"] in ("exact", "conservative"), f"{uid}: unexpected method {u['method']!r}")
            ref = u["reference"]
            _need(isinstance(ref, dict) and isinstance(ref.get("defined"), bool), f"{uid}: unexpected reference")
            if ref["defined"]:
                _need(ref.get("place") in PLACES, f"{uid}: unexpected reference place {ref.get('place')!r}")
                place_key = ref["place"]
            else:
                place_key = "undefined"
            utilities[uid] = {"method": u["method"], "why": u["why_conservative"], "place_key": place_key,
                              "host": uid in hosts, "state": st}
            rel, kept = set(), set()
            for name, bucket in (("relevant_questions", rel), ("kept_questions", kept)):
                _need(isinstance(u[name], list), f"{uid}: {name} is not a list")
                for x in u[name]:
                    _need(isinstance(x, dict) and isinstance(x.get("fid"), str)
                          and isinstance(x.get("question"), str), f"{uid}: {name} entry {x!r}")
                    _need(x["question"] in QUESTION_NAMES, f"{uid}: unexpected question name {x['question']!r}")
                    key = (x["fid"], table_question(x["question"]))
                    _need(key in state_q, f"{uid}: {name} names {key}, not an open question in {st}")
                    _need(key not in bucket, f"{uid}: {name} names {key} twice")
                    bucket.add(key)
            _need(kept <= rel, f"{uid}: keeps questions that are not relevant to it: {sorted(kept - rel)}")
            for key in rel:
                questions[key]["relevant"].append(uid)
            for key in kept:
                questions[key]["keepers"].append(uid)
    missing = [h for h in hosts if h not in utilities]
    _need(not missing, f"hosts not found among the utilities: {missing}")
    for v in questions.values():
        v["keepers"].sort()
        v["relevant"].sort()
    return {"questions": questions, "utilities": utilities, "hosts": hosts, "states": set(attr["exact"])}


def over_the_ceiling(why) -> bool:
    return isinstance(why, str) and "over the ceiling" in why


# ----------------------------------------------------------------------------
# The other inputs
# ----------------------------------------------------------------------------

def _read_csv(path: Path, required: list[str], what: str) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
        cols = rows[0].keys() if rows else []
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(f"{what}: missing columns {missing}")
    return rows


def load_attribution_csv(path: Path) -> tuple[dict, dict]:
    """Return ({site: {operator, county, mw_full, state}}, {uid: utility_name})."""
    rows = _read_csv(path, ["utility", "utility_name", "site", "question", "site_state", "operator", "county",
                            "mw_full"], "attribution CSV")
    sites: dict = {}
    names: dict = {}
    for r in rows:
        info = {"operator": r["operator"].strip(), "county": r["county"].strip(),
                "mw_full": r["mw_full"].strip(), "state": r["site_state"].strip()}
        if r["site"] in sites and sites[r["site"]] != info:
            raise ValueError(f"attribution CSV: site {r['site']} carries two different descriptions")
        sites[r["site"]] = info
        if r["utility"] in names and names[r["utility"]] != r["utility_name"]:
            raise ValueError(f"attribution CSV: utility {r['utility']} carries two names")
        names[r["utility"]] = r["utility_name"]
    return sites, names


def load_table(path: Path) -> dict:
    rows = _read_csv(path, ["site", "site_label", "state", "on_the_list_for", "question", "status",
                            "evidence_on_file", "still_open", "avenues_tried_in_the_log", "leads_that_remain"],
                     "table of questions")
    out = {}
    for r in rows:
        if r["question"] not in TABLE_QUESTIONS:
            raise ValueError(f"table of questions: unexpected question {r['question']!r} for {r['site']}")
        if r["status"] not in TABLE_STATUSES:
            raise ValueError(f"table of questions: unexpected status {r['status']!r} for {r['site']}")
        key = (r["site"], r["question"])
        if key in out:
            raise ValueError(f"table of questions: {key} appears twice")
        out[key] = r
    return out


def load_log_counts(path: Path) -> dict:
    rows = _read_csv(path, ["target", "avenue"], "log")
    counts: dict = defaultdict(Counter)
    for r in rows:
        if not r["avenue"].strip():
            raise ValueError(f"log: a row for {r['target']!r} has no avenue")
        counts[r["target"].strip()][r["avenue"].strip()] += 1
    return counts


def load_corrections(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("corrections: not a list")
    by_fid: dict = defaultdict(list)
    for c in data:
        if not isinstance(c, dict) or c.get("kind") not in CORRECTION_KINDS or not isinstance(c.get("fid"), str):
            raise ValueError(f"corrections: unexpected entry {c!r}")
        if not isinstance(c.get("why"), str):
            raise ValueError(f"corrections: entry for {c['fid']} has no why")
        by_fid[c["fid"]].append(c)
    return by_fid


def parse_browser_section_5(text: str) -> list[str]:
    """First cells of the data rows of the table in section 5 ("## 5." to the next "## ")."""
    m = re.search(r"^## 5\..*?$(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError("browser list: no section 5")
    cells = []
    header_seen = False
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        first = line.strip("|").split("|")[0].strip()
        if re.fullmatch(r":?-+:?", first):
            header_seen = True
            continue
        if not header_seen:
            continue  # the header row
        cells.append(first)
    if not cells:
        raise ValueError("browser list: section 5 has no table rows")
    return cells


def _host_token(host: str) -> str:
    h = re.sub(r"^City of\s+", "", host.strip())
    h = re.sub(r"\s*-\s*\([A-Z]{2}\)\s*$", "", h)
    words = h.split()
    return words[0] if words else ""


def _has_word(text: str, word: str) -> bool:
    return bool(word) and re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text) is not None


def match_browser_rows(cells: list[str], sites: dict) -> tuple[dict, list]:
    """Match section-5 first cells to sites. `sites` is {site: (label, host)}.

    Returns ({site: [cells]}, [unmatched cells]).
    """
    matched: dict = defaultdict(list)
    unmatched = []
    for cell in cells:
        hits = set(f.strip() for f in FID.findall(cell))
        for text, site in BROWSER_EXPLICIT.items():
            if text in cell:
                if site not in sites:
                    raise ValueError(f"browser list: the explicit mapping names {site}, not a site in the table")
                hits.add(site)
        if not hits:
            cands = []
            for site, (label, host) in sites.items():
                operator = label.split(",")[0].strip()
                if _has_word(cell, operator) and _has_word(cell, _host_token(host)):
                    cands.append(site)
            # a cell may name two operators (one site each); keep each operator only if it names one site
            by_op = defaultdict(list)
            for s in cands:
                by_op[sites[s][0].split(",")[0].strip()].append(s)
            hits = {v[0] for v in by_op.values() if len(v) == 1}
        if hits:
            for s in sorted(hits):
                matched[s].append(cell)
        else:
            unmatched.append(cell)
    return dict(matched), unmatched


@dataclass
class Inputs:
    check: dict
    csv_sites: dict
    csv_names: dict
    table: dict
    log_counts: dict
    corrections: dict
    browser_sites: set
    browser_unmatched: list
    browser_matched: dict
    d68: set
    texas_request: str
    named_avenues: dict = field(default_factory=dict)
    attribution_path: str = ""
    corrections_path: str = ""


def load_inputs(attribution, attribution_csv, questions=DEFAULT_QUESTIONS, log=DEFAULT_LOG,
                corrections=DEFAULT_CORRECTIONS, browser_list=DEFAULT_BROWSER_LIST, states_of_d68=DEFAULT_D68,
                texas_request="pending", named_avenues=DEFAULT_NAMED_AVENUES) -> Inputs:
    if not isinstance(texas_request, str) or not texas_request.strip():
        raise ValueError("--texas-request must be a non-empty status text")
    check = index_check(json.loads(Path(attribution).read_text()))
    csv_sites, csv_names = load_attribution_csv(Path(attribution_csv))
    table = load_table(Path(questions))
    table_sites = {}
    for (site, _q), r in table.items():
        table_sites[site] = (r["site_label"], r["on_the_list_for"])
    cells = parse_browser_section_5(Path(browser_list).read_text())
    matched, unmatched = match_browser_rows(cells, table_sites)
    d68 = {s.strip() for s in states_of_d68.split(",") if s.strip()}
    return Inputs(check=check, csv_sites=csv_sites, csv_names=csv_names, table=table,
                  log_counts=load_log_counts(Path(log)), corrections=load_corrections(Path(corrections)),
                  browser_sites=set(matched), browser_unmatched=unmatched, browser_matched=matched,
                  d68=d68, texas_request=texas_request,
                  named_avenues=load_named_avenues(Path(named_avenues)) if named_avenues else {},
                  attribution_path=str(attribution), corrections_path=str(corrections))


def load_named_avenues(path: Path) -> dict:
    """{(site, question or ""): [avenue, ...]} in file order; {} if the file is absent."""
    if not path.exists():
        return {}
    rows = _read_csv(path, ["site", "question", "avenue", "source"], "named avenues")
    out: dict = defaultdict(list)
    for r in rows:
        site, q, av = r["site"].strip(), r["question"].strip(), r["avenue"].strip()
        if not site or not av:
            raise ValueError(f"named avenues: a row has no site or no avenue: {r!r}")
        if q and q not in TABLE_QUESTIONS:
            raise ValueError(f"named avenues: unexpected question {q!r} for {site}")
        out[(site, q)].append(av)
    return dict(out)


# ----------------------------------------------------------------------------
# Rules
# ----------------------------------------------------------------------------

def coverage_label(state: str, open_in_check: bool, d68: set, check_states: set) -> str:
    if open_in_check:
        return COVERAGE_D68 if state in d68 else COVERAGE_FIRST
    return COVERAGE_NOT_OPEN if state in check_states else COVERAGE_NONE


def status_for(question: str, table_row, correction_kinds: set, open_in_check: bool):
    """Return (status, override reason or None)."""
    if table_row is None:
        if not open_in_check:
            raise ValueError("a row neither in the table nor open in the check has no status")
        return "unresolved", None
    status = table_row["status"]
    if question == "assignment":
        if "reopen" in correction_kinds and status != "unresolved":
            return "unresolved", "a reopen in the corrections in force"
        if "assign" in correction_kinds and "reopen" not in correction_kinds and status == "unresolved":
            return STATUS_ENTERED, "an assign in the corrections in force"
    return status, None


def retained_because(keepers, relevant, utils, open_in_check: bool, on_fixed_list: bool) -> list[str]:
    items = []
    others = [u for u in keepers if not utils[u]["host"]]
    if any(utils[u]["host"] for u in keepers):
        items.append(R_HOST)
    if any(utils[u]["place_key"] in ("comparison", "undefined") for u in others):
        items.append(R_COMPARISON)
    if any(utils[u]["place_key"] not in ("comparison", "undefined") for u in others):
        items.append(R_OTHER)
    if keepers and all(utils[u]["method"] != "exact" for u in keepers):
        not_ceiling = [u for u in keepers if not over_the_ceiling(utils[u]["why"])]
        if not_ceiling:
            raise ValueError(f"kept only by a conservative result that is not over the ceiling: {not_ceiling}")
        items.append(R_CEILING)
    if relevant and not keepers:
        items.append(R_REL_NOT_KEPT)
    if open_in_check and not relevant:
        items.append(R_REL_NONE)
    if on_fixed_list and not open_in_check:
        items.append(R_FIXED)
    if not items:
        raise ValueError("a row with no reason to be retained")
    return items


def avenue_never_run(r: dict):
    """Rule 1."""
    if r["on_the_fixed_list"] != "no":
        return None
    return AV_NEVER_RUN if r["avenues_tried"] == "none" else AV_NOT_IN_FULL


def _lead(r: dict) -> str:
    """The lead on file; a lead whose trimmed text starts with the word "None" or "none" is no lead.

    Whole word only, so a lead that starts "Nonesuch Road" stays a lead.
    """
    lead = r.get("leads_that_remain") or ""
    return "" if re.match(r"(?:None|none)\b", lead.strip()) else lead


def avenue_texas_request(r: dict, texas_request: str):
    """Rule 2. The status is free text, shown verbatim (for example "pending", "declined", or a sent date)."""
    if not isinstance(texas_request, str) or not texas_request.strip():
        raise ValueError("the Texas request status is empty")
    if r["state"] == "TX" and r["question"] == "assignment":
        return AV_TEXAS.format(texas_request)
    return None


def avenue_browser(r: dict, browser_sites: set):
    """Rule 3."""
    return AV_BROWSER if r["site"] in browser_sites else None


def avenue_load_only(r: dict):
    """Rule 4."""
    text = _lead(r) + "\n" + (r.get("still_open") or "")
    return AV_LOAD_ONLY if MIXED_FILING.search(text) else None


def avenue_lead(r: dict):
    """Rule 5: the lead verbatim, unless it is no lead (see _lead) or rule 4 matched inside it."""
    lead = _lead(r)
    if not lead.strip() or MIXED_FILING.search(lead):
        return None
    return AV_LEAD + lead


def rule_6_adds_nothing(r: dict, browser_sites: set) -> bool:
    """Rule 6: an operating-date row on the fixed list with no browser row, no mixed filing and no lead."""
    return (r["on_the_fixed_list"] == "yes" and r["question"] == "operating date"
            and avenue_browser(r, browser_sites) is None and avenue_load_only(r) is None
            and avenue_lead(r) is None and r["avenues_tried"] != "none")


def closes_as(r: dict, browser_sites: set, texas_request: str, named=()) -> tuple[str, list[str]]:
    """Return (closes_as text, avenue keys for the summary).

    `named` are avenues from the named-avenues file for this row, added verbatim after rules 1 to 5.
    """
    status = r["status"]
    if status == "resolved for part":
        part = True
    elif status.startswith("resolved"):
        return "resolved", []
    elif status == "not examined":
        return NOT_EXAMINED + ("" if r["open_in_the_check"] == "yes" else NOT_EXAMINED_NOT_OPEN), []
    elif status == "unresolved":
        part = False
    else:
        raise ValueError(f"unexpected status {status!r}")
    found = [a for a in (avenue_never_run(r), avenue_texas_request(r, texas_request), avenue_browser(r, browser_sites),
                         avenue_load_only(r), avenue_lead(r)) if a]
    for a in named:
        if a not in found:
            found.append(a)
    keys = [AV_LEAD_KEY if a.startswith(AV_LEAD) else a for a in found]
    if found:
        text = (PART_PREFIX if part else UNRESOLVED_PREFIX) + "; ".join(found)
    else:
        if r["avenues_tried"] == "none":
            raise ValueError(f"{r['site']} {r['question']}: no avenue applies and none was tried")
        text = PART_ALL_TRIED if part else AV_ALL_TRIED
        keys = [AV_ALL_TRIED]
    if r["open_in_the_check"] == "yes" and r["coverage"].startswith("first run"):
        text += "; " + AV_NO_LOOKUP
        keys.append(AV_NO_LOOKUP)
    return text, keys


def closing_class(status: str, avenues_tried: str, named: list) -> str:
    """One class per row. `named` is the row's list of named avenues (rules 1 to 5 and the named-avenues
    file), without the two entries that name no avenue (every avenue tried; no lookup in this state)."""
    if status.startswith("resolved") and status != "resolved for part":
        return CC_RESOLVED
    if status == "resolved for part":
        return CC_PART_NAMED if named else CC_PART_ALL
    if status == "not examined":
        return CC_NOT_EXAMINED
    if status != "unresolved":
        raise ValueError(f"unexpected status {status!r}")
    if avenues_tried == "none":
        if not named:
            raise ValueError("an unresolved row never looked up carries no named avenue")
        return CC_NEVER
    return CC_IN_PART if named else CC_ALL_TRIED


def display_path(path: str) -> str:
    """The path as written in the summary: relative to the project root when inside it, else absolute,
    normalised either way so that --check does not depend on how a path was spelled."""
    p = Path(path).resolve()
    try:
        return p.relative_to(PROJECT.resolve()).as_posix()
    except ValueError:
        return str(p)


def format_counts(counter) -> str:
    return "; ".join(f"{k} {counter[k]}" for k in sorted(counter) if counter[k])


# ----------------------------------------------------------------------------
# Building the register
# ----------------------------------------------------------------------------

@dataclass
class Result:
    rows: list
    overrides: list
    inputs: Inputs
    notes: list = field(default_factory=list)


def _split(state: str, inputs: Inputs) -> str:
    if state in inputs.d68:
        return SPLITS[0]
    if state in inputs.check["states"]:
        return SPLITS[1]
    return SPLITS[2]


def build_register(inputs: Inputs) -> Result:
    check = inputs.check
    utils = check["utilities"]
    table_sites = {s for (s, _q) in inputs.table}
    keys = set(inputs.table) | set(check["questions"])
    rows, overrides = [], []
    for site, question in keys:
        trow = inputs.table.get((site, question))
        cq = check["questions"].get((site, question))
        open_in = cq is not None
        on_fixed = site in table_sites
        if trow is not None and cq is not None and trow["state"] != cq["state"]:
            raise ValueError(f"{site}: the table says {trow['state']}, the check says {cq['state']}")
        state = trow["state"] if trow is not None else cq["state"]
        csv_site = inputs.csv_sites.get(site)
        if csv_site is not None and csv_site["state"] and csv_site["state"] != state:
            raise ValueError(f"{site}: the attribution CSV says {csv_site['state']}, the register says {state}")
        if trow is not None:
            label = trow["site_label"]
        elif csv_site is not None:
            label = ", ".join(p for p in (csv_site["operator"], csv_site["county"]) if p)
        else:
            label = ""
        keepers = cq["keepers"] if cq else []
        relevant = cq["relevant"] if cq else []
        host_names = [check["hosts"][u] for u in keepers if utils[u]["host"]]
        others = [u for u in keepers if not utils[u]["host"]]
        places = Counter(utils[u]["place_key"] for u in others)
        kinds = {c["kind"] for c in inputs.corrections.get(site, [])}
        status, why_override = status_for(question, trow, kinds, open_in)
        if why_override:
            overrides.append({"site": site, "question": question, "table_status": trow["status"],
                              "reported_status": status, "reason": why_override})
        if trow is not None:
            evidence = trow["evidence_on_file"]
        else:
            evidence = " ".join(c["why"] for c in inputs.corrections.get(site, [])
                                if CORRECTION_QUESTION[c["kind"]] == question)
        if trow is not None and trow["avenues_tried_in_the_log"].strip():
            avenues = trow["avenues_tried_in_the_log"].strip()
        elif inputs.log_counts.get(site):
            avenues = format_counts(inputs.log_counts[site])
        else:
            avenues = "none"
        row = {
            "site": site,
            "question": question,
            "state": state,
            "label": label,
            "mw_full": csv_site["mw_full"] if csv_site else "",
            "on_the_fixed_list": "yes" if on_fixed else "no",
            "coverage": coverage_label(state, open_in, inputs.d68, check["states"]),
            "open_in_the_check": "yes" if open_in else "no",
            "kept_for_hosts": "; ".join(sorted(host_names)),
            "kept_for_other_utilities": str(len(others)),
            "kept_for_other_utilities_by_reference_place": "; ".join(
                f"{p} {places[p]}" for p in PLACE_ORDER if places[p]),
            "kept_only_by_the_conservative_result":
                "yes" if keepers and all(utils[u]["method"] != "exact" for u in keepers) else "no",
            "relevant_not_kept_for": str(len(set(relevant) - set(keepers))),
            "retained_because": "",
            "status": status,
            "evidence_on_file": evidence,
            "avenues_tried": avenues,
            "leads_that_remain": trow["leads_that_remain"] if trow is not None else "",
            "closes_as": "",
        }
        row["_retained"] = retained_because(keepers, relevant, utils, open_in, on_fixed)
        row["retained_because"] = "; ".join(row["_retained"])
        ctx = dict(row, still_open=trow["still_open"] if trow is not None else "")
        row["closes_as"], row["_avenues"] = closes_as(ctx, inputs.browser_sites, inputs.texas_request)
        row["_ctx"] = ctx
        row["_split"] = _split(state, inputs)
        row["_comparison_utilities"] = sorted(
            u for u in others if utils[u]["place_key"] in ("comparison", "undefined"))
        rows.append(row)
    register_keys = {(r["site"], r["question"]) for r in rows}
    register_sites = {s for s, _q in register_keys}
    for (site, q) in inputs.named_avenues:
        if site not in register_sites:
            raise ValueError(f"named avenues: {site} is in no register row")
        if q and (site, q) not in register_keys:
            raise ValueError(f"named avenues: ({site}, {q}) is not a register row")
    for row in rows:
        named = inputs.named_avenues.get((row["site"], ""), []) + \
            inputs.named_avenues.get((row["site"], row["question"]), [])
        if named:
            row["closes_as"], row["_avenues"] = closes_as(row["_ctx"], inputs.browser_sites,
                                                          inputs.texas_request, named)
    for row in rows:
        del row["_ctx"]
        row["_named"] = [k for k in row["_avenues"] if k not in NOT_AVENUES]
        row["closing_class"] = closing_class(row["status"], row["avenues_tried"], row["_named"])
        if (row["closing_class"] in (CC_ALL_TRIED, CC_PART_ALL)) != (AV_ALL_TRIED in row["_avenues"]):
            raise ValueError(f"{row['site']} {row['question']}: closing_class and closes_as disagree")
    rows.sort(key=lambda r: (r["state"], r["site"], r["question"]))
    # keep COLUMNS first and in order; internal fields (leading underscore) after
    ordered = []
    for r in rows:
        o = {c: r[c] for c in COLUMNS}
        o.update({k: v for k, v in r.items() if k.startswith("_")})
        ordered.append(o)
    overrides.sort(key=lambda o: (o["site"], o["question"]))
    return Result(rows=ordered, overrides=overrides, inputs=inputs)


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def render_csv(rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _by_split(rows, values_of) -> dict:
    out = {"all": Counter()}
    for s in SPLITS:
        out[s] = Counter()
    for r in rows:
        for v in values_of(r):
            out["all"][v] += 1
            out[r["_split"]][v] += 1
    return out


def summary_tables(res: Result) -> dict:
    rows = res.rows
    return {
        "status": _by_split(rows, lambda r: [r["status"]]),
        "coverage": _by_split(rows, lambda r: [r["coverage"]]),
        "avenues": _by_split([r for r in rows if r["status"] == "unresolved"], lambda r: r["_named"]),
        "closing_class": _by_split(rows, lambda r: [r["closing_class"]]),
        "retained": _by_split(rows, lambda r: r["_retained"]),
    }


def reconciliation(res: Result) -> dict:
    unres = [r for r in res.rows if r["status"] == "unresolved"]
    by_class = Counter(r["closing_class"] for r in unres)
    by_number = {"0": 0, "1": 0, "2": 0, "3 or more": 0}
    alone_with: dict = {}
    for r in unres:
        k = len(r["_named"])
        by_number["3 or more" if k >= 3 else str(k)] += 1
        for av in r["_named"]:
            a, w = alone_with.get(av, (0, 0))
            alone_with[av] = (a + 1, w) if k == 1 else (a, w + 1)
    return {"unresolved": len(unres), "unresolved_by_class": {c: by_class[c] for c in UNRESOLVED_CLASSES},
            "by_number": by_number, "alone_with": alone_with,
            "avenue_mentions": sum(len(r["_named"]) for r in unres)}


def _avenue_order(texas_request: str) -> list:
    return [AV_NEVER_RUN, AV_NOT_IN_FULL, AV_TEXAS.format(texas_request), AV_BROWSER, AV_LOAD_ONLY, AV_LEAD_KEY]


def per_host_counts(res: Result) -> list:
    """[(host name, utility, kept questions, of which unresolved)] in the JSON's host order."""
    status = {(r["site"], r["question"]): r["status"] for r in res.rows}
    out = []
    for uid, name in res.inputs.check["hosts"].items():
        kept = [k for k, v in res.inputs.check["questions"].items() if uid in v["keepers"]]
        out.append((name, uid, len(kept), sum(1 for k in kept if status[k] == "unresolved")))
    return out


def _utility_name(uid: str, inputs: Inputs) -> str:
    return inputs.check["hosts"].get(uid) or inputs.csv_names.get(uid) or "name not in the inputs"


def _table(title_col: str, split: dict, order=None, total: bool = False) -> list[str]:
    # every key of a fixed order is shown, zeros included; anything outside the order follows, sorted
    keys = (list(order) + [k for k in sorted(split["all"]) if k not in order]) if order else sorted(split["all"])
    lines = [f"| {title_col} | all rows | " + " | ".join(SPLITS) + " |",
             "|---|---:|" + "---:|" * len(SPLITS)]
    for k in keys:
        lines.append(f"| {k} | {split['all'][k]} | " + " | ".join(str(split[s][k]) for s in SPLITS) + " |")
    if total:
        lines.append(f"| total | {sum(split['all'].values())} | "
                     + " | ".join(str(sum(split[s].values())) for s in SPLITS) + " |")
    return lines


def render_summary(res: Result) -> str:
    inputs = res.inputs
    t = summary_tables(res)
    rows = res.rows
    n = len(rows)
    utils = inputs.check["utilities"]
    out = [OPENING, "", "# Closing register of the verification pass: counts", "",
           f"Generated from the corrections file {display_path(inputs.corrections_path)} and the attribution "
           f"JSON {display_path(inputs.attribution_path)}.", ""]
    out += [f"Rows in the register: {n}. A row is one site and one question. The split columns are by the "
            f"row's state: the {len(inputs.d68)} states of D-68, the states the check ran for the first time on "
            f"2026-11-18 (descriptive counts only), and states the check did not run.", ""]
    out += ["## Rows by status", ""]
    out += _table("status", t["status"], order=["resolved", STATUS_ENTERED, "resolved for part", "unresolved",
                                                 "not examined"], total=True)
    out += ["", "## Rows by coverage", ""]
    out += _table("coverage", t["coverage"], order=[COVERAGE_D68, COVERAGE_FIRST, COVERAGE_NOT_OPEN,
                                                     COVERAGE_NONE], total=True)
    rec = reconciliation(res)
    n_unres = rec["unresolved"]
    part_rows = [r for r in rows if r["status"] == "resolved for part"]
    n_no_lookup = sum(1 for r in rows if r["status"] == "unresolved" and AV_NO_LOOKUP in r["_avenues"])
    out += ["", "## Unresolved rows by named avenue", "",
            f"Unresolved rows: {n_unres}. A row is counted under every avenue it carries, so the column adds "
            f"to {rec['avenue_mentions']} avenue entries, not to {n_unres}; the Reconciliation section below "
            f"shows the overlap. Each row's lead text is in the register itself. Rows resolved for part are "
            f"not counted here: {len(part_rows)}, by closing class in the Reconciliation section.", ""]
    out += _table("named avenue", t["avenues"], order=_avenue_order(inputs.texas_request))
    out += ["", f"Unresolved rows in states where no lookup was made (first-run states, open in the check): "
                f"{n_no_lookup}."]
    out += ["", "## Reconciliation", "",
            "Rows by closing class. Each row has exactly one class, so the column adds to the row total.", ""]
    out += _table("closing_class", t["closing_class"], order=list(CLOSING_CLASSES), total=True)
    out += ["", f"The last class, \"{CC_ALL_TRIED}\", is {OWNER_PHRASE}. It is kept apart from the rows "
                f"never looked up and from the rows looked up in part, which close with named avenues "
                f"unpursued.", "",
            "Unresolved rows by closing class:", "",
            "| closing_class | rows |", "|---|---:|"]
    out += [f"| {c} | {rec['unresolved_by_class'][c]} |" for c in UNRESOLVED_CLASSES]
    out += [f"| unresolved rows | {n_unres} |", "",
            "Unresolved rows by how many named avenues each carries:", "",
            "| named avenues on the row | rows |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in rec["by_number"].items()]
    out += [f"| unresolved rows | {n_unres} |", "",
            "Each named avenue, on the unresolved rows that carry it alone and with another:", "",
            "| named avenue | alone | with another | rows carrying it |", "|---|---:|---:|---:|"]
    order = _avenue_order(inputs.texas_request)
    avs = [a for a in order if a in rec["alone_with"]] + sorted(a for a in rec["alone_with"] if a not in order)
    for av in avs:
        a, w = rec["alone_with"][av]
        out.append(f"| {av} | {a} | {w} | {a + w} |")
    multi = rec["by_number"]["2"] + rec["by_number"]["3 or more"]
    out += ["", f"The table of unresolved rows by named avenue counts a row under every avenue it carries, so "
                f"it adds to {rec['avenue_mentions']} avenue entries against {n_unres} unresolved rows: "
                f"{multi} rows carry two or more avenues and {rec['by_number']['0']} rows carry none."]
    out += ["", "## Rows by reason retained", "",
            "A row is counted under every reason it carries.", ""]
    out += _table("retained_because", t["retained"], order=list(RETAINED_ORDER))
    comp_rows = [r for r in rows if R_COMPARISON in r["_retained"]]
    comp_sites = {r["site"] for r in comp_rows}
    comp_utils = sorted({u for r in comp_rows for u in r["_comparison_utilities"]})
    out += ["", "## Behind \"a consequential comparison question\"", "",
            "| what | count |", "|---|---:|",
            f"| rows | {len(comp_rows)} |",
            f"| sites | {len(comp_sites)} |",
            f"| utilities (not one of the listed hosts; comparison or undefined on the reference) that keep "
            f"them | {len(comp_utils)} |"]
    out += ["", "## The listed hosts", "",
            "| host | utility | kept questions | of which unresolved |", "|---|---|---:|---:|"]
    out += [f"| {name} | {uid} | {k} | {u} |" for name, uid, k, u in per_host_counts(res)]
    undefined = sorted(u for u, v in utils.items() if v["place_key"] == "undefined")
    out += ["", "## Utilities whose reference is undefined", "", f"Count: {len(undefined)}.", ""]
    out += ["| utility | name | method | one of the listed hosts |", "|---|---|---|---|"]
    out += [f"| {u} | {_utility_name(u, inputs)} | {utils[u]['method']} | {'yes' if utils[u]['host'] else 'no'} |"
            for u in undefined]
    ceiling = sorted(u for u, v in utils.items() if v["method"] == "conservative" and over_the_ceiling(v["why"]))
    other_cons = sorted(u for u, v in utils.items() if v["method"] == "conservative" and not over_the_ceiling(v["why"]))
    out += ["", "## Utilities over the search ceiling", "", f"Count: {len(ceiling)}.", ""]
    out += ["| utility | name | one of the listed hosts |", "|---|---|---|"]
    out += [f"| {u} | {_utility_name(u, inputs)} | {'yes' if utils[u]['host'] else 'no'} |" for u in ceiling]
    if other_cons:
        out += ["", f"Conservative for another reason: {len(other_cons)} ({', '.join(other_cons)})."]
    out += ["", "## Status overrides from the corrections in force", ""]
    if res.overrides:
        out += ["| site | question | table status | reported status | reason |", "|---|---|---|---|---|"]
        out += [f"| {o['site']} | {o['question']} | {o['table_status']} | {o['reported_status']} | {o['reason']} |"
                for o in res.overrides]
    else:
        out += ["None."]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--attribution", required=True)
    ap.add_argument("--attribution-csv", required=True)
    ap.add_argument("--out", required=True, help="output prefix; writes PREFIX.csv and PREFIX.md")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--corrections", default=str(DEFAULT_CORRECTIONS))
    ap.add_argument("--browser-list", default=str(DEFAULT_BROWSER_LIST))
    ap.add_argument("--named-avenues", default=str(DEFAULT_NAMED_AVENUES),
                    help="optional; if the file is absent, no named avenue is added")
    ap.add_argument("--states-of-d68", default=DEFAULT_D68)
    ap.add_argument("--texas-request", default="pending",
                    help="free text for the status of the request to the Texas commission, shown verbatim")
    ap.add_argument("--check", action="store_true",
                    help="regenerate in memory and exit 1 if the files on disk differ")
    a = ap.parse_args(argv)
    inputs = load_inputs(a.attribution, a.attribution_csv, a.questions, a.log, a.corrections, a.browser_list,
                         a.states_of_d68, a.texas_request, a.named_avenues)
    res = build_register(inputs)
    outputs = {Path(a.out + ".csv"): render_csv(res.rows), Path(a.out + ".md"): render_summary(res)}
    if a.check:
        differ = [p for p, text in outputs.items() if not p.exists() or p.read_text() != text]
        for p in differ:
            print(f"differs: {p}")
        return 1 if differ else 0
    for p, text in outputs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        print(p)
    print(f"rows: {len(res.rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
