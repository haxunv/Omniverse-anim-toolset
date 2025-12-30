# -*- coding: utf-8 -*-
"""
训练数据生成器
==============

使用 LLM API 生成训练数据，用于微调专用的镜头参数生成模型。

生成的数据格式:
    [
        {
            "input": "环绕角色的史诗镜头，从低角度升起",
            "output": {"path": {"type": "orbit"}, "duration": 8, ...}
        },
        ...
    ]

使用方法:
    python generate_dataset.py --api siliconflow --count 1000 --output dataset.json
"""

import json
import random
import argparse
from typing import List, Dict, Any
from pathlib import Path

# 镜头描述模板（用于生成多样化的训练数据）
SHOT_TEMPLATES = {
    "orbit": [
        "环绕{target}的{mood}镜头",
        "围绕{target}旋转的镜头",
        "{mood}的环绕镜头，{modifier}",
        "orbit shot around {target}",
        "{mood} rotating shot around the {target}",
    ],
    "dolly": [
        "推进{target}的{mood}镜头",
        "拉远{target}的镜头",
        "缓慢推向{target}",
        "dolly in towards {target}",
        "{mood} push in shot",
    ],
    "crane": [
        "升起揭示{target}的镜头",
        "从{target}上方下降的镜头",
        "摇臂升起的{mood}镜头",
        "crane up revealing {target}",
        "{mood} crane shot rising above {target}",
    ],
    "follow": [
        "跟随{target}移动的镜头",
        "追踪{target}的{mood}镜头",
        "跟拍{target}",
        "follow shot tracking {target}",
        "{mood} following {target}",
    ],
    "linear": [
        "平移拍摄{target}的镜头",
        "横移镜头展示{target}",
        "从左到右的{mood}平移",
        "pan shot across {target}",
        "{mood} sliding shot",
    ],
}

TARGETS = [
    "角色", "主角", "英雄", "人物", "物体", "场景", "建筑", "车辆",
    "character", "hero", "protagonist", "object", "scene", "building",
]

MOODS = [
    "史诗", "紧张", "温馨", "混乱", "梦幻", "压迫", "轻松", "神秘",
    "epic", "tense", "intimate", "chaotic", "dreamy", "dramatic", "calm",
]

MODIFIERS = [
    "从低角度开始", "慢慢升起", "带有手持感", "平稳移动",
    "快速推进", "缓慢展开", "配合呼吸节奏",
    "starting from low angle", "slowly rising", "with handheld feel",
    "smooth movement", "fast approach", "gentle reveal",
]

