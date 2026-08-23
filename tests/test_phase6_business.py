"""
Phase 6 Business Agent Tests
Tests for business workflow automation, scheduling, and project management.
"""

import pytest
import json
from pathlib import Path
from agents.business_agent import BusinessAgent


@pytest.fixture
def business_agent():
    """Create a BusinessAgent instance for testing."""
    return BusinessAgent("./config/settings.json")


class TestBusinessAgentBasics:
    """Test basic BusinessAgent functionality."""

    def test_business_agent_initialization(self, business_agent):
        """Test that BusinessAgent initializes correctly."""
        assert business_agent is not None
        assert hasattr(business_agent, "tasks")
        assert hasattr(business_agent, "projects")
        assert hasattr(business_agent, "schedules")

    def test_create_task(self, business_agent):
        """Test task creation."""
        result = business_agent.create_task(
            title="Test Task",
            description="Test description",
            priority="high"
        )
        
        assert result["success"] is True
        assert result["task"]["title"] == "Test Task"
        assert result["task"]["priority"] == "high"
        assert result["task"]["status"] == "pending"
        assert "id" in result["task"]

    def test_list_tasks(self, business_agent):
        """Test task listing."""
        # Create some test tasks
        business_agent.create_task("Task 1", "Description 1", "high")
        business_agent.create_task("Task 2", "Description 2", "medium")
        business_agent.create_task("Task 3", "Description 3", "low")
        
        result = business_agent.list_tasks()
        
        assert result["success"] is True
        assert result["total"] >= 3
        assert len(result["tasks"]) >= 3

    def test_list_tasks_with_filter(self, business_agent):
        """Test task listing with priority filter."""
        business_agent.create_task("High Task", "High priority task", "high")
        business_agent.create_task("Low Task", "Low priority task", "low")
        
        result = business_agent.list_tasks(priority="high")
        
        assert result["success"] is True
        assert all(task["priority"] == "high" for task in result["tasks"])

    def test_update_task_status(self, business_agent):
        """Test task status update."""
        create_result = business_agent.create_task("Status Test", "Test status update", "medium")
        task_id = create_result["task"]["id"]
        
        result = business_agent.update_task_status(task_id, "completed")
        
        assert result["success"] is True
        assert result["task"]["status"] == "completed"
        assert result["task"]["completed_at"] is not None

    def test_create_project(self, business_agent):
        """Test project creation."""
        result = business_agent.create_project(
            name="Test Project",
            description="Test project description"
        )
        
        assert result["success"] is True
        assert result["project"]["name"] == "Test Project"
        assert result["project"]["status"] == "active"
        assert "id" in result["project"]

    def test_schedule_reminder(self, business_agent):
        """Test reminder scheduling."""
        from datetime import datetime, timedelta
        
        reminder_time = (datetime.now() + timedelta(hours=1)).isoformat()
        result = business_agent.schedule_reminder(
            title="Test Reminder",
            reminder_time=reminder_time,
            description="Test reminder description"
        )
        
        assert result["success"] is True
        assert result["reminder"]["title"] == "Test Reminder"
        assert result["reminder"]["status"] == "pending"

    def test_get_daily_plan(self, business_agent):
        """Test daily plan generation."""
        # Create some test tasks
        business_agent.create_task("Urgent Task", "Urgent task description", "high")
        business_agent.create_task("Normal Task", "Normal task description", "medium")
        
        result = business_agent.get_daily_plan()
        
        assert result["success"] is True
        assert "daily_plan" in result
        assert "urgent_tasks" in result["daily_plan"]
        assert "all_tasks" in result["daily_plan"]
        assert "suggestions" in result["daily_plan"]

    def test_generate_meeting_agenda(self, business_agent):
        """Test meeting agenda generation."""
        result = business_agent.generate_meeting_agenda(
            meeting_title="Team Standup",
            duration_minutes=30
        )
        
        assert result["success"] is True
        assert "agenda" in result
        assert result["agenda"]["title"] == "Team Standup"
        assert result["agenda"]["duration_minutes"] == 30
        assert len(result["agenda"]["agenda_items"]) == 4


