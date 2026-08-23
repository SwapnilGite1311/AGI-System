import asyncio
import webbrowser
from pathlib import Path

from agents.web_agent import WebAgent
from agents.conversation_agent import ConversationAgent
from core.autonomy import AutonomyEngine
from core.task_decomposer import TaskDecomposer
from learning.adaptive_engine import AdaptiveLearningEngine
from learning.neural_command_model import NeuralCommandModel
from learning.phase5_model import OfflinePreferenceModel
from main import AutonomousSystemController


class DummyMemory:
    def __init__(self):
        self.preferences = {}
        self.short_term = {}

    def remember_episode(self, **kwargs):
        return None

    def remember_short_term(self, key, value):
        self.short_term[key] = value
        return None

    def recall_short_term(self, key):
        return self.short_term.get(key)

    def log_session_activity(self, activity):
        return None

    def save_user_preference(self, key, value):
        self.preferences[key] = {"value": value}

    def get_user_preference(self, key, default=None):
        return self.preferences.get(key, {}).get("value", default)


class DummyLearningAgent:
    def __init__(self):
        self.patterns = {}
        self.history = []

    def find_similar_success(self, command, threshold=0.75):
        return None

    def get_recent_commands(self, limit=10):
        return self.history[-limit:]

    def get_learning_stats(self):
        return {"history_count": len(self.history), "success_rate": 1.0 if self.history else 0.0, "form_patterns": len(self.patterns)}

    def record_command(self, command, strategy, result):
        self.history.append({"command": command, "strategy": strategy, "result": result})
        return self.history[-1]

    def record_feedback(self, feedback, sentiment="neutral", command=None):
        return {"feedback": feedback, "sentiment": sentiment, "command": command}

    def discover_workflow_patterns(self, min_count=2):
        return [{"signature": "intent:browser_action", "count": 2, "examples": ["search a", "search b"]}]

    def remember_form_pattern(self, form_signature, field_order, metadata=None):
        self.patterns[form_signature] = {"field_order": field_order, "metadata": metadata or {}}

    def recall_form_pattern(self, form_signature):
        return self.patterns.get(form_signature)

    def refresh_adaptive_state(self, preferences=None):
        return self.get_adaptive_summary()

    def recommend_strategy(self, command):
        return None

    def classify_command(self, command):
        normalized = command.lower().strip()
        if "show system status" in normalized:
            return {
                "predicted_intent": "system_info",
                "confidence": 0.92,
                "source": "adaptive_cluster",
                "cluster": {
                    "signature": "intent:system_info",
                    "strategy": {"intent": {"type": "system_info"}},
                },
            }
        if "search" in normalized:
            return {
                "predicted_intent": "browser_action",
                "confidence": 0.78,
                "source": "adaptive_cluster",
                "cluster": {
                    "signature": "intent:browser_action",
                    "strategy": {"intent": {"type": "browser_action"}},
                },
            }
        return {"predicted_intent": "unknown", "confidence": 0.0, "source": "none"}

    def get_phase5_summary(self):
        return {
            "summary": {
                "clusters": 1,
                "trained_preferences": 1,
                "advisory": True,
                "offline": True,
                "confidence": 0.72,
                "preference_model": "offline_preference_model",
            },
            "clusters": [{"cluster_id": "web", "signature": "route:web", "size": 1, "examples": []}],
            "preference_candidates": [{"key": "default_browser", "value": "chrome", "confidence": 0.72, "source": "offline_preference_model", "advisory": True}],
            "prediction": {"key": "default_browser", "value": "chrome", "confidence": 0.72, "source": "offline_preference_model", "advisory": True},
            "offline": True,
            "advisory": True,
        }

    def predict_phase5_preference(self, command, preferences=None):
        return {
            "prediction": {"key": "default_browser", "value": "chrome", "confidence": 0.72, "source": "offline_preference_model", "advisory": True},
            "advisory": True,
            "reason": "Browser-oriented activity suggests a default browser preference.",
        }

    def get_adaptive_summary(self):
        return {
            "summary": {
                "examples": len(self.history),
                "clusters": 1 if self.history else 0,
                "workflow_templates": 0,
                "stable_workflow_templates": 0,
                "positive_labels": len(self.history),
                "negative_labels": 0,
                "neutral_labels": 0,
                "recommendation_accuracy": 0.0,
                "user_correction_rate": 0.0,
            },
            "workflow_clusters": [],
            "workflow_templates": [],
            "evaluation_metrics": {
                "recommendation_accuracy": 0.0,
                "user_correction_rate": 0.0,
                "workflow_templates_available": 0,
                "stable_workflow_templates": 0,
                "suggestion_acceptance_ratio": 0.0,
            },
            "preference_signals": {"suggestions": []},
            "preference_evaluation": {
                "suggestions_available": 0,
                "suggestions_accepted": 0,
                "acceptance_ratio": 0.0,
            },
        }


class DummyWebAgent:
    def __init__(self):
        self.navigated = []

    async def perform_browser_action(self, browser_name, action, target):
        if action == "navigate":
            return await self.navigate_to_url(target, browser_name=browser_name)
        return {
            "success": True,
            "browser": browser_name,
            "action": action,
            "target": target,
            "url": f"https://example.com/search?q={target.replace(' ', '+')}",
        }

    async def navigate_to_url(self, url, browser_name=None):
        self.navigated.append((url, browser_name))
        return {"success": True, "url": url, "browser": browser_name}

    async def search_site(self, query, site=None, browser_name=None):
        target = f"https://www.{site or 'example'}.com/search?q={query.replace(' ', '+')}"
        return {"success": True, "site": site, "query": query, "url": target, "browser": browser_name}

    async def intelligent_form_fill(self, field_values, form_name=None, submit=False, focus_first_field=False, require_confirmation=False, allow_keyboard_fallback=True):
        result = {"success": True, "fields_filled": [{"name": key, "value": value} for key, value in field_values.items()]}
        result["allow_keyboard_fallback"] = allow_keyboard_fallback
        if require_confirmation and submit:
            result["requires_confirmation"] = True
            result["confirmation_token"] = "dummy-token"
        return result

    async def confirm_submission(self, token):
        return {"success": True, "submitted": True, "confirmation_token": token}


