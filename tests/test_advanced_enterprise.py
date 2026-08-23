"""
Tests for Advanced Enterprise Features
Comprehensive testing for advanced AI/ML, business process automation, security, and analytics.
"""

import pytest
from learning.advanced_neural_network import AdvancedNeuralNetwork
from agents.business_process_automation import BusinessProcessAutomation
from agents.enterprise_security import EnterpriseSecurity
from agents.advanced_analytics import AdvancedAnalytics


@pytest.fixture
def advanced_neural():
    """Fixture for Advanced Neural Network testing."""
    return AdvancedNeuralNetwork("./config/settings.json")


@pytest.fixture
def business_process():
    """Fixture for Business Process Automation testing."""
    return BusinessProcessAutomation("./config/settings.json")


@pytest.fixture
def enterprise_security():
    """Fixture for Enterprise Security testing."""
    return EnterpriseSecurity("./config/settings.json")


@pytest.fixture
def advanced_analytics():
    """Fixture for Advanced Analytics testing."""
    return AdvancedAnalytics("./config/settings.json")


class TestAdvancedNeuralNetwork:
    """Test advanced neural network capabilities."""

    def test_create_ensemble_model(self, advanced_neural):
        """Test ensemble model creation."""
        result = advanced_neural.create_ensemble_model(
            model_type="random_forest",
            input_features=10,
            task_type="classification"
        )
        
        assert result["success"] is True
        assert "model_id" in result
        assert result["model_type"] == "random_forest"

    def test_train_predictive_model(self, advanced_neural):
        """Test predictive model training."""
        # First create a model
        model_result = advanced_neural.create_ensemble_model(
            model_type="random_forest",
            input_features=5,
            task_type="classification"
        )
        
        # Train with dummy data
        training_data = [[1.0, 2.0, 3.0, 4.0, 5.0], [2.0, 3.0, 4.0, 5.0, 6.0]]
        labels = [0, 1]
        
        result = advanced_neural.train_predictive_model(
            model_id=model_result["model_id"],
            training_data=training_data,
            labels=labels
        )
        
        assert result["success"] is True
        assert "train_score" in result
        assert "val_score" in result

    def test_make_prediction(self, advanced_neural):
        """Test making predictions."""
        # Create and train model
        model_result = advanced_neural.create_ensemble_model(
            model_type="random_forest",
            input_features=3,
            task_type="classification"
        )
        
        training_data = [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]]
        labels = [0, 1]
        
        advanced_neural.train_predictive_model(
            model_id=model_result["model_id"],
            training_data=training_data,
            labels=labels
        )
        
        # Make prediction
        result = advanced_neural.make_prediction(
            model_id=model_result["model_id"],
            features=[1.5, 2.5, 3.5]
        )
        
        assert result["success"] is True
        assert "prediction" in result

    def test_detect_anomalies_statistical(self, advanced_neural):
        """Test statistical anomaly detection."""
        data = [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1], [1.2, 2.2, 3.2], [1000.0, 2000.0, 3000.0]]
        
        result = advanced_neural.detect_anomalies(
            data=data,
            threshold=1.0,  # Lower threshold to detect the extreme outlier
            method="statistical"
        )
        
        assert result["success"] is True
        assert "anomalies" in result
        # Should detect at least the extreme outlier
        assert len(result["anomalies"]) >= 1

    def test_time_series_forecast(self, advanced_neural):
        """Test time series forecasting."""
        data = [10, 12, 15, 18, 20, 22, 25]
        
        result = advanced_neural.create_time_series_forecast(
            data=data,
            forecast_periods=5,
            method="moving_average"
        )
        
        assert result["success"] is True
        assert "forecasts" in result
        assert len(result["forecasts"]) == 5

    def test_create_deep_learning_model(self, advanced_neural):
        """Test deep learning model creation."""
        result = advanced_neural.create_deep_learning_model(
            model_type="feedforward",
            input_size=10,
            hidden_layers=[64, 32],
            output_size=1
        )
        
        # May fail if PyTorch not available
        if result["success"]:
            assert "model_id" in result
            assert result["framework"] == "pytorch"
        else:
            assert "PyTorch not available" in result["error"]

    def test_list_models(self, advanced_neural):
        """Test listing available models."""
        # Create a model first
        advanced_neural.create_ensemble_model(model_type="random_forest")
        
        result = advanced_neural.list_models()
        
        assert result["success"] is True
        assert "models" in result
        assert result["total"] >= 1


