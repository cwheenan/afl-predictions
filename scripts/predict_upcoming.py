#!/usr/bin/env python3
"""Generate predictions for upcoming AFL matches.

Loads trained model and generates predictions for matches that have odds data.
Designed for weekly execution during the season.

Usage:
  python scripts/predict_upcoming.py
  python scripts/predict_upcoming.py --round 1
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import joblib
from datetime import datetime
import json

from afl_predictions.db import get_engine, get_session, Match, MatchOdds
from afl_predictions.features.lineup import features_for_match


def parse_date_string(date_str: str):
    """Parse date string to extract year."""
    if date_str is None:
        return None
    import re
    match = re.search(r'(\d{4})', date_str)
    if match:
        return int(match.group(1))
    return None


def get_upcoming_matches(session, year=2026, round_num=None):
    """Get matches for specified year/round that need predictions."""
    all_matches = session.query(Match).all()
    
    matches = []
    for m in all_matches:
        match_year = parse_date_string(m.date)
        if match_year == year:
            # Only incomplete matches (no scores yet)
            if m.home_score is None or m.away_score is None:
                # Check if odds available
                has_odds = session.query(MatchOdds).filter(
                    MatchOdds.match_id == m.match_id
                ).count() > 0
                
                if has_odds:
                    matches.append(m)
    
    return matches


def predict_match(model, session, match, optimal_odds_weight=0.1):
    """Generate prediction for a single match."""
    try:
        # Extract features
        fv = features_for_match(session, match.match_id)
        
        # Get odds probability
        odds_home_prob = fv.get('odds_home_win_prob', 0.5)
        
        # Prepare feature vector (with odds features)
        feature_names = sorted(fv.keys())
        X = np.array([[fv[k] for k in feature_names]])
        X = np.nan_to_num(X, nan=0.0)
        
        # Get RF probability
        rf_prob = model.predict_proba(X)[0, 1]
        
        # Ensemble: RF + Odds
        final_prob = rf_prob * (1 - optimal_odds_weight) + odds_home_prob * optimal_odds_weight
        
        # Prediction
        prediction = 'HOME' if final_prob >= 0.5 else 'AWAY'
        confidence = abs(final_prob - 0.5) * 2  # 0 to 1 scale
        
        return {
            'match_id': match.match_id,
            'home_team': match.home_team,
            'away_team': match.away_team,
            'venue': match.venue,
            'date': match.date,
            'prediction': prediction,
            'home_win_prob': float(final_prob),
            'away_win_prob': float(1 - final_prob),
            'confidence': float(confidence),
            'rf_prob': float(rf_prob),
            'odds_prob': float(odds_home_prob),
        }
    
    except Exception as e:
        print(f"Error predicting match {match.match_id}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Generate predictions for upcoming matches')
    parser.add_argument('--year', type=int, default=2026, help='Season year')
    parser.add_argument('--round', type=int, help='Specific round number')
    parser.add_argument('--model', type=str, default='models/rf_with_odds_final.joblib',
                       help='Path to trained model')
    parser.add_argument('--odds-weight', type=float, default=0.1,
                       help='Weight for odds in ensemble (default: 0.1)')
    parser.add_argument('--output', type=str, help='Output file path')
    
    args = parser.parse_args()
    
    # Load model
    print(f"Loading model from {args.model}...")
    model = joblib.load(args.model)
    
    # Get matches
    engine = get_engine()
    session = get_session(engine)
    
    print(f"\nLooking for upcoming matches in {args.year}...")
    matches = get_upcoming_matches(session, args.year, args.round)
    
    if not matches:
        print("No upcoming matches found with odds data.")
        print("\nNote: For 2026 predictions, you need to:")
        print("  1. Fetch 2026 match schedule (when available)")
        print("  2. Collect odds using: python scripts/collect_odds.py --fetch-current")
        return
    
    print(f"Found {len(matches)} matches")
    
    # Generate predictions
    predictions = []
    print("\n" + "="*70)
    print("PREDICTIONS")
    print("="*70)
    
    for i, match in enumerate(matches, 1):
        pred = predict_match(model, session, match, args.odds_weight)
        if pred:
            predictions.append(pred)
            
            # Display
            winner = pred['home_team'] if pred['prediction'] == 'HOME' else pred['away_team']
            prob = pred['home_win_prob'] if pred['prediction'] == 'HOME' else pred['away_win_prob']
            
            print(f"\n{i}. {match.home_team} vs {match.away_team}")
            print(f"   Venue: {match.venue}")
            print(f"   Date: {match.date}")
            print(f"   >>> Prediction: {winner:20s} ({prob:.1%} confidence)")
            print(f"   Model breakdown: RF={pred['rf_prob']:.3f}, Odds={pred['odds_prob']:.3f}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"\nTotal predictions: {len(predictions)}")
    
    home_wins = sum(1 for p in predictions if p['prediction'] == 'HOME')
    away_wins = sum(1 for p in predictions if p['prediction'] == 'AWAY')
    avg_confidence = np.mean([p['confidence'] for p in predictions])
    
    print(f"  Home wins predicted: {home_wins}")
    print(f"  Away wins predicted: {away_wins}")
    print(f"  Average confidence: {avg_confidence:.1%}")
    
    # High confidence picks
    high_conf = [p for p in predictions if p['confidence'] >= 0.7]
    if high_conf:
        print(f"\n  High confidence picks ({len(high_conf)}):")
        for p in sorted(high_conf, key=lambda x: x['confidence'], reverse=True):
            winner = p['home_team'] if p['prediction'] == 'HOME' else p['away_team']
            prob = p['home_win_prob'] if p['prediction'] == 'HOME' else p['away_win_prob']
            print(f"    {winner:20s} {prob:.1%}")
    
    # Save predictions
    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f'predictions_{args.year}_{timestamp}.json'
    
    output_data = {
        'generated_at': datetime.now().isoformat(),
        'model_path': args.model,
        'year': args.year,
        'round': args.round,
        'odds_weight': args.odds_weight,
        'predictions': predictions,
        'summary': {
            'total': len(predictions),
            'home_wins': home_wins,
            'away_wins': away_wins,
            'avg_confidence': float(avg_confidence)
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nPredictions saved to: {output_path}")
    
    session.close()


if __name__ == '__main__':
    main()
