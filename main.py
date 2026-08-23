"""
Autonomous System Controller (ASC) - Main Entry Point
Implements direct execution, learning-assisted routing, intelligent form
handling, and decomposed multi-step task execution.
"""

import asyncio
import json
import os
import re
import struct
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pyaudio
import requests
from loguru import logger

if sys.platform == "win32":
    import winsound

from agents.file_agent import FileAgent
from agents.learning_agent import LearningAgent
from agents.conversation_agent import ConversationAgent
from agents.system_agent import SystemAgent
from agents.vision_agent import VisionAgent
from agents.web_agent import WebAgent
from agents.business_agent import BusinessAgent
from agents.business_process_automation import BusinessProcessAutomation
from agents.enterprise_security import EnterpriseSecurity
from agents.advanced_analytics import AdvancedAnalytics
from learning.advanced_neural_network import AdvancedNeuralNetwork
from learning.meta_learning_system import MetaLearningSystem
from learning.self_reflection_system import SelfReflectionSystem
from learning.autonomous_goal_system import AutonomousGoalSystem
from learning.concept_discovery_system import ConceptDiscoverySystem
from learning.self_programming_system import SelfProgrammingSystem
from learning.algorithm_optimization_system import AlgorithmOptimizationSystem
from learning.self_evolving_architecture import SelfEvolvingArchitecture
from learning.advanced_cognitive_architecture import AdvancedCognitiveArchitecture
from core.chairman import Chairman
from core.council import LLMCouncil
from core.autonomy import AutonomyEngine
from core.memory import MemorySystem
from core.task_decomposer import TaskDecomposer
from core.tool_registry import ToolRegistry, ToolSpec