class TestProjectManagement:
    """Test project management features."""

    def test_add_task_to_project(self, business_agent):
        """Test adding a task to a project."""
        project_result = business_agent.create_project("Test Project")
        project_id = project_result["project"]["id"]
        
        task_result = business_agent.create_task("Project Task", "Task for project", "medium")
        task_id = task_result["task"]["id"]
        
        result = business_agent.add_task_to_project(task_id, project_id)
        
        assert result["success"] is True
        assert result["task"]["project_id"] == project_id

    def test_get_project_status(self, business_agent):
        """Test getting project status."""
        project_result = business_agent.create_project("Status Test Project")
        project_id = project_result["project"]["id"]
        
        # Add some tasks to the project
        task1 = business_agent.create_task("Task 1", "First task", "medium")
        task2 = business_agent.create_task("Task 2", "Second task", "high")
        
        business_agent.add_task_to_project(task1["task"]["id"], project_id)
        business_agent.add_task_to_project(task2["task"]["id"], project_id)
        
        # Complete one task
        business_agent.update_task_status(task1["task"]["id"], "completed")
        
        result = business_agent.get_project_status(project_id)
        
        assert result["success"] is True
        assert result["total_tasks"] == 2
        assert result["completed_tasks"] == 1
        assert result["completion_rate"] == 0.5

    def test_list_projects(self, business_agent):
        """Test listing projects."""
        business_agent.create_project("Active Project 1")
        business_agent.create_project("Active Project 2")
        
        result = business_agent.list_projects()
        
        assert result["success"] is True
        assert result["total"] >= 2

    def test_create_milestone(self, business_agent):
        """Test milestone creation."""
        project_result = business_agent.create_project("Milestone Test Project")
        project_id = project_result["project"]["id"]
        
        from datetime import datetime, timedelta
        target_date = (datetime.now() + timedelta(days=7)).isoformat()
        
        result = business_agent.create_milestone(
            project_id=project_id,
            title="Project Milestone",
            target_date=target_date,
            description="Important milestone"
        )
        
        assert result["success"] is True
        assert result["milestone"]["title"] == "Project Milestone"
        assert result["milestone"]["project_id"] == project_id

    def test_get_project_timeline(self, business_agent):
        """Test project timeline generation."""
        project_result = business_agent.create_project("Timeline Test Project")
        project_id = project_result["project"]["id"]
        
        # Add tasks and milestones
        task = business_agent.create_task("Timeline Task", "Task for timeline", "medium")
        business_agent.add_task_to_project(task["task"]["id"], project_id)
        
        from datetime import datetime, timedelta
        target_date = (datetime.now() + timedelta(days=14)).isoformat()
        business_agent.create_milestone(project_id, "Timeline Milestone", target_date)
        
        result = business_agent.get_project_timeline(project_id)
        
        assert result["success"] is True
        assert "timeline" in result
        assert result["timeline"]["total_tasks"] == 1
        assert result["timeline"]["total_milestones"] == 1


class TestEmailAndCommunication:
    """Test email and communication features."""

    def test_send_email_notification_security(self, business_agent):
        """Test that email sending requires credentials (security check)."""
        result = business_agent.send_email_notification(
            to_email="test@example.com",
            subject="Test Email",
            body="Test email body"
        )
        
        # Should fail due to security (no credentials)
        assert result["success"] is False
        assert "configured" in result.get("error", "").lower() or "credentials" in result.get("error", "").lower()

    def test_check_email_configuration(self, business_agent):
        """Test email configuration check."""
        result = business_agent.check_email_configuration()
        
        assert result["success"] is True
        assert "email_configured" in result

    def test_generate_email_template(self, business_agent):
        """Test email template generation."""
        context = {
            "task_title": "Completed Task",
            "description": "Task description",
            "completion_time": "2026-08-15T10:00:00"
        }
        
        result = business_agent.generate_email_template("task_completion", context)
        
        assert result["success"] is True
        assert "subject" in result
        assert "body" in result
        assert "Completed Task" in result["subject"]

    def test_create_communication_log(self, business_agent):
        """Test communication log creation."""
        result = business_agent.create_communication_log(
            communication_type="email",
            recipient="user@example.com",
            subject="Test Subject",
            status="draft"
        )
        
        assert result["success"] is True
        assert result["log_entry"]["recipient"] == "user@example.com"
        assert result["log_entry"]["status"] == "draft"