class DummyFileAgent:
    def __init__(self):
        self.created = []
        self.copied = []
        self.moved = []
        self.searched = []
        self.backups = []

    def create_file(self, path, content=""):
        self.created.append((path, content))
        return {"success": True, "path": path, "content_length": len(content)}

    def create_folder(self, path):
        return {"success": True, "path": path}

    def list_files(self, path="."):
        return []

    def organize_folder(self, path):
        return {"success": True, "path": path}

    def copy_file(self, source, destination):
        self.copied.append((source, destination))
        return {"success": True, "source": source, "destination": destination}

    def move_file(self, source, destination):
        self.moved.append((source, destination))
        return {"success": True, "source": source, "destination": destination}

    def get_file_info(self, path):
        return {"success": True, "path": path, "name": Path(path).name}

    def search_files(self, path, query, search_content=False):
        self.searched.append((path, query, search_content))
        return [{"path": str(Path(path) / f"{query}.txt"), "name": f"{query}.txt"}]

    def backup_folder(self, path, backup_name=None):
        self.backups.append((path, backup_name))
        return {"success": True, "source": path, "backup_path": backup_name or "backup"}

    def analyze_disk_usage(self, path):
        return {"success": True, "folder_path": path, "total_size_mb": 1}

    def find_duplicate_files(self, path):
        return {"success": True, "duplicates_found": 0, "duplicates": {}}

    def restore_organization(self, manifest_id=None):
        return {"success": True, "manifest_id": manifest_id}

    def batch_rename_files(self, path, find_str, replace_str, extension=None):
        return {"success": True, "renamed_count": 1}


class DummySystemAgent:
    def __init__(self):
        self.opened = []
        self.closed = []

    def open_application(self, app_name, args=None):
        self.opened.append((app_name, args))
        return {"success": True, "application": app_name, "args": args}

    def close_application(self, app_name):
        self.closed.append(app_name)
        return {"success": True, "application": app_name}

    def list_processes(self, filter_name=None):
        return [{"pid": 1, "name": "demo.exe", "cpu": 0.0, "memory": 1.0}]

    def get_system_info(self):
        return {
            "cpu": {"percent": 1, "cores": 1},
            "memory": {"used_percent": 10, "available_gb": 1},
            "disk": {"used_percent": 20, "free_gb": 2},
        }

    def run_command(self, command, shell="powershell", confirmed=False):
        return {"success": True, "output": command, "return_code": 0}

    def get_network_info(self):
        return {"success": True, "interfaces": {"loopback": {}}}

    def get_disk_usage_all_drives(self):
        return [{"drive": "C:\\", "used_percent": 20}]

    def get_environment_variable(self, name):
        return {"success": True, "name": name, "value": "demo"}


class DummyConversationAgent:
    def is_conversation(self, text):
        return text.lower().strip() in {"hi", "how are you?", "what can you do?"}

    async def chat(self, message, context=None):
        return {
            "success": True,
            "tier": "conversation",
            "mode": "chat",
            "response": "Hi, I am ASC.",
            "model": "dummy",
        }


class DummyCouncil:
    def __init__(self):
        self.calls = []

    async def decide(self, task, complexity="medium"):
        self.calls.append((task, complexity))
        return {
            "action_plan": [
                {"action": "navigate", "params": {"url": "https://example.com/form"}, "description": "Open the form URL"},
                {"action": "form", "params": {"fields": {"name": "Ada", "email": "ada@example.com"}, "submit": False}, "description": "Fill the form fields"},
            ],
            "confidence": 0.92,
        }


def build_controller():
    controller = object.__new__(AutonomousSystemController)
    controller.config = {
        "web_automation": {"default_browser": "chrome"},
        "execution": {"decompose_complex_tasks": True},
    }
    controller.voice_service_url = "http://localhost:5000"
    controller.voice_enabled = True
    controller.command_cache = {}
    controller.command_cache_size = 100
    controller.execution_pause_seconds = 0
    controller.memory = DummyMemory()
    controller.task_decomposer = TaskDecomposer()
    controller.decompose_complex_tasks = True
    controller.agents = {
        "conversation": DummyConversationAgent(),
        "learning": DummyLearningAgent(),
        "web": DummyWebAgent(),
        "file": DummyFileAgent(),
        "system": DummySystemAgent(),
    }
    controller.tier_stats = {"direct": 0, "single_model": 0, "sequential": 0}
    controller.autonomy = AutonomyEngine(controller.task_decomposer, controller.get_tool_manifest)
    return controller


def test_parse_open_browser_and_search_command():
    controller = build_controller()

    intent = controller._parse_direct_command("open chrome and search for AI trends")

    assert intent == {
        "type": "browser_action",
        "app": "chrome",
        "action": "search",
        "target": "ai trends",
    }


def test_parse_fill_form_command():
    controller = build_controller()

    intent = controller._parse_direct_command(
        "fill form with name: Swapnil, email: swapnil@example.com, company: OpenAI"
    )

    assert intent["type"] == "fill_form"
    assert intent["fields"] == {
        "name": "Swapnil",
        "email": "swapnil@example.com",
        "company": "OpenAI",
    }


def test_parse_fill_form_requires_confirmation():
    controller = build_controller()

    intent = controller._parse_direct_command(
        "Stage the form with name: Alice, email: alice@example.com and confirm before submitting"
    )

    assert intent["type"] == "fill_form"
    assert intent["submit"] is True
    assert intent["require_confirmation"] is True


def test_parse_confirm_submission_token():
    controller = build_controller()

    intent = controller._parse_direct_command(
        "Confirm submission token 123e4567-e89b-12d3-a456-426614174000"
    )

    assert intent["type"] == "confirm_submission"
    assert intent["token"] == "123e4567-e89b-12d3-a456-426614174000"


def test_parse_system_power_actions_are_confirmation_gated():
    controller = build_controller()

    shutdown = controller._parse_direct_command("shutdown system")
    sleep = controller._parse_direct_command("put laptop to sleep")
    power_on = controller._parse_direct_command("turn on laptop")
    unlock = controller._parse_direct_command("unlock laptop")

    assert shutdown["type"] == "system_power_action"
    assert shutdown["power_action"] == "shutdown"
    assert shutdown["command"] == "shutdown /s /t 0"
    assert sleep["power_action"] == "sleep"
    assert power_on["unsupported_reason"]
    assert unlock["unsupported_reason"]


def test_direct_strategy_is_selected_for_browser_search():
    controller = build_controller()

    strategy = controller._determine_execution_strategy("open chrome and search for AI trends")

    assert strategy["tier"] == "direct"
    assert strategy["intent"]["type"] == "browser_action"


def test_direct_execution_uses_web_agent_for_browser_workflow():
    controller = build_controller()

    result = asyncio.run(
        controller._execute_directly(
            "open chrome and search for AI trends",
            {
                "intent": {
                    "type": "browser_action",
                    "app": "chrome",
                    "action": "search",
                    "target": "AI trends",
                }
            },
        )
    )

    assert result["success"] is True
    assert result["tier"] == "direct"
    assert result["results"][0]["browser"] == "chrome"


def test_url_form_fill_disables_blind_keyboard_fallback():
    controller = build_controller()

    result = asyncio.run(
        controller.process_command("https://example.com fill form with name: Swapnil, email: swapnil@example.com")
    )

    assert result["success"] is True
    first = result["results"][0]
    assert first["navigated_url"] == "https://example.com"
    assert first["allow_keyboard_fallback"] is False


