import sys
import requests
import pytest
import subprocess

from agents.system_agent import SystemAgent


def test_health_check_ollama_returns_false_for_bad_host(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        '{"ollama": {"host": "http://127.0.0.1:59999"}}', encoding="utf-8"
    )

    agent = SystemAgent(config_path=str(config_path))
    assert agent.health_check_ollama(timeout=0.5) is False


def test_start_ollama_skips_when_executable_missing(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text('{"paths": {"ollama": "C:/fake/path/ollama.exe"}, "ollama": {"host": "http://127.0.0.1:11434"}}', encoding="utf-8")
    agent = SystemAgent(config_path=str(config_path))

    result = agent.start_ollama(wait=False)
    assert result["success"] is False
    assert "not found" in result["error"].lower() or "cannot find" in result["error"].lower()


def test_start_ollama_applies_ram_safe_environment(tmp_path, monkeypatch):
    exe = tmp_path / "ollama.exe"
    exe.write_text("fake", encoding="utf-8")
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        '{"paths": {"ollama": "%s"}, "ollama": {"host": "http://127.0.0.1:11434", "max_loaded_models": 1, "keep_alive": "0"}}'
        % str(exe).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    captured = {}

    class FakeProcess:
        pid = 123

    def fake_popen(cmd, shell=False, env=None, **kwargs):
        captured["cmd"] = cmd
        captured["shell"] = shell
        captured["env"] = env
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    agent = SystemAgent(config_path=str(config_path))

    result = agent.start_ollama(wait=False)

    assert result["success"] is True
    assert captured["env"]["OLLAMA_MAX_LOADED_MODELS"] == "1"
    assert captured["env"]["OLLAMA_KEEP_ALIVE"] == "0"


def test_start_ollama_detaches_so_it_survives_the_session(tmp_path, monkeypatch):
    """Ollama must not die when the session that started it is closed.

    Started as a plain child it shared VEGA's console process group, so
    Ctrl+C out of a session killed Ollama too. Every session in the logs
    then began with "Ollama not running, attempting auto-start", and any
    command issued during the three-to-five second restart could not reach
    a model - which is what "the model doesn't connect sometimes" was.
    """
    exe = tmp_path / "ollama.exe"
    exe.write_text("fake", encoding="utf-8")
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        '{"paths": {"ollama": "%s"}, "ollama": {"host": "http://127.0.0.1:11434"}}'
        % str(exe).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    captured = {}

    class FakeProcess:
        pid = 456

    def fake_popen(cmd, shell=False, env=None, **kwargs):
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    agent = SystemAgent(config_path=str(config_path))

    result = agent.start_ollama(wait=False)
    assert result["success"] is True

    if sys.platform == "win32":
        flags = captured.get("creationflags", 0)
        assert flags & subprocess.CREATE_NEW_PROCESS_GROUP, (
            "Ollama shares VEGA's process group, so Ctrl+C will kill it too")
    else:
        assert captured.get("start_new_session") is True

    # It must also not be reaped as one of ours on the way out.
    assert FakeProcess.pid not in agent.managed_processes, (
        "Ollama is in managed_processes, so shutdown may terminate it")