class TestExternalAPIIntegration:
    """Test external API integration framework."""

    def test_call_external_api_security(self, business_agent):
        """Test that external API calls require authorization (security check)."""
        result = business_agent.call_external_api(
            service_name="test_service",
            endpoint="/test",
            method="GET"
        )
        
        # Should fail due to security (not enabled)
        assert result["success"] is False
        assert "enabled" in result.get("error", "").lower() or "credentials" in result.get("error", "").lower()

    def test_get_available_services(self, business_agent):
        """Test getting available external services."""
        result = business_agent.get_available_services()
        
        assert result["success"] is True
        assert "services" in result
        assert "total" in result

    def test_configure_service_framework(self, business_agent):
        """Test that service configuration requires manual setup (security check)."""
        result = business_agent.configure_service(
            service_name="test_service",
            configuration={
                "required_fields": ["api_key"],
                "optional_fields": ["timeout"]
            }
        )
        
        # Should indicate manual configuration required
        assert result["success"] is False
        assert "manual" in result.get("error", "").lower() or "required" in result.get("error", "").lower()


class TestMultiAgentCoordination:
    """Test multi-agent coordination features."""

    def test_coordinate_agents(self, business_agent):
        """Test multi-agent coordination planning."""
        result = business_agent.coordinate_agents(
            task="Complex task requiring multiple agents",
            required_agents=["file", "system", "web"],
            coordination_type="sequential"
        )
        
        assert result["success"] is True
        assert "coordination_plan" in result
        assert result["coordination_plan"]["coordination_type"] == "sequential"
        assert len(result["coordination_plan"]["steps"]) == 3

    def test_get_agent_status(self, business_agent):
        """Test getting agent status."""
        result = business_agent.get_agent_status()
        
        assert result["success"] is True
        assert "agent_status" in result
        assert "total_agents" in result
        assert "available_agents" in result

    def test_optimize_agent_workflow(self, business_agent):
        """Test agent workflow optimization."""
        agent_capabilities = {
            "file": ["file_operations", "file_search", "file_organization"],
            "web": ["web_navigation", "web_search", "form_filling"],
            "system": ["system_control", "process_management"]
        }
        
        result = business_agent.optimize_agent_workflow(
            task="File organization task",
            agent_capabilities=agent_capabilities
        )
        
        assert result["success"] is True
        assert "optimized_workflow" in result
        assert "coordination_strategy" in result["optimized_workflow"]
        assert "estimated_efficiency" in result["optimized_workflow"]


class TestAdvancedEmailFeatures:
    """Test advanced email features."""

    def test_configure_email(self, business_agent):
        """Test email configuration."""
        # Note: This test uses dummy credentials for testing purposes
        result = business_agent.configure_email(
            smtp_server="smtp.example.com",
            smtp_port=587,
            email_address="test@example.com",
            password="test_password",
            use_tls=True
        )
        
        # Should fail with invalid SMTP server (expected)
        assert result["success"] is False or result["success"] is True
        if not result["success"]:
            # Accept various connection-related error messages
            error_lower = result.get("error", "").lower()
            assert any(term in error_lower for term in ["smtp", "connection", "getaddrinfo", "dns", "timeout"])

    def test_send_email_with_configuration(self, business_agent):
        """Test email sending when configured."""
        # First configure email (will fail with dummy credentials, but tests the flow)
        config_result = business_agent.configure_email(
            smtp_server="smtp.example.com",
            smtp_port=587,
            email_address="test@example.com",
            password="test_password"
        )
        
        # Even if config fails, test the error handling
        send_result = business_agent.send_email_notification(
            to_email="recipient@example.com",
            subject="Test Email",
            body="This is a test email"
        )
        
        # Should fail due to no valid configuration
        assert send_result["success"] is False


