# -*- coding: utf-8 -*-
"""
LLM Client
==========

Simple LLM API clients for camera shot generation.

Supported:
    - Ollama (local, free)
    - OpenAI (cloud, paid)
    - OpenRouter (cloud, various models)

Usage:
    # Ollama (recommended for testing)
    client = OllamaClient()
    result = client.generate_shot_params("给我一个环绕镜头")
    
    # OpenAI
    client = OpenAIClient(api_key="sk-xxx")
    result = client.generate_shot_params("epic orbit shot")
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

# 尝试导入 requests，如果没有则给出提示
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logging.warning("requests not installed. Run: pip install requests")

# 尝试导入 openai
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# =============================================================================
# System Prompts
# =============================================================================

CAMERA_SHOT_SYSTEM_PROMPT = """You are a professional cinematography AI assistant.
The user will describe a camera shot in natural language.
Output a JSON configuration for a hierarchical camera rig system.

=== CAMERA RIG HIERARCHY ===
The camera rig has 4 layers, each with atomic operations:

Layer 1 - ROOT (Where the rig is placed):
- anchor: { target_prim: "/path/to/object", initial_pos: [x, y, z] }
- transport: { end_offset: [x, y, z], duration: float, easing: "linear|ease_in|ease_out|ease_in_out" }

Layer 2 - ARM (How it moves around target):
- rotate_pivot: { axis: "Y"|"X", start_angle: 0, end_angle: 360, easing: "ease_in_out" }
  (Y = horizontal orbit, X = vertical flip)
- boom: { start_length: 5.0, end_length: 5.0, easing: "ease_in_out" }
  (distance from target, larger = further away)

Layer 3 - HEAD (Where camera looks):
- look_at: { target_prim: "/path", framing_offset: [x, y] }
- roll: { start_angle: 0, end_angle: 0, easing: "ease_in_out" }
  (Dutch angle, negative = tilt left, positive = tilt right)

Layer 4 - LENS & FX:
- lens: { start_focal_length: 35, end_focal_length: 85, easing: "ease_in_out" }
  (24=wide, 50=normal, 85=portrait, 135=telephoto)
- shake: { intensity: 0.1, frequency: 0.5, seed: 0 }
  (intensity: 0=none, 0.1=subtle, 0.5=handheld, 1.0=earthquake)
  (frequency: 0.3=slow/cinematic, 1.0=normal, 3.0=fast/shaky)

=== DISTANCE RULES (CRITICAL!) ===
The user WILL provide object size. You MUST use it to set boom length!

FORMULA: boom.start_length = object_size × 5 (for good product framing)

Examples:
- Object size 1 unit → boom = 5 units, focal_length = 35
- Object size 10 units → boom = 50 units, focal_length = 35
- Object size 100 units → boom = 500 units, focal_length = 35
- Object size 500 units → boom = 2500 units, focal_length = 24

WHY 5x? At 5x distance with 35mm lens, object fills ~30% of frame = good framing!
At 2.5x distance, object fills 80%+ = too close, bad framing!

NEVER use a boom value smaller than object_size × 4!
If the user says "REQUIRED boom.start_length: X", use EXACTLY that value!
For product shots, prefer focal_length 35 (wider) over 50 (too tight).

=== OUTPUT FORMAT ===
{
    "name": "ShotName",
    "duration": 6.0,
    "fps": 24.0,
    "anchor": {
        "target_prim": "$SELECTED",
        "initial_pos": [0, 0, 0]
    },
    "transport": {
        "end_offset": [0, 0, 0],
        "duration": 0,
        "easing": "ease_in_out"
    },
    "rotate_pivot": {
        "axis": "Y",
        "start_angle": 0,
        "end_angle": 360,
        "easing": "ease_in_out"
    },
    "boom": {
        "start_length": 5.0,
        "end_length": 5.0,
        "easing": "ease_in_out"
    },
    "look_at": {
        "target_prim": "",
        "framing_offset": [0, 0]
    },
    "roll": {
        "start_angle": 0,
        "end_angle": 0
    },
    "lens": {
        "start_focal_length": 50,
        "end_focal_length": 50
    },
    "shake": {
        "intensity": 0,
        "frequency": 1.0,
        "seed": 0
    }
}

=== SHOT TYPE EXAMPLES ===

1. Simple 360° orbit:
   rotate_pivot: { axis: "Y", start_angle: 0, end_angle: 360 }
   boom: { start_length: 5.0, end_length: 5.0 }

2. Dolly zoom (Vertigo effect):
   boom: { start_length: 15.0, end_length: 5.0 }
   lens: { start_focal_length: 24, end_focal_length: 85 }

