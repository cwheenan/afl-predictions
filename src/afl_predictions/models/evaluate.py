"""Evaluation utilities for model performance."""

from sklearn.metrics import roc_auc_score, accuracy_score


def evaluate_classification(y_true, y_proba, threshold: float = 0.5):
    y_pred = (y_proba >= threshold).astype(int)
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "auc": roc_auc_score(y_true, y_proba),
    }
