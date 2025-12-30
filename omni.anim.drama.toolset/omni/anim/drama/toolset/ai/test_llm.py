# -*- coding: utf-8 -*-
"""
LLM Quick Test Script
=====================

Run this script to test LLM integration.

Usage (from command line):
    cd d:/ov/kit-app-template/Omniverse-anim-toolset/omni.anim.drama.toolset
    python -m omni.anim.drama.toolset.ai.test_llm

Or simply:
    python omni/anim/drama/toolset/ai/test_llm.py
"""

import json


def test_ollama():
    """Test with local Ollama."""
    print("\n" + "=" * 60)
    print("Testing Ollama (Local LLM)")
    print("=" * 60)
    
    try:
        from llm_client import OllamaClient
    except ImportError:
        from .llm_client import OllamaClient
    
    client = OllamaClient(model="llama3.2")
    
    # Check if running
    if not client.is_available():
        print("❌ Ollama is not running!")
        print("\nTo fix:")
        print("  1. Install Ollama: https://ollama.com")
        print("  2. Run: ollama pull llama3.2")
        print("  3. Start: ollama serve")
        return False
    
    print("✓ Ollama is running!")
    print(f"✓ Available models: {client.list_models()}")
    
    # Test camera shot generation
    print("\n[Testing camera shot generation...]")
    
    test_prompts = [
        "给我一个环绕角色的史诗感镜头",
        "a dramatic dolly-in shot for a tense conversation",
        "crane up reveal shot showing a vast landscape",
    ]
    
    for prompt in test_prompts[:1]:  # Just test first one
        print(f"\nPrompt: {prompt}")
        print("-" * 40)
        
        result = client.generate_shot_params(prompt)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        else:
            print("✓ Generated parameters:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return True


def test_simple_requests():
    """
    Simplest possible test - just using requests.
    No dependencies on the llm_client module.
    """
    print("\n" + "=" * 60)
    print("Simple Ollama Test (requests only)")
    print("=" * 60)
    
    try:
        import requests
    except ImportError:
        print("❌ requests not installed. Run: pip install requests")
        return False
    
    # Check if Ollama is running
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code != 200:
            print("❌ Ollama not responding")
            return False
    except Exception:
        print("❌ Cannot connect to Ollama at localhost:11434")
        print("\nTo fix:")
        print("  1. Install Ollama: https://ollama.com")
        print("  2. Run: ollama pull llama3.2")
        print("  3. Ollama should auto-start, or run: ollama serve")
        return False
    
    print("✓ Ollama is running!")
    
    # List models
    models = r.json().get("models", [])
    model_names = [m["name"] for m in models]
    print(f"✓ Available models: {model_names}")
    
    if not model_names:
        print("❌ No models installed. Run: ollama pull llama3.2")
        return False
    
    # Use first available model
    model = model_names[0].split(":")[0]  # Remove tag
    print(f"\nUsing model: {model}")
    
    # Simple chat
    print("\n[Sending test message...]")
    
    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "user", "content": "Say hello in one sentence!"}
            ],
            "stream": False
        },
        timeout=60
    )
    
    if response.status_code == 200:
        content = response.json().get("message", {}).get("content", "")
        print(f"✓ Response: {content}")
        return True
    else:
        print(f"❌ Error: {response.status_code}")
        return False


def test_camera_prompt():
    """Test camera shot generation with a specific prompt."""
    print("\n" + "=" * 60)
    print("Camera Shot Generation Test")
    print("=" * 60)
    
    try:
        import requests
    except ImportError:
        print("❌ requests not installed")
        return
    
    SYSTEM_PROMPT = """You are a cinematography AI. Output camera shot params as JSON.
Available path types: linear, orbit, bezier, crane, dolly, follow
Available constraints: free, look_at, path_tangent
Available modifiers: handheld, shake, lag

Example output:
{"shot_name": "orbit_hero", "duration": 5, "path": {"type": "orbit", "radius": 4}, "constraint": {"type": "look_at"}}

Respond with JSON only."""

    user_prompt = "给我一个环绕角色的史诗镜头，从低角度慢慢升起"
    
    print(f"Prompt: {user_prompt}")
    print("-" * 40)
    
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.2",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False
            },
            timeout=120
        )
        
        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "")
            print("Raw response:")
            print(content)
            
            # Try to parse JSON
            try:
                # Clean up
                if "```" in content:
                    import re
                    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                    if match:
                        content = match.group(1)
                
                params = json.loads(content.strip())
                print("\n✓ Parsed JSON:")
                print(json.dumps(params, indent=2, ensure_ascii=False))
            except json.JSONDecodeError as e:
                print(f"\n⚠ Could not parse as JSON: {e}")
        else:
            print(f"❌ Error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("   LLM Integration Test Suite")
    print("=" * 60)
    
    # Start with simplest test
    if test_simple_requests():
        # If that works, test camera generation
        test_camera_prompt()
    
    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()