3. Crane up + orbit:
   transport: { end_offset: [0, HEIGHT, 0], duration: 5.0 }
   rotate_pivot: { axis: "Y", start_angle: 0, end_angle: 180 }
   NOTE: HEIGHT should be ~50% of object size for noticeable effect!
   Example: object_size=100 → end_offset=[0, 50, 0]

4. Epic reveal with shake:
   rotate_pivot: { start_angle: -30, end_angle: 30 }
   boom: { start_length: 20, end_length: 8 }
   shake: { intensity: 0.1, frequency: 0.5 }

5. Dutch angle tension shot:
   roll: { start_angle: 0, end_angle: 15 }
   lens: { start_focal_length: 35, end_focal_length: 50 }

IMPORTANT: All movements should be proportional to object size!
The user will provide EXACT values to use. ALWAYS use those values!

CRANE UP (transport.end_offset Y):
- "subtle" = object_size × 0.1
- "slight" = object_size × 0.3
- "moderate" or DEFAULT = object_size × 0.5
- "dramatic" = object_size × 1.0

TRUCK LEFT/RIGHT (transport.end_offset X):
- "small" = object_size × 0.3
- "medium" = object_size × 0.5
- "large" = object_size × 0.8

If user mentions "crane up" without specifying intensity, use MODERATE (50%).
The user will provide exact numbers - USE THEM!

=== FILM VOCABULARY ===
- "epic/heroic" → wide lens (24-35mm), low angle, maybe orbit
- "intimate/close-up" → long lens (85-135mm), shallow DOF
- "tense/uneasy" → Dutch angle (roll 10-20°), subtle shake
- "documentary/natural" → handheld shake (intensity 0.2-0.4)
- "reveal" → crane up + dolly out
- "dramatic push" → dolly in (boom decreases)

Respond ONLY with valid JSON, no other text."""


# =============================================================================
# Base Client
# =============================================================================

class LLMClient(ABC):
    """Abstract base class for LLM clients."""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send a chat message and get response."""
        pass
    
    def generate_shot_params(self, description: str) -> Dict[str, Any]:
        """
        Generate camera shot parameters from natural language description.
        
        Args:
            description: Natural language description of the desired shot
            
        Returns:
            Dict containing shot parameters
        """
        response = self.chat(description, CAMERA_SHOT_SYSTEM_PROMPT)
        
        # Try to parse JSON from response
        try:
            # Clean up response if needed
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            return json.loads(response)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON: {e}")
            self.logger.error(f"Response was: {response[:500]}")
            return {"error": str(e), "raw_response": response}
    
    def refine_shot(self, current_params: Dict, refinement: str) -> Dict[str, Any]:
        """
        Refine existing shot parameters based on user feedback.
        
        Args:
            current_params: Current shot parameters
            refinement: User's refinement request
            
        Returns:
            Updated shot parameters
        """
        prompt = f"""Current camera shot configuration:
{json.dumps(current_params, indent=2)}

User wants to modify: {refinement}

Please output the updated JSON configuration."""
        
        return self.generate_shot_params(prompt)


# =============================================================================
# Ollama Client (Local, Free)
# =============================================================================

class OllamaClient(LLMClient):
    """
    Ollama client for local LLM inference.
    
    Setup:
        1. Install Ollama: https://ollama.com
        2. Run: ollama pull llama3.2
        3. Ollama runs automatically as a service
    
    Usage:
        client = OllamaClient()
        result = client.chat("Hello!")
    """
    
    def __init__(
        self, 
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434"
    ):
        super().__init__()
        self.model = model
        self.base_url = base_url
        
        if not HAS_REQUESTS:
            raise ImportError("requests library required. Install: pip install requests")
    
    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False
    
    def list_models(self) -> list:
        """List available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            self.logger.error(f"Failed to list models: {e}")
        return []
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message to Ollama."""
        if not HAS_REQUESTS:
            return "Error: requests library not installed"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                },
                timeout=120
            )
            
            if response.status_code == 200:
                return response.json().get("message", {}).get("content", "")
            else:
                error = f"Ollama error: {response.status_code} - {response.text}"
                self.logger.error(error)
                return error
                
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Is it running? (ollama serve)"
        except Exception as e:
            return f"Error: {str(e)}"


# =============================================================================
# OpenAI Client
# =============================================================================

