"""
Task decomposition helpers for multi-step ASC workflows.
"""

import re
from pathlib import Path
from typing import Any, Dict, List


class TaskDecomposer:
    """Breaks complex commands into smaller routed subtasks."""

    def should_decompose(self, command: str, complexity: str) -> bool:
        normalized = command.lower()
        if complexity in {"complex", "critical"}:
            return True
        return any(token in normalized for token in [" and ", " then ", " after that "])

    def decompose(self, command: str) -> Dict[str, Any]:
        normalized = " ".join(command.lower().split())
        normalized = normalized.replace("reseach", "research")

        # 1. Template: Download & Organize
        if "download" in normalized and ("organize" in normalized or "move" in normalized):
            url_match = re.search(r"https?://[^\s]+", command)
            download_url = url_match.group(0) if url_match else "https://example.com/file.zip"
            dest_dir = "Downloads"
            if "desktop" in normalized:
                dest_dir = "Desktop"
            elif "documents" in normalized:
                dest_dir = "Documents"
                
            return {
                "goal": command,
                "strategy": "download_and_organize",
                "estimated_total_seconds": 15,
                "subtasks": [
                    {
                        "id": "step-1",
                        "agent": "web",
                        "action": "navigate",
                        "params": {"url": download_url},
                        "description": f"Navigate to download URL: {download_url}",
                        "estimated_seconds": 5,
                        "dependencies": []
                    },
                    {
                        "id": "step-2",
                        "agent": "system",
                        "action": "wait_for_process",
                        "params": {"name": "chrome"},
                        "description": "Wait for browser process to verify launch",
                        "estimated_seconds": 3,
                        "dependencies": ["step-1"]
                    },
                    {
                        "id": "step-3",
                        "agent": "file",
                        "action": "organize",
                        "params": {"directory": dest_dir},
                        "description": f"Organize the target folder '{dest_dir}' by file type",
                        "estimated_seconds": 7,
                        "dependencies": ["step-2"]
                    }
                ]
            }

        # 2. Template: Compare Files
        if "compare" in normalized and ("file" in normalized or "folder" in normalized):
            # Try to find file paths/names
            files = re.findall(r"[\w\-\.\/]+\.\w+", command)
            file1 = files[0] if len(files) > 0 else "file1.txt"
            file2 = files[1] if len(files) > 1 else "file2.txt"
            
            return {
                "goal": command,
                "strategy": "compare_files",
                "estimated_total_seconds": 8,
                "subtasks": [
                    {
                        "id": "step-1",
                        "agent": "file",
                        "action": "list",
                        "params": {"path": "."},
                        "description": "Verify presence of target files in current workspace",
                        "estimated_seconds": 2,
                        "dependencies": []
                    },
                    {
                        "id": "step-2",
                        "agent": "system",
                        "action": "run_command",
                        "params": {"command": f"Compare-Object (Get-Content {file1}) (Get-Content {file2})"},
                        "description": f"Run system comparison between {file1} and {file2}",
                        "estimated_seconds": 6,
                        "dependencies": ["step-1"]
                    }
                ]
            }

        # 3. Template: Backup & Clean
        if "backup" in normalized and ("clean" in normalized or "delete" in normalized or "remove" in normalized):
            source_dir = "."
            if "desktop" in normalized:
                source_dir = "Desktop"
            elif "documents" in normalized:
                source_dir = "Documents"
                
            return {
                "goal": command,
                "strategy": "backup_and_clean",
                "estimated_total_seconds": 20,
                "subtasks": [
                    {
                        "id": "step-1",
                        "agent": "file",
                        "action": "list",
                        "params": {"path": source_dir},
                        "description": f"Verify files to backup in {source_dir}",
                        "estimated_seconds": 3,
                        "dependencies": []
                    },
                    {
                        "id": "step-2",
                        "agent": "system",
                        "action": "run_command",
                        "params": {"command": f"Compress-Archive -Path {source_dir}/* -DestinationPath ./backup.zip -Force"},
                        "description": f"Compress source files into backup.zip",
                        "estimated_seconds": 12,
                        "dependencies": ["step-1"]
                    },
                    {
                        "id": "step-3",
                        "agent": "file",
                        "action": "organize",
                        "params": {"directory": source_dir},
                        "description": f"Perform a cleanup organization on {source_dir}",
                        "estimated_seconds": 5,
                        "dependencies": ["step-2"]
                    }
                ]
            }

        # 4. Template: Research & Report
        if "research" in normalized and "report" in normalized:
            topic = self._extract_topic(normalized, "research", "report")
            report_name = f"{self._slugify(topic or 'research_report')}_report.txt"
            return {
                "goal": command,
                "strategy": "research_report",
                "estimated_total_seconds": 25,
                "subtasks": [
                    {
                        "id": "step-1",
                        "agent": "web",
                        "action": "search",
                        "params": {"query": topic or command},
                        "description": f"Search the web for {topic or command}",
                        "estimated_seconds": 10,
                        "dependencies": []
                    },
                    {
                        "id": "step-2",
                        "agent": "web",
                        "action": "extract_text",
                        "params": {"extract_text": True},
                        "description": "Capture visible page text",
                        "estimated_seconds": 5,
                        "dependencies": ["step-1"]
                    },
                    {
                        "id": "step-3",
                        "agent": "file",
                        "action": "create_report",
                        "params": {
                            "path": str(Path.cwd() / report_name),
                            "topic": topic or command,
                        },
                        "description": "Create a report file from gathered notes",
                        "estimated_seconds": 10,
                        "dependencies": ["step-2"]
                    },
                ],
            }

        if (" and then " in normalized or " then " in normalized or " after that " in normalized) and "search" in normalized and "create file" in normalized:
            clauses = self._split_clauses(command)
            subtasks = []
            for index, clause in enumerate(clauses, start=1):
                subtask = self._build_subtask(clause, index)
                if subtask:
                    subtask["estimated_seconds"] = 5
                    subtask["dependencies"] = [f"step-{index-1}"] if index > 1 else []
                    subtasks.append(subtask)

            return {
                "goal": command,
                "strategy": "browser_then_file",
                "estimated_total_seconds": len(subtasks) * 5,
                "subtasks": subtasks,
            }

        # Generic Clause Splitting (with simple dependency chain)
        clauses = self._split_clauses(command)
        subtasks = []
        for index, clause in enumerate(clauses, start=1):
            subtask = self._build_subtask(clause, index)
            if subtask:
                # Add default details
                subtask["estimated_seconds"] = 5
                subtask["dependencies"] = [f"step-{index-1}"] if index > 1 else []
                subtasks.append(subtask)

        # Propagate URLs from earlier web navigation subtasks to subsequent form subtasks
        for i, st in enumerate(subtasks):
            if st.get("agent") == "web" and st.get("action") == "form":
                params = st.setdefault("params", {})
                if not params.get("url"):
                    # look back for url or target from previous subtasks
                    for prev in reversed(subtasks[:i]):
                        pparams = prev.get("params", {})
                        candidate = pparams.get("url") or pparams.get("target")
                        if candidate:
                            params["url"] = candidate
                            break
                    # fallback to searching the original command
                    if not params.get("url"):
                        um = re.search(r"https?://[^\s]+", command)
                        if um:
                            params["url"] = um.group(0)

        return {
            "goal": command,
            "strategy": "clause_split",
            "estimated_total_seconds": len(subtasks) * 5,
            "subtasks": subtasks,
        }

    def _split_clauses(self, command: str) -> List[str]:
        # Split on explicit sequence words or conjunctions followed by actionable verbs, or direct verb transitions
        pattern = (
            r"\b(?:and\s+then|then|after\s+that)\b|"
            r"\b(?:and|after\s+that)\s+(?=open|launch|start|goto|go\s+to|navigate|search|google|look\s+up|find|fill|create|make|list|show|run|compress|compare|backup|clean|organize)|"
            r"\b(?=goto|go\s+to|navigate\s+to|search\s+for|look\s+up|fill\s+form|create\s+file|create\s+folder)"
        )
        parts = re.split(pattern, command, flags=re.IGNORECASE)
        clauses = []
        for part in parts:
            part_clean = part.strip(" ,.")
            # Remove leading "and" or similar if they slipped in
            part_clean = re.sub(r"^(?:and|then|after that)\s+", "", part_clean, flags=re.IGNORECASE).strip(" ,.")
            if part_clean:
                clauses.append(part_clean)
        return clauses

    def _build_subtask(self, clause: str, index: int) -> Dict[str, Any]:
        normalized = clause.lower()

        # 1. Form Filling Check (check before general browser navigation/search)
        clean_for_check = re.sub(r"https?://[^\s]+", "", normalized)
        if any(word in clean_for_check for word in ["form", "fill"]):
            url_match = re.search(r"https?://[^\s]+", clause)
            url = url_match.group(0) if url_match else None
            # Extract fields — prefer text after 'with' to avoid capturing leading clause words
            fields = {}
            parts = re.split(r"\bwith\b", clause, flags=re.IGNORECASE, maxsplit=1)
            if len(parts) > 1:
                body = parts[1]
                pairs = re.findall(r"([A-Za-z][A-Za-z0-9 _-]{1,30})\s*(?:=|:)\s*([^,;]+)", body)
            else:
                pairs = re.findall(r"([A-Za-z][A-Za-z0-9 _-]{1,30})\s*(?:=|:)\s*([^,;]+)", clause)

            fields = {
                key.strip(): value.strip().strip(".")
                for key, value in pairs
                if key.strip() and value.strip() and key.strip().lower() not in ["http", "https"]
            }
            params = {"description": clause}
            if fields:
                params["fields"] = fields
            if url:
                params["url"] = url
            params["submit"] = "submit" in normalized
            params["focus_first_field"] = True
            return {
                "id": f"step-{index}",
                "agent": "web",
                "action": "form",
                "params": params,
                "description": clause,
            }

        search_files = re.match(r"^(?:search|find)\s+(?:files?\s+)?(?:for\s+)?(?P<query>.+?)\s+(?:in|inside)\s+(?P<path>.+)$", clause, flags=re.IGNORECASE)
        if search_files and not any(site in normalized for site in ["amazon", "flipkart", "google", "youtube"]):
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "search_files",
                "params": {
                    "query": search_files.group("query").strip().strip('"'),
                    "description": clause,
                },
                "description": clause,
            }

        # 2. Web / Browser check
        web_keywords = ["search", "google", "look up", "navigate", "website", "goto", "go to", "youtube", "http://", "https://", "url", "browser"]
        if any(word in normalized for word in web_keywords):
            is_search = any(word in normalized for word in ["search", "look up", "find", "google for", "youtube for"])
            # Clean prefixes
            clean_pattern = r"^(?:open|launch|start|go to|goto|navigate to|search for|search|look up|google for|google|find)\s+"
            target_clean = re.sub(clean_pattern, "", clause, flags=re.IGNORECASE).strip()
            
            # Check special sites
            from urllib.parse import quote_plus
            commerce_search = re.search(
                r"(?:search|find|look up)(?:\s+for)?\s+(?P<query>.+?)\s+(?:on|in)\s+(?P<site>amazon|flipkart)(?:\s+there)?$",
                normalized,
            )
            if commerce_search:
                site = commerce_search.group("site")
                query = commerce_search.group("query").strip()
                action = "navigate"
                target_url = (
                    f"https://www.amazon.in/s?k={quote_plus(query)}"
                    if site == "amazon"
                    else f"https://www.flipkart.com/search?q={quote_plus(query)}"
                )
                target_clean = query
            elif "google" in normalized and not is_search and target_clean.lower() in ["", "google"]:
                target_url = "https://www.google.com"
                action = "navigate"
            elif "youtube" in normalized and not is_search and target_clean.lower() in ["", "youtube"]:
                target_url = "https://www.youtube.com"
                action = "navigate"
            elif is_search:
                action = "search"
                target_url = target_clean
            else:
                action = "navigate"
                target_url = target_clean
                if not target_url.startswith(("http://", "https://")):
                    if "." in target_url:
                        target_url = "https://" + target_url
                    else:
                        common_sites = {
                            "amazon": "https://www.amazon.com",
                            "facebook": "https://www.facebook.com",
                            "github": "https://www.github.com",
                            "wikipedia": "https://www.wikipedia.org"
                        }
                        if target_url in common_sites:
                            target_url = common_sites[target_url]
                        else:
                            target_url = "https://www.google.com/search?q=" + quote_plus(target_url)

            return {
                "id": f"step-{index}",
                "agent": "web",
                "action": action,
                "params": {"query": target_clean, "target": target_url, "url": target_url},
                "description": clause,
            }

        if any(word in normalized for word in ["open", "launch", "start"]):
            app = re.sub(r"^(open|launch|start)\s+", "", normalized).strip()
            return {
                "id": f"step-{index}",
                "agent": "system",
                "action": "open",
                "params": {"app": app},
                "description": clause,
            }

        if normalized.startswith(("close ", "quit ")):
            app = re.sub(r"^(close|quit)\s+", "", normalized).strip()
            return {
                "id": f"step-{index}",
                "agent": "system",
                "action": "close",
                "params": {"app": app},
                "description": clause,
            }

        if normalized.startswith("create file"):
            match = re.search(r"create file(?: named)?\s+(?P<name>.+)$", normalized)
            filename = match.group("name").strip().strip('"') if match else "new_file.txt"
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "create_file",
                "params": {"path": str(Path.cwd() / filename), "description": clause},
                "description": clause,
            }

        if normalized.startswith("create folder") or normalized.startswith("make folder"):
            match = re.search(r"(?:create|make)\s+folder(?: named)?\s+(?P<name>.+)$", normalized)
            foldername = match.group("name").strip().strip('"') if match else "new_folder"
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "create_folder",
                "params": {"path": str(Path.cwd() / foldername), "description": clause},
                "description": clause,
            }

        if normalized.startswith(("backup ", "back up ")):
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "backup",
                "params": {"description": clause},
                "description": clause,
            }

        if "duplicates" in normalized:
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "duplicates",
                "params": {"description": clause},
                "description": clause,
            }

        if "disk usage" in normalized or "space usage" in normalized:
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": "disk_usage",
                "params": {"description": clause},
                "description": clause,
            }

        if any(word in normalized for word in ["organize", "file", "folder", "desktop", "documents", "downloads"]):
            action = "organize" if "organize" in normalized else "list"
            return {
                "id": f"step-{index}",
                "agent": "file",
                "action": action,
                "params": {"description": clause},
                "description": clause,
            }

        if any(word in normalized for word in ["system info", "cpu", "memory", "process", "status"]):
            action = "process" if "process" in normalized else "status"
            return {
                "id": f"step-{index}",
                "agent": "system",
                "action": action,
                "params": {"description": clause},
                "description": clause,
            }

        return {
            "id": f"step-{index}",
            "agent": "general",
            "action": "general",
            "params": {"description": clause},
            "description": clause,
        }

    def _extract_topic(self, normalized: str, start_keyword: str, end_keyword: str) -> str:
        pattern = rf"{start_keyword}\s+(?P<topic>.+?)\s+(?:and\s+create|create)\s+.*{end_keyword}"
        match = re.search(pattern, normalized)
        if match:
            return match.group("topic").strip()
        return normalized

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
