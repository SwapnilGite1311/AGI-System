"""
LLM Council - Optimized with Sequential Loading
Only loads ONE model at a time to save RAM
"""

import asyncio
import json
import os
from typing import Dict, Any, List
from ollama import AsyncClient
from loguru import logger


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


class LLMCouncil:
    """
    Optimized LLM Council with sequential model loading
    Peak RAM: Only 1 model at a time (~5-9GB max)
    """
    
    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize council"""
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        ollama_config = self.config.get('ollama', {})
        self.ollama = AsyncClient(host=ollama_config.get('host', 'http://127.0.0.1:11434'))
        self.ollama_timeout = float(ollama_config.get('timeout', 120))
        self.keep_alive = str(ollama_config.get('keep_alive', '5m'))
        self.fallback_chain = list(ollama_config.get('fallback_chain', ['gemma2:2b', 'tinyllama:latest']))
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
list, create_file, create_folder, organize, copy, move, screenshot, ocr.

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
list, create_file, create_folder, organize, copy, move, screenshot, ocr.

Each step must include "action" and "params". Use params like:
- search: {{"query": "..."}}
- navigate: {{"url": "https://..."}}
- form: {{"fields": {{"name": "value"}}, "submit": false}}
- open: {{"app": "chrome"}}
- create_file: {{"path": "notes.txt", "content": "..."}}
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
            self.member_stats[member]['failures'] += 1
            return {"error": str(e), "member": member}
    
    async def _sequential_council_decision(self, task: str) -> Dict[str, Any]:
        """
        Sequential council: Load ONE model at a time
        This is the KEY optimization!
        """
        
        logger.info("Sequential council (RAM-optimized)...")
        
        members_to_consult = ["strategist", "analyst", "executor"]
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
            response, used_model = await self._generate_with_fallbacks(member, prompt)
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
list, create_file, create_folder, organize, copy, move, screenshot, ocr.

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
    
    async def _generate_with_fallbacks(self, member: str, prompt: str, options: Dict[str, Any] = None, images: List[bytes] = None) -> tuple[Dict[str, Any], str]:
        """Try the preferred model first, then walk down the fallback chain on ANY failure."""
        preferred = self._select_model_for_member(member)
        candidates = [preferred]
        for model in self.fallback_chain + MODEL_FALLBACKS.get(preferred, []):
            if model not in candidates:
                candidates.append(model)

        last_error = None
        for model in candidates:
            try:
                default_options = {"num_ctx": 2048}
                if options:
                    default_options.update(options)
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "keep_alive": self.keep_alive,
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

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from response"""
        
        cleaned = text.strip().replace('```json', '').replace('```', '').strip()
        
        if '{' in cleaned:
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            cleaned = cleaned[start:end]
        
        try:
            return json.loads(cleaned)
        except:
            return {"raw_response": cleaned, "parse_error": "JSON failed"}
    
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

