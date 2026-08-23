"""
Comprehensive System Testing Framework
Automated testing of all system components with thousands of commands
"""

import pytest
import json
import time
import traceback
import sys
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Any

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import all agents and components
from main import AutonomousSystemController


class ComprehensiveSystemTest:
    """Comprehensive system testing framework."""
    
    def __init__(self):
        """Initialize testing framework."""
        self.config_path = "./config/settings.json"
        self.controller = None
        self.test_results = []
        self.bugs_found = []
        self.performance_issues = []
        self.infinite_loops = []
        
    def initialize_controller(self):
        """Initialize the main controller."""
        try:
            self.controller = AutonomousSystemController(self.config_path)
            print("[OK] Controller initialized successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Controller initialization failed: {str(e)}")
            self.bugs_found.append({
                "type": "initialization_error",
                "message": str(e),
                "traceback": traceback.format_exc()
            })
            return False
    
    def test_agent_initialization(self):
        """Test all 17 agents can be initialized."""
        print("\n[TEST] Testing Agent Initialization...")
        
        expected_agents = [
            "conversation", "learning", "system", "vision", "file", "web", "business",
            "business_process", "security", "analytics", "advanced_neural",
            "meta_learning", "self_reflection", "autonomous_goals", "concept_discovery",
            "self_programming", "algorithm_optimization", "self_evolving", "cognitive"
        ]
        
        for agent_name in expected_agents:
            try:
                if agent_name in self.controller.agents:
                    print(f"[OK] {agent_name} agent initialized")
                else:
                    print(f"[FAIL] {agent_name} agent NOT initialized")
                    self.bugs_found.append({
                        "type": "missing_agent",
                        "agent": agent_name,
                        "message": f"{agent_name} agent not found in controller"
                    })
            except Exception as e:
                print(f"[ERROR] {agent_name} agent error: {str(e)}")
                self.bugs_found.append({
                    "type": "agent_error",
                    "agent": agent_name,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
    
    def test_basic_commands(self):
        """Test basic commands."""
        print("\n[TEST] Testing Basic Commands...")
        
        basic_commands = [
            "hi",
            "hello",
            "what can you do?",
            "help",
            "status",
            "show system status",
            "list files in desktop",
            "show drives",
            "network status"
        ]
        
        for command in basic_commands:
            try:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                if execution_time > 5.0:
                    self.performance_issues.append({
                        "command": command,
                        "execution_time": execution_time,
                        "message": f"Command took {execution_time:.2f}s (slow)"
                    })
                
                print(f"[OK] Command '{command}' executed in {execution_time:.2f}s")
                self.test_results.append({
                    "command": command,
                    "success": True,
                    "execution_time": execution_time
                })
            except Exception as e:
                print(f"[FAIL] Command '{command}' failed: {str(e)}")
                self.bugs_found.append({
                    "type": "command_error",
                    "command": command,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
                self.test_results.append({
                    "command": command,
                    "success": False,
                    "error": str(e)
                })
    
    def test_phase_commands(self):
        """Test phase-specific commands."""
        print("\n[TEST] Testing Phase Commands...")
        
        phase_commands = [
            # Phase 4
            "phase 4 status",
            "show adaptive learning",
            "show learned workflows",
            "show preferences",
            
            # Phase 5
            "phase 5 status",
            "show phase 5 model",
            
            # Phase 6
            "show business tasks",
            "create task test task",
            "list projects",
            "daily plan",
            
            # Phase 7
            "meta learning summary",
            "self reflection summary",
            "autonomous goals summary",
            "concept discovery summary",
            "self programming summary",
            "algorithm optimization summary",
            "self evolving summary",
            "cognitive summary"
        ]
        
        for command in phase_commands:
            try:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                if execution_time > 5.0:
                    self.performance_issues.append({
                        "command": command,
                        "execution_time": execution_time,
                        "message": f"Command took {execution_time:.2f}s (slow)"
                    })
                
                print(f"[OK] Phase command '{command}' executed in {execution_time:.2f}s")
                self.test_results.append({
                    "command": command,
                    "success": True,
                    "execution_time": execution_time
                })
            except Exception as e:
                print(f"[FAIL] Phase command '{command}' failed: {str(e)}")
                self.bugs_found.append({
                    "type": "phase_command_error",
                    "command": command,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
                self.test_results.append({
                    "command": command,
                    "success": False,
                    "error": str(e)
                })
    
    def test_edge_cases(self):
        """Test edge cases and error conditions."""
        print("\n[TEST] Testing Edge Cases...")
        
        edge_cases = [
            "",  # Empty command
            "   ",  # Whitespace only
            "command that does not exist at all",  # Invalid command
            "x" * 10000,  # Very long command
            "special chars !@#$%^&*()",  # Special characters only
            "command\nwith\nnewlines",  # Newlines in command
            "command 'with quotes'",  # Quotes in command
            "command;with;semicolons",  # Semicolons in command
        ]
        
        for command in edge_cases:
            try:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                print(f"[OK] Edge case '{command[:50]}...' handled in {execution_time:.2f}s")
                self.test_results.append({
                    "command": command[:50] + "...",
                    "success": True,
                    "execution_time": execution_time
                })
            except Exception as e:
                print(f"[FAIL] Edge case '{command[:50]}...' failed: {str(e)}")
                self.bugs_found.append({
                    "type": "edge_case_error",
                    "command": command[:50],
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
                self.test_results.append({
                    "command": command[:50] + "...",
                    "success": False,
                    "error": str(e)
                })
    
    def test_memory_usage(self):
        """Test memory usage during operations."""
        print("\n[TEST] Testing Memory Usage...")
        
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Run multiple commands
            test_commands = [
                "status",
                "show system status",
                "list files in desktop",
                "phase 4 status",
                "phase 5 status",
                "meta learning summary"
            ]
            
            for command in test_commands:
                asyncio.run(self.controller.process_command(command))
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            print(f"[INFO] Memory usage: {initial_memory:.2f}MB -> {final_memory:.2f}MB (Delta {memory_increase:.2f}MB)")
            
            if memory_increase > 100:
                self.performance_issues.append({
                    "type": "memory_leak",
                    "initial_memory": initial_memory,
                    "final_memory": final_memory,
                    "increase": memory_increase,
                    "message": f"Memory increased by {memory_increase:.2f}MB during testing"
                })
            
        except ImportError:
            print("[WARN] psutil not available, skipping memory test")
    
    def test_agent_interactions(self):
        """Test interactions between agents."""
        print("\n[TEST] Testing Agent Interactions...")
        
        interaction_tests = [
            "show preferences",  # Learning agent
            "daily plan",  # Business agent
            "create task test task",  # Business agent
            "meta learning summary",  # Meta-learning agent
            "self reflection summary",  # Self-reflection agent
        ]
        
        for command in interaction_tests:
            try:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                print(f"[OK] Agent interaction '{command}' in {execution_time:.2f}s")
                self.test_results.append({
                    "command": command,
                    "success": True,
                    "execution_time": execution_time
                })
            except Exception as e:
                print(f"[FAIL] Agent interaction '{command}' failed: {str(e)}")
                self.bugs_found.append({
                    "type": "agent_interaction_error",
                    "command": command,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
    
    def test_command_variations(self):
        """Test variations of similar commands."""
        print("\n[TEST] Testing Command Variations...")
        
        command_variations = [
            # Status commands
            "status",
            "show status",
            "system status",
            "show system status",
            
            # File commands
            "list files in desktop",
            "show files in desktop",
            "desktop files",
            
            # Help commands
            "help",
            "what can you do",
            "capabilities",
        ]
        
        for command in command_variations:
            try:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                print(f"[OK] Variation '{command}' in {execution_time:.2f}s")
                self.test_results.append({
                    "command": command,
                    "success": True,
                    "execution_time": execution_time
                })
            except Exception as e:
                print(f"[FAIL] Variation '{command}' failed: {str(e)}")
                self.bugs_found.append({
                    "type": "command_variation_error",
                    "command": command,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                })
    
    def generate_report(self):
        """Generate comprehensive test report."""
        print("\n[REPORT] GENERATING COMPREHENSIVE TEST REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["success"]])
        failed_tests = total_tests - successful_tests
        
        print(f"\n[SUMMARY] TEST SUMMARY")
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
        print(f"Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        print(f"\n[BUGS] BUGS FOUND: {len(self.bugs_found)}")
        for i, bug in enumerate(self.bugs_found, 1):
            print(f"\n{i}. {bug['type']}")
            print(f"   Message: {bug['message']}")
            if 'command' in bug:
                print(f"   Command: {bug['command']}")
            if 'agent' in bug:
                print(f"   Agent: {bug['agent']}")
        
        print(f"\n[PERF] PERFORMANCE ISSUES: {len(self.performance_issues)}")
        for i, issue in enumerate(self.performance_issues, 1):
            print(f"\n{i}. {issue.get('type', 'performance')}")
            print(f"   Message: {issue['message']}")
            if 'execution_time' in issue:
                print(f"   Execution Time: {issue['execution_time']:.2f}s")
        
        print(f"\n[LOOPS] INFINITE LOOPS: {len(self.infinite_loops)}")
        for i, loop in enumerate(self.infinite_loops, 1):
            print(f"\n{i}. {loop['location']}")
            print(f"   Message: {loop['message']}")
        
        # Save report to file
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "successful": successful_tests,
                "failed": failed_tests,
                "success_rate": successful_tests/total_tests*100 if total_tests > 0 else 0
            },
            "bugs": self.bugs_found,
            "performance_issues": self.performance_issues,
            "infinite_loops": self.infinite_loops,
            "test_results": self.test_results
        }
        
        report_path = Path("data/comprehensive_test_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n[SAVE] Report saved to: {report_path}")
        print("=" * 60)
        
        return report


def main():
    """Run comprehensive system tests."""
    print("[START] STARTING COMPREHENSIVE SYSTEM TESTING")
    print("=" * 60)
    
    tester = ComprehensiveSystemTest()
    
    # Initialize controller
    if not tester.initialize_controller():
        print("[ERROR] Cannot proceed without controller initialization")
        return
    
    # Run all tests
    tester.test_agent_initialization()
    tester.test_basic_commands()
    tester.test_phase_commands()
    tester.test_edge_cases()
    tester.test_memory_usage()
    tester.test_agent_interactions()
    tester.test_command_variations()
    
    # Generate report
    report = tester.generate_report()
    
    print("\n[DONE] COMPREHENSIVE TESTING COMPLETE")
    
    return report


if __name__ == "__main__":
    main()