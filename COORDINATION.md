# AGENT COORDINATION BOARD — AGI-SYSTEM PROJECT

Supervisor: Swapnil | Team Lead: OX-ALPHA | Agents: BON, DEV
Last updated: 2026-08-23 by Team Lead

====================================================================
## MANDATORY RULES — VIOLATING THESE MEANS YOUR WORK GETS REVERTED
====================================================================
1. SINGLE-WRITER PER MODULE: never edit files assigned to another agent. No exceptions.
2. READ this entire file BEFORE starting any task. Re-check TASK STATUS before you begin.
3. LOG EVERYTHING: every bug found, every fix made, goes in YOUR OWN log section below,
   prefixed exactly as `Team Lead:` or `Bon:` or `Dev:` followed by your findings.
   Format: `<date> - <YourName>: <what you found/did> (<files touched>)`
4. Never edit another agent's log section. Only append to your own.
5. COMMIT after EVERY completed task: `git add -A && git commit -m "<Agent>: <task> - <summary>"`
   Never leave uncommitted changes lying around.
6. Do NOT push to origin. The supervisor pushes.
7. VERIFY before marking DONE: python -m py_compile on changed .py files must pass.
   For behavioral fixes, run the relevant test and paste proof in your log entry.
8. If a task requires touching a file outside your ownership: STOP. Mark the task
   HANDOFF-REQUESTED in your log. The Team Lead resolves conflicts.
9. Do NOT modify: COORDINATION.md structure/rules, git history, .gitignore, or anything
   not listed in your assignment.
10. When finished with all your tasks: mark status DONE in the table, write findings
    in your log, then STOP and wait. Do not invent extra work.

====================================================================
## MODULE OWNERSHIP
====================================================================

| Module / Files | Owner |
|---|---|
| core/council.py, core/chairman.py | Team Lead |
| core/memory.py, core/autonomy.py, core/task_decomposer.py, core/tool_registry.py | Team Lead |
| main.py + deletion of Code/main.py duplicate | Team Lead |
| local-server/server.py (voice pipeline) | Team Lead |
| Final review of ALL agents' work | Team Lead |
| learning/*.py (Phase 5 crash fix lives here) | Bon |
| agents/business_agent.py (cwd path fix) | Bon |
| agents/file_agent.py | Bon |
| agents/web_agent.py (line 648 always-False fix) | Dev |
| config/settings.json (dead config block removal ONLY) | Dev |
| Documents/*.md (audit doc reconciliation) | Dev |
| tests/ directory additions welcome from all (in NEW files only) | All |

Shared no-touch zones: test_fix1_smoke.py belongs to Team Lead.

====================================================================
## TASK STATUS  (update only YOUR rows)
====================================================================

| # | Task | Owner | Status |
|---|---|---|---|
| 1 | Two-tier model architecture sized to hardware (DONE: commit 2044643) | Team Lead | DONE |
| 2 | Fix Phase 5 crash: `'NoneType' object has no attribute 'get'` firing on every command. Root is inside learning/phase5_model.py fit()/state chain (see logs/asc_2026-08-22_21-11-17_898121.log). Fix the None propagation, do not just swallow it. | Bon | TODO |
| 3 | Delete Code/main.py (diverged duplicate of root main.py). Remove 6 shadowed method definitions in core/autonomy.py (_generate_advanced_plan, _create_business_plan, _create_sequential_plan, _create_goal_oriented_plan, _determine_action_for_part, _determine_agent_for_part — second definition wins, first is dead). Also remove duplicate send_email handlers in main.py keeping ONE. | Team Lead | DONE |
| 4 | Voice pipeline: recording uses fixed 5s capture with no silence detection (main.py _record_audio ~line 228). Implement basic VAD: stop recording after ~1.2s of sustained silence OR speech end. Must still POST to local-server /listen unchanged. | Team Lead | TODO |
| 5 | web_agent.py line 648: `"submission_verified": False if submitted else False` is always False. Make it actually verify submission success where feasible, else set honest value. | Dev | TODO |
| 6 | business_agent.py line 33 (+sibling loaders): cwd-relative data paths fork saved state depending on launch dir. Resolve against project root like core/memory.py does (lines 27-33 pattern). | Bon | TODO |
| 7 | settings.json: remove dead config blocks never read by code: memory.redis, memory.chromadb, api host/port block, communication twilio/whatsapp block, audio.wake_word. Grep first to confirm nothing reads them; list grep evidence in your log BEFORE deleting. | Dev | TODO |
| 8 | Reconcile Documents/CODEBASE_ISSUES_ANALYSIS.md + SYSTEM_BUG_REPORT.md with reality: mark what is now fixed (model sizing done via commits 2044643+), correct false FIXED claims (Phase 5), note remaining items. Factual doc update, no code changes. | Dev | TODO |

====================================================================
## TEAM LEAD LOG
====================================================================
- 2026-08-23 - Team Lead: Completed task #1. Root cause of "not responding": qwen2.5:14b (9GB) cannot fit 4GB VRAM -> CUDA0 buffer allocation failure on every call. Reworked: council roles -> qwen2.5:3b (fits VRAM 100%, verified via ollama ps), speed -> gemma2:2b, backup -> tinyllama, vision stays llava:7b. Enforced 120s timeouts via asyncio.wait_for on all Ollama calls (council.py, chairman.py, conversation_agent.py). Fixed fallback chain aborting early on non-memory errors. keep_alive 0 -> 5m (models stay warm in VRAM instead of reloading every step). Removed psutil RAM guard that silently downgraded everything to tinyllama. Smoke test passes: test_fix1_smoke.py (5 scenarios, zero crashes).
- 2026-08-23 - Team Lead: Board created. Starting task #3 next, then #4. Note for Bon: chairman being overly conservative in validate_plan (rejected a benign create_file plan) is KNOWN — prompt tuning comes later, do not touch chairman.py.
- 2026-08-23 - Team Lead: Task #3 DONE. (1) Deleted Code/main.py — verified diverged copy, root main.py is live. (2) core/autonomy.py: programmatically confirmed the first set of 6 shadowed methods was byte-identical to the second set, deleted the FIRST block (183 lines) so runtime behavior is unchanged; py_compile passes; exactly one definition of each remains. (3) main.py: removed unreachable duplicate send_email elif handler (was at :1910), unreachable duplicate send_email intent trigger (was at :1287), and redundant `elif "url"` double-print branch (unconditional url print already existed). Verified single occurrences via grep. Next: task #4 voice VAD.

====================================================================
## BON LOG
====================================================================
- (append entries here, prefix each with date - Bon:)

====================================================================
## DEV LOG
====================================================================
- (append entries here, prefix each with date - Dev:)

====================================================================
## SUPERVISOR ALERTS
====================================================================
- (Swapnil writes here when something goes wrong)
