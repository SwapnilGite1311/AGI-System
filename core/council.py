"""
LLM Council - Optimized with Sequential Loading
Only loads ONE model at a time to save RAM
"""

import asyncio
import json
import re
import os
from typing import Dict, Any, List, Optional
from ollama import AsyncClient
from loguru import logger

from core.config import load_config


MODEL_FALLBACKS = {
    "qwen2.5:14b": ["qwen2.5:14b", "qwen2.5:3b", "gemma2:2b", "tinyllama:latest"],
    "qwen2.5:7b": ["qwen2.5:7b", "qwen2.5:3b", "gemma2:2b", "tinyllama:latest"],
    "qwen2.5:3b": ["qwen2.5:3b", "gemma2:2b", "tinyllama:latest"],
    "llama3.1:8b": ["llama3.1:8b", "qwen2.5:3b", "gemma2:2b", "tinyllama:latest"],
    "mistral:7b": ["mistral:7b", "qwen2.5:3b", "gemma2:2b", "tinyllama:latest"],
    "llava:7b": ["llava:7b", "gemma2:2b", "tinyllama:latest"],
    "gemma2:2b": ["gemma2:2b", "tinyllama:latest"],
    "tinyllama": ["tinyllama:latest"],
    "tinyllama:latest": ["tinyllama:latest"],
}


