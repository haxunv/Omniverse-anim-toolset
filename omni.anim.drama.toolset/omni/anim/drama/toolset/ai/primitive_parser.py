# -*- coding: utf-8 -*-
"""
Primitive Parser - 灯光原语解析器
==================================

解析 LLM 返回的灯光操作 JSON。

主要功能:
    - parse_response: 解析 LLM 响应
    - validate_operations: 验证操作列表
    - extract_json: 从文本中提取 JSON
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple

from ..core.stage_utils import safe_log


class LightPrimitiveParser:
    """
    Light operation primitive parser.
    """

    # Supported light types
    VALID_LIGHT_TYPES = [
        "DistantLight",
        "RectLight",
        "SphereLight",
        "DomeLight",
        "CylinderLight",
        "DiskLight",
    ]

    # Supported action types
    VALID_ACTIONS = ["create", "modify", "delete"]

    # =========================================================================
    # Safety Settings
    # =========================================================================
    
    # Whether to allow delete operations
    ALLOW_DELETE = False
    
    # Minimum intensity thresholds by light type
    # Only minimum limits, no maximum constraints
    MIN_INTENSITY = {
        "default": 10.0,         # Default minimum intensity
        "DomeLight": 10.0,       # Environment light - allow very dim for night
        "DistantLight": 1.0,     # Sun/moon light - can be very dim for moonlight
        "RectLight": 10.0,       # Area light
        "SphereLight": 10.0,     # Point light
        "DiskLight": 10.0,
        "CylinderLight": 10.0,
    }
    
    # Maximum intensity (to prevent blown out scenes)
    MAX_INTENSITY = 100000.0
    
    # Minimum color brightness (0.0 to 1.0)
    # Set to 0 to allow very dark colors for night scenes
    MIN_COLOR_BRIGHTNESS = 0.0

    # =========================================================================
    # 主解析方法
    # =========================================================================

    @classmethod
    def parse_response(cls, response_text: str) -> Dict[str, Any]:
        """
        解析 LLM 响应文本。

        Args:
            response_text: LLM 返回的原始文本

        Returns:
            Dict: 解析结果，包含:
                - success: 是否成功
                - operations: 操作列表
                - reasoning: 推理说明
                - raw_json: 原始 JSON
                - error: 错误信息（如果有）
        """
        result = {
            "success": False,
            "operations": [],
            "reasoning": "",
            "raw_json": None,
            "error": None
        }

        # 提取 JSON
        json_str = cls.extract_json(response_text)
        if not json_str:
            result["error"] = "No JSON found in response"
            return result

        # 解析 JSON
        try:
            parsed = json.loads(json_str)
            result["raw_json"] = parsed
        except json.JSONDecodeError as e:
            result["error"] = f"JSON parse error: {e}"
            # 尝试修复常见的 JSON 错误
            fixed_json = cls._try_fix_json(json_str)
            if fixed_json:
                try:
                    parsed = json.loads(fixed_json)
                    result["raw_json"] = parsed
                except Exception:
                    return result
            else:
                return result

        # 提取操作列表
        operations = parsed.get("operations", [])
        if not isinstance(operations, list):
            result["error"] = "operations is not a list"
            return result

        # Validate and clean operations
        valid_operations = []
        blocked_count = 0
        for op in operations:
            is_valid, cleaned_op, error = cls.validate_operation(op)
            if is_valid:
                valid_operations.append(cleaned_op)
            else:
                if "Delete operation is disabled" in str(error):
                    blocked_count += 1
                    safe_log(f"[PrimitiveParser] Blocked delete: {op.get('light_path', 'unknown')}")
                else:
                    safe_log(f"[PrimitiveParser] Invalid operation: {error}")
        
        if blocked_count > 0:
            safe_log(f"[PrimitiveParser] {blocked_count} delete operation(s) blocked for safety")

        result["operations"] = valid_operations
        result["reasoning"] = parsed.get("reasoning", "")
        result["success"] = len(valid_operations) > 0

        return result

    # =========================================================================
    # JSON 提取
    # =========================================================================

    @classmethod
    def extract_json(cls, text: str) -> Optional[str]:
        """
        从文本中提取 JSON 字符串。

        Args:
            text: 包含 JSON 的文本

        Returns:
            str: 提取的 JSON 字符串
        """
        if not text:
            return None

        # 方法1: 尝试从 markdown 代码块提取
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # ```json ... ```
            r'```\s*([\s\S]*?)\s*```',       # ``` ... ```
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            for match in matches:
                if cls._looks_like_json(match):
                    return match.strip()

        # 方法2: 尝试直接找 JSON 对象
        # 找到第一个 { 和最后一个 } 之间的内容
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_candidate = text[first_brace:last_brace + 1]
            if cls._looks_like_json(json_candidate):
                return json_candidate

        # 方法3: 整个文本可能就是 JSON
        if cls._looks_like_json(text):
            return text.strip()

        return None

    @classmethod
    def _looks_like_json(cls, text: str) -> bool:
        """检查文本是否像 JSON。"""
        text = text.strip()
        if not text:
            return False
        
        # 必须以 { 开头，以 } 结尾
        if not (text.startswith('{') and text.endswith('}')):
            return False
        
        # 应该包含 operations 或其他关键字段
        return 'operations' in text or 'action' in text

    @classmethod
    def _try_fix_json(cls, json_str: str) -> Optional[str]:
        """尝试修复常见的 JSON 错误。"""
        if not json_str:
            return None

        fixed = json_str

        # 修复尾随逗号
        fixed = re.sub(r',\s*}', '}', fixed)
        fixed = re.sub(r',\s*]', ']', fixed)

        # 修复单引号
        # 这个比较危险，只在没有双引号的情况下尝试
        if '"' not in fixed and "'" in fixed:
            fixed = fixed.replace("'", '"')

        # 尝试解析
        try:
            json.loads(fixed)
            return fixed
        except Exception:
            pass

        return None

    # =========================================================================
    # 操作验证
    # =========================================================================

    @classmethod
    def validate_operation(cls, op: Dict, light_type_hint: str = "") -> Tuple[bool, Dict, Optional[str]]:
        """
        Validate a single operation.

        Args:
            op: Operation dict
            light_type_hint: Hint for light type (for intensity validation)

        Returns:
            Tuple[bool, Dict, Optional[str]]: (is_valid, cleaned_op, error_message)
        """
        if not isinstance(op, dict):
            return False, {}, "Operation is not a dict"

        action = op.get("action", "").lower()
        if action not in cls.VALID_ACTIONS:
            return False, {}, f"Invalid action: {action}"

        # Safety check: block delete operations if not allowed
        if action == "delete" and not cls.ALLOW_DELETE:
            return False, {}, "Delete operation is disabled for safety"

        cleaned = {"action": action}

        # Validate based on action type
        if action == "create":
            # Must have light type
            light_type = op.get("light_type", "")
            if light_type not in cls.VALID_LIGHT_TYPES:
                return False, {}, f"Invalid light_type: {light_type}"
            
            cleaned["light_type"] = light_type
            cleaned["name"] = op.get("name", "NewLight")
            cleaned["parent_path"] = op.get("parent_path", "/World/Lights")

            # Optional transform
            if "transform" in op:
                cleaned["transform"] = cls._validate_transform(op["transform"])

            # Optional attributes (with safety limits)
            if "attributes" in op:
                cleaned["attributes"] = cls._validate_attributes(op["attributes"], light_type)

        elif action == "modify":
            # Must have light path
            light_path = op.get("light_path", "")
            if not light_path:
                return False, {}, "modify action requires light_path"
            
            cleaned["light_path"] = light_path

            # Try to determine light type from path
            inferred_type = cls._infer_light_type_from_path(light_path)

            # Optional transform and attributes
            if "transform" in op:
                cleaned["transform"] = cls._validate_transform(op["transform"])
            if "attributes" in op:
                cleaned["attributes"] = cls._validate_attributes(op["attributes"], inferred_type)

            # Need at least one modification
            if "transform" not in cleaned and "attributes" not in cleaned:
                return False, {}, "modify action requires transform or attributes"

        elif action == "delete":
            # Must have light path
            light_path = op.get("light_path", "")
            if not light_path:
                return False, {}, "delete action requires light_path"
            
            cleaned["light_path"] = light_path

        return True, cleaned, None

    @classmethod
    def _infer_light_type_from_path(cls, path: str) -> str:
        """Infer light type from path name."""
        path_lower = path.lower()
        for light_type in cls.VALID_LIGHT_TYPES:
            if light_type.lower() in path_lower:
                return light_type
        return ""

    @classmethod
    def _validate_transform(cls, transform: Dict) -> Dict:
        """验证并清理 transform 数据。"""
        result = {}

        if "translate" in transform:
            t = transform["translate"]
            if isinstance(t, (list, tuple)) and len(t) >= 3:
                result["translate"] = [float(t[0]), float(t[1]), float(t[2])]

        if "rotate" in transform:
            r = transform["rotate"]
            if isinstance(r, (list, tuple)) and len(r) >= 3:
                result["rotate"] = [float(r[0]), float(r[1]), float(r[2])]

        if "scale" in transform:
            s = transform["scale"]
            if isinstance(s, (list, tuple)) and len(s) >= 3:
                result["scale"] = [float(s[0]), float(s[1]), float(s[2])]

        return result

    @classmethod
    def _validate_attributes(cls, attributes: Dict, light_type: str = "") -> Dict:
        """Validate and clean attributes data with safety limits."""
        result = {}
        
        # Numeric attributes
        numeric_attrs = [
            "intensity", "temperature", "exposure",
            "radius", "width", "height", "angle", "length"
        ]
        
        for attr in numeric_attrs:
            if attr in attributes:
                try:
                    value = float(attributes[attr])
                    
                    # Apply intensity safety limits
                    if attr == "intensity":
                        min_intensity = cls.MIN_INTENSITY.get(
                            light_type, 
                            cls.MIN_INTENSITY["default"]
                        )
                        original_value = value
                        value = max(min_intensity, min(cls.MAX_INTENSITY, value))
                        if value != original_value:
                            from ..core.stage_utils import safe_log
                            safe_log(f"[Safety] Intensity clamped: {original_value} -> {value} (min: {min_intensity})")
                    
                    result[attr] = value
                except (ValueError, TypeError):
                    pass

        # Color attribute
        if "color" in attributes:
            c = attributes["color"]
            if isinstance(c, (list, tuple)) and len(c) >= 3:
                r = max(0.0, min(1.0, float(c[0])))
                g = max(0.0, min(1.0, float(c[1])))
                b = max(0.0, min(1.0, float(c[2])))
                
                # Only apply brightness boost if MIN_COLOR_BRIGHTNESS > 0
                if cls.MIN_COLOR_BRIGHTNESS > 0:
                    brightness = (r + g + b) / 3.0
                    if brightness < cls.MIN_COLOR_BRIGHTNESS and brightness > 0:
                        scale = cls.MIN_COLOR_BRIGHTNESS / brightness
                        r = min(1.0, r * scale)
                        g = min(1.0, g * scale)
                        b = min(1.0, b * scale)
                        from ..core.stage_utils import safe_log
                        safe_log(f"[Safety] Color brightness boosted: {brightness:.2f} -> {cls.MIN_COLOR_BRIGHTNESS}")
                
                result["color"] = [r, g, b]

        return result

    # =========================================================================
    # 操作摘要
    # =========================================================================

    @classmethod
    def get_operations_summary(cls, operations: List[Dict]) -> str:
        """
        Get text summary of operations list.

        Args:
            operations: Operations list

        Returns:
            str: Summary text
        """
        if not operations:
            return "No light operations"

        lines = [f"Total {len(operations)} light operations:"]
        
        for i, op in enumerate(operations, 1):
            action = op.get("action", "unknown")
            
            if action == "create":
                light_type = op.get("light_type", "Unknown")
                name = op.get("name", "Unknown")
                lines.append(f"  {i}. Create {light_type}: {name}")
                
                if "attributes" in op:
                    attrs = op["attributes"]
                    if "intensity" in attrs:
                        lines.append(f"      Intensity: {attrs['intensity']}")
                    if "color" in attrs:
                        lines.append(f"      Color: {attrs['color']}")

            elif action == "modify":
                light_path = op.get("light_path", "Unknown")
                lines.append(f"  {i}. Modify: {light_path}")
                
                if "attributes" in op:
                    attrs = op["attributes"]
                    changes = []
                    if "intensity" in attrs:
                        changes.append(f"intensity->{attrs['intensity']}")
                    if "color" in attrs:
                        changes.append(f"color->{attrs['color']}")
                    if changes:
                        lines.append(f"      Changes: {', '.join(changes)}")

            elif action == "delete":
                light_path = op.get("light_path", "Unknown")
                lines.append(f"  {i}. Delete: {light_path}")

        return "\n".join(lines)

