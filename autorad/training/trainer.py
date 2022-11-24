import logging
from pathlib import Path
from typing import Sequence

import joblib
import mlflow
import numpy as np
import optuna
from optuna.study import Study
from optuna.trial import Trial
from sklearn.metrics import roc_auc_score

from autorad.config.type_definitions import PathLike
from autorad.data.dataset import FeatureDataset
from autorad.models.classifier import MLClassifier
from autorad.preprocessing.preprocessor import Preprocessor
from autorad.training import train_utils
from autorad.training.optimizer import OptunaOptimizer
from autorad.utils import io

log = logging.getLogger(__name__)


class Trainer:
    """
    Runs the experiment that optimizes the hyperparameters
    for all the models, given the dataset with extracted features.
    """

    def __init__(
        self,
        dataset: FeatureDataset,
        models: Sequence[MLClassifier],
        result_dir: PathLike,
        experiment_name: str = "baseline",
    ):
        self.dataset = dataset
        self.models = models
        self.result_dir = Path(result_dir)
        self.experiment_name = experiment_name

        self._optimizer = None
        self.auto_preprocessing = False

    def set_optimizer(self, optimizer: str, n_trials=100):
        if optimizer == "optuna":
            self._optimizer = OptunaOptimizer(n_trials=n_trials)
        # elif optimizer == "gridsearch":
        #     self.optimizer = GridSearchOptimizer()
        else:
            raise ValueError("Optimizer not recognized.")

    @property
    def optimizer(self):
        if self._optimizer is None:
            raise ValueError("Optimizer is not set!")
        return self._optimizer

    def set_optuna_params(self, model: MLClassifier, trial: Trial):
        params = model.param_fn(trial)
        model.set_params(**params)
        return model

    def save_best_preprocessor(self, study: Study):
        params = study.best_trial.params
        feature_selection = params["feature_selection_method"]
        oversampling = params["oversampling_method"]
        preprocessor = Preprocessor(
            standardize=True,
            feature_selection_method=feature_selection,
            oversampling_method=oversampling,
        )
        preprocessor.fit_transform(self.dataset.data)
        mlflow.sklearn.log_model(preprocessor, "preprocessor")

    def run(
        self,
        auto_preprocess: bool = False,
    ):
        """
        Run hyperparameter optimization for all the models.
        """
        with mlflow.start_run():
            study = self.optimizer.create_study(
                study_name=self.experiment_name
            )

            study.optimize(
                lambda trial: self._objective(trial, auto_preprocess),
                n_trials=self.optimizer.n_trials,
            )
            self.save_best_params(study)
            self.save_best_preprocessor(study)
            self.save_best_model(study)

    def save_best_model(self, study):
        best_model = study.best_trial.user_attrs["model"]
        best_auc = study.best_trial.user_attrs["AUC"]
        mlflow.log_metric("AUC", best_auc)
        best_model.save_to_mlflow()

    def save_best_params(self, study: Study):
        params = study.best_trial.params
        mlflow.log_params(params)
        io.save_json(params, (self.result_dir / "best_params.json"))

    def optimize_preprocessing(self, trial: Trial):
        pkl_path = self.result_dir / "preprocessed.pkl"
        with open(pkl_path, "rb") as f:
            preprocessed = joblib.load(f)
        feature_selection_method = trial.suggest_categorical(
            "feature_selection_method", preprocessed.keys()
        )
        oversampling_method = trial.suggest_categorical(
            "oversampling_method",
            preprocessed[feature_selection_method].keys(),
        )
        result = preprocessed[feature_selection_method][oversampling_method]

        return result

    def _objective(self, trial: optuna.Trial, auto_preprocess=False) -> float:
        """Get params from optuna trial, return the metric."""
        if auto_preprocess:
            data = self.optimize_preprocessing(trial)
        else:
            data = self.dataset.data

        model_name = trial.suggest_categorical(
            "model", [m.name for m in self.models]
        )
        model = train_utils.get_model_by_name(model_name, self.models)
        model = self.set_optuna_params(model, trial)
        aucs = []
        for (
            X_train,
            y_train,
            _,
            X_val,
            y_val,
            _,
        ) in data.iter_training():
            try:
                model.fit(X_train, y_train)
            except ValueError:
                log.error(f"Training {model.name} failed.")
                return np.nan
            y_pred = model.predict_proba_binary(X_val)
            auc_val = roc_auc_score(y_val, y_pred)
            aucs.append(auc_val)
        auc = np.mean(aucs)
        trial.set_user_attr("model", model)
        trial.set_user_attr("AUC", auc)
        # with tempfile.TemporaryDirectory() as dp:
        #     model_path = Path(dp) / "model.pkl"
        #     joblib.dump(model, model_path)
        #     mlflow.log_artifacts(dp)
        # model.save_to_mlflow()
        # mlflow.pyfunc.log_model(artifact_path="model", python_model=model)
        return auc
