"""Train / predict / save / load, on synthetic segment frames."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from inmoai_lt.modeling import SUPPORTED_TARGETS, SegmentModel, split_segment


def test_segment_name_splits_into_property_and_listing_type():
    assert split_segment("apartment_rent") == ("apartment", "rent")
    assert split_segment("house_sale") == ("house", "sale")
    with pytest.raises(ValueError, match="unknown segment"):
        split_segment("apartment_lease")


@pytest.mark.parametrize("target", SUPPORTED_TARGETS)
def test_predictions_are_in_eur_whatever_the_target_mode(target, make_segment_frame, fast_config):
    df = make_segment_frame()
    model = SegmentModel.train("apartment_sale", df=df, config=replace(fast_config, target=target))

    predicted = model.predict(df)
    assert predicted.shape == (len(df),)
    # Same order of magnitude as the fixture's prices; the point is the unit, not the fit.
    assert 0.2 < np.median(predicted) / df["price_eur"].median() < 5.0


def test_as_target_unit_returns_the_untransformed_model_output(make_segment_frame, fast_config):
    df = make_segment_frame()
    config = replace(fast_config, target="price_per_sqm")
    model = SegmentModel.train("apartment_sale", df=df, config=config)

    eur = model.predict(df)
    per_sqm = model.predict(df, as_target_unit=True)
    assert np.allclose(eur, per_sqm * df["total_area_sqm"].to_numpy())


def test_metrics_cover_the_held_out_rows_only(make_segment_frame, fast_config):
    df = make_segment_frame(n=150)
    model = SegmentModel.train("apartment_sale", df=df, config=fast_config)

    assert model.metrics["n"] == model.metadata["n_test"]
    assert model.metadata["n_train"] + model.metadata["n_test"] == len(df)
    assert len(model.metadata["test_index"]) == model.metadata["n_test"]


def test_evaluate_scores_any_labelled_frame_in_eur(make_segment_frame, fast_config):
    df = make_segment_frame()
    model = SegmentModel.train("apartment_sale", df=df, config=fast_config)

    scored = model.evaluate(make_segment_frame(n=80, seed=7))
    assert scored["n"] == 80
    assert scored["MAE"] > 0


def test_saving_and_loading_preserves_predictions(make_segment_frame, fast_config, tmp_path: Path):
    df = make_segment_frame()
    model = SegmentModel.train("apartment_sale", df=df, config=fast_config)

    path = model.save(models_dir=tmp_path)
    reloaded = SegmentModel.load(path)

    assert np.array_equal(model.predict(df), reloaded.predict(df))
    assert reloaded.target == model.target
    assert reloaded.feature_spec == model.feature_spec


def test_loading_a_missing_model_names_the_path(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="train and save"):
        SegmentModel.load("apartment_sale", models_dir=tmp_path)


def test_low_n_is_set_when_the_segment_is_too_small(make_segment_frame, fast_config):
    small = SegmentModel.train(
        "house_rent", df=make_segment_frame("house", "rent", n=60), config=fast_config
    )
    large = SegmentModel.train(
        "house_rent",
        df=make_segment_frame("house", "rent", n=60),
        config=replace(fast_config, low_n_threshold=10),
    )
    assert small.low_n is True
    assert large.low_n is False


def test_house_model_uses_house_features(make_segment_frame, fast_config):
    model = SegmentModel.train(
        "house_sale", df=make_segment_frame("house", "sale"), config=fast_config
    )
    assert "plot_area_sqm" in model.feature_spec.numeric
    assert "house_type" in model.feature_spec.categorical
    assert "floor" not in model.feature_spec.numeric
