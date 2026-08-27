"""Duplicate detection. Two tiers, both counted, neither destructive on the clean output."""

from __future__ import annotations

from typing import Any

import pandas as pd


def flag_identity_duplicates(df: pd.DataFrame, report: Any = None) -> pd.DataFrame:
    """Tier 1: duplicate `listing_id` -> keep first, drop the rest.

    Defensive guard for future multi-run inputs; measured baseline is 0 dupes.
    """
    result = df.copy()
    is_dup = result.duplicated(subset=["listing_id"], keep="first")
    dropped_ids = result.loc[is_dup, "listing_id"].tolist()
    if report is not None:
        report.record_identity_duplicates(count=int(is_dup.sum()), listing_ids=dropped_ids)
    return result.loc[~is_dup].reset_index(drop=True)


def flag_content_duplicates(
    df: pd.DataFrame,
    content_key: list[str],
    area_round_dp: int,
    report: Any = None,
) -> pd.DataFrame:
    """Tier 2: content-based duplicate groups.

    Rows where any key part is NA are never grouped (NA never equals NA in the group-by
    sense used here). For groups of size > 1, assigns `duplicate_group_id`, marks
    exactly one row `is_duplicate_primary=True` (latest `listing_updated_date`; tie ->
    higher `views_count`; tie -> lower `listing_id`), the rest `is_duplicate=True`.
    All rows are kept in the output -- nothing is deleted here.
    """
    result = df.copy()
    result["is_duplicate"] = pd.array([False] * len(result), dtype="boolean")
    result["is_duplicate_primary"] = pd.array([False] * len(result), dtype="boolean")
    result["duplicate_group_id"] = pd.array([pd.NA] * len(result), dtype="Int64")

    # Build the key frame, substituting a rounded area column where requested.
    key_parts = []
    for col in content_key:
        if col == "total_area_sqm_rounded":
            key_parts.append(pd.to_numeric(result["total_area_sqm"], errors="coerce").round(area_round_dp))
        elif col in result.columns:
            key_parts.append(result[col])
        else:
            key_parts.append(pd.Series([pd.NA] * len(result), index=result.index))
    key_frame = pd.concat(key_parts, axis=1)
    key_frame.columns = content_key

    valid_key_mask = key_frame.notna().all(axis=1)

    group_count = 0
    duplicate_row_count = 0
    groups_log = []

    if valid_key_mask.any():
        # Group by the tuple of key values directly (handles mixed dtypes robustly).
        key_tuples = list(key_frame.loc[valid_key_mask].itertuples(index=False, name=None))
        idx_by_key: dict[tuple, list] = {}
        for idx, key_tuple in zip(result.index[valid_key_mask], key_tuples):
            idx_by_key.setdefault(key_tuple, []).append(idx)

        next_group_id = 1
        for key_tuple, idxs in idx_by_key.items():
            if len(idxs) < 2:
                continue
            group_count += 1
            group_df = result.loc[idxs]
            sort_cols = ["listing_updated_date", "views_count", "listing_id"]
            sortable = group_df.copy()
            sortable["_updated"] = pd.to_datetime(sortable["listing_updated_date"], errors="coerce")
            sortable["_views"] = pd.to_numeric(sortable["views_count"], errors="coerce").fillna(-1)
            sortable = sortable.sort_values(
                by=["_updated", "_views", "listing_id"],
                ascending=[False, False, True],
            )
            primary_idx = sortable.index[0]
            other_idxs = [i for i in idxs if i != primary_idx]

            result.loc[idxs, "duplicate_group_id"] = next_group_id
            result.loc[primary_idx, "is_duplicate_primary"] = True
            result.loc[other_idxs, "is_duplicate"] = True
            duplicate_row_count += len(other_idxs)
            groups_log.append(
                {
                    "group_id": next_group_id,
                    "listing_ids": group_df["listing_id"].tolist(),
                    "primary_listing_id": result.loc[primary_idx, "listing_id"],
                }
            )
            next_group_id += 1

    if report is not None:
        report.record_content_duplicates(
            group_count=group_count,
            duplicate_row_count=duplicate_row_count,
            groups=groups_log,
        )

    return result