def _degenerate_output(content: str) -> Optional[str]:
    """Is this generated text obviously unusable?

    Small models under-specified prompts fall into loops and placeholders.
    These checks are deliberately blunt - they are meant to catch output
    that is plainly broken, not to judge writing quality.
    """
    stripped = content.strip()

    if re.search(r"\b(?:your_?\w+_here|placeholder|todo_?here|xxx+|"
                 r"\w+_prose_here|lorem ipsum)\b", stripped, re.IGNORECASE):
        return "it is placeholder text, not real content"

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 6:
        unique = len(set(lines))
        if unique <= max(2, len(lines) // 5):
            return f"it repeats the same {unique} line(s) over and over"

    words = stripped.split()
    if len(words) >= 40 and len(set(words)) <= len(words) // 6:
        return "it loops on the same few words"

    return None


class LLMCouncil:
    """
    Optimized LLM Council with sequential model loading
    Peak RAM: Only 1 model at a time (~5-9GB max)
    """
    
    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize council"""
        
        self.config = load_config(config_path)
        ollama_config = self.config.get('ollama', {})
        self.ollama = AsyncClient(host=ollama_config.get('host', 'http://127.0.0.1:11434'))
        self.ollama_timeout = float(ollama_config.get('timeout', 120))
        self.keep_alive = str(ollama_config.get('keep_alive', '5m'))
        self.fallback_chain = list(ollama_config.get('fallback_chain', ['gemma2:2b', 'tinyllama:latest']))
        # num_gpu offloads to GPU when the host has VRAM to spare; 0 forces
        # CPU-only inference. See config/settings.json for the active value.
        num_gpu = ollama_config.get('num_gpu')
        self.base_options = {"num_ctx": 4096}
        if num_gpu is not None:
            self.base_options["num_gpu"] = int(num_gpu)
        self.council_config = self.config['llm_council']
        self.memory_limit_gb = self._detect_memory_limit_gb()
        
        # Track stats
        self.member_stats = {
            member: {"calls": 0, "successes": 0, "failures": 0}
            for member in self.council_config.keys()
        }
        
        logger.info("Optimized LLM Council initialized (sequential loading)")
    
    async def decide(self, task: str, complexity: str = "medium") -> Dict[str, Any]:
        """
        Main decision method with RAM optimization
        """
        
        logger.info("Council task ({}): {}", complexity, task[:100])
        
        if complexity == "simple":
            return await self._quick_decision(task)
        
        elif complexity == "medium":
            return await self._strategic_decision(task)
        
        elif complexity == "complex":
            return await self._sequential_council_decision(task)
        
        else:  # critical
            return await self._full_council_decision(task)
    
    def _normalize_model_name(self, model: str) -> str:
        """Normalize common model names to the exact tag Ollama expects."""
        if not model:
            return "gemma2:2b"
        if model == "tinyllama":
            return "tinyllama:latest"
        return model

    def _get_available_memory_gb(self) -> float:
        """Estimate available RAM in GB for safe model selection."""
        try:
            import psutil
            return round(psutil.virtual_memory().available / (1024 ** 3), 2)
        except Exception:
            return 8.0

    def _detect_memory_limit_gb(self) -> float:
        """Backward-compatible alias for available memory checks."""
        return self._get_available_memory_gb()

    def _select_model_for_member(self, member: str) -> str:
        """Return the member's configured model.

        All configured primaries are small enough to load fully into GPU VRAM,
        so no speculative downgrading based on system RAM. Real load failures
        are handled by the fallback chain in _generate_with_fallbacks.
        """
        council_cfg = getattr(self, "council_config", None)
        if council_cfg is None:
            council_cfg = getattr(self, "config", {}).get("llm_council", {})

        member_data = council_cfg.get(member, {})
        raw_model = member_data.get('model', 'gemma2:2b') if isinstance(member_data, dict) else 'gemma2:2b'
        return self._normalize_model_name(raw_model)

    def _model_candidates(self, member: str) -> List[str]:
        """Return a safe fallback chain for a council member."""
        preferred = self._select_model_for_member(member)
        return MODEL_FALLBACKS.get(preferred, [preferred, 'gemma2:2b', 'tinyllama:latest'])

    async def _quick_decision(self, task: str) -> Dict[str, Any]:
        """Fast decision using speed model"""
        
        member = "speed"
        model = self._select_model_for_member(member)
        
        prompt = f"""Fast response needed.

Task: {task}

Respond with an executable action plan in JSON. Use only these action names:
search, navigate, form, extract_text, open, status, process, run_command,
list, create_file, create_folder, organize, copy, move, screenshot, ocr,
create_task, list_tasks, send_email, calendar_event, schedule_reminder.

JSON schema:
{{
    "steps": [
        {{"action": "search", "params": {{"query": "example"}}}}
    ],
    "confidence": 0.0-1.0
}}

ONLY JSON:"""

        try:
            response, used_model = await self._generate_with_fallbacks(member, prompt)
            
            result = self._parse_response(response['response'])
            result['member'] = member
            result['model'] = used_model
            
            self.member_stats[member]['calls'] += 1
            self.member_stats[member]['successes'] += 1
            
            logger.info("âš¡ Quick decision by {} using {}", member, used_model)
            return result
            
        except Exception as e:
            logger.error("Quick decision failed: {}", str(e))
            self.member_stats[member]['calls'] += 1
            self.member_stats[member]['failures'] += 1
            return {"error": str(e), "member": member}
    
    async def _strategic_decision(self, task: str) -> Dict[str, Any]:
        """Strategic planning using strategist"""
        
        member = "strategist"
        model = self._select_model_for_member(member)
        
        prompt = f"""Strategic planning needed.

Task: {task}

Create an executable plan in JSON. Use only these action names:
search, navigate, form, extract_text, open, status, process, run_command,
list, create_file, create_folder, organize, copy, move, screenshot, ocr,
create_task, list_tasks, send_email, calendar_event, schedule_reminder.

Each step must include "action" and "params". Use params like:
- search: {{"query": "..."}}
- navigate: {{"url": "https://..."}}
- form: {{"fields": {{"name": "value"}}, "submit": false}}
- open: {{"app": "chrome"}}
- create_file: {{"path": "notes.txt", "content": "..."}}
- create_task: {{"title": "...", "params": {{"description": "..."}}}}
- send_email: {{"to_email": "a@b.com", "subject": "...", "body": "..."}}
- calendar_event: {{"title": "...", "start_time": "..."}}
- run_command: {{"command": "Get-Date", "shell": "powershell"}}

JSON schema:
{{
    "analysis": "brief analysis",
    "approach": "recommended approach",
    "action_plan": [
        {{"action": "search", "params": {{"query": "example"}}, "reason": "why"}}
    ],
    "risks": ["risk 1", "risk 2"],
    "confidence": 0.0-1.0
}}

ONLY JSON:"""

        try:
            response, used_model = await self._generate_with_fallbacks(member, prompt)
            
            result = self._parse_response(response['response'])
            result['member'] = member
            result['model'] = used_model
            
            self.member_stats[member]['calls'] += 1
            self.member_stats[member]['successes'] += 1
            
            logger.info("ðŸŽ¯ Strategic decision by {} using {}", member, used_model)
            return result
            
        except Exception as e:
            logger.error("Strategic decision failed: {}", str(e))
            self.member_stats[member]['calls'] += 1
            self.member_stats[member]['failures'] += 1
            return {"error": str(e), "member": member}
    
    async def _sequential_council_decision(self, task: str) -> Dict[str, Any]:
        """
        Sequential council: Load ONE model at a time
        This is the KEY optimization!
        """
        
        logger.info("Sequential council (RAM-optimized)...")
        # CPU-budget diet: strategist plans, chairman decides. The analyst and
        # executor opinions rarely change the outcome for complex (not critical)
        # tasks but double or triple latency on CPU-only inference.
        members_to_consult = ["strategist"]
        collected_opinions = {}
        
        # CRITICAL: Consult ONE AT A TIME
        for member in members_to_consult:
            logger.info(f"Consulting {member}...")
            
            opinion = await self._get_member_opinion(member, task)
            collected_opinions[member] = opinion
            
            # Small delay to ensure model unloads
            await asyncio.sleep(1)
        
        # Chairman synthesizes (loads chairman model)
        logger.info("Chairman synthesizing...")
        synthesis = await self._chairman_synthesize(task, collected_opinions)
        
        return synthesis
    
    async def _full_council_decision(self, task: str) -> Dict[str, Any]:
        """Full council for critical tasks"""
        
        logger.info("ðŸ›ï¸ FULL COUNCIL (critical task)...")
        
        all_members = ["strategist", "analyst", "executor", "speed"]
        collected_opinions = {}
        
        # Sequential consultation
        for member in all_members:
            logger.info(f"Consulting {member}...")
            opinion = await self._get_member_opinion(member, task)
            collected_opinions[member] = opinion
            await asyncio.sleep(1)
        
        # Chairman final decision
        logger.info("ðŸ‘‘ Chairman final decision...")
        final = await self._chairman_synthesize(task, collected_opinions)
        
        return final
    
    async def _get_member_opinion(self, member: str, task: str) -> Dict[str, Any]:
        """Get opinion from ONE member (loads only this model)"""
        
        model = self._select_model_for_member(member)
        role = self.council_config[member]['role']
        
        prompt = f"""You are the {role.upper()}.

Task: {task}

Your expert opinion in JSON:
{{
    "opinion": "your recommendation",
    "reasoning": "why",
    "confidence": 0.0-1.0
}}

ONLY JSON:"""

        try:
            # keep_alive="0": this is an intermediate opinion, not the final
            # answer - unload it immediately so a multi-member consultation
            # never holds more than one model resident at once.
            response, used_model = await self._generate_with_fallbacks(member, prompt, keep_alive="0")
            result = self._parse_response(response['response'])
            result['model'] = used_model
            return result

        except Exception as e:
            logger.error("{} failed: {}", member, str(e))
            return {"opinion": "unavailable", "error": str(e)}
    
    async def _chairman_synthesize(self, task: str, opinions: Dict[str, Any]) -> Dict[str, Any]:
        """Chairman makes final decision"""
        
        prompt = f"""You are the CHAIRMAN. Make the final executable decision.

Task: {task}

Council Opinions:
{json.dumps(opinions, indent=2)}

Return JSON with an executable action_plan. Use only these action names:
search, navigate, form, extract_text, open, status, process, run_command,
list, create_file, create_folder, organize, copy, move, screenshot, ocr,
create_task, list_tasks, send_email, calendar_event, schedule_reminder.

Final decision in JSON:
{{
    "final_decision": "your decision",
    "reasoning": "synthesis",
    "action_plan": [
        {{"action": "search", "params": {{"query": "example"}}, "reason": "why"}}
    ],
    "confidence": 0.0-1.0
}}

ONLY JSON:"""

        try:
            response, used_model = await self._generate_with_fallbacks("chairman", prompt)

            result = self._parse_response(response['response'])
            result['method'] = 'sequential_council'
            result['consulted'] = list(opinions.keys())
            result['model'] = used_model
            
            logger.success("âœ… Chairman decision complete")
            return result
            
        except Exception as e:
            logger.error("Chairman failed: {}", str(e))
            return {"error": str(e), "method": "chairman_failed"}
    
    async def _generate_with_fallbacks(
        self, member: str, prompt: str, options: Dict[str, Any] = None,
        images: List[bytes] = None, keep_alive: Optional[str] = None,
    ) -> tuple[Dict[str, Any], str]:
        """Try the preferred model first, then walk down the fallback chain on ANY failure.

        `keep_alive` defaults to the configured value; pass "0" for
        intermediate multi-member consultations so the model actually
        unloads before the next one loads - without this override, sequential
        and full council calls held every consulted model resident for the
        full keep_alive window simultaneously, contradicting this class's own
        "only one model at a time" design.
        """
        preferred = self._select_model_for_member(member)
        candidates = [preferred]
        for model in self.fallback_chain + MODEL_FALLBACKS.get(preferred, []):
            if model not in candidates:
                candidates.append(model)

        last_error = None
        for model in candidates:
            try:
                default_options = dict(self.base_options)
                if options:
                    default_options.update(options)
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "keep_alive": keep_alive if keep_alive is not None else self.keep_alive,
                    "options": default_options,
                }
                if images:
                    payload["images"] = images
                response = await asyncio.wait_for(
                    self.ollama.generate(**payload),
                    timeout=self.ollama_timeout,
                )
                return response, model
            except Exception as exc:
                last_error = exc
                logger.warning("Model {} failed for {}: {} - falling back", model, member, str(exc))
        if last_error:
            raise last_error
        raise RuntimeError("No model available")

    async def verify_outcome(self, command: str, summary: str) -> Dict[str, Any]:
        """Ask whether an already-executed outcome actually satisfies the request.

        Deliberately cheap: one short yes/no+reason call with a small
        num_predict, not a full re-plan. This is what turns "the handler
        returned success=True" into "the user actually got what they asked
        for" - previously success was purely structural (steps_completed ==
        steps_total), so a plan that ran every step without error but
        ignored part of the request (e.g. organizing a folder while ignoring
        an age filter the user specified) reported full success with
        nothing to catch the mismatch.

        Uses "strategist" (qwen2.5:3b), not "speed" (gemma2:2b): tested live
        against the organize-with-age-filter case above, gemma2:2b was too
        lenient and reported satisfied=True on the ignored filter, while
        qwen2.5:3b correctly caught it (satisfied=False, confidence 0.8).
        With GPU offload this call still lands in a few seconds.
        """
        member = "strategist"
        prompt = f"""You are a strict verifier. A task was executed. Decide if the outcome actually satisfies what the user asked for.