def test_system_power_action_requires_confirmation_before_execution():
    controller = build_controller()

    first = asyncio.run(controller.process_command("restart system"))
    second = asyncio.run(controller.process_command("confirm command"))

    assert first["success"] is False
    assert first["results"][0]["needs_confirmation"] is True
    assert controller.memory.recall_short_term("pending_system_command") is None
    assert second["success"] is True
    assert "shutdown /r /t 0" in second["results"][0]["output"]


def test_direct_execution_confirm_submission_intent():
    controller = build_controller()

    result = asyncio.run(
        controller._execute_directly(
            "Confirm submission token dummy-token",
            {
                "intent": {
                    "type": "confirm_submission",
                    "token": "dummy-token",
                }
            },
        )
    )

    assert result["success"] is True
    assert result["results"][0]["submitted"] is True
    assert result["results"][0]["confirmation_token"] == "dummy-token"


class StubSystemAgent:
    def __init__(self):
        self.calls = []
        self.typed = []
        self.keys = []
        self.hotkeys = []

    def open_application(self, app_name, args=None):
        self.calls.append((app_name, args))
        return {"success": True, "application": app_name, "pid": 1234, "path": app_name}

    def click_mouse(self, x, y):
        return {"success": True, "x": x, "y": y}

    def type_text(self, text, interval=0.05):
        self.typed.append(text)
        return {"success": True, "text": text}

    def press_hotkey(self, *keys):
        self.hotkeys.append(keys)
        return {"success": True, "keys": list(keys)}

    def press_key(self, key):
        self.keys.append(key)
        return {"success": True, "key": key}


class StubVisionAgent:
    def __init__(self, ocr_available=True, text="Name\nEmail\nCompany\nSubmit"):
        self._ocr_available = ocr_available
        self._text = text

    def extract_text_ocr(self, image=None):
        return self._text

    def is_ocr_available(self):
        return self._ocr_available


class FakeBrowserPage:
    def __init__(self, content_text="Thank you"):
        self.clicks = []
        self.keyboard_presses = []
        self.content_text = content_text
        self.keyboard = self

    async def click(self, selector):
        self.clicks.append(selector)

    async def press(self, key):
        self.keyboard_presses.append(key)


class FakeBrowserDriver:
    def __init__(self, content_text="Thank you"):
        self.page = FakeBrowserPage(content_text=content_text)
        self.fill_calls = []

    async def find_selectors_for_labels(self, labels):
        mapping = {}
        for label in labels:
            normalized = label.lower()
            if normalized in {"name", "email"}:
                mapping[label] = {"selector": f"#{normalized}", "confidence": 0.95}
            else:
                mapping[label] = {"selector": None, "confidence": 0.0}
        return mapping

    async def find_submit_selector(self):
        return "#submit"

    async def fill_fields(self, field_map, submit_selector=None):
        self.fill_calls.append({"field_map": dict(field_map), "submit_selector": submit_selector})
        if submit_selector:
            await self.page.click(submit_selector)
        return {"success": True, "filled": list(field_map.keys()), "page_content": self.page.content_text}

    async def find_label_candidates(self):
        return []


def test_web_agent_builds_search_url_and_reuses_existing_agents():
    system_agent = StubSystemAgent()
    vision_agent = StubVisionAgent()
    learning_agent = DummyLearningAgent()
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=system_agent,
        vision_agent=vision_agent,
        learning_agent=learning_agent,
    )
    agent.browser_driver = None
    agent.navigation_delay_seconds = 0

    result = asyncio.run(agent.search_web("AI trends", browser_name="chrome"))

    assert result["success"] is True
    assert result["query"] == "AI trends"
    assert "google.com/search?q=AI+trends" in result["url"]
    assert system_agent.calls[0][0] == "chrome"


def test_web_agent_form_fill_uses_stored_pattern_order():
    system_agent = StubSystemAgent()
    vision_agent = StubVisionAgent()
    learning_agent = DummyLearningAgent()
    learning_agent.remember_form_pattern(
        "name|email|company|submit",
        ["Name", "Email", "Company"],
    )

    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=system_agent,
        vision_agent=vision_agent,
        learning_agent=learning_agent,
    )
    agent.browser_driver = None
    agent.form_field_delay_seconds = 0
    agent.form_submit_delay_seconds = 0

    result = asyncio.run(
        agent.intelligent_form_fill(
            {"Email": "swapnil@example.com", "Name": "Swapnil", "Company": "ASC"},
            submit=True,
            focus_first_field=False,
        )
    )

    assert result["success"] is True
    assert system_agent.typed == ["Swapnil", "swapnil@example.com", "ASC"]
    assert system_agent.keys.count("tab") == 2
    assert system_agent.keys[-1] == "enter"


def test_web_agent_driver_submit_happens_once():
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=StubSystemAgent(),
        vision_agent=StubVisionAgent(),
        learning_agent=DummyLearningAgent(),
    )
    agent.browser_driver = FakeBrowserDriver()

    result = asyncio.run(
        agent.intelligent_form_fill(
            {"Name": "Swapnil", "Email": "swapnil@example.com"},
            submit=True,
        )
    )

    assert result["success"] is True
    assert result["submitted"] is True
    assert agent.browser_driver.fill_calls[0]["submit_selector"] is None
    assert agent.browser_driver.page.clicks == ["#submit"]


def test_web_agent_driver_stage_does_not_submit_until_confirmed():
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=StubSystemAgent(),
        vision_agent=StubVisionAgent(),
        learning_agent=DummyLearningAgent(),
    )
    agent.browser_driver = FakeBrowserDriver()

    staged = asyncio.run(
        agent.intelligent_form_fill(
            {"Name": "Swapnil", "Email": "swapnil@example.com"},
            submit=True,
            require_confirmation=True,
        )
    )

    assert staged["success"] is True
    assert staged["requires_confirmation"] is True
    assert staged["confirmation_token"]
    assert agent.browser_driver.page.clicks == []

    confirmed = asyncio.run(agent.confirm_submission(staged["confirmation_token"]))

    assert confirmed["success"] is True
    assert confirmed["submitted"] is True
    assert confirmed["confirmation_token"] == staged["confirmation_token"]
    assert agent.browser_driver.page.clicks == ["#submit"]


def test_web_agent_falls_back_to_default_browser_with_warning(monkeypatch):
    class FailingSystemAgent(StubSystemAgent):
        def open_application(self, app_name, args=None):
            self.calls.append((app_name, args))
            return {"success": False, "application": app_name, "error": "missing browser"}

    opened = {}

    def fake_open(url):
        opened["url"] = url
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)

    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=FailingSystemAgent(),
        vision_agent=StubVisionAgent(),
        learning_agent=DummyLearningAgent(),
    )
    agent.browser_driver = None
    agent.navigation_delay_seconds = 0

    result = asyncio.run(agent.navigate_to_url("github.com", browser_name="chrome"))

    assert result["success"] is True
    assert result["launch_mode"] == "fallback"
    assert "warning" in result
    assert opened["url"] == "https://github.com"


