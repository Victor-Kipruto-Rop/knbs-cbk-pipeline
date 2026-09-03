"""
Validates any tidy indicator DataFrame (the shared shape produced by every
cleaner) before it's allowed into staging. Failures here are what should
trip an alert, not a value silently entering the warehouse wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import TIDY_COLUMNS

REQUIRED_COLUMNS = TIDY_COLUMNS
NON_NULLABLE_COLUMNS = ["indicator_code", "period_date", "value", "source_id"]


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise ValueError("Validation failed:\n" + "\n".join(self.errors))


def validate_tidy_frame(df: pd.DataFrame, *, source_id: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Schema shape
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"missing required columns: {missing_cols}")
        return ValidationResult(ok=False, errors=errors)

    # 2. Completeness
    if df.empty:
        errors.append(f"'{source_id}' produced zero rows — likely an upstream layout change")
        return ValidationResult(ok=False, errors=errors)

    # 3. Nulls in required fields
    for col in NON_NULLABLE_COLUMNS:
        null_count = int(df[col].isna().sum())
        if null_count:
            errors.append(f"column '{col}' has {null_count} null value(s)")

    # 4. Dtype sanity on value
    non_numeric = df[~df["value"].apply(lambda v: isinstance(v, (int, float)))]
    if not non_numeric.empty:
        errors.append(f"column 'value' has {len(non_numeric)} non-numeric entries")

    # 5. Duplicates on the natural key
    natural_key = ["indicator_code", "period_date", "source_id"]
    dupes = df[df.duplicated(subset=natural_key, keep=False)]
    if not dupes.empty:
        errors.append(
            f"{len(dupes)} duplicate rows on natural key {natural_key} — "
            "extractor or cleaner is producing the same period twice"
        )

    # 6. Soft range check on percent-unit values (warning, not a hard failure —
    #    rates can legitimately spike, but a 3-digit "percent" is almost
    #    always a parsing bug, e.g. stray currency symbol).
    percent_rows = df[df["unit"] == "percent"]
    out_of_range = percent_rows[(percent_rows["value"] < -20) | (percent_rows["value"] > 100)]
    if not out_of_range.empty:
        warnings.append(
            f"{len(out_of_range)} 'percent' rows outside [-20, 100] — verify parsing"
        )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
