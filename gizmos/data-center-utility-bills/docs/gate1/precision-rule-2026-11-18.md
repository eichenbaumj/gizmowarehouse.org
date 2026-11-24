# The precision rule, one rule for all sites (D-72 item 5; session 13, 2026-11-18)

Written by the session on 2026-11-18 and committed before any of the six host-site lookups was started and before Boardman's location was tied. Known when it was written: D-69's readings of the 23 layer-based verifications and the seven other records its section 4 names. No count of which records the rule would touch was made first, and none of its numbers was chosen for what it does to a site.

## 1. The ruling, in Joe's words (D-72 item 5)

> Evidence and precision. Five kilometres remains a search convention. Leads may add candidates but cannot verify delivery or exclude alternatives. Keep unsupported-input refusals. Write one precision rule for all sites: unresolved location or boundary uncertainty can defeat reliance on a map, but proximity cannot upgrade it to delivery evidence. Check each site against its actual supporting source. Correct the distance-bracket guarantees for geometric approximation, query semantics and incomplete responses.

The principle is Joe's. The working-out below is the session's, and each numbered choice in section 6 is a reading he can strike. It replaces no condition of D-61 section 2 (the six conditions, (a) to (f)), D-63 rules 1, 2, 5 and 6, or D-65 items 2 and 6. It says how the precision fields of D-69 are used with them.

## 2. Each record is first read against its actual supporting source

Every assignment record names what it rests on, as one of:

- **S. A statement about the site** (D-48: the operator's, the utility's, a government document's, or a dated article attributing it by name), or a regulator's certificate or order for the site or its parcel.
- **L. A territory listing** (D-48), with any layer used to check it (D-61 addendum, point 3).
- **M. A depiction of territory:** a layer under the six conditions, or a utility's own map under D-63 rule 6.
- **N. A lead:** a Texas layer, a compilation, an unofficial layer, a planning document, an allegation, a directory.
- **O. Nothing:** the inventory's own placement by the map.

The precision fields decide nothing for a record that rests on S. A site statement is not weakened by a drawn line nearby and not strengthened by a distant one. What such a record needs is the tie between the statement and the row (the same campus, the same address or parcel), which is D-65's tie rule and is checked there.

For L the fields are used as D-61's addendum uses a layer: to check the listing. If the layer shows another supplier at the location, a drawn line inside the location's extent, or a location that is not where the record says, the listing no longer suffices.

For M the fields are used as section 3 says. For N and O they add candidates and do nothing else.

## 3. When uncertainty defeats reliance on a depiction

A record of kind M stands only while all three of these hold. Each is read from fields already on the record. If a field is missing the condition is not shown, and a condition not shown is not met.

**P1. The location is resolved.** The point queried is tied to the facility under D-65's rule: the parcel record's own address or owner, or an operator-published facility address that matches the situs. A point that is not tied has uncertainty "unknown", and unknown defeats reliance. The record then goes back to what an untied point can support: candidates, found from the best location on file outward on the 5 km search convention.

**P2. The whole location is on one side of every drawn line.** For every layer the record relies on, the lower end of the distance to the nearest drawn line, after the allowances of section 5, is greater than the location's extent (for a tied parcel, the greatest distance from the queried point to the outline's vertices). Where it is not, the parcel may straddle a line as drawn, and the depiction does not say which side the facility's service is on. Reliance is defeated unless a separate record places the building or its service point on one side, and that record is then what the assignment rests on. Where there is no distance (a layer whose own edge and holes were not tested, a failed query, a map read by eye whose record gives no distance and no placement resolution), P2 is not shown. For a paper map under D-63 rule 6 the distance is the one its reproducibility record gives, and its allowance is the placement resolution that record states.

**P3. No unresolved boundary uncertainty.** Any of these is boundary uncertainty:
- *Conflicting geometry.* Another layer on file names a different supplier of retail electric delivery at the point or within the location's extent plus the allowance. A different spelling of one legal entity is not a conflict once the two names are tied to one EIA id in the record. A layer that by its publisher's own description does not hold the kind of utility in question is not in conflict by returning nothing. Everything else is a conflict, whatever the standing of the layer that disagrees, until a record resolves it: the regulator's certificate or order, the publisher's own correction, or the layer's own description. The session's judgment that a feature is a drawing defect is a reading and resolves nothing.
- *A stated tolerance larger than the margin.* Where the publisher gives a positional accuracy, it is added to the allowance in P2.
- *A boundary known to have moved.* Evidence on file of an annexation, a territory exchange or a re-certification between the layer's date and the years the assignment is read for (condition (f)).

