# -*- coding: utf-8 -*-
"""
Prompt Templates - 提示词模板
=============================

管理用于 LLM 调用的提示词模板。

主要功能:
    - get_relight_analysis_prompt: 获取重打光分析提示词
    - get_light_suggestion_prompt: 获取灯光建议提示词
"""

from typing import Optional


class PromptTemplates:
    """
    提示词模板管理类。
    """

    # =========================================================================
    # 灯光操作 JSON Schema
    # =========================================================================
    
    LIGHT_OPERATION_SCHEMA = '''
{
  "version": "1.0",
  "operations": [
    {
      "action": "create" | "modify",
      "light_type": "DistantLight" | "RectLight" | "SphereLight" | "DomeLight" | "CylinderLight" | "DiskLight",
      "name": "light name",
      "parent_path": "/World/Lights",
      "light_path": "/World/Lights/ExistingLight",  // for modify only
      "transform": {
        "translate": [x, y, z],
        "rotate": [rx, ry, rz],
        "scale": [sx, sy, sz]
      },
      "attributes": {
        "intensity": 1000.0,
        "color": [r, g, b],  // 0-1 range
        "temperature": 6500,  // color temperature K
        "exposure": 0.0,
        "radius": 50.0,
        "width": 100.0,
        "height": 100.0,
        "angle": 0.53
      }
    }
  ],
  "reasoning": "Explain your lighting adjustments"
}
'''

    # =========================================================================
    # 重打光分析提示词
    # =========================================================================

    @classmethod
    def get_relight_analysis_prompt(cls, scene_info: str) -> str:
        """
        获取重打光分析的提示词。

        Args:
            scene_info: 场景信息文本

        Returns:
            str: 完整的提示词
        """
        return f'''You are a professional lighting artist and 3D scene lighting expert. Your task is to analyze two images (original render and relit target image) and generate specific USD lighting adjustment commands.

## YOUR GOAL: REPLICATE THE TARGET IMAGE LIGHTING AS CLOSELY AS POSSIBLE

**You must adjust ALL existing lights in the scene to match the target image exactly.**
- Analyze EVERY light listed in the scene info below
- Modify EACH light's color, intensity, and other attributes to match the target
- The goal is to make the Omniverse render look IDENTICAL to the target relit image

## CRITICAL RULES

### Rule 1: DO NOT DELETE LIGHTS
**You must NOT use "delete" action. Only use "create" or "modify" actions.**

### Rule 2: CONTRAST IS KEY
**Match the CONTRAST of the target image, not just colors.**
- If target has DARK shadows: DomeLight intensity must be VERY LOW (10-50)
- DomeLight fills ALL shadows - lower it to get darker shadows
- Use RectLight/SphereLight for localized bright areas
- High contrast = low DomeLight + bright local lights

### Rule 3: DOMELIGHT CONTROLS SHADOW DARKNESS
**DomeLight intensity directly controls how dark your shadows are:**
- High contrast scene (dark shadows): DomeLight intensity 10-30
- Medium contrast: DomeLight intensity 50-200
- Low contrast (flat lighting): DomeLight intensity 500+

### Rule 4: MINIMUM INTENSITY (Safety)
- DomeLight: minimum 10 (can go very low for contrast)
- DistantLight: minimum 1
- RectLight/SphereLight: minimum 10

## Current Scene Lights (YOU MUST MODIFY ALL OF THESE)

{scene_info}

**IMPORTANT: Every light listed above should be included in your output operations!**
- Analyze what each light contributes to the ORIGINAL image
- Determine what color/intensity each light needs to achieve the TARGET image look
- Output a "modify" operation for EVERY light

## Your Task

1. **Analyze the TARGET image carefully**:
   - What is the dominant color/mood? (e.g., magenta + cyan in your example)
   - Where are the bright areas? What color are they?
   - How dark are the shadows? (controls DomeLight intensity)
   - What is the overall contrast level?

2. **Map each existing light to the target**:
   - Which light should become the MAGENTA/PINK light source?
   - Which light should become the CYAN/BLUE light source?
   - What should DomeLight's color and intensity be?

3. **Generate operations for EVERY light**:
   - `modify`: Adjust EACH existing light to match target - OUTPUT ONE FOR EACH LIGHT
   - `create`: Only if target has more light sources than current scene
   - **DO NOT use `delete`**

## Light Types

- **DistantLight**: Parallel/sun light for distant light sources
- **RectLight**: Rectangular area light for soft area lighting - USE FOR BRIGHT COLORED AREAS
- **SphereLight**: Spherical point light for local lighting
- **DomeLight**: Dome/environment light - **CONTROLS SHADOW DARKNESS** - lower intensity = darker shadows
- **DiskLight**: Disk light, similar to spotlight
- **CylinderLight**: Cylindrical light source

## Attributes

- **color**: RGB color, range 0-1 - adjust to match target image mood
- **intensity**: Light intensity - freely adjust to match target brightness
  - Minimum: DomeLight >= 10, DistantLight >= 1, Others >= 10
  - No maximum limit - use whatever value achieves the target look
- **temperature**: Color temperature (Kelvin), warm ~3000K, daylight ~5500K, cold ~7000K+
- **exposure**: Exposure adjustment, typical -2 to 2

## Output Format

Output strictly in this JSON format, no other content:

```json
{cls.LIGHT_OPERATION_SCHEMA}
```

## Important Notes

1. Output JSON only, no explanatory text
2. **NEVER use "delete" action**
3. **ANALYZE THE CONTRAST** - if target has dark shadows, DomeLight must be LOW
4. **DomeLight is your shadow controller** - lower DomeLight = darker shadows
5. Example high-contrast setup: DomeLight intensity 20, RectLight intensity 5000
6. Example low-contrast setup: DomeLight intensity 500, RectLight intensity 1000
7. Provide reasoning in the "reasoning" field

Now analyze these two images and generate light operation JSON:
'''

    # =========================================================================
    # 灯光建议提示词
    # =========================================================================

    @classmethod
    def get_light_suggestion_prompt(cls, scene_info: str, description: str) -> str:
        """
        获取根据描述生成灯光建议的提示词。

        Args:
            scene_info: 场景信息文本
            description: 用户描述的期望效果

        Returns:
            str: 完整的提示词
        """
        return f'''你是一位专业的灯光师。根据用户的描述和场景信息，生成灯光配置建议。

## 场景信息

{scene_info}

## 用户期望效果

{description}

## 输出格式

请输出符合以下格式的 JSON：

```json
{cls.LIGHT_OPERATION_SCHEMA}
```

只输出 JSON，不要有其他文字。
'''

    # =========================================================================
    # 单图分析提示词
    # =========================================================================

    @classmethod
    def get_single_image_analysis_prompt(cls, scene_info: str) -> str:
        """
        获取单张图片分析的提示词（分析目标效果图，推断需要的灯光）。

        Args:
            scene_info: 场景信息文本

        Returns:
            str: 完整的提示词
        """
        return f'''你是一位专业的灯光师和 3D 场景布光专家。请分析这张图片的光照效果，并推断需要的灯光配置。

## 场景信息

{scene_info}

## 你的任务

1. **分析光照**：
   - 判断主光源的方向、强度、颜色
   - 识别是否有填充光
   - 分析阴影特征
   - 判断整体色调氛围

2. **生成灯光配置**：基于分析，生成能够重现这个效果的灯光配置 JSON。

## 输出格式

```json
{cls.LIGHT_OPERATION_SCHEMA}
```

只输出 JSON，不要有其他文字。
'''

    # =========================================================================
    # 自定义提示词模板
    # =========================================================================

    @classmethod
    def build_custom_prompt(
        cls,
        task_description: str,
        scene_info: str,
        additional_context: Optional[str] = None
    ) -> str:
        """
        构建自定义提示词。

        Args:
            task_description: 任务描述
            scene_info: 场景信息
            additional_context: 额外上下文

        Returns:
            str: 完整的提示词
        """
        prompt = f'''你是一位专业的灯光师和 3D 场景布光专家。

## 任务

{task_description}

## 场景信息

{scene_info}
'''

        if additional_context:
            prompt += f'''
## 额外信息

{additional_context}
'''

        prompt += f'''
## 输出格式

请输出符合以下格式的 JSON：

```json
{cls.LIGHT_OPERATION_SCHEMA}
```

只输出 JSON，确保格式正确可解析。
'''

        return prompt