User asked: {command}

What happened: {summary[:800]}

Respond with ONLY this JSON, nothing else:
{{"satisfied": true or false, "confidence": 0.0-1.0, "reason": "one short sentence"}}"""

        try:
            response, used_model = await self._generate_with_fallbacks(
                member, prompt, options={"num_predict": 120}
            )
            result = self._parse_response(response["response"])
            if "error" in result:
                # Unparseable verification is not evidence of failure - do
                # not let a flaky verifier override a real success.
                return {"satisfied": True, "confidence": 0.0, "reason": "Verification response unparseable.", "verified": False}
            return {
                "satisfied": bool(result.get("satisfied", True)),
                "confidence": float(result.get("confidence", 0.5) or 0.5),
                "reason": str(result.get("reason", "")),
                "model": used_model,
                "verified": True,
            }
        except Exception as exc:
            logger.warning("Outcome verification unavailable: {}", str(exc))
            # Fail open: an unavailable verifier must never turn a real
            # success into a reported failure.
            return {"satisfied": True, "confidence": 0.0, "reason": f"Verification unavailable: {exc}", "verified": False}

    async def author_file_content(
        self, description: str, filename: str = ""
    ) -> Dict[str, Any]:
        """Write the body of a file the user described rather than quoted.

        "create a file named program.txt with code for a caesar cipher" has
        no literal content to lift out of it - the content has to be
        written. Without this the file was created empty.

        The extension steers the format, because a .py that opens with
        "Here is a Python program:" is broken in a way a .md would not be.
        """
        suffix = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt")
        format_note = {
            "py": "Valid Python only. No markdown fences, no prose outside comments.",
            "js": "Valid JavaScript only. No markdown fences, no prose around it.",
            "html": "A complete valid HTML document. No markdown fences.",
            "css": "Valid CSS only. No markdown fences.",
            "json": "Valid JSON only, nothing else.",
            "sh": "A valid shell script. No markdown fences.",
            "md": "Markdown prose.",
            "csv": "Comma-separated rows only, with a header row.",
        }.get(suffix, "")

        if not format_note:
            # The extension is not always the honest signal. "program.txt
            # with code for a caesar cipher" is a .txt asking for code, and
            # trusting the extension produced a paragraph ABOUT a cipher
            # instead of a cipher.
            wants_code = re.search(
                r"\b(?:code|program|script|function|class|algorithm|"
                r"implementation)\b", description, re.IGNORECASE)
            if wants_code:
                format_note = (
                    "Working, runnable code. Write the actual implementation - "
                    "not a description of it, not a placeholder, and not a note "
                    "explaining what you did not write. No markdown fences.")
            else:
                format_note = "Plain text prose."

        prompt = f"""Write the contents of a file.

