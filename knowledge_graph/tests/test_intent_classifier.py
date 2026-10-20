"""Unit and integration tests for the Trained ML Query Intent Classifier (RP-27).

Verifies:
  1. Training dataset integrity (360 samples, balanced 6 classes).
  2. TF-IDF feature extraction and sublinear scaling.
  3. Model training reproducibility and parameter serialization.
  4. 5-Fold Stratified Cross-Validation metric thresholds (Accuracy >= 90%, F1 >= 90%).
  5. Per-class prediction accuracy across all 6 GraphRAG intent classes.
  6. Probability simplex constraints (sum to 1.0, non-negative).
  7. FastAPI /model/metrics and /model/train endpoint contracts.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from graphrag.anchor_resolver import classify_query_intent_ml, detect_query_intent
from graphrag.intent_classifier import (
    DATASET_PATH,
    INTENT_CLASSES,
    METRICS_PATH,
    MODEL_WEIGHTS_PATH,
    TrainedIntentClassifier,
    _build_curated_dataset,
    _extract_ngrams,
    get_intent_classifier,
)
from main import app


def test_training_dataset_balance_and_integrity() -> None:
    """Verify dataset contains 360 curated queries with exact class balance (60 per class)."""
    dataset = _build_curated_dataset()
    assert len(dataset) == 360

    counts = {}
    for item in dataset:
        assert "query" in item and len(item["query"].strip()) >= 5
        assert "intent" in item and item["intent"] in INTENT_CLASSES
        counts[item["intent"]] = counts.get(item["intent"], 0) + 1

    assert len(counts) == 6
    for c in INTENT_CLASSES:
        assert counts[c] == 60


def test_feature_extraction_ngrams_and_clusters() -> None:
    """Verify n-gram extraction produces unigrams, bigrams, and semantic cluster features."""
    feats = _extract_ngrams("What is blocking the benchmark task due Friday?")
    assert feats["w1:blocking"] > 0
    assert feats["w1:benchmark"] > 0
    assert feats["w2:benchmark_task"] > 0
    assert feats["cls:sem_blocker"] > 0
    assert feats["cls:sem_deadline"] > 0


def test_model_training_and_metric_thresholds() -> None:
    """Verify trained model achieves >= 90% 5-fold cross-validation accuracy and macro F1."""
    clf = get_intent_classifier()
    if not clf.metrics:
        clf.train_and_evaluate()

    m = clf.metrics
    assert m["dataset_size"] == 360
    assert m["classes_count"] == 6
    assert m["vocabulary_size"] >= 2000

    cv = m["cross_validation_5fold"]
    assert cv["mean_accuracy"] >= 0.90, f"CV Accuracy {cv['mean_accuracy']} is below 0.90"
    assert cv["mean_macro_f1"] >= 0.90, f"CV Macro F1 {cv['mean_macro_f1']} is below 0.90"

    test_split = m["test_split_80_20"]
    assert test_split["accuracy"] >= 0.90


def test_model_artifacts_saved_on_disk() -> None:
    """Verify model weights and evaluation metrics JSON files exist on disk."""
    clf = get_intent_classifier()
    if not clf.metrics:
        clf.train_and_evaluate()

    assert MODEL_WEIGHTS_PATH.exists()
    assert METRICS_PATH.exists()
    assert DATASET_PATH.exists()

    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "cross_validation_5fold" in data
        assert "test_split_80_20" in data


@pytest.mark.parametrize(
    "query, expected_intent",
    [
        ("What critical bug is blocking Sarah Chen's WhisperX task?", "blocker_chain"),
        ("Why is the payment flow task delayed and failing?", "blocker_chain"),
        ("When is the deployment deadline on the calendar?", "deadline_schedule"),
        ("What is the due date for the Friday security cutoff?", "deadline_schedule"),
        ("What is David Miller currently working on?", "task_status"),
        ("Who is assigned to deploy the Docker cluster task?", "task_status"),
        ("Summarize the Sprint 14 Architecture Sync meeting minutes", "meeting_summary"),
        ("Who attended the Security Architecture Standup?", "meeting_summary"),
        ("Who is Sarah Chen and what is her role?", "person_context"),
        ("Where does Tharindu work and who are his friends?", "person_context"),
        ("Tell me about Ollama 8B 4-bit quantization details", "general"),
        ("What is the specification of Cloud GPU Invoice #402?", "general"),
    ],
)
def test_predict_all_six_intent_classes(query: str, expected_intent: str) -> None:
    """Verify trained classifier predicts the correct intent for canonical queries."""
    clf = get_intent_classifier()
    pred_intent, conf, probs = clf.predict(query)
    assert pred_intent == expected_intent
    assert 0.50 <= conf <= 1.0
    assert 0.0 <= probs[pred_intent] <= 1.0


def test_predict_proba_simplex_constraints() -> None:
    """Verify predicted class probabilities form a valid probability distribution (sum to 1.0)."""
    clf = get_intent_classifier()
    probs = clf.predict_proba("When is the Weekly sync meeting?")
    assert len(probs) == 6
    assert abs(sum(probs.values()) - 1.0) < 0.005
    for p in probs.values():
        assert 0.0 <= p <= 1.0


def test_classify_query_intent_ml_hybrid() -> None:
    """Verify hybrid classify_query_intent_ml integrates ML confidence and probability bar."""
    intent, conf, probs = classify_query_intent_ml("Who is friend of Kamal?")
    assert intent == "person_context"
    assert conf >= 0.70
    assert "person_context" in probs
    assert probs["person_context"] > 0.50


def test_fastapi_model_metrics_endpoint() -> None:
    """Verify GET /model/metrics returns 200 with complete evaluation data."""
    client = TestClient(app)
    res = client.get("/model/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "cross_validation_5fold" in data
    assert data["cross_validation_5fold"]["mean_accuracy"] >= 0.90
    assert "confusion_matrix" in data["cross_validation_5fold"]["overall_cv_metrics"]


def test_fastapi_model_train_endpoint() -> None:
    """Verify POST /model/train re-trains model and returns updated metrics."""
    client = TestClient(app)
    res = client.post("/model/train")
    assert res.status_code == 200
    data = res.json()
    assert data["dataset_size"] == 360
    assert "cross_validation_5fold" in data
