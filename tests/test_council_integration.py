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

    # Either a usable decision, or an EXPLICIT error - never silent garbage.
    # A 2B model does not always emit valid JSON, and _parse_response now
    # sets an "error" key when it can't parse (previously it returned only
    # "parse_error", so `'error' not in result` passed and process_command's
    # `if "error" in plan` check waved the unparseable output through as a
    # valid empty plan). Asserting "no error" would be asserting that a
    # small local model never malforms output, which is not true and is not
    # what this test is for.
    if result.get('error'):
        assert result.get('raw_response') is not None, "an error must explain itself"
    else:
        assert 'steps' in result or 'action_plan' in result or 'confidence' in result
    print(f"Quick decision returned a well-formed result: {result}")


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
    # Same contract as test_quick_decision: a usable plan, or an explicit
    # self-describing error. Never unparseable output passed off as a plan.
    if result.get('error'):
        assert result.get('raw_response') is not None, "an error must explain itself"
    else:
        assert 'action_plan' in result or 'steps' in result or 'confidence' in result
    print("Strategic decision returned a well-formed result")


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
    
    # utf-8-sig and project-anchored: no encoding argument meant cp1252 on
    # Windows, and the relative path broke when pytest ran from elsewhere.
    config_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
    with open(config_path, 'r', encoding='utf-8-sig') as f:
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


def test_configured_model_is_honoured_and_fallback_chain_covers_failure():
    """The configured model is used as-is; RAM does not silently downgrade it.

    This previously asserted that low available memory swapped every member
    down to gemma2:2b. That speculative downgrading was deliberately removed
    (see _select_model_for_member's docstring): guessing from system RAM
    picked a weaker model even when the real one would have loaded fine,
    and it could not see VRAM at all. Real load failures are handled by
    walking the fallback chain instead, which reacts to what actually
    happened rather than to a guess.
    """
    council = LLMCouncil.__new__(LLMCouncil)
    council.config = {"llm_council": {
        "chairman": {"model": "qwen2.5:14b"}, "strategist": {"model": "qwen2.5:7b"},
        "executor": {"model": "llama3.1:8b"}, "analyst": {"model": "mistral:7b"},
        "vision": {"model": "llava:7b"}, "speed": {"model": "gemma2:2b"},
        "backup": {"model": "tinyllama"},
    }}
    council._get_available_memory_gb = lambda: 7.5

    # Configured model is honoured regardless of reported free memory.
    assert council._select_model_for_member("chairman") == "qwen2.5:14b"
    assert council._select_model_for_member("strategist") == "qwen2.5:7b"
    assert council._select_model_for_member("speed") == "gemma2:2b"
    # "tinyllama" is normalised to the tag Ollama actually expects.
    assert council._select_model_for_member("backup") == "tinyllama:latest"

    # Every primary must degrade to something small if it fails to load.
    for member in ("chairman", "strategist", "executor", "analyst"):
        chain = council._model_candidates(member)
        assert chain[0] == council._select_model_for_member(member)
        assert "tinyllama:latest" in chain, f"{member} has no small-model fallback"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

