# -*- coding: utf-8 -*-
"""
模型微调脚本
============

使用 LoRA 微调 Qwen2.5-0.5B 模型，专门用于镜头参数生成。

依赖安装:
    pip install torch transformers peft datasets accelerate bitsandbytes

使用方法:
    python train_model.py --dataset dataset.json --output ./camera_shot_model

训练完成后:
    - 模型保存在 ./camera_shot_model
    - 可以使用 export_onnx.py 导出为 ONNX 格式
"""

import json
import argparse
from pathlib import Path

def check_dependencies():
    """检查依赖"""
    missing = []
    
    try:
        import torch
    except ImportError:
        missing.append("torch")
    
    try:
        import transformers
    except ImportError:
        missing.append("transformers")
    
    try:
        import peft
    except ImportError:
        missing.append("peft")
    
    try:
        import datasets
    except ImportError:
        missing.append("datasets")
    
    if missing:
        print("缺少依赖，请安装:")
        print(f"  pip install {' '.join(missing)}")
        return False
    
    return True


def load_dataset(path: str):
    """加载数据集"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 转换为训练格式
    formatted_data = []
    for item in data:
        text = f"### 输入:\n{item['input']}\n\n### 输出:\n{json.dumps(item['output'], ensure_ascii=False)}"
        formatted_data.append({"text": text})
    
    return formatted_data


def train(
    dataset_path: str,
    output_dir: str,
    base_model: str = "Qwen/Qwen2.5-0.5B-Instruct",
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
):
    """
    训练模型
    
    Args:
        dataset_path: 数据集路径
        output_dir: 输出目录
        base_model: 基座模型
        epochs: 训练轮数
        batch_size: 批次大小
        learning_rate: 学习率
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
    """
    import torch
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import Dataset
    
    print(f"基座模型: {base_model}")
    print(f"数据集: {dataset_path}")
    print(f"输出目录: {output_dir}")
    
    # 加载数据
    print("\n加载数据集...")
    data = load_dataset(dataset_path)
    dataset = Dataset.from_list(data)
    print(f"  样本数: {len(dataset)}")
    
    # 加载分词器
    print("\n加载分词器...")
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # 分词
    def tokenize(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=512,
            padding="max_length",
        )
    
    print("分词处理...")
    tokenized_dataset = dataset.map(tokenize, batched=True, remove_columns=["text"])
    
    # 划分训练/验证集
    split = tokenized_dataset.train_test_split(test_size=0.1)
    train_dataset = split["train"]
    eval_dataset = split["test"]
    
    # 加载模型
    print("\n加载模型...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    
    # 配置 LoRA
    print("\n配置 LoRA...")
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    # 训练参数
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_steps=100,
        logging_steps=10,
        save_steps=500,
        eval_strategy="steps",
        eval_steps=100,
        save_total_limit=3,
        fp16=True,
        report_to="none",
    )
    
    # 数据整理器
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )
    
    # 训练器
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
    )
    
    # 开始训练
    print("\n开始训练...")
    print("=" * 50)
    trainer.train()
    
    # 保存模型
    print("\n保存模型...")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    
    print(f"\n训练完成！模型保存在: {output_dir}")
    print("\n下一步:")
    print(f"  1. 合并 LoRA: python merge_lora.py --model {output_dir}")
    print(f"  2. 导出 ONNX: python export_onnx.py --model {output_dir}_merged")


def main():
    parser = argparse.ArgumentParser(description="微调镜头参数生成模型")
    parser.add_argument("--dataset", type=str, required=True,
                        help="训练数据集路径 (JSON)")
    parser.add_argument("--output", type=str, default="./camera_shot_model",
                        help="模型输出目录")
    parser.add_argument("--base-model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct",
                        help="基座模型")
    parser.add_argument("--epochs", type=int, default=3,
                        help="训练轮数")
    parser.add_argument("--batch-size", type=int, default=4,
                        help="批次大小")
    parser.add_argument("--lr", type=float, default=2e-4,
                        help="学习率")
    
    args = parser.parse_args()
    
    if not check_dependencies():
        return
    
    train(
        dataset_path=args.dataset,
        output_dir=args.output,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
    )


if __name__ == "__main__":
    main()



