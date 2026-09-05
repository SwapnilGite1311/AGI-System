import json

from learning import intent_classifier as ic


def _tiny_rows():
    return [
        {"command": "open chrome", "intent": "open_application"},
        {"command": "launch calculator", "intent": "open_application"},
        {"command": "start notepad", "intent": "open_application"},
        {"command": "list files in downloads", "intent": "list_files"},
        {"command": "show files on desktop", "intent": "list_files"},
        {"command": "what files are in documents", "intent": "list_files"},
        {"command": "search files for report", "intent": "search_files"},
        {"command": "find my budget file", "intent": "search_files"},
        {"command": "look for invoice pdf", "intent": "search_files"},
    ]


def test_missing_load_returns_false(tmp_path):
    classifier = ic.IntentClassifier(model_path=tmp_path / "missing.json")
    assert classifier.load() is False


def test_predict_works_when_embeddings_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "embed", lambda *args, **kwargs: None)
    classifier = ic.IntentClassifier(model_path=tmp_path / "intent.json")
    classifier.train(_tiny_rows())

    result = classifier.predict("please open calculator")

    assert result["intent"] in {"open_application", "list_files", "search_files"}
    assert 0.0 <= result["confidence"] <= 1.0


def test_confidence_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "embed", lambda *args, **kwargs: None)
    classifier = ic.IntentClassifier(model_path=tmp_path / "intent.json")
    classifier.train(_tiny_rows())

    for command in ["open browser", "show files", "find document"]:
        confidence = classifier.predict(command)["confidence"]
        assert 0.0 <= confidence <= 1.0


def test_training_tiny_fixture_save_and_load(monkeypatch, tmp_path):
    monkeypatch.setattr(ic, "embed", lambda *args, **kwargs: None)
    model_path = tmp_path / "intent.json"
    classifier = ic.IntentClassifier(model_path=model_path)

    metrics = classifier.train(_tiny_rows(), holdout=0.34)
    classifier.save()

    assert model_path.exists()
    assert metrics["train_examples"] > 0
    assert metrics["holdout_examples"] > 0
    assert classifier.predict("find my file")["intent"] in classifier.labels

    loaded = ic.IntentClassifier(model_path=model_path)
    assert loaded.load() is True
    assert loaded.predict("open notepad")["intent"] in loaded.labels


def test_fresh_clone_no_model_predicts_unknown(tmp_path):
    classifier = ic.IntentClassifier(model_path=tmp_path / "intent.json")

    result = classifier.predict("open chrome")

    assert classifier.load() is False
    assert json.dumps(result)
    assert result == {"intent": "unknown", "confidence": 0.0, "alternatives": []}
