import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
from sklearn.model_selection import train_test_split

from autorad.config import config
from autorad.config.type_definitions import PathLike
from autorad.utils import io, splitting, utils

log = logging.getLogger(__name__)


@dataclass
class TrainingInput:
    train: pd.DataFrame
    test: pd.DataFrame
    val: Optional[pd.DataFrame] = None
    train_folds: Optional[List[pd.DataFrame]] = None
    val_folds: Optional[List[pd.DataFrame]] = None


@dataclass
class TrainingLabels:
    train: pd.Series
    test: pd.Series
    val: Optional[pd.DataFrame] = None
    train_folds: Optional[List[pd.DataFrame]] = None
    val_folds: Optional[List[pd.DataFrame]] = None


@dataclass
class TrainingMeta:
    train: pd.DataFrame
    test: pd.DataFrame
    val: Optional[pd.DataFrame] = None
    train_folds: Optional[List[pd.DataFrame]] = None
    val_folds: Optional[List[pd.DataFrame]] = None


@dataclass
class TrainingData:
    X: TrainingInput
    y: TrainingLabels
    meta: TrainingMeta

    _X_preprocessed: Optional[TrainingInput] = None
    _y_preprocessed: Optional[TrainingLabels] = None

    def __repr__(self):
        return f"TrainingData with {len(self.y.train)} training observations,\
        {len(self.y.test)} test observations, {self.X.train.shape[1]} features \
        and {self.meta.train.shape[1]} meta columns."

    @property
    def X_preprocessed(self):
        if self._X_preprocessed is None:
            raise ValueError("Preprocessing not performed!")
        return self._X_preprocessed

    @property
    def selected_features(self):
        if self._X_preprocessed is None:
            raise ValueError("Feature selection not performed!")
        return list(self._X_preprocessed.train.columns)


