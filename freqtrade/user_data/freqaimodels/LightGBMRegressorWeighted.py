import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from lightgbm import LGBMRegressor

from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.tensorboard import LightGBMCallback


logger = logging.getLogger(__name__)


class LightGBMRegressorWeighted(BaseRegressionModel):
    """
    LightGBM regressor with RETURN-ATTRIBUTION sample weighting (2026-06-15).

    The problem this fixes
    ----------------------
    The target is the z-scored 12-candle forward return, recomputed every candle.
    Two issues compound:
      1. Label overlap: consecutive labels share 11/12 of their price path, so the
         training set is far more redundant than its row count suggests.
      2. Equal weighting: a candle before a violent move and a candle before flat
         chop are taught as equally important. The chop candles are exactly where
         the model learns nothing useful and where the live bot's random entries /
         38%-full-stop-loss bleed come from.

    Naive López de Prado "average uniqueness" weighting is near-uniform for a
    FIXED-horizon label (every interior row overlaps identically) → near no-op
    here. The useful half of the weighting formula is the other term: weight by
    the SIZE of the realized move (|return|). High-magnitude samples carry the
    real signal; low-magnitude chop is down-weighted. This focuses the model on
    the moves it is actually used to trade (entries fire on large predicted
    magnitude), without changing features, target, or any trading logic.

    Weight = clip(|z-scored target| / mean(|z-scored target|), floor, cap),
    then multiplied into FreqAI's existing weights (so recency weighting, if
    ever enabled, still composes). floor keeps chop samples present (not zeroed);
    cap stops a single outlier from dominating the fit.

    Selected per-experiment via the config `freqaimodel` field, so the brain can
    A/B it against the stock LightGBMRegressor and MEASURE the effect. The family
    model cache keys on freqaimodel, so weighted and unweighted never collide.
    """

    _WEIGHT_FLOOR = 0.25   # chop samples keep 1/4 weight — present, not erased
    _WEIGHT_CAP = 4.0      # a single huge move counts at most 4x an average one

    def _attribution_weights(self, labels, base_weights):
        """Return base_weights * normalized |label|, clipped. Shape-aligned to rows."""
        y = np.asarray(labels).reshape(-1).astype(float)
        mag = np.abs(y)
        mean_mag = mag[np.isfinite(mag)].mean()
        if not np.isfinite(mean_mag) or mean_mag <= 0:
            return base_weights  # degenerate (all-zero target) → leave unchanged
        attr = np.clip(mag / mean_mag, self._WEIGHT_FLOOR, self._WEIGHT_CAP)
        attr = np.nan_to_num(attr, nan=self._WEIGHT_FLOOR)
        return np.asarray(base_weights, dtype=float) * attr

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        if self.freqai_info.get("data_split_parameters", {}).get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = self._attribution_weights(
                data_dictionary["test_labels"], data_dictionary["test_weights"]
            )

        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]
        train_weights = self._attribution_weights(
            data_dictionary["train_labels"], data_dictionary["train_weights"]
        )

        logger.info(
            "[Weighted] return-attribution sample weights — "
            f"train mean={float(np.mean(train_weights)):.3f} "
            f"min={float(np.min(train_weights)):.3f} max={float(np.max(train_weights)):.3f}"
        )

        init_model = self.get_init_model(dk.pair)
        model = LGBMRegressor(**self.model_training_parameters)

        activate_tensorboard = self.freqai_info.get("activate_tensorboard", True)
        callbacks: list[Callable[..., Any]] = []
        if LightGBMCallback is not None:
            callbacks = [LightGBMCallback(dk.data_path, activate_tensorboard)]

        model.fit(
            X=X,
            y=y,
            eval_set=eval_set,
            sample_weight=train_weights,
            eval_sample_weight=[eval_weights] if eval_weights is not None else None,
            init_model=init_model,
            callbacks=callbacks,
        )
        return model
