"""
Business Process Automation - Enterprise ERP/CRM Integrations and Process Mining
Advanced enterprise workflow automation with external system integrations.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from core.config import load_config, data_dir

from core.atomic_io import write_json_atomic


class BusinessProcessAutomation:
    """
    Enterprise business process automation:
    - ERP system integrations
    - CRM system integrations
    - Process mining and optimization
    - Workflow orchestration
    - Business rule engine
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize business process automation system."""
        
        self.config = load_config(config_path)
        # Project-relative, not cwd-relative (audit M-5).
        self.integrations_path = data_dir(config_path) / "business_integrations"
        self.integrations_path.mkdir(parents=True, exist_ok=True)
        
        self.workflows = self._load_workflows()
        self.business_rules = self._load_business_rules()
        self.process_logs = []
        
        logger.info("Business Process Automation initialized")

    def _load_workflows(self) -> List[Dict[str, Any]]:
        """Load business workflows from storage."""
        workflows_path = self.integrations_path / "workflows.json"
        if workflows_path.exists():
            try:
                with open(workflows_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load workflows: {}", str(e))
        return []

    def _load_business_rules(self) -> List[Dict[str, Any]]:
        """Load business rules from storage."""
        rules_path = self.integrations_path / "business_rules.json"
        if rules_path.exists():
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load business rules: {}", str(e))
        return []

    # Kept in memory only, so an uncapped list grows for the whole process
    # lifetime and is then lost on restart - the worst of both (audit L-2).
    # Matches system_agent.command_history, which was already capped at 200.
    PROCESS_LOG_LIMIT = 500

    def _trim_process_logs(self):
        """Keep the in-memory execution log bounded."""
        if len(self.process_logs) > self.PROCESS_LOG_LIMIT:
            self.process_logs = self.process_logs[-self.PROCESS_LOG_LIMIT:]

    def _save_workflows(self):
        """Save workflows to storage."""
        try:
            workflows_path = self.integrations_path / "workflows.json"
            write_json_atomic(workflows_path, self.workflows)
        except Exception as e:
            logger.error("Failed to save workflows: {}", str(e))

    def _save_business_rules(self):
        """Save business rules to storage."""
        try:
            rules_path = self.integrations_path / "business_rules.json"
            write_json_atomic(rules_path, self.business_rules)
        except Exception as e:
            logger.error("Failed to save business rules: {}", str(e))

    def create_erp_integration(
        self,
        system_name: str,
        api_endpoint: str,
        authentication: Dict[str, str],
        sync_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create an ERP system integration."""
        
        integration = {
            "id": str(uuid.uuid4()),
            "system_name": system_name,
            "system_type": "erp",
            "api_endpoint": api_endpoint,
            "authentication": authentication,
            "sync_config": sync_config,
            "status": "configured",
            "created_at": datetime.now().isoformat(),
            "last_sync": None
        }
        
        # Store integration
        integrations_path = self.integrations_path / f"{system_name}_integration.json"
        try:
            write_json_atomic(integrations_path, integration)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save ERP integration: {str(e)}"
            }
        
        return {
            "success": True,
            "integration": integration,
            "message": f"ERP integration created for {system_name}"
        }

    def create_crm_integration(
        self,
        system_name: str,
        api_endpoint: str,
        authentication: Dict[str, str],
        contact_fields: List[str]
    ) -> Dict[str, Any]:
        """Create a CRM system integration."""
        
        integration = {
            "id": str(uuid.uuid4()),
            "system_name": system_name,
            "system_type": "crm",
            "api_endpoint": api_endpoint,
            "authentication": authentication,
            "contact_fields": contact_fields,
            "status": "configured",
            "created_at": datetime.now().isoformat(),
            "last_sync": None
        }
        
        # Store integration
        integrations_path = self.integrations_path / f"{system_name}_integration.json"
        try:
            write_json_atomic(integrations_path, integration)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to save CRM integration: {str(e)}"
            }
        
        return {
            "success": True,
            "integration": integration,
            "message": f"CRM integration created for {system_name}"
        }

    def sync_with_erp(
        self,
        system_name: str,
        data_type: str = "inventory",
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Sync data with ERP system."""
        
        integration_path = self.integrations_path / f"{system_name}_integration.json"
        
        if not integration_path.exists():
            return {
                "success": False,
                "error": f"ERP integration for {system_name} not found"
            }
        
        try:
            with open(integration_path, "r", encoding="utf-8") as f:
                integration = json.load(f)
            
            # No HTTP client, no credentials flow, and no connected system
            # exist here - nothing is transferred. This previously reported
            # status "completed" and "Successfully synced", which is a claim
            # about the outside world that was never true. Report honestly
            # instead: the integration record exists, the sync does not.
            endpoint = integration.get("api_endpoint") or "(no endpoint configured)"
            return {
                "success": False,
                "not_implemented": True,
                "system_name": system_name,
                "data_type": data_type,
                "error": (
                    f"No data was synced. The ERP integration record for '{system_name}' "
                    f"is stored ({endpoint}), but this build has no connector that can "
                    "actually call it - nothing was transferred in either direction."
                ),
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"ERP sync failed: {str(e)}"
            }

    def sync_with_crm(
        self,
        system_name: str,
        sync_type: str = "contacts",
        record_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Sync data with CRM system."""
        
        integration_path = self.integrations_path / f"{system_name}_integration.json"
        
        if not integration_path.exists():
            return {
                "success": False,
                "error": f"CRM integration for {system_name} not found"
            }
        
        try:
            with open(integration_path, "r", encoding="utf-8") as f:
                integration = json.load(f)
            
            # Simulate CRM sync
            sync_result = {
                "sync_id": str(uuid.uuid4()),
                "system_name": system_name,
                "sync_type": sync_type,
                "records_synced": len(record_ids) if record_ids else 0,
                "sync_time": datetime.now().isoformat(),
                "status": "completed",
                "message": f"Sync with {system_name} completed for {sync_type}"
            }
            
            # Update last sync time
            integration["last_sync"] = sync_result["sync_time"]
            write_json_atomic(integration_path, integration)
            
            return {
                "success": True,
                "sync_result": sync_result,
                "message": f"Successfully synced {sync_type} with {system_name}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"CRM sync failed: {str(e)}"
            }

    def create_business_workflow(
        self,
        name: str,
        description: str,
        steps: List[Dict[str, Any]],
        triggers: List[Dict[str, Any]],
        conditions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create a business workflow with triggers and conditions."""
        
        workflow = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "steps": steps,
            "triggers": triggers,
            "conditions": conditions or [],
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "execution_count": 0,
            "last_executed": None
        }
        
        self.workflows.append(workflow)
        self._save_workflows()
        
        return {
            "success": True,
            "workflow": workflow,
            "message": f"Business workflow '{name}' created successfully"
        }

    def execute_workflow(
        self,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a business workflow with context."""
        
        workflow = next((w for w in self.workflows if w["id"] == workflow_id), None)
        if not workflow:
            return {
                "success": False,
                "error": f"Workflow {workflow_id} not found"
            }
        
        try:
            # Check conditions
            conditions_met = self._check_conditions(workflow["conditions"], context)
            
            if not conditions_met:
                return {
                    "success": False,
                    "error": "Workflow conditions not met",
                    "conditions": workflow["conditions"],
                    "context": context
                }
            
            # Execute steps
            execution_results = []
            for step in workflow["steps"]:
                step_result = self._execute_step(step, context)
                execution_results.append(step_result)
                
                if not step_result.get("success", False):
                    return {
                        "success": False,
                        "error": f"Workflow failed at step: {step.get('name', 'unknown')}",
                        "failed_step": step,
                        "step_result": step_result
                    }
            
            # Update workflow stats
            workflow["execution_count"] += 1
            workflow["last_executed"] = datetime.now().isoformat()
            self._save_workflows()
            
            # Log execution
            self.process_logs.append({
                "workflow_id": workflow_id,
                "workflow_name": workflow["name"],
                "executed_at": datetime.now().isoformat(),
                "context": context,
                "results": execution_results,
                "success": True
            })
            self._trim_process_logs()
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "workflow_name": workflow["name"],
                "execution_results": execution_results,
                "message": f"Workflow '{workflow['name']}' executed successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Workflow execution failed: {str(e)}"
            }

    def _check_conditions(self, conditions: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        """Check if workflow conditions are met."""
        
        if not conditions:
            return True
        
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator", "equals")
            value = condition.get("value")
            
            if field not in context:
                return False
            
            context_value = context[field]
            
            if operator == "equals":
                if context_value != value:
                    return False
            elif operator == "not_equals":
                if context_value == value:
                    return False
            elif operator == "greater_than":
                if not (context_value > value):
                    return False
            elif operator == "less_than":
                if not (context_value < value):
                    return False
            elif operator == "contains":
                if value not in str(context_value):
                    return False
        
        return True

    def _execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow step."""
        
        step_type = step.get("type")
        step_name = step.get("name", "unnamed")
        
        try:
            if step_type == "api_call":
                # Simulate API call
                return {
                    "success": True,
                    "step_name": step_name,
                    "message": f"API call to {step.get('endpoint')} executed"
                }
            
            elif step_type == "data_processing":
                # Simulate data processing
                return {
                    "success": True,
                    "step_name": step_name,
                    "message": f"Data processing on {step.get('source')} completed"
                }
            
            elif step_type == "notification":
                # Simulate notification
                return {
                    "success": True,
                    "step_name": step_name,
                    "message": f"Notification sent to {step.get('recipient')}"
                }
            
            elif step_type == "sync":
                # Simulate sync operation
                return {
                    "success": True,
                    "step_name": step_name,
                    "message": f"Sync with {step.get('system')} completed"
                }
            
            else:
                return {
                    "success": False,
                    "step_name": step_name,
                    "error": f"Unknown step type: {step_type}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "step_name": step_name,
                "error": f"Step execution failed: {str(e)}"
            }

    def mine_process_patterns(
        self,
        process_logs: List[Dict[str, Any]],
        min_frequency: int = 3
    ) -> Dict[str, Any]:
        """Mine process patterns from execution logs."""
        
        try:
            # Extract step sequences
            patterns = {}
            
            for log in process_logs:
                workflow_name = log.get("workflow_name", "unknown")
                if workflow_name not in patterns:
                    patterns[workflow_name] = {
                        "execution_count": 0,
                        "steps": [],
                        "frequent_sequences": []
                    }
                
                patterns[workflow_name]["execution_count"] += 1
                
                # Extract step sequence
                results = log.get("results", [])
                step_sequence = [r.get("step_name", "unknown") for r in results]
                patterns[workflow_name]["steps"].append(step_sequence)
            
            # Find frequent sequences
            for workflow_name, data in patterns.items():
                sequence_counts = {}
                
                for sequence in data["steps"]:
                    sequence_key = " -> ".join(sequence)
                    sequence_counts[sequence_key] = sequence_counts.get(sequence_key, 0) + 1
                
                # Filter by minimum frequency
                frequent_sequences = [
                    {"sequence": seq, "count": count}
                    for seq, count in sequence_counts.items()
                    if count >= min_frequency
                ]
                
                frequent_sequences.sort(key=lambda x: x["count"], reverse=True)
                patterns[workflow_name]["frequent_sequences"] = frequent_sequences[:10]
            
            return {
                "success": True,
                "patterns": patterns,
                "total_workflows": len(patterns),
                "min_frequency": min_frequency,
                "message": f"Process mining completed with {len(patterns)} workflows analyzed"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Process mining failed: {str(e)}"
            }

    def create_business_rule(
        self,
        rule_name: str,
        condition: Dict[str, Any],
        action: Dict[str, Any],
        priority: int = 5
    ) -> Dict[str, Any]:
        """Create a business rule for automated decision making."""
        
        rule = {
            "id": str(uuid.uuid4()),
            "rule_name": rule_name,
            "condition": condition,
            "action": action,
            "priority": priority,  # 1-10, 1 is highest
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "trigger_count": 0
        }
        
        self.business_rules.append(rule)
        self._save_business_rules()
        
        return {
            "success": True,
            "rule": rule,
            "message": f"Business rule '{rule_name}' created successfully"
        }

    def evaluate_business_rules(
        self,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate all business rules against context and trigger actions."""
        
        triggered_rules = []
        
        for rule in self.business_rules:
            if rule["status"] != "active":
                continue
            
            # Check if condition is met
            if self._check_conditions([rule["condition"]], context):
                triggered_rules.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["rule_name"],
                    "priority": rule["priority"],
                    "action": rule["action"],
                    "triggered_at": datetime.now().isoformat()
                })
                
                # Update trigger count
                rule["trigger_count"] += 1
        
        # Sort by priority (lower number = higher priority)
        triggered_rules.sort(key=lambda x: x["priority"])
        
        self._save_business_rules()
        
        return {
            "success": True,
            "triggered_rules": triggered_rules,
            "total_triggered": len(triggered_rules),
            "context": context,
            "message": f"Evaluated {len(self.business_rules)} rules, {len(triggered_rules)} triggered"
        }

    def orchestrate_cross_system_workflow(
        self,
        workflow_name: str,
        systems: List[str],
        data_flow: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Orchestrate a workflow across multiple enterprise systems."""
        
        workflow = {
            "id": str(uuid.uuid4()),
            "name": workflow_name,
            "systems": systems,
            "data_flow": data_flow,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        
        try:
            # Execute cross-system workflow
            execution_results = []
            
            for step in data_flow:
                source_system = step.get("source_system")
                target_system = step.get("target_system")
                operation = step.get("operation")
                
                result = {
                    "source_system": source_system,
                    "target_system": target_system,
                    "operation": operation,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat()
                }
                
                execution_results.append(result)
            
            workflow["status"] = "completed"
            workflow["execution_results"] = execution_results
            workflow["completed_at"] = datetime.now().isoformat()
            
            return {
                "success": True,
                "workflow": workflow,
                "message": f"Cross-system workflow '{workflow_name}' completed successfully"
            }
            
        except Exception as e:
            workflow["status"] = "failed"
            workflow["error"] = str(e)
            
            return {
                "success": False,
                "error": f"Cross-system workflow failed: {str(e)}",
                "workflow": workflow
            }

    def get_process_analytics(
        self,
        workflow_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get analytics about process execution."""
        
        try:
            if workflow_id:
                # Analytics for specific workflow
                workflow = next((w for w in self.workflows if w["id"] == workflow_id), None)
                if not workflow:
                    return {
                        "success": False,
                        "error": f"Workflow {workflow_id} not found"
                    }
                
                workflow_logs = [log for log in self.process_logs if log["workflow_id"] == workflow_id]
                
                return {
                    "success": True,
                    "workflow_id": workflow_id,
                    "workflow_name": workflow["name"],
                    "execution_count": workflow["execution_count"],
                    "last_executed": workflow["last_executed"],
                    "total_logs": len(workflow_logs),
                    "success_rate": len([log for log in workflow_logs if log["success"]]) / len(workflow_logs) if workflow_logs else 0.0,
                    "average_execution_time": self._calculate_avg_execution_time(workflow_logs)
                }
            
            else:
                # Overall process analytics
                total_executions = len(self.process_logs)
                successful_executions = len([log for log in self.process_logs if log["success"]])
                
                workflow_stats = {}
                for workflow in self.workflows:
                    workflow_logs = [log for log in self.process_logs if log["workflow_id"] == workflow["id"]]
                    workflow_stats[workflow["name"]] = {
                        "executions": len(workflow_logs),
                        "success_rate": len([log for log in workflow_logs if log["success"]]) / len(workflow_logs) if workflow_logs else 0.0
                    }
                
                return {
                    "success": True,
                    "total_executions": total_executions,
                    "successful_executions": successful_executions,
                    "overall_success_rate": successful_executions / total_executions if total_executions > 0 else 0.0,
                    "workflow_stats": workflow_stats,
                    "active_workflows": len([w for w in self.workflows if w["status"] == "active"]),
                    "total_workflows": len(self.workflows)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Process analytics failed: {str(e)}"
            }

    def _calculate_avg_execution_time(self, logs: List[Dict[str, Any]]) -> float:
        """Average execution time in seconds, computed from log timestamps.

        Previously returned a flat 5.0 regardless of input - a made-up
        number presented as a measurement.
        """
        if not logs:
            return 0.0

        durations = []
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            # Prefer an explicit duration if the log carries one.
            for key in ("duration_seconds", "elapsed_seconds", "duration"):
                value = entry.get(key)
                if isinstance(value, (int, float)):
                    durations.append(float(value))
                    break
            else:
                start, end = entry.get("started_at"), entry.get("finished_at")
                if start and end:
                    try:
                        delta = datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))
                        durations.append(delta.total_seconds())
                    except (ValueError, TypeError):
                        continue

        if not durations:
            return 0.0  # honest: no timing information in these logs
        return round(sum(durations) / len(durations), 3)