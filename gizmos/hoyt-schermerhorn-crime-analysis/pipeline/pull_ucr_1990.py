"""1990 robbery rate for every US city over 550,000 people, from the FBI's UCR offenses-known file as compiled by
Jacob Kaplan (openICPSR 100707, "Uniform Crime Reporting Program Data: Offenses Known and Clearances by Arrest").
Writes crosswalks/ucr_1990_large_city_robbery.csv, which stage 11 ranks for the opening sentence. The 550,000
cutoff matches the 2025 MCCA comparison later in the same paragraph. Needs pyreadr (pip install pyreadr).

    python3 pull_ucr_1990.py ~/Downloads/offenses_known_rds_1960_2024_year.zip
"""
import sys, zipfile, tempfile
from pathlib import Path
import pyreadr
import config

MIN_POP = 550_000
src = Path(sys.argv[1]).expanduser()
with tempfile.TemporaryDirectory() as tmp:
    with zipfile.ZipFile(src) as z:
        name = next(n for n in z.namelist() if n.endswith(".rds"))
        z.extract(name, tmp)
    df = pyreadr.read_r(str(Path(tmp) / name))[None]
d = df[(df.year == 1990) & (df.agency_type == "local police department") & (df.population >= MIN_POP)]
# a partial-year reporter would understate its rate and could hand NYC a rank it didn't earn
assert (d.number_of_months_reported == 12).all(), d[d.number_of_months_reported != 12][["agency_name", "state_abb"]]
out = d[["ori", "agency_name", "state_abb", "population", "actual_robbery_total", "actual_murder"]].rename(
    columns={"actual_robbery_total": "robbery", "actual_murder": "murder"}).astype({"population": int, "robbery": int, "murder": int})
out["robbery_per_100k"] = (out.robbery / out.population * 1e5).round(1)
out = out.sort_values("robbery_per_100k", ascending=False)
path = config.CROSSWALKS / "ucr_1990_large_city_robbery.csv"
out.to_csv(path, index=False)
print(f"{len(out)} cities >= {MIN_POP:,} -> {path.name}"); print(out.head(5).to_string(index=False))
