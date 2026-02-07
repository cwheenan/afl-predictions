"""Inspect high-confidence mispredictions from a predictions CSV.

Reads models/predictions_{train}_{test}.csv and writes top mispredictions to models/
"""
import argparse
import pandas as pd
import os

def run(pred_csv, out_dir, top_n=10):
    df = pd.read_csv(pred_csv)
    if df.empty:
        print('predictions CSV empty or missing')
        return 1
    # prefer prob_lr column
    if 'prob_lr' in df.columns:
        pcol = 'prob_lr'
    elif 'prob_xgb' in df.columns:
        pcol = 'prob_xgb'
    else:
        print('No probability column found')
        return 1

    df['prob'] = df[pcol]
    # compute predicted label by threshold 0.5
    df['pred'] = (df['prob'] >= 0.5).astype(int)
    # error types
    fp = df[(df['pred'] == 1) & (df['label'] == 0)].copy()
    fn = df[(df['pred'] == 0) & (df['label'] == 1)].copy()

    # confidence = |prob - 0.5|
    df['conf'] = (df['prob'] - 0.5).abs()
    fp['conf'] = (fp['prob'] - 0.5).abs()
    fn['conf'] = (fn['prob'] - 0.5).abs()

    fp_top = fp.sort_values('conf', ascending=False).head(top_n)
    fn_top = fn.sort_values('conf', ascending=False).head(top_n)

    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(pred_csv))[0]
    fp_path = os.path.join(out_dir, f'{base}_fp_top{top_n}.csv')
    fn_path = os.path.join(out_dir, f'{base}_fn_top{top_n}.csv')
    fp_top.to_csv(fp_path, index=False)
    fn_top.to_csv(fn_path, index=False)

    print(f'Found {len(fp)} false positives, {len(fn)} false negatives')
    print('\nTop false positives (high-confidence):')
    if fp_top.empty:
        print('  None')
    else:
        print(fp_top[['token','season','match_id','label','prob','conf']].to_string(index=False))

    print('\nTop false negatives (high-confidence):')
    if fn_top.empty:
        print('  None')
    else:
        print(fn_top[['token','season','match_id','label','prob','conf']].to_string(index=False))

    print(f'Written FP to {fp_path} and FN to {fn_path}')
    return 0

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('usage: python scripts/inspect_mispredictions.py models/predictions_1990_1994_1995.csv [out_dir]')
        sys.exit(1)
    pred_csv = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else 'models'
    exit(run(pred_csv, out_dir))
