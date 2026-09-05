# Task 2: fix the corpus, then measure tool-calling by model size

Previous task is done and verified — numbers reproduce exactly:

```
regex_only              accuracy=0.9227   0.24 ms
classifier_only         accuracy=0.7493  12.66 ms
regex_then_classifier   accuracy=0.9680   1.11 ms
```

Reporting the classifier losing to regex alone was the right call. Two
follow-ups, in order. **Commit after each.**

---

## Part A — the corpus is starving the classifier

`data/intent_corpus.jsonl` has 1,893 examples across 103 intents, but the
distribution is badly skewed:

```
browser_action        121
create_file            94
search_files           83
...
security_port_scan      4
security_ssl_check      4
show_phase5_learning    4
```

**85 of 103 intents have fewer than 20 examples.** That, not the model
architecture, is the likely reason classifier-only sits at 0.7493.

**Goal: every intent reaches at least 40 examples, and no intent exceeds
~150**, so the classifier is not just learning the prior.

Modify `learning/intent_dataset.py` (your own file) to:

1. **Report the distribution before and after**, so the change is visible.
2. **Target generation at the starved intents.** Do not generate uniformly —
   ask the local model for many more paraphrases of the rare ones and few
   or none of the common ones.
3. **Cap the over-represented intents** by sampling down, so the corpus is
   roughly balanced.
4. **Deduplicate.** Near-identical paraphrases inflate counts without adding
   information — normalise whitespace and case, and drop exact repeats.
5. **Verify every generated example still round-trips**: feed it back
   through `_parse_direct_command` where that intent is rule-matchable, and
   discard any paraphrase that now parses as a *different* intent. A
   mislabelled example is worse than a missing one.

Then retrain and re-run `benchmark/intent_eval.py`. **Report the new three
numbers next to the old ones.** If classifier-only does not improve, say so
plainly — that is a real finding and it tells us the ceiling is the model,
not the data.

---

## Part B — how well can this model actually drive tools?

This is the evidence for a hardware decision, so honesty matters more than
a good result.

The system exposes **9 tools with 70 actions** through its tool registry
(`core/tool_registry.py`; `main.py` builds it in `_build_tool_registry`).
An agentic loop needs the model to pick the right action *and* supply the
right arguments. Small models are unreliable at exactly this, and the
failure compounds across steps.

Create **`benchmark/tool_calling_eval.py`** (new file):

1. Build a set of at least 60 instructions with a known-correct
   `(action, key arguments)` answer. Draw them from `benchmark/tasks.py`,
   `benchmark/multistep.py` and the intent corpus; write the expected
   answers explicitly rather than deriving them from the thing being tested.
2. Present the model with the tool manifest and one instruction, and ask it
   to choose an action and arguments as JSON.
3. Score three things separately:
   - **action accuracy** — did it pick the right action?
   - **argument accuracy** — given the right action, were the key arguments
     right?
   - **format validity** — was the response parseable JSON at all?
4. Run it for whichever models are pulled locally, and take a `--model`
   flag so the same script can be run elsewhere on larger ones.
5. Print a per-model table and write results to
   `benchmark/results/tool_calling.json`.

Report the numbers as they come out. If a 3B model scores badly, that is
the finding, and it is worth more than a flattering one.

---

## Constraints (unchanged)

- New files only, except `learning/intent_dataset.py` which you own.
- **Do not modify `main.py`, `core/memory.py`, or `agents/learning_agent.py`**
  — those are being worked on concurrently and you will collide.
- 7.4 GB RAM, 4 GB VRAM. Nothing larger than `qwen2.5:3b` locally.
- Docstrings explain **why**, not what the signature already says.
- Report real numbers even when unflattering.

## Acceptance

```bash
python learning/intent_dataset.py     # before/after distribution, >=40 per intent
python learning/intent_classifier.py  # retrained, new held-out metrics
python benchmark/intent_eval.py       # three numbers, old vs new
python benchmark/tool_calling_eval.py # per-model action/argument/format scores
python -m pytest tests/ -q            # still green
```