class FeatureDataset:
    """
    Store the extracted features and labels, split into training/test sets.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        target: str,
        ID_colname: str,
        features: Optional[list[str]] = None,
        meta_columns: List[str] = [],
        random_state: int = config.SEED,
    ):
        """
        Args:
            dataframe: table with extracted features
            target: name of the label column
            ID_colname: name of column with unique IDs for each case
            features: feature names
            meta_columns: columns to keep that are not features
            random_state: seed, used for splitting
        """
        self.df = dataframe
        self.target = target
        self.ID_colname = ID_colname
        self.random_state = random_state
        self.features = self._init_features(features)
        self.X: pd.DataFrame = self.df[self.features]
        self.y: pd.Series = self.df[self.target]
        self.meta_df = self.df[meta_columns + [ID_colname]]
        self._data: Optional[TrainingData] = None
        self.cv_splits: Optional[List[tuple[Any, Any]]] = None

    def _init_features(
        self, features: Optional[List[str]] = None
    ) -> List[str]:
        if features is None:
            all_cols = self.df.columns.tolist()
            features = utils.get_pyradiomics_names(all_cols)
        return features

    @property
    def data(self):
        if self._data is None:
            raise AttributeError(
                "Data is not split into training/validation/test. \
                 Split the data or load splits from JSON."
            )
        else:
            return self._data

    def load_splits_from_json(self, json_path: PathLike, split_on=None):
        """
        JSON file should contain the following keys:
            - 'test': list of test IDs
            - 'train': dict with n keys (default n = 5)):
                - 'fold_{0..n-1}': list of training and
                                   list of validation IDs
        It can be created using `full_split()` defined below.
        """
        splits = io.load_json(json_path)
        if split_on is None:
            split_on = self.ID_colname
        test_ids = splits["test"]
        test_rows = self.df[split_on].isin(test_ids)
        train_rows = ~self.df[split_on].isin(test_ids)

        # Split dataframe rows
        X, y, meta = {}, {}, {}
        X["test"] = self.X.loc[test_rows]
        y["test"] = self.y.loc[test_rows]
        meta["test"] = self.meta_df.loc[test_rows]
        X["train"] = self.X.loc[train_rows]
        y["train"] = self.y.loc[train_rows]
        meta["train"] = self.meta_df.loc[train_rows]

        train_ids = splits["train"]
        n_splits = len(train_ids)
        self.cv_splits = [
            (train_ids[f"fold_{i}"][0], train_ids[f"fold_{i}"][1])
            for i in range(n_splits)
        ]
        X["train_folds"], X["val_folds"] = [], []
        y["train_folds"], y["val_folds"] = [], []
        meta["train_folds"], meta["val_folds"] = [], []
        for train_fold_ids, val_fold_ids in self.cv_splits:

            train_fold_rows = self.df[split_on].isin(train_fold_ids)
            val_fold_rows = self.df[split_on].isin(val_fold_ids)

            X["train_folds"].append(self.X[train_fold_rows])
            X["val_folds"].append(self.X[val_fold_rows])
            y["train_folds"].append(self.y[train_fold_rows])
            y["val_folds"].append(self.y[val_fold_rows])
            meta["train_folds"].append(self.meta_df[train_fold_rows])
            meta["val_folds"].append(self.meta_df[val_fold_rows])
        self._data = TrainingData(
            TrainingInput(**X), TrainingLabels(**y), TrainingMeta(**meta)
        )
        return self

    def full_split(
        self,
        save_path: PathLike,
        split_on: Optional[str] = None,
        test_size: float = 0.2,
        n_splits: int = 5,
    ):
        """
        Split into test and training, split training into 5 folds.
        Save the splits to json.
        """
        if split_on is None:
            split_on = self.ID_colname
        patient_df = self.df[[split_on, self.target]].drop_duplicates()
        if not patient_df[split_on].is_unique:
            raise ValueError(
                f"Selected column {split_on} has varying labels for the same ID!"
            )
        ids = patient_df[split_on].tolist()
        labels = patient_df[self.target].tolist()
        splits = splitting.split_full_dataset(
            ids=ids,
            labels=labels,
            test_size=test_size,
            n_splits=n_splits,
        )
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        io.save_json(splits, save_path)

    def get_train_test_split_from_column(
        self, column_name: str, test_value: str
    ):
        """
        Use if the splits are already in the dataframe.
        """
        X_train = self.X[self.X[column_name] != test_value]
        y_train = self.y[self.y[column_name] != test_value]
        X_test = self.X[self.X[column_name] == test_value]
        y_test = self.y[self.y[column_name] == test_value]

        return X_train, y_train, X_test, y_test

    def split_train_val_test_from_column(
        self, column_name: str, test_value: str, val_size: float = 0.2
    ):
        data = {}
        (
            X_train_and_val,
            y_train_and_val,
            data["X_test"],
            data["y_test"],
        ) = self.get_train_test_split_from_column(column_name, test_value)
        (
            data["X_train"],
            data["X_val"],
            data["y_train"],
            data["y_val"],
        ) = train_test_split(
            X_train_and_val,
            y_train_and_val,
            test_size=val_size,
            random_state=self.random_state,
        )
        self._data = TrainingData(**data)

    def full_split_with_test_from_column(
        self,
        column_name: str,
        test_value: str,
        save_path: PathLike,
        split_on: Optional[str] = None,
        split_label: Optional[str] = None,
        n_splits: int = 5,
    ):
        """
        Splits into train and test according to `column_name`,
        then performs stratified k-fold cross validation split
        on the training set.
        """
        if split_on is None:
            split_on = self.ID_colname
        if split_label is None:
            split_label = self.target
        df_to_split = self.df[
            [split_on, split_label, column_name]
        ].drop_duplicates()
        if not df_to_split[split_on].is_unique:
            raise ValueError(
                f"Selected column {split_on} has varying labels for the same ID!"
            )
        train_to_split = df_to_split[df_to_split[column_name] != test_value]
        ids_train = train_to_split[split_on].tolist()
        y_train = train_to_split[split_label].tolist()
        ids_test = df_to_split.loc[
            df_to_split[column_name] == test_value, split_on
        ].tolist()

        ids_train_cv = splitting.split_cross_validation(
            ids_train, y_train, n_splits, random_state=self.random_state
        )

        ids_split = {
            "split_type": f"predefined test as {column_name} = {test_value}"
            " and stratified cross validation on training",
            "test": ids_test,
            "train": ids_train_cv,
        }
        io.save_json(ids_split, save_path)

        return self


class ImageDataset:
    """
    Stores paths to the images, segmentations and labels
    """

    def __init__(
        self,
        df: pd.DataFrame,
        image_colname: str = "image_path",
        mask_colname: str = "segmentation_path",
        ID_colname: Optional[str] = None,
        root_dir: Optional[PathLike] = None,
    ):
        """
        Args:
            df: dataframe with image and mask paths
            image_colname: name of the image column in df
            mask_colname: name of the mask column in df
            ID_colname: name of the ID column in df. If None,
                IDs are assigned sequentially
            root_dir: root directory of the dataset, if needed
                to resolve paths
        """
        self._df = df
        self.image_colname = self._check_if_in_df(image_colname)
        self.mask_colname = self._check_if_in_df(mask_colname)
        self._set_ID_col(ID_colname)
        self.root_dir = root_dir

    def _check_if_in_df(self, colname: str):
        if colname not in self._df.columns:
            raise ValueError(
                f"{colname} not found in columns of the dataframe."
            )
        if self._df[colname].isnull().any():
            raise ValueError(f"{colname} contains null values")
        return colname

    def _set_new_IDs(self):
        log.info("ID not set. Assigning sequential IDs.")
        if "ID" not in self._df.columns:
            self.ID_colname = "ID"
        else:
            self.ID_colname = "ID_autogenerated"
        self._df[self.ID_colname] = range(len(self._df))

    def _set_ID_col_from_given(self, id_colname: str):
        if id_colname not in self._df.columns:
            raise ValueError(f"{id_colname} not in columns of dataframe.")
        ids = self._df[id_colname]
        # assert IDs are unique
        if len(ids.unique()) != len(ids):
            raise ValueError("IDs are not unique!")
        self.ID_colname = id_colname

    def _set_ID_col(self, id_colname: Optional[str] = None):
        if id_colname is None:
            self._set_new_IDs()
        else:
            self._set_ID_col_from_given(id_colname)

    @property
    def df(self) -> pd.DataFrame:
        """If root_dir is set, returns the dataframe with paths resolved"""
        if self.root_dir is None:
            return self._df
        result = self._df.copy()
        return result.assign(
            **{
                self.image_colname: self._df[self.image_colname].apply(
                    lambda x: os.path.join(self.root_dir, x)
                )
            }
        ).assign(
            **{
                self.mask_colname: self._df[self.mask_colname].apply(
                    lambda x: os.path.join(self.root_dir, x)
                )
            }
        )

    @property
    def image_paths(self) -> List[str]:
        return self.df[self.image_colname].to_list()

    @property
    def mask_paths(self) -> List[str]:
        return self.df[self.mask_colname].to_list()

    @property
    def ids(self) -> List[str]:
        if self.ID_colname is None:
            raise AttributeError("ID is not set.")
        return self.df[self.ID_colname].to_list()
