"""
Find where the routing model's confidence threshold belongs.

Training the model on twice the data moved held-out accuracy by +1.6 points,
so more data is not the lever. But inspecting the failures showed the model
frequently KNOWS the answer and is refused by the gate:

    "how's my computer holding up"   raw=system (correct)  conf=0.498
    "what's running right now"       raw=system (correct)  conf=0.623
                                              threshold = 0.82

A threshold set too high converts correct-but-hesitant predictions into
"unknown". Set too low it lets wrong answers through. This sweeps it and
reports both effects, because "accuracy went up" is not sufficient - what
matters is whether the WRONG answers grew faster than the right ones.

The prediction is advisory: it never bypasses a safety check, and a wrong
route costs a slower path, not an unsafe action. So a modest rise in wrong
answers can be worth a larger rise in right ones - but that trade should be
made from the numbers, not assumed.

    python benchmark/threshold_sweep.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.route_map import route_for  # noqa: E402
from benchmark.train import CORPUS  # noqa: E402

MODEL_PATH = ROOT / "data" / "neural_command_model.json"
THRESHOLDS = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.82, 0.9]


def held_out() -> list:
    """Every phrasing the model was never trained on."""
    pairs = []
    for intent_type, (_train, evaluate) in CORPUS.items():
        want = route_for(intent_type)
        if not want:
            continue
        for phrase in evaluate:
            pairs.append((phrase, want))
    return pairs


def main() -> int:
    from learning.neural_command_model import NeuralCommandModel

    model = NeuralCommandModel(path=str(MODEL_PATH))
    pairs = held_out()
    if not pairs:
        print("no held-out phrasings")
        return 1

    # Predict once; the threshold is applied afterwards, so the model runs
    # 65 times rather than 650.
    raw = []
    for phrase, want in pairs:
        result = model.predict(phrase) or {}
        raw.append({
            "phrase": phrase,
            "want": want,
            "route": result.get("raw_route") or result.get("predicted_route") or "",
            "confidence": float(result.get("confidence") or 0.0),
        })

    print(f"\nheld-out phrasings: {len(raw)}")
    print(f"\n{'threshold':>10} {'correct':>8} {'wrong':>7} {'refused':>8}   accuracy")
    print("-" * 56)

    best = None
    for threshold in THRESHOLDS:
        correct = wrong = refused = 0
        for row in raw:
            if row["confidence"] < threshold or not row["route"]:
                refused += 1
            elif row["route"] == row["want"]:
                correct += 1
            else:
                wrong += 1
        accuracy = correct / len(raw)
        marker = "   <- current" if abs(threshold - 0.82) < 1e-6 else ""
        print(f"{threshold:>10.2f} {correct:>8} {wrong:>7} {refused:>8}   "
              f"{accuracy:>6.1%}{marker}")
        if best is None or accuracy > best[1]:
            best = (threshold, accuracy, correct, wrong, refused)

    threshold, accuracy, correct, wrong, refused = best
    current = next(
        (c / len(raw) for t, c in
         [(t, sum(1 for r in raw
                  if r["confidence"] >= t and r["route"] == r["want"]))
          for t in (0.82,)]),
        0.0,
    )
    print("\n" + "=" * 56)
    print(f"  best threshold   {threshold:.2f}   accuracy {accuracy:.1%}"
          f"  ({correct} right, {wrong} wrong, {refused} refused)")
    print(f"  current (0.82)          accuracy {current:.1%}")
    print(f"  change           {accuracy - current:+.1%}")
    print("=" * 56)
    print("\n  A refused prediction is not free: the command falls back to a\n"
          "  slower path. A wrong one costs a wrong tool, which the safety\n"
          "  layer still gates. Judge the trade from both columns.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