class OpenAIClient(LLMClient):
    """
    OpenAI API client.
    
    Setup:
        1. Get API key from https://platform.openai.com
        2. pip install openai
    
    Usage:
        client = OpenAIClient(api_key="sk-xxx")
        result = client.chat("Hello!")
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None
    ):
        super().__init__()
        self.model = model
        
        if not HAS_OPENAI:
            raise ImportError("openai library required. Install: pip install openai")
        
        # 允许从环境变量读取
        import os
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key")
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message to OpenAI."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            error = f"OpenAI error: {str(e)}"
            self.logger.error(error)
            return error


# =============================================================================
# OpenRouter Client (Multiple Models)
# =============================================================================

class OpenRouterClient(LLMClient):
    """
    OpenRouter client - access multiple LLM providers with one API.
    
    Setup:
        1. Get API key from https://openrouter.ai
        2. pip install openai (uses OpenAI SDK)
    
    Free models available:
        - "meta-llama/llama-3.2-3b-instruct:free"
        - "google/gemma-2-9b-it:free"
        - "mistralai/mistral-7b-instruct:free"
    
    Usage:
        client = OpenRouterClient(api_key="sk-or-xxx")
        result = client.chat("Hello!")
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "meta-llama/llama-3.2-3b-instruct:free"
    ):
        super().__init__()
        self.model = model
        
        if not HAS_OPENAI:
            raise ImportError("openai library required. Install: pip install openai")
        
        import os
        api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        
        if not api_key:
            raise ValueError("OpenRouter API key required")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message via OpenRouter."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            error = f"OpenRouter error: {str(e)}"
            self.logger.error(error)
            return error


# =============================================================================
# SiliconFlow Client (免费额度大，国内访问快)
# =============================================================================

class SiliconFlowClient(LLMClient):
    """
    硅基流动 SiliconFlow - 国内免费 LLM API 服务
    
    特点:
        - 每月 2000万 tokens 免费额度
        - 国内访问速度快
        - 支持 Qwen、DeepSeek、GLM 等多种模型
        - 兼容 OpenAI API 格式
    
    Setup:
        1. 访问 https://siliconflow.cn 注册
        2. 获取 API Key
    
    Usage:
        client = SiliconFlowClient(api_key="sk-xxx")
        result = client.chat("你好")
    """
    
    # 可用的免费模型
    FREE_MODELS = [
        "Qwen/Qwen2.5-7B-Instruct",      # 通义千问 7B
        "deepseek-ai/DeepSeek-V2.5",      # DeepSeek
        "THUDM/glm-4-9b-chat",            # 智谱 GLM-4
        "internlm/internlm2_5-7b-chat",   # 书生浦语
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "Qwen/Qwen2.5-7B-Instruct"
    ):
        super().__init__()
        self.model = model
        self.base_url = "https://api.siliconflow.cn/v1"
        
        import os
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "SiliconFlow API key required.\n"
                "Get free key at: https://siliconflow.cn\n"
                "Set SILICONFLOW_API_KEY env var or pass api_key"
            )
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message to SiliconFlow."""
        if not HAS_REQUESTS:
            return "Error: requests library not installed"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2048
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                error = f"SiliconFlow error: {response.status_code} - {response.text}"
                self.logger.error(error)
                return error
                
        except Exception as e:
            return f"Error: {str(e)}"


# =============================================================================
# Groq Client (极速，免费)
# =============================================================================

class GroqClient(LLMClient):
    """
    Groq - 极速免费 LLM API
    
    特点:
        - 推理速度极快（号称最快）
        - 免费使用（有速率限制）
        - 支持 Llama、Mixtral 等模型
    
    Setup:
        1. 访问 https://console.groq.com 注册
        2. 获取 API Key
    
    Usage:
        client = GroqClient(api_key="gsk_xxx")
        result = client.chat("Hello")
    """
    
    FREE_MODELS = [
        "llama-3.1-8b-instant",     # Llama 3.1 8B (推荐)
        "llama-3.1-70b-versatile",  # Llama 3.1 70B
        "mixtral-8x7b-32768",       # Mixtral 8x7B
        "gemma2-9b-it",             # Gemma 2 9B
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instant"
    ):
        super().__init__()
        self.model = model
        self.base_url = "https://api.groq.com/openai/v1"
        
        import os
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Groq API key required.\n"
                "Get free key at: https://console.groq.com\n"
                "Set GROQ_API_KEY env var or pass api_key"
            )
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message to Groq."""
        if not HAS_REQUESTS:
            return "Error: requests library not installed"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2048
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                error = f"Groq error: {response.status_code} - {response.text}"
                self.logger.error(error)
                return error
                
        except Exception as e:
            return f"Error: {str(e)}"


# =============================================================================
# DeepSeek Official Client (国产顶级)
# =============================================================================

