"""Deferred enrichment hooks -- signatures only, no implementation.

See `enrichment/README.md` for what each hook needs and why it is deferred. Nothing
in this module is called by `pipeline.run_pipeline`; the cleaning pipeline's output is
self-contained and does not depend on enrichment.
"""

from __future__ import annotations

import pandas as pd


def enrich(df: pd.DataFrame, *, lat_col: str = "latitude", lon_col: str = "longitude") -> pd.DataFrame:
    """Deferred: join census/socio-economic, POI-distance and district-geometry features.

    Not implemented. Calling this raises `NotImplementedError` rather than silently
    returning `df` unchanged, so a future caller cannot mistake "not yet built" for
    "nothing to add". See `enrichment/README.md` for the data each planned enrichment
    needs and why it is out of scope for this pass.
    """
    raise NotImplementedError(
        "enrichment.enrich() is a deferred hook -- see src/inmoai_lt/enrichment/README.md"
    )