A publisher's general disclaimer, or its silence on accuracy, does not by itself defeat reliance: D-65 accepted the Oregon, Nebraska and Minnesota layers knowing both. It stays on the record as a stated limitation, in words, wherever the assignment is described.

**What a defeated record becomes.** The depiction is a lead for that site. The assignment question is unresolved. Its candidates are every supplier any layer on file draws at the point or within the extent plus the allowance, with the 5 km search convention adding more, and delivery off the panel stays a setting. No supplier is excluded by it and no site leaves the panel on it.

## 4. What distance and agreement can never do

- A large distance to the nearest drawn line, agreeing probes, agreeing layers, or a point well inside a feature never raise a record's class, never turn a lead into a verification, never remove a candidate, and never stand in for any of the six conditions.
- A site close to a utility's line, substation, office or other customers is not thereby delivered by it. Proximity to infrastructure is a lead at most.
- Distance is used in one direction only: against reliance. "The nearest line is N km away" may be reported as a description. It is not offered as support.
- Unknown accuracy remains a stated limitation on every record of kind M that stands.

## 5. Allowances on a distance before it is compared with anything

These follow the correction to D-69 made the same day (the dated note under that entry has the reasons).

- *Geometry.* The lower end is multiplied by 0.985. The disc put to a layer is a 32-sided figure with its corners on the circle, so its sides come up to 0.5% inside the stated radius; metres are turned into degrees on a sphere with a flat local approximation, which is off by a few tenths of a percent, more at 20 km. The 1.5% is a margin over the sum, not a measured bound.
- *Datum and reprojection.* 5 m is subtracted. The point and the disc are sent as WGS 84 coordinates and the server turns them into the layer's own system by a transformation the request does not choose. *I am uncertain of the size of this offset: from general knowledge of the difference between WGS 84 and the North American datum, about one to two metres in the lower 48 states, not measured on any of these layers.* 5 m is a convention. A distance under 5 m shows nothing in either direction.
- *What no allowance covers.* A distance is a reading of the server's answers. It assumes the server evaluated each spatial question against the layer's full geometry and returned every feature that satisfies it. The first is tested once per layer, with a one-metre disc; the second cannot be seen from outside. A truncated answer can only make a disc fail early, which shortens a distance. A silently incomplete answer could lengthen one, and nothing in the method would show it. So a distance is described as "on the server's answers", and where the point's own answer is empty, "nothing within N km" is not claimed.
- *What it measures.* The nearest line of any feature as drawn, a seam between two features of one utility included. It is not a distance to the legal or historical boundary.

## 6. The session's readings, for Joe to keep or strike

1. An untied point defeats reliance outright (P1), and is not rescued by any distance.
2. The comparison in P2 is with the parcel's extent, taken as the greatest distance from the queried point to the outline's vertices. That is conservative for a facility that occupies part of a large parcel.
3. A conflict with a layer of lower standing still counts until a record resolves it (P3).
4. A general disclaimer or silence does not defeat reliance and stays a stated limitation (P3).
5. The allowances of section 5: 1.5% and 5 m, both margins and neither a bound.
6. Condition (d)'s four probes at 250 m stay as written. P2 is applied as well as (d), not in place of it.
7. A record that rests on a site statement is outside sections 3 to 5 altogether.

## 7. How it is applied, and to what

- **The seven sites of session 13's lane C** (`bi:817-0`, `bi:848-0`, `bi:910-0`, `bi:911-0`, `epoch:Microsoft SAT14`, `epoch:Microsoft SAT40`, and Boardman's `bi:821-0`): each record written this session states its kind (S, L, M, N or O), and for M the three conditions with their values and the result in words: "reliance stands, with unknown accuracy as a stated limitation", "reliance defeated: which condition", or "does not rely on a depiction".
- **Every record already on file** (`verified/pass_c_layer_conditions.csv`, 73 sites): the rule is read against the fields on file by a script, into a table of what the rule says about each. **No class on file is changed by that table.** A class change moves who counts as verified, so the table goes to Joe with the readings above, and the classes change when he has kept or struck them.
