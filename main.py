"""
VEGA - Autonomous System Controller - Main Entry Point
Implements direct execution, learning-assisted routing, intelligent form
handling, and decomposed multi-step task execution.
"""

import asyncio
import json
from collections import deque
import os
import re
import struct
import subprocess
import threading
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pyaudio
import requests
from loguru import logger

if sys.platform == "win32":
    import winsound

from agents.file_agent import FileAgent
from agents.conversation_agent import ConversationAgent
from agents.system_agent import SystemAgent
from agents.vision_agent import VisionAgent
from agents.web_agent import WebAgent
from agents.business_agent import BusinessAgent
from agents.business_process_automation import BusinessProcessAutomation
from agents.enterprise_security import EnterpriseSecurity
from agents.advanced_analytics import AdvancedAnalytics
from core.chairman import Chairman
from core.council import LLMCouncil
from core.autonomy import AutonomyEngine
from core.memory import MemorySystem
from core.remote_queue import RemoteQueue
from core.intent_router import LLMIntentRouter
from core.task_decomposer import TaskDecomposer
from core.tool_registry import ToolRegistry, ToolSpec


# Resolved from this file, never the working directory: `python
# path/to/main.py --tasks` from elsewhere previously died looking for
# ./config/settings.json relative to wherever it was invoked (audit M-5).
DEFAULT_CONFIG_PATH = str(Path(__file__).resolve().parent / "config" / "settings.json")

# Force UTF-8 on both streams at import time, before anything can print.
# When stdout is not a console - redirected to a log file, piped, or running
# as a scheduled task - Windows falls back to cp1252 and any non-ASCII
# character raises UnicodeEncodeError. That killed the reminder loop mid-fire
# so reminders were never delivered and retried forever (audit M-2). This ran
# inside _setup_logging before, which the --tasks/--journal CLI paths and
# stderr never reached.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

from core.config import load_config


class _LazyAgents:
    """Dict-like agent registry that constructs agents on first access.

    Twelve learning/extras systems are rarely needed in a typical session;
    building them eagerly cost seconds of boot time and tens of MB of RAM.
    Frequently used agents (conversation/learning/system) are passed in
    pre-built; everything else constructs on demand and is cached.
    """

    def __init__(self, config_path: str, prebuilt: Dict[str, Any]):
        self._config_path = config_path
        self._cache: Dict[str, Any] = dict(prebuilt)

    def _build(self, key: str):
        cfg = self._config_path
        if key == "vision":
            return VisionAgent(cfg)
        if key == "file":
            return FileAgent(cfg)
        if key == "business":
            return BusinessAgent(cfg)
        if key == "web":
            return WebAgent(
                config_path=cfg,
                system_agent=self["system"],
                vision_agent=self["vision"],
                learning_agent=self["learning"],
            )
        if key == "learning":
            # Imported here, not at module scope: the chain behind this
            # ends at torch, which costs seconds to import.
            from agents.learning_agent import LearningAgent
            return LearningAgent(cfg)
        if key == "advanced_neural":
            # torch AND sklearn. Very few sessions ever reach this.
            from learning.advanced_neural_network import AdvancedNeuralNetwork
            return AdvancedNeuralNetwork(cfg)
        builders = {
            "business_process": BusinessProcessAutomation,
            "security": EnterpriseSecurity,
            "analytics": AdvancedAnalytics,
        }
        if key in builders:
            return builders[key](cfg)
        raise KeyError(f"Unknown agent: {key}")

    def __getitem__(self, key: str):
        if key not in self._cache:
            self._cache[key] = self._build(key)
            logger.info("Lazy-loaded agent: {}", key)
        return self._cache[key]

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        return True

    def keys(self):
        return list(self._cache.keys())


# Openers that make a sentence a question about something rather than an
# instruction to do something. Used to keep the intent classifier away from
# conversational turns: it is a nearest-centroid model, so it always has a
# nearest centroid, and "where did you put it" is closer to stock_api than
# to nothing at all.
_QUESTION_OPENER = re.compile(
    r"^\s*(?:where|what|which|who|whom|whose|when|why|how|did|do|does|"
    r"have|has|had|are|is|was|were|can|could|would|should|will|shall)\b",
    re.IGNORECASE,
)


