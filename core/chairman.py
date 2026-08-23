"""
Chairman AI - The ultimate decision maker
Makes final calls when council members disagree or for critical tasks
"""

import asyncio
import json
from typing import Dict, Any, List
from ollama import AsyncClient
from loguru import logger


class Chairman:
    """
    The Chairman of the LLM Council
    - Makes final decisions on critical matters
    - Resolves conflicts between council members
    - Has highest authority in the system
    """
    
    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize Chairman with configuration"""
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        ollama_config = self.config.get('ollama', {})
        self.ollama = AsyncClient(host=ollama_config.get('host', 'http://127.0.0.1:11434'))
        self.ollama_timeout = float(ollama_config.get('timeout', 120))
        self.keep_alive = str(ollama_config.get('keep_alive', '5m'))
        self.model = self.config['llm_council']['chairman']['model']
        self.temperature = self.config['llm_council']['chairman']['temperature']
        
        logger.info("Chairman initialized with model: {}", self.model)
    
    async def make_final_decision(
        self, 
        task: str, 
        council_opinions: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Make the final, authoritative decision
        
        Args:
            task: The task at hand
            council_opinions: Opinions from all council members
            context: Additional context (user preferences, history, etc.)
        
        Returns:
            Final decision with full reasoning
        """
        
        logger.info("Chairman reviewing council opinions for final decision")
        
        prompt = self._build_decision_prompt(task, council_opinions, context)
        
        try:
            response = await asyncio.wait_for(
                self.ollama.generate(
                    model=self.model,
                    prompt=prompt,
                    options={
                        "temperature": self.temperature,
                        "num_predict": 2000,
                        "num_ctx": 2048
                    },
                    keep_alive=self.keep_alive
                ),
                timeout=self.ollama_timeout,
            )
            
            decision = self._parse_response(response['response'])
            decision['authority'] = 'chairman'
            decision['final'] = True
            
            logger.success("Chairman decision rendered")
            return decision
            
        except Exception as e:
            logger.error("Chairman decision failed: {}", str(e))
            return {
                "error": str(e),
                "fallback": "reverting to strategist recommendation",
                "authority": "chairman_failed"
            }
    
    async def resolve_conflict(
        self,
        conflicting_opinions: List[Dict[str, Any]],
        task: str
    ) -> Dict[str, Any]:
        """
        Resolve conflicts when council members disagree
        
        Args:
            conflicting_opinions: List of conflicting opinions
            task: The original task
        
        Returns:
            Resolution with reasoning
        """
        
        logger.warning("Conflict detected - Chairman intervening")
        
        prompt = f"""You are the CHAIRMAN resolving a conflict among AI council members.

Original Task: {task}

Conflicting Opinions:
{json.dumps(conflicting_opinions, indent=2)}

As Chairman, you must:
1. Analyze each opinion objectively
2. Identify the core disagreement
3. Make the FINAL decision that serves the user best
4. Explain your reasoning clearly

Provide resolution in JSON:
{{
    "conflict_summary": "what they disagreed about",
    "chosen_approach": "your final decision",
    "reasoning": "why this is the best path",
    "overruled": ["which opinions were rejected and why"],
    "confidence": 0.0-1.0
}}

Respond ONLY with JSON."""

        try:
            response = await asyncio.wait_for(
                self.ollama.generate(
                    model=self.model,
                    prompt=prompt,
                    options={
                        "temperature": self.temperature,
                        "num_predict": 2000,
                        "num_ctx": 2048
                    },
                    keep_alive=self.keep_alive
                ),
                timeout=self.ollama_timeout,
            )

            resolution = self._parse_response(response['response'])
            resolution['authority'] = 'chairman'
            resolution['resolution_type'] = 'conflict_resolution'

            logger.success("Chairman conflict resolution rendered")
            return resolution

        except Exception as e:
            logger.error("Conflict resolution failed: {}", str(e))
            return self._emergency_fallback(conflicting_opinions)

    async def validate_plan(self, plan: Dict[str, Any], task: str) -> Dict[str, Any]:
        """
        Validate a council-produced action plan before it is executed.
        Used as the safety gate for "critical" complexity commands
        (e.g. delete, format, shutdown, registry edits).

        Args:
            plan: The proposed action plan from the council
            task: The original user command

        Returns:
            Validation result containing at least 'approved' (bool) and 'reasoning' (str)
        """

        logger.info("Chairman validating plan for critical task: {}", task[:100])

        prompt = f"""You are the CHAIRMAN reviewing a proposed action plan for a CRITICAL task before it is executed.

Task: {task}

Proposed Plan:
{json.dumps(plan, indent=2, default=str)}

Review this plan for safety and correctness:
- REJECT only if a step is destructive or irreversible (deleting/formatting data, shutdown, registry edits, sending messages to real recipients without confirmation) or if the plan clearly does NOT accomplish the stated task.
- APPROVE routine operations: creating/editing files the user asked for, opening apps, searches, navigation, reading status.
- Do NOT reject a plan merely because it lacks extra safeguards - if the actions themselves are safe and match the task, approve it.

Respond ONLY with JSON:
{{
    "approved": true or false,
    "final_verdict": "approve" or "reject",
    "reasoning": "why you approved or rejected this plan",
    "concerns": ["any risks or issues identified"],
    "confidence": 0.0-1.0
}}"""

        try:
            response = await asyncio.wait_for(
                self.ollama.generate(
                    model=self.model,
                    prompt=prompt,
                    options={
                        "temperature": self.temperature,
                        "num_predict": 1500,
                        "num_ctx": 2048
                    },
                    keep_alive=self.keep_alive
                ),
                timeout=self.ollama_timeout,
            )

            validation = self._parse_response(response['response'])
            validation.setdefault("approved", False)
            validation['authority'] = 'chairman'

            if validation.get("approved"):
                logger.success("Plan approved by Chairman")
            else:
                logger.warning("Plan rejected by Chairman")
            
            return validation
            
        except Exception as e:
            logger.error("Validation failed: {}", str(e))
            # Fail-safe: reject if validation fails
            return {
                "approved": False,
                "final_verdict": "reject",
                "reasoning": f"Validation error: {str(e)}",
                "error": str(e)
            }
    
    def _build_decision_prompt(
        self, 
        task: str, 
        opinions: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> str:
        """Build comprehensive prompt for chairman decision"""
        
        context_str = ""
        if context:
            context_str = f"\nAdditional Context:\n{json.dumps(context, indent=2)}\n"
        
        return f"""You are the CHAIRMAN of an elite AI council. Make the final, authoritative decision.

Task: {task}
{context_str}
Council Member Opinions:
{json.dumps(opinions, indent=2)}

As Chairman, synthesize all input and make the BEST decision. Consider:
- Which opinions have strongest reasoning?
- What are the risks and benefits?
- What would serve the user best?
- Are there overlooked aspects?

Provide your FINAL decision in JSON:
{{
    "chairman_decision": "your authoritative decision",
    "synthesis": "how you combined the best ideas",
    "reasoning": "your complete reasoning process",
    "action_plan": [
        {{"step": "detailed step 1", "assigned_to": "which agent executes"}},
        {{"step": "detailed step 2", "assigned_to": "which agent executes"}}
    ],
    "risk_mitigation": ["how to handle potential issues"],
    "success_criteria": ["how to know if it worked"],
    "confidence": 0.0-1.0
}}

Respond ONLY with JSON."""
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        
        cleaned = response_text.strip()
        cleaned = cleaned.replace('```json', '').replace('```', '').strip()
        
        if '{' in cleaned and '}' in cleaned:
            start = cleaned.find('{')
            end = cleaned.rfind('}') + 1
            cleaned = cleaned[start:end]
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"raw_response": cleaned, "parse_error": "JSON decode failed"}
    
    def _emergency_fallback(self, opinions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Emergency fallback when chairman fails"""
        
        logger.warning("🚨 Emergency fallback activated")
        
        # Choose opinion with highest confidence
        best = max(opinions, key=lambda x: x.get('confidence', 0))
        
        return {
            "resolution_type": "emergency_fallback",
            "chosen": best,
            "reasoning": "Chairman unavailable, selected highest confidence opinion",
            "warning": "This is a fallback decision, review recommended"
        }


# Test function
async def test_chairman():
    """Test chairman decision-making"""
    
    # Remove this problematic import:
    # from core.council import LLMCouncil
    
    chairman = Chairman()
    
    print("\n=== TEST: Chairman Final Decision ===")
    
    # Simulate a complex task
    task = "Should I delete old backup files to free up space?"
    
    # Simulate council opinions (no need to actually run council for test)
    opinions = {
        "strategist": {
            "opinion": "Create archive before deletion",
            "confidence": 0.8
        },
        "analyst": {
            "opinion": "Analyze which files are safe to delete",
            "confidence": 0.9
        },
        "executor": {
            "opinion": "Delete immediately to free space",
            "confidence": 0.6
        }
    }
    
    # Chairman makes final call
    decision = await chairman.make_final_decision(task, opinions)
    print(json.dumps(decision, indent=2))
    
    print("\n=== TEST: Conflict Resolution ===")
    
    conflicts = [
        {"member": "strategist", "opinion": "Wait and analyze more", "confidence": 0.7},
        {"member": "executor", "opinion": "Act immediately", "confidence": 0.8}
    ]
    
    resolution = await chairman.resolve_conflict(conflicts, task)
    print(json.dumps(resolution, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_chairman())