DURATIONS = [2, 3, 4, 5, 6, 8, 10, 12]
RADII = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
HEIGHTS = [0.3, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
ANGLES = [90, 120, 180, 270, 360]
FOCAL_LENGTHS = [24, 35, 50, 85, 135]


def generate_random_params(path_type: str) -> Dict[str, Any]:
    """生成随机的镜头参数"""
    params = {
        "shot_name": f"{path_type.title()} Shot",
        "duration": random.choice(DURATIONS),
        "path": {"type": path_type},
        "constraint": {"type": "look_at", "target": "$SELECTED"},
        "modifiers": [],
        "lens": {"focal_length": random.choice(FOCAL_LENGTHS)}
    }
    
    if path_type == "orbit":
        params["path"]["radius"] = random.choice(RADII)
        params["path"]["angle"] = random.choice(ANGLES)
        if random.random() > 0.5:
            params["path"]["height"] = {
                "start": random.choice(HEIGHTS[:3]),
                "end": random.choice(HEIGHTS[3:])
            }
    
    elif path_type == "dolly":
        params["path"]["distance"] = random.choice([-3, -2, -1.5, 2, 3, 4])
    
    elif path_type == "crane":
        params["path"]["height"] = {
            "start": random.choice(HEIGHTS[:3]),
            "end": random.choice(HEIGHTS[3:])
        }
    
    elif path_type == "follow":
        params["path"]["offset"] = random.choice([2, 3, 4, 5])
        params["path"]["height"] = random.choice([1.0, 1.5, 2.0])
    
    # 随机添加修饰器
    if random.random() > 0.6:
        params["modifiers"].append({
            "type": "handheld",
            "intensity": round(random.uniform(0.1, 0.4), 2)
        })
    
    if random.random() > 0.8:
        params["modifiers"].append({
            "type": "shake",
            "intensity": round(random.uniform(0.2, 0.6), 2)
        })
    
    return params


def generate_description(path_type: str, params: Dict) -> str:
    """根据参数生成自然语言描述"""
    template = random.choice(SHOT_TEMPLATES[path_type])
    
    description = template.format(
        target=random.choice(TARGETS),
        mood=random.choice(MOODS),
        modifier=random.choice(MODIFIERS)
    )
    
    # 随机添加时长描述
    if random.random() > 0.5:
        duration = params["duration"]
        if random.random() > 0.5:
            description += f"，{duration}秒"
        else:
            description += f", {duration}s"
    
    # 随机添加角度描述
    if "height" in params.get("path", {}):
        height = params["path"]["height"]
        if isinstance(height, dict) and height.get("start", 1) < 0.5:
            if random.random() > 0.5:
                description = "低角度" + description
            else:
                description = "low angle " + description
    
    return description


def generate_dataset_local(count: int) -> List[Dict]:
    """本地生成数据集（不需要 API）"""
    dataset = []
    path_types = list(SHOT_TEMPLATES.keys())
    
    for i in range(count):
        path_type = random.choice(path_types)
        params = generate_random_params(path_type)
        description = generate_description(path_type, params)
        
        dataset.append({
            "input": description,
            "output": params
        })
        
        if (i + 1) % 100 == 0:
            print(f"Generated {i + 1}/{count} samples...")
    
    return dataset


def generate_dataset_with_llm(count: int, api_key: str, api_type: str = "siliconflow") -> List[Dict]:
    """使用 LLM 生成更高质量的数据集"""
    try:
        import requests
    except ImportError:
        print("请安装 requests: pip install requests")
        return []
    
    # API 配置
    api_configs = {
        "siliconflow": {
            "url": "https://api.siliconflow.cn/v1/chat/completions",
            "model": "Qwen/Qwen2.5-7B-Instruct"
        },
        "deepseek": {
            "url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat"
        }
    }
    
    config = api_configs.get(api_type, api_configs["siliconflow"])
    
    system_prompt = """你是一个电影摄影数据生成助手。
请生成10条不同的镜头描述和对应的JSON参数。

输出格式（JSON数组）:
[
    {
        "input": "环绕角色的史诗镜头",
        "output": {
            "shot_name": "Orbit Shot",
            "duration": 6,
            "path": {"type": "orbit", "radius": 4, "angle": 180},
            "constraint": {"type": "look_at", "target": "$SELECTED"},
            "modifiers": [{"type": "handheld", "intensity": 0.2}],
            "lens": {"focal_length": 35}
        }
    },
    ...
]

要求:
1. 描述要多样化（中英文混合）
2. 参数要合理
3. path.type 可以是: orbit, dolly, crane, follow, linear
4. 每条描述都要独特"""

    dataset = []
    batches = count // 10
    
    for batch in range(batches):
        try:
            response = requests.post(
                config["url"],
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config["model"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请生成第 {batch + 1} 批数据（10条），确保与之前的不重复。主题提示：{random.choice(MOODS)} {random.choice(TARGETS)}"}
                    ],
                    "max_tokens": 4096
                },
                timeout=60
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # 尝试解析 JSON
                try:
                    # 提取 JSON 部分
                    if "```" in content:
                        import re
                        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                        if match:
                            content = match.group(1)
                    
                    batch_data = json.loads(content.strip())
                    if isinstance(batch_data, list):
                        dataset.extend(batch_data)
                        print(f"Batch {batch + 1}/{batches}: Generated {len(batch_data)} samples")
                except json.JSONDecodeError:
                    print(f"Batch {batch + 1}: Failed to parse JSON")
            else:
                print(f"Batch {batch + 1}: API error {response.status_code}")
                
        except Exception as e:
            print(f"Batch {batch + 1}: Error - {e}")
    
    return dataset


def save_dataset(dataset: List[Dict], output_path: str):
    """保存数据集"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(dataset)} samples to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="生成镜头参数训练数据")
    parser.add_argument("--api", type=str, default="local",
                        choices=["local", "siliconflow", "deepseek"],
                        help="数据生成方式")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API Key（使用云端生成时需要）")
    parser.add_argument("--count", type=int, default=1000,
                        help="生成样本数量")
    parser.add_argument("--output", type=str, default="dataset.json",
                        help="输出文件路径")
    
    args = parser.parse_args()
    
    print(f"生成 {args.count} 条训练数据...")
    print(f"生成方式: {args.api}")
    
    if args.api == "local":
        dataset = generate_dataset_local(args.count)
    else:
        if not args.api_key:
            import os
            args.api_key = os.environ.get(f"{args.api.upper()}_API_KEY")
        
        if not args.api_key:
            print(f"请提供 API Key (--api-key 或设置 {args.api.upper()}_API_KEY 环境变量)")
            return
        
        dataset = generate_dataset_with_llm(args.count, args.api_key, args.api)
    
    save_dataset(dataset, args.output)
    
    # 显示几条样本
    print("\n示例数据:")
    for sample in dataset[:3]:
        print(f"  输入: {sample['input']}")
        print(f"  输出: {json.dumps(sample['output'], ensure_ascii=False)[:100]}...")
        print()


if __name__ == "__main__":
    main()