class AutonomousSystemController:
    """Main ASC controller and execution orchestrator."""

    BROWSER_APPS = {
        "browser",
        "chrome",
        "google",
        "google chrome",
        "youtube",
        "edge",
        "microsoft edge",
        "firefox",
        "brave",
        "opera",
    }

    def __init__(self, config_path: str = "./config/settings.json"):
        self._setup_logging()

        logger.info("=" * 60)
        logger.info("AUTONOMOUS SYSTEM CONTROLLER v1.0")
        logger.info("=" * 60)

        with open(config_path, "r", encoding="utf-8") as file:
            self.config = json.load(file)

        logger.info("Initializing core systems...")
        self.council = LLMCouncil(config_path)
        self.chairman = Chairman(config_path)
        self.memory = MemorySystem(config_path)
        self.task_decomposer = TaskDecomposer()
        self.autonomy = AutonomyEngine(self.task_decomposer, self.get_tool_manifest)

        logger.info("Initializing agents...")
        learning_agent = LearningAgent(config_path)
        conversation_agent = ConversationAgent(config_path)
        system_agent = SystemAgent(config_path)
        
        # Auto-start Ollama if not already running
        logger.info("Checking Ollama status...")
        if not system_agent.health_check_ollama(timeout=2.0):
            logger.info("Ollama not running, attempting auto-start...")
            ollama_start_result = system_agent.start_ollama(wait=True, timeout=30)
            if ollama_start_result.get("success"):
                logger.info(f"Ollama auto-started successfully (PID: {ollama_start_result.get('pid')})")
            else:
                logger.warning(f"Ollama auto-start failed: {ollama_start_result.get('error')}")
        else:
            logger.info("Ollama is already running")
        
        vision_agent = VisionAgent(config_path)
        file_agent = FileAgent(config_path)
        web_agent = WebAgent(
            config_path=config_path,
            system_agent=system_agent,
            vision_agent=vision_agent,
            learning_agent=learning_agent,
        )
        business_agent = BusinessAgent(config_path)
        business_process_agent = BusinessProcessAutomation(config_path)
        security_agent = EnterpriseSecurity(config_path)
        analytics_agent = AdvancedAnalytics(config_path)
        advanced_neural_agent = AdvancedNeuralNetwork(config_path)
        meta_learning_agent = MetaLearningSystem(config_path)
        self_reflection_agent = SelfReflectionSystem(config_path)
        autonomous_goal_agent = AutonomousGoalSystem(config_path)
        concept_discovery_agent = ConceptDiscoverySystem(config_path)
        self_programming_agent = SelfProgrammingSystem(config_path)
        algorithm_optimization_agent = AlgorithmOptimizationSystem(config_path)
        self_evolving_agent = SelfEvolvingArchitecture(config_path)
        cognitive_agent = AdvancedCognitiveArchitecture(config_path)

        self.agents = {
            "conversation": conversation_agent,
            "learning": learning_agent,
            "system": system_agent,
            "vision": vision_agent,
            "file": file_agent,
            "web": web_agent,
            "business": business_agent,
            "business_process": business_process_agent,
            "security": security_agent,
            "analytics": analytics_agent,
            "advanced_neural": advanced_neural_agent,
            "meta_learning": meta_learning_agent,
            "self_reflection": self_reflection_agent,
            "autonomous_goals": autonomous_goal_agent,
            "concept_discovery": concept_discovery_agent,
            "self_programming": self_programming_agent,
            "algorithm_optimization": algorithm_optimization_agent,
            "self_evolving": self_evolving_agent,
            "cognitive": cognitive_agent,
        }

        execution_config = self.config.get("execution", {})
        self.command_cache: Dict[str, Dict[str, Any]] = {}
        self.command_cache_size = int(execution_config.get("command_cache_size", 100))
        self.execution_pause_seconds = float(execution_config.get("direct_pause_seconds", 0.3))
        self.decompose_complex_tasks = bool(execution_config.get("decompose_complex_tasks", True))
        self.tier_stats = {"direct": 0, "single_model": 0, "sequential": 0}
        self.tool_registry = self._build_tool_registry()

        audio_config = self.config.get("audio", {})
        self.voice_enabled = bool(audio_config.get("voice_enabled", False))
        self.voice_service_url = audio_config.get("voice_service_url", "http://localhost:5000")
        self.wake_word = audio_config.get("wake_word", "hey assistant")
        self.stt_model = audio_config.get("stt_model", "whisper")
        self.tts_engine = audio_config.get("tts_engine", "pyttsx3")
        self.voice_service_available = self._check_voice_service() if self.voice_enabled else False
        
        # Auto-start voice server if enabled
        if self.voice_enabled and not self.voice_service_available:
            logger.info("Voice enabled but server unavailable, attempting auto-start...")
            try:
                voice_start = self.agents["system"].start_voice_server(wait=True, timeout=10)
                if voice_start.get("success"):
                    self.voice_service_available = True
                    logger.success("Voice server auto-started successfully")
                else:
                    logger.warning("Voice server auto-start failed: {}", voice_start.get("error"))
            except Exception as exc:
                logger.warning("Voice server auto-start exception: {}", str(exc))

        self.session_id = self.memory.start_session()
        self.running = False

        logger.success("All systems initialized")
        logger.info("=" * 60)

    def _setup_logging(self):
        """Configure console and file logging."""

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        logger.remove()
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
            level="INFO",
        )

        Path("./logs").mkdir(exist_ok=True)
        logger.add(
            "./logs/asc_{time}.log",
            rotation="1 day",
            retention="7 days",
            level="DEBUG",
        )

    def _check_voice_service(self) -> bool:
        """Check whether the local voice service is available."""

        health = self._get_voice_service_health()
        return health.get("available", False)

    def _get_voice_service_health(self) -> Dict[str, Any]:
        """Return detailed voice service status for diagnostics."""

        try:
            response = requests.get(f"{self.voice_service_url}/health", timeout=5)
            data = response.json() if response.content else {}
            return {
                "available": response.status_code == 200,
                "status_code": response.status_code,
                "service_status": data.get("status", "unknown"),
                "missing": data.get("missing", []),
                "url": self.voice_service_url,
            }
        except Exception as exc:
            return {
                "available": False,
                "url": self.voice_service_url,
                "error": str(exc),
            }

    @staticmethod
    def _rms_energy(pcm_data: bytes) -> float:
        """Root-mean-square energy of 16-bit little-endian PCM frames."""
        count = len(pcm_data) // 2
        if not count:
            return 0.0
        samples = struct.unpack(f"<{count}h", pcm_data[: count * 2])
        return (sum(s * s for s in samples) / count) ** 0.5

    def _record_audio(
        self,
        duration: int = 10,
        rate: int = 16000,
        channels: int = 1,
        silence_ms: int = 1200,
    ) -> Optional[str]:
        """Record microphone audio to a temporary WAV file with basic VAD.

        Calibrates ambient noise for ~320ms, records until speech is detected
        and then ~`silence_ms` of silence passes, or until `duration` seconds.
        """
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=1024,
            )
            print("Listening (speak, then pause)...")
            frames = []
            try:
                frame_ms = 1000.0 * 1024 / rate  # ~64ms per 1024-sample frame
                silence_frame_limit = max(1, int(silence_ms / frame_ms))
                calibration_frames = 5  # ~320ms noise-floor estimate

                noise_floor = 0.0
                for _ in range(calibration_frames):
                    noise_floor = max(noise_floor, self._rms_energy(stream.read(1024, exception_on_overflow=False)))

                threshold = max(noise_floor * 2.5, 300.0)
                speech_detected = False
                silent_frames_after_speech = 0
                min_frames_before_stop = int(1000 / frame_ms)  # record at least ~1s total

                total_frames = int(rate / 1024 * duration)
                for index in range(total_frames):
                    data = stream.read(1024, exception_on_overflow=False)
                    frames.append(data)

                    if self._rms_energy(data) > threshold:
                        speech_detected = True
                        silent_frames_after_speech = 0
                    elif speech_detected and index >= min_frames_before_stop:
                        silent_frames_after_speech += 1
                        if silent_frames_after_speech >= silence_frame_limit:
                            logger.info(
                                "Voice: end of speech detected after {:.1f}s",
                                len(frames) * frame_ms / 1000.0,
                            )
                            break
            finally:
                stream.stop_stream()
                stream.close()
                pa.terminate()

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            with wave.open(tmp_file.name, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                wf.setframerate(rate)
                wf.writeframes(b"".join(frames))

            return tmp_file.name
        except Exception as exc:
            logger.error("Voice recording failed: {}", str(exc))
            return None

    def _transcribe_audio(self, audio_path: str) -> Optional[str]:
        """Send a recorded WAV to the local voice server for transcription."""
        try:
            with open(audio_path, "rb") as audio_file:
                files = {"audio": ("command.wav", audio_file, "audio/wav")}
                response = requests.post(
                    f"{self.voice_service_url}/listen",
                    files=files,
                    timeout=60,
                )

            if response.status_code == 200:
                return response.json().get("text", "").strip()
            logger.warning("Voice service returned status %s", response.status_code)
        except Exception as exc:
            logger.error("Voice transcription failed: {}", str(exc))
        return None

    def _speak_text(self, text: str):
        """Send text to the local voice server and play the returned WAV."""
        if not self.voice_enabled:
            return

        try:
            response = requests.post(
                f"{self.voice_service_url}/speak",
                json={"text": text},
                timeout=60,
            )
            if response.status_code != 200:
                logger.warning("Voice server speak failed: %s", response.status_code)
                return

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_file.write(response.content)
            tmp_file.close()

            if sys.platform == "win32":
                winsound.PlaySound(tmp_file.name, winsound.SND_FILENAME)
            else:
                logger.warning("Voice playback only supports Windows via winsound.")

            os.unlink(tmp_file.name)
        except Exception as exc:
            logger.error("Voice playback failed: {}", str(exc))

    def _listen_for_voice_command(self) -> Optional[str]:
        """Record and transcribe a voice command."""
        if not self.voice_enabled:
            return None

        if not self.voice_service_available:
            logger.warning("Voice service is not available at {}", self.voice_service_url)
            print("Voice service is not available. Start local-server/server.py first.")
            return None

        audio_path = self._record_audio()
        if not audio_path:
            print("Voice recording failed.")
            return None

        try:
            command = self._transcribe_audio(audio_path)
            if command:
                print(f"You said: {command}")
                return command
            print("Could not transcribe the voice command.")
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

        return None

    def _speak_result(self, result: Dict[str, Any]):
        """Speak back a simple result summary."""
        if not self.voice_enabled or not self.voice_service_available:
            return

        if result.get("success"):
            message = f"Command completed successfully. {result.get('steps_completed', 0)} of {result.get('steps_total', 0)} steps succeeded."
        else:
            message = f"Command failed. {result.get('error', 'Unknown error')}"
        self._speak_text(message)

    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural-language command through ASC with graceful error handling."""

        logger.info("Processing command: {}", command[:100])
        command = self._resolve_pending_clarification(command)
        self.memory.remember_short_term("last_command", command)
        self.memory.log_session_activity(command)

        strategy = self._determine_execution_strategy(command)
        self.memory.remember_short_term("last_strategy", strategy)
        plan: Dict[str, Any] = {}

        try:
            tier = strategy["tier"]
            complexity = strategy["complexity"]

            if tier == "conversation":
                result = await self.agents["conversation"].chat(
                    command,
                    context={"tools": self.get_tool_manifest()},
                )
                plan = {
                    "tier": tier,
                    "complexity": complexity,
                    "source": strategy.get("source", "conversation"),
                }

            elif tier == "autonomous":
                plan = self.autonomy.plan(
                    command,
                    direct_intent=strategy.get("intent"),
                    context=self._build_autonomy_context(),
                )
                if self._should_use_council_fallback(plan, command) and hasattr(self, "council"):
                    try:
                        council_plan = await self.council.decide(command, complexity)
                        if not council_plan.get("error"):
                            plan = council_plan
                    except Exception as exc:
                        logger.warning("Council fallback for autonomy failed: {}", exc)
                result = await self._execute_autonomous_decision(plan, command)
                result["tier"] = "autonomous"

            elif tier == "direct":
                self.tier_stats["direct"] += 1
                result = await self._execute_directly(command, strategy)
                plan = {
                    "tier": tier,
                    "complexity": complexity,
                    "intent": strategy.get("intent", {}),
                    "source": strategy.get("source", "rules"),
                }
            else:
                decomposition = None
                if (
                    self.decompose_complex_tasks
                    and self.task_decomposer.should_decompose(command, complexity)
                    and not (getattr(self, "autonomy", None) and self.autonomy.should_handle(command, complexity))
                ):
                    decomposition = self.task_decomposer.decompose(command)

                if decomposition and decomposition.get("subtasks"):
                    self.tier_stats["sequential"] += 1
                    plan = decomposition
                    result = await self._execute_decomposed_tasks(decomposition, command)
                    result["tier"] = "sequential"
                else:
                    if tier == "single_model":
                        self.tier_stats["single_model"] += 1
                    else:
                        self.tier_stats["sequential"] += 1

                    plan = await self.council.decide(command, complexity)
                    if "error" in plan:
                        logger.error("Planning failed: {}", plan["error"])
                        result = {
                            "success": False,
                            "tier": tier,
                            "error": "Failed to create execution plan",
                            "details": plan["error"],
                        }
                    else:
                        logger.info(
                            "Plan created by: {}",
                            plan.get("member", plan.get("method", "unknown")),
                        )

                        if complexity == "critical":
                            validation = await self.chairman.validate_plan(plan, command)
                            if not validation.get("approved"):
                                logger.warning("Chairman rejected plan")
                                result = {
                                    "success": False,
                                    "tier": tier,
                                    "rejected": True,
                                    "reason": validation.get("reasoning"),
                                    "validation": validation,
                                }
                            else:
                                result = await self._execute_plan(plan, command)
                                result["tier"] = tier
                        else:
                            result = await self._execute_plan(plan, command)
                            result["tier"] = tier

            self._cache_command_strategy(command, strategy, result)
            self._record_learning(command, strategy, result)
            self._learn_from_execution(command, plan or strategy, result)
            return result

        except Exception as exc:
            logger.error("Command processing failed: {}", str(exc))
            # Graceful error recovery - provide helpful fallback
            result = {
                "success": False,
                "tier": strategy.get("tier", "unknown"),
                "error": str(exc),
                "recovery_suggestion": self._generate_recovery_suggestion(command, exc),
            }
            self._record_learning(command, strategy, result)
            return result

    def _generate_recovery_suggestion(self, command: str, error: Exception) -> str:
        """Generate helpful recovery suggestions when commands fail."""
        normalized = self._normalize_command(command)
        
        # Analyze the error and command to provide specific suggestions
        error_msg = str(error).lower()
        
        if "connection" in error_msg or "network" in error_msg:
            if "web" in normalized or "search" in normalized or "open" in normalized:
                return "It seems there's a network issue. Would you like me to try again, or would you prefer to work on local tasks instead?"
            return "I'm having connectivity issues. Let me help you with local system or file tasks instead."
        
        if "file" in error_msg or "permission" in error_msg:
            return "I encountered a file system issue. Would you like me to try a different location or check the file permissions?"
        
        if "timeout" in error_msg:
            return "The operation timed out. Would you like me to try again with a simpler approach?"
        
        # Generic helpful suggestion
        return f"I encountered an issue with that request. Could you rephrase it, or would you like me to help with something else? I'm designed to be helpful with tasks like opening apps, managing files, checking system status, or web searches."

    def _record_learning(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        """Record command learning without letting storage failures break execution."""

        try:
            self.agents["learning"].record_command(command, strategy, result)
        except Exception as exc:
            logger.warning("Learning history write failed without blocking command: {}", str(exc))

    def _resolve_pending_clarification(self, command: str) -> str:
        """Use a short follow-up answer to complete a prior clarification."""

        pending = self.memory.recall_short_term("pending_clarification") if hasattr(self.memory, "recall_short_term") else None
        if not pending:
            return command

        normalized = self._normalize_command(command)
        if not normalized or normalized in {"open", "search", "create", "run", "fill"}:
            return command

        original = pending.get("original_command", "")
        strategy = pending.get("strategy")
        if strategy == "missing_target" and original:
            self.memory.remember_short_term("pending_clarification", None)
            return f"{original} {command}".strip()

        return command

    def _build_autonomy_context(self) -> Dict[str, Any]:
        """Gather memory/learning context for offline autonomous planning."""

        workflows = []
        try:
            learning_agent = self.agents["learning"]
            if hasattr(learning_agent, "refresh_adaptive_state"):
                learning_agent.refresh_adaptive_state(preferences=getattr(self.memory, "preferences", {}))
            workflows = learning_agent.discover_workflow_patterns(min_count=1)
        except Exception as exc:
            logger.warning("Workflow discovery unavailable for autonomy context: {}", str(exc))

        return {
            "preferences": getattr(self.memory, "preferences", {}),
            "recent_context": self.memory.get_recent_context(limit=5) if hasattr(self.memory, "get_recent_context") else [],
            "workflow_patterns": workflows,
            "tools": self.get_tool_manifest(),
        }

    def _determine_execution_strategy(self, command: str) -> Dict[str, Any]:
        """Determine which execution tier should handle the command."""

        normalized = self._normalize_command(command)
        cached = self.command_cache.get(normalized)
        if cached and cached.get("success"):
            return {
                "tier": cached["tier"],
                "complexity": cached["complexity"],
                "intent": cached.get("intent"),
                "source": "cache",
            }

        complexity = self._assess_complexity(command)
        direct_intent = self._parse_direct_command(command)
        autonomy = getattr(self, "autonomy", None)
        if direct_intent and direct_intent.get("type") in {"browser_action", "fill_form", "confirm_submission"}:
            return {
                "tier": "direct",
                "complexity": "simple",
                "intent": direct_intent,
                "source": "rules",
            }

        if self.decompose_complex_tasks and self._contains_explicit_sequence(normalized):
            return {"tier": "sequential", "complexity": "complex", "source": "decomposer"}

        conversation_agent = self.agents.get("conversation")
        if conversation_agent and conversation_agent.is_conversation(command):
            return {"tier": "conversation", "complexity": "simple", "source": "conversation"}

        similar = self.agents["learning"].find_similar_success(command)
        if similar and similar["score"] >= 0.99:
            learned_strategy = similar["match"].get("strategy", {})
            if learned_strategy.get("tier") == "direct" and self._can_reuse_learned_strategy(learned_strategy):
                return {
                    "tier": learned_strategy["tier"],
                    "complexity": learned_strategy.get("complexity", "simple"),
                    "intent": learned_strategy.get("intent"),
                    "source": "learning",
                }

        classification = None
        if hasattr(self.agents["learning"], "classify_command"):
            try:
                classification = self.agents["learning"].classify_command(command)
            except Exception as exc:
                logger.warning("Adaptive classification unavailable: {}", str(exc))

        if classification and classification.get("source") == "adaptive_cluster" and classification.get("confidence", 0.0) >= 0.75:
            learned_strategy = classification.get("cluster", {}).get("strategy", {})
            if learned_strategy.get("tier") == "direct" and self._can_reuse_learned_strategy(learned_strategy):
                return {
                    "tier": learned_strategy["tier"],
                    "complexity": learned_strategy.get("complexity", "simple"),
                    "intent": learned_strategy.get("intent"),
                    "source": "adaptive_classification",
                    "adaptive": classification,
                }

        adaptive = self._get_adaptive_recommendation(command)
        if adaptive:
            learned_strategy = adaptive.get("strategy", {})
            if learned_strategy.get("tier") == "direct" and self._can_reuse_learned_strategy(learned_strategy):
                return {
                    "tier": learned_strategy["tier"],
                    "complexity": learned_strategy.get("complexity", "simple"),
                    "intent": learned_strategy.get("intent"),
                    "source": "adaptive_learning",
                    "adaptive": adaptive,
                }

        if direct_intent:
            if (
                direct_intent.get("type") == "open_application"
                and direct_intent.get("app") == "browser"
                and autonomy
            ):
                return {"tier": "autonomous", "complexity": complexity, "source": "autonomy"}
            return {
                "tier": "direct",
                "complexity": "simple",
                "intent": direct_intent,
                "source": "rules",
            }

        if autonomy and autonomy.should_handle(command, complexity):
            return {"tier": "autonomous", "complexity": complexity, "source": "autonomy"}

        if complexity in {"simple", "medium"}:
            return {"tier": "single_model", "complexity": complexity, "source": "council"}

        return {"tier": "sequential", "complexity": complexity, "source": "council"}

    def _can_reuse_learned_strategy(self, learned_strategy: Dict[str, Any]) -> bool:
        """Only reuse direct learned strategies that do not carry stale user parameters."""

        intent_type = (learned_strategy.get("intent") or {}).get("type")
        reusable_intents = {
            "system_info",
            "command_history",
            "voice_status",
        }
        return intent_type in reusable_intents

    def _get_adaptive_recommendation(self, command: str) -> Optional[Dict[str, Any]]:
        """Get a Phase 4 advisory routing recommendation without blocking execution."""

        learning_agent = self.agents.get("learning")
        if not learning_agent or not hasattr(learning_agent, "recommend_strategy"):
            return None
        try:
            return learning_agent.recommend_strategy(command)
        except Exception as exc:
            logger.warning("Adaptive recommendation unavailable: {}", str(exc))
            return None

    def _should_use_council_fallback(self, plan: Dict[str, Any], command: str) -> bool:
        """Prefer the council planner when the autonomy engine only produced a weak decomposition."""

        if plan.get("mode") != "execute":
            return True

        decomposition = plan.get("decomposition") or {}
        subtasks = decomposition.get("subtasks") or []
        if not subtasks:
            return False

        if len(subtasks) > 1:
            return False

        step = subtasks[0]
        action = (step.get("action") or "").lower()
        params = step.get("params") or {}
        if action in {"general", "form"} and not (
            params.get("fields") or params.get("url") or params.get("target") or params.get("query")
        ):
            return True

        if action in {"navigate", "search"} and not (params.get("url") or params.get("target") or params.get("query")):
            return True

        return False

    def _contains_explicit_sequence(self, normalized_command: str) -> bool:
        """Return whether the command clearly contains multiple sequential actions."""

        if any(token in normalized_command for token in [" and then ", " then ", " after that "]):
            return True

        action_markers = [
            " create file ",
            " create folder ",
            " list running processes",
            " show system status",
            " show system info",
            " organize desktop",
            " organize documents",
        ]
        if " and " in normalized_command and sum(marker in normalized_command for marker in action_markers) >= 2:
            return True

        if normalized_command.count(" search ") >= 2 or normalized_command.count(" search for ") >= 2:
            return True

        return False

    def _assess_complexity(self, command: str) -> str:
        """Assess command complexity using lightweight heuristics."""

        command_lower = command.lower()

        critical_keywords = [
            "delete",
            "remove",
            "uninstall",
            "format",
            "shutdown",
            "restart",
            "registry",
        ]
        if any(keyword in command_lower for keyword in critical_keywords):
            return "critical"

        complex_keywords = [
            "organize",
            "analyze",
            "automate",
            "schedule",
            "multiple",
            "research",
            "report",
            "workflow",
            "fill form",
            "form",
        ]
        if any(keyword in command_lower for keyword in complex_keywords):
            return "complex"

        medium_keywords = [
            "plan",
            "explain",
            "compare",
            "decide",
            "summarize",
            "search",
            "navigate",
        ]
        if any(keyword in command_lower for keyword in medium_keywords):
            return "medium"

        simple_keywords = [
            "open",
            "launch",
            "show",
            "list",
            "tell",
            "get",
            "status",
        ]
        if any(keyword in command_lower for keyword in simple_keywords):
            return "simple"

        return "medium"

    def _parse_direct_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Parse deterministic commands that should bypass the council."""

        normalized = self._normalize_command(command)
        normalized = re.sub(r"^(?:please|can you|could you|would you)\s+", "", normalized)

        positive_feedback = re.match(r"^(?:that worked|this worked|good job|correct|yes that is right|that was right)(?:\s*[:,-]?\s*(?P<text>.*))?$", normalized)
        if positive_feedback:
            return {
                "type": "record_feedback",
                "sentiment": "positive",
                "feedback": positive_feedback.group("text") or command,
            }

        negative_feedback = re.match(r"^(?:that failed|this failed|wrong|incorrect|not correct|that was wrong)(?:\s*[:,-]?\s*(?P<text>.*))?$", normalized)
        if negative_feedback:
            return {
                "type": "record_feedback",
                "sentiment": "negative",
                "feedback": negative_feedback.group("text") or command,
            }

        preference = re.match(r"^(?:remember that|remember|remeber|set preference)\s+(?P<key>[a-zA-Z0-9 _-]{2,40})\s+(?:is|as|=)\s+(?P<value>.+)$", command, flags=re.IGNORECASE)
        if preference:
            return {
                "type": "save_preference",
                "key": preference.group("key").strip().lower().replace(" ", "_"),
                "value": preference.group("value").strip(),
            }

        approve_preference = re.match(
            r"^(?:approve|accept|confirm)\s+(?:preference|suggestion)\s+(?P<rest>.+)$",
            command,
            flags=re.IGNORECASE,
        )
        if approve_preference:
            rest = approve_preference.group("rest").strip()
            explicit = re.match(r"^(?P<key>[a-zA-Z0-9 _-]{2,40})\s+(?:is|should be|as|=)\s+(?P<value>.+)$", rest, flags=re.IGNORECASE)
            if explicit:
                key = explicit.group("key")
                value = explicit.group("value")
            else:
                parts = rest.split(None, 1)
                key = parts[0]
                value = parts[1].strip() if len(parts) > 1 else None
            return {
                "type": "approve_preference",
                "key": key.strip().lower().replace(" ", "_"),
                "value": value.strip() if value is not None else None,
            }

        reject_preference = re.match(
            r"^(?:reject|ignore|decline)\s+(?:preference|suggestion)\s+(?P<rest>.+)$",
            command,
            flags=re.IGNORECASE,
        )
        if reject_preference:
            rest = reject_preference.group("rest").strip()
            explicit = re.match(r"^(?P<key>[a-zA-Z0-9 _-]{2,40})\s+(?:is|should be|as|=)\s+(?P<value>.+)$", rest, flags=re.IGNORECASE)
            if explicit:
                key = explicit.group("key")
                value = explicit.group("value")
            else:
                parts = rest.split(None, 1)
                key = parts[0]
                value = parts[1].strip() if len(parts) > 1 else None
            return {
                "type": "reject_preference",
                "key": key.strip().lower().replace(" ", "_"),
                "value": value.strip() if value is not None else None,
            }

        if any(phrase in normalized for phrase in ["show preferences", "list preferences", "what are my preferences"]):
            return {"type": "show_preferences"}

        if any(phrase in normalized for phrase in ["show learned workflows", "show workflow patterns", "what workflows have you learned"]):
            return {"type": "show_workflow_patterns"}

        if any(phrase in normalized for phrase in ["show workflow templates", "workflow templates", "show workflow template"]):
            return {"type": "show_workflow_templates"}

        if any(phrase in normalized for phrase in ["show adaptive evaluation", "phase 4 evaluation", "adaptive evaluation", "evaluation metrics"]):
            return {"type": "show_adaptive_evaluation"}

        if any(phrase in normalized for phrase in ["classify command", "what would you do for", "how would you handle"]):
            return {"type": "classify_command", "command": command}

        if any(phrase in normalized for phrase in ["show adaptive learning", "show learning summary", "phase 4 status", "adaptive learning status"]):
            return {"type": "show_adaptive_learning"}

        if any(phrase in normalized for phrase in ["phase 5 status", "show phase 5 status", "show phase5 status"]):
            return {"type": "show_phase5_learning"}

        if any(phrase in normalized for phrase in ["show phase 5 model", "phase 5 model", "show phase5 model"]):
            return {"type": "show_phase5_model"}

        if normalized in {
            "confirm command",
            "confirm system command",
            "run it anyway",
            "execute it anyway",
            "yes run it",
            "yes execute it",
        }:
            return {"type": "confirm_system_command"}

        if normalized in {"cancel command", "cancel system command", "do not run it", "don't run it"}:
            return {"type": "cancel_system_command"}

        power_action = self._parse_power_action(normalized)
        if power_action:
            return {
                "type": "system_power_action",
                **power_action,
            }

        # Cybersecurity Commands (Priority 2, Task 5) - specific matches checked first
        sec_scan = re.match(
            r"^(?:run\s+)?(?:security\s+scan|port\s+scan)(?:\s+(?:on|for))?\s+(?P<host>[a-zA-Z0-9\.-]+)(?:\s+(?:ports|range)\s+(?P<ports>\d+-\d+|common))?$",
            normalized
        )
        if sec_scan:
            return {
                "type": "security_port_scan",
                "host": sec_scan.group("host").strip(),
                "ports": sec_scan.group("ports") or "common"
            }

        ssl_check = re.match(
            r"^(?:run\s+)?(?:ssl\s+check|check\s+ssl)(?:\s+(?:on|for))?\s+(?P<domain>[a-zA-Z0-9\.-]+)$",
            normalized
        )
        if ssl_check:
            return {
                "type": "security_ssl_check",
                "domain": ssl_check.group("domain").strip()
            }

        sec_headers = re.match(
            r"^(?:run\s+)?(?:security\s+headers|check\s+security\s+headers)(?:\s+(?:on|for))?\s+(?P<url>https?://[^\s]+)$",
            normalized
        )
        if sec_headers:
            return {
                "type": "security_headers_check",
                "url": sec_headers.group("url").strip()
            }

        dns_lookup = re.match(
            r"^(?:run\s+)?dns\s+lookup(?:\s+(?:on|for))?\s+(?P<domain>[a-zA-Z0-9\.-]+)$",
            normalized
        )
        if dns_lookup:
            return {
                "type": "dns_lookup",
                "domain": dns_lookup.group("domain").strip()
            }

        # File Agent Advanced Commands (Priority 2, Task 5b) - checked before general list/find/search rules
        undo_org = re.match(
            r"^(?:undo|restore)\s+(?:folder\s+)?organization(?:\s+(?:with\s+)?manifest\s+(?P<manifest>manifest_\w+))?$",
            normalized
        )
        if undo_org:
            return {
                "type": "restore_organization",
                "manifest_id": undo_org.group("manifest")
            }

        disk_usage = re.match(
            r"^(?:analyze|show)\s+(?:disk|space)\s+usage(?:\s+(?:in|for))?\s+(?P<path>.+)$",
            normalized
        )
        if disk_usage:
            return {
                "type": "analyze_disk_usage",
                "path": self._extract_known_path(disk_usage.group("path").strip())
            }

        duplicates = re.match(
            r"^(?:find|search\s+for)\s+duplicates?(?:\s+(?:in|for))?\s+(?P<path>.+)$",
            normalized
        )
        if duplicates:
            return {
                "type": "find_duplicates",
                "path": self._extract_known_path(duplicates.group("path").strip())
            }

        batch_rename = re.match(
            r"^batch\s+rename\s+(?:files\s+in\s+)?(?P<path>[\w\-\.\/\\\:]+?)\s+replace\s+(?P<find>.+?)\s+with\s+(?P<replace>.+?)(?:\s+matching\s+(?P<ext>\.\w+))?$",
            normalized
        )
        if batch_rename:
            return {
                "type": "batch_rename_files",
                "path": self._extract_known_path(batch_rename.group("path").strip()),
                "find": batch_rename.group("find").strip(),
                "replace": batch_rename.group("replace").strip(),
                "extension": batch_rename.group("ext")
            }

        file_info = re.match(
            r"^(?:show|get|check)\s+(?:file\s+)?info(?:rmation)?(?:\s+(?:for|about|on))?\s+(?P<path>.+)$",
            command,
            flags=re.IGNORECASE,
        )
        if file_info:
            return {
                "type": "file_info",
                "path": self._resolve_user_path(file_info.group("path").strip()),
            }

        file_search = re.match(
            r"^(?:search|find)\s+(?:files?\s+)?(?:for\s+)?(?P<query>.+?)\s+(?:in|inside)\s+(?P<path>.+)$",
            command,
            flags=re.IGNORECASE,
        )
        if file_search and not re.search(r"\b(?:on|in)\s+(?:amazon|flipkart|google|youtube)\b", normalized):
            return {
                "type": "search_files",
                "query": file_search.group("query").strip().strip('"'),
                "path": self._extract_known_path(file_search.group("path").strip()),
                "search_content": "content" in normalized or "inside" in normalized,
            }

        backup_folder = re.match(
            r"^(?:backup|back up)\s+(?P<path>.+?)(?:\s+(?:as|named)\s+(?P<name>.+))?$",
            command,
            flags=re.IGNORECASE,
        )
        if backup_folder:
            return {
                "type": "backup_folder",
                "path": self._extract_known_path(backup_folder.group("path").strip()),
                "backup_name": (backup_folder.group("name") or "").strip() or None,
            }

        copy_command = re.match(
            r"^(?:can you\s+)?(?:copy|duplicate)\s+(?:the\s+)?(?P<source>[\w\-. ]+?)\s+(?:and\s+paste(?: it)?\s+)?(?:into|onto|to|on|in)\s+(?P<destination>.+)$",
            normalized,
        )
        if copy_command:
            source = copy_command.group("source").strip()
            destination = copy_command.group("destination").strip()
            return {
                "type": "copy_file",
                "source": source,
                "destination": self._extract_known_path(destination),
            }

        move_command = re.match(
            r"^(?:can you\s+)?(?:move|relocate)\s+(?:the\s+)?(?P<source>[\w\-. ]+?)\s+(?:into|onto|to|on|in)\s+(?P<destination>.+)$",
            normalized,
        )
        if move_command:
            source = move_command.group("source").strip()
            destination = move_command.group("destination").strip()
            return {
                "type": "move_file",
                "source": source,
                "destination": self._extract_known_path(destination),
            }

        search_site = re.match(
            r"^(?:open|launch|start)\s+(?P<site>google|youtube|bing)(?:\s+and\s+(?:search|look up|find)(?:\s+for)?\s+(?P<query>.+))?$",
            normalized,
        )
        if search_site:
            site = search_site.group("site")
            query = search_site.group("query")
            if site == "youtube":
                target = (
                    f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                    if query
                    else "https://www.youtube.com"
                )
            elif site == "google":
                target = (
                    self.config.get("web_automation", {}).get("search_engine_url", "https://www.google.com/search?q={query}").format(query=quote_plus(query))
                    if query
                    else "https://www.google.com"
                )
            else:
                target = (
                    f"https://www.bing.com/search?q={quote_plus(query)}"
                    if query
                    else "https://www.bing.com"
                )
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": target,
            }

        open_goto_search = re.match(
            r"^(?:open|launch|start)\s+(?P<app>[a-z0-9 ._-]+?)\s+(?:and|then)\s+"
            r"(?P<verb>goto|navigate to)\s+(?P<site>[^\s]+)"
            r"(?:\s+and\s+(?:search|find|look up)(?:\s+for)?\s+(?P<query>.+))?$",
            normalized,
        )
        if open_goto_search:
            app_name = open_goto_search.group("app").strip()
            site = open_goto_search.group("site").strip()
            query = open_goto_search.group("query")
            target_url = self._normalize_url(site)
            if query:
                target_url = self._build_search_target_for_site(target_url, query)
            return {
                "type": "browser_action",
                "app": app_name if app_name in self.BROWSER_APPS else self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": target_url,
            }

        ecommerce_search = re.match(
            r"^(?:open|launch|start)\s+(?P<app>[a-z0-9 ._-]+?)\s+"
            r"(?:(?:and\s+)?(?:search|find|look up)(?:\s+for)?\s+)?(?P<site>amazon|flipkart)"
            r"(?:\s+(?:and|then)\s+(?:search|find|look up)(?:\s+for)?\s+(?P<query>.+?)(?:\s+(?:on|in)\s+(?P=site))?(?:\s+there)?)?$",
            normalized,
        )
        if ecommerce_search:
            app_name = ecommerce_search.group("app").strip()
            site = ecommerce_search.group("site").strip()
            query = ecommerce_search.group("query")
            site_url = "https://www.amazon.in" if site == "amazon" else "https://www.flipkart.com"
            target_url = self._build_search_target_for_site(site_url, query) if query else site_url
            return {
                "type": "browser_action",
                "app": app_name if app_name in self.BROWSER_APPS else self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": target_url,
            }

        url_target = self._extract_url_from_command(command)
        form_fields = self._extract_form_fields(command)
        confirmation_token_match = re.search(
            r"\b(?:confirm|approve|submit|execute|finalize)(?:\s+(?:the\s+)?)?(?:staged\s+)?(?:form|submission|request)?(?:\s+token)?\s*(?P<token>[a-f0-9\-]{8,})\b",
            normalized,
        )
        if confirmation_token_match:
            return {
                "type": "confirm_submission",
                "token": confirmation_token_match.group("token"),
            }

        require_confirmation = bool(re.search(
            r"\b(?:stage|staged|confirm before|do not submit|don't submit|wait for confirmation|only after i confirm|hold submission|hold off on submit)\b",
            normalized,
        ))

        if url_target and form_fields:
            return {
                "type": "fill_form",
                "url": url_target,
                "fields": form_fields,
                "submit": "submit" in normalized or "send" in normalized or "stage" in normalized,
                "require_confirmation": require_confirmation,
            }

        if url_target:
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": url_target,
            }

        browser_action = re.match(
            r"^(?:open|launch|start)\s+(?P<app>[a-z0-9 ._-]+?)\s+(?:and|then)\s+"
            r"(?P<verb>search(?:\s+for)?|look up|google|find|go to|navigate to|open)\s+"
            r"(?P<target>.+)$",
            normalized,
        )
        if browser_action:
            app_name = browser_action.group("app").strip()
            if app_name in self.BROWSER_APPS:
                verb = browser_action.group("verb")
                target = browser_action.group("target").strip()
                if self._contains_explicit_sequence(f" {target} ") or re.search(
                    r"\b(?:and|then)\s+(?:search|find|look up|go to|navigate|open)\b",
                    target,
                ):
                    return None
                action = "search" if verb.startswith(("search", "look up", "google", "find")) else "navigate"
                return {
                    "type": "browser_action",
                    "app": app_name,
                    "action": action,
                    "target": target,
                }

        ecommerce_only = re.match(
            r"^(?:search(?:\s+for)?|google|look up|find)\s+(?P<query>.+?)\s+(?:on|in)\s+(?P<site>amazon|flipkart)(?:\s+there)?$",
            normalized,
        )
        if ecommerce_only:
            site = ecommerce_only.group("site")
            site_url = "https://www.amazon.in" if site == "amazon" else "https://www.flipkart.com"
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": self._build_search_target_for_site(site_url, ecommerce_only.group("query").strip()),
            }

        web_only = re.match(
            r"^(?:search(?:\s+for)?|google|look up|find)\s+(?P<target>.+)$",
            normalized,
        )
        if web_only:
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "search",
                "target": web_only.group("target").strip(),
            }

        navigate_only = re.match(
            r"^(?:go to|navigate to|open url)\s+(?P<target>.+)$",
            normalized,
        )
        if navigate_only:
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": navigate_only.group("target").strip(),
            }

        form_fields = self._extract_form_fields(command)
        if form_fields:
            url_match = self._extract_url_from_command(command)
            return {
                "type": "fill_form",
                "fields": form_fields,
                "submit": "submit" in normalized or "send" in normalized,
                "require_confirmation": require_confirmation,
                "url": url_match,
            }

        if any(phrase in normalized for phrase in ["show command history", "show recent commands", "recent commands"]):
            return {"type": "command_history"}

        if any(phrase in normalized for phrase in ["voice status", "voice health", "check voice"]):
            return {"type": "voice_status"}

        if any(phrase in normalized for phrase in ["start voice server", "start voice", "enable voice"]):
            return {"type": "start_voice_server"}

        if any(phrase in normalized for phrase in ["stop voice server", "stop voice", "disable voice"]):
            return {"type": "stop_voice_server"}

        # Phase 6: Business Agent commands
        if any(phrase in normalized for phrase in ["create task", "add task", "new task"]):
            return {"type": "create_task"}

        if any(phrase in normalized for phrase in ["list tasks", "show tasks", "my tasks"]):
            return {"type": "list_tasks"}

        if any(phrase in normalized for phrase in ["complete task", "finish task", "done task"]):
            return {"type": "complete_task"}

        if any(phrase in normalized for phrase in ["create project", "new project", "start project"]):
            return {"type": "create_project"}

        if any(phrase in normalized for phrase in ["daily plan", "today's plan", "schedule today"]):
            return {"type": "daily_plan"}

        if any(phrase in normalized for phrase in ["schedule reminder", "set reminder", "remind me"]):
            return {"type": "schedule_reminder"}

        if any(phrase in normalized for phrase in ["meeting agenda", "agenda for"]):
            return {"type": "meeting_agenda"}

        if any(phrase in normalized for phrase in ["add calendar event", "schedule event", "calendar event"]):
            return {"type": "add_calendar_event"}

        if any(phrase in normalized for phrase in ["upcoming events", "calendar events", "my schedule"]):
            return {"type": "upcoming_events"}

        if any(phrase in normalized for phrase in ["project status", "project progress", "how is project"]):
            return {"type": "project_status"}

        if any(phrase in normalized for phrase in ["list projects", "my projects", "show projects"]):
            return {"type": "list_projects"}

        if any(phrase in normalized for phrase in ["create milestone", "add milestone", "project milestone"]):
            return {"type": "create_milestone"}

        if any(phrase in normalized for phrase in ["project timeline", "project schedule", "timeline"]):
            return {"type": "project_timeline"}

        if any(phrase in normalized for phrase in ["send email", "email notification", "notify"]):
            return {"type": "send_email"}

        if any(phrase in normalized for phrase in ["email template", "generate email", "draft email"]):
            return {"type": "email_template"}

        if any(phrase in normalized for phrase in ["check email", "email status", "email config"]):
            return {"type": "email_status"}

        if any(phrase in normalized for phrase in ["call api", "external service", "api call"]):
            return {"type": "call_external_api"}

        if any(phrase in normalized for phrase in ["available services", "external services", "api services"]):
            return {"type": "available_services"}

        if any(phrase in normalized for phrase in ["configure service", "setup service", "service config"]):
            return {"type": "configure_service"}

        if any(phrase in normalized for phrase in ["coordinate agents", "multi-agent", "agent coordination"]):
            return {"type": "coordinate_agents"}

        if any(phrase in normalized for phrase in ["agent status", "agent health", "check agents"]):
            return {"type": "agent_status"}

        if any(phrase in normalized for phrase in ["optimize workflow", "workflow optimization", "efficient workflow"]):
            return {"type": "optimize_workflow"}

        # Phase 6 Advanced Features
        if any(phrase in normalized for phrase in ["configure email", "setup email", "email config"]):
            return {"type": "configure_email"}

        if any(phrase in normalized for phrase in ["google calendar", "apple calendar", "multi calendar"]):
            return {"type": "calendar_integration"}

        if any(phrase in normalized for phrase in ["gantt chart", "project timeline", "project visualization"]):
            return {"type": "gantt_chart"}

        if any(phrase in normalized for phrase in ["allocate resources", "resource allocation", "assign resources"]):
            return {"type": "allocate_resources"}

        if any(phrase in normalized for phrase in ["resource utilization", "resource analysis", "resource usage"]):
            return {"type": "resource_utilization"}

        if any(phrase in normalized for phrase in ["track time", "time tracking", "log time"]):
            return {"type": "track_time"}

        if any(phrase in normalized for phrase in ["productivity metrics", "productivity report", "productivity analysis"]):
            return {"type": "productivity_report"}

        if any(phrase in normalized for phrase in ["weather", "weather forecast", "weather api"]):
            return {"type": "weather_api"}

        if any(phrase in normalized for phrase in ["news", "news api", "latest news"]):
            return {"type": "news_api"}

        if any(phrase in normalized for phrase in ["stock", "stock price", "stock market"]):
            return {"type": "stock_api"}

        if any(phrase in normalized for phrase in ["business dashboard", "bi dashboard", "analytics dashboard"]):
            return {"type": "business_dashboard"}

        if any(phrase in normalized for phrase in ["add team member", "team member", "add to team"]):
            return {"type": "add_team_member"}

        if any(phrase in normalized for phrase in ["list team", "team members", "show team"]):
            return {"type": "list_team"}

        if any(phrase in normalized for phrase in ["assign to project", "team assignment", "assign team"]):
            return {"type": "assign_team_project"}

        if any(phrase in normalized for phrase in ["task comment", "add comment", "comment on task"]):
            return {"type": "task_comment"}

        if any(phrase in normalized for phrase in ["team notification", "notify team", "team alert"]):
            return {"type": "team_notification"}

        if any(phrase in normalized for phrase in ["shared workspace", "team workspace", "collaboration space"]):
            return {"type": "shared_workspace"}

        # Advanced Enterprise Features
        if any(phrase in normalized for phrase in ["ensemble model", "create ensemble", "machine learning model"]):
            return {"type": "create_ensemble_model"}

        if any(phrase in normalized for phrase in ["train predictive model", "predictive analytics", "train model"]):
            return {"type": "train_predictive_model"}

        if any(phrase in normalized for phrase in ["detect anomalies", "anomaly detection", "find anomalies"]):
            return {"type": "detect_anomalies"}

        if any(phrase in normalized for phrase in ["time series forecast", "forecast prediction", "predict future"]):
            return {"type": "time_series_forecast"}

        if any(phrase in normalized for phrase in ["deep learning model", "neural network", "create neural network"]):
            return {"type": "create_deep_learning_model"}

        if any(phrase in normalized for phrase in ["erp integration", "integrate erp", "connect erp"]):
            return {"type": "erp_integration"}

        if any(phrase in normalized for phrase in ["crm integration", "integrate crm", "connect crm"]):
            return {"type": "crm_integration"}

        if any(phrase in normalized for phrase in ["create workflow", "business workflow", "automate workflow"]):
            return {"type": "create_workflow"}

        if any(phrase in normalized for phrase in ["mine process", "process mining", "analyze process"]):
            return {"type": "process_mining"}

        if any(phrase in normalized for phrase in ["business rule", "create rule", "automation rule"]):
            return {"type": "business_rule"}

        if any(phrase in normalized for phrase in ["create tenant", "multi-tenant", "add tenant"]):
            return {"type": "create_tenant"}

        if any(phrase in normalized for phrase in ["create role", "user role", "access role"]):
            return {"type": "create_role"}

        if any(phrase in normalized for phrase in ["check permission", "user permission", "access check"]):
            return {"type": "check_permission"}

        if any(phrase in normalized for phrase in ["audit trail", "audit log", "security audit"]):
            return {"type": "audit_trail"}

        if any(phrase in normalized for phrase in ["gdpr compliance", "compliance check", "regulatory compliance"]):
            return {"type": "gdpr_compliance"}

        if any(phrase in normalized for phrase in ["bi dashboard", "analytics dashboard", "business dashboard"]):
            return {"type": "bi_dashboard"}

        if any(phrase in normalized for phrase in ["create report", "analytics report", "generate report"]):
            return {"type": "create_report"}

        if any(phrase in normalized for phrase in ["real-time monitor", "monitor system", "live monitoring"]):
            return {"type": "real_time_monitor"}

        if "open youtube" in normalized and "search" not in normalized:
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": "https://www.youtube.com",
            }

        if "open google" in normalized and "search" not in normalized:
            return {
                "type": "browser_action",
                "app": self.config.get("web_automation", {}).get("default_browser", "chrome"),
                "action": "navigate",
                "target": "https://www.google.com",
            }

        powershell_command = re.match(r"^run powershell\s+(?P<cmd>.+)$", command, flags=re.IGNORECASE)
        if powershell_command:
            return {
                "type": "system_command",
                "shell": "powershell",
                "command": powershell_command.group("cmd").strip(),
            }

        cmd_command = re.match(r"^run cmd\s+(?P<cmd>.+)$", command, flags=re.IGNORECASE)
        if cmd_command:
            return {
                "type": "system_command",
                "shell": "cmd",
                "command": cmd_command.group("cmd").strip(),
            }

        close_app = re.match(r"^(?:close|quit|exit)\s+(?P<app>[a-z0-9 ._-]+)$", normalized)
        if close_app and close_app.group("app") not in {"this", "it", "that"}:
            return {"type": "close_application", "app": close_app.group("app").strip()}

        app_open = re.match(r"^(?:open|launch|start)\s+(?P<app>[a-z0-9 ._-]+)$", normalized)
        if app_open:
            return {"type": "open_application", "app": app_open.group("app").strip()}

        if any(phrase in normalized for phrase in ["system info", "system status", "show cpu", "show ram"]):
            return {"type": "system_info"}

        if any(phrase in normalized for phrase in ["network status", "network info", "show network"]):
            return {"type": "network_info"}

        if any(phrase in normalized for phrase in ["disk drives", "show drives", "list drives"]):
            return {"type": "disk_drives"}

        env_var = re.match(
            r"^(?:show|get|check)\s+(?:environment\s+variable|env\s+var|env)\s+(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)$",
            command,
            flags=re.IGNORECASE,
        )
        if env_var:
            return {"type": "environment_variable", "name": env_var.group("name").strip()}

        if ("list" in normalized or "show" in normalized) and any(
            word in normalized for word in ["process", "running task", "running app"]
        ):
            return {
                "type": "list_processes",
                "filter": self._extract_process_filter(normalized),
            }

        if ("list" in normalized or "show" in normalized) and any(
            word in normalized for word in ["file", "folder", "download", "desktop", "document"]
        ):
            return {
                "type": "list_files",
                "path": self._extract_known_path(normalized),
            }

        if "organize" in normalized and any(
            word in normalized for word in ["desktop", "download", "document", "folder"]
        ):
            return {
                "type": "organize_folder",
                "path": self._extract_known_path(normalized),
            }
        create_folder = re.match(
            r"^(?:create|make)\s+(?:a\s+)?folder(?:\s+named)?\s+(?P<name>.+)$",
            normalized,
        )
        if create_folder:
            return {
                "type": "create_folder",
                "path": str(Path.cwd() / create_folder.group("name").strip().strip('"')),
            }

        create_file = re.match(
            r"^(?:create|make)\s+(?:a\s+)?file(?:\s+named)?\s+(?P<name>.+)$",
            normalized,
        )
        if create_file:
            return {
                "type": "create_file",
                "path": str(Path.cwd() / create_file.group("name").strip().strip('"')),
            }

        return None

    def _extract_url_from_command(self, command: str) -> Optional[str]:
        """Extract a bare URL or domain from a command string."""
        # Avoid matching email addresses as URLs
        match = re.search(
            r'(https?://[^\s]+|www\.[^\s]+|(?<!\S)(?![^@\n]+@)([A-Za-z0-9\.-]+\.(?:com|in|org|net|io|gov|edu))(?:/[^\s]*)?)',
            command,
        )
        if not match:
            return None

        url = match.group(1).rstrip('.,;"')
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    def _parse_power_action(self, normalized: str) -> Optional[Dict[str, str]]:
        """Parse disruptive system power actions into confirmation-gated commands."""
        power_commands = {
            "shutdown": {
                "phrases": ["shutdown system", "shut down system", "shutdown laptop", "shut down laptop", "turn off system", "turn off laptop"],
                "command": "shutdown /s /t 0",
                "description": "shut down the system",
            },
            "restart": {
                "phrases": ["restart system", "restart laptop", "reboot system", "reboot laptop"],
                "command": "shutdown /r /t 0",
                "description": "restart the system",
            },
            "sleep": {
                "phrases": ["sleep system", "sleep laptop", "put system to sleep", "put laptop to sleep", "go to sleep"],
                "command": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                "description": "put the system to sleep",
            },
            "lock": {
                "phrases": ["lock system", "lock laptop", "lock screen", "lock workstation"],
                "command": "rundll32.exe user32.dll,LockWorkStation",
                "description": "lock the workstation",
            },
        }
        for action, data in power_commands.items():
            if normalized in data["phrases"]:
                return {
                    "power_action": action,
                    "command": data["command"],
                    "description": data["description"],
                    "shell": "cmd",
                }
        if normalized in {"turn on system", "turn on laptop", "power on system", "power on laptop"}:
            return {
                "power_action": "power_on",
                "command": "",
                "description": "power on the system",
                "shell": "cmd",
                "unsupported_reason": "A fully powered-off computer cannot be turned on by local software without Wake-on-LAN, firmware scheduling, or external hardware support.",
            }
        if normalized in {"unlock laptop", "unlock system", "unlock screen"}:
            return {
                "power_action": "unlock",
                "command": "",
                "description": "unlock the system",
                "shell": "cmd",
                "unsupported_reason": "Unlocking must use the operating system's secure authentication flow; ASC should not store, type, or bypass passwords.",
            }
        return None

    def _build_search_target_for_site(self, url: str, query: str) -> str:
        """Build a best-effort search URL for known site domains."""

        target = url.lower()
        if "amazon." in target:
            return f"https://www.amazon.in/s?k={quote_plus(query)}"
        if "flipkart." in target:
            return f"https://www.flipkart.com/search?q={quote_plus(query)}"
        if "google." in target:
            return self.config.get("web_automation", {}).get("search_engine_url", "https://www.google.com/search?q={query}").format(query=quote_plus(query))
        if "bing." in target:
            return f"https://www.bing.com/search?q={quote_plus(query)}"
        return self.config.get("web_automation", {}).get("search_engine_url", "https://www.google.com/search?q={query}").format(query=quote_plus(query))

    async def _execute_directly(self, command: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Execute deterministic commands without invoking the council."""

        intent = strategy.get("intent", {})
        intent_type = intent.get("type")
        step_result: Dict[str, Any]

        if intent_type == "copy_file":
            source = intent.get("source")
            dest = intent.get("destination")
            if source and dest:
                source_path = str(Path(source))
                if not Path(source_path).exists():
                    source_path = str(Path.cwd() / source)
                step_result = self.agents["file"].copy_file(source_path, dest)
            else:
                step_result = {"success": False, "error": "Missing source or destination for copy."}

        elif intent_type == "move_file":
            source = intent.get("source")
            dest = intent.get("destination")
            if source and dest:
                source_path = str(Path(source))
                if not Path(source_path).exists():
                    source_path = str(Path.cwd() / source)
                step_result = self.agents["file"].move_file(source_path, dest)
            else:
                step_result = {"success": False, "error": "Missing source or destination for move."}

        elif intent_type == "open_application":
            step_result = self.agents["system"].open_application(intent["app"])

        elif intent_type == "close_application":
            step_result = self.agents["system"].close_application(intent["app"])

        elif intent_type == "browser_action":
            step_result = await self.agents["web"].perform_browser_action(
                browser_name=intent.get("app"),
                action=intent.get("action"),
                target=intent.get("target"),
            )

        elif intent_type == "fill_form":
            navigation_url = None
            if intent.get("url"):
                navigation_result = await self.agents["web"].navigate_to_url(intent["url"])
                if not navigation_result.get("success"):
                    navigation_result.setdefault("intent", intent_type)
                    return {
                        "success": False,
                        "tier": "direct",
                        "steps_completed": 0,
                        "steps_total": 1,
                        "results": [navigation_result],
                    }
                navigation_url = intent["url"]
            step_result = await self.agents["web"].intelligent_form_fill(
                field_values=intent["fields"],
                submit=intent.get("submit", False),
                focus_first_field=True,
                require_confirmation=intent.get("require_confirmation", False),
                allow_keyboard_fallback=False,  # Require confident mapping when URL is provided
            )
            if navigation_url:
                step_result["navigated_url"] = navigation_url
            
            # Only report success if form fill was genuinely successful
            if not step_result.get("success") and step_result.get("partial_success"):
                step_result["success"] = False
                step_result["warning"] = "Form was only partially filled. Some fields could not be confidently mapped."

        elif intent_type == "confirm_submission":
            token = intent.get("token")
            if not token:
                step_result = {"success": False, "error": "Missing confirmation token."}
            else:
                step_result = await self.agents["web"].confirm_submission(token)

        elif intent_type == "command_history":
            history = self.agents["learning"].get_recent_commands(limit=10)
            step_result = {"success": True, "command_history": history}

        elif intent_type == "record_feedback":
            recent_command = self.memory.recall_short_term("last_command")
            feedback = self.agents["learning"].record_feedback(
                intent.get("feedback", command),
                sentiment=intent.get("sentiment", "neutral"),
                command=recent_command,
            )
            step_result = {"success": True, "feedback_recorded": feedback}

        elif intent_type == "classify_command":
            classification = self.agents["learning"].classify_command(intent.get("command", command))
            step_result = {"success": True, "classification": classification}

        elif intent_type == "save_preference":
            self.memory.save_user_preference(intent["key"], intent["value"])
            step_result = {
                "success": True,
                "preference_saved": {"key": intent["key"], "value": intent["value"]},
            }

        elif intent_type == "approve_preference":
            self.memory.save_user_preference(intent["key"], intent["value"])
            step_result = {
                "success": True,
                "preference_saved": {"key": intent["key"], "value": intent["value"]},
                "approved": True,
            }

        elif intent_type == "reject_preference":
            if intent.get("value"):
                self.memory.save_user_preference(f"{intent['key']}_rejected", intent["value"])
            step_result = {
                "success": True,
                "preference_rejected": {"key": intent["key"], "value": intent.get("value")},
                "rejected": True,
            }

        elif intent_type == "show_preferences":
            step_result = {"success": True, "preferences": self.memory.preferences}

        elif intent_type == "show_workflow_patterns":
            step_result = {
                "success": True,
                "workflow_patterns": self.agents["learning"].discover_workflow_patterns(min_count=1),
            }

        elif intent_type == "show_workflow_templates":
            adaptive_state = self.agents["learning"].get_adaptive_summary()
            step_result = {
                "success": True,
                "workflow_templates": adaptive_state.get("workflow_templates", []),
            }

        elif intent_type == "show_adaptive_evaluation":
            adaptive_state = self.agents["learning"].get_adaptive_summary()
            step_result = {
                "success": True,
                "evaluation_metrics": adaptive_state.get("evaluation_metrics", {}),
            }

        elif intent_type == "show_adaptive_learning":
            step_result = {
                "success": True,
                "adaptive_learning": self.agents["learning"].get_adaptive_summary(),
            }

        elif intent_type == "show_phase5_learning":
            step_result = {
                "success": True,
                "phase5_learning": self.agents["learning"].get_phase5_summary(),
            }

        elif intent_type == "show_phase5_model":
            prediction = self.agents["learning"].predict_phase5_preference(
                command,
                preferences=getattr(self.memory, "preferences", {}),
            )
            step_result = {
                "success": True,
                "phase5_model": {
                    "summary": self.agents["learning"].get_phase5_summary().get("summary", {}),
                    "prediction": prediction.get("prediction", {}),
                    "route_prediction": prediction.get("route_prediction", {}),
                    "reason": prediction.get("reason", ""),
                    "advisory": prediction.get("advisory", True),
                },
            }

        elif intent_type == "voice_status":
            step_result = {"success": True, "voice": self._get_voice_service_health()}

        elif intent_type == "start_voice_server":
            step_result = self.agents["system"].start_voice_server(wait=True, timeout=15)
            if step_result.get("success"):
                self.voice_service_available = True
                step_result["message"] = "Voice server started successfully."
            else:
                step_result["message"] = f"Failed to start voice server: {step_result.get('error', 'Unknown error')}"

        elif intent_type == "stop_voice_server":
            step_result = self.agents["system"].stop_voice_server()
            if step_result.get("success"):
                self.voice_service_available = False
                step_result["message"] = "Voice server stopped successfully."
            else:
                step_result["message"] = f"Failed to stop voice server: {step_result.get('error', 'Unknown error')}"

        # Phase 6: Business Agent commands
        elif intent_type == "create_task":
            step_result = self.agents["business"].create_task(
                title=intent.get("title", "New Task"),
                description=intent.get("description", ""),
                priority=intent.get("priority", "medium"),
                due_date=intent.get("due_date"),
                project_id=intent.get("project_id"),
                category=intent.get("category", "general")
            )

        elif intent_type == "list_tasks":
            step_result = self.agents["business"].list_tasks(
                status=intent.get("status"),
                priority=intent.get("priority"),
                project_id=intent.get("project_id")
            )

        elif intent_type == "complete_task":
            task_id = intent.get("task_id")
            if task_id:
                step_result = self.agents["business"].update_task_status(task_id, "completed")
            else:
                step_result = {"success": False, "error": "Task ID required for completion"}

        elif intent_type == "create_project":
            step_result = self.agents["business"].create_project(
                name=intent.get("name", "New Project"),
                description=intent.get("description", ""),
                start_date=intent.get("start_date"),
                end_date=intent.get("end_date")
            )

        elif intent_type == "daily_plan":
            step_result = self.agents["business"].get_daily_plan()

        elif intent_type == "schedule_reminder":
            step_result = self.agents["business"].schedule_reminder(
                title=intent.get("title", "Reminder"),
                reminder_time=intent.get("reminder_time"),
                description=intent.get("description", "")
            )

        elif intent_type == "meeting_agenda":
            step_result = self.agents["business"].generate_meeting_agenda(
                meeting_title=intent.get("title", "Meeting"),
                duration_minutes=intent.get("duration", 60)
            )

        elif intent_type == "add_calendar_event":
            step_result = self.agents["business"].add_calendar_event(
                title=intent.get("title", "Event"),
                start_time=intent.get("start_time"),
                end_time=intent.get("end_time"),
                description=intent.get("description", ""),
                location=intent.get("location", "")
            )

        elif intent_type == "upcoming_events":
            step_result = self.agents["business"].get_upcoming_events(
                days_ahead=intent.get("days_ahead", 7)
            )

        elif intent_type == "project_status":
            step_result = self.agents["business"].get_project_status(
                project_id=intent.get("project_id")
            )

        elif intent_type == "list_projects":
            step_result = self.agents["business"].list_projects(
                status=intent.get("status")
            )

        elif intent_type == "create_milestone":
            step_result = self.agents["business"].create_milestone(
                project_id=intent.get("project_id"),
                title=intent.get("title", "Milestone"),
                target_date=intent.get("target_date"),
                description=intent.get("description", "")
            )

        elif intent_type == "project_timeline":
            step_result = self.agents["business"].get_project_timeline(
                project_id=intent.get("project_id")
            )

        elif intent_type == "send_email":
            step_result = self.agents["business"].send_email_notification(
                to_email=intent.get("to_email"),
                subject=intent.get("subject"),
                body=intent.get("body"),
                priority=intent.get("priority", "normal")
            )

        elif intent_type == "email_template":
            step_result = self.agents["business"].generate_email_template(
                template_type=intent.get("template_type", "task_completion"),
                context=intent.get("context", {})
            )

        elif intent_type == "email_status":
            step_result = self.agents["business"].check_email_configuration()

        elif intent_type == "call_external_api":
            step_result = self.agents["business"].call_external_api(
                service_name=intent.get("service_name"),
                endpoint=intent.get("endpoint"),
                method=intent.get("method", "GET"),
                params=intent.get("params"),
                data=intent.get("data")
            )

        elif intent_type == "available_services":
            step_result = self.agents["business"].get_available_services()

        elif intent_type == "configure_service":
            step_result = self.agents["business"].configure_service(
                service_name=intent.get("service_name"),
                configuration=intent.get("configuration", {})
            )

        elif intent_type == "coordinate_agents":
            step_result = self.agents["business"].coordinate_agents(
                task=intent.get("task", "General task"),
                required_agents=intent.get("required_agents", ["file", "system"]),
                coordination_type=intent.get("coordination_type", "sequential")
            )

        elif intent_type == "agent_status":
            step_result = self.agents["business"].get_agent_status()

        elif intent_type == "optimize_workflow":
            step_result = self.agents["business"].optimize_agent_workflow(
                task=intent.get("task", "General task"),
                agent_capabilities=intent.get("agent_capabilities", {})
            )

        # Phase 6 Advanced Features
        elif intent_type == "configure_email":
            step_result = self.agents["business"].configure_email(
                smtp_server=intent.get("smtp_server"),
                smtp_port=intent.get("smtp_port", 587),
                email_address=intent.get("email_address"),
                password=intent.get("password"),
                use_tls=intent.get("use_tls", True)
            )

        elif intent_type == "calendar_integration":
            calendar_type = intent.get("calendar_type", "windows")
            step_result = self.agents["business"].add_calendar_event(
                title=intent.get("title", "Event"),
                start_time=intent.get("start_time"),
                end_time=intent.get("end_time"),
                description=intent.get("description", ""),
                location=intent.get("location", ""),
                calendar_type=calendar_type
            )

        elif intent_type == "gantt_chart":
            step_result = self.agents["business"].create_gantt_chart(
                project_id=intent.get("project_id"),
                output_format=intent.get("output_format", "visual")
            )

        elif intent_type == "allocate_resources":
            step_result = self.agents["business"].allocate_resources(
                project_id=intent.get("project_id"),
                resources=intent.get("resources", [])
            )

        elif intent_type == "resource_utilization":
            step_result = self.agents["business"].analyze_resource_utilization(
                project_id=intent.get("project_id")
            )

        elif intent_type == "track_time":
            step_result = self.agents["business"].track_time_for_task(
                task_id=intent.get("task_id"),
                hours_spent=intent.get("hours_spent", 0.0),
                description=intent.get("description", "")
            )

        elif intent_type == "productivity_report":
            step_result = self.agents["business"].generate_productivity_report(
                days=intent.get("days", 7),
                format=intent.get("format", "text")
            )

        elif intent_type == "weather_api":
            step_result = self.agents["business"].integrate_weather_api(
                location=intent.get("location"),
                api_key=intent.get("api_key")
            )

        elif intent_type == "news_api":
            step_result = self.agents["business"].integrate_news_api(
                query=intent.get("query"),
                api_key=intent.get("api_key"),
                articles_count=intent.get("articles_count", 5)
            )

        elif intent_type == "stock_api":
            step_result = self.agents["business"].integrate_stock_api(
                symbol=intent.get("symbol"),
                api_key=intent.get("api_key")
            )

        elif intent_type == "business_dashboard":
            step_result = self.agents["business"].create_business_intelligence_dashboard(
                days=intent.get("days", 30)
            )

        elif intent_type == "add_team_member":
            step_result = self.agents["business"].add_team_member(
                name=intent.get("name"),
                email=intent.get("email"),
                role=intent.get("role", "member"),
                skills=intent.get("skills")
            )

        elif intent_type == "list_team":
            step_result = self.agents["business"].list_team_members(
                role=intent.get("role")
            )

        elif intent_type == "assign_team_project":
            step_result = self.agents["business"].assign_team_member_to_project(
                team_member_id=intent.get("team_member_id"),
                project_id=intent.get("project_id")
            )

        elif intent_type == "task_comment":
            step_result = self.agents["business"].add_task_comment(
                task_id=intent.get("task_id"),
                comment=intent.get("comment"),
                author_id=intent.get("author_id")
            )

        elif intent_type == "team_notification":
            step_result = self.agents["business"].create_team_notification(
                recipient_id=intent.get("recipient_id"),
                message=intent.get("message"),
                notification_type=intent.get("notification_type", "general"),
                related_task_id=intent.get("related_task_id"),
                related_project_id=intent.get("related_project_id")
            )

        elif intent_type == "shared_workspace":
            step_result = self.agents["business"].create_shared_workspace(
                name=intent.get("name"),
                description=intent.get("description", ""),
                team_member_ids=intent.get("team_member_ids")
            )

        # Advanced Enterprise Features
        elif intent_type == "create_ensemble_model":
            step_result = self.agents["advanced_neural"].create_ensemble_model(
                model_type=intent.get("model_type", "random_forest"),
                input_features=intent.get("input_features", 10),
                task_type=intent.get("task_type", "classification")
            )

        elif intent_type == "train_predictive_model":
            step_result = self.agents["advanced_neural"].train_predictive_model(
                model_id=intent.get("model_id"),
                training_data=intent.get("training_data", []),
                labels=intent.get("labels", []),
                validation_split=intent.get("validation_split", 0.2)
            )

        elif intent_type == "detect_anomalies":
            step_result = self.agents["advanced_neural"].detect_anomalies(
                data=intent.get("data", []),
                threshold=intent.get("threshold", 2.0),
                method=intent.get("method", "statistical")
            )

        elif intent_type == "time_series_forecast":
            step_result = self.agents["advanced_neural"].create_time_series_forecast(
                data=intent.get("data", []),
                forecast_periods=intent.get("forecast_periods", 10),
                method=intent.get("method", "moving_average")
            )

        elif intent_type == "create_deep_learning_model":
            step_result = self.agents["advanced_neural"].create_deep_learning_model(
                model_type=intent.get("model_type", "feedforward"),
                input_size=intent.get("input_size", 10),
                hidden_layers=intent.get("hidden_layers", [64, 32]),
                output_size=intent.get("output_size", 1)
            )

        elif intent_type == "erp_integration":
            step_result = self.agents["business_process"].create_erp_integration(
                system_name=intent.get("system_name"),
                api_endpoint=intent.get("api_endpoint"),
                authentication=intent.get("authentication", {}),
                sync_config=intent.get("sync_config", {})
            )

        elif intent_type == "crm_integration":
            step_result = self.agents["business_process"].create_crm_integration(
                system_name=intent.get("system_name"),
                api_endpoint=intent.get("api_endpoint"),
                authentication=intent.get("authentication", {}),
                contact_fields=intent.get("contact_fields", [])
            )

        elif intent_type == "create_workflow":
            step_result = self.agents["business_process"].create_business_workflow(
                name=intent.get("name"),
                description=intent.get("description", ""),
                steps=intent.get("steps", []),
                triggers=intent.get("triggers", []),
                conditions=intent.get("conditions", [])
            )

        elif intent_type == "process_mining":
            step_result = self.agents["business_process"].mine_process_patterns(
                process_logs=intent.get("process_logs", []),
                min_frequency=intent.get("min_frequency", 3)
            )

        elif intent_type == "business_rule":
            step_result = self.agents["business_process"].create_business_rule(
                rule_name=intent.get("rule_name"),
                condition=intent.get("condition", {}),
                action=intent.get("action", {}),
                priority=intent.get("priority", 5)
            )

        elif intent_type == "create_tenant":
            step_result = self.agents["security"].create_tenant(
                tenant_name=intent.get("tenant_name"),
                domain=intent.get("domain"),
                admin_email=intent.get("admin_email"),
                settings=intent.get("settings", {})
            )

        elif intent_type == "create_role":
            step_result = self.agents["security"].create_role(
                role_name=intent.get("role_name"),
                permissions=intent.get("permissions", []),
                description=intent.get("description", "")
            )

        elif intent_type == "check_permission":
            step_result = self.agents["security"].check_permission(
                user_id=intent.get("user_id"),
                tenant_id=intent.get("tenant_id"),
                required_permission=intent.get("required_permission")
            )

        elif intent_type == "audit_trail":
            step_result = self.agents["security"].get_audit_trail(
                filters=intent.get("filters", {}),
                limit=intent.get("limit", 100)
            )

        elif intent_type == "gdpr_compliance":
            step_result = self.agents["security"].check_gdpr_compliance(
                tenant_id=intent.get("tenant_id")
            )

        elif intent_type == "bi_dashboard":
            step_result = self.agents["analytics"].create_bi_dashboard(
                dashboard_name=intent.get("dashboard_name"),
                description=intent.get("description", ""),
                widgets=intent.get("widgets", []),
                refresh_interval=intent.get("refresh_interval", 300)
            )

        elif intent_type == "create_report":
            step_result = self.agents["analytics"].create_analytics_report(
                report_name=intent.get("report_name"),
                report_type=intent.get("report_type", "productivity"),
                parameters=intent.get("parameters", {}),
                schedule=intent.get("schedule", None)
            )

        elif intent_type == "real_time_monitor":
            step_result = self.agents["analytics"].create_real_time_monitor(
                monitor_name=intent.get("monitor_name"),
                metrics=intent.get("metrics", []),
                thresholds=intent.get("thresholds", {}),
                alert_recipients=intent.get("alert_recipients", [])
            )

        elif intent_type == "system_command":
            step_result = self.agents["system"].run_command(
                intent.get("command", ""),
                shell=intent.get("shell", "powershell"),
            )
            if step_result.get("needs_confirmation"):
                self.memory.remember_short_term(
                    "pending_system_command",
                    {
                        "command": intent.get("command", ""),
                        "shell": intent.get("shell", "powershell"),
                        "warning": step_result.get("warning"),
                        "matched_patterns": step_result.get("matched_patterns", []),
                    },
                )

        elif intent_type == "system_power_action":
            if intent.get("unsupported_reason"):
                step_result = {
                    "success": False,
                    "unsupported": True,
                    "power_action": intent.get("power_action"),
                    "error": intent.get("unsupported_reason"),
                }
            else:
                pending_payload = {
                    "command": intent.get("command", ""),
                    "shell": intent.get("shell", "cmd"),
                    "warning": f"This will {intent.get('description', 'change system power state')}. Type 'confirm command' to proceed or 'cancel command' to discard it.",
                    "matched_patterns": [intent.get("power_action", "system_power_action")],
                    "power_action": intent.get("power_action"),
                }
                self.memory.remember_short_term("pending_system_command", pending_payload)
                step_result = {
                    "success": False,
                    "needs_confirmation": True,
                    "power_action": intent.get("power_action"),
                    "command": intent.get("command"),
                    "warning": pending_payload["warning"],
                    "matched_patterns": pending_payload["matched_patterns"],
                }

        elif intent_type == "confirm_system_command":
            pending = self.memory.recall_short_term("pending_system_command")
            if not pending:
                step_result = {"success": False, "error": "No pending system command to confirm."}
            else:
                step_result = self.agents["system"].run_command(
                    pending.get("command", ""),
                    shell=pending.get("shell", "powershell"),
                    confirmed=True,
                )
                self.memory.remember_short_term("pending_system_command", None)
                step_result["confirmed_command"] = True

        elif intent_type == "cancel_system_command":
            pending = self.memory.recall_short_term("pending_system_command")
            self.memory.remember_short_term("pending_system_command", None)
            step_result = {
                "success": True,
                "cancelled": True,
                "command": (pending or {}).get("command"),
                "message": "Pending system command cancelled.",
            }

        elif intent_type == "system_info":
            system_info = self.agents["system"].get_system_info()
            step_result = {"success": True, **system_info}

        elif intent_type == "network_info":
            step_result = self.agents["system"].get_network_info()

        elif intent_type == "disk_drives":
            step_result = {
                "success": True,
                "drives": self.agents["system"].get_disk_usage_all_drives(),
            }

        elif intent_type == "environment_variable":
            step_result = self.agents["system"].get_environment_variable(intent.get("name", ""))

        elif intent_type == "list_processes":
            processes = self.agents["system"].list_processes(intent.get("filter"))
            step_result = {"success": True, "processes": processes}

        elif intent_type == "list_files":
            files = self.agents["file"].list_files(intent.get("path", "."))
            step_result = {"success": True, "files": files, "path": intent.get("path", ".")}

        elif intent_type == "organize_folder":
            step_result = self.agents["file"].organize_folder(intent.get("path", "."))

        elif intent_type == "file_info":
            step_result = self.agents["file"].get_file_info(intent.get("path", "."))

        elif intent_type == "search_files":
            results = self.agents["file"].search_files(
                intent.get("path", "."),
                intent.get("query", ""),
                search_content=intent.get("search_content", False),
            )
            step_result = {
                "success": True,
                "files": results,
                "path": intent.get("path", "."),
                "query": intent.get("query", ""),
            }

        elif intent_type == "backup_folder":
            step_result = self.agents["file"].backup_folder(
                intent.get("path", "."),
                backup_name=intent.get("backup_name"),
            )

        # Cybersecurity Direct Handlers (Priority 2, Task 5)
        elif intent_type == "security_port_scan":
            step_result = self.agents["system"].scan_ports(
                intent.get("host"),
                intent.get("ports", "common")
            )

        elif intent_type == "security_ssl_check":
            step_result = self.agents["system"].check_ssl_certificate(intent.get("domain"))

        elif intent_type == "security_headers_check":
            step_result = self.agents["system"].check_security_headers(intent.get("url"))

        elif intent_type == "dns_lookup":
            step_result = self.agents["system"].dns_lookup(intent.get("domain"))

        # File Agent Advanced Handlers (Priority 2, Task 5b)
        elif intent_type == "restore_organization":
            step_result = self.agents["file"].restore_organization(intent.get("manifest_id"))

        elif intent_type == "analyze_disk_usage":
            step_result = self.agents["file"].analyze_disk_usage(intent.get("path", "."))

        elif intent_type == "find_duplicates":
            step_result = self.agents["file"].find_duplicate_files(intent.get("path", "."))

        elif intent_type == "batch_rename_files":
            step_result = self.agents["file"].batch_rename_files(
                intent.get("path", "."),
                intent.get("find"),
                intent.get("replace"),
                intent.get("extension")
            )

        elif intent_type == "create_folder":
            step_result = self.agents["file"].create_folder(intent["path"])

        elif intent_type == "create_file":
            step_result = self.agents["file"].create_file(intent["path"])

        else:
            step_result = {"success": False, "error": f"Unsupported direct intent: {intent_type}"}

        step_result.setdefault("intent", intent_type)
        needs_confirmation = bool(step_result.get("needs_confirmation"))
        top_level_error = None if step_result.get("success") or needs_confirmation else step_result.get("error", "Direct execution failed")
        return {
            "success": step_result.get("success", False),
            "tier": "direct",
            "steps_completed": 1 if step_result.get("success") else 0,
            "steps_total": 1,
            "results": [step_result],
            "error": top_level_error,
            "needs_confirmation": needs_confirmation,
            "question": "This command may be destructive. Type 'confirm command' to run it or 'cancel command' to discard it." if needs_confirmation else None,
        }

    async def _execute_autonomous_decision(self, decision: Dict[str, Any], original_command: str) -> Dict[str, Any]:
        """Execute or clarify a phase-3 autonomy decision."""

        mode = decision.get("mode")
        if mode == "clarify":
            informational = decision.get("strategy") in {"workflow_suggestions", "help"}
            if not informational:
                self.memory.remember_short_term(
                    "pending_clarification",
                    {
                        "original_command": original_command,
                        "strategy": decision.get("strategy"),
                        "question": decision.get("question"),
                    },
                )
            return {
                "success": informational,
                "needs_clarification": True,
                "question": decision.get("question", "Can you clarify what you want me to do?"),
                "suggestions": decision.get("suggestions", []),
                "autonomy": decision,
                "steps_completed": 1 if informational else 0,
                "steps_total": 0,
                "error": None if informational else "Clarification needed",
            }

        if decision.get("intent"):
            result = await self._execute_directly(original_command, {"intent": decision["intent"]})
        elif decision.get("decomposition"):
            result = await self._execute_decomposed_tasks(decision["decomposition"], original_command)
        elif decision.get("action_plan"):
            result = await self._execute_plan(decision, original_command)
        else:
            result = {
                "success": False,
                "steps_completed": 0,
                "steps_total": 0,
                "results": [],
                "error": "Autonomy engine could not produce an executable plan.",
            }

        if not result.get("success") and decision.get("mode") == "execute":
            retry = await self._retry_autonomous_decision(decision, original_command, result)
            if retry:
                result = retry

        result["autonomy"] = {
            "strategy": decision.get("strategy"),
            "confidence": decision.get("confidence"),
            "reasoning": decision.get("reasoning"),
        }
        return result

    async def _retry_autonomous_decision(
        self,
        decision: Dict[str, Any],
        original_command: str,
        failed_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Try one simple recovery path when an autonomous plan fails."""

        if not decision.get("action_plan"):
            return None

        retry_steps = []
        changed = False
        for step in decision.get("action_plan", []):
            step_copy = dict(step)
            action = step_copy.get("action")
            params = dict(step_copy.get("params", {}))
            if action == "open" and not params.get("app"):
                params["app"] = self.config.get("web_automation", {}).get("default_browser", "chrome")
                changed = True
            elif action == "search" and not (params.get("query") or params.get("target")):
                params["query"] = original_command
                changed = True
            step_copy["params"] = params
            retry_steps.append(step_copy)

        if not changed:
            return None

        retry_plan = {
            "action_plan": retry_steps,
            "strategy": f"{decision.get('strategy', 'autonomy')}_retry",
        }
        retry_result = await self._execute_plan(retry_plan, original_command)
        retry_result["retry_of"] = failed_result
        retry_result["retried"] = True
        return retry_result

    async def _execute_plan(self, plan: Dict[str, Any], original_command: str) -> Dict[str, Any]:
        """Execute a council-produced action plan."""

        logger.info("Executing plan...")
        results = []
        action_plan = self._normalize_action_plan(plan, original_command)

        for step in action_plan:
            try:
                action_type = step.get("action", step.get("type", "unknown"))
                params = step.get("params", step)

                logger.debug("Executing step: {}", action_type)
                step_result = await self._route_action(action_type, params, original_command)
                step_result.setdefault("action", action_type)
                step_result.setdefault("agent", step.get("agent", self._agent_for_action(action_type)))
                results.append(step_result)
                await asyncio.sleep(self.execution_pause_seconds)

            except Exception as exc:
                logger.error("Step execution failed: {}", str(exc))
                results.append({"success": False, "action": action_type, "error": str(exc)})

        success_count = sum(1 for result in results if result.get("success"))
        logger.success("Execution complete: {}/{} steps succeeded", success_count, len(results))

        return {
            "success": success_count == len(results) and len(results) > 0,
            "steps_completed": success_count,
            "steps_total": len(results),
            "results": results,
        }

    def _normalize_action_plan(self, plan: Dict[str, Any], original_command: str) -> List[Dict[str, Any]]:
        """Convert loose council output into executable agent steps."""

        raw_steps = plan.get("action_plan") or plan.get("steps")
        if raw_steps is None:
            raw_steps = [plan]
        elif isinstance(raw_steps, (str, dict)):
            raw_steps = [raw_steps]

        normalized_steps: List[Dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            step = self._normalize_plan_step(raw_step, index, original_command)
            if step:
                normalized_steps.append(step)

        if normalized_steps:
            return normalized_steps

        fallback = self.task_decomposer.decompose(original_command)
        return fallback.get("subtasks", [])

    def _normalize_plan_step(self, raw_step: Any, index: int, original_command: str) -> Optional[Dict[str, Any]]:
        """Normalize one LLM/council step into ASC's routed action format."""

        if isinstance(raw_step, dict):
            description = str(
                raw_step.get("description")
                or raw_step.get("task")
                or raw_step.get("reason")
                or raw_step.get("action")
                or original_command
            )
            action = str(raw_step.get("action") or raw_step.get("type") or "").strip().lower()
            params = dict(raw_step.get("params") or {})
            for key, value in raw_step.items():
                if key not in {"action", "type", "params", "agent"} and key not in params:
                    params[key] = value
        else:
            description = str(raw_step)
            action = ""
            params = {"description": description}

        if not action or action in {"unknown", "general", "step"}:
            inferred = self._subtask_from_description(description, index)
            if inferred:
                return inferred
            params.setdefault("description", description)
            action = "general"

        params.setdefault("description", description)
        return {
            "id": f"plan-step-{index}",
            "agent": self._agent_for_action(action),
            "action": action,
            "params": params,
            "description": description,
        }

    def _subtask_from_description(self, description: str, index: int) -> Optional[Dict[str, Any]]:
        """Infer a routeable subtask from a natural-language step."""

        direct_intent = self._parse_direct_command(description)
        if direct_intent:
            return self._subtask_from_direct_intent(direct_intent, description, index)

        plan = self.task_decomposer.decompose(description)
        subtasks = plan.get("subtasks", [])
        if len(subtasks) == 1 and subtasks[0].get("action") != "general":
            subtask = dict(subtasks[0])
            subtask["id"] = f"plan-step-{index}"
            return subtask
        return None

    def _subtask_from_direct_intent(self, intent: Dict[str, Any], description: str, index: int) -> Dict[str, Any]:
        """Translate a deterministic intent into the generic routed action schema."""

        intent_type = intent.get("type")
        params = dict(intent)
        params["description"] = description

        mapping = {
            "browser_action": ("web", intent.get("action", "navigate")),
            "fill_form": ("web", "form"),
            "open_application": ("system", "open"),
            "close_application": ("system", "close"),
            "system_command": ("system", "run_command"),
            "system_info": ("system", "status"),
            "network_info": ("system", "network"),
            "disk_drives": ("system", "drives"),
            "environment_variable": ("system", "environment"),
            "list_processes": ("system", "process"),
            "list_files": ("file", "list"),
            "organize_folder": ("file", "organize"),
            "create_folder": ("file", "create_folder"),
            "create_file": ("file", "create_file"),
            "copy_file": ("file", "copy"),
            "move_file": ("file", "move"),
            "file_info": ("file", "file_info"),
            "search_files": ("file", "search_files"),
            "backup_folder": ("file", "backup"),
            "analyze_disk_usage": ("file", "disk_usage"),
            "find_duplicates": ("file", "duplicates"),
            "restore_organization": ("file", "restore"),
            "batch_rename_files": ("file", "batch_rename"),
            "security_port_scan": ("system", "command"),
            "security_ssl_check": ("system", "command"),
            "security_headers_check": ("system", "command"),
            "dns_lookup": ("system", "command"),
        }
        agent, action = mapping.get(intent_type, ("general", "general"))
        if intent_type == "browser_action":
            params["browser"] = intent.get("app")
            params["query"] = intent.get("target")
            params["target"] = intent.get("target")
        elif intent_type == "fill_form":
            params["fields"] = intent.get("fields", {})
        elif intent_type == "system_command":
            params["command"] = intent.get("command", "")

        return {
            "id": f"plan-step-{index}",
            "agent": agent,
            "action": action,
            "params": params,
            "description": description,
        }

    def _agent_for_action(self, action_type: str) -> str:
        """Return the agent name normally responsible for an action."""

        registry = getattr(self, "tool_registry", None)
        if registry:
            spec = registry.resolve(action_type)
            if spec:
                return spec.agent

        action_lower = (action_type or "").lower()
        if action_lower in [
            "file", "folder", "organize", "move", "copy", "delete", "list", "create",
            "create_file", "create_folder", "file_info", "search_files", "backup",
            "disk_usage", "duplicates", "restore", "batch_rename",
        ]:
            return "file"
        if action_lower in [
            "system", "process", "application", "command", "run_command", "open",
            "close", "status", "wait_for_process", "network", "drives", "environment",
        ]:
            return "system"
        if action_lower in ["vision", "screenshot", "ocr", "screen", "analyze"]:
            return "vision"
        if action_lower in ["web", "browser", "navigate", "search", "site_search", "form", "extract_text"]:
            return "web"
        return "general"

    def _build_tool_registry(self) -> ToolRegistry:
        """Build the explicit phase-2 tool boundary used by planners."""

        registry = ToolRegistry()
        registry.register(ToolSpec(
            name="file_ops",
            agent="file",
            description="Create, list, search, inspect, organize, backup, move, copy, and delete local files/folders.",
            actions=[
                "file", "folder", "organize", "move", "copy", "delete", "list",
                "create", "create_file", "create_folder", "file_info", "search_files",
                "backup", "disk_usage", "duplicates", "restore", "batch_rename",
            ],
            handler=lambda action, params, context: self._execute_file_action(action, params),
        ))
        registry.register(ToolSpec(
            name="system_ops",
            agent="system",
            description="Open/close apps, inspect processes, run safe shell commands, and read system/network/disk status.",
            actions=[
                "system", "process", "application", "command", "run_command", "open",
                "close", "status", "wait_for_process", "network", "drives", "environment",
            ],
            handler=lambda action, params, context: self._execute_system_action(action, params),
        ))
        registry.register(ToolSpec(
            name="vision_ops",
            agent="vision",
            description="Capture screenshots, OCR visible text, and analyze the screen.",
            actions=["vision", "screenshot", "ocr", "screen", "analyze"],
            handler=lambda action, params, context: self._execute_vision_action(action, params),
        ))
        registry.register(ToolSpec(
            name="web_ops",
            agent="web",
            description="Search, navigate websites, extract page text, and fill visible forms.",
            actions=["web", "browser", "navigate", "search", "site_search", "form", "extract_text"],
            handler=lambda action, params, context: self._execute_web_action(action, params),
        ))
        return registry

    def get_tool_manifest(self) -> List[Dict[str, Any]]:
        """Expose available tool metadata for future autonomous planners."""

        registry = getattr(self, "tool_registry", None)
        if not registry:
            registry = self._build_tool_registry()
            self.tool_registry = registry
        return registry.manifest()

    async def _execute_decomposed_tasks(self, decomposition: Dict[str, Any], original_command: str) -> Dict[str, Any]:
        """Execute a decomposed multi-step task sequentially with rollback support on failure."""

        logger.info("Executing decomposed task with {} subtasks", len(decomposition.get("subtasks", [])))
        results: List[Dict[str, Any]] = []
        rollback_actions = []
        failed = False
        error_msg = ""

        for subtask in decomposition.get("subtasks", []):
            action = subtask.get("action", "general")
            params = dict(subtask.get("params", {}))

            if action == "create_report":
                content = self._build_report_content(original_command, results)
                step_result = self.agents["file"].create_file(params["path"], content)
                step_result["report_topic"] = params.get("topic")
            else:
                step_result = await self._route_action(action, params, subtask.get("description", original_command))

            step_result["subtask_id"] = subtask.get("id")
            step_result["subtask_description"] = subtask.get("description")
            results.append(step_result)

            if step_result.get("success"):
                # Register rollback actions
                if action == "organize" and step_result.get("manifest_id"):
                    rollback_actions.append({
                        "type": "restore_organization",
                        "manifest_id": step_result["manifest_id"]
                    })
                elif action == "create_file" or (action == "create" and "file" in params.get("description", "").lower()):
                    rollback_actions.append({
                        "type": "delete_file",
                        "path": step_result.get("path") or params.get("path")
                    })
                elif action == "create_folder" or (action == "create" and "folder" in params.get("description", "").lower()):
                    rollback_actions.append({
                        "type": "delete_folder",
                        "path": step_result.get("path") or params.get("path")
                    })
            else:
                failed = True
                error_msg = step_result.get("error", "Subtask failed")
                break

            await asyncio.sleep(self.execution_pause_seconds)

        if failed:
            logger.warning("Subtask failed. Initiating rollback of {} actions...", len(rollback_actions))
            for rb in reversed(rollback_actions):
                try:
                    if rb["type"] == "restore_organization":
                        logger.info("Rolling back folder organization using manifest: {}", rb["manifest_id"])
                        self.agents["file"].restore_organization(rb["manifest_id"])
                    elif rb["type"] == "delete_file" and rb["path"]:
                        logger.info("Rolling back file creation by deleting: {}", rb["path"])
                        self.agents["file"].delete_file(rb["path"])
                    elif rb["type"] == "delete_folder" and rb["path"]:
                        logger.info("Rolling back folder creation by deleting: {}", rb["path"])
                        self.agents["file"].delete_folder(rb["path"], recursive=True)
                except Exception as ex:
                    logger.error("Failed to execute rollback action: {}", str(ex))

        success_count = sum(1 for result in results if result.get("success"))
        return {
            "success": not failed and success_count == len(results) and len(results) > 0,
            "steps_completed": success_count,
            "steps_total": len(decomposition.get("subtasks", [])),
            "results": results,
            "decomposition": decomposition,
            "rollback_executed": failed and len(rollback_actions) > 0,
            "error": error_msg if failed else None
        }

    async def _route_action(self, action_type: str, params: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Route an action to the most appropriate agent."""

        registry = getattr(self, "tool_registry", None)
        if not registry:
            registry = self._build_tool_registry()
            self.tool_registry = registry

        routed = await registry.execute(action_type.lower(), params, context)
        if routed.get("success") or "No registered tool" not in routed.get("error", ""):
            return routed

        return await self._execute_general_action(context, params)

    def _execute_file_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute file-related actions."""

        file_agent = self.agents["file"]

        if action_type == "create_folder":
            return file_agent.create_folder(params.get("path", "./new_folder"))

        if action_type == "create_file":
            return file_agent.create_file(params.get("path", "./new_file.txt"), params.get("content", ""))

        if "organize" in action_type:
            path = params.get("path") or self._extract_known_path(params.get("description", "desktop"))
            return file_agent.organize_folder(path)

        if action_type == "file_info":
            return file_agent.get_file_info(params.get("path") or self._resolve_user_path(params.get("description", ".")))

        if action_type == "search_files":
            results = file_agent.search_files(
                params.get("path") or self._extract_known_path(params.get("description", ".")),
                params.get("query") or params.get("target") or "",
                search_content=params.get("search_content", False),
            )
            return {"success": True, "files": results, "path": params.get("path", "."), "query": params.get("query", "")}

        if action_type == "backup":
            return file_agent.backup_folder(
                params.get("path") or self._extract_known_path(params.get("description", ".")),
                backup_name=params.get("backup_name"),
            )

        if action_type == "disk_usage":
            return file_agent.analyze_disk_usage(params.get("path") or self._extract_known_path(params.get("description", ".")))

        if action_type == "duplicates":
            return file_agent.find_duplicate_files(params.get("path") or self._extract_known_path(params.get("description", ".")))

        if action_type == "restore":
            return file_agent.restore_organization(params.get("manifest_id"))

        if action_type == "batch_rename":
            return file_agent.batch_rename_files(
                params.get("path") or self._extract_known_path(params.get("description", ".")),
                params.get("find"),
                params.get("replace"),
                params.get("extension"),
            )

        if "create" in action_type:
            if params.get("path") and "folder" not in params.get("description", "").lower():
                return file_agent.create_file(params["path"], params.get("content", ""))
            if "folder" in params.get("description", "").lower():
                return file_agent.create_folder(params.get("path", "./new_folder"))
            return file_agent.create_file(params.get("path", "./new_file.txt"), params.get("content", ""))

        if "move" in action_type:
            return file_agent.move_file(params.get("source"), params.get("destination"))

        if "copy" in action_type:
            source = params.get("source") or params.get("description")
            destination = params.get("destination") or params.get("path") or self._extract_known_path(params.get("description", "desktop"))
            if source and destination:
                if not Path(source).exists():
                    source = str(Path.cwd() / source)
                return file_agent.copy_file(source, destination)
            return {"success": False, "error": "Missing source or destination for copy."}

        if "delete" in action_type:
            target_path = params.get("path", "")
            if Path(target_path).is_dir():
                return file_agent.delete_folder(target_path, recursive=False)
            return file_agent.delete_file(target_path)

        path = params.get("path")
        if not path and params.get("description"):
            path = self._extract_known_path(params["description"])
        files = file_agent.list_files(path or ".")
        return {"success": True, "files": files, "path": path or "."}

    async def _execute_system_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute system-related actions."""

        system_agent = self.agents["system"]

        if "open" in action_type or "application" in action_type:
            app_name = params.get("app", params.get("application", "notepad"))
            target_url = params.get("url") or params.get("target_url")
            if target_url:
                return await self.agents["web"].navigate_to_url(target_url, browser_name=app_name)
            return system_agent.open_application(app_name, args=params.get("args"))

        if "close" in action_type:
            app_name = params.get("app", params.get("application"))
            return system_agent.close_application(app_name)

        if "process" in action_type:
            processes = system_agent.list_processes(params.get("filter"))
            return {"success": True, "processes": processes[:10]}

        if action_type == "network":
            return system_agent.get_network_info()

        if action_type == "drives":
            return {"success": True, "drives": system_agent.get_disk_usage_all_drives()}

        if action_type == "environment":
            return system_agent.get_environment_variable(params.get("name", ""))

        if action_type == "wait_for_process":
            return system_agent.wait_for_process(params.get("name", ""), timeout=params.get("timeout", 30))

        if "command" in action_type:
            shell_name = params.get("shell", "powershell")
            return system_agent.run_command(params.get("command", ""), shell=shell_name)

        system_info = system_agent.get_system_info()
        return {"success": True, **system_info}

    async def _execute_vision_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute vision-related actions."""

        vision_agent = self.agents["vision"]

        if "screenshot" in action_type:
            image = vision_agent.capture_screen()
            return {"success": image is not None, "message": "Screenshot captured"}

        if "ocr" in action_type:
            text = vision_agent.extract_text_ocr()
            return {"success": bool(text), "text": text[:500]}

        result = await vision_agent.understand_screen(params.get("question"))
        return {"success": "error" not in result, **result}

    async def _execute_web_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute web/browser and form actions."""

        web_agent = self.agents["web"]
        browser_name = params.get("app") or params.get("browser") or self.config.get("web_automation", {}).get(
            "default_browser", "chrome"
        )

        if action_type == "extract_text" or params.get("extract_text"):
            return await web_agent.extract_text_from_page()

        if action_type == "site_search" or params.get("site"):
            target = params.get("query") or params.get("target") or params.get("description", "")
            return await web_agent.search_site(
                target,
                site=params.get("site"),
                browser_name=browser_name,
            )

        if "search" in action_type:
            target = params.get("query") or params.get("target") or params.get("description", "")
            return await web_agent.perform_browser_action(browser_name, "search", target)

        if "navigate" in action_type or "browser" in action_type or "web" in action_type:
            target = params.get("url") or params.get("target")
            if target:
                return await web_agent.perform_browser_action(browser_name, "navigate", target)

        if "form" in action_type:
            if params.get("url"):
                navigation = await web_agent.navigate_to_url(params["url"], browser_name=browser_name)
                if not navigation.get("success"):
                    return navigation
            if params.get("fields"):
                form_result = await web_agent.intelligent_form_fill(
                    field_values=params["fields"],
                    form_name=params.get("form_name"),
                    submit=params.get("submit", False),
                    focus_first_field=params.get("focus_first_field", False),
                    allow_keyboard_fallback=not bool(params.get("url")),
                )
                if params.get("url"):
                    form_result["navigated_url"] = params["url"]
                return form_result
            return await web_agent.analyze_form(params.get("form_name"))

        return {"success": False, "error": "Unknown web action"}

    async def _execute_general_action(self, context: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback action inference when a plan step is vague."""

        description = params.get("description", context)
        inferred_intent = self._parse_direct_command(description) or self._parse_direct_command(context)
        if inferred_intent:
            return (await self._execute_directly(description, {"intent": inferred_intent}))["results"][0]

        try:
            plan = await self.council.decide(description, "medium")
            if not isinstance(plan, dict):
                raise ValueError("Council did not return a plan")
            normalized_plan = self._normalize_action_plan({"action_plan": plan.get("action_plan") or plan.get("steps")}, description)
            if normalized_plan:
                execution = await self._execute_plan({"action_plan": normalized_plan}, description)
                if execution.get("success"):
                    return {
                        "success": True,
                        "action": "council_planned",
                        "description": description,
                        "plan": normalized_plan,
                        "results": execution.get("results", []),
                    }
                return {
                    "success": False,
                    "action": "council_planned",
                    "error": execution.get("error") or "Council plan failed to execute.",
                    "description": description,
                    "plan": normalized_plan,
                }
        except Exception as exc:
            logger.warning("Council fallback for vague action failed: {}", exc)

        return {
            "success": False,
            "action": "unsupported",
            "error": (
                "I could not map this step to a real agent action yet. "
                "Try phrasing it as open/search/navigate/fill form/list/create/run/organize."
            ),
            "description": description,
        }

    def _cache_command_strategy(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        """Cache successful routing decisions."""

        if not result.get("success"):
            return

        normalized = self._normalize_command(command)
        if len(self.command_cache) >= self.command_cache_size:
            oldest_key = next(iter(self.command_cache))
            del self.command_cache[oldest_key]

        self.command_cache[normalized] = {
            "tier": strategy["tier"],
            "complexity": strategy["complexity"],
            "intent": strategy.get("intent"),
            "success": True,
        }

    def _normalize_command(self, command: str) -> str:
        """Normalize a command string for parsing and caching."""

        return " ".join(command.lower().strip().split())

    def _extract_process_filter(self, command: str) -> Optional[str]:
        """Extract a likely process filter from a direct command."""

        candidates = ["python", "chrome", "edge", "firefox", "code", "notepad", "ollama"]
        for candidate in candidates:
            if candidate in command:
                return candidate

        match = re.search(r"(?:for|named)\s+([a-z0-9._-]+)$", command)
        if match:
            return match.group(1)
        return None

    def _extract_known_path(self, command: str) -> str:
        """Map simple location keywords to concrete paths."""

        resolved = self._resolve_user_path(command)
        if resolved:
            return resolved

        home = Path.home()
        locations = {
            "desktop": home / "Desktop",
            "download": home / "Downloads",
            "downloads": home / "Downloads",
            "document": home / "Documents",
            "documents": home / "Documents",
        }

        for keyword, location in locations.items():
            if keyword in command.lower():
                return str(location)

        quoted_path = re.search(r'"([^"]+)"', command)
        if quoted_path:
            return quoted_path.group(1)

        return str(Path.cwd())

    def _resolve_user_path(self, value: str) -> Optional[str]:
        """Resolve quoted, absolute, home-relative, or plain filename paths."""

        if not value:
            return None

        text = value.strip().strip(".")
        quoted_path = re.search(r'"([^"]+)"|' + r"'([^']+)'", text)
        if quoted_path:
            text = quoted_path.group(1) or quoted_path.group(2)

        text = re.sub(r"^(?:the\s+)?(?:file|folder|directory)\s+", "", text, flags=re.IGNORECASE).strip()
        text = text.strip('"').strip("'")

        if re.match(r"^[a-zA-Z]:[\\/]", text) or text.startswith(("\\\\", "/", "~")):
            return str(Path(text).expanduser())

        if re.search(r"[\\/]", text):
            return str(Path(text).expanduser())

        if re.search(r"\.[A-Za-z0-9]{1,8}$", text):
            return str(Path.cwd() / text)

        return None

    def _extract_form_fields(self, command: str) -> Optional[Dict[str, str]]:
        """Extract field-value pairs from a form-filling command."""

        if not re.search(r"\b(fill|complete|stage|submit|send)\b.*\bform\b", command, flags=re.IGNORECASE):
            return None

        fields_section = re.split(r"\bwith\b", command, flags=re.IGNORECASE, maxsplit=1)
        if len(fields_section) < 2:
            return None

        field_text = re.sub(
            r"\b(?:and\s+confirm(?:\s+before)?\s+submitting|and\s+confirm|confirm\s+before\s+submitting|and\s+submit|please\s+submit|and\s+send|and\s+submit)\b.*$",
            "",
            fields_section[1],
            flags=re.IGNORECASE,
        )

        pairs = re.findall(r"([A-Za-z][A-Za-z0-9 _-]{1,30})\s*(?:=|:)\s*([^,;]+)", field_text)
        fields = {
            key.strip(): value.strip().strip(".")
            for key, value in pairs
            if key.strip() and value.strip()
        }
        if fields:
            return fields

        natural_pairs = re.findall(
            r"([A-Za-z][A-Za-z0-9 _-]{1,30})\s*(?:is|as)\s*([^,;]+)",
            fields_section[1],
        )
        fields = {
            key.strip(): value.strip().strip(".")
            for key, value in natural_pairs
            if key.strip() and value.strip()
        }
        return fields or None

    def _build_report_content(self, command: str, prior_results: List[Dict[str, Any]]) -> str:
        """Build a simple text report from prior subtask results."""

        lines = [f"ASC Report", f"Original task: {command}", ""]

        for index, result in enumerate(prior_results, start=1):
            lines.append(f"Step {index}: {result.get('subtask_description', 'Unnamed step')}")
            if result.get("url"):
                lines.append(f"URL: {result['url']}")
            if result.get("text"):
                lines.append("Captured text:")
                lines.append(result["text"][:1500])
            elif result.get("message"):
                lines.append(f"Message: {result['message']}")
            lines.append("")

        if len(lines) <= 3:
            lines.append("No detailed source text was captured.")

        return "\n".join(lines)

    def _learn_from_execution(self, command: str, plan: Dict[str, Any], result: Dict[str, Any]):
        """Store the execution outcome in episodic memory."""

        try:
            self.memory.remember_episode(
                task=command,
                action=json.dumps(plan, default=str)[:800],
                result=f"Success: {result.get('success')}, Steps: {result.get('steps_completed', 0)}",
                success=result.get("success", False),
                learned=(
                    f"Tier: {result.get('tier', 'unknown')}, "
                    f"Completed: {result.get('steps_completed', 0)}/{result.get('steps_total', 1)}"
                ),
            )
        except Exception as exc:
            logger.warning("Episodic memory write failed without blocking command: {}", str(exc))

    def get_status(self) -> Dict[str, Any]:
        """Get overall system status."""

        return {
            "system": "Autonomous System Controller v1.0",
            "status": "running" if self.running else "idle",
            "components": {
                "council": "active",
                "chairman": "active",
                "memory": "active",
                "agents": list(self.agents.keys()),
            },
            "tier_stats": self.tier_stats,
            "tools": self.get_tool_manifest(),
            "voice": self._get_voice_service_health() if self.voice_enabled else {"available": False, "enabled": False},
            "learning_stats": self.agents["learning"].get_learning_stats(),
            "adaptive_learning": self.agents["learning"].get_adaptive_summary()
            if hasattr(self.agents["learning"], "get_adaptive_summary") else {},
            "memory_stats": self.memory.get_memory_stats(),
            "council_stats": self.council.get_stats(),
        }

    async def run_interactive(self):
        """Run ASC in interactive mode with Jarvis-like presentation."""

        self.running = True

        print("\n" + "=" * 60)
        print("AUTONOMOUS SYSTEM CONTROLLER")
        print("=" * 60)
        print("\nGreetings. I am ASC, your advanced local AI assistant.")
        print("I'm here to help you with tasks, answer questions, and assist with your work.")
        
        if self.voice_enabled and self.voice_service_available:
            print("\nVoice control is active. Type 'voice' to speak a command, or type your command normally.")
        elif self.voice_enabled:
            print("\nVoice support is configured, but the local voice server is currently offline.")
            print("Type 'start voice server' to enable voice interaction.")
        else:
            print("\nI'm ready to assist through text commands. Type 'help' for what I can do.")
        
        print("\nHow may I assist you today?\n")

        while self.running:
            try:
                command = input("You: ").strip()

                if not command:
                    continue

                if self.voice_enabled and command.lower() == "voice":
                    command = self._listen_for_voice_command()
                    if not command:
                        continue

                if command.lower() in ["exit", "quit", "bye", "goodbye", "see you"]:
                    print("\nIt was a pleasure assisting you today. Goodbye!")
                    self.memory.end_session()
                    self.running = False
                    break

                if command.lower() in ["help", "what can you do", "capabilities"]:
                    self._display_capabilities()
                    continue

                if command.lower() == "status":
                    print(json.dumps(self.get_status(), indent=2))
                    continue

                result = await self.process_command(command)
                self._display_result(result)
                if self.voice_enabled:
                    self._speak_result(result)

            except KeyboardInterrupt:
                print("\n\nUnderstood. I'll conclude our session now. Take care!")
                self.memory.end_session()
                self.running = False
                break

            except Exception as exc:
                logger.error("Error in interactive mode: {}", str(exc))
                print(f"\nI encountered an issue: {str(exc)}")
                print("Let me try to help you with something else.\n")

    def _display_capabilities(self):
        """Display available capabilities in a Jarvis-like format."""
        print("\n" + "=" * 60)
        print("CAPABILITIES")
        print("=" * 60)
        print("\nI can assist you with:\n")
        print("Conversation & Intelligence:")
        print("  - Natural conversation and Q&A")
        print("  - Context-aware responses")
        print("  - Learning from your preferences")
        print("\nSystem Control:")
        print("  - Open and manage applications")
        print("  - Execute safe system commands")
        print("  - Monitor system resources")
        print("  - Power management (with confirmation)")
        print("\nFile Management:")
        print("  - Create, organize, and search files")
        print("  - Backup and duplicate detection")
        print("  - Disk usage analysis")
        print("\nWeb Automation:")
        print("  - Navigate and search websites")
        print("  - Intelligent form filling")
        print("  - Browser automation")
        print("\nVoice Interaction:")
        print("  - Voice commands (when server is running)")
        print("  - Text-to-speech responses")
        print("\nAdvanced Features:")
        print("  - Multi-step task planning")
        print("  - Adaptive learning from your patterns")
        print("  - Workflow automation")
        print("  - Proactive suggestions")
        print("\n" + "=" * 60 + "\n")

    def _display_result(self, result: Dict[str, Any]):
        """Render command results with Jarvis-like sophistication."""

        if result.get("tier") == "conversation" or result.get("mode") == "chat":
            response = result.get("response")
            if response:
                print(f"\nASC: {response}\n")
            elif result.get("success"):
                print("\nASC: I'm ready to assist you. What would you like me to help with?\n")
            else:
                print(f"\nASC: I'm having some difficulty with that request. {result.get('error', '')}\n")
            return

        if result.get("needs_confirmation"):
            print(f"\nASC: {result.get('question', 'This action requires your confirmation before I proceed.')}")
            for step_result in result.get("results", []):
                if step_result.get("warning"):
                    print(f"Note: {step_result['warning']}")
                if step_result.get("command"):
                    print(f"Command: {step_result['command']}")
            print()
            return

        if result.get("needs_clarification"):
            print(f"\nASC: {result.get('question', 'I need to clarify something to help you better.')}")
            suggestions = result.get("suggestions") or []
            if suggestions:
                print("Suggestions:")
                for suggestion in suggestions[:5]:
                    print(f"  - {suggestion}")
            print()
            return

        if result.get("success"):
            # Jarvis-like success response
            tier = result.get("tier", "unknown")
            steps_completed = result.get("steps_completed", 1)
            steps_total = result.get("steps_total", 1)
            
            if tier == "direct":
                print(f"\nExcellent. Task completed successfully via direct execution.")
            elif tier == "autonomous":
                print(f"\nI've successfully handled that autonomously using my planning capabilities.")
            elif tier == "sequential":
                print(f"\nExcellent. I've completed {steps_completed} of {steps_total} steps in that sequence.")
            else:
                print(f"\nSuccess. I've processed your request through the {tier} tier.")

            # Detailed results with Jarvis-like explanations
            for step_result in result.get("results", []):
                self._display_step_result(step_result)

            print()
        else:
            # Jarvis-like error handling
            error = result.get("error", "Unknown error")
            recovery = result.get("recovery_suggestion", "")
            
            print(f"\nI encountered an issue: {error}")
            if recovery:
                print(f"\n{recovery}")
            print("\nWould you like me to try a different approach, or would you prefer to work on something else?")
            print()

    def _display_step_result(self, step_result: Dict[str, Any]):
        """Display individual step results with informative explanations."""
        
        if "processes" in step_result:
            print("\nSystem Processes:")
            for process in step_result["processes"][:10]:
                print(f"  - {process['name']} (PID: {process['pid']}, CPU: {process['cpu']}%)")

        elif "files" in step_result:
            print(f"\nFiles Found ({len(step_result['files'])} total):")
            for file_info in step_result["files"][:20]:
                size = file_info.get("size", 0)
                if size > 1024 * 1024:
                    size_text = f"{round(size / (1024 * 1024), 2)}MB"
                else:
                    size_text = f"{round(size / 1024, 1)}KB"
                print(f"  - {file_info['name']} ({size_text})")

        elif "cpu" in step_result and "memory" in step_result:
            print("\nSystem Status:")
            print(f"  CPU: {step_result['cpu']['percent']}% ({step_result['cpu']['cores']} cores)")
            print(f"  RAM: {step_result['memory']['used_percent']}% used ({step_result['memory']['available_gb']}GB free)")
            print(f"  Disk: {step_result['disk']['used_percent']}% used ({step_result['disk']['free_gb']}GB free)")

        elif "fields_filled" in step_result:
            print("\nForm Fields Processed:")
            for field in step_result["fields_filled"]:
                confidence = field.get("confidence", 0.0)
                print(f"  - {field['name']} (confidence: {confidence:.2f})")

        elif "command_history" in step_result:
            print("\nRecent Commands:")
            for item in step_result["command_history"]:
                status = "✓" if item['result'].get('success') else "✗"
                print(f"  {status} {item['command']}")

        elif "feedback_recorded" in step_result:
            feedback = step_result["feedback_recorded"]
            print(f"\nFeedback Noted: {feedback.get('sentiment', 'neutral')} - {feedback.get('feedback', '')}")

        elif "preference_saved" in step_result:
            preference = step_result["preference_saved"]
            print(f"\nPreference Learned: {preference['key']} = {preference['value']}")

        elif "preference_rejected" in step_result:
            preference = step_result["preference_rejected"]
            value = f" = {preference['value']}" if preference.get('value') is not None else ""
            print(f"\nPreference Noted: {preference['key']}{value}")

        elif "preferences" in step_result:
            print("\nYour Current Preferences:")
            for key, data in step_result["preferences"].items():
                value = data.get("value") if isinstance(data, dict) else data
                print(f"  - {key}: {value}")

        elif "workflow_patterns" in step_result:
            print("\nLearned Workflow Patterns:")
            for pattern in step_result["workflow_patterns"]:
                print(f"  - {pattern['signature']} (used {pattern['count']} time(s))")

        elif "adaptive_learning" in step_result:
            adaptive = step_result["adaptive_learning"]
            summary = adaptive.get("summary", {})
            print("\nAdaptive Learning Status:")
            print(f"  Examples processed: {summary.get('examples', 0)}")
            print(f"  Workflow clusters: {summary.get('clusters', 0)}")
            print(f"  Accuracy: {summary.get('recommendation_accuracy', 0.0):.2%}")

        elif "phase5_learning" in step_result:
            phase5 = step_result["phase5_learning"]
            summary = phase5.get("summary", {})
            print("\nAdvanced Learning Status:")
            print(f"  Neural model trained: {summary.get('neural_trained', False)}")
            print(f"  Model accuracy: {summary.get('neural_accuracy', 0.0):.2%}")
            print(f"  Confidence level: {summary.get('confidence', 0.0):.2f}")

        if step_result.get("warning"):
            print(f"  Note: {step_result['warning']}")

        if step_result.get("message"):
            print(f"  {step_result['message']}")

        if step_result.get("url"):
            print(f"  Opened: {step_result['url']}")

    def free_memory(self):
        """Model unloading is already handled with keep_alive=0."""

        logger.info("Model unloading is handled through keep_alive=0")


async def main():
    """Main entry point."""

    asc = AutonomousSystemController()
    await asc.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