The user asked for: {description}
Filename: {filename or "(unspecified)"}

Format: {format_note}

Write the COMPLETE contents of that file - it is written to disk exactly
as you give it, so anything that is not meant to be in the file must not
appear. Do not explain what you wrote, do not wrap it in code fences, and
do not leave anything out or describe it as unimplemented. Whatever was
asked for must actually be there, in full.

Respond with ONLY this JSON, nothing else:
{{"content": "the full file contents"}}"""

        try:
            response, used_model = await self._generate_with_fallbacks(
                "executor", prompt, options={"num_predict": 1200}
            )
            result = self._parse_response(response["response"])
            content = str((result or {}).get("content", ""))
            if not content.strip():
                return {"success": False, "error": "The model returned no content."}

            problem = _degenerate_output(content)
            if problem:
                # A 3B model asked for real code will sometimes emit
                # placeholder soup - "plaintext_prose_here" over and over.
                # Writing that to the user's file is worse than admitting
                # the model could not do it.
                logger.warning("Rejected authored content: {}", problem)
                return {
                    "success": False,
                    "error": (f"The local model could not write usable content "
                              f"({problem}). It is a 3B model - complex code is "
                              "past what it does reliably."),
                }

            return {
                "success": True,
                "content": content,
                "model": used_model,
            }
        except Exception as exc:
            logger.warning("Could not author file content: {}", str(exc))
            return {"success": False, "error": str(exc)}

    async def summarize_findings(self, topic: str, raw_text: str) -> Dict[str, Any]:
        """Turn raw scraped page text into an actual synthesized summary.

        Previously the "research and report" pipeline (core/task_decomposer.py's
        research_report template) just dumped the first 1500 characters of
        raw page text into a .txt file with no synthesis at all - "research"
        that never actually read or understood anything. This is what
        upgrades it into a real report: a short synthesis in prose, not a
        raw scrape.
        """
        prompt = f"""You are writing a research summary.

