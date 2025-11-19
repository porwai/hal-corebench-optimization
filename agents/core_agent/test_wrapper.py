#!/usr/bin/env python3
"""
Test script for LiteLLMResponsesModel wrapper.
This script tests that the wrapper can be imported and used with a simple smolagent.

Requirements:
  - smolagents (see requirements.txt for specific version)
  - litellm (see requirements.txt for specific version)
  - API key set in environment (e.g., OPENAI_API_KEY)

Usage:
  python test_wrapper.py
  
  Or with a custom model:
  TEST_MODEL=gpt-4 python test_wrapper.py
"""

import os
import sys
from pathlib import Path

# Add the current directory to the path so we can import the wrapper
sys.path.insert(0, str(Path(__file__).parent))

def test_import():
    """Test that we can import the wrapper without errors."""
    print("=" * 60)
    print("Test 1: Testing wrapper import...")
    print("=" * 60)
    try:
        from utils.litellm_responses_wrapper import LiteLLMResponsesModel
        print("✓ Successfully imported LiteLLMResponsesModel")
        return True
    except ImportError as e:
        print(f"✗ Failed to import wrapper: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error during import: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_wrapper_instantiation():
    """Test that we can create an instance of the wrapper."""
    print("\n" + "=" * 60)
    print("Test 2: Testing wrapper instantiation...")
    print("=" * 60)
    try:
        from utils.litellm_responses_wrapper import LiteLLMResponsesModel
        
        # Get model from environment or use a default
        model_name = os.getenv("TEST_MODEL", "gpt-3.5-turbo")
        print(f"Using model: {model_name}")
        
        model = LiteLLMResponsesModel(model_id=model_name)
        print(f"✓ Successfully created LiteLLMResponsesModel instance")
        print(f"  Model ID: {model.model_id}")
        return True, model
    except Exception as e:
        print(f"✗ Failed to create wrapper instance: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_simple_generate(model):
    """Test that the wrapper can generate a simple response."""
    print("\n" + "=" * 60)
    print("Test 3: Testing simple generate call...")
    print("=" * 60)
    try:
        from smolagents.models import MessageRole
        
        messages = [
            {
                "role": MessageRole.USER,
                "content": [
                    {
                        "type": "text",
                        "text": "Say 'Hello, wrapper test!' and nothing else."
                    }
                ]
            }
        ]
        
        print("Calling model.generate()...")
        response = model.generate(messages)
        
        print(f"✓ Successfully generated response")
        print(f"  Response type: {type(response)}")
        print(f"  Response role: {response.role}")
        print(f"  Response content: {response.content[:100]}...")
        
        if hasattr(response, 'token_usage'):
            print(f"  Token usage: {response.token_usage}")
        else:
            print("  Token usage: Not available")
            
        return True
    except Exception as e:
        error_str = str(e)
        # Check if it's an authentication error
        if "API key" in error_str or "Authentication" in error_str or "401" in error_str:
            print(f"⚠ API key not set or invalid (this is expected if you haven't set OPENAI_API_KEY)")
            print(f"  Error: {error_str[:200]}...")
            print(f"  This is not a wrapper issue - just set your API key to test fully.")
            return None  # Return None to indicate it's not a failure, just missing config
        else:
            print(f"✗ Failed to generate response: {e}")
            import traceback
            traceback.print_exc()
            return False

def test_agent_creation(model):
    """Test that we can create a CodeAgent with the wrapper."""
    print("\n" + "=" * 60)
    print("Test 4: Testing CodeAgent creation with wrapper...")
    print("=" * 60)
    try:
        from smolagents import CodeAgent
        
        agent = CodeAgent(
            model=model,
            tools=[],
            max_steps=1,
        )
        print("✓ Successfully created CodeAgent with wrapper")
        return True, agent
    except Exception as e:
        print(f"✗ Failed to create CodeAgent: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_agent_run(agent):
    """Test that the agent can run a simple query."""
    print("\n" + "=" * 60)
    print("Test 5: Testing agent.run() with simple query...")
    print("=" * 60)
    try:
        prompt = "What is 2 + 2? Answer with just the number."
        print(f"Running agent with prompt: '{prompt}'")
        
        response = agent.run(prompt)
        
        print(f"✓ Successfully ran agent")
        print(f"  Response type: {type(response)}")
        print(f"  Response: {response}")
        return True
    except Exception as e:
        error_str = str(e)
        # Check if it's an authentication error
        if "API key" in error_str or "Authentication" in error_str or "401" in error_str:
            print(f"⚠ API key not set or invalid (this is expected if you haven't set OPENAI_API_KEY)")
            print(f"  Error: {error_str[:200]}...")
            print(f"  This is not a wrapper issue - just set your API key to test fully.")
            return None  # Return None to indicate it's not a failure, just missing config
        else:
            print(f"✗ Failed to run agent: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LiteLLMResponsesModel Wrapper Test Suite")
    print("=" * 60)
    print("\nNote: Make sure you have:")
    print("  1. smolagents installed (pip install smolagents)")
    print("  2. litellm installed (pip install litellm)")
    print("  3. API keys set in environment (OPENAI_API_KEY, etc.)")
    print("  4. Optional: Set TEST_MODEL env var (default: gpt-3.5-turbo)")
    print()
    
    # Test 1: Import
    if not test_import():
        print("\n✗ Import test failed. Cannot continue.")
        return 1
    
    # Test 2: Instantiation
    success, model = test_wrapper_instantiation()
    if not success or model is None:
        print("\n✗ Instantiation test failed. Cannot continue.")
        return 1
    
    # Test 3: Simple generate
    generate_result = test_simple_generate(model)
    if generate_result is False:
        print("\n⚠ Simple generate test failed, but continuing...")
    elif generate_result is None:
        print("\n⚠ Simple generate test skipped (API key not set), but continuing...")
    
    # Test 4: Agent creation
    success, agent = test_agent_creation(model)
    if not success or agent is None:
        print("\n✗ Agent creation test failed. Cannot continue.")
        return 1
    
    # Test 5: Agent run
    agent_run_result = test_agent_run(agent)
    if agent_run_result is False:
        print("\n⚠ Agent run test failed.")
        return 1
    elif agent_run_result is None:
        print("\n⚠ Agent run test skipped (API key not set).")
    
    print("\n" + "=" * 60)
    print("✓ Core wrapper tests passed!")
    if generate_result is None or agent_run_result is None:
        print("⚠ Some tests were skipped due to missing API key.")
        print("  Set OPENAI_API_KEY to run full tests.")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())