def test_form_fill_with_url_is_parsed():
    controller = build_controller()

    intent = controller._parse_direct_command(
        "https://example.com/form fill form with name: Swapnil, email: swapnil@example.com"
    )

    assert intent["type"] == "fill_form"
    assert intent["url"] == "https://example.com/form"


def test_sequence_commands_prefer_decomposition():
    controller = build_controller()

    strategy = controller._determine_execution_strategy(
        "show system status and then list running processes"
    )

    assert strategy["tier"] == "sequential"


def test_task_decomposer_creates_research_report_workflow():
    decomposer = TaskDecomposer()
    plan = decomposer.decompose("reseach AI trends and create a report")

    assert plan["strategy"] == "research_report"
    assert [step["action"] for step in plan["subtasks"]] == ["search", "extract_text", "create_report"]


def test_controller_executes_decomposed_report_workflow():
    controller = build_controller()
    decomposition = controller.task_decomposer.decompose("research AI trends and create a report")

    async def fake_route_action(action, params, context):
        if action == "search":
            return {"success": True, "url": "https://example.com/ai-trends"}
        if action == "extract_text":
            return {"success": True, "text": "AI trends are accelerating across local agents."}
        return {"success": True, "message": context}

    controller._route_action = fake_route_action

    result = asyncio.run(controller._execute_decomposed_tasks(decomposition, decomposition["goal"]))

    assert result["success"] is True
    assert result["steps_total"] == 3
    created_path, created_content = controller.agents["file"].created[0]
    assert created_path.endswith("_report.txt")
    assert "AI trends are accelerating" in created_content


def test_task_decomposer_handles_browser_then_create_file():
    decomposer = TaskDecomposer()
    plan = decomposer.decompose("open chrome and search for agentic ai and then create file named agentic_notes.txt")

    assert plan["strategy"] == "browser_then_file"
    assert plan["subtasks"][0]["action"] in {"open", "search"}
    assert plan["subtasks"][-1]["action"] == "create_file"


def test_memory_session_management():
    from core.memory import MemorySystem
    import shutil
    
    # Initialize real MemorySystem with default/config
    memory = MemorySystem()
    
    # Test session startup, logging, and preference retrieval
    sess_id = memory.start_session("Test CLI Start")
    assert sess_id.startswith("session_")
    
    memory.log_session_activity("User queried disk usage")
    activities = memory.get_last_session_activities()
    assert "User queried disk usage" in activities or "Test CLI Start" in activities
    
    memory.save_user_preference("theme", "dark")
    pref = memory.get_user_preference("theme")
    assert pref == "dark"
    
    memory.end_session()
    assert memory.current_session_id is None


def test_decomposer_advanced_templates():
    decomposer = TaskDecomposer()
    
    # 1. Download & Organize
    plan1 = decomposer.decompose("download https://example.com/data.csv and organize desktop")
    assert plan1["strategy"] == "download_and_organize"
    assert [step["action"] for step in plan1["subtasks"]] == ["navigate", "wait_for_process", "organize"]
    
    # 2. Compare Files
    plan2 = decomposer.decompose("compare file1.txt and file2.txt")
    assert plan2["strategy"] == "compare_files"
    assert [step["action"] for step in plan2["subtasks"]] == ["list", "run_command"]
    
    # 3. Backup & Clean
    plan3 = decomposer.decompose("backup desktop and clean folder")
    assert plan3["strategy"] == "backup_and_clean"
    assert [step["action"] for step in plan3["subtasks"]] == ["list", "run_command", "organize"]


def test_parse_security_commands():
    controller = build_controller()
    
    # Port scan
    intent = controller._parse_direct_command("run security scan on 127.0.0.1 ports 80-443")
    assert intent["type"] == "security_port_scan"
    assert intent["host"] == "127.0.0.1"
    assert intent["ports"] == "80-443"
    
    # SSL Check
    intent = controller._parse_direct_command("ssl check google.com")
    assert intent["type"] == "security_ssl_check"
    assert intent["domain"] == "google.com"
    
    # Security Headers
    intent = controller._parse_direct_command("check security headers for https://example.com")
    assert intent["type"] == "security_headers_check"
    assert intent["url"] == "https://example.com"
    
    # DNS Lookup
    intent = controller._parse_direct_command("dns lookup for localhost")
    assert intent["type"] == "dns_lookup"
    assert intent["domain"] == "localhost"


def test_parse_file_advanced_commands():
    controller = build_controller()
    
    # Undo organization
    intent = controller._parse_direct_command("undo organization with manifest manifest_123")
    assert intent["type"] == "restore_organization"
    assert intent["manifest_id"] == "manifest_123"
    
    # Analyze disk usage
    intent = controller._parse_direct_command("analyze disk usage in desktop")
    assert intent["type"] == "analyze_disk_usage"
    
    # Find duplicates
    intent = controller._parse_direct_command("find duplicates in downloads")
    assert intent["type"] == "find_duplicates"
    
    # Batch rename
    intent = controller._parse_direct_command("batch rename files in c:\\temp replace old with new matching .jpg")
    assert intent["type"] == "batch_rename_files"
    assert intent["find"] == "old"
    assert intent["replace"] == "new"
    assert intent["extension"] == ".jpg"


def test_controller_decomposed_tasks_rollback():
    controller = build_controller()
    
    # We mock subtasks: step-1 succeeds (create folder), step-2 fails (system command)
    decomposition = {
        "goal": "create folder ./temp_test and then run invalid command",
        "strategy": "clause_split",
        "subtasks": [
            {
                "id": "step-1",
                "agent": "file",
                "action": "create_folder",
                "params": {"path": "./temp_test", "description": "create folder ./temp_test"},
                "description": "create folder ./temp_test"
            },
            {
                "id": "step-2",
                "agent": "system",
                "action": "run_command",
                "params": {"command": "invalid-cmd-12345"},
                "description": "run invalid command"
            }
        ]
    }
    
    deleted_paths = []
    
    class MockFileAgentWithDelete:
        def create_folder(self, path):
            return {"success": True, "path": path}
        def delete_folder(self, path, recursive=True):
            deleted_paths.append(path)
            return {"success": True}
            
    controller.agents["file"] = MockFileAgentWithDelete()
    
    async def fake_route_action(action, params, context):
        if action == "create_folder":
            return controller.agents["file"].create_folder(params.get("path"))
        return {"success": False, "error": "command failed"}
        
    controller._route_action = fake_route_action
    
    result = asyncio.run(controller._execute_decomposed_tasks(decomposition, "goal"))
    
    assert result["success"] is False
    assert result["rollback_executed"] is True
    assert "./temp_test" in deleted_paths


