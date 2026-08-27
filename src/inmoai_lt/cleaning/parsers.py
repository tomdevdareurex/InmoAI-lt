"""Pure scalar parsers: numbers, areas, dates, years, text folding.

None of these functions mutate input; all return new values. `parse_decimal` never
fabricates ``0`` on failure -- it returns ``None``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd

# Space variants used as thousands separators by the scraper / source site.
_THOUSANDS_SEPARATORS = re.compile(r"[\s\u00a0\u2009\u202f]")
_UNIT_SUFFIXES = re.compile(r"(m²|m2|ha|a|€|eur)\s*$", re.IGNORECASE)
_NUMERIC_CHARS = re.compile(r"[^0-9,.\-]")

_YEAR_STATYBA_RE = re.compile(r"(\d{4})\s*statyba", re.IGNORECASE)
_YEAR_RENOVACIJA_RE = re.compile(r"(\d{4})\s*renovacija", re.IGNORECASE)
_YEAR_BARE_RE = re.compile(r"^\s*(\d{4})\s*$")

_REDACTED_MARKER = "[REDACTED_"


def parse_decimal(raw: object) -> Optional[float]:
    """Parse a Lithuanian-formatted decimal string into a float.

    Handles comma decimal separators (``"54,02"``), space / NBSP / thin-space thousands
    separators (``"1 000"``), and unit suffixes (``m²``, ``a``, ``ha``, ``€``).
    Returns ``None`` on any parse failure -- never fabricates ``0``.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        if pd.isna(raw):
            return None
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    text = _UNIT_SUFFIXES.sub("", text).strip()
    text = _THOUSANDS_SEPARATORS.sub("", text)
    text = _NUMERIC_CHARS.sub("", text)
    if not text or text in {"-", "."}:
        return None
    # Lithuanian decimal separator is a comma; there are no thousands commas left
    # at this point because spaces were already stripped.
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(raw: object) -> Optional[int]:
    """Parse an integer, tolerating the same formatting as `parse_decimal`."""
    value = parse_decimal(raw)
    if value is None:
        return None
    try:
        return int(round(value))
    except (ValueError, OverflowError):
        return None


def to_nullable_int_series(series: pd.Series) -> pd.Series:
    """Coerce a series to pandas nullable Int64, parsing each value defensively."""
    parsed = series.map(parse_int)
    return pd.array(parsed, dtype="Int64")


def parse_years(metai_raw: object) -> tuple[Optional[int], Optional[int]]:
    """Parse the `Metai` attribute into (construction_year, renovation_year).

    Formats observed:
      - ``"2013"``                             -> (2013, None)
      - ``"1960 statyba, 2026 renovacija"``     -> (1960, 2026)
    """
    if metai_raw is None:
        return None, None
    text = str(metai_raw).strip()
    if not text:
        return None, None

    construction: Optional[int] = None
    renovation: Optional[int] = None

    m_statyba = _YEAR_STATYBA_RE.search(text)
    if m_statyba:
        construction = int(m_statyba.group(1))
    m_renovacija = _YEAR_RENOVACIJA_RE.search(text)
    if m_renovacija:
        renovation = int(m_renovacija.group(1))

    if construction is None:
        m_bare = _YEAR_BARE_RE.match(text)
        if m_bare:
            construction = int(m_bare.group(1))

    return construction, renovation


def normalize_text(raw: object) -> Optional[str]:
    """Collapse whitespace / NBSP, strip, NFC-normalize. Empty -> None.

    Never strips Lithuanian diacritics from the stored value.
    """
    if raw is None:
        return None
    if isinstance(raw, float) and pd.isna(raw):
        return None
    text = str(raw)
    text = text.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def fold_key(raw: object) -> Optional[str]:
    """Diacritic-folded, casefolded key for internal matching only.

    NFKD-normalizes, strips combining marks, casefolds. Must never be written to output.
    """
    text = normalize_text(raw)
    if text is None:
        return None
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def contains_redacted_marker(raw: object) -> bool:
    """True if the text contains a `[REDACTED_...]` privacy-redaction marker."""
    if raw is None:
        return False
    if isinstance(raw, float) and pd.isna(raw):
        return False
    return _REDACTED_MARKER in str(raw)


def parse_iso_date(raw: object) -> pd.Timestamp:
    """Parse an ISO date string ('date only', no time component) to a Timestamp."""
    if raw is None:
        return pd.NaT
    return pd.to_datetime(raw, errors="coerce")


def parse_iso_datetime_utc(raw: object) -> pd.Timestamp:
    """Parse an ISO 8601 timestamp (may include offset) to a tz-aware UTC Timestamp."""
    if raw is None:
        return pd.NaT
    ts = pd.to_datetime(raw, errors="coerce", utc=True)
    return ts
