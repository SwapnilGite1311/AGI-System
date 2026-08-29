"""
Business Agent - Handles business-level automation and workflow management.
This is Phase 6: Business-level task automation, scheduling, and project management.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path
import subprocess
import re

from loguru import logger

from core.atomic_io import write_json_atomic
from core.config import load_config


class BusinessAgent:
    """
    Handles business-oriented tasks:
    - Task scheduling and reminders
    - Daily planning assistance
    - Meeting management
    - Priority-based task queuing
    - Project tracking
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize the business agent."""

        # Resolve data files against the project root so saved state does not
        # fork depending on the directory ASC was launched from.
        self.project_root = Path(config_path).resolve().parent.parent

        self.config_path = Path(config_path).resolve()
        self.config = load_config(config_path)
        # Merge secrets from gitignored credentials files so settings.json
        # stays shareable while email/calendar still work.
        # load_credentials transparently decrypts OS-protected values and
        # upgrades any remaining plaintext in place on first read, so an
        # existing install migrates without user action.
        for section, filename in self.CREDENTIAL_FILES.items():
            try:
                from core.secrets import load_credentials

                creds = load_credentials(self.project_root / "data" / filename)
                if creds:
                    self.config.setdefault(section, {}).update(creds)
            except Exception as exc:
                logger.warning("{} credentials merge skipped: {}", section, str(exc))

        self.data_path = self._data_file("business_tasks.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

        self.tasks = self._load_tasks()
        self.projects = self._load_projects()
        self.schedules = self._load_schedules()

        logger.info("Business Agent initialized")

    def _data_file(self, filename: str) -> Path:
        """Resolve a file inside <project_root>/data/ regardless of cwd."""
        return self.project_root / "data" / filename

    # Config sections whose secrets live in a gitignored credentials file
    # instead of settings.json. settings.json is tracked by git, so a secret
    # written there is a secret committed to the repository (audit H-1).
    CREDENTIAL_FILES = {
        "email": "email_credentials.json",
        "google_calendar": "google_credentials.json",
    }

    def _persist_config_section(
        self,
        section: str,
        values: Dict[str, Any],
        secret_keys: tuple = (),
    ) -> None:
        """Save a config section, keeping secrets out of settings.json.

        Secrets go to <project_root>/data/<section>_credentials.json, encrypted
        at rest by the OS keystore; everything else goes to settings.json,
        written atomically. Previously both halves were written straight into
        settings.json in clear text - a tracked file - which put a live Gmail
        app password and a Google API key into version control (audit H-1),
        and did it with a truncate-then-write that could destroy the config
        outright if interrupted (audit H-3).
        """
        secrets_part = {k: v for k, v in values.items() if k in secret_keys and v}
        public_part = {k: v for k, v in values.items() if k not in secret_keys}

        # In-memory config keeps everything so the running session works.
        self.config[section] = dict(values)

        if secrets_part:
            try:
                from core.secrets import save_credentials

                filename = self.CREDENTIAL_FILES.get(section, f"{section}_credentials.json")
                save_credentials(self._data_file(filename), secrets_part)
            except Exception as exc:
                logger.error("Could not store {} secrets securely: {}", section, str(exc))
                raise

        try:
            settings = load_config(str(self.config_path))
            settings[section] = public_part
            write_json_atomic(self.config_path, settings)
        except Exception as exc:
            logger.warning("Could not save {} configuration: {}", section, str(exc))

    def _load_tasks(self) -> List[Dict[str, Any]]:
        """Load business tasks from storage."""
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("tasks", [])
            except Exception as e:
                logger.warning("Failed to load tasks: {}", str(e))
        return []

    def _load_projects(self) -> List[Dict[str, Any]]:
        """Load projects from storage."""
        projects_path = self._data_file("projects.json")
        if projects_path.exists():
            try:
                with open(projects_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load projects: {}", str(e))
        return []

    def _load_schedules(self) -> List[Dict[str, Any]]:
        """Load schedules from storage."""
        schedules_path = self._data_file("schedules.json")
        if schedules_path.exists():
            try:
                with open(schedules_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load schedules: {}", str(e))
        return []

    def _save_tasks(self):
        """Save tasks to storage."""
        try:
            data = {
                "tasks": self.tasks,
                "updated_at": datetime.now().isoformat()
            }
            write_json_atomic(self.data_path, data)
        except Exception as e:
            logger.error("Failed to save tasks: {}", str(e))

    def _save_projects(self):
        """Save projects to storage."""
        try:
            projects_path = self._data_file("projects.json")
            write_json_atomic(projects_path, self.projects)
        except Exception as e:
            logger.error("Failed to save projects: {}", str(e))

    def _save_schedules(self):
        """Save schedules to storage."""
        try:
            schedules_path = self._data_file("schedules.json")
            write_json_atomic(schedules_path, self.schedules)
        except Exception as e:
            logger.error("Failed to save schedules: {}", str(e))

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: Optional[str] = None,
        project_id: Optional[str] = None,
        category: str = "general"
    ) -> Dict[str, Any]:
        """Create a new business task."""
        
        task = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "priority": priority,  # high, medium, low
            "status": "pending",  # pending, in_progress, completed, cancelled
            "created_at": datetime.now().isoformat(),
            "due_date": due_date,
            "project_id": project_id,
            "category": category,
            "completed_at": None
        }
        
        self.tasks.append(task)
        self._save_tasks()
        
        return {
            "success": True,
            "task": task,
            "message": f"Task '{title}' created successfully"
        }

    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List tasks with optional filtering."""
        
        filtered_tasks = self.tasks
        
        if status:
            filtered_tasks = [t for t in filtered_tasks if t["status"] == status]
        if priority:
            filtered_tasks = [t for t in filtered_tasks if t["priority"] == priority]
        if project_id:
            filtered_tasks = [t for t in filtered_tasks if t.get("project_id") == project_id]
        
        # Sort by priority and due date
        priority_order = {"high": 0, "medium": 1, "low": 2}
        filtered_tasks.sort(key=lambda t: (
            priority_order.get(t["priority"], 3),
            t.get("due_date") or "9999-12-31"
        ))
        
        return {
            "success": True,
            "tasks": filtered_tasks,
            "total": len(filtered_tasks)
        }

    def update_task_status(
        self,
        task_id: str,
        status: str = "completed"
    ) -> Dict[str, Any]:
        """Update task status."""

        task_id = str(task_id or "").strip()
        if not task_id:
            return {"success": False, "error": "Task ID is required to update a task."}

        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = status
                if status == "completed":
                    task["completed_at"] = datetime.now().isoformat()
                self._save_tasks()
                return {
                    "success": True,
                    "task": task,
                    "message": f"Task status updated to {status}"
                }
        
        return {
            "success": False,
            "error": f"Task with ID {task_id} not found"
        }

    def create_project(
        self,
        name: str,
        description: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new project."""
        
        project = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "start_date": start_date,
            "end_date": end_date,
            "status": "active",  # active, completed, cancelled
            "created_at": datetime.now().isoformat(),
            "tasks": []
        }
        
        self.projects.append(project)
        self._save_projects()
        
        return {
            "success": True,
            "project": project,
            "message": f"Project '{name}' created successfully"
        }

    def schedule_reminder(
        self,
        title: str,
        reminder_time: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Schedule a reminder."""
        
        reminder = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "reminder_time": reminder_time,
            "status": "pending",  # pending, completed, cancelled
            "created_at": datetime.now().isoformat()
        }
        
        self.schedules.append(reminder)
        self._save_schedules()
        
        return {
            "success": True,
            "reminder": reminder,
            "message": f"Reminder '{title}' scheduled for {reminder_time}"
        }

    def get_daily_plan(self) -> Dict[str, Any]:
        """Generate a daily plan based on tasks and schedules."""
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Get today's tasks
        today_tasks = [
            task for task in self.tasks 
            if task["status"] in ["pending", "in_progress"]
        ]
        
        # Get today's reminders
        today_reminders = [
            reminder for reminder in self.schedules
            if isinstance(reminder.get("reminder_time"), str)
            and reminder["reminder_time"].startswith(today)
            and reminder.get("status") == "pending"
        ]
        
        # Get urgent tasks (high priority or due today)
        urgent_tasks = [
            task for task in today_tasks
            if task["priority"] == "high" or task.get("due_date") == today
        ]
        
        # Generate plan
        plan = {
            "date": today,
            "urgent_tasks": urgent_tasks,
            "all_tasks": today_tasks,
            "reminders": today_reminders,
            "task_count": len(today_tasks),
            "reminder_count": len(today_reminders),
            "suggestions": self._generate_daily_suggestions(today_tasks, urgent_tasks)
        }
        
        return {
            "success": True,
            "daily_plan": plan
        }

    def _generate_daily_suggestions(
        self,
        all_tasks: List[Dict[str, Any]],
        urgent_tasks: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate suggestions for daily planning."""
        
        suggestions = []
        
        if urgent_tasks:
            suggestions.append(f"Focus on {len(urgent_tasks)} urgent task(s) first")
        
        if len(all_tasks) > 5:
            suggestions.append("Consider prioritizing your tasks - you have a busy day ahead")
        
        if not urgent_tasks and all_tasks:
            suggestions.append("No urgent tasks today - good opportunity to work on medium-priority items")
        
        if not all_tasks:
            suggestions.append("Your task list is clear - consider planning for upcoming days")
        
        return suggestions

    def generate_meeting_agenda(
        self,
        meeting_title: str,
        duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """Generate a basic meeting agenda."""
        
        agenda = {
            "title": meeting_title,
            "duration_minutes": duration_minutes,
            "created_at": datetime.now().isoformat(),
            "agenda_items": [
                {
                    "title": "Opening and welcome",
                    "duration_minutes": 5,
                    "description": "Brief introduction and meeting objectives"
                },
                {
                    "title": "Main discussion",
                    "duration_minutes": duration_minutes - 15,
                    "description": "Primary meeting content"
                },
                {
                    "title": "Action items and next steps",
                    "duration_minutes": 5,
                    "description": "Review decisions and assign tasks"
                },
                {
                    "title": "Closing",
                    "duration_minutes": 5,
                    "description": "Summary and follow-up actions"
                }
            ]
        }
        
        return {
            "success": True,
            "agenda": agenda,
            "message": f"Meeting agenda generated for '{meeting_title}'"
        }

    def add_calendar_event(
        self,
        title: str = None,
        start_time: str = None,
        end_time: str = None,
        description: str = "",
        location: str = "",
        calendar_type: str = "windows"
    ) -> Dict[str, Any]:
        """Add an event to various calendar platforms."""

        title = str(title or "").strip()
        if not title:
            return {"success": False, "error": "Event title is required. Say what the event is about."}
        if not start_time:
            return {"success": False, "error": "Start time is required, e.g. 'tomorrow 11am'."}
        
        if calendar_type == "windows":
            return self._add_windows_calendar_event(title, start_time, end_time, description, location)
        elif calendar_type == "google":
            return self._add_google_calendar_event(title, start_time, end_time, description, location)
        elif calendar_type == "apple":
            return self._add_apple_calendar_event(title, start_time, end_time, description, location)
        else:
            return {
                "success": False,
                "error": f"Unsupported calendar type: {calendar_type}",
                "message": "Supported calendar types: windows, google, apple"
            }

    def _add_windows_calendar_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Add an event to Windows Calendar via Outlook."""
        
        try:
            # Format times for Windows Calendar
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            
            # Create Outlook appointment via PowerShell
            ps_script = f'''
            $Outlook = New-Object -ComObject Outlook.Application
            $Appointment = $Outlook.CreateItem(1)
            $Appointment.Subject = "{title}"
            $Appointment.Start = "{start_dt}"
            $Appointment.End = "{end_dt}"
            $Appointment.Body = "{description}"
            $Appointment.Location = "{location}"
            $Appointment.Save()
            '''
            
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Calendar event '{title}' added to Windows Calendar",
                    "calendar_type": "windows",
                    "start_time": start_time,
                    "end_time": end_time
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to add calendar event: {result.stderr}",
                    "message": "Event saved locally but not added to Windows Calendar"
                }
                
        except Exception as e:
            logger.warning("Windows Calendar integration failed: {}", str(e))
            return {
                "success": False,
                "error": f"Windows Calendar integration unavailable: {str(e)}",
                "message": "Event saved locally but not added to calendar"
            }

    def _add_google_calendar_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Add an event to Google Calendar via API."""
        
        try:
            # Check if Google Calendar is configured
            google_config = self.config.get("google_calendar", {})
            if not google_config.get("configured", False):
                return {
                    "success": False,
                    "error": "Google Calendar not configured",
                    "message": "Google Calendar integration requires API credentials. "
                              "Please configure Google Calendar using configure_google_calendar.",
                    "setup_instructions": {
                        "method": "configure_google_calendar",
                        "required_fields": ["api_key", "calendar_id"],
                        "setup_guide": "Enable Google Calendar API, create credentials, and provide API key"
                    }
                }
            
            # Format times for Google Calendar API
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            
            # Create event data
            event_data = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {
                    "dateTime": start_dt.isoformat(),
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": end_dt.isoformat(),
                    "timeZone": "UTC"
                }
            }
            
            # Call Google Calendar API (framework - requires requests library)
            try:
                import requests
                
                api_key = google_config.get("api_key")
                calendar_id = google_config.get("calendar_id", "primary")
                
                url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
                headers = {"Authorization": f"Bearer {api_key}"}
                
                response = requests.post(url, json=event_data, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": f"Calendar event '{title}' added to Google Calendar",
                        "calendar_type": "google",
                        "event_id": response.json().get("id"),
                        "start_time": start_time,
                        "end_time": end_time
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Google Calendar API error: {response.status_code}",
                        "message": "Failed to add event to Google Calendar"
                    }
                    
            except ImportError:
                return {
                    "success": False,
                    "error": "Requests library not available",
                    "message": "Google Calendar integration requires the requests library. "
                              "Install with: pip install requests"
                }
                
        except Exception as e:
            logger.warning("Google Calendar integration failed: {}", str(e))
            return {
                "success": False,
                "error": f"Google Calendar integration failed: {str(e)}",
                "message": "Event saved locally but not added to Google Calendar"
            }

    def _add_apple_calendar_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Add an event to Apple Calendar via AppleScript."""
        
        try:
            # Format times for Apple Calendar
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            
            # Create AppleScript command
            applescript = f'''
            tell application "Calendar"
                set newEvent to make new event at end of events of calendar "Home"
                set summary of newEvent to "{title}"
                set start date of newEvent to date "{start_dt.strftime('%B %d, %Y %I:%M:%S %p')}"
                set end date of newEvent to date "{end_dt.strftime('%B %d, %Y %I:%M:%S %p')}"
                set description of newEvent to "{description}"
                set location of newEvent to "{location}"
            end tell
            '''
            
            result = subprocess.run(
                ["osascript", "-e", applescript],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Calendar event '{title}' added to Apple Calendar",
                    "calendar_type": "apple",
                    "start_time": start_time,
                    "end_time": end_time
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to add calendar event: {result.stderr}",
                    "message": "Event saved locally but not added to Apple Calendar"
                }
                
        except Exception as e:
            logger.warning("Apple Calendar integration failed: {}", str(e))
            return {
                "success": False,
                "error": f"Apple Calendar integration unavailable: {str(e)}",
                "message": "Event saved locally but not added to calendar (Apple Calendar requires macOS)"
            }

    def configure_google_calendar(
        self,
        api_key: str,
        calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Configure Google Calendar integration."""
        
        try:
            # Validate configuration
            if not all([api_key, calendar_id]):
                return {
                    "success": False,
                    "error": "Incomplete Google Calendar configuration",
                    "message": "Both api_key and calendar_id are required"
                }
            
            # Test the configuration
            try:
                import requests
                url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
                headers = {"Authorization": f"Bearer {api_key}"}
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Invalid API key",
                        "message": "The provided API key is invalid or expired"
                    }
            except ImportError:
                return {
                    "success": False,
                    "error": "Requests library not available",
                    "message": "Google Calendar integration requires the requests library"
                }
            
            google_config = {
                "configured": True,
                "api_key": api_key,
                "calendar_id": calendar_id,
                "configured_at": datetime.now().isoformat()
            }

            # api_key is a secret: it goes to the gitignored credentials file,
            # never into the tracked settings.json.
            self._persist_config_section("google_calendar", google_config, secret_keys=("api_key",))
            
            return {
                "success": True,
                "message": "Google Calendar configured successfully",
                "calendar_id": calendar_id,
                "test_result": "Configuration valid"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Google Calendar configuration failed: {str(e)}",
                "message": "Failed to configure Google Calendar. Please check your inputs."
            }

    def get_upcoming_events(self, days_ahead: int = 7) -> Dict[str, Any]:
        """Get upcoming events from calendar."""
        
        try:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=days_ahead)
            
            ps_script = f'''
            $Outlook = New-Object -ComObject Outlook.Application
            $Calendar = $Outlook.Session.GetDefaultFolder(9)
            $Items = $Calendar.Items
            $Items.Sort("[Start]")
            $Items.IncludeRecurrences = $true
            $Filter = "[Start] >= '{start_date.strftime("%m/%d/%Y %H:%M")}' AND [End] <= '{end_date.strftime("%m/%d/%Y %H:%M")}'"
            $FilteredItems = $Items.Restrict($Filter)
            
            $events = @()
            foreach ($Item in $FilteredItems) {{
                $events += @{{
                    Subject = $Item.Subject
                    Start = $Item.Start.ToString()
                    End = $Item.End.ToString()
                    Location = $Item.Location
                    Body = $Item.Body
                }}
            }}
            $events | ConvertTo-Json
            '''
            
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout:
                events = json.loads(result.stdout)
                return {
                    "success": True,
                    "events": events,
                    "total": len(events),
                    "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to retrieve calendar events",
                    "message": "Using local reminders instead"
                }
                
        except Exception as e:
            logger.warning("Calendar retrieval failed: {}", str(e))
            # Fall back to local reminders
            upcoming_reminders = [
                reminder for reminder in self.schedules
                if reminder["status"] == "pending" and datetime.fromisoformat(reminder["reminder_time"]) > datetime.now()
            ]
            return {
                "success": True,
                "events": upcoming_reminders,
                "total": len(upcoming_reminders),
                "source": "local_reminders",
                "message": "Using local reminders (calendar unavailable)"
            }

    def add_task_to_project(self, task_id: str, project_id: str) -> Dict[str, Any]:
        """Add an existing task to a project."""
        
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        project = next((p for p in self.projects if p["id"] == project_id), None)
        
        if not task:
            return {"success": False, "error": f"Task with ID {task_id} not found"}
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        task["project_id"] = project_id
        project["tasks"].append(task_id)
        
        self._save_tasks()
        self._save_projects()
        
        return {
            "success": True,
            "message": f"Task '{task['title']}' added to project '{project['name']}'",
            "task": task,
            "project": project
        }

    def get_project_status(self, project_id: str) -> Dict[str, Any]:
        """Get detailed status of a project."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        project_tasks = [t for t in self.tasks if t.get("project_id") == project_id]
        
        completed_tasks = [t for t in project_tasks if t["status"] == "completed"]
        in_progress_tasks = [t for t in project_tasks if t["status"] == "in_progress"]
        pending_tasks = [t for t in project_tasks if t["status"] == "pending"]
        
        completion_rate = len(completed_tasks) / len(project_tasks) if project_tasks else 0.0
        
        return {
            "success": True,
            "project": project,
            "total_tasks": len(project_tasks),
            "completed_tasks": len(completed_tasks),
            "in_progress_tasks": len(in_progress_tasks),
            "pending_tasks": len(pending_tasks),
            "completion_rate": round(completion_rate, 2),
            "status": self._calculate_project_status(completion_rate, project)
        }

    def _calculate_project_status(self, completion_rate: float, project: Dict[str, Any]) -> str:
        """Calculate overall project status based on completion rate."""
        
        if completion_rate == 1.0:
            return "completed"
        elif completion_rate >= 0.75:
            return "near_completion"
        elif completion_rate >= 0.25:
            return "in_progress"
        elif completion_rate > 0.0:
            return "started"
        else:
            return "not_started"

    def list_projects(self, status: Optional[str] = None) -> Dict[str, Any]:
        """List projects with optional filtering."""
        
        filtered_projects = self.projects
        
        if status:
            filtered_projects = [p for p in filtered_projects if p["status"] == status]
        
        # Calculate status for each project
        for project in filtered_projects:
            project_tasks = [t for t in self.tasks if t.get("project_id") == project["id"]]
            completed_tasks = [t for t in project_tasks if t["status"] == "completed"]
            completion_rate = len(completed_tasks) / len(project_tasks) if project_tasks else 0.0
            project["completion_rate"] = round(completion_rate, 2)
            project["task_count"] = len(project_tasks)
        
        return {
            "success": True,
            "projects": filtered_projects,
            "total": len(filtered_projects)
        }

    def create_milestone(
        self,
        project_id: str,
        title: str,
        target_date: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Create a project milestone."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        milestone = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "title": title,
            "description": description,
            "target_date": target_date,
            "status": "pending",  # pending, completed, overdue
            "created_at": datetime.now().isoformat()
        }
        
        if "milestones" not in project:
            project["milestones"] = []
        
        project["milestones"].append(milestone)
        self._save_projects()
        
        return {
            "success": True,
            "milestone": milestone,
            "message": f"Milestone '{title}' created for project '{project['name']}'"
        }

    def get_project_timeline(self, project_id: str) -> Dict[str, Any]:
        """Generate a project timeline with milestones and tasks."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        project_tasks = [t for t in self.tasks if t.get("project_id") == project_id]
        milestones = project.get("milestones", [])
        
        # Sort tasks by due date and milestones by target date
        sorted_tasks = sorted(project_tasks, key=lambda t: t.get("due_date") or "9999-12-31")
        sorted_milestones = sorted(milestones, key=lambda m: m.get("target_date") or "9999-12-31")
        
        timeline = {
            "project": project,
            "tasks": sorted_tasks,
            "milestones": sorted_milestones,
            "total_tasks": len(project_tasks),
            "total_milestones": len(milestones),
            "start_date": project.get("start_date"),
            "end_date": project.get("end_date")
        }
        
        return {
            "success": True,
            "timeline": timeline
        }

    def send_email_notification(
        self,
        to_email: str,
        subject: str,
        body: str,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Send an email notification with user-provided credentials."""

        # Defensive coercion: LLM planners often omit fields entirely, and
        # MIMEText(None) crashes with 'NoneType' has no attribute 'encode'.
        to_email = str(to_email or "").strip()
        subject = str(subject or "").strip() or "(no subject)"
        body = str(body or "").strip() or "(empty body)"

        if "@" not in to_email:
            return {
                "success": False,
                "error": f"Invalid recipient address: '{to_email or '(missing)'}'",
                "message": "Say the full email address, e.g. 'send an email to name@gmail.com about ...'",
            }

        email_config = self.config.get("email", {})
        
        # Check if email is configured
        if not email_config.get("configured", False):
            return {
                "success": False,
                "error": "Email not configured",
                "message": "Email sending requires configuration. Please set up your email credentials "
                          "in the secure configuration file or use the configure_email method.",
                "setup_instructions": {
                    "method": "configure_email",
                    "required_fields": ["smtp_server", "smtp_port", "email_address", "password"],
                    "example": "configure_email(smtp_server='smtp.gmail.com', smtp_port=587, "
                              "email_address='your@gmail.com', password='your_app_password')"
                }
            }
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Get email configuration
            smtp_server = email_config.get("smtp_server")
            smtp_port = email_config.get("smtp_port", 587)
            email_address = email_config.get("email_address")
            password = email_config.get("password")
            
            if not all([smtp_server, smtp_port, email_address, password]):
                return {
                    "success": False,
                    "error": "Incomplete email configuration",
                    "message": "Please provide all required email configuration fields.",
                    "missing_fields": [
                        field for field in ["smtp_server", "smtp_port", "email_address", "password"]
                        if not email_config.get(field)
                    ]
                }
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = email_address
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add priority header
            priority_mapping = {
                "high": "1",
                "normal": "3",
                "low": "5"
            }
            msg['X-Priority'] = priority_mapping.get(priority, "3")
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_address, password)
            server.send_message(msg)
            server.quit()
            
            # Log the communication
            self.create_communication_log(
                communication_type="email",
                recipient=to_email,
                subject=subject,
                status="sent"
            )
            
            return {
                "success": True,
                "message": f"Email sent successfully to {to_email}",
                "to": to_email,
                "subject": subject,
                "sent_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Email sending failed: {}", str(e))
            return {
                "success": False,
                "error": f"Email sending failed: {str(e)}",
                "message": "Failed to send email. Please check your email configuration and credentials."
            }

    def configure_email(
        self,
        smtp_server: str,
        smtp_port: int,
        email_address: str,
        password: str,
        use_tls: bool = True
    ) -> Dict[str, Any]:
        """Configure email settings with user-provided credentials."""
        
        try:
            # Validate configuration
            if not all([smtp_server, smtp_port, email_address, password]):
                return {
                    "success": False,
                    "error": "Incomplete email configuration",
                    "message": "All fields are required: smtp_server, smtp_port, email_address, password"
                }
            
            # Test the configuration
            import smtplib
            try:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                if use_tls:
                    server.starttls()
                server.login(email_address, password)
                server.quit()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Email configuration test failed: {str(e)}",
                    "message": "Could not connect to SMTP server with provided credentials. "
                              "Please check your settings and try again."
                }
            
            email_config = {
                "configured": True,
                "smtp_server": smtp_server,
                "smtp_port": smtp_port,
                "email_address": email_address,
                "password": password,
                "use_tls": use_tls,
                "configured_at": datetime.now().isoformat()
            }

            # The password is split out into the gitignored credentials file
            # and encrypted by the OS keystore; only the non-secret fields
            # reach settings.json.
            self._persist_config_section("email", email_config, secret_keys=("password",))
            
            return {
                "success": True,
                "message": "Email configured successfully",
                "email_address": email_address,
                "smtp_server": smtp_server,
                "test_result": "Connection successful"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Email configuration failed: {str(e)}",
                "message": "Failed to configure email. Please check your inputs and try again."
            }

    def check_email_configuration(self) -> Dict[str, Any]:
        """Check if email is configured (without revealing credentials)."""
        
        email_config = self.config.get("email", {})
        is_configured = bool(email_config.get("configured", False))
        
        return {
            "success": True,
            "email_configured": is_configured,
            "message": "Email is configured" if is_configured else "Email is not configured. "
                      "To enable email notifications, please configure your email settings in the secure configuration.",
            "available_features": [
                "Task completion notifications",
                "Project milestone alerts",
                "Daily planning summaries",
                "Meeting reminders"
            ] if is_configured else []
        }

    def generate_email_template(
        self,
        template_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate an email template for various business scenarios."""
        
        templates = {
            "task_completion": {
                "subject": "Task Completed: {task_title}",
                "body": """Dear User,

I'm pleased to inform you that the following task has been completed:

Task: {task_title}
Description: {description}
Completed at: {completion_time}

If you have any questions or need further assistance, please let me know.

Best regards,
ASC (Autonomous System Controller)"""
            },
            "project_milestone": {
                "subject": "Project Milestone: {milestone_title}",
                "body": """Dear User,

A milestone has been reached in your project:

Project: {project_name}
Milestone: {milestone_title}
Target Date: {target_date}
Status: {status}

This marks significant progress in your project timeline.

Best regards,
ASC"""
            },
            "daily_summary": {
                "subject": "Daily Summary - {date}",
                "body": """Dear User,

Here's your daily summary for {date}:

Tasks Completed: {completed_count}
Tasks Remaining: {remaining_count}
Upcoming Events: {event_count}

Key Highlights:
{highlights}

Let me know if you need any adjustments to your schedule.

Best regards,
ASC"""
            }
        }
        
        template = templates.get(template_type)
        if not template:
            return {
                "success": False,
                "error": f"Template type '{template_type}' not found"
            }
        
        try:
            subject = template["subject"].format(**context)
            body = template["body"].format(**context)
            
            return {
                "success": True,
                "template_type": template_type,
                "subject": subject,
                "body": body,
                "message": f"Email template generated for {template_type}"
            }
        except KeyError as e:
            return {
                "success": False,
                "error": f"Missing context variable: {str(e)}",
                "required_context": list(context.keys())
            }

    def create_communication_log(
        self,
        communication_type: str,
        recipient: str,
        subject: str,
        status: str = "draft"
    ) -> Dict[str, Any]:
        """Create a log entry for communication (for tracking without sending)."""
        
        log_entry = {
            "id": str(uuid.uuid4()),
            "type": communication_type,  # email, message, notification
            "recipient": recipient,
            "subject": subject,
            "status": status,  # draft, sent, failed
            "created_at": datetime.now().isoformat()
        }
        
        # Store in a separate communication log file
        comm_log_path = self._data_file("communication_log.json")
        comm_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            if comm_log_path.exists():
                with open(comm_log_path, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            else:
                logs = []
            
            logs.append(log_entry)
            
            write_json_atomic(comm_log_path, logs)
            
            return {
                "success": True,
                "log_entry": log_entry,
                "message": f"Communication log entry created for {communication_type}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create communication log: {str(e)}"
            }

    def call_external_api(
        self,
        service_name: str,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Framework for calling external APIs with security and error handling."""
        
        # Security: Never call external APIs without explicit user authorization
        # This provides a framework but requires user configuration
        
        api_config = self.config.get("external_apis", {})
        service_config = api_config.get(service_name, {})
        
        if not service_config.get("enabled", False):
            return {
                "success": False,
                "error": f"External API '{service_name}' is not enabled",
                "message": "To enable external API integration, please configure the service in your settings "
                          "and explicitly authorize API access for security reasons."
            }
        
        # This is a framework - actual API calls require user-provided credentials
        return {
            "success": False,
            "error": "API credentials required",
            "message": f"External API framework for '{service_name}' is available, but requires "
                      "explicit user-provided credentials for security. Please configure your API settings "
                      "in the secure configuration file.",
            "security_note": "ASC never stores or auto-fills API credentials for security reasons.",
            "available_endpoints": service_config.get("available_endpoints", [])
        }

    def get_available_services(self) -> Dict[str, Any]:
        """Get list of available external services and their capabilities."""
        
        api_config = self.config.get("external_apis", {})
        
        services = []
        for service_name, config in api_config.items():
            services.append({
                "name": service_name,
                "enabled": config.get("enabled", False),
                "description": config.get("description", ""),
                "capabilities": config.get("capabilities", []),
                "requires_auth": config.get("requires_auth", True)
            })
        
        return {
            "success": True,
            "services": services,
            "total": len(services),
            "message": f"Found {len(services)} external service configurations"
        }

    def configure_service(
        self,
        service_name: str,
        configuration: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Configure an external service (framework only - requires user approval)."""
        
        # Security: This is a framework that requires explicit user configuration
        # It does not automatically apply configurations
        
        return {
            "success": False,
            "error": "Manual configuration required",
            "message": f"External service configuration for '{service_name}' requires manual setup "
                      "in the secure configuration file. For security reasons, ASC does not automatically "
                      "configure external services.",
            "security_note": "Please configure external services manually in your settings file "
                          "to ensure you understand and approve all integrations.",
            "configuration_guide": {
                "service": service_name,
                "required_fields": configuration.get("required_fields", []),
                "optional_fields": configuration.get("optional_fields", []),
                "security_considerations": "Always use API keys with limited permissions and regularly rotate credentials"
            }
        }

    def coordinate_agents(
        self,
        task: str,
        required_agents: List[str],
        coordination_type: str = "sequential"
    ) -> Dict[str, Any]:
        """Coordinate multiple agents for complex tasks."""
        
        # Validate that required agents are available
        available_agents = ["file", "system", "web", "vision", "learning", "business", "conversation"]
        missing_agents = [agent for agent in required_agents if agent not in available_agents]
        
        if missing_agents:
            return {
                "success": False,
                "error": f"Required agents not available: {missing_agents}",
                "available_agents": available_agents
            }
        
        # Create coordination plan
        coordination_plan = {
            "task": task,
            "required_agents": required_agents,
            "coordination_type": coordination_type,  # sequential, parallel, hierarchical
            "created_at": datetime.now().isoformat(),
            "steps": self._generate_coordination_steps(task, required_agents, coordination_type)
        }
        
        return {
            "success": True,
            "coordination_plan": coordination_plan,
            "message": f"Multi-agent coordination plan created for task involving {len(required_agents)} agents"
        }

    def _generate_coordination_steps(
        self,
        task: str,
        required_agents: List[str],
        coordination_type: str
    ) -> List[Dict[str, Any]]:
        """Generate step-by-step coordination plan for agents."""
        
        steps = []
        
        if coordination_type == "sequential":
            # Execute agents one after another
            for i, agent in enumerate(required_agents):
                steps.append({
                    "step_number": i + 1,
                    "agent": agent,
                    "action": f"Execute {agent} operations on task",
                    "depends_on": required_agents[:i] if i > 0 else [],
                    "status": "pending"
                })
        
        elif coordination_type == "parallel":
            # Execute agents simultaneously
            for i, agent in enumerate(required_agents):
                steps.append({
                    "step_number": i + 1,
                    "agent": agent,
                    "action": f"Execute {agent} operations on task",
                    "depends_on": [],
                    "status": "pending",
                    "parallel": True
                })
        
        elif coordination_type == "hierarchical":
            # Business agent coordinates, others execute
            steps.append({
                "step_number": 1,
                "agent": "business",
                "action": "Plan and coordinate task execution",
                "depends_on": [],
                "status": "pending",
                "coordinator": True
            })
            
            for i, agent in enumerate(required_agents):
                if agent != "business":
                    steps.append({
                        "step_number": i + 2,
                        "agent": agent,
                        "action": f"Execute {agent} operations per business plan",
                        "depends_on": ["business"],
                        "status": "pending"
                    })
        
        return steps

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents for coordination purposes."""
        
        # This would integrate with the main controller to get real agent status
        # For now, provide a framework
        
        agent_status = {
            "file": {"status": "available", "load": "low"},
            "system": {"status": "available", "load": "low"},
            "web": {"status": "available", "load": "low"},
            "vision": {"status": "available", "load": "low"},
            "learning": {"status": "available", "load": "medium"},
            "business": {"status": "available", "load": "low"},
            "conversation": {"status": "available", "load": "low"}
        }
        
        return {
            "success": True,
            "agent_status": agent_status,
            "total_agents": len(agent_status),
            "available_agents": len([a for a in agent_status.values() if a["status"] == "available"])
        }

    def optimize_agent_workflow(
        self,
        task: str,
        agent_capabilities: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """Optimize agent workflow based on task requirements and agent capabilities."""
        
        # Analyze task requirements
        task_requirements = self._analyze_task_requirements(task)
        
        # Match requirements to agent capabilities
        recommended_agents = []
        for agent, capabilities in agent_capabilities.items():
            matches = [req for req in task_requirements if req in capabilities]
            if matches:
                recommended_agents.append({
                    "agent": agent,
                    "matched_capabilities": matches,
                    "match_score": len(matches) / len(task_requirements) if task_requirements else 0.0
                })
        
        # Sort by match score
        recommended_agents.sort(key=lambda x: x["match_score"], reverse=True)
        
        # Generate optimized workflow
        optimized_workflow = {
            "task": task,
            "requirements": task_requirements,
            "recommended_agents": recommended_agents,
            "coordination_strategy": self._determine_coordination_strategy(recommended_agents),
            "estimated_efficiency": self._estimate_efficiency(recommended_agents)
        }
        
        return {
            "success": True,
            "optimized_workflow": optimized_workflow,
            "message": f"Optimized workflow generated using {len(recommended_agents)} agents"
        }

    def _analyze_task_requirements(self, task: str) -> List[str]:
        """Analyze task to determine required capabilities."""
        
        requirements = []
        task_lower = task.lower()
        
        # Determine required capabilities based on task content
        if any(word in task_lower for word in ["file", "folder", "document", "organize", "backup"]):
            requirements.extend(["file_operations", "file_search", "file_organization"])
        
        if any(word in task_lower for word in ["web", "browser", "search", "website", "form"]):
            requirements.extend(["web_navigation", "web_search", "form_filling"])
        
        if any(word in task_lower for word in ["system", "process", "command", "app", "program"]):
            requirements.extend(["system_control", "process_management", "application_control"])
        
        if any(word in task_lower for word in ["image", "visual", "screenshot", "ocr", "read"]):
            requirements.extend(["vision", "ocr", "image_analysis"])
        
        if any(word in task_lower for word in ["learn", "remember", "pattern", "preference"]):
            requirements.extend(["learning", "pattern_recognition", "adaptation"])
        
        if any(word in task_lower for word in ["task", "schedule", "plan", "project", "meeting"]):
            requirements.extend(["task_management", "scheduling", "project_coordination"])
        
        if any(word in task_lower for word in ["email", "notify", "communicate", "message"]):
            requirements.extend(["communication", "notification", "email"])
        
        if not requirements:
            requirements = ["general_processing", "conversation"]
        
        return list(set(requirements))  # Remove duplicates

    def _determine_coordination_strategy(self, agents: List[Dict[str, Any]]) -> str:
        """Determine best coordination strategy based on agent dependencies."""
        
        if len(agents) == 1:
            return "single_agent"
        elif len(agents) == 2:
            return "sequential"
        elif len(agents) <= 4:
            return "parallel"
        else:
            return "hierarchical"

    def _estimate_efficiency(self, agents: List[Dict[str, Any]]) -> str:
        """Estimate workflow efficiency based on agent selection."""
        
        total_match_score = sum(agent["match_score"] for agent in agents)
        avg_match_score = total_match_score / len(agents) if agents else 0
        
        if avg_match_score >= 0.8:
            return "high"
        elif avg_match_score >= 0.5:
            return "medium"
        else:
            return "low"

    def create_gantt_chart(
        self,
        project_id: str,
        output_format: str = "data"
    ) -> Dict[str, Any]:
        """Generate Gantt chart data for a project."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        project_tasks = [t for t in self.tasks if t.get("project_id") == project_id]
        milestones = project.get("milestones", [])
        
        # Create Gantt chart data structure
        gantt_data = {
            "project": project["name"],
            "start_date": project.get("start_date"),
            "end_date": project.get("end_date"),
            "tasks": [],
            "milestones": []
        }
        
        # Add tasks to Gantt chart
        for task in project_tasks:
            task_start = task.get("created_at", datetime.now().isoformat())
            task_end = task.get("due_date") or task_start
            task_status = task["status"]
            
            # Determine color based on status
            color = {
                "completed": "#4CAF50",
                "in_progress": "#2196F3",
                "pending": "#FF9800",
                "cancelled": "#F44336"
            }.get(task_status, "#9E9E9E")
            
            gantt_data["tasks"].append({
                "id": task["id"],
                "name": task["title"],
                "start": task_start,
                "end": task_end,
                "status": task_status,
                "color": color,
                "progress": 1.0 if task_status == "completed" else 0.5 if task_status == "in_progress" else 0.0
            })
        
        # Add milestones to Gantt chart
        for milestone in milestones:
            gantt_data["milestones"].append({
                "id": milestone["id"],
                "name": milestone["title"],
                "date": milestone["target_date"],
                "status": milestone["status"],
                "color": "#E91E63" if milestone["status"] == "completed" else "#9C27B0"
            })
        
        # Sort by start date
        gantt_data["tasks"].sort(key=lambda x: x["start"])
        gantt_data["milestones"].sort(key=lambda x: x["date"])
        
        if output_format == "data":
            return {
                "success": True,
                "gantt_data": gantt_data,
                "message": f"Gantt chart data generated for project '{project['name']}'"
            }
        elif output_format == "visual":
            # Generate a simple ASCII-based visual representation
            return self._generate_ascii_gantt(gantt_data)
    
    def _generate_ascii_gantt(self, gantt_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate ASCII-based Gantt chart visualization."""
        
        if not gantt_data["tasks"]:
            return {
                "success": False,
                "error": "No tasks to visualize in Gantt chart"
            }
        
        # Determine date range
        all_dates = []
        for task in gantt_data["tasks"]:
            all_dates.append(task["start"])
            all_dates.append(task["end"])
        for milestone in gantt_data["milestones"]:
            all_dates.append(milestone["date"])
        
        # Convert to datetime and find range
        dates = [datetime.fromisoformat(d) for d in all_dates if d]
        if not dates:
            return {"success": False, "error": "No valid dates found"}
        
        min_date = min(dates)
        max_date = max(dates)
        total_days = (max_date - min_date).days + 1
        
        # Generate ASCII Gantt chart
        chart_lines = []
        chart_lines.append(f"Gantt Chart: {gantt_data['project']}")
        chart_lines.append(f"Timeline: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
        chart_lines.append("")
        
        # Add tasks
        for task in gantt_data["tasks"]:
            task_start = datetime.fromisoformat(task["start"])
            task_end = datetime.fromisoformat(task["end"])
            
            start_offset = (task_start - min_date).days
            duration = (task_end - task_start).days + 1
            
            # Create bar
            bar = " " * start_offset + "█" * duration
            
            # Add task info
            status_symbol = {
                "completed": "✓",
                "in_progress": "→",
                "pending": "○",
                "cancelled": "✗"
            }.get(task["status"], "?")
            
            chart_lines.append(f"{status_symbol} {task['name'][:30]:30} {bar}")
        
        # Add milestones
        chart_lines.append("")
        chart_lines.append("Milestones:")
        for milestone in gantt_data["milestones"]:
            milestone_date = datetime.fromisoformat(milestone["date"])
            offset = (milestone_date - min_date).days
            bar = " " * offset + "▼"
            status_symbol = "✓" if milestone["status"] == "completed" else "○"
            chart_lines.append(f"{status_symbol} {milestone['name'][:30]:30} {bar}")
        
        return {
            "success": True,
            "gantt_chart": "\n".join(chart_lines),
            "message": "ASCII Gantt chart generated"
        }

    def allocate_resources(
        self,
        project_id: str,
        resources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Allocate resources to a project."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        # Initialize resources if not present
        if "resources" not in project:
            project["resources"] = []
        
        # Add resources with allocation tracking
        for resource in resources:
            resource_entry = {
                "id": str(uuid.uuid4()),
                "name": resource.get("name", "Unnamed Resource"),
                "type": resource.get("type", "human"),  # human, equipment, budget
                "availability": resource.get("availability", 1.0),  # 0.0 to 1.0
                "allocated_tasks": [],
                "cost_per_hour": resource.get("cost_per_hour", 0),
                "assigned_at": datetime.now().isoformat()
            }
            project["resources"].append(resource_entry)
        
        self._save_projects()
        
        return {
            "success": True,
            "message": f"Allocated {len(resources)} resources to project '{project['name']}'",
            "resources": project["resources"]
        }

    def assign_task_to_resource(
        self,
        task_id: str,
        resource_id: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Assign a task to a specific resource."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task with ID {task_id} not found"}
        
        resource = next((r for r in project.get("resources", []) if r["id"] == resource_id), None)
        if not resource:
            return {"success": False, "error": f"Resource with ID {resource_id} not found"}
        
        # Assign task to resource
        resource["allocated_tasks"].append(task_id)
        task["assigned_resource"] = resource_id
        
        self._save_projects()
        self._save_tasks()
        
        return {
            "success": True,
            "message": f"Task '{task['title']}' assigned to resource '{resource['name']}'",
            "task": task,
            "resource": resource
        }

    def analyze_resource_utilization(self, project_id: str) -> Dict[str, Any]:
        """Analyze resource utilization for a project."""
        
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        resources = project.get("resources", [])
        project_tasks = [t for t in self.tasks if t.get("project_id") == project_id]
        
        utilization_data = {
            "project": project["name"],
            "resources": [],
            "overall_utilization": 0.0,
            "recommendations": []
        }
        
        total_utilization = 0.0
        
        for resource in resources:
            assigned_tasks = len(resource["allocated_tasks"])
            total_project_tasks = len(project_tasks)
            
            if total_project_tasks > 0:
                utilization = assigned_tasks / total_project_tasks
            else:
                utilization = 0.0
            
            # Calculate cost contribution
            task_count = len(resource["allocated_tasks"])
            cost_contribution = task_count * resource.get("cost_per_hour", 0)
            
            resource_data = {
                "name": resource["name"],
                "type": resource["type"],
                "utilization": round(utilization, 2),
                "assigned_tasks": assigned_tasks,
                "availability": resource["availability"],
                "cost_contribution": cost_contribution,
                "overloaded": utilization > resource["availability"]
            }
            
            utilization_data["resources"].append(resource_data)
            total_utilization += utilization
            
            # Generate recommendations
            if resource_data["overloaded"]:
                utilization_data["recommendations"].append(
                    f"Resource '{resource['name']}' is overloaded ({utilization:.1%} utilization vs {resource['availability']:.1%} availability)"
                )
            elif utilization < 0.3 and resource["availability"] > 0.5:
                utilization_data["recommendations"].append(
                    f"Resource '{resource['name']}' is underutilized ({utilization:.1%} utilization)"
                )
        
        if resources:
            utilization_data["overall_utilization"] = round(total_utilization / len(resources), 2)
        
        return {
            "success": True,
            "utilization_analysis": utilization_data,
            "message": f"Resource utilization analysis completed for project '{project['name']}'"
        }

    def track_time_for_task(
        self,
        task_id: str,
        hours_spent: float,
        description: str = ""
    ) -> Dict[str, Any]:
        """Track time spent on a specific task."""
        
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task with ID {task_id} not found"}
        
        # Initialize time tracking if not present
        if "time_tracking" not in task:
            task["time_tracking"] = []
        
        time_entry = {
            "id": str(uuid.uuid4()),
            "hours_spent": hours_spent,
            "description": description,
            "recorded_at": datetime.now().isoformat()
        }
        
        task["time_tracking"].append(time_entry)
        
        # Update total time
        total_time = sum(entry["hours_spent"] for entry in task["time_tracking"])
        task["total_hours_spent"] = round(total_time, 2)
        
        self._save_tasks()
        
        return {
            "success": True,
            "message": f"Recorded {hours_spent} hours for task '{task['title']}'",
            "time_entry": time_entry,
            "total_hours_spent": task["total_hours_spent"]
        }

    def calculate_productivity_metrics(self, days: int = 7) -> Dict[str, Any]:
        """Calculate productivity metrics for a specified time period."""
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get tasks completed in the period
        completed_tasks = [
            task for task in self.tasks
            if task["status"] == "completed" and task.get("completed_at")
            and start_date <= datetime.fromisoformat(task["completed_at"]) <= end_date
        ]
        
        # Get tasks created in the period
        created_tasks = [
            task for task in self.tasks
            if start_date <= datetime.fromisoformat(task["created_at"]) <= end_date
        ]
        
        # Calculate metrics
        total_completed = len(completed_tasks)
        total_created = len(created_tasks)
        completion_rate = total_completed / total_created if total_created > 0 else 0.0
        
        # Calculate time spent
        total_hours = 0.0
        for task in completed_tasks:
            total_hours += task.get("total_hours_spent", 0.0)
        
        # Calculate average time per task
        avg_time_per_task = total_hours / total_completed if total_completed > 0 else 0.0
        
        # Calculate task priority distribution
        priority_distribution = {}
        for task in completed_tasks:
            priority = task["priority"]
            priority_distribution[priority] = priority_distribution.get(priority, 0) + 1
        
        # Calculate project distribution
        project_distribution = {}
        for task in completed_tasks:
            project_id = task.get("project_id")
            if project_id:
                project = next((p for p in self.projects if p["id"] == project_id), None)
                if project:
                    project_name = project["name"]
                    project_distribution[project_name] = project_distribution.get(project_name, 0) + 1
        
        metrics = {
            "period_days": days,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "tasks_completed": total_completed,
            "tasks_created": total_created,
            "completion_rate": round(completion_rate, 2),
            "total_hours_spent": round(total_hours, 2),
            "average_hours_per_task": round(avg_time_per_task, 2),
            "priority_distribution": priority_distribution,
            "project_distribution": project_distribution,
            "productivity_score": self._calculate_productivity_score(
                total_completed, completion_rate, total_hours, days
            )
        }
        
        return {
            "success": True,
            "productivity_metrics": metrics,
            "message": f"Productivity metrics calculated for the past {days} days"
        }

    def _calculate_productivity_score(
        self,
        tasks_completed: int,
        completion_rate: float,
        total_hours: float,
        days: int
    ) -> float:
        """Calculate an overall productivity score (0.0 to 1.0)."""
        
        # Base score from completion rate
        score = completion_rate * 0.4
        
        # Add completion volume component
        expected_tasks_per_day = 2.0  # Adjustable baseline
        actual_tasks_per_day = tasks_completed / days if days > 0 else 0
        volume_score = min(actual_tasks_per_day / expected_tasks_per_day, 1.0) * 0.3
        score += volume_score
        
        # Add efficiency component (more tasks completed in fewer hours is better)
        if tasks_completed > 0:
            avg_hours_per_task = total_hours / tasks_completed
            if avg_hours_per_task > 0:
                expected_hours_per_task = 2.0  # Adjustable baseline
                efficiency_score = min(expected_hours_per_task / avg_hours_per_task, 1.0) * 0.3
                score += efficiency_score
            else:
                # If no time tracked, give neutral efficiency score
                score += 0.15  # Half of max efficiency score
        
        return round(score, 2)

    def generate_productivity_report(
        self,
        days: int = 7,
        format: str = "text"
    ) -> Dict[str, Any]:
        """Generate a comprehensive productivity report."""
        
        metrics_result = self.calculate_productivity_metrics(days)
        if not metrics_result["success"]:
            return metrics_result
        
        metrics = metrics_result["productivity_metrics"]
        
        if format == "text":
            report_lines = []
            report_lines.append("=" * 50)
            report_lines.append(f"PRODUCTIVITY REPORT - Last {days} Days")
            report_lines.append("=" * 50)
            report_lines.append(f"Period: {metrics['period_start']} to {metrics['period_end']}")
            report_lines.append("")
            report_lines.append("Summary:")
            report_lines.append(f"  Tasks Completed: {metrics['tasks_completed']}")
            report_lines.append(f"  Tasks Created: {metrics['tasks_created']}")
            report_lines.append(f"  Completion Rate: {metrics['completion_rate']:.1%}")
            report_lines.append(f"  Total Hours Spent: {metrics['total_hours_spent']:.1f}")
            report_lines.append(f"  Average Hours per Task: {metrics['average_hours_per_task']:.1f}")
            report_lines.append(f"  Productivity Score: {metrics['productivity_score']:.1%}")
            report_lines.append("")
            
            if metrics['priority_distribution']:
                report_lines.append("Priority Distribution:")
                for priority, count in metrics['priority_distribution'].items():
                    report_lines.append(f"  {priority.capitalize()}: {count} tasks")
                report_lines.append("")
            
            if metrics['project_distribution']:
                report_lines.append("Project Distribution:")
                for project, count in metrics['project_distribution'].items():
                    report_lines.append(f"  {project}: {count} tasks")
                report_lines.append("")
            
            report_lines.append("=" * 50)
            
            return {
                "success": True,
                "productivity_report": "\n".join(report_lines),
                "metrics": metrics,
                "message": f"Productivity report generated for the past {days} days"
            }
        
        elif format == "json":
            return {
                "success": True,
                "productivity_report": metrics,
                "message": f"Productivity report generated (JSON format)"
            }
        
        else:
            return {
                "success": False,
                "error": f"Unsupported format: {format}",
                "message": "Supported formats: text, json"
            }

    def integrate_weather_api(
        self,
        location: str,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Integrate with weather API for location-based information."""
        
        # Use provided API key or check configuration
        weather_config = self.config.get("weather_api", {})
        api_key = api_key or weather_config.get("api_key")
        
        if not api_key:
            return {
                "success": False,
                "error": "Weather API key required",
                "message": "Please provide an API key or configure weather_api in settings.json",
                "setup_instructions": {
                    "method": "configure_weather_api",
                    "required_fields": ["api_key"],
                    "example": "OpenWeatherMap, WeatherAPI, or similar service"
                }
            }
        
        try:
            import requests
            
            # Example using OpenWeatherMap API
            base_url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": api_key,
                "units": "metric"
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                weather_data = response.json()
                
                return {
                    "success": True,
                    "weather_data": {
                        "location": weather_data.get("name"),
                        "temperature": weather_data["main"]["temp"],
                        "humidity": weather_data["main"]["humidity"],
                        "description": weather_data["weather"][0]["description"],
                        "wind_speed": weather_data["wind"]["speed"]
                    },
                    "message": f"Weather data retrieved for {location}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Weather API error: {response.status_code}",
                    "message": "Failed to retrieve weather data. Check API key and location."
                }
                
        except ImportError:
            return {
                "success": False,
                "error": "Requests library not available",
                "message": "Weather API integration requires the requests library"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Weather API integration failed: {str(e)}",
                "message": "Failed to retrieve weather data"
            }

    def integrate_news_api(
        self,
        query: str,
        api_key: Optional[str] = None,
        articles_count: int = 5
    ) -> Dict[str, Any]:
        """Integrate with news API for topic-based news retrieval."""
        
        news_config = self.config.get("news_api", {})
        api_key = api_key or news_config.get("api_key")
        
        if not api_key:
            return {
                "success": False,
                "error": "News API key required",
                "message": "Please provide an API key or configure news_api in settings.json",
                "setup_instructions": {
                    "method": "configure_news_api",
                    "required_fields": ["api_key"],
                    "example": "NewsAPI.org or similar service"
                }
            }
        
        try:
            import requests
            
            # Example using NewsAPI
            base_url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "apiKey": api_key,
                "pageSize": articles_count,
                "sortBy": "publishedAt"
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                news_data = response.json()
                articles = news_data.get("articles", [])
                
                formatted_articles = []
                for article in articles[:articles_count]:
                    formatted_articles.append({
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "published_at": article.get("publishedAt"),
                        "source": article.get("source", {}).get("name")
                    })
                
                return {
                    "success": True,
                    "news_data": {
                        "query": query,
                        "total_results": len(formatted_articles),
                        "articles": formatted_articles
                    },
                    "message": f"Retrieved {len(formatted_articles)} news articles for '{query}'"
                }
            else:
                return {
                    "success": False,
                    "error": f"News API error: {response.status_code}",
                    "message": "Failed to retrieve news data. Check API key and query."
                }
                
        except ImportError:
            return {
                "success": False,
                "error": "Requests library not available",
                "message": "News API integration requires the requests library"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"News API integration failed: {str(e)}",
                "message": "Failed to retrieve news data"
            }

    def integrate_stock_api(
        self,
        symbol: str,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Integrate with stock market API for financial data."""
        
        stock_config = self.config.get("stock_api", {})
        api_key = api_key or stock_config.get("api_key")
        
        if not api_key:
            return {
                "success": False,
                "error": "Stock API key required",
                "message": "Please provide an API key or configure stock_api in settings.json",
                "setup_instructions": {
                    "method": "configure_stock_api",
                    "required_fields": ["api_key"],
                    "example": "Alpha Vantage, Yahoo Finance, or similar service"
                }
            }
        
        try:
            import requests
            
            # Example using Alpha Vantage API
            base_url = "https://www.alphavantage.co/query"
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": api_key
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            
            if response.status_code == 200:
                stock_data = response.json()
                quote = stock_data.get("Global Quote", {})
                
                if quote:
                    return {
                        "success": True,
                        "stock_data": {
                            "symbol": symbol,
                            "price": float(quote.get("05. price", 0)),
                            "change": float(quote.get("09. change", 0)),
                            "change_percent": quote.get("10. change percent", "0%"),
                            "volume": int(quote.get("06. volume", 0)),
                            "last_updated": quote.get("07. latest trading day")
                        },
                        "message": f"Stock data retrieved for {symbol}"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Invalid stock symbol or API response",
                        "message": "Could not retrieve stock data for the provided symbol"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Stock API error: {response.status_code}",
                    "message": "Failed to retrieve stock data. Check API key and symbol."
                }
                
        except ImportError:
            return {
                "success": False,
                "error": "Requests library not available",
                "message": "Stock API integration requires the requests library"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Stock API integration failed: {str(e)}",
                "message": "Failed to retrieve stock data"
            }

    def create_business_intelligence_dashboard(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """Create a comprehensive business intelligence dashboard."""
        
        # Gather all data sources
        productivity_result = self.calculate_productivity_metrics(days)
        projects_result = self.list_projects()
        tasks_result = self.list_tasks()
        
        dashboard_data = {
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "productivity": productivity_result.get("productivity_metrics", {}) if productivity_result["success"] else {},
            "projects": {
                "total": projects_result.get("total", 0),
                "active": len([p for p in projects_result.get("projects", []) if p.get("status") == "active"]),
                "completed": len([p for p in projects_result.get("projects", []) if p.get("status") == "completed"])
            },
            "tasks": {
                "total": tasks_result.get("total", 0),
                "completed": len([t for t in tasks_result.get("tasks", []) if t.get("status") == "completed"]),
                "in_progress": len([t for t in tasks_result.get("tasks", []) if t.get("status") == "in_progress"]),
                "pending": len([t for t in tasks_result.get("tasks", []) if t.get("status") == "pending"])
            }
        }
        
        # Calculate overall health score
        health_score = self._calculate_overall_health_score(dashboard_data)
        dashboard_data["overall_health_score"] = health_score
        
        # Generate insights
        insights = self._generate_business_insights(dashboard_data)
        dashboard_data["insights"] = insights
        
        return {
            "success": True,
            "business_intelligence_dashboard": dashboard_data,
            "message": f"Business intelligence dashboard generated for the past {days} days"
        }

    def _calculate_overall_health_score(self, dashboard_data: Dict[str, Any]) -> float:
        """Calculate an overall business health score (0.0 to 1.0)."""
        
        score = 0.0
        
        # Productivity component (40%)
        productivity = dashboard_data.get("productivity", {})
        productivity_score = productivity.get("productivity_score", 0.0)
        score += productivity_score * 0.4
        
        # Project completion component (30%)
        projects = dashboard_data.get("projects", {})
        total_projects = projects.get("total", 0)
        if total_projects > 0:
            project_completion_rate = projects.get("completed", 0) / total_projects
            score += project_completion_rate * 0.3
        
        # Task completion component (30%)
        tasks = dashboard_data.get("tasks", {})
        total_tasks = tasks.get("total", 0)
        if total_tasks > 0:
            task_completion_rate = tasks.get("completed", 0) / total_tasks
            score += task_completion_rate * 0.3
        
        return round(score, 2)

    def _generate_business_insights(self, dashboard_data: Dict[str, Any]) -> List[str]:
        """Generate actionable business insights from dashboard data."""
        
        insights = []
        
        # Productivity insights
        productivity = dashboard_data.get("productivity", {})
        productivity_score = productivity.get("productivity_score", 0.0)
        
        if productivity_score >= 0.8:
            insights.append("Excellent productivity! Your team is performing above expectations.")
        elif productivity_score >= 0.6:
            insights.append("Good productivity levels. Consider optimizing workflows for better efficiency.")
        elif productivity_score >= 0.4:
            insights.append("Moderate productivity. Review task allocation and resource utilization.")
        else:
            insights.append("Low productivity detected. Consider reviewing processes and resource allocation.")
        
        # Project insights
        projects = dashboard_data.get("projects", {})
        active_projects = projects.get("active", 0)
        completed_projects = projects.get("completed", 0)
        
        if active_projects > 5:
            insights.append(f"High number of active projects ({active_projects}). Consider prioritizing key initiatives.")
        elif completed_projects > active_projects:
            insights.append("Strong project completion rate. Good momentum in project delivery.")
        
        # Task insights
        tasks = dashboard_data.get("tasks", {})
        pending_tasks = tasks.get("pending", 0)
        in_progress_tasks = tasks.get("in_progress", 0)
        
        if pending_tasks > 10:
            insights.append(f"High number of pending tasks ({pending_tasks}). Consider task prioritization.")
        if in_progress_tasks > 15:
            insights.append(f"Many tasks in progress ({in_progress_tasks}). Focus on completion rather than starting new tasks.")
        
        # Time-based insights
        total_hours = productivity.get("total_hours_spent", 0)
        if total_hours > 40 * dashboard_data.get("period_days", 1):
            insights.append("High total hours logged. Monitor for burnout and consider resource optimization.")
        
        return insights

    def add_team_member(
        self,
        name: str,
        email: str,
        role: str = "member",
        skills: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Add a team member to the system."""
        
        team_path = self._data_file("team_members.json")
        team_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing team members
        try:
            if team_path.exists():
                with open(team_path, "r", encoding="utf-8") as f:
                    team_members = json.load(f)
            else:
                team_members = []
        except Exception as e:
            logger.warning("Failed to load team members: {}", str(e))
            team_members = []
        
        # Check if team member already exists
        for member in team_members:
            if member["email"] == email:
                return {
                    "success": False,
                    "error": f"Team member with email {email} already exists"
                }
        
        # Create new team member
        team_member = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "role": role,  # admin, manager, member
            "skills": skills or [],
            "assigned_projects": [],
            "assigned_tasks": [],
            "joined_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        team_members.append(team_member)
        
        # Save team members
        try:
            write_json_atomic(team_path, team_members)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save team member: {str(e)}"
            }
        
        return {
            "success": True,
            "team_member": team_member,
            "message": f"Team member '{name}' added successfully"
        }

    def list_team_members(self, role: Optional[str] = None) -> Dict[str, Any]:
        """List team members with optional role filtering."""
        
        team_path = self._data_file("team_members.json")
        
        try:
            if team_path.exists():
                with open(team_path, "r", encoding="utf-8") as f:
                    team_members = json.load(f)
            else:
                team_members = []
        except Exception as e:
            logger.warning("Failed to load team members: {}", str(e))
            team_members = []
        
        # Filter by role if specified
        if role:
            team_members = [m for m in team_members if m["role"] == role]
        
        return {
            "success": True,
            "team_members": team_members,
            "total": len(team_members)
        }

    def assign_team_member_to_project(
        self,
        team_member_id: str,
        project_id: str
    ) -> Dict[str, Any]:
        """Assign a team member to a project."""
        
        # Load team members
        team_path = self._data_file("team_members.json")
        try:
            if team_path.exists():
                with open(team_path, "r", encoding="utf-8") as f:
                    team_members = json.load(f)
            else:
                team_members = []
        except Exception as e:
            return {"success": False, "error": f"Failed to load team members: {str(e)}"}
        
        # Find team member
        team_member = next((m for m in team_members if m["id"] == team_member_id), None)
        if not team_member:
            return {"success": False, "error": f"Team member with ID {team_member_id} not found"}
        
        # Find project
        project = next((p for p in self.projects if p["id"] == project_id), None)
        if not project:
            return {"success": False, "error": f"Project with ID {project_id} not found"}
        
        # Assign team member to project
        if project_id not in team_member["assigned_projects"]:
            team_member["assigned_projects"].append(project_id)
        
        # Initialize team members in project if not present
        if "team_members" not in project:
            project["team_members"] = []
        
        if team_member_id not in project["team_members"]:
            project["team_members"].append(team_member_id)
        
        # Save both
        try:
            write_json_atomic(team_path, team_members)
            self._save_projects()
        except Exception as e:
            return {"success": False, "error": f"Failed to save assignment: {str(e)}"}
        
        return {
            "success": True,
            "message": f"Team member '{team_member['name']}' assigned to project '{project['name']}'"
        }

    def add_task_comment(
        self,
        task_id: str,
        comment: str,
        author_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a comment to a task."""
        
        task = next((t for t in self.tasks if t["id"] == task_id), None)
        if not task:
            return {"success": False, "error": f"Task with ID {task_id} not found"}
        
        # Initialize comments if not present
        if "comments" not in task:
            task["comments"] = []
        
        # Create comment
        comment_entry = {
            "id": str(uuid.uuid4()),
            "comment": comment,
            "author_id": author_id,
            "created_at": datetime.now().isoformat()
        }
        
        task["comments"].append(comment_entry)
        self._save_tasks()
        
        return {
            "success": True,
            "comment": comment_entry,
            "message": f"Comment added to task '{task['title']}'"
        }

    def create_team_notification(
        self,
        recipient_id: str,
        message: str,
        notification_type: str = "general",
        related_task_id: Optional[str] = None,
        related_project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a notification for a team member."""
        
        notifications_path = self._data_file("team_notifications.json")
        notifications_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing notifications
        try:
            if notifications_path.exists():
                with open(notifications_path, "r", encoding="utf-8") as f:
                    notifications = json.load(f)
            else:
                notifications = []
        except Exception as e:
            logger.warning("Failed to load notifications: {}", str(e))
            notifications = []
        
        # Create notification
        notification = {
            "id": str(uuid.uuid4()),
            "recipient_id": recipient_id,
            "message": message,
            "type": notification_type,  # task, project, general, reminder
            "related_task_id": related_task_id,
            "related_project_id": related_project_id,
            "read": False,
            "created_at": datetime.now().isoformat()
        }
        
        notifications.append(notification)
        
        # Save notifications
        try:
            write_json_atomic(notifications_path, notifications)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save notification: {str(e)}"
            }
        
        return {
            "success": True,
            "notification": notification,
            "message": f"Notification created for team member {recipient_id}"
        }

    def get_team_notifications(
        self,
        team_member_id: str,
        unread_only: bool = False
    ) -> Dict[str, Any]:
        """Get notifications for a team member."""
        
        notifications_path = self._data_file("team_notifications.json")
        
        try:
            if notifications_path.exists():
                with open(notifications_path, "r", encoding="utf-8") as f:
                    notifications = json.load(f)
            else:
                notifications = []
        except Exception as e:
            logger.warning("Failed to load notifications: {}", str(e))
            notifications = []
        
        # Filter for recipient
        user_notifications = [n for n in notifications if n["recipient_id"] == team_member_id]
        
        # Filter for unread if specified
        if unread_only:
            user_notifications = [n for n in user_notifications if not n["read"]]
        
        # Sort by creation date (newest first)
        user_notifications.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "success": True,
            "notifications": user_notifications,
            "total": len(user_notifications),
            "unread_count": len([n for n in user_notifications if not n["read"]])
        }

    def mark_notification_as_read(
        self,
        notification_id: str,
        team_member_id: str
    ) -> Dict[str, Any]:
        """Mark a notification as read."""
        
        notifications_path = self._data_file("team_notifications.json")
        
        try:
            if notifications_path.exists():
                with open(notifications_path, "r", encoding="utf-8") as f:
                    notifications = json.load(f)
            else:
                notifications = []
        except Exception as e:
            return {"success": False, "error": f"Failed to load notifications: {str(e)}"}
        
        # Find and update notification
        notification = next(
            (n for n in notifications 
             if n["id"] == notification_id and n["recipient_id"] == team_member_id),
            None
        )
        
        if not notification:
            return {"success": False, "error": "Notification not found"}
        
        notification["read"] = True
        notification["read_at"] = datetime.now().isoformat()
        
        # Save notifications
        try:
            write_json_atomic(notifications_path, notifications)
        except Exception as e:
            return {"success": False, "error": f"Failed to save notification: {str(e)}"}
        
        return {
            "success": True,
            "message": "Notification marked as read"
        }

    def create_shared_workspace(
        self,
        name: str,
        description: str = "",
        team_member_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a shared workspace for team collaboration."""
        
        workspaces_path = self._data_file("shared_workspaces.json")
        workspaces_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing workspaces
        try:
            if workspaces_path.exists():
                with open(workspaces_path, "r", encoding="utf-8") as f:
                    workspaces = json.load(f)
            else:
                workspaces = []
        except Exception as e:
            logger.warning("Failed to load workspaces: {}", str(e))
            workspaces = []
        
        # Create workspace
        workspace = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "team_members": team_member_ids or [],
            "shared_projects": [],
            "shared_tasks": [],
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        workspaces.append(workspace)
        
        # Save workspaces
        try:
            write_json_atomic(workspaces_path, workspaces)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save workspace: {str(e)}"
            }
        
        return {
            "success": True,
            "workspace": workspace,
            "message": f"Shared workspace '{name}' created successfully"
        }

    def list_shared_workspaces(self, team_member_id: Optional[str] = None) -> Dict[str, Any]:
        """List shared workspaces, optionally filtered by team member."""
        
        workspaces_path = self._data_file("shared_workspaces.json")
        
        try:
            if workspaces_path.exists():
                with open(workspaces_path, "r", encoding="utf-8") as f:
                    workspaces = json.load(f)
            else:
                workspaces = []
        except Exception as e:
            logger.warning("Failed to load workspaces: {}", str(e))
            workspaces = []
        
        # Filter by team member if specified
        if team_member_id:
            workspaces = [w for w in workspaces if team_member_id in w.get("team_members", [])]
        
        return {
            "success": True,
            "workspaces": workspaces,
            "total": len(workspaces)
        }