def test_clause_splitting_complex_browser_actions():
    decomposer = TaskDecomposer()
    plan = decomposer.decompose("open google goto amazon and search for laptops")
    assert plan["strategy"] == "clause_split"
    assert len(plan["subtasks"]) == 3
    assert plan["subtasks"][0]["action"] == "navigate"
    assert "google.com" in plan["subtasks"][0]["params"]["target"]
    assert plan["subtasks"][1]["action"] == "navigate"
    assert "amazon.com" in plan["subtasks"][1]["params"]["target"]
    assert plan["subtasks"][2]["action"] == "search"
    assert plan["subtasks"][2]["params"]["query"] == "laptops"


def test_decomposer_form_filling_parsing():
    decomposer = TaskDecomposer()
    plan = decomposer.decompose("go to https://forms.gle/XYZ and fill the form with name: Swapnil, email: swapnil@gmail.com")
    assert len(plan["subtasks"]) == 2
    assert plan["subtasks"][0]["action"] == "navigate"
    assert plan["subtasks"][0]["params"]["target"] == "https://forms.gle/XYZ"
    assert plan["subtasks"][1]["action"] == "form"
    assert plan["subtasks"][1]["params"]["fields"] == {"name": "Swapnil", "email": "swapnil@gmail.com"}
    assert plan["subtasks"][1]["params"]["url"] == "https://forms.gle/XYZ"


def test_web_agent_vision_guided_click_fallback():
    class ClickTrackingSystemAgent(StubSystemAgent):
        def __init__(self):
            super().__init__()
            self.clicks = []
        def click_mouse(self, x, y):
            self.clicks.append((x, y))
            return {"success": True, "x": x, "y": y}

    system_agent = ClickTrackingSystemAgent()
    called_text = []

    class MockVisionAgentWithCoordinates(StubVisionAgent):
        def find_text_coordinates(self, text, image=None):
            called_text.append(text)
            return (500, 300)

    vision_agent = MockVisionAgentWithCoordinates()
    learning_agent = DummyLearningAgent()

    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=system_agent,
        vision_agent=vision_agent,
        learning_agent=learning_agent,
    )
    agent.browser_driver = None
    agent.form_field_delay_seconds = 0
    agent.form_submit_delay_seconds = 0

    result = asyncio.run(
        agent.intelligent_form_fill(
            {"Name": "Swapnil"},
            submit=False,
            focus_first_field=True,
        )
    )

    assert result["success"] is True
    assert "Name" in called_text
    assert system_agent.clicks == [(500, 345)]


def test_unknown_general_action_fails_instead_of_fake_success():
    controller = build_controller()

    result = asyncio.run(
        controller._execute_general_action(
            "do the mysterious unsupported thing",
            {"description": "do the mysterious unsupported thing"},
        )
    )

    assert result["success"] is False
    assert result["action"] == "unsupported"
    assert "real agent action" in result["error"]


def test_council_string_plan_is_normalized_to_routed_action():
    controller = build_controller()
    plan = {"steps": ["search for laptops on amazon"], "confidence": 0.8}

    result = asyncio.run(controller._execute_plan(plan, "search for laptops on amazon"))

    assert result["success"] is True
    assert result["steps_completed"] == 1
    assert result["results"][0]["action"] == "navigate"
    target_url = result["results"][0].get("url") or result["results"][0].get("target", "")
    assert "amazon.in" in target_url
    assert "laptops" in target_url


def test_ecommerce_browser_command_maps_to_site_search_url():
    controller = build_controller()

    intent = controller._parse_direct_command(
        "open chrome and search for amazon and search for laptops on amazon"
    )

    assert intent["type"] == "browser_action"
    assert intent["action"] == "navigate"
    assert "amazon.in/s?k=laptops" in intent["target"]


def test_ecommerce_there_command_prefers_single_direct_action():
    controller = build_controller()

    strategy = controller._determine_execution_strategy(
        "open chrome and search for amazon and search for laptops there"
    )

    assert strategy["tier"] == "direct"
    assert strategy["intent"]["type"] == "browser_action"
    assert strategy["intent"]["action"] == "navigate"
    assert "amazon.in/s?k=laptops" in strategy["intent"]["target"]


def test_tool_registry_exposes_phase_two_tools():
    controller = build_controller()

    manifest = controller.get_tool_manifest()
    tool_names = {tool["name"] for tool in manifest}
    actions = {action for tool in manifest for action in tool["actions"]}

    assert {"file_ops", "system_ops", "vision_ops", "web_ops"}.issubset(tool_names)
    assert {"search", "site_search", "navigate", "form", "open", "create_file", "run_command"}.issubset(actions)


def test_route_action_uses_registered_web_tool():
    controller = build_controller()

    result = asyncio.run(
        controller._route_action(
            "search",
            {"query": "phase 2 autonomy"},
            "search for phase 2 autonomy",
        )
    )

    assert result["success"] is True
    assert result["agent"] == "web"
    assert result["tool"] == "web_ops"
    assert result["action"] == "search"


def test_parse_voice_status_command():
    controller = build_controller()

    intent = controller._parse_direct_command("check voice status")

    assert intent == {"type": "voice_status"}


def test_conversation_strategy_is_selected_for_greeting():
    controller = build_controller()

    strategy = controller._determine_execution_strategy("hi")

    assert strategy["tier"] == "conversation"
    assert strategy["source"] == "conversation"


def test_conversation_agent_detects_capability_statement():
    agent = ConversationAgent("./config/settings.json")

    assert agent.is_conversation("tell me what you are capable of") is True


def test_conversation_agent_fallback_answers_without_ollama():
    agent = ConversationAgent("./config/settings.json")
    agent.use_llm = False

    result = asyncio.run(agent.chat("what can you do?"))

    assert result["success"] is True
    assert result["tier"] == "conversation"
    assert "automate" in result["response"]


def test_display_result_prints_conversation_response(capsys):
    controller = build_controller()

    controller._display_result({
        "success": True,
        "tier": "conversation",
        "mode": "chat",
        "response": "Hi, I am ASC.",
    })

    captured = capsys.readouterr()
    assert "ASC: Hi, I am ASC." in captured.out
    assert "Success via conversation tier" not in captured.out


def test_display_result_prints_command_output(capsys):
    controller = build_controller()

    controller._display_result({
        "success": True,
        "tier": "direct",
        "steps_completed": 1,
        "steps_total": 1,
        "results": [{
            "success": True,
            "output": "Friday, July 14, 2026",
            "error": "",
            "return_code": 0,
        }],
    })

    captured = capsys.readouterr()
    assert "Excellent" in captured.out
    assert "direct execution" in captured.out


def test_autonomy_asks_for_missing_target():
    controller = build_controller()

    strategy = controller._determine_execution_strategy("open")
    result = asyncio.run(controller.process_command("open"))

    assert strategy["tier"] == "autonomous"
    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert "What should I open" in result["question"]


