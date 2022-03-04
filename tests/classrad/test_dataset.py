from pathlib import Path

import hypothesis_utils
from hypothesis import given, settings

from classrad.data.dataset import FeatureDataset


class TestFeatureDataset:
    @given(df=hypothesis_utils.simple_df())
    @settings(max_examples=5)
    def test_init(self, df):
        dataset = FeatureDataset(
            dataframe=df,
            features=["Feature1"],
            target="Label",
            ID_colname="ID",
            task_name="Testing",
        )
        assert dataset.X.columns == ["Feature1"]
        assert dataset.y.name == "Label"

    test_data_path = (
        Path(__file__).parent.parent / "testing_data" / "splits.json"
    )

    def test_load_splits_from_json(self, test_data_path):
        print(test_data_path)
