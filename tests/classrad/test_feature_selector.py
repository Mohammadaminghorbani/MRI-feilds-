from datetime import timedelta

import hypothesis_utils
import numpy as np
import pytest
from hypothesis import assume, given, settings

from classrad.feature_selection.feature_selector import FeatureSelector


class TestFeatureSelector:
    def setup_method(self):
        self.feature_selector = FeatureSelector()

    def teardown_method(self):
        del self.feature_selector

    @given(df=hypothesis_utils.medium_df())
    @settings(max_examples=5)
    def test_fit_anova(self, df):
        # assume(df["Label"].nunique() == 2)  # assume both categories present
        X, y = df.drop("Label", axis=1).to_numpy(), df["Label"].to_numpy()
        selected_columns = self.feature_selector.fit_anova(X, y, k=5)
        assert isinstance(selected_columns, list)
        assert len(selected_columns) == 5
        assert type(selected_columns[0]) == int
        assert max(selected_columns) < X.shape[1]
        assert min(selected_columns) >= 0

    @given(df=hypothesis_utils.medium_df())
    @settings(max_examples=2, deadline=timedelta(seconds=20))
    def test_fit_lasso(self, df):
        assume(df["Label"].nunique() == 2)  # assume both categories present
        X, y = df.drop("Label", axis=1).to_numpy(), df["Label"].to_numpy()
        selected_columns = self.feature_selector.fit_lasso(X, y, verbose=0)
        assert isinstance(selected_columns, list)
        assert len(selected_columns) >= 0

    @given(df=hypothesis_utils.medium_df())
    @settings(max_examples=2, deadline=timedelta(seconds=20))
    def test_fit_boruta(self, df):
        X, y = df.drop("Label", axis=1).to_numpy(), df["Label"].to_numpy()
        selected_columns = self.feature_selector.fit_boruta(X, y, verbose=0)
        assert isinstance(selected_columns, list)
        assert len(selected_columns) >= 0

    @given(df=hypothesis_utils.medium_df())
    @settings(max_examples=1, deadline=timedelta(seconds=20))
    def test_fit_transform(self, df):
        X, y = df.drop("Label", axis=1).to_numpy(), df["Label"].to_numpy()
        for valid_method in ["anova", "lasso", "boruta"]:
            feature_selector = FeatureSelector(method=valid_method)
            X_trans = feature_selector.fit_transform(X, y)
            assert isinstance(X_trans, np.ndarray)
        with pytest.raises(ValueError):
            feature_selector = FeatureSelector(method="foo")
            feature_selector.fit_transform(X, y)
