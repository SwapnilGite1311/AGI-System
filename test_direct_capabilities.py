"""
Direct Real-World Capabilities Test
Test web agent and business agent directly for form filling and email
"""

import asyncio
import sys
import json
from pathlib import Path

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agents.web_agent import WebAgent
from agents.business_agent import BusinessAgent


class DirectCapabilityTest:
    """Test real-world capabilities directly with agents."""
    
    def __init__(self):
        """Initialize direct capability test."""
        self.config_path = "./config/settings.json"
        self.web_agent = None
        self.business_agent = None
        self.test_results = []
        
    def initialize_agents(self):
        """Initialize agents directly."""
        try:
            print("[INFO] Initializing Web Agent...")
            self.web_agent = WebAgent(self.config_path)
            print("[OK] Web Agent initialized")
            
            print("[INFO] Initializing Business Agent...")
            self.business_agent = BusinessAgent(self.config_path)
            print("[OK] Business Agent initialized")
            
            return True
        except Exception as e:
            print(f"[ERROR] Agent initialization failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_form_filling(self):
        """Test actual form filling capability."""
        print("\n[TEST] Testing Form Filling...")
        print("=" * 60)
        
        try:
            # Test with a real form - using a simple test form
            form_url = "https://httpbin.org/forms/post"  # Simple test form
            
            command = f"navigate to {form_url} and fill the form with name 'ASC Test' and email 'asc@test.com'"
            print(f"[INFO] Command: {command}")
            
            result = asyncio.run(self.web_agent.process(command))
            
            print(f"[RESULT] Form filling result: {result}")
            
            if result and result.get("success"):
                print("[SUCCESS] Form filling test PASSED")
                self.test_results.append({"test": "form_filling", "success": True})
                return True
            else:
                print("[FAIL] Form filling test FAILED")
                self.test_results.append({"test": "form_filling", "success": False, "error": str(result)})
                return False
                
        except Exception as e:
            print(f"[ERROR] Form filling test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            self.test_results.append({"test": "form_filling", "success": False, "error": str(e)})
            return False
    
    def test_email_sending(self):
        """Test actual email sending capability."""
        print("\n[TEST] Testing Email Sending...")
        print("=" * 60)
        
        try:
            # Test sending a dummy email to the specified address
            recipient = "swapnilgite9028@gmail.com"
            command = f"send email to {recipient} with subject 'ASC Test Email' and body 'This is a test email from Autonomous System Controller'"
            print(f"[INFO] Command: {command}")
            print(f"[INFO] Recipient: {recipient}")
            
            result = asyncio.run(self.business_agent.process(command))
            
            print(f"[RESULT] Email sending result: {result}")
            
            if result and result.get("success"):
                print("[SUCCESS] Email sending test PASSED")
                print(f"[INFO] Email should be sent to: {recipient}")
                self.test_results.append({"test": "email_sending", "success": True})
                return True
            else:
                print("[FAIL] Email sending test FAILED")
                print(f"[INFO] Check if email agent is properly configured")
                self.test_results.append({"test": "email_sending", "success": False, "error": str(result)})
                return False
                
        except Exception as e:
            print(f"[ERROR] Email sending test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            self.test_results.append({"test": "email_sending", "success": False, "error": str(e)})
            return False
    
    def test_meeting_scheduling(self):
        """Test actual meeting scheduling capability."""
        print("\n[TEST] Testing Meeting Scheduling...")
        print("=" * 60)
        
        try:
            # Test scheduling a meeting
            command = "schedule a meeting titled 'ASC Test Meeting' for tomorrow at 2pm for 1 hour"
            print(f"[INFO] Command: {command}")
            
            result = asyncio.run(self.business_agent.process(command))
            
            print(f"[RESULT] Meeting scheduling result: {result}")
            
            if result and result.get("success"):
                print("[SUCCESS] Meeting scheduling test PASSED")
                print(f"[INFO] Meeting should be scheduled in your calendar")
                self.test_results.append({"test": "meeting_scheduling", "success": True})
                return True
            else:
                print("[FAIL] Meeting scheduling test FAILED")
                print(f"[INFO] Check if calendar integration is properly configured")
                self.test_results.append({"test": "meeting_scheduling", "success": False, "error": str(result)})
                return False
                
        except Exception as e:
            print(f"[ERROR] Meeting scheduling test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            self.test_results.append({"test": "meeting_scheduling", "success": False, "error": str(e)})
            return False
    
    def test_browser_automation(self):
        """Test browser automation capabilities."""
        print("\n[TEST] Testing Browser Automation...")
        print("=" * 60)
        
        try:
            # Test simple browser automation
            command = "navigate to google.com and search for 'autonomous system controller'"
            print(f"[INFO] Command: {command}")
            
            result = asyncio.run(self.web_agent.process(command))
            
            print(f"[RESULT] Browser automation result: {result}")
            
            if result and result.get("success"):
                print("[SUCCESS] Browser automation test PASSED")
                self.test_results.append({"test": "browser_automation", "success": True})
                return True
            else:
                print("[FAIL] Browser automation test FAILED")
                self.test_results.append({"test": "browser_automation", "success": False, "error": str(result)})
                return False
                
        except Exception as e:
            print(f"[ERROR] Browser automation test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            self.test_results.append({"test": "browser_automation", "success": False, "error": str(e)})
            return False
    
    def generate_real_world_report(self):
        """Generate comprehensive real-world capability report."""
        print("\n[REPORT] REAL-WORLD CAPABILITY TEST REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["success"]])
        
        print(f"\n[SUMMARY] REAL-WORLD CAPABILITY SUMMARY")
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests}")
        print(f"Failed: {total_tests - successful_tests}")
        
        if total_tests > 0:
            print(f"Success Rate: {successful_tests/total_tests*100:.1f}%")
        else:
            print("Success Rate: N/A (no tests completed)")
        
        print(f"\n[DETAILED RESULTS]")
        for test in self.test_results:
            status = "✅ PASSED" if test["success"] else "❌ FAILED"
            print(f"{status} - {test['test']}")
            if not test["success"] and "error" in test:
                print(f"  Error: {test['error']}")
        
        print("\n[CONCLUSION]")
        if successful_tests == total_tests:
            print("All real-world capabilities are working!")
            print("The system can perform actual tasks as requested.")
        else:
            print(f"Some capabilities need attention: {total_tests - successful_tests} tests failed")
            print("Check the agent configurations and integrations.")
        
        print("=" * 60)
        
        return {
            "total_tests": total_tests,
            "successful": successful_tests,
            "failed": total_tests - successful_tests,
            "success_rate": successful_tests/total_tests*100 if total_tests > 0 else 0,
            "details": self.test_results
        }


def main():
    """Run real-world capability tests."""
    print("[START] STARTING REAL-WORLD CAPABILITY TEST")
    print("=" * 60)
    print("This test will perform ACTUAL actions:")
    print("- Fill a real web form")
    print("- Send a real email to swapnilgite9028@gmail.com")
    print("- Schedule a real meeting")
    print("- Perform browser automation")
    print("=" * 60)
    
    tester = DirectCapabilityTest()
    
    # Initialize agents
    if not tester.initialize_agents():
        print("[ERROR] Cannot proceed without agent initialization")
        return
    
    # Run real-world tests
    tester.test_form_filling()
    tester.test_email_sending()
    tester.test_meeting_scheduling()
    tester.test_browser_automation()
    
    # Generate report
    report = tester.generate_real_world_report()
    
    print("\n[DONE] REAL-WORLD CAPABILITY TEST COMPLETE")
    
    return report


if __name__ == "__main__":
    main()