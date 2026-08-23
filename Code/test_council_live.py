#!/usr/bin/env python3
"""
Quick test to verify the LLM Council can connect and use live Ollama models
"""

import asyncio
import json
from core.council import LLMCouncil
from loguru import logger

logger.enable("core")


async def main():
    print("\n" + "="*60)
    print("COUNCIL LIVE TEST - Verifying Ollama Integration")
    print("="*60 + "\n")
    
    # Initialize council
    council = LLMCouncil(config_path="./config/settings.json")
    
    # Show config
    print("Council Configuration:")
    for member, config in council.council_config.items():
        if member != "backup":  # Skip backup for clarity
            print(f"  {member:12} -> {config['model']:20} (role: {config['role']})")
    
    print("\nOllama Host:", council.config['ollama']['host'])
    
    # Test 1: Simple decision (uses speed model - gemma2:2b)
    print("\n" + "-"*60)
    print("TEST 1: Quick Decision (Speed Model - gemma2:2b)")
    print("-"*60)
    try:
        result = await council.decide(
            "What is the capital of France?",
            complexity="simple"
        )
        print(f"[OK] Response received:")
        print(f"   Confidence: {result.get('confidence', 'N/A')}")
        print(f"   Steps count: {len(result.get('steps', []))}")
        if result.get('steps'):
            print(f"   First step: {result['steps'][0]}")
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
    
    # Test 2: Medium complexity (uses strategist - qwen2.5:7b)
    print("\n" + "-"*60)
    print("TEST 2: Strategic Decision (Strategist - qwen2.5:7b)")
    print("-"*60)
    try:
        result = await council.decide(
            "Create a plan to organize my desktop files by type",
            complexity="medium"
        )
        print(f"[OK] Response received:")
        print(f"   Confidence: {result.get('confidence', 'N/A')}")
        print(f"   Steps count: {len(result.get('steps', []))}")
        if result.get('steps'):
            print(f"   First step: {result['steps'][0]}")
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
    
    # Test 3: Complex decision (uses full council)
    print("\n" + "-"*60)
    print("TEST 3: Complex Decision (Full Council)")
    print("-"*60)
    try:
        result = await council.decide(
            "Search for 'python tutorials' on Google and extract the top 3 links",
            complexity="complex"
        )
        print(f"[OK] Response received:")
        print(f"   Strategy: {result.get('strategy', 'N/A')[:80]}...")
        print(f"   Execution: {result.get('execution', 'N/A')[:80]}...")
    except Exception as e:
        print(f"[FAIL] Failed: {e}")
    
    # Show stats
    print("\n" + "-"*60)
    print("Council Stats:")
    print("-"*60)
    for member, stats in council.member_stats.items():
        if stats['calls'] > 0:
            success_rate = (stats['successes'] / stats['calls'] * 100) if stats['calls'] > 0 else 0
            print(f"  {member:12} -> Calls: {stats['calls']}, Success: {success_rate:.0f}%")
    
    print("\n" + "="*60)
    print("[OK] Council Live Test Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
