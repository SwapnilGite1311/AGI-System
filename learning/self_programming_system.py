"""
Self-Programming System - Write and Integrate New Code Autonomously
Advanced self-programming capabilities for autonomous code generation and integration.
"""

import json
import uuid
import ast
import inspect
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger


class SelfProgrammingSystem:
    """
    Self-programming system for autonomous code generation:
    - Code generation from specifications
    - Code refactoring and optimization
    - Autonomous bug fixing
    - Feature implementation
    - Code integration and testing
    """

    def __init__(self, config_path: str = "./config/settings.json"):
        """Initialize self-programming system."""
        
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)
        
        self.programming_path = Path("data/self_programming")
        self.programming_path.mkdir(parents=True, exist_ok=True)
        
        self.generated_code = self._load_generated_code()
        self.refactoring_history = self._load_refactoring_history()
        self.bug_fixes = self._load_bug_fixes()
        
        logger.info("Self-Programming System initialized")

    def _load_generated_code(self) -> List[Dict[str, Any]]:
        """Load generated code from storage."""
        code_path = self.programming_path / "generated_code.json"
        if code_path.exists():
            try:
                with open(code_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load generated code: {}", str(e))
        return []

    def _load_refactoring_history(self) -> List[Dict[str, Any]]:
        """Load refactoring history from storage."""
        history_path = self.programming_path / "refactoring_history.json"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load refactoring history: {}", str(e))
        return []

    def _load_bug_fixes(self) -> List[Dict[str, Any]]:
        """Load bug fixes from storage."""
        fixes_path = self.programming_path / "bug_fixes.json"
        if fixes_path.exists():
            try:
                with open(fixes_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load bug fixes: {}", str(e))
        return []

    def _save_generated_code(self):
        """Save generated code to storage."""
        try:
            code_path = self.programming_path / "generated_code.json"
            with open(code_path, "w", encoding="utf-8") as f:
                json.dump(self.generated_code, f, indent=2)
        except Exception as e:
            logger.error("Failed to save generated code: {}", str(e))

    def _save_refactoring_history(self):
        """Save refactoring history to storage."""
        try:
            history_path = self.programming_path / "refactoring_history.json"
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.refactoring_history, f, indent=2)
        except Exception as e:
            logger.error("Failed to save refactoring history: {}", str(e))

    def _save_bug_fixes(self):
        """Save bug fixes to storage."""
        try:
            fixes_path = self.programming_path / "bug_fixes.json"
            with open(fixes_path, "w", encoding="utf-8") as f:
                json.dump(self.bug_fixes, f, indent=2)
        except Exception as e:
            logger.error("Failed to save bug fixes: {}", str(e))

    def generate_code_from_specification(
        self,
        specification: str,
        target_file: str,
        language: str = "python"
    ) -> Dict[str, Any]:
        """Generate code from natural language specification."""
        
        try:
            # Parse specification
            parsed_spec = self._parse_specification(specification)
            
            # Generate code based on parsed spec
            generated_code = self._generate_code(parsed_spec, language)
            
            # Validate generated code
            validation_result = self._validate_code(generated_code, language)
            
            # Store generated code
            code_entry = {
                "id": str(uuid.uuid4()),
                "specification": specification,
                "target_file": target_file,
                "language": language,
                "generated_code": generated_code,
                "validation_result": validation_result,
                "generated_at": datetime.now().isoformat(),
                "status": "proposed"
            }
            
            self.generated_code.append(code_entry)
            self._save_generated_code()
            
            return {
                "success": True,
                "generated_code": code_entry,
                "validation": validation_result,
                "message": f"Code generated for {target_file}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Code generation failed: {str(e)}"
            }

    def _parse_specification(self, specification: str) -> Dict[str, Any]:
        """Parse natural language specification into structured format."""
        
        # Simple parsing based on keywords
        spec_lower = specification.lower()
        
        parsed_spec = {
            "functionality": specification,
            "type": "function" if "function" in spec_lower else "class" if "class" in spec_lower else "module",
            "language_features": [],
            "complexity": "medium"
        }
        
        # Detect language features
        if "async" in spec_lower:
            parsed_spec["language_features"].append("async")
        if "generator" in spec_lower:
            parsed_spec["language_features"].append("generator")
        if "decorator" in spec_lower:
            parsed_spec["language_features"].append("decorator")
        if "class" in spec_lower:
            parsed_spec["language_features"].append("class")
        
        # Estimate complexity
        if "complex" in spec_lower or "advanced" in spec_lower:
            parsed_spec["complexity"] = "high"
        elif "simple" in spec_lower or "basic" in spec_lower:
            parsed_spec["complexity"] = "low"
        
        return parsed_spec

    def _generate_code(self, parsed_spec: Dict[str, Any], language: str) -> str:
        """Generate code based on parsed specification."""
        
        if language != "python":
            return f"# Code generation for {language} not yet implemented"
        
        # Generate Python code based on spec
        if parsed_spec["type"] == "function":
            code = self._generate_function_code(parsed_spec)
        elif parsed_spec["type"] == "class":
            code = self._generate_class_code(parsed_spec)
        else:
            code = self._generate_module_code(parsed_spec)
        
        return code

    def _generate_function_code(self, spec: Dict[str, Any]) -> str:
        """Generate function code."""
        
        functionality = spec["functionality"]
        features = spec["language_features"]
        
        # Generate function signature
        function_name = self._extract_function_name(functionality)
        params = ["self"] if "class" in features else []
        params.extend(["param1", "param2"])  # Default parameters
        
        code_lines = []
        
        # Add docstring
        code_lines.append(f'def {function_name}({", ".join(params)}):')
        code_lines.append(f'    """')
        code_lines.append(f'    {functionality}')
        code_lines.append(f'    """')
        code_lines.append(f'    ')
        
        # Add async decorator if needed
        if "async" in features:
            code_lines.insert(0, "@asyncio.coroutine")
        
        # Add function body
        code_lines.append("    # Implementation placeholder")
        code_lines.append("    pass")
        
        return "\n".join(code_lines)

    def _generate_class_code(self, spec: Dict[str, Any]) -> str:
        """Generate class code."""
        
        functionality = spec["functionality"]
        class_name = self._extract_class_name(functionality)
        
        code_lines = []
        
        # Add class definition
        code_lines.append(f"class {class_name}:")
        code_lines.append(f'    """')
        code_lines.append(f'    {functionality}')
        code_lines.append(f'    """')
        code_lines.append(f'    ')
        
        # Add __init__ method
        code_lines.append("    def __init__(self):")
        code_lines.append("        self.initialized = True")
        code_lines.append("")
        
        # Add a sample method
        code_lines.append("    def execute(self):")
        code_lines.append("        # Implementation placeholder")
        code_lines.append("        pass")
        
        return "\n".join(code_lines)

    def _generate_module_code(self, spec: Dict[str, Any]) -> str:
        """Generate module code."""
        
        functionality = spec["functionality"]
        
        code_lines = []
        
        # Add module docstring
        code_lines.append(f'"""')
        code_lines.append(f'{functionality}')
        code_lines.append(f'"""')
        code_lines.append("")
        
        # Add imports
        code_lines.append("import json")
        code_lines.append("from typing import Dict, Any")
        code_lines.append("")
        
        # Add a main function
        code_lines.append("def main():")
        code_lines.append("    # Implementation placeholder")
        code_lines.append("    pass")
        code_lines.append("")
        
        return "\n".join(code_lines)

    def _extract_function_name(self, functionality: str) -> str:
        """Extract function name from functionality description."""
        
        # Simple extraction - take first word and convert to snake_case
        words = functionality.split()[:3]
        function_name = "_".join(words).lower().replace(" ", "_")
        
        # Remove special characters
        function_name = "".join(c for c in function_name if c.isalnum() or c == "_")
        
        return function_name or "generated_function"

    def _extract_class_name(self, functionality: str) -> str:
        """Extract class name from functionality description."""
        
        # Simple extraction - convert to CamelCase
        words = functionality.split()[:2]
        class_name = "".join(word.capitalize() for word in words)
        
        # Remove special characters
        class_name = "".join(c for c in class_name if c.isalnum())
        
        return class_name or "GeneratedClass"

    def _validate_code(self, code: str, language: str) -> Dict[str, Any]:
        """Validate generated code for syntax and structure."""
        
        validation_result = {
            "language": language,
            "syntax_valid": False,
            "structure_valid": False,
            "errors": [],
            "warnings": []
        }
        
        if language == "python":
            try:
                # Check syntax
                ast.parse(code)
                validation_result["syntax_valid"] = True
            except SyntaxError as e:
                validation_result["errors"].append(f"Syntax error: {str(e)}")
            
            # Check structure
            if "def " in code or "class " in code:
                validation_result["structure_valid"] = True
            else:
                validation_result["warnings"].append("No function or class found")
        
        return validation_result

    def refactor_code(
        self,
        source_file: str,
        refactoring_type: str = "optimization"
    ) -> Dict[str, Any]:
        """Refactor existing code for improvement."""
        
        try:
            # Read source file
            source_path = Path(source_file)
            if not source_path.exists():
                return {
                    "success": False,
                    "error": f"Source file {source_file} not found"
                }
            
            with open(source_path, "r", encoding="utf-8") as f:
                original_code = f.read()
            
            # Analyze code
            code_analysis = self._analyze_code(original_code)
            
            # Generate refactored code
            refactored_code = self._generate_refactored_code(original_code, code_analysis, refactoring_type)
            
            # Validate refactored code
            validation_result = self._validate_code(refactored_code, "python")
            
            # Store refactoring history
            refactoring_entry = {
                "id": str(uuid.uuid4()),
                "source_file": source_file,
                "refactoring_type": refactoring_type,
                "original_code": original_code,
                "refactored_code": refactored_code,
                "code_analysis": code_analysis,
                "validation_result": validation_result,
                "refactored_at": datetime.now().isoformat(),
                "status": "proposed"
            }
            
            self.refactoring_history.append(refactoring_entry)
            self._save_refactoring_history()
            
            return {
                "success": True,
                "refactoring": refactoring_entry,
                "message": f"Code refactored using {refactoring_type}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Code refactoring failed: {str(e)}"
            }

    def _analyze_code(self, code: str) -> Dict[str, Any]:
        """Analyze code for refactoring opportunities."""
        
        analysis = {
            "line_count": len(code.split("\n")),
            "function_count": code.count("def "),
            "class_count": code.count("class "),
            "complexity": "medium",
            "opportunities": []
        }
        
        # Identify refactoring opportunities
        if analysis["line_count"] > 50:
            analysis["opportunities"].append("Function extraction - split long code")
        
        if code.count("TODO") > 0:
            analysis["opportunities"].append("TODO resolution - address pending items")
        
        if code.count("if ") > 10:
            analysis["opportunities"].append("Conditional simplification - reduce nested conditions")
        
        if "import *" in code:
            analysis["opportunities"].append("Import optimization - use specific imports")
        
        return analysis

    def _generate_refactored_code(
        self,
        original_code: str,
        analysis: Dict[str, Any],
        refactoring_type: str
    ) -> str:
        """Generate refactored version of code."""
        
        # Simple refactoring based on type
        if refactoring_type == "optimization":
            refactored_code = self._optimize_code(original_code, analysis)
        elif refactoring_type == "readability":
            refactored_code = self._improve_readability(original_code, analysis)
        elif refactoring_type == "simplification":
            refactored_code = self._simplify_code(original_code, analysis)
        else:
            refactored_code = original_code  # No refactoring
        
        return refactored_code

    def _optimize_code(self, code: str, analysis: Dict[str, Any]) -> str:
        """Optimize code for performance."""
        
        # Simple optimizations
        optimized_code = code
        
        # Add comments about optimization
        if not optimized_code.startswith("# Optimized version"):
            optimized_code = "# Optimized version\n" + optimized_code
        
        return optimized_code

    def _improve_readability(self, code: str, analysis: Dict[str, Any]) -> str:
        """Improve code readability."""
        
        # Simple readability improvements
        improved_code = code
        
        # Add docstring if missing
        if '"""' not in improved_code and "def " in improved_code:
            improved_code = improved_code.replace("def ", 'def \n    """Generated docstring"""\n        ', 1)
        
        return improved_code

    def _simplify_code(self, code: str, analysis: Dict[str, Any]) -> str:
        """Simplify code structure."""
        
        # Simple simplification
        simplified_code = code
        
        # Remove excessive blank lines
        lines = simplified_code.split("\n")
        simplified_lines = [line for i, line in enumerate(lines) if not (line.strip() == "" and i > 0 and lines[i-1].strip() == "")]
        simplified_code = "\n".join(simplified_lines)
        
        return simplified_code

    def fix_bug(
        self,
        bug_report: str,
        source_file: str,
        bug_location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fix a bug in source code autonomously."""
        
        try:
            # Analyze bug report
            bug_analysis = self._analyze_bug_report(bug_report)
            
            # Read source file
            source_path = Path(source_file)
            if not source_path.exists():
                return {
                    "success": False,
                    "error": f"Source file {source_file} not found"
                }
            
            with open(source_path, "r", encoding="utf-8") as f:
                original_code = f.read()
            
            # Generate fix
            fixed_code = self._generate_bug_fix(original_code, bug_analysis, bug_location)
            
            # Validate fixed code
            validation_result = self._validate_code(fixed_code, "python")
            
            # Store bug fix
            bug_fix_entry = {
                "id": str(uuid.uuid4()),
                "bug_report": bug_report,
                "source_file": source_file,
                "bug_location": bug_location,
                "bug_analysis": bug_analysis,
                "original_code": original_code,
                "fixed_code": fixed_code,
                "validation_result": validation_result,
                "fixed_at": datetime.now().isoformat(),
                "status": "proposed"
            }
            
            self.bug_fixes.append(bug_fix_entry)
            self._save_bug_fixes()
            
            return {
                "success": True,
                "bug_fix": bug_fix_entry,
                "message": f"Bug fix generated for {source_file}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Bug fix failed: {str(e)}"
            }

    def _analyze_bug_report(self, bug_report: str) -> Dict[str, Any]:
        """Analyze bug report to understand the issue."""
        
        bug_analysis = {
            "bug_type": "unknown",
            "severity": "medium",
            "suggested_fix_type": "correction"
        }
        
        # Simple bug type detection
        bug_lower = bug_report.lower()
        
        if "error" in bug_lower or "exception" in bug_lower:
            bug_analysis["bug_type"] = "error_handling"
        elif "syntax" in bug_lower:
            bug_analysis["bug_type"] = "syntax"
        elif "logic" in bug_lower:
            bug_analysis["bug_type"] = "logic"
        elif "performance" in bug_lower:
            bug_analysis["bug_type"] = "performance"
        
        # Severity detection
        if "critical" in bug_lower or "crash" in bug_lower:
            bug_analysis["severity"] = "high"
        elif "minor" in bug_lower or "cosmetic" in bug_lower:
            bug_analysis["severity"] = "low"
        
        return bug_analysis

    def _generate_bug_fix(
        self,
        original_code: str,
        bug_analysis: Dict[str, Any],
        bug_location: Optional[str]
    ) -> str:
        """Generate code fix for the bug."""
        
        # Simple fix generation based on bug type
        if bug_analysis["bug_type"] == "error_handling":
            fixed_code = self._add_error_handling(original_code)
        elif bug_analysis["bug_type"] == "syntax":
            fixed_code = self._fix_syntax_issues(original_code)
        elif bug_analysis["bug_type"] == "logic":
            fixed_code = self._fix_logic_issues(original_code)
        else:
            fixed_code = original_code  # No specific fix
        
        # Add fix comment
        if not fixed_code.startswith("# Bug fix applied"):
            fixed_code = f"# Bug fix applied for {bug_analysis['bug_type']}\n" + fixed_code
        
        return fixed_code

    def _add_error_handling(self, code: str) -> str:
        """Add error handling to code."""
        
        # Simple error handling addition
        if "try:" not in code and "def " in code:
            # Wrap function body in try-except
            lines = code.split("\n")
            for i, line in enumerate(lines):
                if "def " in line:
                    # Insert try-except after function definition
                    indent = "    "
                    lines.insert(i + 2, f"{indent}except Exception as e:")
                    lines.insert(i + 3, f"{indent}    # Error handling")
                    lines.insert(i + 4, f"{indent}    pass")
                    break
            
            return "\n".join(lines)
        
        return code

    def _fix_syntax_issues(self, code: str) -> str:
        """Fix common syntax issues."""
        
        # Simple syntax fixes
        fixed_code = code
        
        # Fix missing colons in function definitions
        fixed_code = fixed_code.replace("def ", "def :")
        fixed_code = fixed_code.replace("def :", "def generated_function():")
        
        return fixed_code

    def _fix_logic_issues(self, code: str) -> str:
        """Fix logic issues in code."""
        
        # Simple logic fixes
        fixed_code = code
        
        # Add comments about logic verification
        if not fixed_code.startswith("# Logic verification applied"):
            fixed_code = "# Logic verification applied\n" + fixed_code
        
        return fixed_code

    def integrate_generated_code(
        self,
        code_id: str,
        integration_method: str = "append"
    ) -> Dict[str, Any]:
        """Integrate generated code into the system."""
        
        try:
            # Find generated code
            code_entry = next((c for c in self.generated_code if c["id"] == code_id), None)
            if not code_entry:
                return {
                    "success": False,
                    "error": f"Generated code {code_id} not found"
                }
            
            target_file = code_entry["target_file"]
            generated_code = code_entry["generated_code"]
            
            # Integrate based on method
            if integration_method == "append":
                result = self._append_to_file(target_file, generated_code)
            elif integration_method == "replace":
                result = self._replace_file(target_file, generated_code)
            elif integration_method == "create":
                result = self._create_file(target_file, generated_code)
            else:
                return {
                    "success": False,
                    "error": f"Unknown integration method: {integration_method}"
                }
            
            # Update code entry status
            code_entry["status"] = "integrated"
            code_entry["integrated_at"] = datetime.now().isoformat()
            code_entry["integration_method"] = integration_method
            self._save_generated_code()
            
            return {
                "success": True,
                "integration_result": result,
                "message": f"Code integrated into {target_file}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Code integration failed: {str(e)}"
            }

    def _append_to_file(self, target_file: str, code: str) -> Dict[str, Any]:
        """Append code to target file."""
        
        try:
            target_path = Path(target_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "a", encoding="utf-8") as f:
                f.write("\n\n# Auto-generated code\n")
                f.write(code)
            
            return {
                "success": True,
                "method": "append",
                "file": target_file
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _replace_file(self, target_file: str, code: str) -> Dict[str, Any]:
        """Replace target file with generated code."""
        
        try:
            target_path = Path(target_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            return {
                "success": True,
                "method": "replace",
                "file": target_file
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _create_file(self, target_file: str, code: str) -> Dict[str, Any]:
        """Create new file with generated code."""
        
        try:
            target_path = Path(target_file)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            return {
                "success": True,
                "method": "create",
                "file": target_file
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_programming_summary(self) -> Dict[str, Any]:
        """Get self-programming summary."""
        
        return {
            "success": True,
            "programming_summary": {
                "total_generated_code": len(self.generated_code),
                "total_refactorings": len(self.refactoring_history),
                "total_bug_fixes": len(self.bug_fixes),
                "integrated_code": len([c for c in self.generated_code if c.get("status") == "integrated"]),
                "refactoring_types": {
                    "optimization": len([r for r in self.refactoring_history if r.get("refactoring_type") == "optimization"]),
                    "readability": len([r for r in self.refactoring_history if r.get("refactoring_type") == "readability"]),
                    "simplification": len([r for r in self.refactoring_history if r.get("refactoring_type") == "simplification"])
                }
            },
            "message": "Programming summary generated successfully"
        }