# Modelling layer

_Last reconciled: 2026-08-30_

Price models for the four Vilnius market segments, and the cap-rate cross-prediction they
exist to support. The cleaning pipeline (`README.md`) stops at analysis-ready segment files;
everything described here starts from those files and never touches raw data.

---

## 1. Why this exists

The question this layer answers is not "what is this flat worth" but:

> **If I bought this for-sale listing, what rent could it achieve, and what yield is that?**

Which requires two models per property type — a sale model and a rent model — and the ability
to score a *sale* listing with the *rent* model. Everything else in the design follows from
that requirement.

The approach is adapted from the Chilean **InmoAI** work, specifically
`InmoAI/models/MAIN_Tomas_feature_selection_2.3._neighbours_percentages_departamento.ipynb`,
which already computed `cap_rate = price_uf_pred_rent * 12 / price_uf`. The cap-rate use case
is a port, not an invention. The Chilean `suputilval` (useful surface) maps onto the
Lithuanian `total_area_sqm`; that one correspondence carries most of the reused logic across.

---

## 2. The four segments

A segment is `<property_type>_<listing_type>`. They are modelled separately and never
pooled — rent is EUR/month and sale is EUR, so a shared target distribution would be
meaningless.

| Segment | Analysis rows | Train / held-out | Notes |
|---|---|---|---|
| `apartment_sale` | 3036 | 2428 / 608 | the deepest segment |
| `apartment_rent` | 1629 | 1303 / 326 | supplies rent estimates for apartment cap rates |
| `house_sale` | 814 | 651 / 163 | wide price dispersion |
| `house_rent` | 96 | 76 / 20 | **low-n**, see §8 |

`house_rent` existed as `data/raw/houses_rent_vilnius.csv` all along but was not registered in
`config/cleaning.yaml`, so no segment file was produced. Registering it was a four-line config
change; the bounds for `house_rent` were already present in that file.

---

## 3. How four models avoid four code paths

Measured against the cleaned segment files, **feature availability is a function of
`property_type`, not `listing_type`**:

- apartments carry `floor`, `floor_ratio`, `is_ground_floor`, `is_top_floor`, `balcony`,
  `storage`, `orientation_count` — 0% populated for houses;
- houses carry `plot_area_sqm`, `plot_to_building_ratio`, `garage`, `fenced_area`,
  `paved_access`, `water_city`, `house_type` — 0% populated for apartments;
- sale and rent listings of the same property type have an identical set of populated columns.
  They differ only in price regime.

So **two feature lists plus one pipeline builder generate all four models**, with no
per-segment branching anywhere in the code. Both lists happen to come to 33 features
(apartment: 29 numeric + 4 categorical; house: 28 numeric + 5 categorical).

This is also precisely what makes cross-prediction possible: because an `apartment_sale`
frame and an `apartment_rent` frame have the same columns, the rent model can be handed sale
listings directly, with no adapter.

### Deliberate exclusions

Some fully-populated columns are excluded on purpose:

| Excluded | Reason |
|---|---|
| `views_count`, `listing_age_days`, `days_since_update` | Describe the *advertisement*, not the property. Including them would break cross-prediction: when the rent model scores a for-sale listing, that ad metadata belongs to the sale ad, not to the hypothetical rental ad being priced. |
| `image_count` | A scraper capture artefact — capped at 4 for 5640/5676 rows. |
| `price_per_sqm_eur` | Derived from the target; it would leak the answer. |

Missing values are left as NaN rather than imputed: CatBoost reads them natively, and
`years_since_renovation` (~9% populated) carries real signal in its absence. Categoricals get
an explicit `"unknown"` level, which matters for `energy_class` (16–31% populated).

---

## 4. The estimator, and why it is shaped that way

```
Pipeline
├── preprocess : ColumnTransformer
│     ├── categorical -> PricePerAreaTargetEncoder(area_column="total_area_sqm")
│     └── numeric     -> passthrough
└── stack : StackingRegressor(passthrough=True, cv=KFold(5))
      ├── base  : GeoNeighbourRegressor  (haversine KNN over lat/lon, k=30)
      └── final : CatBoostRegressor(lr=0.087, n_estimators=400, max_depth=9)
```

**Target encoding against price per sqm, not price.** A district full of large flats has a
high mean price without being expensive. Encoding `y / total_area_sqm` measures the price
*level* of a category rather than the size of the properties in it. Ported from
`TargetPerSuputilvalEncoder`. Unseen categories fall back to the global mean — that fallback
is what makes the rent model usable on sale listings from districts it never saw, and §7
explains how that is surfaced rather than hidden.