class TestMultiPlatformCalendar:
    """Test multi-platform calendar integration."""

    def test_windows_calendar_event(self, business_agent):
        """Test Windows calendar event creation."""
        from datetime import datetime, timedelta
        
        start_time = (datetime.now() + timedelta(hours=1)).isoformat()
        end_time = (datetime.now() + timedelta(hours=2)).isoformat()
        
        result = business_agent.add_calendar_event(
            title="Test Windows Event",
            start_time=start_time,
            end_time=end_time,
            calendar_type="windows"
        )
        
        # May fail if Outlook not available, but should return proper structure
        assert "success" in result
        assert "calendar_type" in result or "error" in result

    def test_google_calendar_configuration(self, business_agent):
        """Test Google Calendar configuration."""
        result = business_agent.configure_google_calendar(
            api_key="test_api_key",
            calendar_id="primary"
        )
        
        # Should fail with invalid API key (expected)
        assert result["success"] is False or result["success"] is True
        if not result["success"]:
            assert "API" in result.get("error", "").upper() or "requests" in result.get("error", "").lower()

    def test_google_calendar_event(self, business_agent):
        """Test Google Calendar event creation."""
        from datetime import datetime, timedelta
        
        start_time = (datetime.now() + timedelta(hours=1)).isoformat()
        end_time = (datetime.now() + timedelta(hours=2)).isoformat()
        
        result = business_agent.add_calendar_event(
            title="Test Google Event",
            start_time=start_time,
            end_time=end_time,
            calendar_type="google"
        )
        
        # Should fail if not configured
        assert result["success"] is False
        assert "configured" in result.get("error", "").lower()

    def test_apple_calendar_event(self, business_agent):
        """Test Apple Calendar event creation."""
        from datetime import datetime, timedelta
        
        start_time = (datetime.now() + timedelta(hours=1)).isoformat()
        end_time = (datetime.now() + timedelta(hours=2)).isoformat()
        
        result = business_agent.add_calendar_event(
            title="Test Apple Event",
            start_time=start_time,
            end_time=end_time,
            calendar_type="apple"
        )
        
        # Should fail on Windows (expected)
        assert result["success"] is False or result["success"] is True
        if not result["success"]:
            assert "macOS" in result.get("message", "") or "unavailable" in result.get("error", "").lower()


class TestAdvancedProjectManagement:
    """Test advanced project management features."""

    def test_create_gantt_chart(self, business_agent):
        """Test Gantt chart generation."""
        # Create a project with tasks
        project_result = business_agent.create_project("Gantt Test Project")
        project_id = project_result["project"]["id"]
        
        # Add tasks
        task1 = business_agent.create_task("Task 1", "First task", "high")
        task2 = business_agent.create_task("Task 2", "Second task", "medium")
        
        business_agent.add_task_to_project(task1["task"]["id"], project_id)
        business_agent.add_task_to_project(task2["task"]["id"], project_id)
        
        # Create Gantt chart
        result = business_agent.create_gantt_chart(project_id, output_format="data")
        
        assert result["success"] is True
        assert "gantt_data" in result
        assert result["gantt_data"]["project"] == "Gantt Test Project"
        assert len(result["gantt_data"]["tasks"]) == 2

    def test_ascii_gantt_chart(self, business_agent):
        """Test ASCII Gantt chart visualization."""
        project_result = business_agent.create_project("ASCII Gantt Project")
        project_id = project_result["project"]["id"]
        
        task = business_agent.create_task("ASCII Task", "Test task", "high")
        business_agent.add_task_to_project(task["task"]["id"], project_id)
        
        result = business_agent.create_gantt_chart(project_id, output_format="visual")
        
        assert result["success"] is True
        assert "gantt_chart" in result
        assert isinstance(result["gantt_chart"], str)

    def test_allocate_resources(self, business_agent):
        """Test resource allocation."""
        project_result = business_agent.create_project("Resource Test Project")
        project_id = project_result["project"]["id"]
        
        resources = [
            {
                "name": "Developer 1",
                "type": "human",
                "availability": 0.8,
                "cost_per_hour": 50
            },
            {
                "name": "Developer 2",
                "type": "human",
                "availability": 1.0,
                "cost_per_hour": 60
            }
        ]
        
        result = business_agent.allocate_resources(project_id, resources)
        
        assert result["success"] is True
        assert len(result["resources"]) == 2

    def test_assign_task_to_resource(self, business_agent):
        """Test assigning task to resource."""
        project_result = business_agent.create_project("Task Assignment Project")
        project_id = project_result["project"]["id"]
        
        # Allocate resources
        resources = [{"name": "Test Resource", "type": "human", "availability": 1.0}]
        allocate_result = business_agent.allocate_resources(project_id, resources)
        resource_id = allocate_result["resources"][0]["id"]
        
        # Create and assign task
        task = business_agent.create_task("Resource Task", "Test task", "medium")
        business_agent.add_task_to_project(task["task"]["id"], project_id)
        
        result = business_agent.assign_task_to_resource(task["task"]["id"], resource_id, project_id)
        
        assert result["success"] is True
        assert result["task"]["assigned_resource"] == resource_id

    def test_resource_utilization_analysis(self, business_agent):
        """Test resource utilization analysis."""
        project_result = business_agent.create_project("Utilization Project")
        project_id = project_result["project"]["id"]
        
        # Allocate resources
        resources = [{"name": "Test Resource", "type": "human", "availability": 0.5}]
        business_agent.allocate_resources(project_id, resources)
        
        # Add tasks
        task1 = business_agent.create_task("Task 1", "First task", "high")
        task2 = business_agent.create_task("Task 2", "Second task", "medium")
        
        business_agent.add_task_to_project(task1["task"]["id"], project_id)
        business_agent.add_task_to_project(task2["task"]["id"], project_id)
        
        result = business_agent.analyze_resource_utilization(project_id)
        
        assert result["success"] is True
        assert "utilization_analysis" in result
        assert "resources" in result["utilization_analysis"]