def test_autonomy_handles_currently_opened_apps_without_ollama():
    controller = build_controller()

    result = asyncio.run(controller.process_command("currently opened apps"))

    assert result["success"] is True
    assert result["tier"] == "autonomous"
    assert result["autonomy"]["strategy"] == "heuristic_single_step"
    assert result["results"][0]["agent"] == "system"


def test_autonomy_creates_note_from_flexible_request():
    controller = build_controller()

    result = asyncio.run(controller.process_command("make a note about project ideas"))

    assert result["success"] is True
    assert result["tier"] == "autonomous"
    created_path, created_content = controller.agents["file"].created[0]
    assert created_path.endswith("project_ideas_note.txt")
    assert "project ideas" in created_content


def test_autonomy_uses_council_for_ambiguous_form_workflow():
    controller = build_controller()
    controller.council = DummyCouncil()

    result = asyncio.run(controller.process_command("fill this form for me"))

    assert result["success"] is True
    assert result["tier"] == "autonomous"
    assert controller.council.calls
    assert controller.agents["web"].navigated[0][0] == "https://example.com/form"


def test_feedback_command_records_feedback():
    controller = build_controller()
    controller.memory.remember_short_term("last_command", "open chrome")

    result = asyncio.run(controller.process_command("that worked"))

    assert result["success"] is True
    feedback = result["results"][0]["feedback_recorded"]
    assert feedback["sentiment"] == "positive"
    assert feedback["command"] == "that worked"


def test_preference_commands_save_and_show_preferences():
    controller = build_controller()

    save_result = asyncio.run(controller.process_command("remeber default browser is chrome"))
    show_result = asyncio.run(controller.process_command("show preferences"))

    assert save_result["success"] is True
    assert save_result["results"][0]["preference_saved"]["key"] == "default_browser"
    assert show_result["success"] is True
    assert show_result["results"][0]["preferences"]["default_browser"]["value"] == "chrome"


def test_approve_preference_command_saves_preference():
    controller = build_controller()

    approve_result = asyncio.run(controller.process_command("approve preference default browser is edge"))
    assert approve_result["success"] is True
    assert approve_result["results"][0]["approved"] is True
    assert controller.memory.get_user_preference("default_browser") == "edge"


def test_workflow_patterns_command_returns_learning_summary():
    controller = build_controller()

    result = asyncio.run(controller.process_command("show learned workflows"))

    assert result["success"] is True
    patterns = result["results"][0]["workflow_patterns"]
    assert patterns[0]["signature"] == "intent:browser_action"


def test_phase4_adaptive_engine_builds_labeled_clusters(tmp_path):
    engine = AdaptiveLearningEngine(str(tmp_path / "adaptive_state.json"), min_recommendation_score=0.5)
    experiences = [
        {
            "command": "show system status",
            "normalized": "show system status",
            "strategy": {"tier": "direct", "intent": {"type": "system_info"}},
            "result": {"success": True},
            "reward": 1.0,
        },
        {
            "command": "show cpu status",
            "normalized": "show cpu status",
            "strategy": {"tier": "direct", "intent": {"type": "system_info"}},
            "result": {"success": True},
            "reward": 0.9,
        },
    ]

    state = engine.update(experiences, {}, preferences={})
    recommendation = engine.recommend_strategy("show system status")

    assert state["summary"]["positive_labels"] == 2
    assert state["workflow_clusters"][0]["signature"] == "intent:system_info"
    assert recommendation["recommended"] is True
    assert recommendation["strategy"]["intent"]["type"] == "system_info"


