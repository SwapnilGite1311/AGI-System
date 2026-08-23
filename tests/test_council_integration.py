"""
Council Integration Test - Verify council can connect to Ollama and use models
"""

import asyncio
import pytest
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.council import LLMCouncil
from core.chairman import Chairman
from agents.system_agent import SystemAgent


def require_ollama():
    """Skip live council tests when the local Ollama server is offline."""
    system = SystemAgent()
    if not system.health_check_ollama(timeout=0.5):
        pytest.skip("Ollama server is not running; skipping live council integration test.")


def test_ollama_connectivity():
    """Test that Ollama is running and accessible"""
    require_ollama()
    print(f"âœ… Ollama is running and healthy")


@pytest.mark.asyncio
async def test_council_initialization():
    """Test that LLMCouncil initializes correctly with config"""
    council = LLMCouncil()
    assert council.council_config is not None
    assert 'chairman' in council.council_config
    assert 'strategist' in council.council_config
    assert 'executor' in council.council_config
    assert 'speed' in council.council_config
    print(f"âœ… Council initialized with {len(council.council_config)} members")


@pytest.mark.asyncio
async def test_chairman_initialization():
    """Test that Chairman initializes correctly"""
    chairman = Chairman()
    assert chairman.model is not None
    assert chairman.ollama is not None
    print(f"âœ… Chairman initialized with model: {chairman.model}")


@pytest.mark.asyncio
async def test_quick_decision():
    """Test quick decision using speed model (fastest)"""
    require_ollama()
    council = LLMCouncil()
    
    result = await council.decide(
        task="What is 2+2?",
        complexity="simple"
    )
    
    assert result is not None
    assert 'member' in result
    assert result['member'] == 'speed'
    assert 'error' not in result or result.get('error') is None
    print(f"âœ… Quick decision succeeded: {result}")


@pytest.mark.asyncio
async def test_strategic_decision():
    """Test strategic decision using multiple models"""
    require_ollama()
    council = LLMCouncil()
    
    result = await council.decide(
        task="How would you fill a login form?",
        complexity="medium"
    )
    
    assert result is not None
    assert 'error' not in result or result.get('error') is None
    print(f"âœ… Strategic decision succeeded")


@pytest.mark.asyncio
async def test_council_stats():
    """Test that council tracks member statistics"""
    require_ollama()
    council = LLMCouncil()
    
    # Make a few decisions
    for i in range(2):
        await council.decide(task=f"Test task {i}", complexity="simple")
    
    # Check stats
    speed_stats = council.member_stats.get('speed', {})
    assert speed_stats.get('calls', 0) >= 2, "Council should track calls"
    print(f"âœ… Council stats tracking works: {council.member_stats}")


@pytest.mark.asyncio
async def test_model_availability():
    """Test that all configured models are available in Ollama"""
    require_ollama()
    from ollama import AsyncClient
    import json
    
    with open('./config/settings.json', 'r') as f:
        config = json.load(f)
    
    client = AsyncClient(host=config['ollama']['host'])
    
    # Get available models
    try:
        models_response = await client.list()
        available_models = {m.model.split(':')[0] for m in models_response.models}
        print(f"Available models: {available_models}")
        
        # Check council models
        for member, config_data in config['llm_council'].items():
            model_name = config_data['model'].split(':')[0]
            assert model_name in available_models, f"Model {model_name} not found in Ollama"
        
        print(f"âœ… All {len(config['llm_council'])} council models are available")
        
    except Exception as e:
        pytest.fail(f"Failed to list models from Ollama: {e}")


def test_low_memory_selects_smaller_models():
    """Low-memory systems should avoid the largest council models by default."""
    council = LLMCouncil.__new__(LLMCouncil)
    council.config = {"llm_council": {"chairman": {"model": "qwen2.5:14b"}, "strategist": {"model": "qwen2.5:7b"}, "executor": {"model": "llama3.1:8b"}, "analyst": {"model": "mistral:7b"}, "vision": {"model": "llava:7b"}, "speed": {"model": "gemma2:2b"}, "backup": {"model": "tinyllama"}}}
    council._get_available_memory_gb = lambda: 7.5

    assert council._select_model_for_member("chairman") == "gemma2:2b"
    assert council._select_model_for_member("strategist") == "gemma2:2b"
    assert council._select_model_for_member("executor") == "gemma2:2b"
    assert council._select_model_for_member("analyst") == "gemma2:2b"
    assert council._select_model_for_member("backup") == "tinyllama"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

