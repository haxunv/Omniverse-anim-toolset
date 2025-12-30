# 🎬 训练你自己的镜头参数生成模型

## 概述

通过微调小型语言模型，创建一个专门用于生成镜头参数的 AI 模型。

**最终效果**：
- 模型大小：~300MB
- 推理速度：毫秒级
- 完全离线：可嵌入插件分发

## 训练流程

```
第一步              第二步              第三步              第四步
生成数据     →     微调模型     →     合并导出     →     嵌入插件
(1000条)          (几小时)          (ONNX格式)        (发布)
```

## 环境准备

### 硬件要求

| 配置 | 最低要求 | 推荐配置 |
|------|----------|----------|
| GPU | GTX 1060 6GB | RTX 3060 12GB+ |
| 内存 | 16GB | 32GB |
| 硬盘 | 20GB 空闲 | SSD 50GB |

### 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 安装 PyTorch（根据你的 CUDA 版本）
# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 安装训练依赖
pip install transformers peft datasets accelerate bitsandbytes
```

## 第一步：生成训练数据

### 方式 A：本地生成（快速，不需要 API）

```bash
cd omni/anim/drama/toolset/ai/training
python generate_dataset.py --api local --count 1000 --output dataset.json
```

### 方式 B：使用 LLM 生成（质量更高）

```bash
# 使用硅基流动 API
set SILICONFLOW_API_KEY=你的Key
python generate_dataset.py --api siliconflow --count 1000 --output dataset.json

# 或使用 DeepSeek API
set DEEPSEEK_API_KEY=你的Key
python generate_dataset.py --api deepseek --count 1000 --output dataset.json
```

生成的数据格式：
```json
[
    {
        "input": "环绕角色的史诗镜头，从低角度升起",
        "output": {
            "shot_name": "Orbit Shot",
            "duration": 8,
            "path": {"type": "orbit", "radius": 4, "height": {"start": 0.3, "end": 3}},
            "constraint": {"type": "look_at"},
            "modifiers": [{"type": "handheld", "intensity": 0.2}]
        }
    }
]
```

## 第二步：微调模型

```bash
python train_model.py \
    --dataset dataset.json \
    --output ./camera_shot_model \
    --epochs 3 \
    --batch-size 4
```

### 训练参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| --base-model | Qwen/Qwen2.5-0.5B-Instruct | 基座模型 |
| --epochs | 3 | 训练轮数 |
| --batch-size | 4 | 批次大小（显存不够就调小） |
| --lr | 2e-4 | 学习率 |

### 预计训练时间

| 数据量 | RTX 3060 | RTX 4090 |
|--------|----------|----------|
| 1000条 | ~1小时 | ~15分钟 |
| 5000条 | ~5小时 | ~1小时 |

## 第三步：测试模型

```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# 加载模型
base_model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
model = PeftModel.from_pretrained(base_model, "./camera_shot_model")
tokenizer = AutoTokenizer.from_pretrained("./camera_shot_model")

# 测试
prompt = "### 输入:\n环绕角色的史诗镜头\n\n### 输出:\n"
inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=256)
print(tokenizer.decode(outputs[0]))
```

## 第四步：导出和部署

### 合并 LoRA 权重

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM

base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")
model = PeftModel.from_pretrained(base, "./camera_shot_model")
merged = model.merge_and_unload()
merged.save_pretrained("./camera_shot_model_merged")
```

### 量化（可选，减小体积）

```python
# 使用 GPTQ 或 AWQ 量化
# 可将模型从 1GB 压缩到 ~300MB
```

### 导出 ONNX（可选）

```python
# 导出为 ONNX 格式，用于跨平台部署
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("./camera_shot_model_merged")
model.export("camera_shot.onnx")
```

## 在插件中使用

训练好的模型可以通过以下方式在插件中使用：

```python
from omni.anim.drama.toolset.ai import LocalModelClient

# 使用本地训练的模型
client = LocalModelClient(model_path="./camera_shot_model_merged")
params = client.generate_shot_params("环绕镜头")
```

## 常见问题

### Q: 显存不够怎么办？

1. 减小 batch_size（改为 1 或 2）
2. 使用更小的基座模型（如 Qwen2.5-0.5B）
3. 启用梯度检查点（gradient checkpointing）

### Q: 训练效果不好怎么办？

1. 增加训练数据量（至少 1000 条）
2. 使用 LLM 生成更高质量的数据
3. 增加训练轮数（epochs）
4. 检查数据格式是否正确

### Q: 如何提高推理速度？

1. 使用量化（INT4/INT8）
2. 导出为 ONNX 格式
3. 使用 llama.cpp 部署（需要转换格式）

## 文件说明

```
training/
├── generate_dataset.py   # 生成训练数据
├── train_model.py        # 微调模型
├── README.md             # 本文档
└── dataset.json          # 生成的数据（训练后产生）
```