class TestBusinessProcessAutomation:
    """Test business process automation features."""

    def test_create_erp_integration(self, business_process):
        """Test ERP system integration creation."""
        result = business_process.create_erp_integration(
            system_name="SAP",
            api_endpoint="https://api.sap.com/v1",
            authentication={"api_key": "test_key"},
            sync_config={"interval": 3600}
        )
        
        assert result["success"] is True
        assert result["integration"]["system_name"] == "SAP"
        assert result["integration"]["system_type"] == "erp"

    def test_create_crm_integration(self, business_process):
        """Test CRM system integration creation."""
        result = business_process.create_crm_integration(
            system_name="Salesforce",
            api_endpoint="https://api.salesforce.com/v1",
            authentication={"token": "test_token"},
            contact_fields=["name", "email", "phone"]
        )
        
        assert result["success"] is True
        assert result["integration"]["system_name"] == "Salesforce"
        assert result["integration"]["system_type"] == "crm"

    def test_sync_with_erp(self, business_process):
        """Test ERP data synchronization."""
        # First create integration
        business_process.create_erp_integration(
            system_name="SAP",
            api_endpoint="https://api.sap.com/v1",
            authentication={"api_key": "test_key"},
            sync_config={}
        )
        
        result = business_process.sync_with_erp(
            system_name="SAP",
            data_type="inventory"
        )
        
        assert result["success"] is True
        assert "sync_result" in result

    def test_create_business_workflow(self, business_process):
        """Test business workflow creation."""
        steps = [
            {"type": "api_call", "name": "Call External API", "endpoint": "https://api.example.com"},
            {"type": "data_processing", "name": "Process Data", "source": "external"}
        ]
        
        triggers = [{"type": "schedule", "schedule": "daily"}]
        
        result = business_process.create_business_workflow(
            name="Daily Data Sync",
            description="Sync data with external systems daily",
            steps=steps,
            triggers=triggers
        )
        
        assert result["success"] is True
        assert result["workflow"]["name"] == "Daily Data Sync"
        assert len(result["workflow"]["steps"]) == 2

    def test_execute_workflow(self, business_process):
        """Test workflow execution."""
        # Create workflow
        workflow_result = business_process.create_business_workflow(
            name="Test Workflow",
            description="Test workflow execution",
            steps=[{"type": "notification", "name": "Send Notification", "recipient": "admin"}],
            triggers=[]
        )
        
        result = business_process.execute_workflow(
            workflow_id=workflow_result["workflow"]["id"],
            context={"user": "test_user"}
        )
        
        assert result["success"] is True
        assert "execution_results" in result

    def test_create_business_rule(self, business_process):
        """Test business rule creation."""
        result = business_process.create_business_rule(
            rule_name="Auto-approve High Priority",
            condition={"field": "priority", "operator": "equals", "value": "high"},
            action={"type": "auto_approve"},
            priority=8
        )
        
        assert result["success"] is True
        assert result["rule"]["rule_name"] == "Auto-approve High Priority"
        assert result["rule"]["priority"] == 8

    def test_evaluate_business_rules(self, business_process):
        """Test business rule evaluation."""
        # Create a rule
        business_process.create_business_rule(
            rule_name="Test Rule",
            condition={"field": "status", "operator": "equals", "value": "pending"},
            action={"type": "notify"}
        )
        
        result = business_process.evaluate_business_rules(
            context={"status": "pending", "user": "test_user"}
        )
        
        assert result["success"] is True
        assert "triggered_rules" in result

    def test_mine_process_patterns(self, business_process):
        """Test process mining."""
        # Create dummy process logs
        process_logs = [
            {
                "workflow_name": "Data Sync",
                "results": [
                    {"step_name": "Fetch Data", "success": True},
                    {"step_name": "Process Data", "success": True}
                ]
            },
            {
                "workflow_name": "Data Sync",
                "results": [
                    {"step_name": "Fetch Data", "success": True},
                    {"step_name": "Process Data", "success": True}
                ]
            }
        ]
        
        result = business_process.mine_process_patterns(
            process_logs=process_logs,
            min_frequency=2
        )
        
        assert result["success"] is True
        assert "patterns" in result


