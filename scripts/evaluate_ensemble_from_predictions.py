#!/usr/bin/env python3
"""Read saved predictions CSV and evaluate simple ensembles.

Produces:
 - models/ensemble_eval_1990_1994_1995.json
 - models/predictions_1990_1994_1995_ensemble.csv

The script expects the predictions CSV created earlier to contain columns at least:
 - label (0/1)
 - prob_lr (probability from logistic regression)
 - prob_xgb (probability from xgboost)
 - season, match_id, token (optional)
"""
import json
import numpy as np
import pandas as pd
import os
from sklearn import metrics

IN = 'models/predictions_1990_1994_1995.csv'
OUT_JSON = 'models/ensemble_eval_1990_1994_1995.json'
OUT_CSV = 'models/predictions_1990_1994_1995_ensemble.csv'

if not os.path.exists(IN):
    raise SystemExit(f'Predictions CSV not found: {IN}')

print('Reading', IN)
df = pd.read_csv(IN)
# Inspect column names
print('Columns:', df.columns.tolist())

# try common names
prob_cols = [c for c in df.columns if c.lower().startswith('prob')]
print('Prob columns found:', prob_cols)

# heuristics for lr/xgb
prob_lr = None
prob_xgb = None
for c in prob_cols:
    lc = c.lower()
    if 'lr' in lc or 'logreg' in lc or 'logistic' in lc:
        prob_lr = c
    if 'xgb' in lc or 'xgboost' in lc:
        prob_xgb = c
# fallback: pick first two prob columns
if prob_lr is None or prob_xgb is None:
    if len(prob_cols) >= 2:
        prob_lr = prob_lr or prob_cols[0]
        prob_xgb = prob_xgb or prob_cols[1]

if prob_lr is None or prob_xgb is None:
    raise SystemExit('Could not find both LR and XGB probability columns in predictions CSV')

print('Using prob_lr =', prob_lr, 'prob_xgb =', prob_xgb)

y = df['label'].values
p_lr = df[prob_lr].values
p_xgb = df[prob_xgb].values

# simple mean ensemble
p_mean = (p_lr + p_xgb) / 2.0

# evaluate helper
def eval_probs(y, p):
    acc = ( (p >= 0.5) == y ).mean()
    try:
        auc = metrics.roc_auc_score(y, p)
    except Exception:
        auc = None
    brier = metrics.brier_score_loss(y, p)
    cm = metrics.confusion_matrix(y, (p >= 0.5).astype(int)).tolist()
    return {'acc': float(acc), 'auc': float(auc) if auc is not None else None, 'brier': float(brier), 'confusion': cm}

results = {}
results['prob_lr_name'] = prob_lr
results['prob_xgb_name'] = prob_xgb
results['mean'] = eval_probs(y, p_mean)

# search best weight w in [0,1] for p = w*p_xgb + (1-w)*p_lr maximizing AUC
best = {'w': None, 'auc': -1}
for w in np.linspace(0, 1, 21):
    p = w * p_xgb + (1 - w) * p_lr
    try:
        auc = metrics.roc_auc_score(y, p)
    except Exception:
        auc = -1
    if auc > best['auc']:
        best['auc'] = float(auc)
        best['w'] = float(w)

results['best_weight_search'] = best
# compute metrics for best weight
w = best['w']
p_best = w * p_xgb + (1 - w) * p_lr
results['best'] = eval_probs(y, p_best)

# also compute simple majority vote (thresholded preds)
pred_lr = (p_lr >= 0.5).astype(int)
pred_xgb = (p_xgb >= 0.5).astype(int)
vote = (pred_lr + pred_xgb) >= 1  # at least one says 1
acc_vote = (vote == y).mean()
try:
    auc_vote = metrics.roc_auc_score(y, vote)
except Exception:
    auc_vote = None
results['majority_vote'] = {'acc': float(acc_vote), 'auc': float(auc_vote) if auc_vote is not None else None}

# add AUCs of individual models
results['lr'] = eval_probs(y, p_lr)
results['xgb'] = eval_probs(y, p_xgb)

# save ensemble predictions CSV
df_out = df.copy()
df_out['prob_ensemble_mean'] = p_mean
df_out['prob_ensemble_best'] = p_best

print('Writing', OUT_CSV)
df_out.to_csv(OUT_CSV, index=False)

print('Writing', OUT_JSON)
with open(OUT_JSON, 'w') as f:
    json.dump(results, f, indent=2)

print('Done. Summary:')
print(json.dumps(results, indent=2))