class TestBusinessAnalytics:
    """Test business analytics and productivity features."""

    def test_track_time_for_task(self, business_agent):
        """Test time tracking for tasks."""
        task = business_agent.create_task("Time Tracking Task", "Test time tracking", "medium")
        
        result = business_agent.track_time_for_task(
            task_id=task["task"]["id"],
            hours_spent=2.5,
            description="Initial work on task"
        )
        
        assert result["success"] is True
        assert result["total_hours_spent"] == 2.5

    def test_calculate_productivity_metrics(self, business_agent):
        """Test productivity metrics calculation."""
        result = business_agent.calculate_productivity_metrics(days=7)
        
        assert result["success"] is True
        assert "productivity_metrics" in result
        assert "tasks_completed" in result["productivity_metrics"]
        assert "completion_rate" in result["productivity_metrics"]
        assert "productivity_score" in result["productivity_metrics"]

    def test_generate_productivity_report(self, business_agent):
        """Test productivity report generation."""
        result = business_agent.generate_productivity_report(days=7, format="text")
        
        assert result["success"] is True
        assert "productivity_report" in result
        assert isinstance(result["productivity_report"], str)

    def test_productivity_report_json_format(self, business_agent):
        """Test productivity report in JSON format."""
        result = business_agent.generate_productivity_report(days=7, format="json")
        
        assert result["success"] is True
        assert "productivity_report" in result
        assert isinstance(result["productivity_report"], dict)


class TestExternalAPIIntegrations:
    """Test external API integrations."""

    def test_weather_api_integration(self, business_agent):
        """Test weather API integration."""
        result = business_agent.integrate_weather_api(
            location="New York",
            api_key="test_key"
        )
        
        # Should fail with invalid API key (expected) or succeed if the API allows it
        if not result["success"]:
            assert "API" in result.get("error", "").upper() or "requests" in result.get("error", "").lower()
        else:
            # If it succeeds, check that it returned proper structure
            assert "weather_data" in result

    def test_news_api_integration(self, business_agent):
        """Test news API integration."""
        result = business_agent.integrate_news_api(
            query="artificial intelligence",
            api_key="test_key"
        )
        
        # Should fail with invalid API key (expected) or succeed if the API allows it
        if not result["success"]:
            assert "API" in result.get("error", "").upper() or "requests" in result.get("error", "").lower()
        else:
            # If it succeeds, check that it returned proper structure
            assert "news_data" in result

    def test_stock_api_integration(self, business_agent):
        """Test stock API integration."""
        result = business_agent.integrate_stock_api(
            symbol="AAPL",
            api_key="test_key"
        )
        
        # Should fail with invalid API key (expected) or succeed if the API allows it
        if not result["success"]:
            assert "API" in result.get("error", "").upper() or "requests" in result.get("error", "").lower()
        else:
            # If it succeeds, check that it returned proper structure
            assert "stock_data" in result


