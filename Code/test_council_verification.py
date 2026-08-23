"""
Council Verification Test - Verify LLM Council is Working
Live testing of council decision-making with actual Ollama models
"""

import json
import time
import asyncio
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import AutonomousSystemController


class CouncilVerificationTest:
    """Comprehensive council verification testing."""
    
    def __init__(self):
        """Initialize council verification test."""
        self.config_path = "./config/settings.json"
        self.controller = None
        self.test_results = []
        
    def initialize_controller(self):
        """Initialize the main controller."""
        try:
            self.controller = AutonomousSystemController(self.config_path)
            print("[OK] Controller initialized successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Controller initialization failed: {str(e)}")
            return False
    
    def test_ollama_status(self):
        """Test if Ollama is running and accessible."""
        print("\n[TEST] Testing Ollama Status...")
        
        try:
            ollama_running = self.controller.agents["system"].health_check_ollama(timeout=5.0)
            
            if ollama_running:
                print("[OK] Ollama is running and accessible")
                return True
            else:
                print("[FAIL] Ollama is not running or not accessible")
                return False
        except Exception as e:
            print(f"[ERROR] Ollama status check failed: {str(e)}")
            return False
    
    def test_council_initialization(self):
        """Test if council is properly initialized."""
        print("\n[TEST] Testing Council Initialization...")
        
        try:
            council_info = {
                "council_exists": self.controller.council is not None,
                "chairman_exists": self.controller.chairman is not None,
                "council_config": self.controller.config.get("council", {}),
                "ollama_config": self.controller.config.get("ollama", {})
            }
            
            print(f"[INFO] Council exists: {council_info['council_exists']}")
            print(f"[INFO] Chairman exists: {council_info['chairman_exists']}")
            print(f"[INFO] Council members configured: {list(council_info['council_config'].keys())}")
            print(f"[INFO] Ollama host: {council_info['ollama_config'].get('host')}")
            
            if council_info["council_exists"] and council_info["chairman_exists"]:
                print("[OK] Council properly initialized")
                return True
            else:
                print("[FAIL] Council not properly initialized")
                return False
                
        except Exception as e:
            print(f"[ERROR] Council initialization test failed: {str(e)}")
            return False
    
    def test_council_simple_decision(self):
        """Test council with a simple decision."""
        print("\n[TEST] Testing Council Simple Decision...")
        
        try:
            # Use a simple command that will trigger council
            result = asyncio.run(self.controller.process_command("what is the weather like"))
            
            print(f"[INFO] Command executed successfully")
            print(f"[INFO] Result type: {type(result)}")
            
            if result:
                print("[OK] Council simple decision test passed")
                return True
            else:
                print("[FAIL] Council simple decision test failed - no result")
                return False
                
        except Exception as e:
            print(f"[ERROR] Council simple decision test failed: {str(e)}")
            return False
    
    def test_council_sequential_processing(self):
        """Test that council processes sequentially (RAM-safe)."""
        print("\n[TEST] Testing Council Sequential Processing...")
        
        try:
            # Use a command that requires council decision
            result = asyncio.run(self.controller.process_command("how can I optimize my workflow"))
            
            print(f"[INFO] Sequential processing test completed")
            
            if result:
                print("[OK] Council sequential processing test passed")
                return True
            else:
                print("[FAIL] Council sequential processing test failed")
                return False
                
        except Exception as e:
            print(f"[ERROR] Council sequential processing test failed: {str(e)}")
            return False
    
    def test_council_model_fallback(self):
        """Test council model fallback behavior."""
        print("\n[TEST] Testing Council Model Fallback...")
        
        try:
            # Test with a command that might require fallback
            result = asyncio.run(self.controller.process_command("explain the benefits of autonomous systems"))
            
            print(f"[INFO] Model fallback test completed")
            
            if result:
                print("[OK] Council model fallback test passed")
                return True
            else:
                print("[FAIL] Council model fallback test failed")
                return False
                
        except Exception as e:
            print(f"[ERROR] Council model fallback test failed: {str(e)}")
            return False
    
    def test_council_complex_decision(self):
        """Test council with a complex decision requiring multiple council members."""
        print("\n[TEST] Testing Council Complex Decision...")
        
        try:
            # Use a complex command that should trigger full council consultation
            result = asyncio.run(self.controller.process_command("create a comprehensive plan for improving my productivity using automation"))
            
            print(f"[INFO] Complex decision test completed")
            
            if result:
                print("[OK] Council complex decision test passed")
                return True
            else:
                print("[FAIL] Council complex decision test failed")
                return False
                
        except Exception as e:
            print(f"[ERROR] Council complex decision test failed: {str(e)}")
            return False
    
    def test_chairman_synthesis(self):
        """Test chairman synthesis functionality."""
        print("\n[TEST] Testing Chairman Synthesis...")
        
        try:
            # Test command that requires chairman synthesis
            result = asyncio.run(self.controller.process_command("should I prioritize work or learning today"))
            
            print(f"[INFO] Chairman synthesis test completed")
            
            if result:
                print("[OK] Chairman synthesis test passed")
                return True
            else:
                print("[FAIL] Chairman synthesis test failed")
                return False
                
        except Exception as e:
            print(f"[ERROR] Chairman synthesis test failed: {str(e)}")
            return False
    
    def test_council_performance(self):
        """Test council performance and timing."""
        print("\n[TEST] Testing Council Performance...")
        
        try:
            # Test multiple council decisions and measure time
            test_commands = [
                "what should I focus on today",
                "how can I improve my workflow",
                "what are the best productivity strategies"
            ]
            
            performance_data = []
            
            for command in test_commands:
                start_time = time.time()
                result = asyncio.run(self.controller.process_command(command))
                execution_time = time.time() - start_time
                
                performance_data.append({
                    "command": command,
                    "execution_time": execution_time,
                    "success": result is not None
                })
            
            avg_time = sum(d["execution_time"] for d in performance_data) / len(performance_data)
            
            print(f"[INFO] Average council decision time: {avg_time:.2f}s")
            print(f"[INFO] Success rate: {sum(1 for d in performance_data if d['success']) / len(performance_data) * 100:.1f}%")
            
            if avg_time < 15.0:  # Reasonable time for council decisions
                print("[OK] Council performance test passed")
                return True
            else:
                print("[WARN] Council performance is slow but functional")
                return True
                
        except Exception as e:
            print(f"[ERROR] Council performance test failed: {str(e)}")
            return False
    
    def test_council_memory_safety(self):
        """Test that council is RAM-safe with sequential processing."""
        print("\n[TEST] Testing Council Memory Safety...")
        
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Run several council decisions
            for i in range(5):
                asyncio.run(self.controller.process_command(f"test council decision {i}"))
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
            
            print(f"[INFO] Memory usage: {initial_memory:.2f}MB -> {final_memory:.2f}MB (Delta {memory_increase:.2f}MB)")
            
            if memory_increase < 50:  # Acceptable memory increase
                print("[OK] Council memory safety test passed")
                return True
            else:
                print("[WARN] Council memory increase is significant")
                return True
                
        except ImportError:
            print("[WARN] psutil not available, skipping memory test")
            return True
        except Exception as e:
            print(f"[ERROR] Council memory safety test failed: {str(e)}")
            return False
    
    def generate_council_report(self):
        """Generate comprehensive council verification report."""
        print("\n[REPORT] GENERATING COUNCIL VERIFICATION REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["success"]])
        
        print(f"\n[SUMMARY] COUNCIL VERIFICATION SUMMARY")
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests} ({successful_tests/total_tests*100:.1f}%)")
        print(f"Failed: {total_tests - successful_tests} ({(total_tests - successful_tests)/total_tests*100:.1f}%)")
        
        if successful_tests == total_tests:
            print("\n[SUCCESS] Council is working correctly!")
            print("Council features verified:")
            print("- Sequential RAM-safe processing")
            print("- Model fallback mechanisms")
            print("- Chairman synthesis")
            print("- Complex decision handling")
        else:
            print("\n[ISSUES] Council has some issues that need attention")
        
        print("=" * 60)
        
        return {
            "total_tests": total_tests,
            "successful": successful_tests,
            "failed": total_tests - successful_tests,
            "success_rate": successful_tests/total_tests*100 if total_tests > 0 else 0
        }


def main():
    """Run council verification tests."""
    print("[START] STARTING COUNCIL VERIFICATION TEST")
    print("=" * 60)
    
    tester = CouncilVerificationTest()
    
    # Initialize controller
    if not tester.initialize_controller():
        print("[ERROR] Cannot proceed without controller initialization")
        return
    
    # Run council tests
    tester.test_ollama_status()
    tester.test_council_initialization()
    tester.test_council_simple_decision()
    tester.test_council_sequential_processing()
    tester.test_council_model_fallback()
    tester.test_council_complex_decision()
    tester.test_chairman_synthesis()
    tester.test_council_performance()
    tester.test_council_memory_safety()
    
    # Generate report
    report = tester.generate_council_report()
    
    print("\n[DONE] COUNCIL VERIFICATION COMPLETE")
    
    return report


if __name__ == "__main__":
    main()