**The geographic neighbour feature.** `KNeighborsRegressor(30, metric="haversine")` over
latitude/longitude *in radians*, predicting local price per sqm — the notebook's "neighbours
percentages" idea. Location in this data is a coordinate pair and a district string; the KNN
turns those into a continuous local price level that no single feature expresses.

Two implementation details that are easy to get wrong:

- `algorithm="ball_tree"` is set explicitly. It is the only sklearn algorithm supporting the
  haversine metric; `"auto"` may select `kd_tree` and fail.
- **Uniform weights**, sklearn's default and the notebook's choice. Many listings share a
  building and therefore share exact coordinates, which would give distance weighting an
  infinite weight on a single neighbour.

**Why stacking rather than a precomputed feature.** A neighbour-price feature computed once
over the training set leaks: a row's own price contributes to its own neighbourhood estimate.
`StackingRegressor` cross-fits base learners, so the neighbour value a row is trained on comes
from a fold that excluded it. That is the entire reason for the stack — the structure *is* the
leakage guard. `passthrough=True` lets CatBoost see the original features alongside the
neighbour estimate rather than only the estimate.

---

## 5. Target modes

`config/modeling.yaml` selects what the estimator regresses on:

| `target` | Forward | Inverse |
|---|---|---|
| `price` (default) | `price_eur` | identity |
| `price_per_sqm` | `price_eur / total_area_sqm` | `× total_area_sqm` |
| `log_price` | `log(price_eur)` | `exp(·)` |

**`predict()` always returns EUR.** The inversion lives in the model, not in the notebook.
This is deliberate: if the caller had to multiply by area, then metrics would not be
comparable across modes, and `investment.py` would need to know which mode each model was
trained in. Instead the target flag becomes a genuine experiment — retrain, compare the same
held-out metrics, keep what wins. `predict(..., as_target_unit=True)` exposes the raw model
output when you want to inspect it.

One subtlety this creates: `StackingRegressor` passes the *transformed* target to base
learners, so a naive `y / area` inside the KNN would compute `price / area²` in
`price_per_sqm` mode. `TargetTransform.to_per_sqm()` expresses the per-sqm basis in each
target's own space (`y / area`, `y`, and `y − log(area)` respectively).

---

## 6. Deviations from the reference notebook

Each of these is a decision, not an omission.

| Notebook | Here | Why |
|---|---|---|
| `SelectFromModel(Lasso(alpha=10.394))` | dropped | That alpha was tuned on Chilean UF-denominated prices; transplanting the literal value to EUR would be miscalibrated. Lasso also cannot consume the NaN-bearing features without imputation machinery that CatBoost makes redundant — and CatBoost selects internally. |
| `StandardScaler` after encoding | dropped | The final estimator is a tree ensemble. Scaling features leaves its predictions unchanged. |
| `PandasStackingRegressor` | stock `StackingRegressor` | The custom subclass existed only to make `passthrough=True` return a DataFrame. After target encoding the matrix is fully numeric, so it is unnecessary. |
| fixed `k=30` | `k` configurable per segment | k=30 over-smooths the 76 training rows of `house_rent`, which uses k=8 and 3 stacking folds. |
| matplotlib / seaborn | Plotly | Already a project dependency for the cleaning report. |

CatBoost hyperparameters are carried over **unchanged** and are *not* recalibrated to Vilnius
data. If held-out metrics disappoint, that is the first place to look.

---

## 7. Cap rates

```
estimated_monthly_rent = rent_model.predict(sale_listings)     # EUR/month
gross_cap_rate_pct     = estimated_monthly_rent * 12 / asking_price * 100
```

`estimate_cap_rate()` guards the two ways this can be misused: it refuses a model whose
`listing_type` is not `rent`, and it refuses listings whose `property_type` does not match the
model's.

Passing `sale_model` as well adds `predicted_price_eur` and `price_premium_pct`, so a listing
can be read on two independent axes — its yield, and whether it is asking above or below what
the sale model thinks it is worth.

**`low_confidence` is set when either:**

1. the rent model is low-n (`house_rent`); or
2. the listing's district was never seen during rent training. There are 52 districts in
   `apartment_sale` against 46 in `apartment_rent`; target encoding silently falls back to the
   global mean for the difference, which means the rent estimate carries no local signal. The
   flag surfaces that rather than letting it average away. It affects 11 of 3036 apartment
   sale listings.

**Gross, not net.** Vacancy, management, maintenance and tax are all ignored. Use these
numbers to rank listings, not to underwrite them. And note the failure mode no model here can
see: a listing may be cheap for a reason absent from the features — legal issues, a bad
neighbour, something visible only in a photo.

---

## 8. Results, and how much to trust them

