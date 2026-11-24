"""The availability audit's fixed vocabulary (docs/gate1/availability-audit-route.md; Joe's ruling of 2026-11-16).

Constants only: this module opens no file and imports nothing from the pipeline, so the audit (P2) can
import it without reaching the panel build or anything that reads revenue.

The reason a utility-year is not usable is its FIRST APPLICABLE EXCLUSION REASON: the first code in
REASON_ORDER whose test holds. Reasons already knowable from the quantities file come first, so a reason
that depends on revenue or price is reached only by a utility-year that passes every quantity test. Counts
by first applicable exclusion reason therefore depend on this order: a utility-year that fails several
tests is counted once, under the first.
"""
from __future__ import annotations

DEFINITION_VERSION = "2026-11-16.2"           # .2: the supplier-row status (D-72 item 2)

# Schema versions of every output (D-72 item 2). The audit and the preservation step refuse a record whose version is
# not the one below. Record, sidecar and manifest moved up one under D-76: each now carries the hash of the
# authorizing entry's text.
SCHEMA_VERSIONS = {"quantities_columns": 2, "p1_record": 4, "mask": 2, "sidecar": 4, "preserved_manifest": 3}
# P1's record and P2's sidecar are first written "in_progress" for the attempt, before anything they describe is
# replaced, and rewritten "completed" last; a reader accepts only "completed" (D-74; D-75).
IN_PROGRESS, COMPLETED = "in_progress", "completed"

# The analysis's filter, as the code writes it (power_simulation.py: `p.meets_size_floor & (p.res_price > 0)`).
ANALYSIS_FILTER = "meets_size_floor & (res_price > 0), a missing price failing"

NOT_IN_PANEL = "not_in_panel"                     # assigned by the audit (P2): the utility-year has no row in the panel
NO_EXCLUSION = "none"                             # the utility-year is usable

# Assigned by the panel build (P1), in this order. Expressions refer to pipeline/electricity/panel.py.
REASON_ORDER = (
    ("no_residential_sales", "not (res_mwh > 0)", "quantities"),
    ("under_customer_floor", "not meets_size_floor (res_customers >= 2000)", "quantities"),
    ("no_supply_price", "res_mwh_delivery > 0 and no supply price (supply_price_basis == 'none_available')", "quantities"),
    ("bundled_revenue_missing", "res_mwh_bundled > 0 and residential bundled revenue missing", "revenue"),
    ("delivery_revenue_missing", "res_mwh_delivery > 0 and residential delivery revenue missing", "revenue"),
    ("price_not_above_zero", "the constructed price is not above zero", "price"),
)
BUILD_REASONS = tuple(code for code, _, _ in REASON_ORDER)
ALL_CODES = (NOT_IN_PANEL,) + BUILD_REASONS + (NO_EXCLUSION,)

# Columns the panel build adds to the quantities file.
FLAG_COL = "res_price_usable"
REASON_COL = "res_price_first_exclusion_reason"
UNKNOWN_COL = "res_rows_imputation_status"        # "known" or "unknown": whether any contributing residential row had no imputation flag
IMPUTATION_STATUS = ("known", "unknown")
# Whether the state's observed supplier rows, where they set this unit-year's supply price, include any with no
# imputation flag. "not_used" where the price does not use them (D-72 item 2).
SUPPLIER_COL = "supplier_rows_imputation_status"
SUPPLIER_STATUS = ("known", "unknown", "not_used")
NEW_QUANTITY_COLS = (FLAG_COL, REASON_COL, UNKNOWN_COL, SUPPLIER_COL)

# The input hashes a reader requires, each present and well formed (D-76, G2). Their values are what the writer
# recorded: no later step can recompute the raw sales or outcome hashes, because no later step may read those files.
P1_INPUT_HASHES = ("sales", "succession", "quantities", "outcomes")
P2_INPUT_HASHES = ("quantities", "p1_record")
# The fields of P1's record the sidecar copies under "flag_build". The preservation step requires each copy to equal
# P1's record (D-76, G2: duplicated fields are reconciled).
SIDECAR_FLAG_BUILD_KEYS = ("run_id", "inputs_sha256", "checks", "git_commit", "authorized_by", "sandbox_profile_sha256")

# P1's five checks, by name. P2 and the preservation step require exactly these, each true (D-72 item 2).
P1_CHECKS = ("outcomes_identical", "by_unit_identical", "existing_quantity_columns_identical",
             "flag_equals_analysis_filter", "reasons_valid_and_consistent")

# What each step's pin list covers (D-72 item 2: pin the actual approved code and isolation profiles). Paths are
# relative to the gizmo folder. The execution instruction's ledger entry carries a hash for every file and a
# version for every library; each step refuses to run if anything it uses differs. The probe file is not pinned:
# the sandbox makes it unreadable, which is its purpose, and its content carries nothing.
PIN_HEADER = "availability-pins v1"
P1_PROFILE, P2_PROFILE = "pipeline/electricity/sandbox/p1.sb", "pipeline/electricity/sandbox/p2.sb"
P1_PINNED = ("pipeline/__init__.py", "pipeline/electricity/__init__.py", "pipeline/electricity/write_usable_flag.py",
             "pipeline/electricity/access_guard.py", "pipeline/electricity/availability_codes.py",
             "pipeline/electricity/availability_records.py",
             "pipeline/electricity/panel.py", "pipeline/electricity/succession.py", "pipeline/electricity/succession.csv",
             "pipeline/electricity/run_availability.sh", P1_PROFILE)
P2_PINNED = ("pipeline/__init__.py", "pipeline/electricity/__init__.py", "pipeline/electricity/audit_availability.py",
             "pipeline/electricity/access_guard.py", "pipeline/electricity/availability_codes.py",
             "pipeline/electricity/availability_records.py",
             "pipeline/electricity/run_availability.sh", P2_PROFILE)
PRESERVE_PINNED = ("pipeline/__init__.py", "pipeline/electricity/__init__.py", "pipeline/electricity/preserve_availability.py",
                   "pipeline/electricity/access_guard.py", "pipeline/electricity/availability_codes.py",
                   "pipeline/electricity/availability_records.py")
P1_LIBRARIES = ("python", "numpy", "pandas", "pyarrow", "duckdb")
P2_LIBRARIES = ("python", "pandas", "pyarrow")
PRESERVE_LIBRARIES = ("python",)

# Columns the audit may read, and only these (Joe's ruling, item 4: the four quantity columns are for consistency checks only).
KEYS = ("utility_id_eia", "state", "year")
CHECK_COLS = ("res_mwh", "meets_size_floor", "supply_price_basis", "res_mwh_delivery")
AUDIT_READ_COLS = KEYS + NEW_QUANTITY_COLS + CHECK_COLS

# The audit's output.
PANEL_YEARS = tuple(range(2001, 2026))            # every panel year (Joe's ruling, item 4)
MASK_COLUMNS = ("utility_id_eia", "state", "year", "usable", "first_exclusion_reason", "imputation_status",
                "supplier_rows_imputation_status")
MASK_IMPUTATION_STATUS = IMPUTATION_STATUS + ("no_rows",)
MASK_SUPPLIER_STATUS = SUPPLIER_STATUS + ("no_rows",)
