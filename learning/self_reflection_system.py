"""
Self-Reflection System - Analyze Own Performance and Improve
Advanced self-awareness and introspection capabilities for autonomous improvement.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - some features limited")


class SelfReflectionSystem:
    """
    Self-reflection system for analyzing own performance:
    - Performance analysis and introspection
    - Decision quality assessment
    - Capability gap identification
    - Self-improvement planning
    - Cognitive bias detection
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize self-reflection system."""
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self.reflection_path = Path("data/self_reflection")
        self.reflection_path.mkdir(parents=True, exist_ok=True)
        
        self.reflection_history = self._load_reflection_history()
        self.capability_profile = self._load_capability_profile()
        self.performance_metrics = self._load_performance_metrics()
        
        logger.info("Self-Reflection System initialized")

    def _load_reflection_history(self) -> List[Dict[str, Any]]:
        """Load reflection history from storage."""
        history_path = self.reflection_path / "reflection_history.json"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load reflection history: {}", str(e))
        return []

    def _load_capability_profile(self) -> Dict[str, Any]:
        """Load capability profile from storage."""
        profile_path = self.reflection_path / "capability_profile.json"
        if profile_path.exists():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load capability profile: {}", str(e))
        return self._initialize_capability_profile()

    def _load_performance_metrics(self) -> Dict[str, Any]:
        """Load performance metrics from storage."""
        metrics_path = self.reflection_path / "performance_metrics.json"
        if metrics_path.exists():
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load performance metrics: {}", str(e))
        return {}

    def _initialize_capability_profile(self) -> Dict[str, Any]:
        """Initialize default capability profile."""
        return {
            "agent_capabilities": {
                "conversation": {"proficiency": 0.8, "experience": 100},
                "learning": {"proficiency": 0.7, "experience": 80},
                "system": {"proficiency": 0.9, "experience": 150},
                "vision": {"proficiency": 0.6, "experience": 50},
                "file": {"proficiency": 0.85, "experience": 120},
                "web": {"proficiency": 0.75, "experience": 90},
                "business": {"proficiency": 0.8, "experience": 100},
                "business_process": {"proficiency": 0.7, "experience": 60},
                "security": {"proficiency": 0.75, "experience": 70},
                "analytics": {"proficiency": 0.7, "experience": 65},
                "advanced_neural": {"proficiency": 0.6, "experience": 40}
            },
            "overall_intelligence": 0.73,
            "learning_rate": 0.05,
            "adaptability": 0.8
        }

    def _save_reflection_history(self):
        """Save reflection history to storage."""
        try:
            history_path = self.reflection_path / "reflection_history.json"
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.reflection_history, f, indent=2)
        except Exception as e:
            logger.error("Failed to save reflection history: {}", str(e))

    def _save_capability_profile(self):
        """Save capability profile to storage."""
        try:
            profile_path = self.reflection_path / "capability_profile.json"
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(self.capability_profile, f, indent=2)
        except Exception as e:
            logger.error("Failed to save capability profile: {}", str(e))

    def _save_performance_metrics(self):
        """Save performance metrics to storage."""
        try:
            metrics_path = self.reflection_path / "performance_metrics.json"
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(self.performance_metrics, f, indent=2)
        except Exception as e:
            logger.error("Failed to save performance metrics: {}", str(e))

    def perform_self_reflection(
        self,
        recent_actions: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive self-reflection on recent actions."""
        
        reflection_id = str(uuid.uuid4())
        
        try:
            # Analyze action outcomes
            action_analysis = self._analyze_action_outcomes(recent_actions)
            
            # Assess decision quality
            decision_quality = self._assess_decision_quality(recent_actions)
            
            # Identify capability gaps
            capability_gaps = self._identify_capability_gaps(recent_actions)
            
            # Detect cognitive biases
            cognitive_biases = self._detect_cognitive_biases(recent_actions)
            
            # Calculate overall performance score
            performance_score = self._calculate_performance_score(
                action_analysis, decision_quality, capability_gaps
            )
            
            # Generate improvement suggestions
            improvement_suggestions = self._generate_improvement_suggestions(
                action_analysis, decision_quality, capability_gaps, cognitive_biases
            )
            
            reflection = {
                "id": reflection_id,
                "timestamp": datetime.now().isoformat(),
                "context": context or {},
                "action_analysis": action_analysis,
                "decision_quality": decision_quality,
                "capability_gaps": capability_gaps,
                "cognitive_biases": cognitive_biases,
                "performance_score": performance_score,
                "improvement_suggestions": improvement_suggestions
            }
            
            self.reflection_history.append(reflection)
            self._save_reflection_history()
            
            # Update capability profile based on reflection
            self._update_capability_profile(reflection)
            
            return {
                "success": True,
                "reflection": reflection,
                "message": f"Self-reflection completed. Performance score: {performance_score:.3f}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Self-reflection failed: {str(e)}"
            }

    def _analyze_action_outcomes(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze outcomes of recent actions."""
        
        if not actions:
            return {"total_actions": 0, "success_rate": 0.0, "failure_rate": 0.0}
        
        successful_actions = [a for a in actions if a.get("success", False)]
        failed_actions = [a for a in actions if not a.get("success", True)]
        
        success_rate = len(successful_actions) / len(actions) if actions else 0.0
        failure_rate = len(failed_actions) / len(actions) if actions else 0.0
        
        # Analyze action types
        action_types = {}
        for action in actions:
            action_type = action.get("type", "unknown")
            action_types[action_type] = action_types.get(action_type, 0) + 1
        
        # Calculate execution times
        execution_times = [a.get("execution_time", 0.0) for a in actions if "execution_time" in a]
        avg_execution_time = np.mean(execution_times) if execution_times else 0.0
        
        return {
            "total_actions": len(actions),
            "successful_actions": len(successful_actions),
            "failed_actions": len(failed_actions),
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "action_types": action_types,
            "average_execution_time": avg_execution_time
        }

    def _assess_decision_quality(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess the quality of decisions made."""
        
        if not actions:
            return {"decision_count": 0, "average_quality": 0.0}
        
        decision_qualities = []
        
        for action in actions:
            # Assess decision quality based on multiple factors
            quality_score = 0.0
            
            # Success contribution
            if action.get("success", False):
                quality_score += 0.4
            
            # Efficiency contribution
            execution_time = action.get("execution_time", 10.0)
            if execution_time < 5.0:
                quality_score += 0.3
            elif execution_time < 10.0:
                quality_score += 0.2
            
            # Confidence contribution
            confidence = action.get("confidence", 0.5)
            quality_score += confidence * 0.3
            
            decision_qualities.append(quality_score)
        
        if decision_qualities:
            if NUMPY_AVAILABLE:
                average_quality = np.mean(decision_qualities)
            else:
                average_quality = sum(decision_qualities) / len(decision_qualities)
        else:
            average_quality = 0.0
        
        return {
            "decision_count": len(actions),
            "average_quality": average_quality,
            "decision_qualities": decision_qualities,
            "high_quality_decisions": len([q for q in decision_qualities if q > 0.7]),
            "low_quality_decisions": len([q for q in decision_qualities if q < 0.4])
        }

    def _identify_capability_gaps(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Identify gaps in current capabilities."""
        
        capability_gaps = []
        
        # Analyze which agent capabilities were used and their success rates
        agent_usage = {}
        for action in actions:
            agent = action.get("agent", "unknown")
            if agent not in agent_usage:
                agent_usage[agent] = {"total": 0, "successful": 0}
            agent_usage[agent]["total"] += 1
            if action.get("success", False):
                agent_usage[agent]["successful"] += 1
        
        # Identify agents with low success rates
        for agent, usage in agent_usage.items():
            if usage["total"] > 0:
                success_rate = usage["successful"] / usage["total"]
                if success_rate < 0.7:
                    capability_gaps.append({
                        "agent": agent,
                        "success_rate": success_rate,
                        "total_attempts": usage["total"],
                        "gap_severity": "high" if success_rate < 0.5 else "medium"
                    })
        
        # Check against capability profile
        for agent, capability in self.capability_profile["agent_capabilities"].items():
            if capability["proficiency"] < 0.7:
                capability_gaps.append({
                    "agent": agent,
                    "current_proficiency": capability["proficiency"],
                    "required_proficiency": 0.8,
                    "gap_severity": "high" if capability["proficiency"] < 0.5 else "medium"
                })
        
        return {
            "total_gaps": len(capability_gaps),
            "capability_gaps": capability_gaps,
            "agent_usage": agent_usage
        }

    def _detect_cognitive_biases(self, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect potential cognitive biases in decision-making."""
        
        detected_biases = []
        
        # Check for confirmation bias (favoring familiar actions)
        action_types = [a.get("type", "unknown") for a in actions]
        type_counts = {}
        for action_type in action_types:
            type_counts[action_type] = type_counts.get(action_type, 0) + 1
        
        if len(type_counts) > 0:
            max_count = max(type_counts.values())
            if max_count / len(actions) > 0.7:
                detected_biases.append({
                    "bias_type": "confirmation_bias",
                    "description": "Over-reliance on familiar action types",
                    "severity": "medium"
                })
        
        # Check for anchoring bias (consistent preference for similar solutions)
        if len(actions) > 3:
            action_values = [a.get("confidence", 0.5) for a in actions]
            if np.std(action_values) < 0.1:
                detected_biases.append({
                    "bias_type": "anchoring_bias",
                    "description": "Consistent confidence values suggest anchoring",
                    "severity": "low"
                })
        
        # Check for availability bias (recent actions influence)
        if len(actions) > 5:
            recent_success = [a.get("success", False) for a in actions[-3:]]
            if all(recent_success):
                detected_biases.append({
                    "bias_type": "availability_bias",
                    "description": "Recent success may be influencing decisions",
                    "severity": "low"
                })
        
        return {
            "total_biases": len(detected_biases),
            "detected_biases": detected_biases
        }

    def _calculate_performance_score(
        self,
        action_analysis: Dict[str, Any],
        decision_quality: Dict[str, Any],
        capability_gaps: Dict[str, Any]
    ) -> float:
        """Calculate overall performance score."""
        
        # Action performance component (40%)
        action_score = action_analysis.get("success_rate", 0.0) * 0.4
        
        # Decision quality component (30%)
        decision_score = decision_quality.get("average_quality", 0.0) * 0.3
        
        # Capability component (20%)
        total_gaps = capability_gaps.get("total_gaps", 0)
        capability_score = max(0.0, (1.0 - total_gaps * 0.1)) * 0.2
        
        # Efficiency component (10%)
        avg_time = action_analysis.get("average_execution_time", 10.0)
        efficiency_score = max(0.0, (1.0 - avg_time / 20.0)) * 0.1
        
        return action_score + decision_score + capability_score + efficiency_score

    def _generate_improvement_suggestions(
        self,
        action_analysis: Dict[str, Any],
        decision_quality: Dict[str, Any],
        capability_gaps: Dict[str, Any],
        cognitive_biases: Dict[str, Any]
    ) -> List[str]:
        """Generate improvement suggestions based on analysis."""
        
        suggestions = []
        
        # Action-based suggestions
        if action_analysis.get("success_rate", 0.0) < 0.8:
            suggestions.append("Improve action success rate through better task planning")
        
        if action_analysis.get("average_execution_time", 0.0) > 10.0:
            suggestions.append("Optimize execution time through parallel processing or caching")
        
        # Decision-based suggestions
        if decision_quality.get("average_quality", 0.0) < 0.7:
            suggestions.append("Enhance decision quality through better information gathering")
        
        # Capability-based suggestions
        for gap in capability_gaps.get("capability_gaps", []):
            if gap.get("gap_severity") == "high":
                suggestions.append(f"Address critical capability gap in {gap.get('agent', 'unknown')} agent")
        
        # Bias-based suggestions
        for bias in cognitive_biases.get("detected_biases", []):
            if bias.get("severity") == "high":
                suggestions.append(f"Mitigate {bias.get('bias_type', 'unknown')} to improve decision quality")
        
        # General suggestions
        if not suggestions:
            suggestions.append("Maintain current performance through continuous monitoring")
        
        return suggestions

    def _update_capability_profile(self, reflection: Dict[str, Any]):
        """Update capability profile based on reflection."""
        
        # Update overall intelligence
        current_intelligence = self.capability_profile.get("overall_intelligence", 0.5)
        performance_score = reflection.get("performance_score", 0.5)
        
        # Gradual learning rate update
        learning_rate = self.capability_profile.get("learning_rate", 0.05)
        new_intelligence = current_intelligence + (performance_score - current_intelligence) * learning_rate
        
        self.capability_profile["overall_intelligence"] = new_intelligence
        
        # Update adaptability based on recent reflections
        recent_reflections = self.reflection_history[-10:] if len(self.reflection_history) > 10 else self.reflection_history
        if recent_reflections:
            recent_scores = [r.get("performance_score", 0.5) for r in recent_reflections]
            if NUMPY_AVAILABLE:
                trend = np.polyfit(range(len(recent_scores)), recent_scores, 1)[0]
            else:
                # Simple trend calculation without numpy
                if len(recent_scores) > 1:
                    trend = (recent_scores[-1] - recent_scores[0]) / len(recent_scores)
                else:
                    trend = 0.0
            adaptability = max(0.0, min(1.0, 0.5 + trend))
            self.capability_profile["adaptability"] = adaptability
        
        self._save_capability_profile()

    def generate_self_improvement_plan(
        self,
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate a comprehensive self-improvement plan."""
        
        try:
            # Analyze current state
            current_intelligence = self.capability_profile.get("overall_intelligence", 0.5)
            adaptability = self.capability_profile.get("adaptability", 0.5)
            
            # Identify priority areas
            capability_gaps = []
            for agent, capability in self.capability_profile["agent_capabilities"].items():
                if capability["proficiency"] < 0.8:
                    capability_gaps.append({
                        "agent": agent,
                        "current_proficiency": capability["proficiency"],
                        "target_proficiency": 0.9,
                        "improvement_priority": "high" if capability["proficiency"] < 0.6 else "medium"
                    })
            
            # Sort by proficiency (lowest first)
            capability_gaps.sort(key=lambda x: x["current_proficiency"])
            
            # Generate improvement steps
            improvement_steps = []
            
            for gap in capability_gaps[:5]:  # Focus on top 5 gaps
                step = {
                    "area": gap["agent"],
                    "current_level": gap["current_proficiency"],
                    "target_level": gap["target_proficiency"],
                    "actions": [
                        f"Increase training frequency for {gap['agent']} capabilities",
                        f"Analyze failure patterns in {gap['agent']} tasks",
                        f"Improve resource allocation for {gap['agent']} operations"
                    ],
                    "estimated_improvement": gap["target_proficiency"] - gap["current_proficiency"],
                    "priority": gap["improvement_priority"]
                }
                improvement_steps.append(step)
            
            # Calculate overall improvement potential
            total_improvement_potential = sum(step["estimated_improvement"] for step in improvement_steps)
            target_intelligence = min(1.0, current_intelligence + total_improvement_potential * 0.1)
            
            improvement_plan = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(),
                "current_intelligence": current_intelligence,
                "target_intelligence": target_intelligence,
                "adaptability": adaptability,
                "focus_areas": focus_areas or ["all"],
                "improvement_steps": improvement_steps,
                "estimated_completion_time": f"{len(improvement_steps) * 7} days",
                "success_probability": adaptability
            }
            
            return {
                "success": True,
                "improvement_plan": improvement_plan,
                "message": f"Self-improvement plan generated. Target intelligence: {target_intelligence:.3f}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Self-improvement plan generation failed: {str(e)}"
            }

    def execute_self_improvement(
        self,
        improvement_plan_id: str,
        step_index: int = 0
    ) -> Dict[str, Any]:
        """Execute a step from the self-improvement plan."""
        
        # In a real implementation, this would execute actual improvement actions
        # For now, simulate the execution
        
        try:
            # Simulate improvement execution
            improvement_result = {
                "step_index": step_index,
                "execution_status": "completed",
                "improvement_achieved": np.random.uniform(0.05, 0.15),
                "execution_time": np.random.uniform(10, 30),
                "resource_usage": np.random.uniform(20, 40)
            }
            
            return {
                "success": True,
                "improvement_result": improvement_result,
                "message": f"Self-improvement step {step_index} executed successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Self-improvement execution failed: {str(e)}"
            }

    def get_intelligence_summary(self) -> Dict[str, Any]:
        """Get comprehensive intelligence summary."""
        
        return {
            "success": True,
            "intelligence_summary": {
                "overall_intelligence": self.capability_profile.get("overall_intelligence", 0.5),
                "adaptability": self.capability_profile.get("adaptability", 0.5),
                "learning_rate": self.capability_profile.get("learning_rate", 0.05),
                "agent_capabilities": self.capability_profile.get("agent_capabilities", {}),
                "total_reflections": len(self.reflection_history),
                "recent_performance": np.mean([r.get("performance_score", 0.5) for r in self.reflection_history[-10:]]) if self.reflection_history else 0.0
            },
            "message": "Intelligence summary generated successfully"
        }