Held-out performance, target `price`, all figures in EUR (EUR/month for rent):

| Segment | Train rows | MAPE | MedAE | RMSE | R² |
|---|---|---|---|---|---|
| `apartment_sale` | 2428 | 16.3% | 17 812 | 75 787 | 0.887 |
| `apartment_rent` | 1303 | 13.1% | 64 | 161 | 0.823 |
| `house_sale` | 651 | 39.1% | 65 818 | 258 352 | 0.714 |
| `house_rent` | 76 | 50.3% | 469 | 1 363 | 0.392 |

Read `MedAE` alongside `MAPE`: the median absolute error is much smaller than the mean,
meaning a minority of listings drive most of the error. That is expected — the top of the
market is thin and heterogeneous.

Resulting apartment cap rates: median **4.79%**, 5–95% band **2.91–8.52%** — the plausible
range for Vilnius. Highest-yielding districts are the cheaper peripheral ones (Grigiškės
6.74%, Naujoji Vilnia 6.68%, Naujininkai 6.60%), which is what a yield/price-level tradeoff
should look like and is a reasonable sanity check on the whole chain.

**`house_rent` is not a reliable model.** 76 training rows, R² 0.39, and metrics that swing
between seeds. It is trained and shipped because a flagged estimate is more useful than no
estimate, but every house cap rate carries `low_confidence=True`. This is a data-volume
limit, not a code defect — the honest fix is a larger rent scrape upstream, not more
modelling.

---

## 9. Structure

```
config/modeling.yaml               target mode, CatBoost params, k, low-n threshold, paths
src/inmoai_lt/modeling/
    __init__.py                    public API
    config.py                      ModelConfig (frozen) + per-segment overrides
    features.py                    feature lists keyed by property_type
    target.py                      TargetTransform: forward / inverse / to_per_sqm
    transformers.py                PricePerAreaTargetEncoder, GeoNeighbourRegressor
    estimator.py                   build_estimator() -> Pipeline(preprocess, stack)
    dataset.py                     load_segment(), prepare(), dtype coercion
    metrics.py                     MAE/MedAE/RMSE/MAPE/RMSPE/R2, always EUR
    model.py                       SegmentModel: train/predict/evaluate/save/load
    investment.py                  estimate_monthly_rent(), estimate_cap_rate()
models/<segment>.joblib            saved artifacts (gitignored)
notebooks/
    01_train_segment.ipynb         parameterised by SEGMENT
    02_cap_rate.ipynb              parameterised by PROPERTY_TYPE
tests/test_modeling_*.py           synthetic fixtures; never trains on real data
```

The saved artifact is the pipeline plus metadata: train/held-out sizes, the held-out row
indices, the `low_n` flag, the neighbour and CatBoost settings, the random seed, the districts
seen during training, the training timestamp and the sklearn version. Metrics describe exactly
the object you load — the model is scored on the held-out split and saved as-is, never refit.

---

## 10. How to run

```bash
pip install -r requirements.txt
python -m inmoai_lt clean            # produces data/processed/segments/*_analysis.csv
```

**In notebooks** (the intended path). Open `notebooks/01_train_segment.ipynb`, set `SEGMENT`
in the first cell, run top to bottom, repeat for each of the four segments. Then open
`notebooks/02_cap_rate.ipynb`, set `PROPERTY_TYPE`, run.

**In Python:**

```python
from inmoai_lt.modeling import (
    SegmentModel, cap_rate_by_district, estimate_cap_rate, format_metrics, load_segment,
)

# train + score a held-out split, then persist
model = SegmentModel.train("apartment_sale")
format_metrics(model.metrics)
model.save()                                   # -> models/apartment_sale.joblib

# or all four at once
from inmoai_lt.modeling import train_all
models = train_all()

# reload and predict -- always EUR (EUR/month for rent models)
sale_model = SegmentModel.load("apartment_sale")
rent_model = SegmentModel.load("apartment_rent")
sale = load_segment("apartment_sale")

sale_model.predict(sale.head(3))               # [193186., 177980., 254736.]
rent_model.predict(sale.head(3))               # [701., 643., 799.]  <- cross-prediction

# cap rates per listing, then per district
caps = estimate_cap_rate(sale, rent_model, sale_model=sale_model)
cap_rate_by_district(caps, min_listings=10)
```

To try a different target mode without editing the config:

```python
from inmoai_lt.modeling import load_model_config
model = SegmentModel.train("apartment_sale", config=load_model_config(target="log_price"))
```

**Tests:** `pytest --cov=src/inmoai_lt --cov-report=term-missing`. The modelling tests use
synthetic segment frames and a shrunken config, so they run in seconds and never depend on
the real data being present.