Topic: {topic}

Raw source material (may be messy web page text):
{raw_text[:4000]}

Write a clear, well-organized summary of the key findings relevant to the
topic, in 3-5 short paragraphs of plain prose. Do not just repeat the raw
text - synthesize it. If the source material has nothing relevant, say so
plainly instead of inventing findings.

Respond with ONLY this JSON, nothing else:
{{"summary": "the summary text"}}"""

        try:
            response, used_model = await self._generate_with_fallbacks(
                "strategist", prompt, options={"num_predict": 700}
            )
            result = self._parse_response(response["response"])
            summary = result.get("summary") if "error" not in result else None
            if not summary:
                # Model didn't return valid JSON - fall back to the raw
                # response text itself rather than failing the whole report.
                summary = response["response"].strip()
            return {"success": True, "summary": summary, "model": used_model}
        except Exception as exc:
            logger.warning("Findings summarization unavailable: {}", str(exc))
            return {"success": False, "summary": None, "error": str(exc)}

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from response"""
        
        cleaned = text.strip().replace('```json', '').replace('```', '').strip()
        
        if '{' in cleaned:
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            cleaned = cleaned[start:end]
        
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            # "error" must be present - process_command checks `if "error" in
            # plan` to detect a failed plan; without this key malformed model
            # output was silently treated as a valid (empty) plan.
            return {"raw_response": cleaned, "parse_error": "JSON failed", "error": "JSON failed"}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get council statistics"""
        return self.member_stats


# Test
async def test_council():
    """Test optimized council"""
    
    council = LLMCouncil()
    
    print("\n=== TEST: Simple Decision ===")
    result = await council.decide("What is 2+2?", "simple")
    print(json.dumps(result, indent=2))
    
    print("\n=== TEST: Complex Decision (Sequential) ===")
    result = await council.decide("Plan to organize my files", "complex")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(test_council())