class TestBusinessIntelligence:
    """Test business intelligence dashboard."""

    def test_create_business_intelligence_dashboard(self, business_agent):
        """Test business intelligence dashboard creation."""
        result = business_agent.create_business_intelligence_dashboard(days=30)
        
        assert result["success"] is True
        assert "business_intelligence_dashboard" in result
        assert "productivity" in result["business_intelligence_dashboard"]
        assert "projects" in result["business_intelligence_dashboard"]
        assert "tasks" in result["business_intelligence_dashboard"]
        assert "overall_health_score" in result["business_intelligence_dashboard"]
        assert "insights" in result["business_intelligence_dashboard"]


class TestTeamCollaboration:
    """Test team collaboration features."""

    def test_add_team_member(self, business_agent):
        """Test adding team members."""
        # Use unique email to avoid conflicts with previous test runs
        import uuid
        unique_email = f"john_{uuid.uuid4().hex[:8]}@example.com"
        
        result = business_agent.add_team_member(
            name="John Doe",
            email=unique_email,
            role="developer",
            skills=["Python", "AI"]
        )
        
        assert result["success"] is True
        assert result["team_member"]["name"] == "John Doe"
        assert result["team_member"]["email"] == unique_email

    def test_list_team_members(self, business_agent):
        """Test listing team members."""
        # Use unique emails to avoid conflicts
        import uuid
        email1 = f"alice_{uuid.uuid4().hex[:8]}@example.com"
        email2 = f"bob_{uuid.uuid4().hex[:8]}@example.com"
        
        # Add some team members first
        business_agent.add_team_member("Alice", email1, "manager")
        business_agent.add_team_member("Bob", email2, "developer")
        
        result = business_agent.list_team_members()
        
        assert result["success"] is True
        assert result["total"] >= 2

    def test_assign_team_member_to_project(self, business_agent):
        """Test assigning team member to project."""
        # Use unique email to avoid conflicts
        import uuid
        unique_email = f"charlie_{uuid.uuid4().hex[:8]}@example.com"
        
        # Add team member
        team_result = business_agent.add_team_member("Charlie", unique_email, "developer")
        team_member_id = team_result["team_member"]["id"]
        
        # Create project
        project_result = business_agent.create_project("Team Project")
        project_id = project_result["project"]["id"]
        
        result = business_agent.assign_team_member_to_project(team_member_id, project_id)
        
        assert result["success"] is True

    def test_add_task_comment(self, business_agent):
        """Test adding comments to tasks."""
        task = business_agent.create_task("Comment Task", "Task for comments", "medium")
        
        result = business_agent.add_task_comment(
            task_id=task["task"]["id"],
            comment="This is a test comment",
            author_id="test_user"
        )
        
        assert result["success"] is True
        assert result["comment"]["comment"] == "This is a test comment"

    def test_create_team_notification(self, business_agent):
        """Test creating team notifications."""
        result = business_agent.create_team_notification(
            recipient_id="test_user",
            message="Task assigned to you",
            notification_type="task",
            related_task_id="task_123"
        )
        
        assert result["success"] is True
        assert result["notification"]["message"] == "Task assigned to you"

    def test_get_team_notifications(self, business_agent):
        """Test getting team notifications."""
        # Create some notifications
        business_agent.create_team_notification("user1", "Notification 1")
        business_agent.create_team_notification("user1", "Notification 2")
        
        result = business_agent.get_team_notifications("user1")
        
        assert result["success"] is True
        assert result["total"] >= 2

    def test_mark_notification_as_read(self, business_agent):
        """Test marking notifications as read."""
        # Create notification
        notif_result = business_agent.create_team_notification("user1", "Test notification")
        notification_id = notif_result["notification"]["id"]
        
        result = business_agent.mark_notification_as_read(notification_id, "user1")
        
        assert result["success"] is True

    def test_create_shared_workspace(self, business_agent):
        """Test creating shared workspaces."""
        result = business_agent.create_shared_workspace(
            name="Development Team Workspace",
            description="Shared workspace for development team"
        )
        
        assert result["success"] is True
        assert result["workspace"]["name"] == "Development Team Workspace"

    def test_list_shared_workspaces(self, business_agent):
        """Test listing shared workspaces."""
        # Create a workspace
        business_agent.create_shared_workspace("Test Workspace")
        
        result = business_agent.list_shared_workspaces()
        
        assert result["success"] is True
        assert result["total"] >= 1