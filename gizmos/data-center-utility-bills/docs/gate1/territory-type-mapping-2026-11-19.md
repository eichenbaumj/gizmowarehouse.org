# Territory TYPE mapping (R4 access 1, D-107), 2026-11-19

Written by a build agent of session 21 (job 4). **Every class below is the agent's reading, not a ruling.** Joe's words (D-107): "For territory TYPE values, document the mapping and build under clearly supported classifications marked as your reading. Report ambiguous values without guessing; do not let them silently determine inclusion."

## The layer

`data/raw/territories/retail_service_territories.geojson`, in no fetch manifest. As found on 2026-11-19: 16,836,083 bytes, SHA-256 `03eefefba04e4c80ea61ab81d8acb4ba12551903de8f5e490630d524cec84b0e`.

Access 1 read the field `TYPE` alone (`pyogrio.read_dataframe(path, columns=["TYPE"], read_geometry=False)`, through `reconciliation_inputs.read_type_values`) and kept its distinct values. The polygon counts below come from access 2, which read `ID`, `TYPE` and geometry by a column list.

## The reading of "clearly supported"

The session's reading, carried here: a value is `retail` only if its own text names retail service, and `wholesale_only` only if its own text names wholesale only. Anything else is `ambiguous`. A value is not classed from what a kind of utility usually does. A value that is missing, or that is not in the list below, is `ambiguous` in the code.

## The values

2,931 polygons, every one with a `TYPE` (none missing). "Sites decided under row U" is the number of inventory sites whose row U outcome turns on how the value is classed, for some classing of the other ambiguous values among that site's polygons; the lists are in the summary file. Under row C the count is zero for every value.

| `TYPE` value | Polygons | Class (the agent's reading) | Why | Sites decided under row U |
|---|---:|---|---|---:|
| COMMUNITY CHOICE AGGREGATOR | 1 | ambiguous | names an aggregation arrangement; does not say retail or wholesale-only service | 3 |
| COOPERATIVE | 553 | ambiguous | names an ownership type | 735 |
| FEDERAL | 6 | ambiguous | names an ownership type | 464 |
| INVESTOR OWNED | 157 | ambiguous | names an ownership type | 1,886 |
| MUNICIPAL | 459 | ambiguous | names an ownership type | 328 |
| MUNICIPAL MKTG AUTHORITY | 2 | ambiguous | "marketing" does not say retail or wholesale-only service | 10 |
| NOT AVAILABLE | 1,685 | ambiguous | names no type | 221 |
| POLITICAL SUBDIVISION | 54 | ambiguous | names a governance type | 179 |
| STATE | 13 | ambiguous | names an ownership type | 42 |
| WHOLESALE POWER MARKETER | 1 | ambiguous | names a wholesale marketer, not wholesale only (see below) | 0 (no inventory site falls in it) |

By class: retail 0, wholesale-only 0, ambiguous 2,931. Of the 2,220 sites with a point, 2,217 fall in at least one polygon, and every one of them is decided under row U by at least one ambiguous value. That a value names an ownership type is not read as retail, though such utilities usually sell at retail, because that would be classing from outside knowledge.

## What this means

No value names retail service, and none names wholesale only. **The field does not mark wholesale-only territories by name,** and it does not mark retail territories by name either: eight of the ten values name an ownership or governance type (or nothing), one names an aggregation arrangement, and one names a wholesale marketer.

So, under this reading, row U's rule "retail providers before wholesale-only territories" (Ryu and Hiatt, p. 5) cannot be applied from this layer's `TYPE` field. That is a finding, not something repaired here. The incidence table carries every polygon as `ambiguous`, and `data/frozen/reconciliation_polygon_incidence_summary.json` lists, for each value, the sites whose row U outcome would turn on how it is classed. Row C's rule (the smallest polygon over every territory) does not read the type, so no site's row C outcome turns on it; the summary computes that and does not assume it.

`WHOLESALE POWER MARKETER` is the nearest candidate for `wholesale_only`: it is the only value whose text names wholesale. The agent did not class it so, because the text names a wholesale marketer and not wholesale only; reading it as "no retail service" adds "only" from outside the text. Whether to class it `wholesale_only`, and whether any value may be classed `retail`, are for the session and Joe. I am uncertain whether the paper's own copy of the layer carried the same field and values; the paper gives no vintage, and ours is a later copy (bounded read of row U, element 6). Row C's paper counts 3,805 territories (D-106 section 6); this copy has 2,931 polygons, so it is not the layer row C's paper used either.
