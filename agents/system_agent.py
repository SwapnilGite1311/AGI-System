"""
System Agent - Operating system level control
Controls files, processes, applications, and local interaction.
Enhanced with: command history, dangerous command protection,
cybersecurity tools, and advanced system queries.
"""

import hashlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psutil
import pyautogui
from loguru import logger
import requests


class SystemAgent:
    """
    Handles system-level operations:
    - Process management
    - Application control
    - System commands with history & safety
    - Resource monitoring
    - Keyboard and mouse automation
    - Cybersecurity scanning
    """

    SYSTEM_APPS = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "explorer": "explorer.exe",
        "paint": "mspaint.exe",
        "wordpad": "write.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "firefox": "firefox.exe",
        "brave": "brave.exe",
        "opera": "opera.exe",
        "browser": "msedge.exe",
        "ollama": "ollama.exe",
    }

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize the system agent."""

        with open(config_path, "r", encoding="utf-8") as file:
            self.config = json.load(file)

        self.app_cache_file = Path("./data/app_cache.json")
        self.app_cache = self._load_app_cache()
        self.custom_paths = self.config.get("paths", {})

        # Command history & safety
        agent_config = self.config.get("system_agent", {})
        self.command_history: List[Dict[str, Any]] = []
        self.command_history_limit = int(agent_config.get("command_history_limit", 200))
        self.dangerous_patterns = agent_config.get("dangerous_patterns", [])
        self.dangerous_action = agent_config.get("dangerous_command_action", "confirm")
        self.command_timeout = int(agent_config.get("command_timeout_seconds", 30))

        # Cybersecurity config
        cyber_config = self.config.get("cybersecurity", {})
        self.port_scan_timeout = float(cyber_config.get("port_scan_timeout_seconds", 1.0))
        self.common_ports = cyber_config.get("common_ports", [80, 443, 22, 8080])
        self.ssl_timeout = float(cyber_config.get("ssl_check_timeout_seconds", 5))
        self.max_port_range = int(cyber_config.get("max_port_range", 1024))

        # Track subprocesses for cleanup
        self.managed_processes: Dict[int, subprocess.Popen] = {}

        logger.info("System Agent initialized (enhanced)")

    def __del__(self):
        """Cleanup managed processes on destruction."""
        self.cleanup_managed_processes()
    
    def cleanup_managed_processes(self):
        """Clean up all managed subprocesses."""
        for pid, proc in list(self.managed_processes.items()):
            try:
                if proc.poll() is None:  # Process is still running
                    proc.terminate()
                    logger.info(f"Terminated managed process {pid}")
            except Exception as exc:
                logger.warning(f"Failed to terminate process {pid}: {exc}")
        self.managed_processes.clear()

    # ============= APP CACHE =============

    def _load_app_cache(self) -> Dict[str, str]:
        """Load cached app locations."""
        if self.app_cache_file.exists():
            try:
                with open(self.app_cache_file, "r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception:
                return {}
        return {}

    def _save_app_cache(self):
        """Persist the app cache."""
        self.app_cache_file.parent.mkdir(exist_ok=True)
        with open(self.app_cache_file, "w", encoding="utf-8") as file:
            json.dump(self.app_cache, file, indent=2)

    # ============= PROCESS MANAGEMENT =============

    def list_processes(self, filter_name: str = None) -> List[Dict[str, Any]]:
        """List running processes, optionally filtered by name."""
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                name = info.get("name") or ""
                if filter_name and filter_name.lower() not in name.lower():
                    continue
                processes.append({
                    "pid": info["pid"],
                    "name": name,
                    "cpu": info["cpu_percent"],
                    "memory": info["memory_percent"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        logger.debug("Found {} processes", len(processes))
        return processes

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """Get detailed info about a specific process by PID."""
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                return {
                    "success": True,
                    "pid": pid,
                    "name": proc.name(),
                    "status": proc.status(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(proc.create_time()).isoformat(),
                    "exe": proc.exe() if proc.exe() else "N/A",
                    "num_threads": proc.num_threads(),
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            return {"success": False, "pid": pid, "error": str(exc)}

    def wait_for_process(self, name: str, timeout: int = 30) -> Dict[str, Any]:
        """Wait for a process to appear (e.g. after launching an app)."""
        start = time.time()
        while time.time() - start < timeout:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if name.lower() in (proc.info.get("name") or "").lower():
                        return {"success": True, "pid": proc.info["pid"], "name": proc.info["name"]}
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            time.sleep(0.5)
        return {"success": False, "error": f"Process '{name}' not found within {timeout}s"}

    def get_window_titles(self) -> List[Dict[str, Any]]:
        """Get titles of all visible windows (Windows-only via PowerShell)."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-Process | Where-Object {$_.MainWindowTitle} | "
                 "Select-Object Id, ProcessName, MainWindowTitle | ConvertTo-Json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                return [{"pid": w.get("Id"), "process": w.get("ProcessName"),
                         "title": w.get("MainWindowTitle")} for w in data]
        except Exception as exc:
            logger.error("Window titles failed: {}", str(exc))
        return []

    def kill_process(self, process_name: str = None, pid: int = None) -> Dict[str, Any]:
        """Kill a process by name or PID."""
        try:
            if pid:
                proc = psutil.Process(pid)
                proc.terminate()
                logger.info("Killed process PID: {}", pid)
                return {"success": True, "pid": pid}
            if process_name:
                killed_count = 0
                for proc in psutil.process_iter(["pid", "name"]):
                    if process_name.lower() in (proc.info.get("name") or "").lower():
                        proc.terminate()
                        killed_count += 1
                logger.info("Killed {} instances of {}", killed_count, process_name)
                return {"success": True, "killed": killed_count, "process": process_name}
            return {"success": False, "error": "No process name or PID provided"}
        except Exception as exc:
            logger.error("Kill process failed: {}", str(exc))
            return {"success": False, "error": str(exc)}

    # ============= APPLICATION CONTROL =============

    def find_application(self, app_name: str) -> Optional[str]:
        """Find an application executable with caching."""
        app_key = app_name.lower()
        if app_key in self.app_cache:
            cached_path = self.app_cache[app_key]
            if os.path.exists(cached_path):
                return cached_path
            del self.app_cache[app_key]

        custom_path = self.custom_paths.get(app_key)
        if custom_path and os.path.exists(custom_path):
            self.app_cache[app_key] = custom_path
            self._save_app_cache()
            return custom_path

        path_result = shutil.which(f"{app_name}.exe") or shutil.which(app_name)
        if path_result:
            self.app_cache[app_key] = path_result
            self._save_app_cache()
            return path_result

        search_paths = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        ]
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for search_path in search_paths:
            if not os.path.exists(search_path):
                continue
            try:
                result = subprocess.run(
                    ["where", "/R", search_path, f"{app_name}.exe"],
                    capture_output=True, text=True, timeout=15,
                    creationflags=create_no_window,
                )
                if result.returncode == 0 and result.stdout.strip():
                    exe_path = result.stdout.strip().splitlines()[0]
                    self.app_cache[app_key] = exe_path
                    self._save_app_cache()
                    return exe_path
            except (subprocess.TimeoutExpired, Exception):
                continue

        desktop = Path.home() / "Desktop"
        try:
            for shortcut in desktop.glob("*.lnk"):
                if app_key in shortcut.name.lower():
                    self.app_cache[app_key] = str(shortcut)
                    self._save_app_cache()
                    return str(shortcut)
        except Exception:
            pass
        logger.warning("Application not found: {}", app_name)
        return None

    def _resolve_application_executable(self, app_name: str) -> Optional[str]:
        """Resolve the best executable path for an application."""

        app_key = app_name.lower()
        mapped = self.SYSTEM_APPS.get(app_key)
        candidates = []

        if mapped:
            candidates.append(mapped)

        # Search using the friendly name first.
        candidates.append(app_name)

        browser_specific = {
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "google chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ],
            "microsoft edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            ],
            "firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "opera": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera\opera.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
            ],
            "brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
        }

        for candidate_path in browser_specific.get(app_key, []):
            if os.path.exists(candidate_path):
                self.app_cache[app_key] = candidate_path
                self._save_app_cache()
                return candidate_path

        for candidate in candidates:
            if not candidate:
                continue
            resolved = self.find_application(candidate.replace(".exe", ""))
            if resolved:
                return resolved

            if candidate.lower().endswith(".exe"):
                direct_path = shutil.which(candidate)
                if direct_path:
                    return direct_path

        return None

    def open_application(self, app_name: str, args: List[str] = None) -> Dict[str, Any]:
        """Open an application and optionally pass launch arguments."""
        app_key = app_name.lower()
        exe = self._resolve_application_executable(app_name)
        if not exe:
            if os.name == "nt":
                # Refuse implausible launch targets (misrouted sentences like
                # "you didn't opened chrome at all!") instead of reporting a
                # fake success when Windows cannot find the file.
                tokens = app_name.split()
                if len(tokens) > 3 and not app_name.lower().endswith((".exe", ".lnk")):
                    return {
                        "success": False,
                        "application": app_name,
                        "error": f"'{app_name}' does not look like an installed application.",
                    }
                try:
                    joined_args = " ".join(f'"{arg}"' for arg in (args or []))
                    process = subprocess.Popen(f'start "" "{app_name}" {joined_args}'.strip(), shell=True)
                    self.managed_processes[process.pid] = process
                    logger.success("Opened via start: {}", app_name)
                    return {
                        "success": True,
                        "application": app_name,
                        "pid": process.pid,
                        "path": app_name,
                        "launch_mode": "start_fallback",
                    }
                except Exception as exc:
                    logger.warning("Windows start fallback failed for {}: {}", app_name, str(exc))
            return {"success": False, "application": app_name,
                    "error": f"Application '{app_name}' not found on this system."}
        try:
            if exe.lower().endswith(".lnk"):
                os.startfile(exe)
                return {"success": True, "application": app_name, "pid": None, "path": exe}
            cmd = [exe]
            if args:
                cmd.extend(args)
            process = subprocess.Popen(cmd, shell=False)
            self.managed_processes[process.pid] = process
            logger.success("Opened: {} (PID: {})", app_name, process.pid)
            return {"success": True, "application": app_name, "pid": process.pid, "path": exe}
        except Exception as exc:
            logger.error("Failed to open {}: {}", app_name, str(exc))
            return {"success": False, "application": app_name, "error": str(exc)}

    def close_application(self, app_name: str) -> Dict[str, Any]:
        """Close an application by name."""
        return self.kill_process(process_name=app_name)

    # ============= OLLAMA HELPERS =============

    def health_check_voice_server(self, timeout: float = 2.0) -> bool:
        """Check whether the voice server is reachable."""
        voice_url = self.config.get("audio", {}).get("voice_service_url", "http://localhost:5000")
        if not voice_url:
            return False
        try:
            resp = requests.get(f"{voice_url}/health", timeout=timeout)
            return 200 <= resp.status_code < 400
        except Exception:
            return False

    def start_voice_server(self, wait: bool = True, timeout: int = 15) -> Dict[str, Any]:
        """Attempt to start the voice server using the local-server path."""
        # local-server is a sibling of AGI-System:
        #   <root>/AGI-System/agents/system_agent.py -> parents[2] = <root>
        # Override with VOICE_SERVER_PATH env var when placed elsewhere.
        voice_server_path = Path(
            os.environ.get(
                "VOICE_SERVER_PATH",
                str(Path(__file__).resolve().parents[2] / "local-server" / "server.py"),
            )
        )
        if not voice_server_path.exists():
            return {"success": False, "error": f"Voice server script not found at {voice_server_path}."}

        try:
            import subprocess
            env = os.environ.copy()
            proc = subprocess.Popen(
                [sys.executable, str(voice_server_path)],
                shell=False,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.managed_processes[proc.pid] = proc
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if not wait:
            return {"success": True, "pid": proc.pid, "started": True}

        start = time.time()
        while time.time() - start < timeout:
            if self.health_check_voice_server(timeout=1.0):
                return {
                    "success": True,
                    "pid": proc.pid,
                    "voice_service_url": self.config.get("audio", {}).get("voice_service_url"),
                }
            time.sleep(0.5)

        return {"success": False, "pid": proc.pid, "error": "Voice server did not become healthy in time."}

    def stop_voice_server(self) -> Dict[str, Any]:
        """Stop the voice server process."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info.get('name') and 'python' in proc.info.get('name', '').lower():
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and 'server.py' in ' '.join(cmdline):
                        proc.terminate()
                        return {"success": True, "stopped": True, "pid": proc.pid}
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {"success": False, "error": "Voice server process not found."}

    def health_check_ollama(self, timeout: float = 2.0) -> bool:
        """Check whether the configured Ollama host is reachable."""
        host = self.config.get("ollama", {}).get("host")
        if not host:
            return False
        try:
            resp = requests.get(host, timeout=timeout)
            return 200 <= resp.status_code < 400
        except Exception:
            return False

    def start_ollama(self, args: List[str] = None, wait: bool = True, timeout: int = 30) -> Dict[str, Any]:
        """Attempt to start Ollama using configured paths or resolved executable."""
        exe = self.custom_paths.get("ollama") or self._resolve_application_executable("ollama")
        if not exe:
            return {"success": False, "error": "Ollama executable not found in paths or on PATH."}

        cmd = [exe]
        cmd.extend(args if args is not None else ["serve"])
        try:
            env = os.environ.copy()
            ollama_config = self.config.get("ollama", {})
            if ollama_config.get("max_loaded_models") is not None:
                env.setdefault("OLLAMA_MAX_LOADED_MODELS", str(ollama_config["max_loaded_models"]))
            if ollama_config.get("keep_alive") is not None:
                env.setdefault("OLLAMA_KEEP_ALIVE", str(ollama_config["keep_alive"]))
            proc = subprocess.Popen(cmd, shell=False, env=env)
            self.managed_processes[proc.pid] = proc
        except Exception as exc:
            return {"success": False, "error": str(exc)}

        if not wait:
            return {"success": True, "pid": proc.pid, "started": True}

        start = time.time()
        max_retries = int(self.config.get("ollama", {}).get("max_retries", 3))
        attempt = 0
        while time.time() - start < timeout and attempt < max_retries:
            if self.health_check_ollama(timeout=2.0):
                return {
                    "success": True,
                    "pid": proc.pid,
                    "host": self.config.get("ollama", {}).get("host"),
                }
            time.sleep(1.0)
            attempt += 1

        return {"success": False, "pid": proc.pid, "error": "Ollama did not become healthy in time."}

    def stop_ollama(self) -> Dict[str, Any]:
        """Terminate running Ollama processes."""
        killed = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info.get("name") and "ollama" in proc.info.get("name").lower():
                    proc.terminate()
                    killed += 1
            except Exception:
                continue
        return {"success": True, "killed": killed}

    def search_applications(self, query: str = None) -> List[Dict[str, Any]]:
        """Search for installed applications."""
        found_apps = []
        search_locations = [
            (r"C:\Program Files", "Program Files"),
            (r"C:\Program Files (x86)", "Program Files (x86)"),
        ]
        create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for location, name in search_locations:
            if not os.path.exists(location):
                continue
            try:
                result = subprocess.run(
                    ["where", "/R", location, "*.exe"],
                    capture_output=True, text=True, timeout=30,
                    creationflags=create_no_window,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().splitlines()[:50]:
                        exe_path = line.strip()
                        exe_name = os.path.basename(exe_path)
                        if query and query.lower() not in exe_name.lower():
                            continue
                        found_apps.append({"name": exe_name, "path": exe_path, "location": name})
            except Exception:
                continue
        return found_apps

    # ============= COMMAND EXECUTION WITH SAFETY =============

    def is_dangerous_command(self, command: str) -> bool:
        """Check if a command matches any dangerous pattern."""
        cmd_lower = command.lower()
        return any(pattern.lower() in cmd_lower for pattern in self.dangerous_patterns)

    def is_network_call(self, command: str) -> bool:
        """Detect shell commands attempting direct network requests.

        LLM planners occasionally hallucinate external API endpoints and try
        to invoke them via PowerShell/curl. All legitimate network activity
        must go through the web agent's registered tools instead.
        """
        cmd_lower = command.lower()
        network_patterns = (
            "invoke-webrequest", "invoke-restmethod", "iwr ", "irm ",
            "curl ", "wget ", "http://", "https://", "ftp://",
            "system.net.webclient", "start-process *-http*",
            "net.webclient", "downloadstring", "uploadfile",
        )
        return any(p in cmd_lower for p in network_patterns)

    def run_command(self, command: str, shell: str = "powershell",
                    confirmed: bool = False) -> Dict[str, Any]:
        """Run a system command with safety checks and history tracking."""
        if not command or not command.strip():
            return {"success": False, "error": "Empty command - nothing to run."}

        logger.info("Running command: {}", command[:80])

        # Safety check
        if self.is_dangerous_command(command) and not confirmed:
            logger.warning("Dangerous command detected: {}", command[:80])
            return {
                "success": False,
                "needs_confirmation": True,
                "command": command,
                "warning": "This command may be destructive. Please confirm execution.",
                "matched_patterns": [p for p in self.dangerous_patterns if p.lower() in command.lower()],
            }

        # Network-call block: shell commands must never touch the network.
        # Web activity belongs to the web agent's registered tools; LLM
        # planners sometimes hallucinate API endpoints (e.g. fake email APIs).
        if self.is_network_call(command):
            logger.warning("Blocked shell network call: {}", command[:80])
            return {
                "success": False,
                "blocked": True,
                "command": command,
                "error": (
                    "Direct network calls from shell commands are blocked. "
                    "Use the web agent (navigate/search) or a dedicated "
                    "configured service instead."
                ),
            }

        try:
            if shell == "powershell":
                full_cmd = ["powershell", "-Command", command]
            else:
                full_cmd = ["cmd", "/c", command]

            start_time = time.time()
            result = subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=self.command_timeout,
            )
            elapsed = round(time.time() - start_time, 3)

            entry = {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
                "return_code": result.returncode,
                "elapsed_seconds": elapsed,
            }

            # Track history
            self._record_command(command, shell, entry)
            return entry

        except subprocess.TimeoutExpired:
            logger.error("Command timed out")
            entry = {"success": False, "error": "Command timeout",
                      "suggestion": f"Increase timeout (current: {self.command_timeout}s)"}
            self._record_command(command, shell, entry)
            return entry
        except FileNotFoundError:
            entry = {"success": False, "error": "Shell not found",
                      "suggestion": f"Shell '{shell}' is not available on this system"}
            self._record_command(command, shell, entry)
            return entry
        except PermissionError:
            entry = {"success": False, "error": "Permission denied",
                      "suggestion": "Try running as administrator"}
            self._record_command(command, shell, entry)
            return entry
        except Exception as exc:
            entry = {"success": False, "error": str(exc)}
            self._record_command(command, shell, entry)
            return entry

    def _record_command(self, command: str, shell: str, result: Dict[str, Any]):
        """Store command execution in history ring buffer."""
        self.command_history.append({
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "shell": shell,
            "success": result.get("success", False),
            "return_code": result.get("return_code"),
            "elapsed": result.get("elapsed_seconds"),
        })
        if len(self.command_history) > self.command_history_limit:
            self.command_history = self.command_history[-self.command_history_limit:]

    def get_command_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent command history entries."""
        return self.command_history[-limit:]

    # ============= SYSTEM INFORMATION =============

    def get_system_info(self) -> Dict[str, Any]:
        """Get CPU, memory, disk, and platform information."""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu": {"percent": cpu_percent, "cores": psutil.cpu_count()},
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": disk.percent,
            },
            "platform": sys.platform,
            "python_version": sys.version,
        }

    def get_disk_usage_all_drives(self) -> List[Dict[str, Any]]:
        """Get disk usage for all mounted drives."""
        drives = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                drives.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "used_percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return drives

    def get_network_info(self) -> Dict[str, Any]:
        """Get network interface and connection information."""
        interfaces = {}
        for name, addrs in psutil.net_if_addrs().items():
            interfaces[name] = []
            for addr in addrs:
                interfaces[name].append({
                    "family": str(addr.family),
                    "address": addr.address,
                    "netmask": addr.netmask,
                })

        connections = []
        try:
            for conn in psutil.net_connections(kind="inet")[:20]:
                connections.append({
                    "status": conn.status,
                    "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A",
                    "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A",
                    "pid": conn.pid,
                })
        except (psutil.AccessDenied, PermissionError):
            connections = [{"error": "Access denied — run as admin for full details"}]

        io = psutil.net_io_counters()
        return {
            "success": True,
            "interfaces": interfaces,
            "active_connections": connections,
            "bytes_sent_mb": round(io.bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(io.bytes_recv / (1024**2), 2),
        }

    def get_environment_variable(self, var_name: str) -> Dict[str, Any]:
        """Get a specific environment variable."""
        value = os.environ.get(var_name)
        if value is not None:
            return {"success": True, "variable": var_name, "value": value}
        return {"success": False, "error": f"Variable '{var_name}' not set"}

    def list_environment_variables(self, filter_str: str = None) -> Dict[str, str]:
        """List environment variables, optionally filtered."""
        env = dict(os.environ)
        if filter_str:
            env = {k: v for k, v in env.items() if filter_str.lower() in k.lower()}
        return env

    # ============= CYBERSECURITY TOOLS =============

    def scan_ports(self, host: str, port_range: str = None) -> Dict[str, Any]:
        """
        Scan ports on a host. Use 'common' for common ports or '1-1024' for range.
        Designed for your own servers/websites only.
        """
        logger.info("Port scanning: {}", host)
        open_ports = []
        closed_count = 0

        if port_range and port_range != "common":
            try:
                start, end = map(int, port_range.split("-"))
                end = min(end, start + self.max_port_range)
                ports = range(start, end + 1)
            except ValueError:
                return {"success": False, "error": f"Invalid port range: {port_range}"}
        else:
            ports = self.common_ports

        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.port_scan_timeout)
                result = sock.connect_ex((host, port))
                if result == 0:
                    try:
                        service = socket.getservbyport(port)
                    except OSError:
                        service = "unknown"
                    open_ports.append({"port": port, "service": service, "state": "open"})
                else:
                    closed_count += 1
                sock.close()
            except socket.gaierror:
                return {"success": False, "error": f"Cannot resolve host: {host}"}
            except Exception:
                closed_count += 1

        return {
            "success": True,
            "host": host,
            "open_ports": open_ports,
            "closed_count": closed_count,
            "total_scanned": len(list(ports)),
        }

    def check_ssl_certificate(self, domain: str) -> Dict[str, Any]:
        """Check SSL certificate validity and details for a domain."""
        logger.info("SSL check: {}", domain)
        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=self.ssl_timeout) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    not_after = cert.get("notAfter", "")
                    not_before = cert.get("notBefore", "")
                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    subject = dict(x[0] for x in cert.get("subject", []))

                    # Check expiry
                    from email.utils import parsedate_to_datetime
                    expiry = parsedate_to_datetime(not_after)
                    days_remaining = (expiry - datetime.now(expiry.tzinfo)).days

                    return {
                        "success": True,
                        "domain": domain,
                        "valid": True,
                        "issuer": issuer.get("organizationName", "Unknown"),
                        "subject": subject.get("commonName", domain),
                        "valid_from": not_before,
                        "valid_until": not_after,
                        "days_remaining": days_remaining,
                        "expired": days_remaining < 0,
                        "protocol": ssock.version(),
                    }
        except ssl.SSLCertVerificationError as exc:
            return {"success": True, "domain": domain, "valid": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "domain": domain, "error": str(exc)}

    def check_security_headers(self, url: str) -> Dict[str, Any]:
        """Check HTTP security headers for a website."""
        logger.info("Security headers check: {}", url)
        try:
            import urllib.request
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "ASC-SecurityScanner/1.0")
            with urllib.request.urlopen(req, timeout=10) as response:
                headers = dict(response.headers)

            important_headers = {
                "Strict-Transport-Security": "HSTS — forces HTTPS",
                "Content-Security-Policy": "CSP — prevents XSS",
                "X-Frame-Options": "Clickjacking protection",
                "X-Content-Type-Options": "MIME sniffing prevention",
                "X-XSS-Protection": "XSS filter (legacy)",
                "Referrer-Policy": "Controls referrer info leakage",
                "Permissions-Policy": "Controls browser features",
            }

            results = {}
            missing = []
            for header, description in important_headers.items():
                value = headers.get(header)
                if value:
                    results[header] = {"present": True, "value": value, "purpose": description}
                else:
                    results[header] = {"present": False, "purpose": description}
                    missing.append(header)

            score = round((len(important_headers) - len(missing)) / len(important_headers) * 100) if important_headers else 0
            return {
                "success": True,
                "url": url,
                "headers": results,
                "missing_count": len(missing),
                "security_score": score,
                "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "F",
            }
        except Exception as exc:
            return {"success": False, "url": url, "error": str(exc)}

    def dns_lookup(self, domain: str) -> Dict[str, Any]:
        """Perform DNS lookup for a domain."""
        try:
            results = {"domain": domain, "success": True}
            # A record
            try:
                ips = socket.gethostbyname_ex(domain)
                results["hostname"] = ips[0]
                results["aliases"] = ips[1]
                results["ip_addresses"] = ips[2]
            except socket.gaierror as exc:
                results["a_record_error"] = str(exc)
            # Reverse DNS
            if results.get("ip_addresses"):
                try:
                    reverse = socket.gethostbyaddr(results["ip_addresses"][0])
                    results["reverse_dns"] = reverse[0]
                except Exception:
                    results["reverse_dns"] = "N/A"
            return results
        except Exception as exc:
            return {"success": False, "domain": domain, "error": str(exc)}

    # ============= KEYBOARD & MOUSE =============

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Any]:
        """Type text into the active application."""
        try:
            pyautogui.write(text, interval=interval)
            return {"success": True, "text": text}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a single key."""
        try:
            pyautogui.press(key)
            return {"success": True, "key": key}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def press_hotkey(self, *keys: str) -> Dict[str, Any]:
        """Press a keyboard shortcut such as Ctrl+A or Ctrl+L."""
        try:
            pyautogui.hotkey(*keys)
            return {"success": True, "keys": list(keys)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def click_mouse(self, x: int = None, y: int = None) -> Dict[str, Any]:
        """Click the mouse at a specific location or at the current cursor."""
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y)
            else:
                pyautogui.click()
            return {"success": True, "x": x, "y": y}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_mouse_position(self) -> Dict[str, int]:
        """Get the current mouse position."""
        x, y = pyautogui.position()
        return {"x": x, "y": y}


def test_system_agent():
    """Basic smoke tests for the system agent."""
    agent = SystemAgent()

    print("\n=== TEST 1: System Info ===")
    print(json.dumps(agent.get_system_info(), indent=2))

    print("\n=== TEST 2: List Processes ===")
    processes = agent.list_processes(filter_name="python")
    print(f"Found {len(processes)} Python processes")

    print("\n=== TEST 3: Disk Drives ===")
    drives = agent.get_disk_usage_all_drives()
    for d in drives:
        print(f"  {d['device']} — {d['free_gb']}GB free ({d['used_percent']}% used)")

    print("\n=== TEST 4: Dangerous Command Check ===")
    result = agent.run_command("format C:")
    print(f"Needs confirmation: {result.get('needs_confirmation')}")

    print("\n=== TEST 5: Safe Command ===")
    result = agent.run_command("echo Hello from AGI System")
    print(f"Output: {result.get('output', '').strip()}")


if __name__ == "__main__":
    test_system_agent()
