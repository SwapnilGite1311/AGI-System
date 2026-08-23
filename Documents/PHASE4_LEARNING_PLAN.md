# Phase 4: Learning & Adaptation

Phase 4 makes ASC adapt to the user over time while keeping Phase 3 safety rules in control.

## Implemented Foundation

- Adaptive learning state stored in `data/adaptive_state.json`.
- Semi-supervised labels from command success, reward scores, and explicit feedback.
- Workflow clustering from repeated successful commands.
- Preference signal extraction for future suggestions.
- Advisory strategy recommendations that do not bypass deterministic safety gates.
- `phase 4 status` / `show adaptive learning` command.

## Safety Policy

- Learned behavior is advisory first.
- Deterministic rules, confirmation prompts, and tool safety stay above learned suggestions.
- Learned routing can only reuse direct strategies that are explicitly marked safe for reuse.
- Model fine-tuning remains disabled until we have enough labeled data and evaluation tests.

## Next Phase 4 Steps

- Add an evaluation harness for learned strategy recommendations.
- Add explicit preference suggestion approval, for example: "approve preference default_browser chrome".
- Add workflow templates generated from stable clusters.
- Add a lightweight local classifier for intent/tool routing after enough data is collected.
- Add DNN experimentation only as an offline training/evaluation path, not live execution.
- Add metrics for recommendation accuracy and user correction rate.

## Useful Commands

```text
phase 4 status
show adaptive learning
show learned workflows
that worked
that failed
```
