# -*- coding: utf-8 -*-
"""
Qwen3 8B 测试脚本
==================

测试 Ollama + Qwen3 8B 的镜头参数生成功能。

使用方法：
    python test_qwen3.py
"""

import requests
import json

# Ollama API 地址
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"

# 镜头生成的系统提示词
SYSTEM_PROMPT = """你是一个专业的电影摄影 AI 助手。
用户会用自然语言描述想要的镜头，你需要输出 JSON 格式的参数配置。

可用的路径类型 (path.type):
- "orbit": 环绕运动
- "dolly": 推拉运动
- "crane": 升降运动
- "follow": 跟随运动
- "linear": 直线平移

可用的约束类型 (constraint.type):
- "look_at": 始终看向目标
- "free": 自由方向
- "path_tangent": 沿路径方向

可用的修饰器 (modifiers):
- "handheld": 手持晃动感
- "shake": 强烈震动
- "lag": 延迟跟随

输出格式示例：
{
    "shot_name": "Epic Orbit",
    "duration": 6.0,
    "path": {
        "type": "orbit",
        "radius": 4.0,
        "angle": 180,
        "height": {"start": 0.5, "end": 3.0}
    },
    "constraint": {
        "type": "look_at",
        "target": "$SELECTED"
    },
    "modifiers": [
        {"type": "handheld", "intensity": 0.2}
    ],
    "lens": {
        "focal_length": 35
    }
}

只输出 JSON，不要其他解释文字。"""


def test_connection():
    """测试 Ollama 连接"""
    print("=" * 60)
    print("步骤 1: 测试 Ollama 连接")
    print("=" * 60)
    
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]
            print(f"✓ Ollama 运行正常")
            print(f"✓ 已安装模型: {model_names}")
            
            # 检查 qwen3:8b
            if any("qwen3" in m for m in model_names):
                print(f"✓ Qwen3 模型已安装")
                return True
            else:
                print(f"✗ 未找到 Qwen3 模型，请运行: ollama pull qwen3:8b")
                return False
        else:
            print(f"✗ Ollama 响应异常: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到 Ollama")
        print("  请确保 Ollama 正在运行")
        print("  如果刚安装，请重启电脑或运行: ollama serve")
        return False
    except Exception as e:
        print(f"✗ 错误: {e}")
        return False


def test_simple_chat():
    """测试简单对话"""
    print("\n" + "=" * 60)
    print("步骤 2: 测试简单对话")
    print("=" * 60)
    
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {"role": "user", "content": "用一句话介绍你自己"}
                ],
                "stream": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "")
            print(f"✓ 模型响应正常")
            print(f"  回复: {content[:200]}...")
            return True
        else:
            print(f"✗ 请求失败: {response.status_code}")
            print(f"  {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ 错误: {e}")
        return False


def test_shot_generation():
    """测试镜头参数生成"""
    print("\n" + "=" * 60)
    print("步骤 3: 测试镜头参数生成")
    print("=" * 60)
    
    test_prompts = [
        "给我一个环绕角色的史诗镜头，从低角度慢慢升起",
        "紧张的推进特写，3秒",
        "epic orbit shot around the hero",
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n测试 {i}: {prompt}")
        print("-" * 50)
        
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                },
                timeout=120
            )
            
            if response.status_code == 200:
                content = response.json().get("message", {}).get("content", "")
                print(f"原始响应:\n{content[:500]}")
                
                # 尝试解析 JSON
                try:
                    # 清理响应
                    json_str = content.strip()
                    if "```" in json_str:
                        import re
                        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', json_str)
                        if match:
                            json_str = match.group(1)
                    
                    params = json.loads(json_str)
                    print(f"\n✓ JSON 解析成功:")
                    print(json.dumps(params, indent=2, ensure_ascii=False))
                except json.JSONDecodeError as e:
                    print(f"\n⚠ JSON 解析失败: {e}")
                    print("  模型返回的不是纯 JSON，但这是正常的")
            else:
                print(f"✗ 请求失败: {response.status_code}")
                
        except Exception as e:
            print(f"✗ 错误: {e}")
    
    return True


def test_with_client():
    """使用封装的客户端测试"""
    print("\n" + "=" * 60)
    print("步骤 4: 测试封装的客户端")
    print("=" * 60)
    
    try:
        # 尝试导入客户端
        import sys
        sys.path.insert(0, ".")
        
        from omni.anim.drama.toolset.ai import OllamaClient
        
        client = OllamaClient(model="qwen3:8b")
        
        if client.is_available():
            print("✓ OllamaClient 初始化成功")
            
            # 测试生成
            print("\n测试 generate_shot_params()...")
            result = client.generate_shot_params("环绕角色的史诗镜头，低角度升起")
            
            if "error" not in result:
                print("✓ 生成成功:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"⚠ 生成返回错误: {result.get('error')}")
                print("  这可能是 JSON 解析问题，不影响基本功能")
        else:
            print("✗ Ollama 不可用")
            
    except ImportError as e:
        print(f"⚠ 无法导入客户端模块: {e}")
        print("  这不影响直接使用 Ollama API")
    except Exception as e:
        print(f"✗ 错误: {e}")


def main():
    """运行所有测试"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + "  Qwen3 8B + Ollama 测试脚本  ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 测试连接
    if not test_connection():
        print("\n❌ 连接测试失败，请先确保 Ollama 正在运行")
        return
    
    # 测试简单对话
    if not test_simple_chat():
        print("\n❌ 对话测试失败")
        return
    
    # 测试镜头生成
    test_shot_generation()
    
    # 测试客户端
    test_with_client()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("""
下一步:
  1. 如果所有测试通过，说明 Qwen3 8B 已就绪
  2. 可以在插件中使用:
     
     from omni.anim.drama.toolset.ai import OllamaClient
     client = OllamaClient(model="qwen3:8b")
     params = client.generate_shot_params("你的镜头描述")
     
  3. 或者继续生成训练数据:
     cd omni/anim/drama/toolset/ai/training
     python generate_dataset.py --api local --count 100
""")


if __name__ == "__main__":
    main()



