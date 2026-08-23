"""
Enterprise Security & Compliance - GDPR, Audit Trails, Multi-Tenant Support
Advanced security features for enterprise deployment and regulatory compliance.
"""

import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger


class EnterpriseSecurity:
    """
    Enterprise security and compliance:
    - GDPR compliance features
    - Audit trail management
    - Multi-tenant support
    - Role-based access control
    - Data encryption
    - Security monitoring
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize enterprise security system."""
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self.security_path = Path("data/security")
        self.security_path.mkdir(parents=True, exist_ok=True)
        
        self.audit_trail = self._load_audit_trail()
        self.tenants = self._load_tenants()
        self.roles = self._load_roles()
        self.encryption_keys = self._load_encryption_keys()
        
        logger.info("Enterprise Security initialized")

    def _load_audit_trail(self) -> List[Dict[str, Any]]:
        """Load audit trail from storage."""
        audit_path = self.security_path / "audit_trail.json"
        if audit_path.exists():
            try:
                with open(audit_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load audit trail: {}", str(e))
        return []

    def _load_tenants(self) -> List[Dict[str, Any]]:
        """Load tenant configurations."""
        tenants_path = self.security_path / "tenants.json"
        if tenants_path.exists():
            try:
                with open(tenants_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load tenants: {}", str(e))
        return []

    def _load_roles(self) -> List[Dict[str, Any]]:
        """Load role definitions."""
        roles_path = self.security_path / "roles.json"
        if roles_path.exists():
            try:
                with open(roles_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load roles: {}", str(e))
        return []

    def _load_encryption_keys(self) -> Dict[str, str]:
        """Load encryption keys."""
        keys_path = self.security_path / "encryption_keys.json"
        if keys_path.exists():
            try:
                with open(keys_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load encryption keys: {}", str(e))
        return {}

    def _save_audit_trail(self):
        """Save audit trail to storage."""
        try:
            audit_path = self.security_path / "audit_trail.json"
            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(self.audit_trail, f, indent=2)
        except Exception as e:
            logger.error("Failed to save audit trail: {}", str(e))

    def _save_tenants(self):
        """Save tenant configurations."""
        try:
            tenants_path = self.security_path / "tenants.json"
            with open(tenants_path, "w", encoding="utf-8") as f:
                json.dump(self.tenants, f, indent=2)
        except Exception as e:
            logger.error("Failed to save tenants: {}", str(e))

    def _save_roles(self):
        """Save role definitions."""
        try:
            roles_path = self.security_path / "roles.json"
            with open(roles_path, "w", encoding="utf-8") as f:
                json.dump(self.roles, f, indent=2)
        except Exception as e:
            logger.error("Failed to save roles: {}", str(e))

    def _save_encryption_keys(self):
        """Save encryption keys."""
        try:
            keys_path = self.security_path / "encryption_keys.json"
            with open(keys_path, "w", encoding="utf-8") as f:
                json.dump(self.encryption_keys, f, indent=2)
        except Exception as e:
            logger.error("Failed to save encryption keys: {}", str(e))

    def create_tenant(
        self,
        tenant_name: str,
        domain: str,
        admin_email: str,
        settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new tenant for multi-tenant deployment."""
        
        tenant = {
            "id": str(uuid.uuid4()),
            "tenant_name": tenant_name,
            "domain": domain,
            "admin_email": admin_email,
            "settings": settings or {},
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "user_count": 0,
            "storage_quota_gb": 100,
            "storage_used_gb": 0
        }
        
        self.tenants.append(tenant)
        self._save_tenants()
        
        # Log audit entry
        self.log_audit_event(
            event_type="tenant_created",
            actor="system",
            resource_type="tenant",
            resource_id=tenant["id"],
            details={"tenant_name": tenant_name, "domain": domain}
        )
        
        return {
            "success": True,
            "tenant": tenant,
            "message": f"Tenant '{tenant_name}' created successfully"
        }

    def create_role(
        self,
        role_name: str,
        permissions: List[str],
        description: str = ""
    ) -> Dict[str, Any]:
        """Create a role with specific permissions."""
        
        role = {
            "id": str(uuid.uuid4()),
            "role_name": role_name,
            "permissions": permissions,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "user_count": 0
        }
        
        self.roles.append(role)
        self._save_roles()
        
        # Log audit entry
        self.log_audit_event(
            event_type="role_created",
            actor="system",
            resource_type="role",
            resource_id=role["id"],
            details={"role_name": role_name, "permissions": permissions}
        )
        
        return {
            "success": True,
            "role": role,
            "message": f"Role '{role_name}' created successfully"
        }

    def assign_user_to_tenant(
        self,
        user_id: str,
        tenant_id: str,
        role_id: str
    ) -> Dict[str, Any]:
        """Assign a user to a tenant with a specific role."""
        
        tenant = next((t for t in self.tenants if t["id"] == tenant_id), None)
        if not tenant:
            return {
                "success": False,
                "error": f"Tenant {tenant_id} not found"
            }
        
        role = next((r for r in self.roles if r["id"] == role_id), None)
        if not role:
            return {
                "success": False,
                "error": f"Role {role_id} not found"
            }
        
        # Initialize user assignments if not present
        if "users" not in tenant:
            tenant["users"] = []
        
        user_assignment = {
            "user_id": user_id,
            "role_id": role_id,
            "assigned_at": datetime.now().isoformat(),
            "status": "active"
        }
        
        tenant["users"].append(user_assignment)
        tenant["user_count"] = len(tenant["users"])
        role["user_count"] += 1
        
        self._save_tenants()
        self._save_roles()
        
        # Log audit entry
        self.log_audit_event(
            event_type="user_assigned",
            actor="system",
            resource_type="user",
            resource_id=user_id,
            details={
                "tenant_id": tenant_id,
                "role_id": role_id,
                "tenant_name": tenant["tenant_name"],
                "role_name": role["role_name"]
            }
        )
        
        return {
            "success": True,
            "assignment": user_assignment,
            "message": f"User {user_id} assigned to tenant '{tenant['tenant_name']}' with role '{role['role_name']}'"
        }

    def check_permission(
        self,
        user_id: str,
        tenant_id: str,
        required_permission: str
    ) -> Dict[str, Any]:
        """Check if a user has a specific permission."""
        
        tenant = next((t for t in self.tenants if t["id"] == tenant_id), None)
        if not tenant:
            return {
                "success": False,
                "error": f"Tenant {tenant_id} not found"
            }
        
        # Find user assignment
        user_assignment = next(
            (u for u in tenant.get("users", []) if u["user_id"] == user_id),
            None
        )
        
        if not user_assignment:
            return {
                "success": False,
                "has_permission": False,
                "error": f"User {user_id} not found in tenant"
            }
        
        # Get role permissions
        role_id = user_assignment["role_id"]
        role = next((r for r in self.roles if r["id"] == role_id), None)
        
        if not role:
            return {
                "success": False,
                "has_permission": False,
                "error": f"Role {role_id} not found"
            }
        
        # Check permission
        has_permission = required_permission in role["permissions"]
        
        # Log access check
        self.log_audit_event(
            event_type="permission_check",
            actor=user_id,
            resource_type="permission",
            resource_id=required_permission,
            details={
                "tenant_id": tenant_id,
                "has_permission": has_permission,
                "role_id": role_id
            }
        )
        
        return {
            "success": True,
            "has_permission": has_permission,
            "user_id": user_id,
            "required_permission": required_permission,
            "role_id": role_id,
            "role_name": role["role_name"]
        }

    def log_audit_event(
        self,
        event_type: str,
        actor: str,
        resource_type: str,
        resource_id: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Log an audit event for compliance tracking."""
        
        audit_entry = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "actor": actor,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "ip_address": "system",  # In production, capture actual IP
            "user_agent": "asc-enterprise"
        }
        
        self.audit_trail.append(audit_entry)
        self._save_audit_trail()
        
        return {
            "success": True,
            "audit_entry": audit_entry,
            "message": f"Audit event logged: {event_type}"
        }

    def get_audit_trail(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Retrieve audit trail with optional filtering."""
        
        filtered_trail = self.audit_trail
        
        if filters:
            if "event_type" in filters:
                filtered_trail = [e for e in filtered_trail if e["event_type"] == filters["event_type"]]
            if "actor" in filters:
                filtered_trail = [e for e in filtered_trail if e["actor"] == filters["actor"]]
            if "resource_type" in filters:
                filtered_trail = [e for e in filtered_trail if e["resource_type"] == filters["resource_type"]]
            if "start_date" in filters:
                start_date = datetime.fromisoformat(filters["start_date"])
                filtered_trail = [
                    e for e in filtered_trail
                    if datetime.fromisoformat(e["timestamp"]) >= start_date
                ]
            if "end_date" in filters:
                end_date = datetime.fromisoformat(filters["end_date"])
                filtered_trail = [
                    e for e in filtered_trail
                    if datetime.fromisoformat(e["timestamp"]) <= end_date
                ]
        
        # Sort by timestamp (newest first)
        filtered_trail.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Apply limit
        filtered_trail = filtered_trail[:limit]
        
        return {
            "success": True,
            "audit_trail": filtered_trail,
            "total_entries": len(filtered_trail),
            "filters_applied": filters
        }

    def encrypt_data(
        self,
        data: str,
        encryption_key_id: str = "default"
    ) -> Dict[str, Any]:
        """Encrypt sensitive data using configured encryption keys."""
        
        try:
            # Get encryption key
            key = self.encryption_keys.get(encryption_key_id)
            if not key:
                return {
                    "success": False,
                    "error": f"Encryption key {encryption_key_id} not found"
                }
            
            # Simple XOR encryption for demonstration
            # In production, use AES-256
            key_bytes = key.encode()
            data_bytes = data.encode()
            
            encrypted_bytes = bytes([data_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(data_bytes))])
            encrypted_data = encrypted_bytes.hex()
            
            return {
                "success": True,
                "encrypted_data": encrypted_data,
                "encryption_key_id": encryption_key_id,
                "message": "Data encrypted successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Encryption failed: {str(e)}"
            }

    def decrypt_data(
        self,
        encrypted_data: str,
        encryption_key_id: str = "default"
    ) -> Dict[str, Any]:
        """Decrypt data using configured encryption keys."""
        
        try:
            key = self.encryption_keys.get(encryption_key_id)
            if not key:
                return {
                    "success": False,
                    "error": f"Encryption key {encryption_key_id} not found"
                }
            
            # Simple XOR decryption
            key_bytes = key.encode()
            encrypted_bytes = bytes.fromhex(encrypted_data)
            
            decrypted_bytes = bytes([encrypted_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(encrypted_bytes))])
            decrypted_data = decrypted_bytes.decode()
            
            return {
                "success": True,
                "decrypted_data": decrypted_data,
                "encryption_key_id": encryption_key_id,
                "message": "Data decrypted successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Decryption failed: {str(e)}"
            }

    def generate_encryption_key(
        self,
        key_id: str,
        key_name: str = "default"
    ) -> Dict[str, Any]:
        """Generate a new encryption key."""
        
        import secrets
        
        # Generate random key
        key = secrets.token_urlsafe(32)
        
        self.encryption_keys[key_id] = key
        self._save_encryption_keys()
        
        # Log audit entry
        self.log_audit_event(
            event_type="encryption_key_generated",
            actor="system",
            resource_type="encryption_key",
            resource_id=key_id,
            details={"key_name": key_name}
        )
        
        return {
            "success": True,
            "key_id": key_id,
            "key_name": key_name,
            "message": f"Encryption key '{key_name}' generated successfully"
        }

    def check_gdpr_compliance(
        self,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Check GDPR compliance status for a tenant."""
        
        tenant = next((t for t in self.tenants if t["id"] == tenant_id), None)
        if not tenant:
            return {
                "success": False,
                "error": f"Tenant {tenant_id} not found"
            }
        
        # Check compliance requirements
        compliance_checks = {
            "data_encryption": bool(self.encryption_keys),
            "audit_trail": len(self.audit_trail) > 0,
            "role_based_access": len(self.roles) > 0,
            "tenant_isolation": True,  # Multi-tenant architecture
            "data_retention_policy": self._check_data_retention_policy(tenant),
            "user_consent": self._check_user_consent(tenant),
            "data_portability": self._check_data_portability(tenant),
            "right_to_deletion": self._check_right_to_deletion(tenant)
        }
        
        overall_compliance = all(compliance_checks.values())
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "tenant_name": tenant["tenant_name"],
            "compliance_checks": compliance_checks,
            "overall_compliance": overall_compliance,
            "compliance_score": sum(compliance_checks.values()) / len(compliance_checks),
            "message": f"GDPR compliance check completed for '{tenant['tenant_name']}'"
        }

    def _check_data_retention_policy(self, tenant: Dict[str, Any]) -> bool:
        """Check if tenant has data retention policy configured."""
        return tenant.get("settings", {}).get("data_retention_policy") is not None

    def _check_user_consent(self, tenant: Dict[str, Any]) -> bool:
        """Check if tenant collects user consent."""
        return tenant.get("settings", {}).get("collect_user_consent", False)

    def _check_data_portability(self, tenant: Dict[str, Any]) -> bool:
        """Check if tenant supports data portability."""
        return tenant.get("settings", {}).get("data_portability", False)

    def _check_right_to_deletion(self, tenant: Dict[str, Any]) -> bool:
        """Check if tenant supports right to deletion."""
        return tenant.get("settings", {}).get("right_to_deletion", False)

    def generate_compliance_report(
        self,
        tenant_id: str,
        report_type: str = "gdpr"
    ) -> Dict[str, Any]:
        """Generate a compliance report for audit purposes."""
        
        compliance_result = self.check_gdpr_compliance(tenant_id)
        
        if not compliance_result["success"]:
            return compliance_result
        
        try:
            report_lines = []
            report_lines.append("=" * 60)
            report_lines.append(f"COMPLIANCE REPORT - {report_type.upper()}")
            report_lines.append("=" * 60)
            report_lines.append(f"Tenant: {compliance_result['tenant_name']}")
            report_lines.append(f"Report Date: {datetime.now().isoformat()}")
            report_lines.append("")
            report_lines.append("Compliance Status:")
            report_lines.append(f"  Overall: {'COMPLIANT' if compliance_result['overall_compliance'] else 'NON-COMPLIANT'}")
            report_lines.append(f"  Score: {compliance_result['compliance_score']:.1%}")
            report_lines.append("")
            report_lines.append("Detailed Checks:")
            
            for check_name, passed in compliance_result["compliance_checks"].items():
                status = "✓" if passed else "✗"
                report_lines.append(f"  {status} {check_name.replace('_', ' ').title()}")
            
            report_lines.append("")
            report_lines.append("Recommendations:")
            
            recommendations = self._generate_compliance_recommendations(compliance_result["compliance_checks"])
            for recommendation in recommendations:
                report_lines.append(f"  - {recommendation}")
            
            report_lines.append("")
            report_lines.append("=" * 60)
            
            return {
                "success": True,
                "compliance_report": "\n".join(report_lines),
                "compliance_data": compliance_result,
                "message": f"Compliance report generated for {report_type.upper()}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Report generation failed: {str(e)}"
            }

    def _generate_compliance_recommendations(self, compliance_checks: Dict[str, bool]) -> List[str]:
        """Generate recommendations based on compliance checks."""
        
        recommendations = []
        
        if not compliance_checks["data_encryption"]:
            recommendations.append("Enable data encryption for sensitive information")
        
        if not compliance_checks["audit_trail"]:
            recommendations.append("Ensure audit trail is enabled for accountability")
        
        if not compliance_checks["role_based_access"]:
            recommendations.append("Implement role-based access control for data security")
        
        if not compliance_checks["data_retention_policy"]:
            recommendations.append("Configure data retention policy for compliance")
        
        if not compliance_checks["user_consent"]:
            recommendations.append("Implement user consent collection mechanism")
        
        if not compliance_checks["data_portability"]:
            recommendations.append("Enable data portability features for user data export")
        
        if not compliance_checks["right_to_deletion"]:
            recommendations.append("Implement right to deletion for user data management")
        
        return recommendations

    def get_security_summary(self) -> Dict[str, Any]:
        """Get overall security summary of the system."""
        
        return {
            "success": True,
            "security_summary": {
                "total_tenants": len(self.tenants),
                "total_roles": len(self.roles),
                "total_audit_entries": len(self.audit_trail),
                "encryption_keys_available": len(self.encryption_keys),
                "active_tenants": len([t for t in self.tenants if t["status"] == "active"]),
                "total_users": sum(t.get("user_count", 0) for t in self.tenants),
                "compliance_score": self._calculate_compliance_score()
            },
            "message": "Security summary generated successfully"
        }

    def _calculate_compliance_score(self) -> float:
        """Calculate overall compliance score."""
        
        # Sample compliance calculation
        score = 0.0
        
        if self.encryption_keys:
            score += 0.25
        if self.audit_trail:
            score += 0.25
        if self.roles:
            score += 0.25
        if self.tenants:
            score += 0.25
        
        return score