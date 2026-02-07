"""Common metric helpers wrapped for convenience."""

from sklearn.metrics import accuracy_score, roc_auc_score


def print_classification_metrics(y_true, y_proba):
    from pprint import pprint
    metrics = {
        "accuracy": accuracy_score(y_true, (y_proba>=0.5).astype(int)),
        "auc": roc_auc_score(y_true, y_proba),
    }
    pprint(metrics)