class DeepSeekClient(LLMClient):
    """
    DeepSeek 官方 API - 国产顶级模型
    
    特点:
        - 注册送 500万 tokens
        - 推理能力强（数学、代码）
        - 中文支持极好
    
    Setup:
        1. 访问 https://platform.deepseek.com 注册
        2. 获取 API Key
    
    Usage:
        client = DeepSeekClient(api_key="sk-xxx")
        result = client.chat("你好")
    """
    
    MODELS = [
        "deepseek-chat",      # DeepSeek-V3 (推荐)
        "deepseek-reasoner",  # DeepSeek-R1 (推理增强)
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat"
    ):
        super().__init__()
        self.model = model
        self.base_url = "https://api.deepseek.com/v1"
        
        import os
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "DeepSeek API key required.\n"
                "Get free tokens at: https://platform.deepseek.com\n"
                "Set DEEPSEEK_API_KEY env var or pass api_key"
            )
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat message to DeepSeek."""
        if not HAS_REQUESTS:
            return "Error: requests library not installed"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": 2048
                },
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                error = f"DeepSeek error: {response.status_code} - {response.text}"
                self.logger.error(error)
                return error
                
        except Exception as e:
            return f"Error: {str(e)}"


# =============================================================================
# Auto Client (自动选择最佳可用后端)
# =============================================================================

class AutoClient(LLMClient):
    """
    自动客户端 - 自动检测并使用可用的 LLM 后端
    
    优先级:
        1. Ollama (本地)
        2. SiliconFlow (国内云端)
        3. Groq (国际云端)
        4. DeepSeek (国内云端)
    
    Usage:
        client = AutoClient()  # 自动选择可用后端
        result = client.chat("你好")
    """
    
    def __init__(self):
        super().__init__()
        self._backend = None
        self._backend_name = "none"
        self._init_backend()
    
    def _init_backend(self):
        """初始化后端，按优先级尝试"""
        import os
        
        # 1. 尝试 Ollama（本地）
        try:
            client = OllamaClient()
            if client.is_available():
                self._backend = client
                self._backend_name = "Ollama (local)"
                self.logger.info("Using Ollama backend")
                return
        except Exception:
            pass
        
        # 2. 尝试 SiliconFlow
        if os.environ.get("SILICONFLOW_API_KEY"):
            try:
                self._backend = SiliconFlowClient()
                self._backend_name = "SiliconFlow"
                self.logger.info("Using SiliconFlow backend")
                return
            except Exception:
                pass
        
        # 3. 尝试 Groq
        if os.environ.get("GROQ_API_KEY"):
            try:
                self._backend = GroqClient()
                self._backend_name = "Groq"
                self.logger.info("Using Groq backend")
                return
            except Exception:
                pass
        
        # 4. 尝试 DeepSeek
        if os.environ.get("DEEPSEEK_API_KEY"):
            try:
                self._backend = DeepSeekClient()
                self._backend_name = "DeepSeek"
                self.logger.info("Using DeepSeek backend")
                return
            except Exception:
                pass
        
        self.logger.warning("No LLM backend available")
    
    @property
    def backend_name(self) -> str:
        """获取当前后端名称"""
        return self._backend_name
    
    def is_available(self) -> bool:
        """检查是否有可用后端"""
        return self._backend is not None
    
    def chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """发送消息"""
        if not self._backend:
            return "Error: No LLM backend available. Please configure Ollama or API keys."
        return self._backend.chat(prompt, system_prompt)


# =============================================================================
# Quick Test Function
# =============================================================================

def quick_test():
    """Quick test function - run this to verify setup."""
    print("=" * 60)
    print("LLM Client Quick Test")
    print("=" * 60)
    
    # Test Ollama
    print("\n[1] Testing Ollama (local)...")
    try:
        client = OllamaClient()
        if client.is_available():
            models = client.list_models()
            print(f"    ✓ Ollama is running! Models: {models}")
            
            if models:
                print(f"    Testing chat with {client.model}...")
                response = client.chat("Say 'Hello from Ollama!' in one line")
                print(f"    Response: {response[:100]}...")
        else:
            print("    ✗ Ollama not running. Start with: ollama serve")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    # Test OpenAI
    print("\n[2] Testing OpenAI...")
    import os
    if os.environ.get("OPENAI_API_KEY"):
        try:
            client = OpenAIClient()
            response = client.chat("Say 'Hello from OpenAI!' in one line")
            print(f"    ✓ Response: {response[:100]}...")
        except Exception as e:
            print(f"    ✗ Error: {e}")
    else:
        print("    ✗ OPENAI_API_KEY not set")
    
    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    quick_test()