class TestEnterpriseSecurity:
    """Test enterprise security and compliance features."""

    def test_create_tenant(self, enterprise_security):
        """Test tenant creation for multi-tenant deployment."""
        result = enterprise_security.create_tenant(
            tenant_name="ACME Corporation",
            domain="acme.com",
            admin_email="admin@acme.com",
            settings={"data_retention_policy": "90_days"}
        )
        
        assert result["success"] is True
        assert result["tenant"]["tenant_name"] == "ACME Corporation"
        assert result["tenant"]["status"] == "active"

    def test_create_role(self, enterprise_security):
        """Test role creation with permissions."""
        result = enterprise_security.create_role(
            role_name="Business Analyst",
            permissions=["read_reports", "create_dashboards", "view_analytics"],
            description="Can view and create analytics reports"
        )
        
        assert result["success"] is True
        assert result["role"]["role_name"] == "Business Analyst"
        assert len(result["role"]["permissions"]) == 3

    def test_assign_user_to_tenant(self, enterprise_security):
        """Test user assignment to tenant with role."""
        # Create tenant and role first
        tenant_result = enterprise_security.create_tenant(
            tenant_name="Test Corp",
            domain="test.com",
            admin_email="admin@test.com"
        )
        
        role_result = enterprise_security.create_role(
            role_name="User",
            permissions=["read_data"]
        )
        
        result = enterprise_security.assign_user_to_tenant(
            user_id="user_123",
            tenant_id=tenant_result["tenant"]["id"],
            role_id=role_result["role"]["id"]
        )
        
        assert result["success"] is True
        assert "assignment" in result

    def test_check_permission(self, enterprise_security):
        """Test permission checking."""
        # Setup tenant, role, and user
        tenant_result = enterprise_security.create_tenant(
            tenant_name="Perm Test",
            domain="permtest.com",
            admin_email="admin@permtest.com"
        )
        
        role_result = enterprise_security.create_role(
            role_name="Admin",
            permissions=["read_data", "write_data", "delete_data"]
        )
        
        enterprise_security.assign_user_to_tenant(
            user_id="admin_user",
            tenant_id=tenant_result["tenant"]["id"],
            role_id=role_result["role"]["id"]
        )
        
        result = enterprise_security.check_permission(
            user_id="admin_user",
            tenant_id=tenant_result["tenant"]["id"],
            required_permission="read_data"
        )
        
        assert result["success"] is True
        assert result["has_permission"] is True

    def test_log_audit_event(self, enterprise_security):
        """Test audit event logging."""
        result = enterprise_security.log_audit_event(
            event_type="data_access",
            actor="user_123",
            resource_type="report",
            resource_id="report_456",
            details={"action": "view", "report_name": "Q3 Report"}
        )
        
        assert result["success"] is True
        assert "audit_entry" in result
        assert result["audit_entry"]["event_type"] == "data_access"

    def test_get_audit_trail(self, enterprise_security):
        """Test audit trail retrieval."""
        # Log some events first
        enterprise_security.log_audit_event(
            event_type="user_login",
            actor="user_1",
            resource_type="session",
            resource_id="session_1"
        )
        
        enterprise_security.log_audit_event(
            event_type="data_export",
            actor="user_1",
            resource_type="report",
            resource_id="report_1"
        )
        
        result = enterprise_security.get_audit_trail(limit=10)
        
        assert result["success"] is True
        assert "audit_trail" in result
        assert result["total_entries"] >= 2

    def test_generate_encryption_key(self, enterprise_security):
        """Test encryption key generation."""
        result = enterprise_security.generate_encryption_key(
            key_id="primary_key",
            key_name="Primary Encryption Key"
        )
        
        assert result["success"] is True
        assert result["key_id"] == "primary_key"

    def test_encrypt_decrypt_data(self, enterprise_security):
        """Test data encryption and decryption."""
        # Generate key first
        enterprise_security.generate_encryption_key(key_id="test_key")
        
        original_data = "Sensitive Business Data"
        
        # Encrypt
        encrypt_result = enterprise_security.encrypt_data(
            data=original_data,
            encryption_key_id="test_key"
        )
        
        assert encrypt_result["success"] is True
        assert "encrypted_data" in encrypt_result
        
        # Decrypt
        decrypt_result = enterprise_security.decrypt_data(
            encrypted_data=encrypt_result["encrypted_data"],
            encryption_key_id="test_key"
        )
        
        assert decrypt_result["success"] is True
        assert decrypt_result["decrypted_data"] == original_data

    def test_check_gdpr_compliance(self, enterprise_security):
        """Test GDPR compliance checking."""
        # Create tenant with GDPR settings
        tenant_result = enterprise_security.create_tenant(
            tenant_name="GDPR Test",
            domain="gdprtest.com",
            admin_email="admin@gdprtest.com",
            settings={
                "data_retention_policy": "90_days",
                "collect_user_consent": True,
                "data_portability": True,
                "right_to_deletion": True
            }
        )
        
        result = enterprise_security.check_gdpr_compliance(
            tenant_id=tenant_result["tenant"]["id"]
        )
        
        assert result["success"] is True
        assert "compliance_checks" in result
        assert "overall_compliance" in result

    def test_generate_compliance_report(self, enterprise_security):
        """Test compliance report generation."""
        # Create tenant
        tenant_result = enterprise_security.create_tenant(
            tenant_name="Report Test",
            domain="reporttest.com",
            admin_email="admin@reporttest.com"
        )
        
        result = enterprise_security.generate_compliance_report(
            tenant_id=tenant_result["tenant"]["id"],
            report_type="gdpr"
        )
        
        assert result["success"] is True
        assert "compliance_report" in result
        assert isinstance(result["compliance_report"], str)

    def test_get_security_summary(self, enterprise_security):
        """Test security summary generation."""
        # Create some data first
        enterprise_security.create_tenant("Test Tenant", "test.com", "admin@test.com")
        enterprise_security.create_role("Test Role", ["read"])
        enterprise_security.log_audit_event("test", "user", "resource", "id")
        
        result = enterprise_security.get_security_summary()
        
        assert result["success"] is True
        assert "security_summary" in result
        assert result["security_summary"]["total_tenants"] >= 1