def test_phase4_adaptive_learning_status_command():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "show system status",
        {"tier": "direct", "intent": {"type": "system_info"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("phase 4 status"))

    assert result["success"] is True
    assert "adaptive_learning" in result["results"][0]
    adaptive = result["results"][0]["adaptive_learning"]
    assert adaptive["summary"]["examples"] >= 1
    assert "workflow_templates" in adaptive["summary"]
    assert "recommendation_accuracy" in adaptive["summary"]
    assert "user_correction_rate" in adaptive["summary"]


def test_reject_preference_command_marks_suggestion_rejected():
    controller = build_controller()

    result = asyncio.run(controller.process_command("reject preference default_browser chrome"))

    assert result["success"] is True
    assert result["results"][0]["preference_rejected"]["key"] == "default_browser"
    assert result["results"][0]["preference_rejected"]["value"] == "chrome"


def test_show_workflow_templates_command_returns_templates():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "open chrome and search for AI trends",
        {"tier": "direct", "intent": {"type": "browser_action"}},
        {"success": True},
    )
    controller.agents["learning"].record_command(
        "search youtube for music",
        {"tier": "direct", "intent": {"type": "browser_action"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("show workflow templates"))

    assert result["success"] is True
    templates = result["results"][0]["workflow_templates"]
    assert isinstance(templates, list)


def test_phase5_status_command_returns_offline_model_summary():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "open chrome and search for AI trends",
        {"tier": "direct", "intent": {"type": "browser_action"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("phase 5 status"))

    assert result["success"] is True
    phase5 = result["results"][0]["phase5_learning"]
    assert phase5["summary"]["clusters"] >= 1
    assert "preference_model" in phase5["summary"]


def test_phase5_preference_prediction_is_advisory_and_confident():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "open chrome and search for AI trends",
        {"tier": "direct", "intent": {"type": "browser_action"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("show phase 5 model"))

    assert result["success"] is True
    model = result["results"][0]["phase5_model"]
    assert model["summary"]["trained_preferences"] >= 0
    assert isinstance(model["prediction"], dict)


def test_phase5_model_reports_richer_summary_metrics(tmp_path):
    model = OfflinePreferenceModel(path=str(tmp_path / "phase5_model.json"))

    state = model.fit(
        [{"command": "open chrome and search for AI trends", "result": {"success": True}}],
        preferences={},
    )

    assert state["summary"]["preference_model"] == "offline_preference_model"
    assert state["summary"]["top_cluster"] == "web"
    assert state["summary"]["evidence_strength"] >= 0.0


def test_phase5_prediction_includes_confidence_label_and_evidence():
    model = OfflinePreferenceModel(path="./tmp_phase5_model.json")
    prediction = model.predict_preference("open chrome and search for AI trends", preferences={})

    assert prediction["prediction"]["confidence_label"] in {"low", "medium", "high"}
    assert "evidence" in prediction
    assert isinstance(prediction["evidence"], str)


def test_online_learning_exposes_weighted_signals(tmp_path):
    model = OfflinePreferenceModel(path=str(tmp_path / "phase5_model.json"))
    state = model.fit(
        [{"command": "open chrome and search for AI trends", "result": {"success": True}}],
        preferences={},
    )

    assert state["summary"]["online_mode"] is True
    assert state["summary"]["online_weight_strength"] >= 0.0

    prediction = model.predict_preference("open chrome and search for AI trends", preferences={})
    assert prediction["prediction"]["online_weight_score"] >= 0.0
    assert prediction["prediction"]["dominant_signal"] in {"default_browser", "notes_folder", "general"}


def test_phase5_neural_command_model_trains_advisory_routes(tmp_path):
    model = NeuralCommandModel(path=str(tmp_path / "neural_command_model.json"), min_examples=4)
    experiences = [
        {"command": "open chrome and search for laptops", "strategy": {"intent": {"type": "browser_action"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "search amazon for phones", "strategy": {"intent": {"type": "browser_action"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "list files in desktop", "strategy": {"intent": {"type": "list_files"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "backup desktop folder", "strategy": {"intent": {"type": "backup_folder"}}, "result": {"success": True}, "reward": 0.9},
        {"command": "show system status", "strategy": {"intent": {"type": "system_info"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "run powershell Get-Date", "strategy": {"intent": {"type": "system_command"}}, "result": {"success": True}, "reward": 1.0},
    ]

    state = model.fit(experiences)
    prediction = model.predict("open browser and search google")

    assert state["trained"] is True
    assert state["advisory"] is True
    assert state["metrics"]["train_examples"] >= 1
    assert prediction["source"] == "neural_command_model"
    assert prediction["advisory"] is True
    assert prediction["raw_route"] in {"web", "file", "system"}


def test_phase5_summary_includes_deep_neural_metrics(tmp_path):
    model = OfflinePreferenceModel(path=str(tmp_path / "phase5_model.json"), min_confidence=0.5)
    experiences = [
        {"command": "open chrome and search for laptops", "strategy": {"intent": {"type": "browser_action"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "search amazon for phones", "strategy": {"intent": {"type": "browser_action"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "list files in desktop", "strategy": {"intent": {"type": "list_files"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "backup desktop folder", "strategy": {"intent": {"type": "backup_folder"}}, "result": {"success": True}, "reward": 0.9},
        {"command": "show system status", "strategy": {"intent": {"type": "system_info"}}, "result": {"success": True}, "reward": 1.0},
        {"command": "run powershell Get-Date", "strategy": {"intent": {"type": "system_command"}}, "result": {"success": True}, "reward": 1.0},
    ]

    state = model.fit(experiences)
    prediction = model.predict_preference("open chrome and search for AI trends", preferences={})

    assert state["summary"]["neural_trained"] is True
    assert state["summary"]["neural_train_examples"] >= 1
    assert "neural_command_model" in state
    assert prediction["route_prediction"]["source"] == "neural_command_model"


def test_show_adaptive_evaluation_command_returns_metrics():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "show system status",
        {"tier": "direct", "intent": {"type": "system_info"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("show adaptive evaluation"))

    assert result["success"] is True
    metrics = result["results"][0]["evaluation_metrics"]
    assert "recommendation_accuracy" in metrics
    assert "user_correction_rate" in metrics


def test_classify_command_returns_adaptive_prediction():
    controller = build_controller()
    controller.agents["learning"].record_command(
        "show system status",
        {"tier": "direct", "intent": {"type": "system_info"}},
        {"success": True},
    )

    result = asyncio.run(controller.process_command("classify command show system status"))

    assert result["success"] is True
    classification = result["results"][0]["classification"]
    assert classification["predicted_intent"] in {"system_info", "intent:system_info"}
    assert classification["confidence"] >= 0.0


def test_autonomy_uses_default_browser_preference():
    controller = build_controller()
    controller.memory.save_user_preference("default_browser", "edge")

    result = asyncio.run(controller.process_command("open browser"))

    assert result["success"] is True
    assert result["tier"] == "autonomous"
    assert controller.agents["system"].opened[0][0] == "edge"


def test_autonomy_uses_notes_folder_preference(tmp_path):
    controller = build_controller()
    controller.memory.save_user_preference("notes_folder", str(tmp_path))

    result = asyncio.run(controller.process_command("make a note about roadmap"))

    assert result["success"] is True
    created_path, _ = controller.agents["file"].created[0]
    assert created_path == str(tmp_path / "roadmap_note.txt")


def test_autonomy_suggests_learned_workflows():
    controller = build_controller()

    result = asyncio.run(controller.process_command("suggest workflows"))

    assert result["success"] is True
    assert result["needs_clarification"] is True
    assert result["autonomy"]["strategy"] == "workflow_suggestions"
    assert "intent:browser_action" in result["suggestions"][0]


def test_phase3_searches_files_without_ollama():
    controller = build_controller()

    result = asyncio.run(controller.process_command("search files for roadmap in desktop"))

    assert result["success"] is True
    assert result["tier"] == "direct"
    assert controller.agents["file"].searched[0][1] == "roadmap"
    assert "Desktop" in controller.agents["file"].searched[0][0]


def test_phase3_gets_file_info_from_natural_language():
    controller = build_controller()

    result = asyncio.run(controller.process_command("show file info for launch_checklist_note.txt"))

    assert result["success"] is True
    assert result["results"][0]["name"] == "launch_checklist_note.txt"


def test_phase3_backs_up_known_folder():
    controller = build_controller()

    result = asyncio.run(controller.process_command("backup desktop as desktop_snapshot"))

    assert result["success"] is True
    assert controller.agents["file"].backups[0][1] == "desktop_snapshot"


def test_phase3_closes_application_without_council():
    controller = build_controller()

    result = asyncio.run(controller.process_command("close notepad"))

    assert result["success"] is True
    assert controller.agents["system"].closed == ["notepad"]


def test_phase3_system_network_drives_and_env_commands():
    controller = build_controller()

    network = asyncio.run(controller.process_command("network status"))
    drives = asyncio.run(controller.process_command("show drives"))
    env = asyncio.run(controller.process_command("show env PATH"))

    assert network["success"] is True
    assert drives["success"] is True
    assert env["success"] is True
    assert env["results"][0]["name"] == "PATH"


def test_dangerous_system_command_requires_confirmation():
    class ConfirmingSystemAgent(DummySystemAgent):
        def __init__(self):
            super().__init__()
            self.confirmed_runs = []

        def run_command(self, command, shell="powershell", confirmed=False):
            if "Remove-Item" in command and not confirmed:
                return {
                    "success": False,
                    "needs_confirmation": True,
                    "command": command,
                    "warning": "This command may be destructive. Please confirm execution.",
                    "matched_patterns": ["Remove-Item"],
                }
            self.confirmed_runs.append((command, shell, confirmed))
            return {"success": True, "output": command, "return_code": 0, "confirmed": confirmed}

    controller = build_controller()
    controller.agents["system"] = ConfirmingSystemAgent()

    first = asyncio.run(controller.process_command("run powershell Remove-Item test.txt"))
    second = asyncio.run(controller.process_command("confirm command"))

    assert first["success"] is False
    assert first["needs_confirmation"] is True
    assert "pending_system_command" in controller.memory.short_term
    assert second["success"] is True
    assert second["results"][0]["confirmed"] is True
    assert controller.memory.recall_short_term("pending_system_command") is None


def test_dangerous_system_command_can_be_cancelled():
    class ConfirmingSystemAgent(DummySystemAgent):
        def run_command(self, command, shell="powershell", confirmed=False):
            return {
                "success": False,
                "needs_confirmation": True,
                "command": command,
                "warning": "This command may be destructive. Please confirm execution.",
            }

    controller = build_controller()
    controller.agents["system"] = ConfirmingSystemAgent()

    first = asyncio.run(controller.process_command("run powershell Remove-Item test.txt"))
    second = asyncio.run(controller.process_command("cancel command"))

    assert first["needs_confirmation"] is True
    assert second["success"] is True
    assert second["results"][0]["cancelled"] is True
    assert controller.memory.recall_short_term("pending_system_command") is None


def test_phase3_decomposer_routes_file_search_before_web_search():
    decomposer = TaskDecomposer()

    plan = decomposer.decompose("search files for roadmap in desktop then open notepad")

    assert plan["subtasks"][0]["agent"] == "file"
    assert plan["subtasks"][0]["action"] == "search_files"
    assert plan["subtasks"][1]["agent"] == "system"
    assert plan["subtasks"][1]["action"] == "open"


def test_clarification_followup_completes_missing_target():
    controller = build_controller()

    first = asyncio.run(controller.process_command("open"))
    second = asyncio.run(controller.process_command("browser"))

    assert first["needs_clarification"] is True
    assert second["success"] is True
    assert controller.agents["system"].opened[0][0] == "chrome"


def test_display_result_prints_clarifying_question(capsys):
    controller = build_controller()

    controller._display_result({
        "success": False,
        "needs_clarification": True,
        "question": "What should I open?",
        "suggestions": ["open chrome"],
    })

    captured = capsys.readouterr()
    assert "ASC: What should I open?" in captured.out
    assert "open chrome" in captured.out


def test_parameterized_learned_direct_strategy_is_not_reused():
    controller = build_controller()

    class SimilarLearningAgent(DummyLearningAgent):
        def find_similar_success(self, command, threshold=0.75):
            return {
                "score": 1.0,
                "match": {
                    "strategy": {
                        "tier": "direct",
                        "complexity": "simple",
                        "intent": {
                            "type": "create_file",
                            "path": "old_note.txt",
                        },
                    }
                },
            }

    controller.agents["learning"] = SimilarLearningAgent()

    strategy = controller._determine_execution_strategy("create file named new_note.txt")

    assert strategy["source"] == "rules"
    assert strategy["intent"]["path"].endswith("new_note.txt")


def test_explicit_sequence_is_not_collapsed_by_learning():
    controller = build_controller()

    class SimilarLearningAgent(DummyLearningAgent):
        def find_similar_success(self, command, threshold=0.75):
            return {
                "score": 1.0,
                "match": {
                    "strategy": {
                        "tier": "direct",
                        "complexity": "simple",
                        "intent": {"type": "system_info"},
                    }
                },
            }

    controller.agents["learning"] = SimilarLearningAgent()

    strategy = controller._determine_execution_strategy(
        "show system status and then list running processes"
    )

    assert strategy["tier"] == "sequential"
    assert strategy["source"] == "decomposer"


def test_memory_paths_survive_cwd_change(tmp_path, monkeypatch):
    from core.memory import MemorySystem

    memory = MemorySystem("./config/settings.json")
    original_db = memory.episodic_db
    monkeypatch.chdir(tmp_path)

    memory.remember_episode(
        task="cwd change test",
        action="test",
        result="ok",
        success=True,
    )

    assert memory.episodic_db == original_db
    assert memory.get_memory_stats()["episodes_count"] >= 1


def test_learning_paths_survive_cwd_change(tmp_path, monkeypatch):
    from agents.learning_agent import LearningAgent

    agent = LearningAgent("./config/settings.json")
    original_path = agent.replay.path
    monkeypatch.chdir(tmp_path)

    agent.record_command(
        "learning cwd test",
        {"tier": "direct", "intent": {"type": "system_info"}},
        {"success": True, "tier": "direct", "steps_completed": 1, "steps_total": 1},
    )

    assert agent.replay.path == original_path
    assert original_path.exists()


def test_tool_registry_converts_handler_exception_to_failure():
    from core.tool_registry import ToolRegistry, ToolSpec

    registry = ToolRegistry()

    def explode(action, params, context):
        raise RuntimeError("boom")

    registry.register(ToolSpec(
        name="boom_tool",
        agent="test",
        description="Explodes for testing",
        actions=["boom"],
        handler=explode,
    ))

    result = asyncio.run(registry.execute("boom", {}, "context"))

    assert result["success"] is False
    assert result["tool"] == "boom_tool"
    assert result["error"] == "boom"


def test_web_agent_site_search_builds_known_site_url():
    system_agent = StubSystemAgent()
    vision_agent = StubVisionAgent()
    learning_agent = DummyLearningAgent()
    agent = WebAgent(
        config_path="./config/settings.json",
        system_agent=system_agent,
        vision_agent=vision_agent,
        learning_agent=learning_agent,
    )
    agent.browser_driver = None
    agent.navigation_delay_seconds = 0

    result = asyncio.run(agent.search_site("laptops", site="amazon", browser_name="chrome"))

    assert result["success"] is True
    assert result["site"] == "amazon"
    assert result["url"] == "https://www.amazon.in/s?k=laptops"


def test_routed_form_action_navigates_before_filling():
    controller = build_controller()
    web_agent = controller.agents["web"]

    result = asyncio.run(
        controller._route_action(
            "form",
            {
                "url": "https://example.com/form",
                "fields": {"name": "Swapnil"},
                "focus_first_field": True,
            },
            "fill the form",
        )
    )

    assert result["success"] is True
    assert result["navigated_url"] == "https://example.com/form"
    assert web_agent.navigated == [("https://example.com/form", "chrome")]


def test_phase5_cold_start_bootstrap():
    from learning.phase5_model import OfflinePreferenceModel
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        model = OfflinePreferenceModel(tmp.name)
        state = model.fit([])
        assert state["summary"]["clusters"] >= 1
        assert "prediction" in state
        assert state["summary"]["offline"] is True


def test_learning_agent_explicit_preference_retraining():
    from agents.learning_agent import LearningAgent
    import tempfile, json

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cfg_file:
        config = {
            "paths": {"data": tempfile.gettempdir()},
            "learning": {"history_limit": 100, "adaptive_min_confidence": 0.5}
        }
        cfg_file.write(json.dumps(config).encode("utf-8"))
        cfg_file.flush()

        agent = LearningAgent(config_path=cfg_file.name)
        res = agent.learn_explicit_preference("default_browser", "firefox")
        assert res["success"] is True
        assert res["learned_preference"] == {"default_browser": "firefox"}

