"""Produce a report for top mispredictions including full features and nearby historical margins.

Usage:
  python scripts/report_mispredictions_context.py --predictions models/predictions_1990_1994_1995.csv --fp models/predictions_1990_1994_1995_fp_top10.csv --fn models/predictions_1990_1994_1995_fn_top10.csv --out models --n 10
"""
import argparse
import json
import os
import pandas as pd

from afl_predictions.db import get_engine, get_session, Match


def team_last_margins(session, team_name, before_match_id, n=5):
    """Return last n margins for team before before_match_id as list (oldest->newest).
    Each margin is team_score - opp_score for that prior match.
    """
    if not team_name:
        return []
    rows = (
        session.query(Match)
        .filter(
            (Match.home_team == team_name) | (Match.away_team == team_name),
            Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
        .order_by(Match.match_id.desc())
        .limit(n)
        .all()
    )
    margins = []
    # rows are newest->oldest, convert to oldest->newest
    for m in reversed(rows):
        try:
            hs = float(m.home_score)
            as_ = float(m.away_score)
        except Exception:
            continue
        if m.home_team == team_name:
            margins.append(hs - as_)
        elif m.away_team == team_name:
            margins.append(as_ - hs)
    return margins


def enrich_rows(pred_df, rows_df, session, n=5):
    out = []
    for _, r in rows_df.iterrows():
        token = r['token']
        match_id = int(r['match_id'])
        # find full feature row in pred_df
        full = pred_df[pred_df['match_id'] == match_id]
        if full.empty:
            features = {}
        else:
            # take first row (should be unique)
            row = full.iloc[0]
            # drop identifying cols
            drop_cols = {'token','season','match_id','label','prob_lr','prob_xgb','pred','conf'}
            features = {c: (None if pd.isna(row[c]) else row[c]) for c in row.index if c not in drop_cols}
        # load match info for teams
        m = session.query(Match).filter(Match.match_id == match_id).first()
        home = m.home_team if m else None
        away = m.away_team if m else None
        home_margins = team_last_margins(session, home, match_id, n=n)
        away_margins = team_last_margins(session, away, match_id, n=n)
        entry = {
            'token': token,
            'match_id': match_id,
            'season': int(r['season']) if not pd.isna(r['season']) else None,
            'label': int(r['label']),
            'prob': float(r['prob']) if 'prob' in r and not pd.isna(r['prob']) else (float(r['prob_lr']) if 'prob_lr' in r and not pd.isna(r['prob_lr']) else None),
            'pred': int(r['pred']) if 'pred' in r else (1 if (r.get('prob',0)>=0.5) else 0),
            'home_team': home,
            'away_team': away,
            'features': features,
            'home_last_margins': home_margins,
            'away_last_margins': away_margins,
            'home_recent_margin_avg': (sum(home_margins)/len(home_margins)) if home_margins else None,
            'away_recent_margin_avg': (sum(away_margins)/len(away_margins)) if away_margins else None,
        }
        out.append(entry)
    return out


def run(predictions_csv, fp_csv, fn_csv, out_dir, n=10):
    pred_df = pd.read_csv(predictions_csv)
    fp_df = pd.read_csv(fp_csv)
    fn_df = pd.read_csv(fn_csv)

    engine = get_engine()
    session = get_session(engine)

    fp_enriched = enrich_rows(pred_df, fp_df, session, n=n)
    fn_enriched = enrich_rows(pred_df, fn_df, session, n=n)

    report = {
        'summary': {
            'n_fp': len(fp_df),
            'n_fn': len(fn_df),
            'top_n': n,
            'predictions_csv': predictions_csv,
        },
        'false_positives': fp_enriched,
        'false_negatives': fn_enriched,
    }

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'mispredictions_report_{n}_{os.path.basename(predictions_csv).replace(".csv","")}.json')
    # normalize types to JSON-serializable native Python types
    def _normalize(o):
        # convert pandas/numpy scalars and nested containers
        try:
            import numpy as _np
            import pandas as _pd
        except Exception:
            _np = None
            _pd = None

        if isinstance(o, dict):
            return {str(k): _normalize(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_normalize(v) for v in o]
        if _pd is not None and isinstance(o, _pd.Timestamp):
            return o.isoformat()
        if _np is not None and isinstance(o, (_np.integer,)):
            return int(o)
        if _np is not None and isinstance(o, (_np.floating,)):
            return float(o)
        if _np is not None and isinstance(o, (_np.ndarray,)):
            return [_normalize(x) for x in o.tolist()]
        # pandas NA and numpy nan
        try:
            if _pd is not None and o is _pd.NA:
                return None
        except Exception:
            pass
        if isinstance(o, float) and (o != o):
            return None
        return o

    serializable = _normalize(report)
    with open(out_path, 'w', encoding='utf8') as fh:
        json.dump(serializable, fh, indent=2)

    print('Wrote report to', out_path)
    # print compact summary for first few entries
    print('\nSample FP entries:')
    for e in fp_enriched[:min(3,len(fp_enriched))]:
        print('-', e['token'], 'match_id', e['match_id'], 'prob', e['prob'])
        print('  home', e['home_team'], 'away', e['away_team'])
        print('  home_last_margins (oldest->newest):', e['home_last_margins'])
        print('  away_last_margins (oldest->newest):', e['away_last_margins'])
        print('  features sample:', {k: e['features'].get(k) for k in list(e['features'].keys())[:6]})

    print('\nSample FN entries:')
    for e in fn_enriched[:min(3,len(fn_enriched))]:
        print('-', e['token'], 'match_id', e['match_id'], 'prob', e['prob'])
        print('  home', e['home_team'], 'away', e['away_team'])
        print('  home_last_margins (oldest->newest):', e['home_last_margins'])
        print('  away_last_margins (oldest->newest):', e['away_last_margins'])
        print('  features sample:', {k: e['features'].get(k) for k in list(e['features'].keys())[:6]})

    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--predictions', required=True)
    p.add_argument('--fp', required=True)
    p.add_argument('--fn', required=True)
    p.add_argument('--out', default='models')
    p.add_argument('--n', type=int, default=10)
    args = p.parse_args()
    exit(run(args.predictions, args.fp, args.fn, args.out, n=args.n))