class AutonomousSystemController:
    """Main VEGA controller and execution orchestrator."""

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

    SEARCH_ENGINE_TEMPLATES = {
        "google": "https://www.google.com/search?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
        "duckduckgo": "https://duckduckgo.com/?q={query}",
        "ddg": "https://duckduckgo.com/?q={query}",
    }

    def __init__(self, config_path: str = None):
        config_path = config_path or DEFAULT_CONFIG_PATH
        self._setup_logging(config_path)

        logger.info("=" * 60)
        logger.info("AUTONOMOUS SYSTEM CONTROLLER v1.0")
        logger.info("=" * 60)

        self.config = load_config(config_path)
        logger.info("Initializing core systems...")
        self.council = LLMCouncil(config_path)
        self.chairman = Chairman(config_path)
        self.memory = MemorySystem(config_path)
        self.task_decomposer = TaskDecomposer()
        self.autonomy = AutonomyEngine(self.task_decomposer, self.get_tool_manifest)
        self.intent_router = LLMIntentRouter(self.config, self.get_tool_manifest)
        self._last_execution_summary = ""
        # What the system has actually DONE recently, as opposed to what it
        # has said. The conversational model needs this to answer "where did
        # you save it" without inventing an answer.
        self._recent_actions: "deque[Dict[str, Any]]" = deque(maxlen=8)

        logger.info("Initializing agents...")
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

        # "learning" is deliberately NOT seeded here - building it eagerly
        # was what made the lazy map pointless for the expensive agent.
        self.agents = _LazyAgents(config_path, {
            "conversation": conversation_agent,
            "system": system_agent,
        })

        execution_config = self.config.get("execution", {})
        self.command_cache: Dict[str, Dict[str, Any]] = {}
        self.command_cache_size = int(execution_config.get("command_cache_size", 100))
        self.execution_pause_seconds = float(execution_config.get("direct_pause_seconds", 0.3))
        self.decompose_complex_tasks = bool(execution_config.get("decompose_complex_tasks", True))
        self.tier_stats = {"direct": 0, "single_model": 0, "sequential": 0}
        # Per-intent and per-agent outcome counters (item 4/7 of the
        # autonomy pass): visibility into which routes and which agents are
        # actually reliable, which is what a real "system improving with
        # usage" claim needs to be checked against instead of asserted.
        self.intent_stats: Dict[str, Dict[str, int]] = {}
        self.agent_stats: Dict[str, Dict[str, int]] = {}
        # Simple hourly rate limiter for actions that can run without a
        # human watching in real time: remote/email-triggered commands and
        # outward-facing actions (send_email). A ring buffer of timestamps,
        # not a persisted budget - resets naturally as old entries age out.
        self._unattended_action_timestamps: List[float] = []
        self.unattended_action_hourly_limit = int(
            execution_config.get("unattended_action_hourly_limit", 30)
        )
        self.tool_registry = self._build_tool_registry()

        audio_config = self.config.get("audio", {})
        self.voice_enabled = bool(audio_config.get("voice_enabled", False))
        self.voice_service_url = audio_config.get("voice_service_url", "http://localhost:5000")
        self.wake_word = audio_config.get("wake_word", "hey assistant")
        self.stt_model = audio_config.get("stt_model", "whisper")
        self.tts_engine = audio_config.get("tts_engine", "pyttsx3")
        self.voice_service_available = self._check_voice_service() if self.voice_enabled else False
        # True while the interactive loop reads input from the microphone.
        self._voice_mode = False
        
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
        # Serializes process_command calls across the interactive prompt and
        # the background remote-queue worker. Agents (WebAgent.last_url,
        # BrowserDriver.page, SystemAgent.command_history, WebAgent's
        # _pending_confirmations, ...) hold single-instance state with no
        # locking of their own - they were built assuming one command runs
        # at a time. Freeing input() off the event loop (below) makes true
        # concurrent execution possible for the first time, so this lock
        # preserves that original one-at-a-time assumption instead of
        # silently introducing races.
        self._command_lock = asyncio.Lock()
        # Set only while re-running a command the user explicitly approved
        # after the automated safety review was unavailable (_chairman_gate).
        self._critical_gate_bypass: Optional[str] = None

        logger.success("All systems initialized")
        self._warm_up_lazy_agents()
        logger.info("=" * 60)

    def _setup_logging(self, config_path: str = None):
        """Configure console and file logging.

        Takes the path rather than reading self.config: this runs before
        the config attribute exists, and load_config is cached, so
        reading it here costs nothing.
        """

        logger.remove()

        # The console belongs to the user, not to us. Internal progress -
        # which agent was constructed, which episode was recorded - is a
        # fact about our implementation and not about their request, and
        # printing it buried the one line they were waiting for.
        #
        # Everything still goes to the file at DEBUG, which is where it was
        # always the right place for it. --verbose puts it back on screen.
        try:
            cfg = load_config(config_path or DEFAULT_CONFIG_PATH)
        except Exception:
            cfg = {}
        console_level = str(
            (cfg.get("system") or {}).get("console_log_level", "WARNING")
        ).upper()
        if "--verbose" in sys.argv or "--debug" in sys.argv:
            console_level = "DEBUG"

        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
            level=console_level,
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
    def _pick_input_device(pa: "pyaudio.PyAudio") -> Optional[int]:
        """Choose a real microphone device, avoiding virtual/loopback inputs.

        Windows machines expose many capture endpoints (noise-cancelling VACs,
        stereo mix loops); the system default may be silent. Prefer devices
        whose name looks like a physical microphone.
        """
        configured = None
        try:
            audio_cfg = json.load(open("config/settings.json", encoding="utf-8")).get("audio", {})
            configured = audio_cfg.get("input_device_index")
        except Exception:
            pass
        if isinstance(configured, int):
            return configured

        best_idx: Optional[int] = None
        best_score = -1
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) <= 0:
                continue
            name = (info.get("name") or "").lower()
            if any(bad in name for bad in ("stereo mix", "virtual", "speaker", "loopback")):
                continue
            score = 1
            if "microphone" in name or "mic array" in name:
                score += 5
            if "noise" in name:
                score -= 2  # ASUS AI noise-cancelling VACs often route silence
            if score > best_score:
                best_score = score
                best_idx = i
        return best_idx

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
            device_index = self._pick_input_device(pa)
            if device_index is not None:
                logger.info("Voice: using input device #{} ({})", device_index, pa.get_device_info_by_index(device_index).get("name"))
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024,
            )
            print("Listening (speak, then pause)...")
            frames = []
            speech_detected = False
            sample_width = pa.get_sample_size(pyaudio.paInt16)
            try:
                frame_ms = 1000.0 * 1024 / rate  # ~64ms per 1024-sample frame
                silence_frame_limit = max(1, int(silence_ms / frame_ms))

                # The stream returns silence for the first frames after
                # open(). Measuring those was the whole problem: the noise
                # floor came out near zero, so the threshold fell back to a
                # constant that sat BELOW this room's ambient peaks.
                warmup_frames = 8            # ~0.5s of stream spin-up
                calibration_frames = 12      # ~0.75s of actual room

                for _ in range(warmup_frames):
                    stream.read(1024, exception_on_overflow=False)

                ambient = []
                for _ in range(calibration_frames):
                    ambient.append(self._rms_energy(
                        stream.read(1024, exception_on_overflow=False)))
                ambient.sort()

                # Median, not max - one keyboard click must not poison the
                # threshold for the whole utterance.
                noise_floor = ambient[len(ambient) // 2]
                ambient_peak = ambient[-1]

                # Clear the room's own peaks, and require a real margin over
                # its typical level. The 300 floor stays only as a guard for
                # a genuinely silent input.
                threshold = max(noise_floor * 3.0, ambient_peak * 1.4, 300.0)
                logger.info(
                    "Voice: ambient median={:.0f} peak={:.0f} -> threshold={:.0f}",
                    noise_floor, ambient_peak, threshold,
                )

                # Hysteresis: one loud frame is a door slam, not speech.
                loud_run = 0
                frames_to_start = 2
                silent_frames_after_speech = 0
                min_frames_before_stop = int(1000 / frame_ms)  # ~1s minimum

                total_frames = int(rate / 1024 * duration)
                for index in range(total_frames):
                    data = stream.read(1024, exception_on_overflow=False)
                    frames.append(data)

                    if self._rms_energy(data) > threshold:
                        loud_run += 1
                        if loud_run >= frames_to_start:
                            speech_detected = True
                        silent_frames_after_speech = 0
                    else:
                        loud_run = 0
                        if speech_detected and index >= min_frames_before_stop:
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

            if not speech_detected:
                # Transcribing this produces "[BLANK_AUDIO]" or an invented
                # sentence. Saying nothing was heard is the honest answer.
                logger.info("Voice: no speech detected above the noise floor")
                return None

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            with wave.open(tmp_file.name, "wb") as wf:
                wf.setnchannels(channels)
                # Captured BEFORE pa.terminate() above - this used to query a
                # PyAudio instance that had already been torn down.
                wf.setsampwidth(sample_width)
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

    _tts_engine = None

    def _speak_text(self, text: str):
        """Hand text to the speech queue. Returns immediately.

        The actual synthesis happens on core.speech's dedicated thread, so
        a slow voice server or a stuck audio device can no longer hold up
        the interactive prompt - which is what it used to do.
        """
        if not self.voice_enabled:
            return
        from core import speech
        speech.configure(self._synthesise_speech)
        speech.say(text)

    def _synthesise_speech(self, text: str):
        """Actually produce sound. Only ever called on the speech thread.

        Primary: Windows SAPI via pyttsx3 - instant, never truncates.
        Fallback: piper TTS through the voice server (higher quality,
        slower, requires local-server running).
        """
        if not self.voice_enabled:
            return

        # Piper first when it is available and the user wants the natural
        # voice. SAPI was first only because speech used to block the
        # prompt and SAPI is instant; now that speech runs on its own
        # thread, piper's extra beat costs nothing anyone is waiting on.
        prefer_natural = bool(
            (self.config.get("audio") or {}).get("prefer_natural_voice", True)
        )
        if prefer_natural and self.voice_service_available:
            if self._speak_via_piper(text):
                return
            logger.debug("Piper unavailable for this utterance, using SAPI.")

        # --- Tier 1: pyttsx3 (offline SAPI) ---
        try:
            import pyttsx3

            if AutonomousSystemController._tts_engine is None:
                engine = pyttsx3.init()
                engine.setProperty("rate", 170)
                AutonomousSystemController._tts_engine = engine
            engine = AutonomousSystemController._tts_engine
            engine.say(text)
            engine.runAndWait()
            return
        except Exception as exc:
            # Debug, not warning: falling back to piper is the normal path on
            # this machine, and a startup WARNING made a working system
            # look broken before the user had typed anything.
            logger.debug("SAPI speech unavailable ({}), using piper.", str(exc)[:80])

        # --- Tier 2: piper via voice server ---
        if not self.voice_service_available:
            logger.warning("No speech engine available.")
            return
        self._speak_via_piper(text)

    def _speak_via_piper(self, text: str) -> bool:
        """Speak through the local piper server. True if sound was produced.

        Only ever called on the speech thread, so the network round trip
        and the playback cannot delay anything the user is waiting for.
        """
        try:
            response = requests.post(
                f"{self.voice_service_url}/speak",
                json={"text": text},
                # Was 60. Nothing about one spoken sentence justifies
                # waiting a minute, and this now runs on the speech thread
                # where a long wait silently delays later utterances.
                timeout=15,
            )
            if response.status_code != 200:
                logger.warning("Voice server speak failed: %s", response.status_code)
                return False

            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_file.write(response.content)
            tmp_file.close()

            if sys.platform == "win32":
                winsound.PlaySound(tmp_file.name, winsound.SND_FILENAME)
            else:
                logger.warning("Voice playback only supports Windows via winsound.")
                return False

            os.unlink(tmp_file.name)
            return True
        except Exception as exc:
            logger.debug("Piper playback failed: {}", str(exc))
            return False

    def _listen_for_voice_command(self) -> Optional[str]:
        """Record and transcribe a voice command.

        Honours audio.stt_model:
          "auto"   - cloud first, local whisper as fallback (default)
          "google" - cloud only
          "whisper"- local whisper only, never leaves the machine

        The setting was previously read into self.stt_model and never used,
        so a config asking for local whisper still sent audio to Google. It
        also made the local pipeline unreachable whenever the network was
        up, which is why a broken local path could go unnoticed for so long.
        """
        if not self.voice_enabled:
            return None

        preference = str(getattr(self, "stt_model", "auto") or "auto").lower()

        # --- Tier 1: cloud STT (SpeechRecognition + Google) ---
        try:
            if preference == "whisper":
                raise ImportError("stt_model=whisper: skipping cloud STT")

            import speech_recognition as sr

            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                print("Listening (cloud STT)...")
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                audio = recognizer.listen(source, timeout=8, phrase_time_limit=10)
            try:
                text = recognizer.recognize_google(audio).strip()
                if text:
                    print(f"You said: {text}")
                    return text
            except sr.UnknownValueError:
                print("Cloud STT could not understand audio - trying local whisper...")
            except Exception as exc:
                logger.warning("Cloud STT unavailable ({}), using local whisper.", str(exc)[:80])
        except ImportError:
            pass

        if preference == "google":
            print("Cloud STT failed and stt_model=google, so not falling back to whisper.")
            return None

        # --- Tier 2: local whisper.cpp pipeline ---
        if not self.voice_service_available:
            logger.warning("Voice service is not available at {}", self.voice_service_url)
            print("Voice service is not available. Start local-server/server.py first.")
            return None

        audio_path = self._record_audio()
        if not audio_path:
            # Not necessarily a failure: the recorder also returns None when
            # nothing crossed the noise floor, which is the ordinary "you
            # didn't say anything" case. The caller's silence-streak handling
            # takes it from here.
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
        """Speak the actual response content, not a generic summary."""
        if not self.voice_enabled or not self.voice_service_available:
            return

        response = str(result.get("response") or "").strip()
        if response:
            message = response
        elif result.get("success"):
            steps = [
                str(
                    s.get("subtask_description")
                    or s.get("message")
                    or s.get("action")
                    or ""
                ).strip()
                for s in (result.get("results") or [])
                if isinstance(s, dict)
            ]
            parts = [p for p in steps if p][:3]
            message = "Done. " + "; ".join(parts) if parts else "Task completed successfully."
        else:
            message = f"Sorry, that failed. {str(result.get('error') or 'Unknown error')[:140]}"

        message = self._strip_unspeakable(message)
        if len(message) > 300:
            message = message[:297] + "..."

        if not message.strip():
            return
        self._speak_text(message)

    # Things that are unbearable read aloud: URLs, file paths, long hashes.
    _URL_RE = re.compile(r"https?://\S+|www\.\S+")
    _PATH_RE = re.compile(r"[A-Za-z]:\\[^\s,;]+|(?:/[\w.-]+){2,}")
    _HASH_RE = re.compile(r"\b[0-9a-f]{16,}\b", re.IGNORECASE)
    _QUERY_RE = re.compile(r"\?\S*=\S*")

    @classmethod
    def _strip_unspeakable(cls, text: str) -> str:
        """Replace things no one wants dictated to them.

        A web search made VEGA read the full result URL out loud, query
        string and all - "h-t-t-p-s colon slash slash w-w-w dot google dot
        com slash search question mark q equals..." - which is unusable.
        The link is still printed on screen; it just is not spoken.
        """
        if not text:
            return ""
        spoken = cls._URL_RE.sub("the link on screen", text)
        spoken = cls._PATH_RE.sub("the path on screen", spoken)
        spoken = cls._QUERY_RE.sub("", spoken)
        spoken = cls._HASH_RE.sub("an identifier", spoken)
        return re.sub(r"\s{2,}", " ", spoken).strip()

    async def process_command(self, command: str) -> Dict[str, Any]:
        """Process a natural-language command through VEGA with graceful error handling."""
        from core import progress

        progress.start("Thinking")
        try:
            return await self._process_command_inner(command)
        finally:
            # Always, on every path. A status line left spinning after an
            # exception is worse than none at all.
            progress.stop()

    async def _process_command_inner(self, command: str) -> Dict[str, Any]:
        from core import progress

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

            # Say what is actually about to happen, in the user's terms.
            progress.update({
                "direct": "Working on it",
                "brain": "Working out what you mean",
                "conversation": "Thinking",
                "autonomous": "Planning the steps",
                "sequential": "Working through the steps",
                "react": "Working through the steps",
                "clarify": "Thinking",
            }.get(tier, "Working on it"))

            critical_rejection = None
            # Every tier, not just direct/brain. The benchmark caught
            # "delete the entire windows folder" and "format C:" being
            # assessed as CRITICAL and then routed to the sequential tier,
            # which executed them without the Chairman ever seeing the plan
            # ("Excellent. I've completed 1 of 1 steps in that sequence.").
            # Which tier happens to claim a command is an internal routing
            # detail; it must not decide whether the safety review runs.
            # conversation is excluded because it performs no actions.
            if complexity == "critical" and tier != "conversation":
                gate_repr = {
                    "tier": tier,
                    "intent": strategy.get("intent"),
                    "plan": strategy.get("plan"),
                    "params": strategy.get("params"),
                }
                critical_rejection = await self._chairman_gate(command, gate_repr)

            if critical_rejection is not None:
                result = critical_rejection
                result["tier"] = tier

            elif tier == "brain":
                self.tier_stats["brain"] = self.tier_stats.get("brain", 0) + 1
                plan_steps = strategy.get("plan")
                results = []
                if plan_steps:
                    for idx, step_def in enumerate(plan_steps, start=1):
                        action_name = str(step_def.get("action", "")).strip()
                        print(f"[Brain] Step {idx}/{len(plan_steps)}: {action_name}")
                        try:
                            step_res = await self._route_action(
                                action_name, step_def.get("params") or {}, command
                            )
                        except Exception as exc:
                            step_res = {"success": False, "error": str(exc)}
                        results.append(step_res)
                        if not step_res.get("success", True):
                            break
                    ok_count = sum(
                        1 for s in results if isinstance(s, dict) and s.get("success")
                    )
                    success = bool(results) and ok_count == len(results)
                    response_text = "; ".join(
                        p
                        for p in (
                            str(s.get("subtask_description") or s.get("message") or s.get("action") or "")
                            for s in results
                            if isinstance(s, dict)
                        )
                        if p
                    )
                    result = {
                        "tier": "brain",
                        "success": success,
                        "results": results,
                        "steps_completed": ok_count,
                        "steps_total": len(results),
                        "response": response_text or ("Plan completed." if success else "Plan failed."),
                    }
                    if not success and isinstance(results[-1], dict) and results[-1].get("error"):
                        result["error"] = str(results[-1]["error"])
                else:
                    intent = strategy.get("intent") or {}
                    step = await self._route_action(
                        intent.get("type", ""), strategy.get("params") or {}, command
                    )
                    result = {
                        "tier": "brain",
                        "success": bool(step.get("success")),
                        "results": [step],
                        "response": str(
                            step.get("message")
                            or step.get("subtask_description")
                            or ("Done." if step.get("success") else "")
                        ),
                    }
                    if not step.get("success") and step.get("error"):
                        result["error"] = str(step.get("error"))

            elif tier == "clarify":
                question = strategy.get("question", "Could you rephrase that?")
                result = {
                    "success": True,
                    "tier": "clarify",
                    "needs_clarification": True,
                    "question": question,
                    "response": question,
                }

            elif tier == "conversation":
                result = await self.agents["conversation"].chat(
                    command,
                    context={
                        "tools": self.get_tool_manifest(),
                        # What was actually done, so questions about it are
                        # answered from a record rather than invented.
                        "recent_actions": self._recent_actions_context(),
                    },
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
                autonomous_rejection = (
                    await self._chairman_gate(command, plan) if complexity == "critical" else None
                )
                if autonomous_rejection is not None:
                    result = autonomous_rejection
                    result["tier"] = "autonomous"
                else:
                    if self._should_use_council_fallback(plan, command) and hasattr(self, "council"):
                        try:
                            council_plan = await self.council.decide(command, complexity)
                            if not council_plan.get("error"):
                                plan = council_plan
                        except Exception as exc:
                            logger.warning("Council fallback for autonomy failed: {}", exc)
                    result = await self._execute_autonomous_decision(plan, command)
                    result["tier"] = "autonomous"

                    # The planner keeps everything it is good at - asking
                    # when a target is missing, honouring preferences,
                    # deferring to the council when a form is ambiguous.
                    # When it simply could not do the thing, the reasoning
                    # loop gets a second attempt, because carrying one
                    # step's result into the next is what it does and what
                    # the planner does not.
                    if (not result.get("success")
                            and not result.get("needs_clarification")
                            and self._react_loop_enabled()):
                        retry = await self._run_react_loop(command)
                        if retry.get("success"):
                            retry["recovered_by"] = "react_loop"
                            result = retry

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
                ):
                    # Deterministic clause-splitting always gets first chance on
                    # multi-action commands; autonomy/council remain fallbacks.
                    # (Previously an autonomy veto skipped this and threw
                    # every complex task into LLM planning.)
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

            # Remember what we just did so follow-ups ("email that to raj")
            # can resolve pronouns against the last result.
            self._last_execution_summary = self._summarize_result(result)
            self._record_action(command, result)

            # Outcome verification: one cheap follow-up call checking whether
            # the result actually satisfies what was asked, not just whether
            # every step returned success=True.
            #
            # ADVISORY ONLY - it reports, it never re-executes. The previous
            # version responded to a flagged mismatch by asking the council
            # for a fresh plan and running it, which re-ran the side effects
            # the first run had already performed (verified: it sent the same
            # email twice). Automatic recovery needs idempotent actions, and
            # the action layer has no idempotency keys - so the honest
            # behaviour is to tell the user what looks wrong and let them
            # decide, rather than silently doing it again.
            #
            # Skipped for direct/conversation/clarify tiers: those are cheap
            # and deterministic, and paying a model call to check them is
            # what made trivial commands slow.
            # Only worth paying a model call where a mismatch is actually
            # possible: multi-step work can silently drop part of a request
            # (the case this exists to catch), whereas a single action that
            # succeeded either did the one thing or didn't. Verifying every
            # single-step result cost ~15s to confirm the obvious.
            steps_total = int(result.get("steps_total") or 0)
            worth_verifying = steps_total > 1 or bool(result.get("decomposition"))

            if result.get("success") and worth_verifying and tier in {"brain", "autonomous", "sequential", "single_model"}:
                try:
                    verification = await self.council.verify_outcome(command, self._last_execution_summary)
                except Exception as exc:
                    logger.warning("Outcome verification call failed: {}", str(exc))
                    verification = None

                if verification:
                    result["verification"] = verification
                    if (
                        verification.get("verified")
                        and not verification.get("satisfied")
                        and verification.get("confidence", 0.0) >= 0.5
                    ):
                        reason = str(verification.get("reason") or "").strip()
                        logger.warning("Outcome verification flagged a possible mismatch: {}", reason)
                        # Surface it honestly instead of re-running: the work
                        # DID happen, it just may not have been what was asked.
                        result["verification_warning"] = (
                            f"I completed that, but it may not fully match what you asked: {reason}"
                            if reason else
                            "I completed that, but it may not fully match what you asked."
                        )
                        # A detected mismatch is not a success. Announcing
                        # "Task completed successfully" and then recording
                        # `-> success` taught the learner that searching the
                        # web is a correct response to "create a document",
                        # so it would confidently repeat the mistake. The
                        # actions still ran and are still reported; what
                        # changes is that we stop calling it a win.
                        result["outcome_mismatch"] = True

            self._cache_command_strategy(command, strategy, result)
            self._record_learning(command, strategy, result)
            self._learn_from_execution(command, plan or strategy, result)
            self._journal(command, strategy, result)
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
            self._journal(command, strategy, result)
            return result

    def _journal(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        """Append a human-readable record of one executed command to the
        execution_journal table (data/episodic_memory.db) so the supervisor
        can review activity without reading raw logs. Journaling must never
        break execution. Previously a single JSON file rewritten whole (up
        to 500 entries) on every command."""

        try:
            raw_steps = result.get("results") or result.get("steps") or []
            step_summary = []
            for step in raw_steps[:10]:
                if not isinstance(step, dict):
                    continue
                intent = step.get("intent") or {}
                label = (
                    step.get("action")
                    or (intent.get("type") if isinstance(intent, dict) else None)
                    or step.get("subtask_description")
                    or "unknown"
                )
                step_summary.append(
                    {
                        "action": str(label)[:80],
                        "success": bool(step.get("success", True)),
                        **({"error": str(step.get("error"))} if step.get("error") else {}),
                    }
                )

            entry = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "command": command,
                "tier": result.get("tier") or strategy.get("tier", "unknown"),
                "success": bool(result.get("success")),
                "steps": step_summary,
            }
            if result.get("error"):
                entry["error"] = str(result.get("error"))

            self.memory.add_journal_entry(entry)
        except Exception as exc:
            logger.debug("Execution journal write skipped: {}", str(exc))

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

    @staticmethod
    def _summarize_result(result: Dict[str, Any]) -> str:
        """Build a short human-readable summary of an execution result.

        Used both for conversational follow-up ("email that to raj") and as
        the input to outcome verification - factored out so both stay in
        sync instead of duplicating the same bit-collection logic.
        """
        try:
            summary_bits = []
            resp_text = str(result.get("response") or "").strip()
            if resp_text:
                summary_bits.append(resp_text[:200])
            for s in (result.get("results") or [])[:3]:
                if isinstance(s, dict):
                    d = str(s.get("subtask_description") or s.get("message") or s.get("action") or "").strip()
                    if d:
                        summary_bits.append(d[:120])
            return " | ".join(summary_bits)[:600]
        except Exception:
            return ""

    _ARTIFACT_KEYS = ("path", "filepath", "file_path", "backup_path",
                      "destination", "saved_path", "url", "final_url")
    # Numbers a follow-up question is likely to ask about. "How many did you
    # just show me" cannot be answered from a path.
    _COUNT_KEYS = ("total", "count", "deleted", "killed", "removed", "rows",
                   "files", "size", "remaining", "sections")

    def _record_action(self, command: str, result: Dict[str, Any]) -> None:
        """Remember what was DONE, so the conversation can talk about it.

        Chat history alone was not enough: it records what was said, and a
        file being written is not something that was said. Artefact paths
        are pulled out explicitly because "where did you put it" is the
        follow-up people actually ask, and a model with no record of the
        path will confidently make one up.
        """
        try:
            if (result.get("tier") == "conversation"
                    or result.get("mode") == "chat"):
                return  # talking is already in the chat history

            artifacts = []
            counts = []

            def _harvest(node, depth=0):
                if depth > 3 or len(artifacts) >= 6:
                    return
                if isinstance(node, dict):
                    for key in self._ARTIFACT_KEYS:
                        value = node.get(key)
                        if isinstance(value, str) and value.strip():
                            if value not in artifacts:
                                artifacts.append(value)
                    for key in self._COUNT_KEYS:
                        value = node.get(key)
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            entry = f"{key}={value}"
                            if entry not in counts:
                                counts.append(entry)
                    # A list of records answers "how many" directly.
                    for key in ("tasks", "projects", "team_members", "processes",
                                "results", "drives"):
                        value = node.get(key)
                        if isinstance(value, list):
                            entry = f"{key}={len(value)}"
                            if entry not in counts:
                                counts.append(entry)
                    for value in node.values():
                        if isinstance(value, (dict, list)):
                            _harvest(value, depth + 1)
                elif isinstance(node, list):
                    for item in node[:8]:
                        _harvest(item, depth + 1)

            _harvest(result)

            self._recent_actions.append({
                "command": command[:200],
                "succeeded": bool(result.get("success")),
                "summary": (self._summarize_result(result) or "")[:300],
                "artifacts": artifacts[:6],
                "counts": counts[:5],
                "error": str(result.get("error") or "")[:200],
            })
        except Exception as exc:
            logger.debug("Could not record action for context: {}", str(exc)[:100])

    def _recent_actions_context(self) -> str:
        """The recent actions, written for a model to read as fact."""
        if not self._recent_actions:
            return ""
        lines = []
        for entry in list(self._recent_actions)[-5:]:
            status = "succeeded" if entry["succeeded"] else "FAILED"
            line = f"- \"{entry['command']}\" -> {status}"
            detail = []
            if entry["artifacts"]:
                detail.append("produced: " + ", ".join(entry["artifacts"][:3]))
            if entry.get("counts"):
                detail.append(", ".join(entry["counts"][:3]))
            if detail:
                line += f" ({'; '.join(detail)})"
            elif entry["summary"]:
                line += f" ({entry['summary'][:120]})"
            if not entry["succeeded"] and entry["error"]:
                line += f" [error: {entry['error'][:100]}]"
            lines.append(line)
        return "\n".join(lines)

    def _record_learning(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        """Record command learning without letting storage failures break execution."""

        try:
            # A run the verifier flagged as not matching the request is not a
            # pattern to reuse. Recording it as a success is what taught the
            # system that "search the web" answers "create a document".
            if result.get("outcome_mismatch"):
                result = dict(result)
                result["success"] = False
                result["mismatch"] = True
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

    def _recall_relevant_context(self, command: str, limit: int = 3) -> str:
        """Summarize semantically similar past commands for the planner.

        This is what makes episodic memory actually influence a decision.
        The embedding write was previously paid on every command while
        nothing ever read it back (audit H-1); this is the read side.
        Falls back silently to "" when no embedding model is available,
        so it degrades to the system's prior behaviour rather than failing.
        """
        try:
            episodes = self.memory.recall_similar_episodes(command, limit=limit)
        except Exception as exc:
            logger.debug("Similar-episode recall unavailable: {}", str(exc))
            return ""

        lines = []
        for ep in episodes:
            task = str(ep.get("task") or "").strip()
            if not task or task.lower() == (command or "").strip().lower():
                continue  # don't feed the command back to itself
            outcome = "succeeded" if ep.get("success") else "failed"
            lines.append(f"- \"{task[:110]}\" ({outcome})")
        return "\n".join(lines[:limit])

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

        # autonomy._generate_proactive_suggestions/_summarize_context read
        # recent_context as [{"command": ...}, ...]. get_recent_context()
        # returns short-term memory SLOTS keyed by name (last_command,
        # last_strategy, ...) - not a command history - so every lookup of
        # ctx.get("command") always returned "" and proactive suggestions
        # could never fire. Session activities already hold the real recent
        # command history (log_session_activity is called every command).
        recent_commands = self.memory.get_last_session_activities(limit=5) if hasattr(self.memory, "get_last_session_activities") else []

        return {
            "preferences": getattr(self.memory, "preferences", {}),
            "recent_context": [{"command": c} for c in recent_commands],
            "workflow_patterns": workflows,
            "tools": self.get_tool_manifest(),
        }

    ACTION_VERBS = (
        "open", "launch", "start", "search", "find", "look up", "google",
        "navigate", "go to", "create", "make", "send", "fill", "list",
        "show", "run", "copy", "move", "delete", "organize", "download",
        "check", "play", "suggest", "recommend", "close", "read", "analyze",
        "schedule", "remind", "call", "email", "write", "scan", "backup",
        "compare", "buy", "order", "book", "clean", "sort", "rename",
        # Added after live sessions: real phrasings that fell through the
        # gate and were answered as small talk.
        "tidy", "tidy up", "clear", "clear out", "empty", "archive",
        "summarise", "summarize", "explain", "research", "draft", "generate",
        "install", "update", "upgrade", "restart", "stop", "kill", "print",
        "add", "remove", "delete", "mark", "set", "assign", "schedule",
        "convert", "extract", "export", "import", "record", "translate",
    )

    # Question openers. Real requests are often phrased as questions with no
    # imperative verb and no "?" typed at all - "how much room have i got
    # left", "whats hogging the memory". Requiring a verb dismissed those as
    # gibberish and answered them as small talk.
    QUESTION_OPENERS = (
        "what", "whats", "what's", "how", "hows", "how's", "where", "which",
        "when", "why", "who", "is there", "are there", "do i", "have i",
        "can you", "could you", "would you", "any chance",
    )

    # Nouns from this system's own domain. A sentence naming one is about the
    # machine, not chit-chat - "my cat is fluffy" names none of them.
    DOMAIN_NOUNS = (
        "file", "files", "folder", "folders", "directory", "disk", "drive",
        "drives", "space", "storage", "room", "memory", "ram", "cpu",
        "processor", "process", "processes", "app", "apps", "application",
        "program", "window", "screen", "browser", "tab", "download",
        "downloads", "desktop", "document", "documents", "spreadsheet",
        "email", "inbox", "task", "tasks", "project", "reminder", "calendar",
        "battery", "network", "wifi", "internet", "system", "machine",
        "laptop", "computer", "temp", "cache", "junk", "trash", "recycle",
    )

    @classmethod
    def _looks_actionable(cls, normalized: str) -> bool:
        """Heuristic: does this look like a real task/command at all?

        Accepts a question mark, a digit, a known action verb, or - added
        after real misroutes - a question opener paired with a noun from this
        system's domain.

        The verb-only rule sent "how much room have i got left" (a disk
        query) and "whats hogging the memory" (a process query) to small
        talk, because neither contains an imperative verb. Requiring BOTH an
        opener and a domain noun keeps genuine gibberish out: "flurbick
        wibble wobble" and "my cat is fluffy" still fail every branch.
        """
        if "?" in normalized:
            return True
        if any(ch.isdigit() for ch in normalized):
            return True
        if any(re.search(rf"\b{re.escape(v)}\b", normalized) for v in cls.ACTION_VERBS):
            return True

        has_opener = any(
            re.search(rf"\b{re.escape(q)}\b", normalized) for q in cls.QUESTION_OPENERS
        )
        has_domain_noun = any(
            re.search(rf"\b{re.escape(n)}\b", normalized) for n in cls.DOMAIN_NOUNS
        )
        return has_opener and has_domain_noun

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

        # Unambiguous multi-step markers ("and then"/"then"/"after that", or
        # 2+ named action_markers) must decompose BEFORE the single-intent
        # shortcut below can collapse them into one action. A phrase-substring
        # match in _parse_direct_command (e.g. "system status" inside "show
        # system status and then list running processes") matches the whole
        # multi-clause sentence and silently discards everything after it.
        # This is intentionally narrower than the full _contains_explicit_
        # sequence check (see below): its broad "2+ verbs joined by and"
        # heuristic also fires on "open chrome and search for AI trends",
        # which has a dedicated single-action browser_action regex - running
        # the broad heuristic this early would wrongly decompose a command
        # that is correctly handled as one action.
        if self.decompose_complex_tasks and self._has_unambiguous_sequence_marker(normalized):
            return {"tier": "sequential", "complexity": "complex", "source": "decomposer"}

        direct_intent = self._parse_direct_command(command)
        autonomy = getattr(self, "autonomy", None)

        # ANY deterministic intent routes directly - all 76 types have
        # execution handlers (contract audit). Power actions keep their
        # confirmation gates inside the executor.
        if direct_intent:
            return {
                "tier": "direct",
                "complexity": "simple",
                "intent": direct_intent,
                "source": "rules",
            }

        # The rules did not recognise it. Before handing a phrasing nobody
        # anticipated to a language model, ask the learned classifier -
        # which generalises where the rules cannot. It answers only for
        # intents that never carry arguments, and only when confident
        # enough that it was right every time on the measured set, so a
        # miss here costs nothing: it simply falls through as before.
        classified = self._classify_intent(command)
        if classified:
            return {
                "tier": "direct",
                "complexity": "simple",
                "intent": classified,
                "source": "classifier",
            }

        # AUTONOMY claims only unparsed commands - 'open browser' is parsed
        # directly and resolves the saved default_browser preference inside
        # _execute_directly's open_application handler, so autonomy's role
        # here is heuristics deterministic parsing genuinely cannot resolve:
        # 'currently opened apps', bare-open clarification flows, etc.
        # Deferred: see _autonomy_fallback below. should_handle matches on
        # bare verbs ("create", "make", "write", "research", "report",
        # "file", "folder"), which is nearly every task-shaped sentence, so
        # it claimed commands before the model-backed router ever saw them.
        # Measured: the router produces a correct 2-step plan for "research
        # X and write me a report", while autonomy produced a web search and
        # an empty file. The model is better at this than the keyword list,
        # so the model goes first and autonomy catches what it cannot
        # resolve.
        autonomy_would_handle = bool(
            autonomy and autonomy.should_handle(command, complexity)
        )

        # Multi-action UNPARSED commands decompose deterministically - this
        # is the broader heuristic (includes "2+ verbs joined by and/then"
        # and "2+ search for" counting) that would false-positive on composite
        # single-action patterns already handled above by direct_intent.
        if self.decompose_complex_tasks and self._contains_explicit_sequence(normalized):
            return {"tier": "sequential", "complexity": "complex", "source": "decomposer"}

        conversation_agent = self.agents.get("conversation")
        if conversation_agent and conversation_agent.is_conversation(command):
            return {"tier": "conversation", "complexity": "simple", "source": "conversation"}

        # Nonsense gate: commands with no action verbs, no digits, and no
        # question mark are almost certainly gibberish or chat - never plan
        # tasks from them ("flurbick wibble wobble" used to become a task).
        # autonomy_would_handle is a second opinion on "is this a task?".
        # Without it, "currently opened apps" fell to the nonsense gate
        # ("opened" is not the verb "open") and was answered as small talk.
        if not self._looks_actionable(normalized) and not autonomy_would_handle:
            return {"tier": "conversation", "complexity": "simple", "source": "nonsense_gate"}

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

        if complexity in {"simple", "medium", "complex"}:
            # BRAIN TIER (final fallback): no regex matched and no learned
            # route claims this - let the model understand the sentence
            # against the tool manifest instead of guessing with a council.
            # Widened to include "complex" - the intent router already
            # supports multi-step PLANS (this is the whole point of Brain
            # v2), and one Brain call is cheaper and more accurate than a
            # multi-member council for compound-but-not-critical commands.
            # "critical" complexity still falls through below to the full
            # council + Chairman validation path.
            if getattr(self, "intent_router", None):
                try:
                    # Router context = what just happened (for pronoun
                    # resolution) + semantically similar past commands (so
                    # the model can reuse phrasings that worked before).
                    context_parts = []
                    # The same record the conversation gets. Without it the
                    # router could not resolve "where did you save that" -
                    # it had only a loose summary of the last result, with
                    # no artifact paths - so it asked for clarification
                    # about something the system already knew. That is the
                    # routing half of "it feels like two separate systems".
                    actions = self._recent_actions_context()
                    if actions:
                        # Labelled as evidence, not as a menu. Handing the
                        # router a bare list of past work made it chain new
                        # steps onto it - "create task" became create, then
                        # list, then update a task id it invented.
                        context_parts.append(
                            "ACTIONS ALREADY PERFORMED (for answering questions "
                            "about them - do NOT repeat these or chain new work "
                            "onto them):\n" + actions
                        )
                    last_summary = getattr(self, "_last_execution_summary", "") or ""
                    if last_summary:
                        context_parts.append(last_summary)
                    similar = self._recall_relevant_context(command)
                    if similar:
                        context_parts.append("Similar past commands:\n" + similar)
                    decision = self.intent_router.decide(
                        command,
                        context="\n\n".join(context_parts) or None,
                    )
                except Exception as exc:
                    logger.warning("IntentRouter error: {}", str(exc)[:100])
                    decision = None
                if decision:
                    plan_steps = decision.get("plan")
                    if plan_steps:
                        return {
                            "tier": "brain",
                            "complexity": "complex",
                            "source": "brain",
                            "plan": plan_steps,
                        }
                    action = decision.get("action")
                    if action == "chat":
                        return {"tier": "conversation", "complexity": "simple", "source": "brain"}
                    if action == "clarify":
                        return {
                            "tier": "clarify",
                            "complexity": "simple",
                            "question": (decision.get("params") or {}).get(
                                "question", "Could you rephrase that for me?"
                            ),
                            "source": "brain",
                        }
                    return {
                        "tier": "brain",
                        "complexity": "simple",
                        "source": "brain",
                        "intent": {"type": action},
                        "params": decision.get("params", {}),
                    }
            if autonomy_would_handle:
                return {"tier": "autonomous", "complexity": complexity,
                        "source": "autonomy_fallback"}
            return {"tier": "single_model", "complexity": complexity, "source": "council"}

        return {"tier": "sequential", "complexity": complexity, "source": "council"}

    def _can_reuse_learned_strategy(self, learned_strategy: Dict[str, Any]) -> bool:
        """Whether a learned direct strategy is safe/confident enough to reuse.

        Previously hardcoded to exactly 3 read-only intent types regardless
        of how well any OTHER intent actually performed - the adaptive/
        phase-5 learning stack computed a confidence score for every intent
        but could only ever act on system_info/command_history/voice_status,
        so learning never influenced routing for anything else (the L-6
        finding). Replaced with a real check: any intent type may be reused
        once its OWN measured success rate (LearningAgent.get_intent_
        confidence, weighted by verified outcomes where available - see
        core.council.verify_outcome) crosses a high bar over enough samples.

        This only changes WHICH intents may be reused, not the safety net
        around it: every caller of this method already requires a >=0.99
        near-exact text match (find_similar_success) or an equivalent
        adaptive-cluster/classification match before reaching here, so
        replayed parameters are always paired with essentially the same
        original command text.
        """
        intent_type = (learned_strategy.get("intent") or {}).get("type")
        if not intent_type:
            return False

        # Always-safe: read-only, no command-specific parameters to go stale.
        if intent_type in {"system_info", "command_history", "voice_status"}:
            return True

        learning_agent = self.agents.get("learning")
        if not learning_agent or not hasattr(learning_agent, "get_intent_confidence"):
            return False
        try:
            stats = learning_agent.get_intent_confidence(intent_type)
        except Exception as exc:
            logger.warning("Intent confidence lookup failed: {}", str(exc))
            return False
        return stats.get("samples", 0) >= 5 and stats.get("success_rate", 0.0) >= 0.9

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

    async def _chairman_gate(self, command: str, plan_repr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Critical-complexity safety gate reachable from every tier.

        Previously Chairman.validate_plan only ran inside the council branch,
        so direct/brain/autonomous tiers skipped safety review entirely for
        critical-complexity commands (verified: "delete the temp folder"
        routes to the autonomous tier, which never consulted the Chairman).
        Returns None when approved; otherwise a rejected result ready to
        return from process_command.

        Degrades to a typed confirmation when the model is unreachable
        instead of refusing outright. The gate previously failed closed on
        any model error, which meant one Ollama hiccup made every command
        containing delete/remove/restart/format/uninstall impossible -
        including harmless ones like "format my notes" - in a product whose
        premise is working locally when things are down. The action is still
        never performed without approval; the approver just becomes the user.
        """
        # The user already approved this exact command after an unavailable
        # safety review - honour it once and fall straight through.
        if getattr(self, "_critical_gate_bypass", None) == command:
            logger.info("Critical gate bypassed by explicit user confirmation.")
            return None

        try:
            validation = await self.chairman.validate_plan(plan_repr, command)
        except Exception as exc:
            logger.error("Chairman critical-tier gate failed: {}", str(exc))
            return self._stage_critical_confirmation(command, plan_repr, str(exc))

        # A model that answered but couldn't produce a verdict (parse
        # failure) is also "unavailable" for our purposes - don't treat an
        # unparseable response as a considered rejection.
        if validation.get("error") and not validation.get("reasoning"):
            return self._stage_critical_confirmation(command, plan_repr, str(validation.get("error")))

        if validation.get("approved"):
            return None

        logger.warning("Chairman rejected critical-complexity command outside the council path")
        reasoning = str(validation.get("reasoning") or "").strip()
        # The display reads result["error"]; this path only set "reason", so a
        # CORRECT safety refusal surfaced to the user as "I encountered an
        # issue: Unknown error" - indistinguishable from a crash. Say plainly
        # that it was refused, and why.
        return {
            "success": False,
            "rejected": True,
            "reason": validation.get("reasoning"),
            "error": (
                f"I refused that on safety grounds: {reasoning}" if reasoning
                else "I refused that on safety grounds - it looked destructive "
                     "and I could not confirm it was safe to run."
            ),
            "recovery_suggestion": (
                "If you genuinely want this, rephrase it narrowly (name the exact "
                "file or folder) and I will ask you to confirm before acting."
            ),
            "validation": validation,
        }

    def _stage_critical_confirmation(self, command: str, plan_repr: Dict[str, Any], why: str) -> Dict[str, Any]:
        """Fall back to human approval when automated review is unavailable."""

        self.memory.remember_short_term(
            "pending_critical_command",
            {"command": command, "plan": plan_repr, "reason": why},
        )
        logger.warning("Safety review unavailable ({}) - deferring to user confirmation.", why[:80])
        return {
            "success": False,
            "needs_confirmation": True,
            "question": (
                "I couldn't run my automated safety review for that "
                f"(reason: {why[:100]}). It looks potentially destructive. "
                "Type 'confirm command' to run it anyway, or 'cancel command' to discard it."
            ),
            "warning": f"Automated safety review unavailable: {why[:140]}",
            "results": [],
        }

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

    def _has_unambiguous_sequence_marker(self, normalized_command: str) -> bool:
        """The narrow subset of _contains_explicit_sequence safe to check
        BEFORE direct-intent parsing: an explicit "and then"/"then"/"after
        that" marker, or 2+ specifically-named action phrases. Both signal a
        real multi-step command with no plausible single-action reading, so
        there is no composite regex they could be wrongly overriding.
        """
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
        return " and " in normalized_command and sum(marker in normalized_command for marker in action_markers) >= 2

    def _contains_explicit_sequence(self, normalized_command: str) -> bool:
        """Return whether the command clearly contains multiple sequential actions."""

        if self._has_unambiguous_sequence_marker(normalized_command):
            return True

        if normalized_command.count(" search ") >= 2 or normalized_command.count(" search for ") >= 2:
            return True

        # Natural-language multi-action: two or more distinct action verbs
        # joined by "and"/"then" (e.g. "open google and search for amazon").
        if " and " in normalized_command or " then " in normalized_command:
            action_verbs = (
                "open", "launch", "start", "search", "find", "look up", "google",
                "navigate", "go to", "create", "make", "send", "fill", "list",
                "show", "run", "copy", "move", "delete", "organize", "download",
                "check", "play",
            )
            found = [v for v in action_verbs if re.search(rf"\b{v}\b", normalized_command)]
            if len(found) >= 2:
                return True

        return False

    def _assess_complexity(self, command: str) -> str:
        """Assess command complexity using lightweight heuristics."""

        command_lower = command.lower()

        # Word-boundary matched, and "format" is qualified: a bare substring
        # check classified "format my notes" (text formatting) as critical,
        # which then required a safety review to do anything at all.
        # "delete" alone is not a danger signal. Deleting a TASK RECORD is
        # routine; deleting a system folder is not. Treating every delete as
        # critical sent "delete all the tasks" and "remove priya from the
        # team" to the safety review, which refused them - a regression
        # introduced when the Chairman gate was correctly widened to every
        # tier without narrowing what counted as critical.
        #
        # So: a destructive verb only escalates when it is aimed at
        # something on the machine. App-level records have their own
        # handlers and are recoverable from the store.
        destructive_verb = r"(?:delete|deleting|remove|removing|wipe|erase|" \
                           r"uninstall|format|destroy|purge)"

        # Records this system owns. Removing one is ordinary work.
        app_level = re.search(
            destructive_verb + r"[\w\s]{0,20}\b"
            r"(?:task|tasks|reminder|reminders|note|notes|project|projects|"
            r"team\s*member|member|team|staff|roster|contact|entry|record|row|event|"
            r"appointment|todo|list\s*item)\b",
            command_lower,
        )

        # Things on the machine. These stay critical.
        system_level = [
            destructive_verb + r"[\w\s]{0,20}\b"
            r"(?:folder|directory|drive|disk|partition|volume|system32|"
            r"windows|program\s*files|users|appdata|registry|everything|"
            r"all\s+files|all\s+my\s+files|repository|repo)\b",
            r"\b(?:format)\b\s+(?:the\s+|my\s+)?(?:[a-z]:|disk|drive|volume|"
            r"partition|usb|sd\s*card)",
            r"\b(?:shut\s*down|shutdown|reboot|restart)\b",
            r"\bregistry\b",
            r"\brm\s+-rf\b|\bdel\s+/[sf]\b|\bformat\s+[a-z]:",
            # A bare path with a destructive verb: "delete C:/Windows"
            destructive_verb + r"\s+[\"']?[a-zA-Z]:[\\/]",
        ]

        if app_level and not any(
            re.search(pattern, command_lower) for pattern in system_level
        ):
            # Ordinary record management - let the normal handlers deal with
            # it, including their own confirmations.
            pass
        elif any(re.search(pattern, command_lower) for pattern in system_level):
            return "critical"
        elif re.search(destructive_verb + r"\b", command_lower):
            # A destructive verb with no clear target. Err towards review.
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

    # A bare address, and the words that introduce a subject.
    _EMAIL_ADDR_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    _SUBJECT_INTRO = (
        "regarding", "about", "re", "with subject", "subject",
        "concerning", "on the topic of",
    )
    _BODY_INTRO = (
        "saying", "that says", "with body", "body", "with message",
        "message", "telling them", "and say", "which says",
    )

    def _parse_structured_command(self, command: str, normalized: str) -> Optional[Dict[str, Any]]:
        """Catch structured requests before the generic browser branch.

        _parse_direct_command is an ordered chain, and the browser/search
        branches sit roughly 350 lines above the enterprise ones. Anything
        containing a domain-shaped token or the word "search" was therefore
        claimed by the browser first:

            "create tenant Acme with domain acme.com"  -> opened acme.com
            "search for files named report"            -> googled it

        Neither needs a language model to understand; they just needed to be
        matched before the catch-all. Returns None for anything that is not
        an unambiguous structured request, so every other tier is untouched.
        """
        # --- what is using the memory / CPU ----------------------------------
        heavy = re.search(
            # "whats" with no apostrophe is how it actually gets typed.
            r"\b(?:what(?:'?s| is| are)?|which|show|list|tell\s+me)\b[\w\s]{0,30}?"
            r"\b(?:hogging|eating|using|consuming|taking|hyping)\b"
            r"[\w\s]{0,20}?\b(?P<what>memory|ram|cpu|processor)\b",
            command, re.IGNORECASE,
        )
        if not heavy:
            heavy = re.search(
                r"\b(?:top|biggest|heaviest|largest)\b[\w\s]{0,20}?"
                r"\b(?:process|processes|app|apps|program|programs)\b"
                r"[\w\s]{0,20}?\b(?P<what>memory|ram|cpu|processor)\b",
                command, re.IGNORECASE,
            )
        if heavy:
            kind = heavy.group("what").lower()
            return {
                "type": "top_processes",
                "by": "cpu" if kind in ("cpu", "processor") else "memory",
            }

        # --- arithmetic ------------------------------------------------------
        # "what is 17 percent of 4500" was taking ~12 seconds because it
        # went to a language model. It is arithmetic. The sandbox evaluator
        # already exists; it just was not reachable without the model.
        expr = self._parse_arithmetic(command)
        if expr:
            return {"type": "calculate", "expression": expr, "original": command.strip()}

        # --- open a FOLDER -------------------------------------------------
        # "open the downloads folder" was treated as an APPLICATION named
        # "the downloads folder". Folders come before files below because
        # "documents folder" would otherwise look like a filename.
        open_folder = re.search(
            # The name must not carry a file extension or a "from" clause:
            # "open my_tasks.xlsx from documents folder" opens a FILE that
            # merely names a folder, and it was being swallowed here.
            r"^(?:just\s+|please\s+|can\s+you\s+)?open\s+(?:the\s+|my\s+)?"
            r"(?P<name>(?!.*\bfrom\b)(?!.*\.[A-Za-z0-9]{1,5}\b)[\w .\\/:-]+?)"
            r"\s*(?:folder|directory)\s*$",
            command, re.IGNORECASE,
        )
        if not open_folder:
            open_folder = re.search(
                r"^(?:just\s+|please\s+)?open\s+(?:the\s+|my\s+)?"
                r"(?:folder|directory)\s+(?P<name>[\w .\\/:-]+?)\s*$",
                command, re.IGNORECASE,
            )
        if open_folder:
            return {
                "type": "open_folder",
                "folder": open_folder.group("name").strip(),
            }

        # --- remove someone from the team ----------------------------------
        # There was no branch at all, so it fell to the model and then hit
        # the safety review because it contains "remove".
        drop_member = re.search(
            r"\b(?:remove|delete|drop|take)\s+(?P<name>[A-Za-z][A-Za-z .'-]{1,40}?)"
            r"\s+(?:from|out\s+of|off)\s+(?:the\s+)?(?:team|staff|roster)\s*$",
            command, re.IGNORECASE,
        )
        if drop_member:
            return {
                "type": "remove_team_member",
                "name": drop_member.group("name").strip(),
            }

        # --- delete tasks --------------------------------------------------
        if re.search(r"\b(?:delete|remove|clear)\s+(?:all\s+)?(?:my\s+|the\s+)?tasks?\b",
                     normalized):
            named = re.search(
                r"\b(?:delete|remove)\s+(?:the\s+)?task\s+"
                r"(?:named|called|titled\s+)?[\"']?(?P<title>.+?)[\"']?\s*$",
                command, re.IGNORECASE,
            )
            return {
                "type": "delete_tasks",
                "title": named.group("title").strip() if named else None,
                "all": bool(re.search(r"\ball\b", normalized)) and not named,
            }

        # --- search WITHIN a site, in one tab ------------------------------
        # "go to amazon.in and search for laptops" opened amazon in one tab
        # and then a separate Google search in another. It is one action.
        site_search = re.search(
            r"(?:go\s+to|open|visit)\s+(?P<site>[\w-]+\.[\w.]+)"
            r"[\s,]*(?:and\s+)?(?:then\s+)?search\s+(?:for\s+)?"
            r"[\"']?(?P<query>.+?)[\"']?\s*$",
            command, re.IGNORECASE,
        )
        if site_search:
            return {
                "type": "site_search",
                "site": site_search.group("site").strip(),
                "query": site_search.group("query").strip(),
            }

        # --- open a FILE, which is not the same as opening an app ---------
        # "just open my_tasks.xlsx from documents folder" fell through to
        # the model, and "open my_tasks.xlsx" was treated as an application
        # name. The session shows this asked four different ways and failing
        # every time: "why failed it is such a simple task can't you just
        # open the spreadsheet?"
        open_file = re.search(
            r"^(?:just\s+|please\s+|can\s+you\s+)?open\s+(?:the\s+|my\s+)?"
            r"(?:file\s+|spreadsheet\s+|document\s+|sheet\s+)?"
            r"[\"']?(?P<name>[\w .()-]+\.[A-Za-z0-9]{1,5})[\"']?"
            r"(?:\s+(?:from|in)\s+(?:the\s+|my\s+)?(?P<where>[\w .\\/-]+?)(?:\s+folder)?)?\s*$",
            command, re.IGNORECASE,
        )
        # A bare filename on its own line is also a request to open it.
        if not open_file:
            open_file = re.match(
                r"^[\"']?(?P<name>[\w.()-]+\.[A-Za-z0-9]{1,5})[\"']?\s*$",
                command.strip(),
            )
        if open_file:
            return {
                "type": "open_file",
                "filename": open_file.group("name").strip(),
                "where": (open_file.groupdict().get("where") or "").strip() or None,
            }

        # --- delete a named FILE (not a task, not an app) -----------------
        delete_file = re.search(
            r"\bdelete\s+(?:the\s+|my\s+)?"
            r"(?:file\s+|spreadsheet\s+|document\s+)?"
            r"[\"']?(?P<name>[\w .()-]+\.[A-Za-z0-9]{1,5})[\"']?"
            r"(?:\s+(?:from|in)\s+(?:the\s+|my\s+)?(?P<where>[\w .\\/-]+?)(?:\s+folder)?)?\s*$",
            command, re.IGNORECASE,
        )
        if delete_file:
            return {
                "type": "delete_named_file",
                "filename": delete_file.group("name").strip(),
                "where": (delete_file.groupdict().get("where") or "").strip() or None,
            }

        # --- questions about ITSELF ---------------------------------------
        # Asked repeatedly in the session and answered by a 3B model that
        # has no idea which model it is or where it lives, so it invented
        # answers. These facts are known locally; read them out instead.
        if re.search(r"\b(?:which|what)\b.*\bmodels?\b.*\b(?:you|using|running)\b",
                     normalized) or re.search(
                     r"\bwhat\s+model\b|\bwhich\s+model\b", normalized):
            return {"type": "self_report", "topic": "model"}

        if re.search(r"\b(?:which|what)\s+(?:folder|directory|path)\b.*\byou\b",
                     normalized) or re.search(
                     r"\bwhere\s+(?:are|is)\s+(?:you|your\s+files)\b", normalized):
            return {"type": "self_report", "topic": "location"}

        if re.search(
            r"\bwhat\s+(?:can|could)\s+you\s+do\b"
            r"|\btell\s+me\s+what\s+you\s+can\s+do\b"
            r"|\byour\s+capabilit|\bwhat\s+are\s+you\s+able\s+to\b"
            r"|\blist\s+your\s+(?:features|abilities|capabilities)\b",
            normalized,
        ):
            return {"type": "self_report", "topic": "capabilities"}

        # --- add a person to the team -------------------------------------
        # "add priya to the team" reached the conversation tier, which
        # replied "Sure thing, Priya added." and added nobody. Claiming an
        # action that never happened is the worst failure mode this system
        # has, so this phrasing gets a real branch.
        member = re.search(
            r"\b(?:add|register|onboard)\s+(?P<name>[A-Za-z][A-Za-z .'-]{1,40}?)"
            r"\s+(?:to|into)\s+(?:the\s+)?(?:team|staff|roster)"
            # "...with email x@y.com" and "...as a developer" are common and
            # used to push the whole command out to the model.
            r"(?:\s+(?:with|and)\s+(?:the\s+)?e-?mail\s+(?P<email>[\w.+-]+@[\w-]+\.[\w.-]+))?"
            r"(?:\s+as\s+(?:a\s+|an\s+)?(?P<role>[A-Za-z ]{2,30}?))?\s*$",
            command, re.IGNORECASE,
        )
        if member:
            return {
                "type": "add_team_member",
                "name": member.group("name").strip(),
                "email": (member.groupdict().get("email") or "").strip() or None,
                "role": (member.groupdict().get("role") or "").strip() or "member",
            }

        # --- complete a task by NAME, not by uuid --------------------------
        # "mark call supplier as done" failed with "Task ID is required":
        # the handler only accepted an id, which a person never has.
        done = re.search(
            r"\b(?:mark|set|flag)\s+(?P<title>.+?)\s+as"
            r"\s+(?:done|complete|completed|finished)\s*$",
            command, re.IGNORECASE,
        )
        if done:
            return {"type": "complete_task", "title": done.group("title").strip()}

        # --- read the screen: OCR, not a web search ------------------------
        # "read the text on my screen" was routed to web search and failed
        # with "Search query missing".
        if re.search(r"\btext\b.*\b(?:screen|display|monitor)\b", normalized) or \
           re.search(r"\bread\s+(?:my|the)\s+screen\b", normalized):
            return {"type": "extract_text"}

        # --- free disk space is not folder size ----------------------------
        # "how much disk do i have left" analysed the project folder and
        # reported 54 MB, which is a confident wrong answer.
        if re.search(r"\b(?:disk|drive|storage|space)\b.*\b(?:left|free|remaining|available)\b",
                     normalized) or \
           re.search(r"\b(?:free|available|remaining)\s+(?:disk|drive|storage)\b", normalized):
            return {"type": "disk_drives"}

        # --- spreadsheet means spreadsheet ---------------------------------
        # "create a spreadsheet of my tasks" listed the tasks instead,
        # because the task branch matched first.
        sheet = re.search(
            r"\b(?:create|make|generate|build|export)\s+(?:me\s+)?(?:a|an)?\s*"
            r"(?:spreadsheet|excel|xlsx|csv)\b"
            r"(?:\s+(?:of|for|with|from)\s+(?P<subject>.+?))?\s*$",
            command, re.IGNORECASE,
        )
        if sheet:
            subject = (sheet.group("subject") or "data").strip()
            return {"type": "create_spreadsheet", "title": subject, "subject": subject}

        # --- tenant creation: a domain here is data, not a place to visit ---
        tenant = re.search(
            r"\b(?:create|add|register|set\s*up)\s+(?:a\s+)?tenant\s+"
            r"(?P<name>[A-Za-z0-9 &._-]+?)"
            r"(?:\s+with\s+domain\s+(?P<domain>[\w.-]+\.[A-Za-z]{2,}))?\s*$",
            command, re.IGNORECASE,
        )
        if tenant:
            return {
                "type": "create_tenant",
                "tenant_name": tenant.group("name").strip(),
                "domain": (tenant.group("domain") or "").strip() or None,
            }

        # --- file search: this is the filesystem, not the web -------------
        # "search my computer for photos" was answered with a Google search.
        # The old guard only recognised the literal words file/folder/
        # document, so naming the MACHINE instead of the file type sent the
        # user to the web to look for their own files. "locate", "where is"
        # and "do i have" were not recognised as searching at all.
        _search_verb = re.search(
            r"\b(?:search|find|look|locate|where\s+is|where\s+are|do\s+i\s+have)\b",
            normalized,
        )
        _local_noun = re.search(
            r"\bfiles?\b|\bfolders?\b|\bdocuments?\b|\bcomputer\b|\bmachine\b"
            r"|\bpc\b|\blaptop\b|\bdrive\b|\bdisk\b|\bsystem\b|\bdirectory\b"
            r"|\bdesktop\b|\bdownloads\b",
            normalized,
        )
        if _search_verb and _local_noun:
            # The older branch below parses "<query> in <path>" and splits
            # the location off correctly; only take searches that name no
            # location, which it could not handle at all.
            if re.search(r"\b(?:in|inside|under|within)\b", normalized):
                return None
            if not re.search(r"\b(?:on|in)\s+(?:the\s+)?(?:web|internet|google|bing|amazon|youtube)\b", normalized):
                # Prefer an explicit introducer, which brackets the term
                # precisely; "for"/"with" are last resorts because they also
                # appear in scaffolding ("search FOR files named report"
                # would otherwise yield "files named report").
                cleaned = ""
                explicit = re.search(
                    r"\b(?:named|called|titled|matching|containing)\s+"
                    r"[\"']?(?P<q>[^\"']+?)[\"']?\s*$",
                    command, re.IGNORECASE,
                )
                if explicit:
                    cleaned = explicit.group("q")
                else:
                    loose = re.search(
                        r"\b(?:for|with)\s+[\"']?(?P<q>[^\"']+?)[\"']?\s*$",
                        command, re.IGNORECASE,
                    )
                    if loose:
                        cleaned = loose.group("q")

                if cleaned:
                    # Strip the words that describe WHERE or WHAT KIND, so the
                    # query is the term the user actually wants matched.
                    cleaned = re.sub(
                        r"^(?:any\s+|a\s+|the\s+)?"
                        r"(?:files?|folders?|documents?)\s+"
                        r"(?:named|called|titled|with|matching)?\s*",
                        "", cleaned, flags=re.IGNORECASE,
                    )
                    cleaned = re.sub(
                        r"\s+(?:in|with)\s+(?:the\s+)?name\s*$", "",
                        cleaned, flags=re.IGNORECASE,
                    )
                    # Drop any leading scaffolding word by word. A regex
                    # handles one fixed shape; real phrasings stack them
                    # ("any file with budget"), and searching filenames for
                    # that whole phrase matches nothing.
                    scaffold = {
                        "any", "a", "an", "the", "file", "files", "folder",
                        "folders", "document", "documents", "with", "named",
                        "called", "titled", "my", "matching", "containing",
                        "for", "some",
                    }
                    words = cleaned.split()
                    while words and words[0].lower().strip(".,") in scaffold:
                        words.pop(0)
                    cleaned = " ".join(words).strip(" .,'\"")
                return {
                    "type": "search_files",
                    "query": cleaned,
                    "path": self._extract_known_path(command),
                    "search_content": "content" in normalized or "inside" in normalized,
                }

        # --- task creation ---
        task = re.search(
            r"\b(?:create|add|make|new)\s+(?:a\s+)?task\s+"
            r"(?:(?:named|called|titled|for|to)\s+)?[\"']?(?P<title>.+?)[\"']?\s*$",
            command, re.IGNORECASE,
        )
        if task:
            title = task.group("title").strip()
            if title:
                return {"type": "create_task", "title": title, "description": title}

        # --- document / report creation ---
        document = re.search(
            r"\b(?:create|write|make|draft|generate|prepare)\s+"
            r"(?:me\s+)?(?:a|an|the)?\s*(?P<kind>document|doc|report|summary|write[- ]?up)\b"
            r"(?:\s+(?:about|on|for|regarding|covering|titled|called|named)\s+(?P<topic>.+?))?\s*$",
            command, re.IGNORECASE,
        )
        if document:
            topic = (document.group("topic") or "").strip()
            if topic:
                return {
                    "type": "create_document",
                    "title": topic,
                    "topic": topic,
                    "kind": document.group("kind").lower(),
                }

        return None

    # Whisper writes non-speech events in brackets. Nothing a user types
    # deliberately looks like this.
    _NOISE_RE = re.compile(
        r"^[\s]*(?:[\[(][^\])]*[\])][\s]*)+$"
    )
    _NOISE_WORDS = (
        "typewriter", "keyboard", "clicking", "silence", "music", "noise",
        "blank_audio", "blank audio", "inaudible", "background", "static",
        "coughing", "laughter", "applause", "footsteps", "breathing",
    )

    @classmethod
    def _is_transcription_noise(cls, command: str) -> bool:
        """Is this a whisper annotation rather than something the user said?"""
        text = (command or "").strip()
        if not text:
            return False
        if not cls._NOISE_RE.match(text):
            return False
        lowered = text.lower()
        # Only treat it as noise if it also NAMES a non-speech sound; a user
        # could legitimately type "(status)" and mean it.
        return any(word in lowered for word in cls._NOISE_WORDS)

    def _parse_email_command(self, command: str, normalized: str) -> Optional[Dict[str, Any]]:
        """Deterministically parse "send an email to X regarding Y".

        There was no send_email branch in the direct parser at all, so every
        email request fell through to the Brain tier and depended on a 3B
        model extracting recipient, subject and body as JSON. It routinely
        failed, and "send an email to <addr> regarding project" simply did
        not work. Address and intent are structured enough to parse exactly;
        only the wording around them varies.

        Returns None for anything that is not clearly an email request, so
        the existing tiers keep handling everything else.
        """
        if not re.search(r"\b(?:e-?mail|mail)\b", normalized):
            return None
        has_send_verb = re.search(
            r"\b(?:send|write|shoot|fire off|compose|draft)\b", normalized
        )
        # "email bob@x.com ..." uses "email" itself as the verb.
        email_as_verb = re.match(r"^(?:e-?mail|mail)\s+[\w.+-]+@", normalized)
        if not has_send_verb and not email_as_verb:
            # "check email" / "read my inbox" are different intents.
            return None

        # Use the ORIGINAL text for the address and body so casing survives.
        match = self._EMAIL_ADDR_RE.search(command)
        if not match:
            return {
                "type": "send_email",
                "to_email": None,
                "subject": None,
                "body": None,
                "needs": "recipient",
            }
        to_email = match.group(0)

        # Everything after the address is where subject/body live.
        tail = command[match.end():].strip(" ,.;:-")

        subject = None
        body = None

        subject_pattern = r"\b(?:" + "|".join(
            re.escape(w) for w in sorted(self._SUBJECT_INTRO, key=len, reverse=True)
        ) + r")\b\s+(.+)"
        body_pattern = r"\b(?:" + "|".join(
            re.escape(w) for w in sorted(self._BODY_INTRO, key=len, reverse=True)
        ) + r")\b\s+(.+)"

        body_match = re.search(body_pattern, tail, re.IGNORECASE)
        if body_match:
            body = body_match.group(1).strip(" \"'")
            tail = tail[:body_match.start()].strip(" ,.;:-")

        subject_match = re.search(subject_pattern, tail, re.IGNORECASE)
        if subject_match:
            subject = subject_match.group(1).strip(" \"'")
        elif tail:
            # "send an email to x@y.com project update" - the remainder is
            # the subject even without an introducing word.
            subject = tail.strip(" \"'")

        # Trailing conjunctions survive splitting on the body phrase
        # ("with subject Update and body all done" -> "Update and").
        if subject:
            subject = re.sub(r"\s+(?:and|then|plus)\s*$", "", subject).strip(" ,.;:-")

        if subject and not body:
            # A one-liner like "regarding project" is the whole message.
            body = subject
        if body and not subject:
            subject = body[:60]

        return {
            "type": "send_email",
            "to_email": to_email,
            "subject": subject or "(no subject)",
            "body": body or "",
            "needs": None if (subject or body) else "content",
        }

    def _parse_direct_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Parse deterministic commands that should bypass the council."""

        normalized = self._normalize_command(command)
        normalized = re.sub(r"^(?:please|can you|could you|would you)\s+", "", normalized)

        # Whisper brackets every non-speech sound it hears, and those
        # annotations were run as commands - the session log contains
        # "[Typewriter sounds]" and "(keyboard clicking) (keyboard clicking)"
        # being processed as instructions.
        if self._is_transcription_noise(command):
            return {"type": "transcription_noise", "heard": command.strip()}

        email_intent = self._parse_email_command(command, normalized)
        if email_intent:
            return email_intent

        structured = self._parse_structured_command(command, normalized)
        if structured:
            return structured

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
            raw_path_text = backup_folder.group("path").strip()
            resolved_path = self._extract_known_path(raw_path_text)
            # _extract_known_path silently falls back to Path.cwd() when it
            # recognizes nothing specific - for a backup (which can compress
            # gigabytes) that meant "backup my thesis" archived the entire
            # AGI-System repo root with no warning. Only accept a cwd result
            # when the user actually said so; otherwise fall through so
            # Brain/clarify can ask for a real target.
            explicit_cwd_reference = any(
                kw in raw_path_text.lower() for kw in ("current folder", "current directory", "this folder", "here")
            )
            if resolved_path == str(Path.cwd()) and not explicit_cwd_reference:
                return None
            return {
                "type": "backup_folder",
                "path": resolved_path,
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
                    self._get_search_engine_url_template().format(query=quote_plus(query))
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
                "app": self._resolve_default_browser(),
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
                "app": app_name if app_name in self.BROWSER_APPS else self._resolve_default_browser(),
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
                "app": app_name if app_name in self.BROWSER_APPS else self._resolve_default_browser(),
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

        if url_target and not re.search(
            r"\b(?:and|then)\s+(?:search|find|look up|go to|navigate|open)\b", normalized
        ):
            # Guarded the same way as the browser_action/web_only/navigate_only
            # composite regexes below: without it, ANY command containing a
            # recognizable domain (e.g. "navigate to amazon.in and search for
            # laptops") short-circuited here first, navigating to the bare
            # domain and silently discarding every clause after it.
            return {
                "type": "browser_action",
                "app": self._resolve_default_browser(),
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
                "app": self._resolve_default_browser(),
                "action": "navigate",
                "target": self._build_search_target_for_site(site_url, ecommerce_only.group("query").strip()),
            }

        web_only = re.match(
            r"^(?:search(?:\s+for)?|google|look up|find)\s+(?P<target>.+)$",
            normalized,
        )
        if web_only:
            target_text = web_only.group("target").strip()
            # A trailing "and search"/"and then navigate"/etc clause means
            # this is really two actions - without this guard the greedy
            # target group swallowed the second clause whole (e.g. "search
            # amazon and then buy the cheapest one" became one bogus query).
            if not re.search(r"\b(?:and|then)\s+(?:search|find|look up|go to|navigate|open)\b", target_text):
                # "google calendar/docs/drive..." name Google PRODUCTS, not a search
                # verb + query; let specific intent branches handle them.
                google_products = ("calendar", "docs", "drive", "meet", "sheets", "slides", "keep", "forms")
                if not (web_only.group(0).lower().startswith("google ") and target_text.split() and target_text.split()[0] in google_products):
                    return {
                        "type": "browser_action",
                        "app": self._resolve_default_browser(),
                        "action": "search",
                        "target": target_text,
                    }

        navigate_only = re.match(
            r"^(?:go to|navigate to|open url)\s+(?P<target>.+)$",
            normalized,
        )
        if navigate_only:
            target_text = navigate_only.group("target").strip()
            # Same guard as web_only above: "navigate to amazon.in and search
            # for laptops" was matching whole, with the greedy target group
            # swallowing "and search for laptops" into the navigation target
            # instead of decomposing into two real steps.
            if not re.search(r"\b(?:and|then)\s+(?:search|find|look up|go to|navigate|open)\b", target_text):
                return {
                    "type": "browser_action",
                    "app": self._resolve_default_browser(),
                    "action": "navigate",
                    "target": target_text,
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
        #
        # create_task, complete_task, schedule_reminder, and add_calendar_event
        # used to have bare zero-extraction matches here ("create task" ->
        # create_task with no title/description at all, "send email" -> no
        # recipient/subject/body). Those intents ARE reachable through the
        # Brain tier's business_ops tool (create_task/complete_task/
        # calendar_event/schedule_reminder all have working handlers in
        # _execute_business_action), which can actually extract real
        # parameters from the sentence - so the bare shortcuts were removed
        # in favor of letting Brain parameterize them correctly. NOTE:
        # create_project and meeting_agenda are NOT removed despite looking
        # similar - the tool registry lists "project"/"meeting_agenda" as
        # selectable actions but _execute_business_action has no handler
        # branch for either, so Brain cannot actually complete them; removing
        # their regex shortcuts would make those two intents unreachable.
        if any(phrase in normalized for phrase in ["list tasks", "show tasks", "my tasks"]):
            return {"type": "list_tasks"}

        if any(phrase in normalized for phrase in ["create project", "new project", "start project"]):
            return {"type": "create_project"}

        if any(phrase in normalized for phrase in ["daily plan", "today's plan", "schedule today"]):
            return {"type": "daily_plan"}

        if any(phrase in normalized for phrase in ["meeting agenda", "agenda for"]):
            return {"type": "meeting_agenda"}

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

        if any(phrase in normalized for phrase in ["email template", "generate email", "draft email"]):
            return {"type": "email_template"}

        if any(phrase in normalized for phrase in ["check email", "email status"]):
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

        # Word-boundary match: a plain substring check on "news" matched
        # "newsletter" ("show me the latest newsletter"), wrongly claiming it
        # as a news-API request. "news api"/"latest news" both already
        # contain the standalone word "news", so one boundary check covers
        # all three phrases.
        if re.search(r"\bnews\b", normalized):
            return {"type": "news_api"}

        if any(phrase in normalized for phrase in ["stock", "stock price", "stock market"]):
            return {"type": "stock_api"}

        if any(phrase in normalized for phrase in ["business dashboard", "business analytics", "kpi dashboard"]):
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

        if any(phrase in normalized for phrase in ["bi dashboard", "analytics dashboard", "power bi"]):
            return {"type": "bi_dashboard"}

        if any(phrase in normalized for phrase in ["create report", "analytics report", "generate report"]):
            return {"type": "create_report"}

        if any(phrase in normalized for phrase in ["real-time monitor", "monitor system", "live monitoring"]):
            return {"type": "real_time_monitor"}

        if "open youtube" in normalized and "search" not in normalized:
            return {
                "type": "browser_action",
                "app": self._resolve_default_browser(),
                "action": "navigate",
                "target": "https://www.youtube.com",
            }

        if "open google" in normalized and "search" not in normalized:
            return {
                "type": "browser_action",
                "app": self._resolve_default_browser(),
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
            intent = {"type": "open_application", "app": app_open.group("app").strip()}
            # Browser privacy modifiers: "open incognito in chrome",
            # "open chrome private window" etc.
            if "incognito" in normalized or "private" in normalized:
                browser = "edge" if "edge" in normalized else ("brave" if "brave" in normalized else "chrome")
                intent["app"] = browser
                intent["args"] = ["--incognito"] if browser != "brave" else ["--incognito"]
            return intent

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

        # Vision: screen understanding and screenshots
        if any(
            phrase in normalized
            for phrase in [
                "what is on my screen", "what's on my screen", "whats on my screen",
                "analyze my screen", "analyze the screen", "describe my screen",
                "describe the screen", "read my screen", "what do you see",
            ]
        ):
            return {"type": "screen_qa"}

        if any(
            phrase in normalized
            for phrase in ["take a screenshot", "take screenshot", "capture my screen", "capture the screen", "grab a screenshot"]
        ):
            return {"type": "screenshot"}

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

        # "tidy up my downloads folder" means the same thing as "organize"
        # it, and was the phrasing that actually got used.
        if any(verb in normalized for verb in
               ("organize", "organise", "tidy", "clean up", "sort out", "declutter")) \
                and any(word in normalized for word in
                        ["desktop", "download", "document", "folder", "directory"]):
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
            # "called"/"titled" as well as "named" - this branch knew only
            # "named", so "create a file called demo.txt" was saved literally
            # as "called demo.txt". _derive_filename had already been fixed
            # for this, but this parser never reached it.
            r"^(?:create|make|write)\s+(?:a\s+)?(?:new\s+)?file"
            r"(?:\s+(?:named|called|titled))?\s+(?P<name>.+?)"
            r"(?:\s+(?:with\s+(?:the\s+)?(?:content|text)|containing|that\s+says)\s+(?P<content>.+))?$",
            normalized,
        )
        if create_file:
            # Run the captured name through the shared deriver so any leftover
            # filler ("called", "a", "the") is stripped in exactly one place.
            filename = self._derive_filename(create_file.group("name").strip().strip('"'))
            return {
                "type": "create_file",
                "path": str(self._documents_dir() / filename),
                "content": (create_file.group("content") or "").strip(),
            }

        return None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Ensure a bare domain/site token has a scheme, mirroring WebAgent._normalize_url."""

        cleaned = (url or "").strip()
        if not cleaned:
            return cleaned
        if cleaned.startswith(("http://", "https://")):
            return cleaned
        return f"https://{cleaned}"

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
                "command": "shutdown /s /t 10",
                "description": "shut down the system",
            },
            "restart": {
                "phrases": ["restart system", "restart laptop", "reboot system", "reboot laptop"],
                "command": "shutdown /r /t 10",
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
                "unsupported_reason": "Unlocking must use the operating system's secure authentication flow; VEGA should not store, type, or bypass passwords.",
            }
        return None

    def _get_search_engine_url_template(self) -> str:
        """Search-engine URL template: saved user preference first, config fallback.

        Extends the same save_user_preference/get_user_preference pattern
        already used for default_browser - "remember that
        default_search_engine is bing" now changes what "search for X"
        opens, the same way a saved default_browser already changes what
        "open browser" launches. Accepts either a known engine name or a
        raw "...{query}..." template.
        """
        preferred = self.memory.get_user_preference("default_search_engine", None)
        if preferred:
            preferred_key = str(preferred).strip().lower()
            if preferred_key in self.SEARCH_ENGINE_TEMPLATES:
                return self.SEARCH_ENGINE_TEMPLATES[preferred_key]
            if "{query}" in str(preferred):
                return str(preferred)
        return self.config.get("web_automation", {}).get("search_engine_url", "https://www.google.com/search?q={query}")

    def _build_search_target_for_site(self, url: str, query: str) -> str:
        """Build a best-effort search URL for known site domains."""

        target = url.lower()
        if "amazon." in target:
            return f"https://www.amazon.in/s?k={quote_plus(query)}"
        if "flipkart." in target:
            return f"https://www.flipkart.com/search?q={quote_plus(query)}"
        if "google." in target:
            return self._get_search_engine_url_template().format(query=quote_plus(query))
        if "bing." in target:
            return f"https://www.bing.com/search?q={quote_plus(query)}"
        return self._get_search_engine_url_template().format(query=quote_plus(query))

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
            app_name = str(intent.get("app", "")).strip()
            # Generic "browser" resolves to the user's saved preference
            # (autonomy saves this when they say 'use edge from now on').
            if app_name.lower() == "browser":
                app_name = self._resolve_default_browser()
            step_result = self.agents["system"].open_application(app_name, args=intent.get("args"))

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
            # A person says "mark call supplier as done", never a uuid. This
            # demanded task_id and failed with "Task ID required", which made
            # the feature unreachable from natural language.
            task_id = intent.get("task_id")
            title = (intent.get("title") or "").strip()

            if not task_id and title:
                wanted = title.lower()
                tasks = getattr(self.agents["business"], "tasks", []) or []
                open_tasks = [
                    t for t in tasks
                    if str(t.get("status", "")).lower() != "completed"
                ]
                exact = [t for t in open_tasks if str(t.get("title", "")).lower() == wanted]
                partial = [t for t in open_tasks if wanted in str(t.get("title", "")).lower()]
                matches = exact or partial

                if len(matches) == 1:
                    task_id = matches[0].get("id")
                elif len(matches) > 1:
                    # Ambiguous: ask rather than completing the wrong one.
                    names = [str(t.get("title", "")) for t in matches[:5]]
                    step_result = {
                        "success": False,
                        "error": (f"{len(matches)} open tasks match '{title}': "
                                  + ", ".join(names)
                                  + ". Which one did you mean?"),
                        "candidates": names,
                    }
                    task_id = None
                    title = ""
                else:
                    step_result = {
                        "success": False,
                        "error": f"No open task matching '{title}'.",
                    }
                    title = ""

            if task_id:
                step_result = self.agents["business"].update_task_status(task_id, "completed")
            elif title:
                step_result = {"success": False,
                               "error": "Tell me which task to complete."}

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
            step_result = self._stage_or_send_email(
                to_email=intent.get("to_email"),
                subject=intent.get("subject"),
                body=intent.get("body"),
                priority=intent.get("priority", "normal"),
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

        elif intent_type == "create_document":
            # The direct parser can now recognise "create a document about X",
            # which previously fell through to the Brain tier and was answered
            # with a Google search. Route it to the real document tool.
            topic = intent.get("topic") or intent.get("title") or ""
            step_result = self._execute_document_action(
                "create_document",
                {
                    "title": topic,
                    "topic": topic,
                    "content": intent.get("content") or "",
                    "kind": intent.get("kind") or "document",
                },
                command,
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
            pending_outward = self.memory.recall_short_term("pending_outward_action")
            pending_critical = self.memory.recall_short_term("pending_critical_command")
            if pending:
                step_result = self.agents["system"].run_command(
                    pending.get("command", ""),
                    shell=pending.get("shell", "powershell"),
                    confirmed=True,
                )
                self.memory.remember_short_term("pending_system_command", None)
                step_result["confirmed_command"] = True
            elif pending_outward and pending_outward.get("action") == "send_email":
                payload = pending_outward.get("payload", {})
                step_result = self.agents["business"].send_email_notification(**payload)
                self.memory.remember_short_term("pending_outward_action", None)
                step_result["confirmed_action"] = "send_email"
            elif pending_critical:
                # Automated safety review was unavailable and the user
                # approved anyway - re-run the original command with the
                # gate bypassed exactly once.
                original = pending_critical.get("command", "")
                self.memory.remember_short_term("pending_critical_command", None)
                self._critical_gate_bypass = original
                try:
                    rerun = await self.process_command(original)
                finally:
                    self._critical_gate_bypass = None
                step_result = {
                    "success": bool(rerun.get("success")),
                    "confirmed_command": True,
                    "message": f"Confirmed and executed: {original[:80]}",
                    "rerun_result": rerun,
                    **({"error": rerun.get("error")} if rerun.get("error") else {}),
                }
            else:
                step_result = {"success": False, "error": "No pending system command to confirm."}

        elif intent_type == "cancel_system_command":
            pending = self.memory.recall_short_term("pending_system_command")
            pending_outward = self.memory.recall_short_term("pending_outward_action")
            pending_critical = self.memory.recall_short_term("pending_critical_command")
            self.memory.remember_short_term("pending_system_command", None)
            self.memory.remember_short_term("pending_outward_action", None)
            self.memory.remember_short_term("pending_critical_command", None)
            if pending_critical and not pending and not pending_outward:
                step_result = {
                    "success": True,
                    "cancelled": True,
                    "command": pending_critical.get("command"),
                    "message": "Pending command cancelled.",
                }
            elif pending_outward and not pending:
                step_result = {
                    "success": True,
                    "cancelled": True,
                    "action": pending_outward.get("action"),
                    "message": "Pending action cancelled.",
                }
            else:
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
            step_result = {"success": True, **self.agents["system"].get_network_info()}

        elif intent_type == "disk_drives":
            step_result = {
                "success": True,
                "drives": self.agents["system"].get_disk_usage_all_drives(),
            }

        elif intent_type == "screen_qa":
            question = intent.get("question")
            vision_result = await self.agents["vision"].understand_screen(question)
            if vision_result.get("error"):
                step_result = {"success": False, "error": str(vision_result["error"])}
            else:
                step_result = {"success": True, **vision_result}

        elif intent_type == "transcription_noise":
            step_result = {
                "success": False,
                "error": (
                    f"I heard {intent.get('heard')!r}, which is background noise "
                    "rather than speech, so I have not acted on it."
                ),
            }

        elif intent_type == "top_processes":
            step_result = self._top_processes(intent.get("by", "memory"))

        elif intent_type == "calculate":
            from core.sandbox import evaluate_expression
            step_result = evaluate_expression(intent.get("expression", ""))
            if step_result.get("success"):
                step_result["message"] = (
                    f"{intent.get('original', 'Result')} = {step_result.get('result')}"
                )

        elif intent_type == "open_folder":
            step_result = self._open_named_folder(intent.get("folder"))

        elif intent_type == "remove_team_member":
            step_result = self.agents["business"].remove_team_member(
                name=intent.get("name")
            )

        elif intent_type == "delete_tasks":
            step_result = self.agents["business"].delete_task(
                title=intent.get("title"),
                delete_all=bool(intent.get("all")),
            )

        elif intent_type == "site_search":
            step_result = await self._search_within_site(
                intent.get("site"), intent.get("query")
            )

        elif intent_type == "open_file":
            step_result = self._open_named_file(
                intent.get("filename"), intent.get("where")
            )

        elif intent_type == "delete_named_file":
            target = self._locate_named_file(
                intent.get("filename"), intent.get("where")
            )
            if not target:
                step_result = {
                    "success": False,
                    "error": (f"I could not find {intent.get('filename')!r}. "
                              "Tell me the folder and I will look there."),
                }
            else:
                step_result = self.agents["file"].delete_file(str(target))
                if step_result.get("success"):
                    step_result["message"] = f"Deleted {target}"

        elif intent_type == "self_report":
            step_result = self._describe_self(intent.get("topic"))

        elif intent_type == "extract_text":
            # OCR the screen. Without this branch the intent fell through to
            # the web tool, which received no query and failed with
            # "Search query missing" - a screen-reading request answered by
            # a broken web search.
            text = await asyncio.to_thread(self.agents["vision"].extract_text_ocr)
            cleaned = (text or "").strip()
            if cleaned:
                step_result = {
                    "success": True,
                    "screen_text": cleaned[:4000],
                    "characters": len(cleaned),
                }
            else:
                step_result = {
                    "success": False,
                    "error": ("I could not read any text from the screen. "
                              "Tesseract may not be installed, or the screen "
                              "may have no readable text on it."),
                }

        elif intent_type == "create_spreadsheet":
            # "create a spreadsheet of my tasks" used to list the tasks
            # instead of producing a file.
            subject = intent.get("subject") or intent.get("title") or "data"
            rows = []
            if re.search(r"\btasks?\b", str(subject), re.IGNORECASE):
                tasks = getattr(self.agents["business"], "tasks", []) or []
                rows = [["Title", "Status", "Priority", "Due"]] + [
                    [t.get("title", ""), t.get("status", ""),
                     t.get("priority", ""), t.get("due_date", "")]
                    for t in tasks[:500]
                ]
            step_result = self._execute_document_action(
                "create_spreadsheet",
                {"title": subject, "subject": subject, "rows": rows},
                command,
            )

        elif intent_type == "screenshot":
            shot = await asyncio.to_thread(self.agents["vision"].capture_screen, save=True)
            shot_path = None
            try:
                shots_dir = Path(self.config["paths"]["data"]) / "screenshots"
                latest = sorted(shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
                if latest:
                    shot_path = str(latest[-1])
            except Exception:
                pass
            step_result = {
                "success": bool(shot),
                "message": "Screenshot captured." if shot else "Screenshot failed.",
                **({"path": shot_path} if shot_path else {}),
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
            # CPU/IO-bound and can take seconds per port - off the event
            # loop so it doesn't stall the reminders/remote-queue workers.
            step_result = await asyncio.to_thread(
                self.agents["system"].scan_ports,
                intent.get("host"),
                intent.get("ports", "common"),
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
            step_result = await asyncio.to_thread(self.agents["file"].analyze_disk_usage, intent.get("path", "."))

        elif intent_type == "find_duplicates":
            step_result = await asyncio.to_thread(self.agents["file"].find_duplicate_files, intent.get("path", "."))

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
            step_result = self.agents["file"].create_file(intent["path"], intent.get("content", ""))

        else:
            step_result = {"success": False, "error": f"Unsupported direct intent: {intent_type}"}

        step_result.setdefault("intent", intent_type)
        self._record_action_stats(self._agent_for_action(intent_type), intent_type, bool(step_result.get("success")))
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
                params["app"] = self._resolve_default_browser()
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

    def _start_task_record(self, command: str, steps_total: int) -> Optional[int]:
        """Create a durable task record; never let a storage failure block execution."""
        try:
            return self.memory.create_task_record(command, steps_total)
        except Exception as exc:
            logger.warning("Task record creation failed without blocking execution: {}", str(exc))
            return None

    def _update_task_record(self, task_id: Optional[int], **fields):
        if task_id is None:
            return
        try:
            self.memory.update_task_record(task_id, **fields)
        except Exception as exc:
            logger.warning("Task record update failed without blocking execution: {}", str(exc))

    def _finish_task_record(self, task_id: Optional[int], success: bool):
        self._update_task_record(task_id, status="done" if success else "failed")

    async def _execute_plan(self, plan: Dict[str, Any], original_command: str) -> Dict[str, Any]:
        """Execute a council-produced action plan."""

        logger.info("Executing plan...")
        results = []
        action_plan = self._normalize_action_plan(plan, original_command)
        task_id = self._start_task_record(original_command, len(action_plan))

        for step in action_plan:
            try:
                action_type = step.get("action", step.get("type", "unknown"))
                params = step.get("params", step)

                logger.debug("Executing step: {}", action_type)
                step_result = await self._route_action(action_type, params, original_command)
                step_result.setdefault("action", action_type)
                step_result.setdefault("agent", step.get("agent", self._agent_for_action(action_type)))
                results.append(step_result)
                self._update_task_record(task_id, steps_completed=len(results))
                if not step_result.get("success"):
                    self._update_task_record(task_id, last_error=str(step_result.get("error") or "Step failed"))
                await asyncio.sleep(self.execution_pause_seconds)

            except Exception as exc:
                logger.error("Step execution failed: {}", str(exc))
                results.append({"success": False, "action": action_type, "error": str(exc)})
                self._update_task_record(task_id, steps_completed=len(results), last_error=str(exc))

        success_count = sum(1 for result in results if result.get("success"))
        logger.success("Execution complete: {}/{} steps succeeded", success_count, len(results))
        overall_success = success_count == len(results) and len(results) > 0
        self._finish_task_record(task_id, overall_success)

        return {
            "success": overall_success,
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
        """Normalize one LLM/council step into VEGA's routed action format."""

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

    def _warm_up_lazy_agents(self) -> None:
        """Build the expensive agents in the background, off the request path.

        The learning agent's import chain ends at PyTorch, roughly ten
        seconds. Lazily loading it kept that cost out of startup, which was
        right - but it moved the cost onto whoever typed the first
        instruction, which is worse, because they are waiting and startup is
        not.

        This pays it in the gap where nobody is waiting. Purely an
        optimisation: if the user gets there first the normal lazy path
        still runs, and nothing anywhere depends on this having completed.
        """
        def _warm():
            try:
                self.agents["learning"]
            except Exception as exc:
                logger.debug("Agent warm-up skipped: {}", str(exc)[:120])

            # Make the language model resident too. Loading it costs about
            # five seconds off disk, and whoever asks the first question
            # that needs it should not be the one who pays that. One tiny
            # generation is enough to bring it in and keep it there.
            try:
                import requests
                ollama_cfg = self.config.get("ollama") or {}
                model = ((self.config.get("council_mode") or {}).get("primary_model")
                         or (self.config.get("conversation") or {}).get("model"))
                if not model:
                    return
                requests.post(
                    f"{ollama_cfg.get('host', 'http://127.0.0.1:11434')}/api/generate",
                    json={"model": model, "prompt": "hi", "stream": False,
                          "keep_alive": str(ollama_cfg.get("keep_alive", "30m")),
                          "options": {"num_predict": 1}},
                    timeout=90,
                )
                logger.debug("Language model warmed and resident")
            except Exception as exc:
                logger.debug("Model warm-up skipped: {}", str(exc)[:120])

        threading.Thread(target=_warm, name="agent-warmup", daemon=True).start()

    def _react_loop_enabled(self) -> bool:
        """Whether compound instructions go to the reasoning loop.

        A flag rather than a code change, so the execution path can be put
        back without a deploy if it turns out worse in real use than it was
        on the benchmark.
        """
        return bool((self.config.get("execution") or {}).get("use_react_loop", True))

    async def _run_react_loop(self, command: str) -> Dict[str, Any]:
        """Run one instruction through think/act/observe.

        Falls back to the previous autonomous path on any failure: an
        experiment in how instructions are executed must not be able to
        make the system worse than it was.
        """
        from core.progress import update as _progress
        from core.react_loop import ReactLoop

        loop = getattr(self, "_react_loop", None)
        if loop is None:
            loop = self._react_loop = ReactLoop(self)

        try:
            _progress("Working out the steps")
            outcome = await loop.run(command)
            result = outcome.as_dict()
            if result.get("success"):
                return result

            # The loop ran and did not get there. Say why rather than
            # reporting a bare failure - "stopped after 6 steps" is
            # actionable, "failed" is not.
            logger.info("ReAct loop did not complete: {}", result.get("stop_reason"))
            result.setdefault(
                "error",
                f"I worked through {result.get('steps_completed', 0)} step(s) and "
                f"stopped: {result.get('stop_reason') or 'no further progress'}.",
            )
            return result
        except Exception as exc:
            logger.warning("ReAct loop failed ({}), using the planner instead: {}",
                           type(exc).__name__, str(exc)[:120])
            plan = self.autonomy.plan(
                command,
                direct_intent=None,
                context=self._build_autonomy_context(),
            )
            fallback = await self._execute_autonomous_decision(plan, command)
            fallback["tier"] = "autonomous"
            fallback["react_fallback_reason"] = f"{type(exc).__name__}: {exc}"
            return fallback

    _classifier = None
    _argument_free_intents = None

    def _classify_intent(self, command: str):
        """Ask the learned classifier what the rules could not work out.

        Returns an intent dict ready to dispatch, or None. Deliberately
        conservative: it answers only for intents that never take arguments,
        and only above a confidence where it was right every time on the
        measured set. It predicts WHAT is wanted, not what it is wanted
        ABOUT - so "delete the task called X" is exactly the shape it must
        not be trusted with.
        """
        execution = self.config.get("execution") or {}
        if not execution.get("use_intent_classifier", True):
            return None

        cls = type(self)
        if cls._classifier is None:
            try:
                from learning.intent_classifier import IntentClassifier
                model = IntentClassifier()
                if not model.load("data/intent_classifier.json"):
                    cls._classifier = False       # absent is normal, not an error
                    return None
                cls._classifier = model

                free = json.loads(
                    Path("data/argument_free_intents.json").read_text(encoding="utf-8")
                )
                cls._argument_free_intents = set(free.get("intents") or [])
            except Exception as exc:
                logger.debug("Intent classifier unavailable: {}", str(exc)[:120])
                cls._classifier = False
                return None
        if cls._classifier is False:
            return None

        # A question ABOUT something is not an instruction to do something.
        # "where have u stored" was classified as stock_api and acted on,
        # because a nearest-centroid model must return its nearest centroid
        # even when nothing is close. It has no way to say "this is not a
        # command at all", so that judgement has to happen out here.
        if _QUESTION_OPENER.match(command or ""):
            return None

        try:
            prediction = cls._classifier.predict(command)
        except Exception as exc:
            logger.debug("Intent classification failed: {}", str(exc)[:120])
            return None

        intent = prediction.get("intent")
        margin = float(prediction.get("margin") or 0.0)
        threshold = float(execution.get("intent_classifier_margin", 0.20))

        if (not intent or intent == "unknown"
                or intent not in (cls._argument_free_intents or set())
                or margin < threshold):
            return None

        logger.info("Intent classified as {} (margin {:.3f})", intent, margin)
        return {"type": intent, "source": "classifier", "margin": margin}

    # Preference order when nothing else decides. Edge is first because it
    # is present on every Windows install, so it is the safest last resort.
    _BROWSER_CANDIDATES = ("chrome", "msedge", "edge", "brave", "firefox",
                           "opera", "vivaldi")

    def _resolve_default_browser(self) -> str:
        """The browser to use when the user did not name one.

        Resolved against what is actually installed rather than assumed.
        "chrome" was hardcoded as the fallback in ten places; on a machine
        without Chrome that aimed every browser operation at software that
        is not there, and made "set the default browser" look broken when
        the real problem was the default itself.

        Cached per session: this shells out to locate executables, and the
        set of installed browsers does not change mid-conversation.
        """
        cached = getattr(self, "_default_browser_cache", None)
        if cached:
            return cached

        # This is reached from the parsing path, which is exercised against
        # a bare controller in tests and could be called before the agents
        # exist. Missing collaborators mean "cannot check", not a crash.
        memory = getattr(self, "memory", None)
        agents = getattr(self, "agents", None)

        def installed(name: str) -> bool:
            if agents is None:
                return False
            # Probing is expected to miss - that is what probing is - so it
            # must not narrate a warning per candidate. Looking for Chrome
            # and not finding it is the normal path on a machine without
            # Chrome, not something to tell the user about.
            logger.disable("agents.system_agent")
            try:
                return bool(self.agents["system"]._resolve_application_executable(name))
            except Exception:
                return False
            finally:
                logger.enable("agents.system_agent")

        # An explicit choice is honoured unconditionally. If the user said
        # "use edge from now on", using something else because a probe could
        # not confirm edge exists is worse than trying and failing with a
        # clear message - silently substituting for an explicit instruction
        # is never the right call.
        preferred = (memory.get_user_preference("default_browser", None)
                     if memory is not None else None)
        if preferred:
            chosen = str(preferred).strip().lower()
            self._default_browser_cache = chosen
            return chosen

        candidates = []
        configured = (self.config.get("web_automation") or {}).get("default_browser")
        if configured:
            candidates.append(str(configured).strip().lower())
        candidates.extend(self._BROWSER_CANDIDATES)

        if agents is None:
            return str(configured or "chrome").strip().lower()

        seen = set()
        for name in candidates:
            if not name or name in seen:
                continue
            seen.add(name)
            if installed(name):
                if name != candidates[0]:
                    logger.info("Default browser resolved to {} ({} unavailable)",
                                name, candidates[0])
                self._default_browser_cache = name
                return name

        # Nothing found. Return the configured value so the error the user
        # sees names what was actually attempted.
        fallback = configured or "chrome"
        logger.warning("No installed browser found; falling back to {}", fallback)
        self._default_browser_cache = fallback
        return fallback

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
        registry.register(ToolSpec(
            name="business_ops",
            agent="business",
            description="Create/complete tasks, send email notifications, schedule events and reminders.",
            actions=[
                "business", "task", "tasks", "create_task", "list_tasks",
                "complete_task", "send_email", "email", "calendar_event",
                "schedule_reminder", "schedule", "project", "meeting_agenda",
            ],
            handler=lambda action, params, context: self._execute_business_action(action, params),
        ))
        registry.register(ToolSpec(
            name="document_ops",
            agent="document",
            description=(
                "Create real Word documents and Excel spreadsheets. "
                "Params: title (document title), content (the body text), "
                "path (optional file path), rows/header (spreadsheets only)."
            ),
            actions=["create_document", "create_word_document", "create_spreadsheet", "create_excel"],
            handler=lambda action, params, context: self._execute_document_action(action, params, context),
        ))
        registry.register(ToolSpec(
            name="analytics_ops",
            agent="analytics",
            description=(
                "Report on your real tasks, projects and team: counts, completion rates, "
                "breakdowns by priority/status/category. Params: report_type "
                "('productivity'), metric (e.g. 'total_tasks', 'completed_tasks', "
                "'productivity_score', 'team_size'). Reads live records - it has no "
                "financial ledger or incident log."
            ),
            actions=["analytics", "report_metrics", "productivity_report", "metric"],
            handler=lambda action, params, context: self._execute_analytics_action(action, params),
        ))
        registry.register(ToolSpec(
            name="team_ops",
            agent="business",
            description=(
                "Manage team members and workspaces. Params: name, email, role, skills "
                "(add_team_member); role (list_team)."
            ),
            actions=["add_team_member", "list_team", "team", "assign_team_project"],
            handler=lambda action, params, context: self._execute_team_action(action, params),
        ))
        registry.register(ToolSpec(
            name="math_ops",
            agent="calculator",
            description=(
                "Evaluate a single arithmetic or math expression and return the number. "
                "Param: expression (e.g. '17/100*4500', 'sqrt(144)', 'round(mean([1,2,3]),2)'). "
                "Use Python operator syntax: ** for powers (not ^). "
                "Arithmetic only - it cannot run scripts, read files, or access the system."
            ),
            actions=["calculate", "compute", "evaluate", "math"],
            handler=lambda action, params, context: self._execute_math_action(action, params, context),
        ))
        return registry

    # Where a user means when they say "documents folder", "desktop", etc.
    _NAMED_PLACES = {
        "documents": lambda: Path.home() / "Documents",
        "document": lambda: Path.home() / "Documents",
        "desktop": lambda: Path.home() / "Desktop",
        "downloads": lambda: Path.home() / "Downloads",
        "download": lambda: Path.home() / "Downloads",
        "pictures": lambda: Path.home() / "Pictures",
        "home": lambda: Path.home(),
    }

    # Words people actually use for arithmetic, and what they mean.
    _MATH_WORDS = [
        (r"\bplus\b|\badded to\b|\band\b(?=\s*\d)", "+"),
        (r"\bminus\b|\bless\b|\bsubtract(?:ed)?\s+(?:by\s+)?", "-"),
        (r"\btimes\b|\bmultiplied by\b|\bmultiply(?:\s+by)?\b|\bx\b(?=\s*\d)", "*"),
        (r"\bdivided by\b|\bdivide(?:\s+by)?\b|\bover\b(?=\s*\d)", "/"),
        (r"\bto the power of\b|\braised to\b|\bsquared\b", "**"),
        (r"\bmodulo\b|\bmod\b|\bremainder of\b", "%"),
    ]

    def _parse_arithmetic(self, command: str) -> Optional[str]:
        """Turn a spoken arithmetic question into an expression, or None.

        Deliberately conservative: it returns None the moment the text
        contains anything it does not recognise, so a real question that
        merely mentions numbers still reaches the model.
        """
        if not command:
            return None
        text = command.strip().lower().rstrip("?！!.")

        # Strip the question framing.
        text = re.sub(
            r"^(?:hey\s+|ok\s+|okay\s+)?(?:vega[,\s]+)?"
            r"(?:what(?:'s| is| are)|calculate|compute|work out|evaluate|"
            r"tell me|how much is|solve|find)\s+",
            "", text,
        ).strip()
        text = re.sub(r"^(?:the\s+)?(?:answer|result|value)\s+(?:of|to|for)\s+", "", text)
        text = text.replace(",", "")

        if not re.search(r"\d", text):
            return None

        # "17 percent of 4500" / "17% of 4500"
        pct = re.match(
            r"^(?P<p>\d+(?:\.\d+)?)\s*(?:percent|%|per\s*cent)\s+(?:of\s+)?"
            r"(?P<n>\d+(?:\.\d+)?)$", text)
        if pct:
            return f"({pct.group('p')} / 100) * {pct.group('n')}"

        # "square root of 144"
        sqrt = re.match(r"^(?:the\s+)?squ?a?re?\s*root\s+of\s+(?P<n>\d+(?:\.\d+)?)$", text)
        if sqrt:
            return f"{sqrt.group('n')} ** 0.5"

        # "5 squared"
        sq = re.match(r"^(?P<n>\d+(?:\.\d+)?)\s+squared$", text)
        if sq:
            return f"{sq.group('n')} ** 2"

        # Word operators -> symbols.
        for pattern, symbol in self._MATH_WORDS:
            text = re.sub(pattern, f" {symbol} ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Whatever is left must be arithmetic and nothing else. If a single
        # stray word survived, this is not a sum - hand it to the model.
        if not re.fullmatch(r"[\d\s+\-*/%().]+(?:\*\*[\d\s+\-*/%().]+)*", text):
            return None
        if not re.search(r"[+\-*/%]", text):
            return None
        if len(text) > 120:
            return None
        return text

    def _top_processes(self, by: str = "memory", limit: int = 8) -> Dict[str, Any]:
        """The processes actually using the machine right now.

        SystemAgent.list_processes already reported memory_percent; there
        was simply no phrasing that reached it, so "whats hogging the
        memory" went to a language model that cannot see the process table.
        """
        key = "cpu" if by == "cpu" else "memory"
        try:
            processes = self.agents["system"].list_processes()
        except Exception as exc:
            return {"success": False, "error": f"Could not read the process list: {exc}"}

        if not processes:
            return {"success": False, "error": "The process list came back empty."}

        ranked = sorted(
            processes, key=lambda p: (p.get(key) or 0), reverse=True
        )[:limit]

        # No "message" here on purpose: _display_step_result renders the
        # ranked list itself, and returning both printed it twice.
        return {
            "success": True,
            "ranked_by": key,
            "processes": ranked,
        }

    def _open_named_folder(self, folder: Optional[str]) -> Dict[str, Any]:
        """Open a folder in the file explorer.

        "open the downloads folder" was being read as an application named
        "the downloads folder", so it failed. A folder is not an app.
        """
        if not folder:
            return {"success": False, "error": "Which folder?"}

        raw = str(folder).strip().strip("\"'")
        key = raw.lower().removeprefix("the ").removeprefix("my ").strip()

        target: Optional[Path] = None
        if key in self._NAMED_PLACES:
            target = self._NAMED_PLACES[key]()
        else:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                target = candidate
            else:
                # A bare name - look for it under the usual places.
                for root_fn in (lambda: Path.home(),
                                lambda: Path.home() / "Documents",
                                lambda: Path.home() / "Desktop",
                                lambda: Path.home() / "Downloads",
                                lambda: Path.cwd()):
                    root = root_fn()
                    try:
                        for child in root.iterdir():
                            if child.is_dir() and child.name.lower() == key:
                                target = child
                                break
                    except (OSError, PermissionError):
                        continue
                    if target:
                        break

        if target is None:
            known = ", ".join(sorted(set(self._NAMED_PLACES)))
            return {
                "success": False,
                "error": f"I could not find a folder called {raw!r}. "
                         f"I know these by name: {known}. "
                         "Otherwise give me the full path.",
            }

        if not target.is_dir():
            return {"success": False, "error": f"{target} is not a folder."}

        try:
            os.startfile(str(target))  # noqa: S606 - Windows shell open
        except AttributeError:
            subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            return {"success": False, "error": f"Could not open {target}: {exc}"}

        return {
            "success": True,
            "path": str(target),
            "message": f"Opened {target}",
        }

    async def _search_within_site(
        self, site: Optional[str], query: Optional[str]
    ) -> Dict[str, Any]:
        """Search inside a site, in one tab.

        "go to amazon.in and search for laptops" used to open the site in
        one tab and then run a separate Google search in another. It is
        one action: go to that site's own search results.
        """
        if not site or not query:
            return {"success": False, "error": "I need both a site and something to search for."}

        host = str(site).strip().lower().removeprefix("https://").removeprefix("http://")
        host = host.removeprefix("www.").strip("/")
        term = quote_plus(str(query).strip())

        # Sites whose search URL is not /search?q=
        patterns = {
            "amazon.": "https://www.{host}/s?k={term}",
            "flipkart.com": "https://www.{host}/search?q={term}",
            "youtube.com": "https://www.{host}/results?search_query={term}",
            "wikipedia.org": "https://en.{host}/w/index.php?search={term}",
            "github.com": "https://{host}/search?q={term}",
            "reddit.com": "https://www.{host}/search/?q={term}",
            "ebay.": "https://www.{host}/sch/i.html?_nkw={term}",
            "stackoverflow.com": "https://{host}/search?q={term}",
        }
        url = None
        for marker, template in patterns.items():
            if marker in host:
                url = template.format(host=host, term=term)
                break
        if url is None:
            url = f"https://{host}/search?q={term}"

        result = await self.agents["web"].navigate_to_url(url)
        if isinstance(result, dict):
            result.setdefault("url", url)
            if result.get("success"):
                result["message"] = f"Searched {host} for {query!r}"
        return result

    def _locate_named_file(self, filename: str, where: Optional[str] = None) -> Optional[Path]:
        """Find a file the user named, searching the places they mean.

        "just open my_tasks.xlsx from documents folder" used to reach the
        model, which turned it into a web search. The file was sitting in
        the user's Documents folder the whole time.
        """
        if not filename:
            return None
        name = str(filename).strip().strip("\"'")

        roots = []
        if where:
            key = str(where).strip().lower().replace(" folder", "")
            if key in self._NAMED_PLACES:
                roots.append(self._NAMED_PLACES[key]())
            else:
                candidate = Path(where).expanduser()
                if candidate.is_dir():
                    roots.append(candidate)
        roots += [
            Path.home() / "Documents", Path.home() / "Desktop",
            Path.home() / "Downloads", Path.cwd(),
            Path(DEFAULT_CONFIG_PATH).parent.parent,
        ]

        direct = Path(name).expanduser()
        if direct.is_file():
            return direct

        for root in roots:
            try:
                if not root or not root.is_dir():
                    continue
                exact = root / name
                if exact.is_file():
                    return exact
                for hit in root.glob(f"**/{name}"):
                    if hit.is_file():
                        return hit
            except Exception:
                continue
        return None

    def _open_named_file(self, filename: str, where: Optional[str] = None) -> Dict[str, Any]:
        """Open a file with whatever application the OS associates with it."""
        target = self._locate_named_file(filename, where)
        if not target:
            return {
                "success": False,
                "error": (f"I could not find {filename!r}. Tell me which folder "
                          "it is in and I will open it."),
            }
        try:
            if sys.platform == "win32":
                os.startfile(str(target))          # noqa: S606 - user asked
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return {
                "success": True,
                "path": str(target),
                # The file exists and the OS accepted the request. Whether
                # an application actually came up - and whether it could
                # read the file - is not visible from here, so do not
                # claim more than the handoff.
                "verified": False,
                "note": "Handed to the OS; the file exists and opening was requested.",
                "message": f"Opened {target.name}",
            }
        except Exception as exc:
            return {"success": False, "error": f"Could not open {target.name}: {exc}"}

    def _describe_self(self, topic: Optional[str]) -> Dict[str, Any]:
        """Answer questions about this system from FACT, not from the model.

        Asked several times in one session - which model, which folder, what
        can you do - and answered by a 3B model with no way to know, so it
        invented answers. All of this is knowable locally.
        """
        config = self.config or {}
        council = config.get("llm_council", {})
        root = Path(DEFAULT_CONFIG_PATH).parent.parent

        if topic == "model":
            models = {
                role: (spec or {}).get("model")
                for role, spec in council.items()
                if isinstance(spec, dict) and spec.get("model")
            }
            return {
                "success": True,
                "message": (
                    "I run entirely on local models through Ollama - nothing is "
                    "sent to any external service."
                ),
                "models_by_role": models,
                "conversation_model": config.get("conversation", {}).get("model"),
                "embedding_model": config.get("embeddings", {}).get("model"),
            }

        if topic == "location":
            return {
                "success": True,
                "message": f"My code and data live in {root}",
                "project_root": str(root),
                "data_directory": str(root / config.get("paths", {}).get("data", "data")),
                "entry_point": str(root / "main.py"),
            }

        # capabilities
        tools = []
        for tool in self.get_tool_manifest():
            tools.append({
                "tool": tool.get("name"),
                "does": str(tool.get("description", ""))[:110],
            })
        return {
            "success": True,
            "message": "Everything below runs locally on this machine.",
            "capabilities": tools,
        }

    def _execute_document_action(self, action_type: str, params: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Execute document/spreadsheet-generation actions routed from plans."""

        from core.document_tools import create_word_document, create_spreadsheet

        # Accept the key names models actually emit, not just the ones the
        # handler was originally written against - live routing showed the
        # model sending {"name": "notes"} for a document whose title/body
        # the handler then never saw (audit finding H-3).
        title = (
            params.get("title") or params.get("name") or params.get("topic")
            or params.get("filename") or params.get("document_name")
        )
        body_text = (
            params.get("content") or params.get("body") or params.get("text")
            or params.get("summary")
        )

        if action_type in ("create_spreadsheet", "create_excel"):
            sheet_name = title or params.get("sheet_name") or "Sheet1"
            path = params.get("path") or str(self._documents_dir() / f"{self._slugify_filename(sheet_name)}.xlsx")
            return create_spreadsheet(
                path,
                sheet_name=sheet_name,
                rows=params.get("rows") or [],
                header=params.get("header"),
            )

        # create_document / create_word_document. Only fall back to the raw
        # command text for the TITLE, never for the filename - deriving the
        # filename from the whole sentence is what produced artifacts like
        # "make a word document called notes with the text hello.docx".
        sections = params.get("sections")
        if not sections:
            sections = [body_text] if body_text else []
        if not title:
            title = context or "Document"
        filename_source = (
            params.get("title") or params.get("name") or params.get("filename")
            or params.get("document_name") or params.get("topic") or "document"
        )
        path = params.get("path") or str(self._documents_dir() / f"{self._slugify_filename(filename_source)}.docx")
        return create_word_document(path, title=title, sections=sections)

    def _documents_dir(self) -> Path:
        """Where generated documents land by default.

        Not Path.cwd() - that dropped generated files straight into the
        project root. Uses the user's Documents folder when it exists.
        """
        candidate = Path.home() / "Documents"
        try:
            if candidate.is_dir():
                return candidate
        except Exception:
            pass
        return Path.cwd()

    @staticmethod
    def _slugify_filename(text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_\- ]", "", text or "document").strip().replace(" ", "_")
        return slug[:60] or "document"

    def _execute_analytics_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reporting over real task/project/team records.

        These intents previously had no ToolSpec at all, so the Brain could
        not select them and they depended entirely on bare phrase matching
        with no parameter extraction (audit M-7).
        """
        analytics = self.agents["analytics"]

        metric = params.get("metric") or params.get("name")
        if action_type == "metric" or metric:
            if not metric:
                return {"success": False, "error": "Which metric? e.g. total_tasks, completed_tasks, productivity_score."}

            value = analytics._get_metric_value(str(metric))
            if value is None:
                # The name was invented rather than looked up. Say so, and
                # say what does exist - answering with a number here is how
                # "how many world heritage sites" got the answer 0.0 sourced
                # to task records.
                known = ", ".join(analytics.KNOWN_METRICS)
                return {
                    "success": False,
                    "metric": metric,
                    "error": (f"I do not track a metric called {metric!r}. "
                              f"I can report: {known}."),
                    "available_metrics": list(analytics.KNOWN_METRICS),
                }

            return {
                "success": True,
                "metric": metric,
                "value": value,
                "source": "live task/project records",
            }

        report_type = params.get("report_type") or params.get("type") or "productivity"
        data = analytics._generate_report_data(str(report_type), params)
        if not data.get("available", True):
            return {"success": False, "error": data.get("reason", "No data available."), **data}
        return {"success": True, "report_type": report_type, **data}

    def _execute_team_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Team-member management routed from plans (audit M-7)."""
        business = self.agents["business"]

        if action_type in ("add_team_member",):
            name = params.get("name") or params.get("member") or params.get("title")
            if not name:
                return {"success": False, "error": "A name is required to add a team member."}
            return business.add_team_member(
                name=name,
                email=params.get("email"),
                role=params.get("role", "member"),
                skills=params.get("skills"),
            )

        if action_type in ("assign_team_project",):
            return business.assign_team_member_to_project(
                team_member_id=params.get("team_member_id") or params.get("member_id"),
                project_id=params.get("project_id"),
            )

        return business.list_team_members(role=params.get("role"))

    def _execute_math_action(self, action_type: str, params: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Evaluate an arithmetic/math expression (core.sandbox).

        Accepts the several key names models actually emit for this. Replaces
        the previous arbitrary-Python execution tool, which was escapable -
        see core/sandbox.py for why that approach was abandoned entirely.
        """
        from core.sandbox import evaluate_expression

        expression = (
            params.get("expression") or params.get("expr") or params.get("query")
            or params.get("code") or params.get("calculation") or params.get("input") or ""
        )
        if not expression:
            return {
                "success": False,
                "error": "No expression provided. Pass the arithmetic to evaluate as 'expression'.",
            }
        return evaluate_expression(str(expression))

    def _stage_or_send_email(self, to_email: str, subject: str, body: str, priority: str = "normal") -> Dict[str, Any]:
        """Send immediately if the user has opted out of confirmation,
        otherwise stage the send behind the existing confirm/cancel flow.

        send_email reaches a real third party and is irreversible once sent.
        The owner has chosen to send without a prompt, so the default is now
        to send; the confirm/cancel path still exists and is one setting
        away.

        Turn confirmation back on with either:
            "remember that auto_confirm_email is false"
            email.confirm_before_send = true   in config/settings.json

        The hourly budget below is deliberately kept. It does not second-
        guess the user - it stops a LOOP from sending in bulk, which is a
        different failure from a person choosing to send one message.
        """
        auto = self.memory.get_user_preference("auto_confirm_email", None)
        if auto is None:
            # Config decides when the user has expressed no preference.
            auto = not bool(
                (self.config.get("email") or {}).get("confirm_before_send", False)
            )
        if bool(auto):
            if not self._check_unattended_action_budget():
                return {
                    "success": False,
                    "error": f"Email not sent: more than {self.unattended_action_hourly_limit} unattended actions in the last hour.",
                }
            return self.agents["business"].send_email_notification(
                to_email=to_email, subject=subject, body=body, priority=priority,
            )

        warning = f"This will send an email to {to_email or '(missing recipient)'} with subject '{subject or '(no subject)'}'."
        self.memory.remember_short_term(
            "pending_outward_action",
            {
                "action": "send_email",
                "payload": {"to_email": to_email, "subject": subject, "body": body, "priority": priority},
                "warning": warning,
            },
        )
        return {
            "success": False,
            "needs_confirmation": True,
            "warning": f"{warning} Type 'confirm command' to send it or 'cancel command' to discard it.",
            "to_email": to_email,
            "subject": subject,
        }

    def _execute_business_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute business-agent actions routed from plans."""

        business = self.agents["business"]
        context = str(params.get("context") or params.get("description") or "")

        if action_type in ("send_email", "email"):
            return self._stage_or_send_email(
                to_email=params.get("to_email") or params.get("target") or "",
                subject=params.get("subject") or (params.get("query") or ""),
                body=params.get("body") or context,
            )
        if action_type in ("create_task", "task", "add_task"):
            title = params.get("title") or params.get("target") or context or "New task"
            return business.create_task(title=title, description=context)
        if action_type in ("list_tasks", "tasks"):
            return business.list_tasks()
        if action_type in ("complete_task", "update_task_status"):
            return business.update_task_status(
                task_id=params.get("task_id"),
                status=params.get("status", "completed"),
            )
        if action_type in ("calendar_event", "schedule_reminder", "schedule"):
            return business.add_calendar_event(
                title=params.get("title") or context or "Event",
                start_time=params.get("start_time"),
            )
        return {"success": False, "error": f"Unknown business action: {action_type}"}

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
        task_id = self._start_task_record(original_command, len(decomposition.get("subtasks", [])))

        for subtask in decomposition.get("subtasks", []):
            action = subtask.get("action", "general")
            params = dict(subtask.get("params", {}))

            # Captured BEFORE execution: a rollback that deletes a "newly
            # created" file must never delete a file that already existed -
            # otherwise overwriting an existing report.txt and then failing a
            # later step deleted the user's original file on rollback.
            target_path_before = params.get("path")
            path_existed_before = bool(target_path_before) and Path(target_path_before).exists()

            if action == "create_report":
                step_result = await self._build_and_save_report(
                    original_command, params.get("topic"), params["path"], results
                )
            else:
                step_result = await self._route_action(action, params, subtask.get("description", original_command))

            step_result["subtask_id"] = subtask.get("id")
            step_result["subtask_description"] = subtask.get("description")
            results.append(step_result)
            self._update_task_record(task_id, steps_completed=len(results))

            if step_result.get("success"):
                # Register rollback actions
                if action == "organize" and step_result.get("manifest_id"):
                    rollback_actions.append({
                        "type": "restore_organization",
                        "manifest_id": step_result["manifest_id"]
                    })
                elif not path_existed_before and (
                    action == "create_file" or (action == "create" and "file" in params.get("description", "").lower())
                ):
                    rollback_actions.append({
                        "type": "delete_file",
                        "path": step_result.get("path") or params.get("path")
                    })
                elif not path_existed_before and (
                    action == "create_folder" or (action == "create" and "folder" in params.get("description", "").lower())
                ):
                    rollback_actions.append({
                        "type": "delete_folder",
                        "path": step_result.get("path") or params.get("path")
                    })
            else:
                failed = True
                error_msg = step_result.get("error", "Subtask failed")
                self._update_task_record(task_id, last_error=str(error_msg))
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
        overall_success = not failed and success_count == len(results) and len(results) > 0
        self._finish_task_record(task_id, overall_success)
        return {
            "success": overall_success,
            "steps_completed": success_count,
            "steps_total": len(decomposition.get("subtasks", [])),
            "results": results,
            "decomposition": decomposition,
            "rollback_executed": failed and len(rollback_actions) > 0,
            "error": error_msg if failed else None
        }

    def _record_action_stats(self, agent: str, intent_type: str, success: bool):
        """Update per-agent and per-intent outcome counters.

        This is the visibility layer item 6 (learning-loop closure) reads
        from - real success/failure counts per intent type, not just the
        tier-level totals in tier_stats.
        """
        intent_bucket = self.intent_stats.setdefault(intent_type or "unknown", {"calls": 0, "successes": 0})
        intent_bucket["calls"] += 1
        if success:
            intent_bucket["successes"] += 1

        agent_bucket = self.agent_stats.setdefault(agent or "unknown", {"calls": 0, "successes": 0})
        agent_bucket["calls"] += 1
        if success:
            agent_bucket["successes"] += 1

    def _check_unattended_action_budget(self) -> bool:
        """Return True if another unattended action is within the hourly
        budget, recording this attempt either way.

        Applies to remote/email-triggered commands and outward-facing
        actions (send_email) - the two classes of action that can run
        without a human watching in real time, per the audit's S-2/C-2
        findings. A ring buffer of recent timestamps, not a persisted
        counter - it naturally resets as old entries age past an hour.
        """
        now = time.time()
        cutoff = now - 3600
        self._unattended_action_timestamps = [t for t in self._unattended_action_timestamps if t > cutoff]
        if len(self._unattended_action_timestamps) >= self.unattended_action_hourly_limit:
            return False
        self._unattended_action_timestamps.append(now)
        return True

    async def _route_action(self, action_type: str, params: Dict[str, Any], context: str) -> Dict[str, Any]:
        """Route an action to the most appropriate agent."""

        registry = getattr(self, "tool_registry", None)
        if not registry:
            registry = self._build_tool_registry()
            self.tool_registry = registry

        routed = await registry.execute(action_type.lower(), params, context)
        if routed.get("success") or "No registered tool" not in (routed.get("error") or ""):
            self._record_action_stats(routed.get("agent", "unknown"), action_type, bool(routed.get("success")))
            return routed

        general_result = await self._execute_general_action(context, params)
        self._record_action_stats("general", action_type, bool(general_result.get("success")))
        return general_result

    # Words that introduce a filename, and filler that must never end up IN it.
    _NAME_INTRO = r"(?:named|called|titled|name|title)"
    _LEADING_FILLER = (
        "create", "make", "new", "a", "an", "the", "file", "document", "doc",
        "note", "text", "please", "me", "to", "for", "write", "generate",
    )

    # Verbs that mean "compose this for me" rather than "copy what I said".
    _AUTHORING_RE = re.compile(
        r"\b(?:with|containing|that|which|to)\b[\w\s]{0,20}?"
        r"\b(?:code|program|script|function|class|essay|poem|story|letter|"
        r"summary|notes?|list|recipe|explanation|example|template|report|"
        r"documentation|readme|tutorial|guide)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _wants_authored_content(cls, text: str) -> bool:
        """Did the user describe content to be written, not quoted?

        "with content hello world" is a quote - _extract_inline_content
        handles that. "with code for a caesar cipher" is a commission, and
        used to produce a zero-byte file.
        """
        if not text:
            return False
        return bool(cls._AUTHORING_RE.search(text))

    @staticmethod
    def _extract_inline_content(text: str) -> str:
        """Recover file body text embedded in the request sentence.

        "create a file called notes.txt with content hello world" carries the
        body inline; when the planner did not lift it into a content param
        the file was written empty and still reported as a success.
        """
        if not text:
            return ""
        match = re.search(
            r"\b(?:with\s+(?:the\s+)?(?:content|text|body)|containing|that\s+says|saying)\s+"
            r"[\"']?(.+?)[\"']?\s*$",
            text, re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _derive_filename(text: str) -> str:
        """Pull a plausible filename out of a natural phrase.

        Two real failures this had to fix:
          "create a file called shakdown.txt with content hello world"
              -> only "named" was recognised, so the whole sentence was
                 truncated and the file was literally saved as
                 "called shakdown.txt".
          "research quantum computing and write me a report"
              -> the model's plan text became the name:
                 "To_create_a_structured_document.txt".
        """
        cls = AutonomousSystemController
        text = " ".join((text or "").strip().split())

        # Prefer an explicit "called/named X" phrase.
        match = re.search(
            rf"\b{cls._NAME_INTRO}\s+[\"']?([a-zA-Z0-9_\-. ]+?)[\"']?"
            r"(?:\s+(?:with|containing|that says|and)\b.*)?$",
            text, re.IGNORECASE,
        )
        # Otherwise take a bare token that already looks like a filename.
        if not match:
            match = re.search(r"\b([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,5})\b", text)

        name = match.group(1).strip() if match else ""

        if not name:
            name = re.sub(r"[^a-zA-Z0-9_\- ]", "", text).strip()
            # Drop the imperative preamble so the verb never becomes the name.
            words = [w for w in name.split() if w]
            while words and words[0].lower() in cls._LEADING_FILLER:
                words.pop(0)
            name = " ".join(words[:6])[:40].strip()

        # Strip any filler that survived at the front of an explicit match.
        words = [w for w in name.split() if w]
        while len(words) > 1 and words[0].lower() in cls._LEADING_FILLER:
            words.pop(0)
        name = " ".join(words)

        if not name:
            name = "vega_file"
        name = re.sub(r"[^a-zA-Z0-9_\-. ]", "", name).strip().replace(" ", "_")
        name = re.sub(r"_{2,}", "_", name).strip("_.") or "vega_file"
        if "." not in name:
            name += ".txt"
        return name

    async def _execute_file_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute file-related actions.

        async so the two genuinely CPU-bound branches below (disk_usage,
        duplicates - full-file hashing over potentially thousands of files)
        can run in a thread instead of blocking the event loop; every other
        branch here is fast enough that awaiting it directly is fine.
        ToolRegistry.execute already awaits any awaitable handler result, so
        this needed no change to how the tool is registered.
        """

        file_agent = self.agents["file"]

        # Normalize generic brain actions: bare "file"/"file_ops" with content
        # means create; without content it means list.
        if action_type in ("file", "file_ops"):
            if params.get("content") is not None:
                action_type = "create_file"
            else:
                action_type = "list_files"

        if action_type == "create_folder":
            return file_agent.create_folder(params.get("path", "./new_folder"))

        if action_type in ("create_file",):
            description = params.get("description") or params.get("context") or ""
            path = params.get("path") or self._derive_filename(description or "vega_note.txt")
            authoring_error = None
            content = params.get("content")
            if content in (None, ""):
                # The planner often puts the body in the sentence rather than
                # in a "content" param, so files were created 0 bytes and
                # reported as done. Recover it before writing nothing.
                content = self._extract_inline_content(description)
            if not str(content or "").strip() and self._wants_authored_content(description):
                # Nothing to copy, but the user described content they want
                # WRITTEN. That is the model's job, not a regex's.
                authored = await self.council.author_file_content(
                    description, str(path))
                if authored.get("success"):
                    content = authored["content"]
                else:
                    authoring_error = authored.get("error")
            result = file_agent.create_file(path, content or "")
            if result.get("success") and not (content or "").strip():
                if authoring_error:
                    # Content was the point of the request and it did not
                    # happen. An empty file is not a success here, whatever
                    # the filesystem reports.
                    result["success"] = False
                    result["error"] = (
                        f"Created {path} but could not write the content you "
                        f"asked for: {authoring_error}"
                    )
                    result["empty_file_left_at"] = str(path)
                else:
                    # Be explicit rather than claiming a clean success: an
                    # empty file is almost never what the user meant.
                    result["warning"] = (
                        f"Created {path}, but I could not work out what to put "
                        "in it, so it is empty. Tell me the content and I will "
                        "fill it."
                    )
            return result

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
            return await asyncio.to_thread(
                file_agent.analyze_disk_usage,
                params.get("path") or self._extract_known_path(params.get("description", ".")),
            )

        if action_type == "duplicates":
            return await asyncio.to_thread(
                file_agent.find_duplicate_files,
                params.get("path") or self._extract_known_path(params.get("description", ".")),
            )

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
            step_result = system_agent.run_command(params.get("command", ""), shell=shell_name)
            if step_result.get("needs_confirmation"):
                # Mirror _execute_directly's stash: without this, a dangerous
                # command reached through a plan/brain step reported
                # needs_confirmation with no way for "confirm command" to
                # find and release it.
                self.memory.remember_short_term(
                    "pending_system_command",
                    {
                        "command": params.get("command", ""),
                        "shell": shell_name,
                        "warning": step_result.get("warning"),
                        "matched_patterns": step_result.get("matched_patterns", []),
                    },
                )
            return step_result

        system_info = system_agent.get_system_info()
        return {"success": True, **system_info}

    async def _execute_vision_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute vision-related actions."""

        vision_agent = self.agents["vision"]

        if "screenshot" in action_type:
            image = await asyncio.to_thread(vision_agent.capture_screen)
            return {"success": image is not None, "message": "Screenshot captured"}

        if "ocr" in action_type:
            text = await asyncio.to_thread(vision_agent.extract_text_ocr)
            return {"success": bool(text), "text": text[:500]}

        result = await vision_agent.understand_screen(params.get("question"))
        return {"success": "error" not in result, **result}

    async def _execute_web_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute web/browser and form actions."""

        web_agent = self.agents["web"]
        browser_name = params.get("app") or params.get("browser") or self.config.get("web_automation", {}).get(
            "default_browser", "chrome"
        )

        # Normalize generic brain actions: bare "web" means search.
        if action_type == "web":
            action_type = "search"

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
            target = (
                params.get("query")
                or params.get("target")
                or params.get("description")
                or params.get("context", "")
            )
            if not target:
                return {"success": False, "error": "Search query missing."}
            return await web_agent.perform_browser_action(browser_name, "search", str(target).strip())

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
        """Fallback when a plan step matches no registered tool.

        Tries ONE level of direct-command inference; if that fails, reports an
        honest failure instead of speculatively re-planning (the old recursive
        council loop caused minute-long hangs and false successes).
        """

        description = params.get("description", context)
        inferred_intent = self._parse_direct_command(description) or self._parse_direct_command(context)
        if inferred_intent:
            return (await self._execute_directly(description, {"intent": inferred_intent}))["results"][0]

        return {
            "success": False,
            "action": params.get("action", "unknown"),
            "error": (
                f"No executable action matched for: {str(description)[:140]}. "
                "The generated plan was too vague to execute safely. "
                "Try a more specific command."
            ),
        }

    def _cache_command_strategy(self, command: str, strategy: Dict[str, Any], result: Dict[str, Any]):
        """Cache successful routing decisions.

        Only the "direct" tier round-trips cleanly through the cached
        {tier, complexity, intent} shape on replay. Brain/clarify/autonomous/
        council strategies carry extra state (plan, params, question) that the
        cache does not store, so caching them produces a strategy on replay
        that silently drops that state and can execute the wrong action with
        reported success. Restrict caching to what the schema actually covers.
        """

        if not result.get("success") or strategy.get("tier") != "direct":
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

    async def _build_and_save_report(
        self, command: str, topic: str, path: str, prior_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize a real summary from prior steps' captured text and save
        it as a real .docx - replaces the old raw-scrape-into-a-.txt-file
        report, which never actually read or understood anything it found.
        """
        from core.document_tools import create_word_document

        raw_chunks = []
        sources = []
        for result in prior_results:
            if result.get("url"):
                sources.append(result["url"])
            if result.get("text"):
                raw_chunks.append(result["text"])

        raw_text = "\n\n".join(raw_chunks)
        sections: List[Any] = []

        if raw_text.strip():
            # Fail open, same as verify_outcome: an unavailable/failing
            # summarizer must degrade the report, never abort it.
            try:
                synthesis = await self.council.summarize_findings(topic or command, raw_text)
                summary_text = synthesis.get("summary") or "Summarization was unavailable; see raw captured text below."
            except Exception as exc:
                logger.warning("Findings summarization failed, falling back to raw text: {}", str(exc))
                summary_text = "Summarization was unavailable; see raw captured text below."
        else:
            summary_text = "No source text was captured during research, so no findings could be synthesized."

        sections.append({"heading": "Summary", "body": summary_text})
        if sources:
            sections.append({"heading": "Sources", "body": "\n".join(sources)})
        if raw_text.strip():
            sections.append({"heading": "Raw captured text (for reference)", "body": raw_text[:3000]})

        doc_result = create_word_document(path, title=topic or command, sections=sections)
        doc_result["report_topic"] = topic
        return doc_result

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
            "intent_stats": self.intent_stats,
            "agent_stats": self.agent_stats,
            "unattended_actions_last_hour": len(self._unattended_action_timestamps),
            "unattended_action_hourly_limit": self.unattended_action_hourly_limit,
            "tools": self.get_tool_manifest(),
            "voice": self._get_voice_service_health() if self.voice_enabled else {"available": False, "enabled": False},
            "learning_stats": self.agents["learning"].get_learning_stats(),
            "adaptive_learning": self.agents["learning"].get_adaptive_summary()
            if hasattr(self.agents["learning"], "get_adaptive_summary") else {},
            "memory_stats": self.memory.get_memory_stats(),
            "council_stats": self.council.get_stats(),
        }

    async def _handle_remote_task(self, remote_queue: "RemoteQueue", remote_task: Dict[str, Any]):
        """Execute one claimed remote task and report/reply, under the command lock."""

        if not self._check_unattended_action_budget():
            logger.warning(
                "Remote task {} rejected: hourly unattended-action budget ({}) exceeded.",
                remote_task["id"], self.unattended_action_hourly_limit,
            )
            remote_queue.mark_failed(
                remote_task["id"],
                f"Rejected: more than {self.unattended_action_hourly_limit} unattended actions in the last hour.",
            )
            print(f"[REMOTE] Rejected {remote_task['id']}: hourly budget exceeded.")
            return

        print(f"\n[REMOTE {remote_task['source']} | {remote_task['sender']}] {remote_task['command']}")
        try:
            async with self._command_lock:
                remote_result = await self.process_command(remote_task["command"])
            if remote_result.get("success"):
                remote_queue.mark_done(
                    remote_task["id"],
                    str(remote_result.get("response") or "Task completed successfully."),
                )
                print("[REMOTE] Done.")
            else:
                remote_queue.mark_failed(
                    remote_task["id"],
                    str(remote_result.get("error") or "Task failed."),
                )
                print(f"[REMOTE] Failed: {str(remote_result.get('error'))[:120]}")

            # Email-sourced tasks get the result mailed back.
            if remote_task.get("source") == "email":
                try:
                    summary = str(
                        remote_result.get("response")
                        or ("Done. " + "; ".join(
                            str(s.get("subtask_description") or s.get("action") or "")
                            for s in (remote_result.get("results") or []) if isinstance(s, dict)
                        ))
                        or remote_result.get("error")
                        or "Completed."
                    )
                    status_word = "completed" if remote_result.get("success") else "failed"
                    # Deliberate, narrow exception to the outward-action
                    # approval gate (_stage_or_send_email): this is a status
                    # reply to a task the user themselves submitted by email,
                    # addressed only back to the verified allowed sender.
                    # Staging it for confirmation would be incoherent - the
                    # user isn't at the keyboard, which is why they emailed.
                    # It is still budgeted, and email_listener's self-send
                    # guard is what stops a reply becoming a new command.
                    reply_to = remote_task.get("sender", "")
                    allowed_senders = {
                        str(s).strip().lower()
                        for s in self.config.get("email", {}).get("allowed_senders", [])
                    }
                    if reply_to.strip().lower() not in allowed_senders:
                        print(f"[REMOTE] Reply suppressed: {reply_to} is not an allowed sender.")
                    else:
                        self.agents["business"].send_email_notification(
                            to_email=reply_to,
                            subject=f"VEGA task {status_word}: {remote_task['command'][:60]}",
                            body=f"Your command: {remote_task['command']}\n\nStatus: {status_word}\n\nResult:\n{summary[:1000]}",
                        )
                        print(f"[REMOTE] Result emailed to {reply_to}")
                except Exception as mail_exc:
                    print(f"[REMOTE] Reply email failed: {mail_exc}")
        except Exception as exc:
            remote_queue.mark_failed(remote_task["id"], f"{type(exc).__name__}: {exc}")
            print(f"[REMOTE] Failed: {exc}")

    async def _memory_maintenance_worker(self, initial_delay: float = 90.0, interval: float = 300.0):
        """Background upkeep for episodic memory: prune, then backfill
        embeddings for older episodes in bounded batches.

        Runs in a thread so the embedding calls never block the loop, and in
        small batches so it competes gently with real commands. Without this,
        semantic recall could only ever see episodes recorded after the
        feature was added (audit M-1), and the episodes table grew unbounded
        (M-4).
        """
        # 90s, not 20. At 20 it began mid-way through the user's FIRST
        # instruction and competed with it for the model.
        await asyncio.sleep(initial_delay)
        while self.running:
            try:
                await asyncio.to_thread(self.memory.prune_episodes)
                # 50 per 5-minute tick left coverage at 19% of history -
                # most recalls silently fell back to the LIKE scan (audit
                # L-3). This runs off-loop in a thread, so a larger batch
                # costs nothing interactive.
                result = await asyncio.to_thread(
                    self.memory.backfill_episode_embeddings, 300,
                    lambda: getattr(self, "_command_in_flight", False),
                )
                if result.get("remaining", 0) == 0 and result.get("embedded", 0) == 0:
                    # Nothing left to do - back off to a slow heartbeat.
                    await asyncio.sleep(interval * 4)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Memory maintenance tick skipped: {}", str(exc))
            await asyncio.sleep(interval)

    async def _remote_queue_worker(self, remote_queue: "RemoteQueue", poll_interval: float = 3.0):
        """Background task: drain the remote queue independently of the input prompt.

        Previously this only ran once per input() cycle, so a remotely
        submitted task waited for the user to finish typing before it was
        even looked at. Runs for the life of the session; cancelled by
        run_interactive on exit.
        """
        while self.running:
            try:
                remote_task = remote_queue.claim_next()
                if remote_task:
                    await self._handle_remote_task(remote_queue, remote_task)
                    continue  # check for another queued task immediately
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Remote queue worker tick failed: {}", str(exc))
            await asyncio.sleep(poll_interval)

    async def run_interactive(self):
        """Run VEGA in interactive mode with cinematic presentation."""

        self.running = True

        print("\n" + "=" * 60)
        print("AUTONOMOUS SYSTEM CONTROLLER")
        print("=" * 60)
        print("\nGreetings. I am VEGA, your advanced local AI assistant.")
        print("I'm here to help you with tasks, answer questions, and assist with your work.")

        if self.voice_enabled and self.voice_service_available:
            print("\nVoice control is active. Type 'voice' to speak a command, or type your command normally.")
        elif self.voice_enabled:
            print("\nVoice support is configured, but the local voice server is currently offline.")
            print("Type 'start voice server' to enable voice interaction.")
        else:
            print("\nI'm ready to assist through text commands. Type 'help' for what I can do.")

        print("\nHow may I assist you today?\n")

        remote_queue = RemoteQueue(Path(__file__).resolve().parent / "data" / "remote_queue.json")

        # Background workers. Both require input() to be off the event loop
        # (below) to ever actually get scheduled time - previously input()
        # blocking the loop meant the reminders loop, once started, never
        # ticked, and the remote queue only drained between typed commands.
        from core.reminders import ReminderLoop

        # speak= is deliberately a thread-dispatching wrapper, not
        # _speak_text directly. ReminderLoop.check_once() is synchronous and
        # runs inside an async task, so calling pyttsx3's runAndWait() (or
        # winsound.PlaySound) from it froze the whole event loop - including
        # the input prompt and the remote-queue worker - for the length of
        # the spoken sentence. Firing a reminder must not stall the session.
        def _speak_without_blocking(text: str):
            try:
                asyncio.get_running_loop().create_task(asyncio.to_thread(self._speak_text, text))
            except RuntimeError:
                self._speak_text(text)  # no loop running (e.g. direct unit-test call)

        reminder_loop = ReminderLoop(
            schedules_path=Path(__file__).resolve().parent / "data" / "schedules.json",
            speak=_speak_without_blocking,
        )
        background_tasks = [
            asyncio.create_task(self._remote_queue_worker(remote_queue)),
            asyncio.create_task(reminder_loop.run()),
            asyncio.create_task(self._memory_maintenance_worker()),
        ]

        try:
            while self.running:
                try:
                    # input() is blocking; run it in a thread so the event
                    # loop keeps servicing the background workers above
                    # while waiting for the user to type.
                    from core.console import prompt_input

                    if getattr(self, "_voice_mode", False):
                        # The listener blocks on the microphone inside a
                        # worker thread. asyncio cannot cancel a thread that
                        # is already running, so Ctrl+C surfaced here as
                        # CancelledError from to_thread and tore the whole
                        # process down - three forced restarts in one live
                        # session. Shield the await and handle both.
                        try:
                            command = (await asyncio.shield(
                                asyncio.to_thread(self._listen_for_voice_command)
                            ) or "").strip()
                        except (asyncio.CancelledError, KeyboardInterrupt):
                            self._voice_mode = False
                            self._voice_silence_streak = 0
                            print("\n\nVoice mode OFF - back to typing.\n")
                            continue

                        if not command:
                            # Repeated silence means the mic has stopped
                            # producing usable audio (it stopped responding
                            # entirely mid-session). Say so and hand control
                            # back rather than looping invisibly forever.
                            streak = getattr(self, "_voice_silence_streak", 0) + 1
                            self._voice_silence_streak = streak
                            if streak == 1:
                                print("  (didn't catch that - speak again, or say 'voice off')")
                            elif streak >= 4:
                                self._voice_mode = False
                                self._voice_silence_streak = 0
                                print("\nI stopped hearing anything after several tries, "
                                      "so I've switched back to typing.")
                                print("Type 'voice' to try again.\n")
                            continue

                        self._voice_silence_streak = 0
                        # Echo what was heard, labelled, so the transcript
                        # reads like a conversation instead of bare text.
                        print(f"You (voice): {command}")

                        # Whisper adds punctuation and casing, so an exact
                        # match missed "Voice off." - the exit phrase did not
                        # work in the live session.
                        spoken = re.sub(r"[^a-z ]", "", command.lower()).strip()
                        if spoken in ("voice off", "voiceoff", "stop listening",
                                      "text mode", "exit voice", "stop voice",
                                      "turn off voice", "switch to typing"):
                            self._voice_mode = False
                            self._voice_silence_streak = 0
                            print("\nVoice mode OFF - back to typing.\n")
                            continue
                    else:
                        # NOT asyncio.to_thread: that starts a new reader
                        # thread per prompt, and a cancelled await leaves
                        # the old one blocked on stdin swallowing input.
                        from core.console import read_line
                        typed = await read_line("You: ")
                        if typed is None:  # stdin closed
                            self.running = False
                            break
                        command = typed.strip()

                    if not command:
                        continue

                    if self.voice_enabled and command.lower() in ("voice", "voice on", "listen"):
                        # Enter continuous voice mode. It used to transcribe a
                        # single utterance and drop straight back to typing,
                        # so "voice" had to be retyped before every spoken
                        # command - which defeats hands-free use entirely.
                        self._voice_mode = True
                        print("\nVoice mode ON - speak your commands.")
                        print("Say or type 'voice off' (or press Ctrl+C) to go back to typing.\n")
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

                    async with self._command_lock:
                        # Tells background upkeep to stand aside; catching up
                        # on history must never make someone wait.
                        self._command_in_flight = True
                        try:
                            result = await self.process_command(command)
                        finally:
                            self._command_in_flight = False
                    self._display_result(result)
                    if self.voice_enabled:
                        # Queued, not awaited. This used to be
                        # `await asyncio.to_thread(self._speak_result, ...)`
                        # with no timeout, behind a 60-second HTTP call and
                        # a winsound.PlaySound that has no timeout at all -
                        # so any stall in the speech path froze the prompt
                        # permanently and the session stopped accepting
                        # input. Speech is cosmetic; the prompt is not.
                        self._speak_result(result)

                except KeyboardInterrupt:
                    # In voice mode Ctrl+C means "stop listening", not "quit".
                    # Previously it tore the whole session down mid-recording and
                    # left the terminal needing to be killed.
                    if getattr(self, "_voice_mode", False):
                        self._voice_mode = False
                        print("\n\nVoice mode OFF - back to typing.\n")
                        continue
                    print("\n\nUnderstood. I'll conclude our session now. Take care!")
                    self.memory.end_session()
                    self.running = False
                    break

                except Exception as exc:
                    detail = str(exc) or exc.__class__.__name__
                    logger.error("Error in interactive mode ({}): {}", exc.__class__.__name__, detail)
                    print(f"\nI encountered an issue ({exc.__class__.__name__}): {detail}")
                    print("Let me try to help you with something else.\n")
        finally:
            self.running = False
            for task in background_tasks:
                task.cancel()
            for task in background_tasks:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            await self.shutdown()

    async def shutdown(self):
        """Release external resources held for the life of the session.

        The speech thread is stopped first and with a short join, so a
        stuck utterance cannot hold up the exit the way it used to hold up
        the prompt.

        BrowserDriver.stop() had no caller anywhere in the repo, so the
        Playwright Chromium process, its Node supervisor and (with the
        persistent profile) a locked profile directory leaked on every exit.
        Only touches agents that were actually built - self.agents is lazy,
        so `.keys()` reflects what exists rather than constructing more on
        the way out.
        """
        try:
            from core import speech
            speech.shutdown()
        except Exception:
            pass

        try:
            if "web" in self.agents.keys():
                driver = getattr(self.agents["web"], "browser_driver", None)
                if driver is not None:
                    await driver.stop()
                    logger.info("Browser driver stopped cleanly.")
        except Exception as exc:
            logger.warning("Browser driver shutdown skipped: {}", str(exc))

        try:
            if "system" in self.agents.keys():
                # Only reaps subprocesses this agent actually spawned and
                # that have already exited - never the user's own apps.
                system_agent = self.agents["system"]
                for pid, proc in list(getattr(system_agent, "managed_processes", {}).items()):
                    if proc.poll() is not None:
                        system_agent.managed_processes.pop(pid, None)
        except Exception as exc:
            logger.debug("Process table cleanup skipped: {}", str(exc))

    def _display_capabilities(self):
        """Display available capabilities in a clean format."""
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
        """Render command results with polished presentation."""

        if result.get("tier") == "conversation" or result.get("mode") == "chat":
            response = result.get("response")
            if response:
                print(f"\nVEGA: {response}\n")
            elif result.get("success"):
                print("\nVEGA: I'm ready to assist you. What would you like me to help with?\n")
            else:
                print(f"\nVEGA: I'm having some difficulty with that request. {result.get('error', '')}\n")
            return

        if result.get("needs_confirmation"):
            print(f"\nVEGA: {result.get('question', 'This action requires your confirmation before I proceed.')}")
            for step_result in result.get("results", []):
                if step_result.get("warning"):
                    print(f"Note: {step_result['warning']}")
                if step_result.get("command"):
                    print(f"Command: {step_result['command']}")
            print()
            return

        if result.get("needs_clarification"):
            print(f"\nVEGA: {result.get('question', 'I need to clarify something to help you better.')}")
            suggestions = result.get("suggestions") or []
            if suggestions:
                print("Suggestions:")
                for suggestion in suggestions[:5]:
                    print(f"  - {suggestion}")
            print()
            return

        if result.get("success"):
            # Cinematic success response
            tier = result.get("tier", "unknown")
            steps_completed = result.get("steps_completed", 1)
            steps_total = result.get("steps_total", 1)

            if result.get("outcome_mismatch"):
                # Lead with the problem. Printing "completed successfully"
                # above a "Heads up: that isn't what you asked for" buried
                # the only line that mattered.
                print("\nI did something, but I don't think it's what you asked for.")
                if result.get("verification_warning"):
                    print(f"  {result['verification_warning']}")
                print("\n  What I actually did:")
                for step_result in result.get("results", []):
                    self._display_step_result(step_result)
                print("\nWant me to try again differently?")
                print()
                return

            if tier == "direct":
                print(f"\nExcellent. Task completed successfully via direct execution.")
            elif tier == "autonomous":
                print(f"\nI've successfully handled that autonomously using my planning capabilities.")
            elif tier == "sequential":
                print(f"\nExcellent. I've completed {steps_completed} of {steps_total} steps in that sequence.")
            else:
                print(f"\nSuccess. I've processed your request through the {tier} tier.")

            # Verification is advisory (it never re-runs anything) - so when
            # it flags a mismatch the user has to actually see it, otherwise
            # the check may as well not exist.
            if result.get("verification_warning"):
                print(f"\n  Heads up: {result['verification_warning']}")

            # Detailed results with polished explanations
            for step_result in result.get("results", []):
                self._display_step_result(step_result)

            print()
        else:
            # Graceful error handling
            error = result.get("error", "Unknown error")
            recovery = result.get("recovery_suggestion", "")
            
            # A deliberate safety refusal is not a malfunction. Prefixing
            # it with "I encountered an issue" made correct behaviour read
            # as a crash, which is how the live session interpreted it.
            if result.get("rejected"):
                print(f"\n{error}")
            else:
                print(f"\nI encountered an issue: {error}")
            if recovery:
                print(f"\n{recovery}")
            if not result.get("rejected"):
                print("\nWould you like me to try a different approach, or would you prefer to work on something else?")
            print()

    def _display_step_result(self, step_result: Dict[str, Any]):
        """Display individual step results with informative explanations."""
        
        if "processes" in step_result:
            # Show the column the user asked about. This always printed CPU,
            # so asking what was using the MEMORY produced a list of
            # "CPU: 0.0%" next to a ranking it did not explain.
            ranked_by = step_result.get("ranked_by")
            if ranked_by == "memory":
                print("\nTop processes by memory:")
                for process in step_result["processes"][:10]:
                    print(f"  - {process['name']} (PID: {process['pid']}, "
                          f"memory: {process.get('memory', 0):.1f}%)")
            elif ranked_by == "cpu":
                print("\nTop processes by CPU:")
                for process in step_result["processes"][:10]:
                    print(f"  - {process['name']} (PID: {process['pid']}, "
                          f"CPU: {process.get('cpu', 0):.1f}%)")
            else:
                print("\nSystem Processes:")
                for process in step_result["processes"][:10]:
                    print(f"  - {process['name']} (PID: {process['pid']}, "
                          f"CPU: {process['cpu']}%)")

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

        if step_result.get("subtask_description") and not any(
            k in step_result for k in ("processes", "files", "url", "message")
        ):
            status = "completed" if step_result.get("success", True) else "failed"
            print(f"  Step {status}: {step_result['subtask_description']}")

        if step_result.get("url"):
            print(f"  Opened: {step_result['url']}")

        # Generic fallback. The branches above cover 11 hardcoded keys; every
        # other payload printed NOTHING, so "list tasks", "list team", "disk
        # drives", "audit trail" and "show phase5 model" all ran fine, said
        # "completed successfully", and showed the user an empty screen. A
        # renderer that silently drops data it does not recognise makes
        # working features look broken.
        # Always run: duplication is prevented per-key by _NOISE_KEYS and
        # _HANDLED_KEYS, not by skipping the whole payload. A short generic
        # "message" used to suppress everything else, which hid the actual
        # productivity report sitting alongside it.
        self._display_generic_payload(step_result)

    # Keys that are bookkeeping, not results worth showing the user.
    _NOISE_KEYS = frozenset({
        "success", "tier", "complexity", "intent", "source", "params",
        "action", "action_type", "step", "steps", "steps_total",
        "steps_completed", "subtask_description", "message", "warning",
        "url", "error", "timestamp", "executed_at", "advisory", "accepted",
        "reason", "confidence", "raw_route", "verification_warning",
        "ranked_by",
    })

    # Keys the explicit branches above already render.
    _HANDLED_KEYS = frozenset({
        "processes", "files", "cpu", "memory", "fields_filled",
        "command_history", "feedback_recorded", "preference_saved",
        "preference_rejected", "preferences", "workflow_patterns",
        "adaptive_learning", "phase5_learning",
        # The System Status block already prints disk and host details;
        # without these the fallback repeated them underneath.
        "disk", "platform", "python_version", "hostname", "boot_time",
    })

    def _printed_anything_for(self, step_result: Dict[str, Any]) -> bool:
        """Did one of the explicit branches already show this to the user?"""
        if not isinstance(step_result, dict):
            return False
        if any(k in step_result for k in self._HANDLED_KEYS):
            return True
        return bool(step_result.get("message") or step_result.get("url"))

    def _display_generic_payload(self, step_result: Dict[str, Any]) -> None:
        """Render an unrecognised result rather than dropping it silently."""
        if not isinstance(step_result, dict):
            if step_result:
                print(f"  {step_result}")
            return

        # Anything the message already told the user is not worth repeating
        # under a different label. Asking for 17 percent of 4500 printed the
        # answer four times - as the message, then again as Result, Output
        # and Expression - which reads as a system that does not know what
        # it just said.
        already_said = str(step_result.get("message") or "")

        for key, value in step_result.items():
            # _HANDLED_KEYS too: an explicit branch above already rendered
            # those, and printing them again gave "Files Found (1 total)"
            # immediately followed by "Files (1)".
            if (key in self._NOISE_KEYS or key in self._HANDLED_KEYS
                    or value in (None, "", [], {})):
                continue
            if (already_said and isinstance(value, (str, int, float))
                    and str(value) in already_said):
                continue
            label = key.replace("_", " ").title()

            if isinstance(value, list):
                print(f"\n{label} ({len(value)}):")
                for item in value[:20]:
                    print(f"  - {self._summarise_item(item)}")
                if len(value) > 20:
                    print(f"  ... and {len(value) - 20} more")

            elif isinstance(value, dict):
                print(f"\n{label}:")
                for sub_key, sub_value in list(value.items())[:20]:
                    if isinstance(sub_value, (dict, list)):
                        sub_value = self._summarise_item(sub_value)
                    print(f"  {sub_key.replace('_', ' ').title()}: {sub_value}")

            elif isinstance(value, str) and ("\n" in value or len(value) > 200):
                # A generated report, not a field value.
                print(f"\n{label}:")
                for line in value.splitlines()[:40]:
                    print(f"  {line}")

            else:
                print(f"  {label}: {value}")

    @staticmethod
    def _summarise_item(item: Any) -> str:
        """One readable line for a list/dict entry."""
        if isinstance(item, dict):
            # Prefer the fields a person actually wants to see.
            # "id" last: a bare UUID is the least useful thing to show a
            # person. The audit trail rendered as a column of raw GUIDs
            # because "id" was preferred over "event_type".
            for key in ("name", "title", "event_type", "device", "drive",
                        "mountpoint", "description", "path", "command",
                        "summary", "label", "id"):
                if item.get(key):
                    label = str(item[key])
                    extras = [
                        f"{k}={item[k]}" for k in ("status", "priority", "role",
                                                   "actor", "resource_type",
                                                   "size_gb", "percent", "free_gb")
                        if item.get(k) not in (None, "")
                    ][:3]
                    return f"{label} ({', '.join(extras)})" if extras else label
            return ", ".join(f"{k}={v}" for k, v in list(item.items())[:4])
        if isinstance(item, list):
            return f"[{len(item)} items]"
        return str(item)

    def free_memory(self):
        """Models unload automatically per their configured keep_alive window
        (council members between multi-member consultations use keep_alive=0
        to unload immediately; single-shot calls use the configured default)."""

        logger.info(
            "Model residency is controlled by keep_alive (config default: {})",
            self.config.get("ollama", {}).get("keep_alive", "5m"),
        )


async def main():
    """Main entry point."""

    asc = AutonomousSystemController()
    await asc.run_interactive()


if __name__ == "__main__":
    if "--doctor" in sys.argv:
        from core.doctor import run as run_doctor

        sys.exit(run_doctor())

    if "--demo" in sys.argv:
        # A guided tour for showing the system to someone. Runs the real
        # command path; nothing is mocked.
        from core.showcase import run as run_showcase

        async def _demo():
            asc = AutonomousSystemController()
            try:
                await run_showcase(asc)
            finally:
                await asc.shutdown()

        asyncio.run(_demo())
        sys.exit(0)

    if "--metrics" in sys.argv:
        from core.metrics import collect, render_text

        data_dir = Path(DEFAULT_CONFIG_PATH).parent.parent / "data"
        snapshot = collect(data_dir)
        if "--json" in sys.argv:
            print(json.dumps(snapshot, indent=2))
        else:
            print(render_text(snapshot))
        sys.exit(0)

    if "--clean-data" in sys.argv:
        # Repeated test runs wrote into the same stores the product reads,
        # so the live analytics were computed over ~1,100 duplicate and
        # fixture records. Dry run by default; --apply backs up first.
        from core.data_hygiene import clean

        apply_it = "--apply" in sys.argv
        report = clean(Path(DEFAULT_CONFIG_PATH).parent.parent / "data", dry_run=not apply_it)

        print()
        print("=" * 62)
        print("DATA CLEANUP " + ("(APPLIED)" if apply_it else "(DRY RUN - nothing changed)"))
        print("=" * 62)
        for filename, stats in report["files"].items():
            if "error" in stats:
                print(f"  {filename:24} ERROR: {stats['error']}")
                continue
            print(f"  {filename:24} {stats['before']:>5} -> {stats['after']:<5}"
                  f"  junk {stats['junk_removed']:>4}, duplicates {stats['duplicates_removed']:>4}")
        print(f"\n  records removed: {report['total_removed']}")
        if apply_it:
            print(f"  backup written to: {report.get('backup')}")
        else:
            print("\n  Nothing was changed. Re-run with --apply to do it for real:")
            print("      python main.py --clean-data --apply")
        print()
        sys.exit(0)
    if "--journal" in sys.argv:
        journal_flag_idx = sys.argv.index("--journal")
        journal_count = int(sys.argv[journal_flag_idx + 1]) if len(sys.argv) > journal_flag_idx + 1 else 15
        memory = MemorySystem(DEFAULT_CONFIG_PATH)
        tail = memory.get_journal_entries(journal_count)
        print("=" * 60)
        print(f"VEGA EXECUTION JOURNAL - last {len(tail)} commands")
        print("=" * 60)
        for e in reversed(tail):
            flag = "OK  " if e.get("success") else "FAIL"
            steps = ", ".join(str(s.get("action", "?")) for s in e.get("steps", [])) or "-"
            err = f"  [error: {e.get('error')}]" if e.get("error") else ""
            print(f"[{flag}] {e.get('timestamp', '')}  {str(e.get('command'))[:60]}")
            print(f"       tier={e.get('tier')} steps: {steps}{err}")
        sys.exit(0)
    if "--tasks" in sys.argv:
        # Surfaces multi-step plans left in a non-terminal state (e.g. by a
        # crash mid-execution). Deliberately just a viewer - see
        # MemorySystem.get_incomplete_tasks for why these are not
        # auto-resumed.
        memory = MemorySystem(DEFAULT_CONFIG_PATH)
        incomplete = memory.get_incomplete_tasks()
        print("=" * 60)
        print(f"VEGA INCOMPLETE TASKS - {len(incomplete)} left running")
        print("=" * 60)
        if not incomplete:
            print("None. Every recorded multi-step task reached done/failed.")
        for t in incomplete:
            print(f"[#{t['id']}] {t['command'][:70]}")
            print(f"    steps: {t['steps_completed']}/{t['steps_total']}  updated: {t['updated']}")
            if t.get("last_error"):
                print(f"    last error: {t['last_error']}")
        sys.exit(0)
    # The reminders loop now always runs inside run_interactive itself
    # (background_tasks, alongside the remote-queue worker) - it no longer
    # needs a --reminders flag or a separate entry point, since input() no
    # longer blocks the event loop that the loop needs to tick on.
    asyncio.run(main())
