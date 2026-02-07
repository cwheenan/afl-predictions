#!/usr/bin/env python3
"""Evaluate impact of betting odds features on model performance.

Trains models with and without odds features and compares accuracy.
Tests on 2024-2025 data (where odds are available).

Usage:
  python scripts/evaluate_odds_impact.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sqlalchemy import and_

from afl_predictions.db import get_engine, get_session, Match, MatchOdds
from afl_predictions.features.lineup import features_for_match


def parse_date_string(date_str: str):
    """Parse date string to extract year."""
    import re
    match = re.search(r'(\d{4})', date_str)
    if match:
        return int(match.group(1))
    return None


def build_dataset(session, years, include_odds=True):
    """Build feature matrix and labels for specified years.
    
    Args:
        session: Database session
        years: List of years to include
        include_odds: If True, include odds features; if False, exclude them
    
    Returns:
        X: Feature matrix
        y: Labels (1 = home win, 0 = away win)
        match_ids: List of match IDs
    """
    print(f"\nBuilding dataset for years {years}, include_odds={include_odds}")
    
    # Get all matches from specified years
    all_matches = session.query(Match).all()
    matches = []
    for m in all_matches:
        year = parse_date_string(m.date)
        if year and year in years:
            # Filter to matches with scores (completed games)
            if m.home_score is not None and m.away_score is not None:
                matches.append(m)
    
    print(f"Found {len(matches)} completed matches")
    
    # If include_odds, filter to matches with odds data
    if include_odds:
        matches_with_odds = []
        for m in matches:
            odds_count = session.query(MatchOdds).filter(
                MatchOdds.match_id == m.match_id
            ).count()
            if odds_count > 0:
                matches_with_odds.append(m)
        
        matches = matches_with_odds
        print(f"Filtered to {len(matches)} matches with odds data")
    
    if not matches:
        raise ValueError(f"No matches found for years {years}")
    
    # Extract features
    X = []
    y = []
    match_ids = []
    
    for i, m in enumerate(matches):
        if i % 50 == 0:
            print(f"  Processing {i}/{len(matches)}...")
        
        try:
            fv = features_for_match(session, m.match_id)
            
            # If excluding odds, remove odds features
            if not include_odds:
                odds_keys = [k for k in fv.keys() if k.startswith('odds_')]
                for k in odds_keys:
                    fv.pop(k, None)
            
            # Convert to feature vector
            feature_names = sorted(fv.keys())
            features = [fv[k] for k in feature_names]
            
            # Label: 1 if home won, 0 if away won
            label = 1 if m.home_score > m.away_score else 0
            
            X.append(features)
            y.append(label)
            match_ids.append(m.match_id)
        except Exception as e:
            print(f"  Warning: Could not process match {m.match_id}: {e}")
            continue
    
    print(f"Built dataset: {len(X)} samples, {len(X[0]) if X else 0} features")
    
    # Handle NaN values - replace with 0
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    
    return np.array(X), np.array(y), match_ids, feature_names


def evaluate_model(model, X_train, y_train, X_test, y_test, name="Model"):
    """Train and evaluate a model."""
    print(f"\n{name}:")
    print(f"  Training on {len(X_train)} samples...")
    model.fit(X_train, y_train)
    
    train_acc = accuracy_score(y_train, model.predict(X_train))
    test_acc = accuracy_score(y_test, model.predict(X_test))
    
    print(f"  Train accuracy: {train_acc:.1%}")
    print(f"  Test accuracy:  {test_acc:.1%}")
    
    # Detailed test results
    y_pred = model.predict(X_test)
    print(f"\n  Correct predictions: {sum(y_pred == y_test)}/{len(y_test)}")
    
    return test_acc


def main():
    engine = get_engine()
    session = get_session(engine)
    
    print("=" * 60)
    print("EVALUATING IMPACT OF BETTING ODDS FEATURES")
    print("=" * 60)
    
    # Use 2024 for training, 2025 for testing (both have odds data)
    train_years = [2024]
    test_years = [2025]
    
    print(f"\nTraining on: {train_years}")
    print(f"Testing on:  {test_years}")
    
    # Build training set (2024 - no odds filtering for baseline)
    print("\n" + "=" * 60)
    print("BUILDING TRAINING DATA (2024 - without odds requirement)")
    print("=" * 60)
    X_train_no_odds, y_train, train_ids, feature_names_no_odds = build_dataset(
        session, train_years, include_odds=False
    )
    
    # Build test sets
    print("\n" + "=" * 60)
    print("BUILDING TEST DATA (2025)")
    print("=" * 60)
    
    # Test WITHOUT odds features (all matches)
    X_test_no_odds, y_test, test_ids, _ = build_dataset(
        session, test_years, include_odds=False
    )
    
    # Test WITH odds features (only matches that have odds)
    X_test_with_odds, y_test_odds, test_ids_odds, feature_names_with_odds = build_dataset(
        session, test_years, include_odds=True
    )
    
    # For fair comparison, also filter no-odds test set to same matches
    test_ids_odds_set = set(test_ids_odds)
    indices = [i for i, mid in enumerate(test_ids) if mid in test_ids_odds_set]
    X_test_no_odds_filtered = X_test_no_odds[indices]
    y_test_filtered = y_test[indices]
    
    print(f"\nTest set sizes:")
    print(f"  All 2024-2025 matches (no odds): {len(y_test)}")
    print(f"  Matches with odds data: {len(y_test_odds)}")
    
    # Ensure training features match test features (no odds)
    # Training data from 2023 might not have odds in DB
    if X_train_no_odds.shape[1] != X_test_no_odds_filtered.shape[1]:
        print(f"\nWarning: Feature mismatch - training {X_train_no_odds.shape[1]}, test {X_test_no_odds_filtered.shape[1]}")
        print("Features will be aligned")
    
    # Train models WITHOUT odds features
    print("\n" + "=" * 60)
    print("BASELINE: MODELS WITHOUT ODDS FEATURES")
    print("=" * 60)
    
    rf_no_odds = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_split=5,
        max_features='log2',
        bootstrap=False,
        random_state=42
    )
    
    lr_no_odds = LogisticRegression(
        C=0.001,
        penalty='l2',
        solver='liblinear',
        random_state=42,
        max_iter=1000
    )
    
    rf_acc_no_odds = evaluate_model(
        rf_no_odds, X_train_no_odds, y_train, X_test_no_odds_filtered, y_test_filtered,
        name="Random Forest (NO ODDS)"
    )
    
    lr_acc_no_odds = evaluate_model(
        lr_no_odds, X_train_no_odds, y_train, X_test_no_odds_filtered, y_test_filtered,
        name="Logistic Regression (NO ODDS)"
    )
    
    # Now build training data WITH odds
    # This will be smaller as we need matches with odds
    print("\n" + "=" * 60)
    print("BUILDING TRAINING DATA WITH ODDS (2024 matches that have odds)")
    print("=" * 60)
    X_train_with_odds, y_train_odds, train_ids_odds, _ = build_dataset(
        session, train_years, include_odds=True
    )
    
    # Train models WITH odds features
    print("\n" + "=" * 60)
    print("WITH ODDS: MODELS WITH BETTING ODDS FEATURES")
    print("=" * 60)
    
    rf_with_odds = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_split=5,
        max_features='log2',
        bootstrap=False,
        random_state=42
    )
    
    lr_with_odds = LogisticRegression(
        C=0.001,
        penalty='l2',
        solver='liblinear',
        random_state=42,
        max_iter=1000
    )
    
    rf_acc_with_odds = evaluate_model(
        rf_with_odds, X_train_with_odds, y_train_odds, X_test_with_odds, y_test_odds,
        name="Random Forest (WITH ODDS)"
    )
    
    lr_acc_with_odds = evaluate_model(
        lr_with_odds, X_train_with_odds, y_train_odds, X_test_with_odds, y_test_odds,
        name="Logistic Regression (WITH ODDS)"
    )
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nTrain: 2024 ({len(y_train_odds)} matches with odds)")
    print(f"Test:  2025 ({len(y_test_odds)} matches with odds)")
    print("\nBaseline (stats only):")
    print(f"  Random Forest:        {rf_acc_no_odds:.1%} ({int(rf_acc_no_odds * len(y_test_odds))}/{len(y_test_odds)})")
    print(f"  Logistic Regression:  {lr_acc_no_odds:.1%} ({int(lr_acc_no_odds * len(y_test_odds))}/{len(y_test_odds)})")
    
    print("\nWith odds features:")
    print(f"  Random Forest:        {rf_acc_with_odds:.1%} ({int(rf_acc_with_odds * len(y_test_odds))}/{len(y_test_odds)})")
    print(f"  Logistic Regression:  {lr_acc_with_odds:.1%} ({int(lr_acc_with_odds * len(y_test_odds))}/{len(y_test_odds)})")
    
    print("\nImprovement:")
    print(f"  Random Forest:        {(rf_acc_with_odds - rf_acc_no_odds):.1%} ({int((rf_acc_with_odds - rf_acc_no_odds) * len(y_test_odds))} more correct)")
    print(f"  Logistic Regression:  {(lr_acc_with_odds - lr_acc_no_odds):.1%} ({int((lr_acc_with_odds - lr_acc_no_odds) * len(y_test_odds))} more correct)")
    
    # Feature importance (if available)
    if hasattr(rf_with_odds, 'feature_importances_'):
        print("\n" + "=" * 60)
        print("TOP 10 FEATURE IMPORTANCES (Random Forest with Odds)")
        print("=" * 60)
        
        importances = rf_with_odds.feature_importances_
        indices = np.argsort(importances)[::-1]
        
        for i in range(min(10, len(feature_names_with_odds))):
            idx = indices[i]
            print(f"  {i+1:2d}. {feature_names_with_odds[idx]:30s}  {importances[idx]:.4f}")
    
    session.close()


if __name__ == '__main__':
    main()