class TestAdvancedAnalytics:
    """Test advanced analytics and reporting features."""

    def test_create_bi_dashboard(self, advanced_analytics):
        """Test BI dashboard creation."""
        widgets = [
            {
                "id": "widget_1",
                "type": "kpi_card",
                "metric": "total_tasks"
            },
            {
                "id": "widget_2",
                "type": "chart",
                "chart_type": "line",
                "data_source": "productivity"
            }
        ]
        
        result = advanced_analytics.create_bi_dashboard(
            dashboard_name="Executive Overview",
            description="High-level business metrics",
            widgets=widgets,
            refresh_interval=300
        )
        
        assert result["success"] is True
        assert result["dashboard"]["dashboard_name"] == "Executive Overview"
        assert len(result["dashboard"]["widgets"]) == 2

    def test_refresh_dashboard(self, advanced_analytics):
        """Test dashboard data refresh."""
        # Create dashboard first
        dashboard_result = advanced_analytics.create_bi_dashboard(
            dashboard_name="Test Dashboard",
            description="Test",
            widgets=[{"id": "w1", "type": "kpi_card", "metric": "total_tasks"}]
        )
        
        result = advanced_analytics.refresh_dashboard(
            dashboard_id=dashboard_result["dashboard"]["id"]
        )
        
        assert result["success"] is True
        assert "refreshed_widgets" in result

    def test_create_predictive_model(self, advanced_analytics):
        """Test predictive model creation."""
        result = advanced_analytics.create_predictive_model(
            model_name="Task Completion Predictor",
            prediction_type="classification",
            features=["priority", "complexity", "assigned_to"],
            training_data_source="historical_tasks"
        )
        
        assert result["success"] is True
        assert result["model"]["model_name"] == "Task Completion Predictor"

    def test_create_analytics_report(self, advanced_analytics):
        """Test analytics report creation."""
        result = advanced_analytics.create_analytics_report(
            report_name="Weekly Productivity Report",
            report_type="productivity",
            parameters={"period": "7 days"},
            schedule={"frequency": "weekly", "day": "monday"}
        )
        
        assert result["success"] is True
        assert result["report"]["report_name"] == "Weekly Productivity Report"
        assert result["report"]["report_type"] == "productivity"

    def test_generate_report(self, advanced_analytics):
        """Test report generation."""
        # Create report first
        report_result = advanced_analytics.create_analytics_report(
            report_name="Test Report",
            report_type="productivity",
            parameters={"period": "30 days"}
        )
        
        result = advanced_analytics.generate_report(
            report_id=report_result["report"]["id"]
        )
        
        assert result["success"] is True
        assert "report_data" in result

    def test_create_real_time_monitor(self, advanced_analytics):
        """Test real-time monitor creation."""
        result = advanced_analytics.create_real_time_monitor(
            monitor_name="System Health Monitor",
            metrics=["cpu_usage", "memory_usage", "response_time"],
            thresholds={"cpu_usage": 80.0, "memory_usage": 85.0},
            alert_recipients=["admin@company.com", "ops@company.com"]
        )
        
        assert result["success"] is True
        assert result["monitor"]["monitor_name"] == "System Health Monitor"
        assert len(result["monitor"]["metrics"]) == 3

    def test_get_analytics_summary(self, advanced_analytics):
        """Test analytics summary generation."""
        # Create some data first
        advanced_analytics.create_bi_dashboard("Test Dashboard", "Test", [])
        advanced_analytics.create_analytics_report("Test Report", "productivity", {})
        
        result = advanced_analytics.get_analytics_summary()
        
        assert result["success"] is True
        assert "analytics_summary" in result
        assert result["analytics_summary"]["total_dashboards"] >= 1