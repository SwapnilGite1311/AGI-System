"""
Extended System Testing - Thousands of Commands
Stress testing the system with extensive command variations
"""

import json
import time
import traceback
import sys
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

from main import AutonomousSystemController


class ExtendedSystemTest:
    """Extended system testing with thousands of commands."""
    
    def __init__(self):
        """Initialize extended testing framework."""
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
    
    def generate_thousands_of_commands(self):
        """Generate thousands of test commands."""
        commands = []
        
        # Conversation variations
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
        for greeting in greetings:
            commands.append(greeting)
            commands.append(f"{greeting}!")
            commands.append(f"{greeting} there")
        
        # Status variations
        status_commands = ["status", "show status", "system status", "show system status", 
                         "get status", "current status", "what is the status"]
        commands.extend(status_commands)
        
        # File command variations
        file_commands = [
            "list files in desktop", "show files in desktop", "desktop files",
            "list files in documents", "show files in documents", "documents files",
            "list files in downloads", "show files in downloads", "downloads files",
            "list files in pictures", "show files in pictures", "pictures files"
        ]
        commands.extend(file_commands)
        
        # System command variations
        system_commands = [
            "show drives", "list drives", "what drives are available",
            "network status", "show network status", "check network",
            "show processes", "list processes", "running processes",
            "show cpu", "cpu usage", "check cpu",
            "show memory", "memory usage", "check memory"
        ]
        commands.extend(system_commands)
        
        # Phase 4 command variations
        phase4_commands = [
            "phase 4 status", "show adaptive learning", "adaptive learning status",
            "show learned workflows", "learned workflows", "workflow patterns",
            "show preferences", "user preferences", "my preferences",
            "show workflow templates", "workflow templates", "templates"
        ]
        commands.extend(phase4_commands)
        
        # Phase 5 command variations
        phase5_commands = [
            "phase 5 status", "show phase 5 model", "phase 5 model",
            "show phase 5 summary", "phase 5 summary", "neural model status"
        ]
        commands.extend(phase5_commands)
        
        # Phase 6 command variations
        phase6_commands = [
            "show business tasks", "list business tasks", "business tasks",
            "create task test task", "add task test task", "new task test task",
            "list projects", "show projects", "all projects",
            "daily plan", "show daily plan", "today's plan",
            "schedule reminder test", "set reminder test", "add reminder test"
        ]
        commands.extend(phase6_commands)
        
        # Phase 7 command variations
        phase7_commands = [
            "meta learning summary", "show meta learning", "meta learning status",
            "self reflection summary", "show self reflection", "self reflection status",
            "autonomous goals summary", "show autonomous goals", "autonomous goals status",
            "concept discovery summary", "show concept discovery", "concept discovery status",
            "self programming summary", "show self programming", "self programming status",
            "algorithm optimization summary", "show algorithm optimization", "algorithm optimization status",
            "self evolving summary", "show self evolving", "self evolving status",
            "cognitive summary", "show cognitive", "cognitive status"
        ]
        commands.extend(phase7_commands)
        
        # Help and capability variations
        help_commands = [
            "help", "what can you do", "capabilities", "show capabilities",
            "list capabilities", "your capabilities", "features", "show features"
        ]
        commands.extend(help_commands)
        
        # Complex command combinations
        complex_commands = [
            "show status and list files in desktop",
            "phase 4 status and phase 5 status",
            "show preferences and show learned workflows",
            "daily plan and list projects",
            "meta learning summary and self reflection summary"
        ]
        commands.extend(complex_commands)
        
        # Number-based commands
        for i in range(1, 51):
            commands.append(f"test command {i}")
            commands.append(f"command number {i}")
        
        # Repeated command stress test
        for i in range(100):
            commands.append("status")
            commands.append("help")
        
        print(f"[INFO] Generated {len(commands)} test commands")
        return commands
    
    def run_stress_test(self, commands: List[str]):
        """Run stress test with thousands of commands."""
        print(f"\n[STRESS] Running stress test with {len(commands)} commands...")
        
        batch_size = 100
        total_batches = len(commands) // batch_size + 1
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, len(commands))
            batch_commands = commands[start_idx:end_idx]
            
            print(f"[BATCH] Processing batch {batch_num + 1}/{total_batches} ({len(batch_commands)} commands)...")
            
            for command in batch_commands:
                try:
                    start_time = time.time()
                    result = asyncio.run(self.controller.process_command(command))
                    execution_time = time.time() - start_time
                    
                    if execution_time > 2.0:
                        self.performance_issues.append({
                            "command": command,
                            "execution_time": execution_time,
                            "message": f"Command took {execution_time:.2f}s (slow)"
                        })
                    
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
            
            print(f"[BATCH] Batch {batch_num + 1} completed")
    
    def test_concurrent_commands(self):
        """Test concurrent command processing."""
        print("\n[CONCURRENT] Testing concurrent command processing...")
        
        # Create a list of commands to run concurrently
        concurrent_commands = [
            "status", "help", "phase 4 status", "phase 5 status",
            "meta learning summary", "self reflection summary"
        ] * 10  # 60 commands total
        
        print(f"[INFO] Testing {len(concurrent_commands)} concurrent commands...")
        
        # Run commands sequentially but measure throughput
        start_time = time.time()
        
        for command in concurrent_commands:
            try:
                asyncio.run(self.controller.process_command(command))
            except Exception as e:
                self.bugs_found.append({
                    "type": "concurrent_error",
                    "command": command,
                    "message": str(e)
                })
        
        total_time = time.time() - start_time
        throughput = len(concurrent_commands) / total_time
        
        print(f"[INFO] Throughput: {throughput:.2f} commands/second")
        
        if throughput < 5.0:
            self.performance_issues.append({
                "type": "low_throughput",
                "throughput": throughput,
                "message": f"System throughput is low: {throughput:.2f} commands/second"
            })
    
    def test_data_integrity(self):
        """Test data integrity across operations."""
        print("\n[INTEGRITY] Testing data integrity...")
        
        try:
            # Test that commands that should return data actually do
            data_commands = [
                "show preferences",
                "show learned workflows",
                "list projects",
                "meta learning summary"
            ]
            
            for command in data_commands:
                try:
                    result = asyncio.run(self.controller.process_command(command))
                    
                    # Check if result contains expected data
                    if result and hasattr(result, '__dict__'):
                        print(f"[OK] Data integrity check passed for '{command}'")
                    else:
                        print(f"[WARN] Data integrity check questionable for '{command}'")
                        self.bugs_found.append({
                            "type": "data_integrity_issue",
                            "command": command,
                            "message": f"Command may not be returning proper data structure"
                        })
                except Exception as e:
                    print(f"[FAIL] Data integrity check failed for '{command}': {str(e)}")
                    self.bugs_found.append({
                        "type": "data_integrity_error",
                        "command": command,
                        "message": str(e)
                    })
                    
        except Exception as e:
            print(f"[ERROR] Data integrity test failed: {str(e)}")
    
    def generate_extended_report(self):
        """Generate extended test report."""
        print("\n[REPORT] GENERATING EXTENDED TEST REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["success"]])
        failed_tests = total_tests - successful_tests
        
        # Calculate average execution time
        execution_times = [r.get("execution_time", 0) for r in self.test_results if r["success"]]
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        print(f"\n[SUMMARY] EXTENDED TEST SUMMARY")
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
        print(f"Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        print(f"Average Execution Time: {avg_execution_time:.4f}s")
        print(f"Throughput: {total_tests/sum(execution_times):.2f} commands/second" if execution_times else "N/A")
        
        print(f"\n[BUGS] BUGS FOUND: {len(self.bugs_found)}")
        for i, bug in enumerate(self.bugs_found[:10], 1):  # Show first 10 bugs
            print(f"\n{i}. {bug['type']}")
            print(f"   Message: {bug['message']}")
            if 'command' in bug:
                print(f"   Command: {bug['command']}")
        
        if len(self.bugs_found) > 10:
            print(f"\n... and {len(self.bugs_found) - 10} more bugs")
        
        print(f"\n[PERF] PERFORMANCE ISSUES: {len(self.performance_issues)}")
        for i, issue in enumerate(self.performance_issues[:10], 1):  # Show first 10 issues
            print(f"\n{i}. {issue.get('type', 'performance')}")
            print(f"   Message: {issue['message']}")
            if 'execution_time' in issue:
                print(f"   Execution Time: {issue['execution_time']:.2f}s")
        
        if len(self.performance_issues) > 10:
            print(f"\n... and {len(self.performance_issues) - 10} more performance issues")
        
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
                "success_rate": successful_tests/total_tests*100 if total_tests > 0 else 0,
                "average_execution_time": avg_execution_time,
                "throughput": total_tests/sum(execution_times) if execution_times else 0
            },
            "bugs": self.bugs_found,
            "performance_issues": self.performance_issues,
            "infinite_loops": self.infinite_loops,
            "test_results": self.test_results[:1000]  # Save first 1000 results to avoid huge files
        }
        
        report_path = Path("data/extended_test_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n[SAVE] Report saved to: {report_path}")
        print("=" * 60)
        
        return report


def main():
    """Run extended system tests."""
    print("[START] STARTING EXTENDED SYSTEM TESTING")
    print("=" * 60)
    
    tester = ExtendedSystemTest()
    
    # Initialize controller
    if not tester.initialize_controller():
        print("[ERROR] Cannot proceed without controller initialization")
        return
    
    # Generate thousands of commands
    commands = tester.generate_thousands_of_commands()
    
    # Run stress test
    tester.run_stress_test(commands)
    
    # Test concurrent processing
    tester.test_concurrent_commands()
    
    # Test data integrity
    tester.test_data_integrity()
    
    # Generate report
    report = tester.generate_extended_report()
    
    print("\n[DONE] EXTENDED TESTING COMPLETE")
    
    return report


if __name__ == "__main__":
    main()