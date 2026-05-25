# -*- coding: utf-8 -*-
"""
Tool Registry - 工具注册器
==========================

提供全局工具注册与元数据管理：

- ``@tool`` 装饰器：把任意 Python 函数注册成 LLM 可调用工具
- ``ToolPermission`` 枚举：read_only / mutate / destructive
- ``ToolDef``：工具元数据（名字、描述、参数 schema、权限、tag）
- ``ToolRegistry``：全局单例，维护所有已注册工具

工具 schema 规则：
    - 自动根据函数类型注解 + docstring 生成 JSON Schema（OpenAI tools 格式）
    - 也允许显式传入 ``parameters_schema`` 覆盖自动生成结果

Schema 生成策略：
    - int/float/str/bool 基本类型 → 对应 JSON 类型
    - Optional[T] → type: T + not required
    - list/List[T] → array
    - dict/Dict → object
    - 其它复杂类型 → 退化为 string 并在描述中说明
"""

from __future__ import annotations

import enum
import inspect
import threading
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin, get_type_hints,
)


# =============================================================================
# 权限等级
# =============================================================================

class ToolPermission(str, enum.Enum):
    """
    工具权限等级：

    - READ_ONLY: 纯查询，不修改 Stage / 文件系统 / 外部资源
    - MUTATE: 修改 Stage（创建/修改 prim、属性、layer 等）
    - DESTRUCTIVE: 不可逆修改（删除 prim、删除文件等），默认需用户解锁
    """
    READ_ONLY = "read_only"
    MUTATE = "mutate"
    DESTRUCTIVE = "destructive"


# =============================================================================
# ToolDef
# =============================================================================

@dataclass
class ToolDef:
    """
    工具定义。

    Attributes:
        name: 工具名（必须匹配 ``^[a-zA-Z_][a-zA-Z0-9_-]{2,63}$``，和 Kimi/OpenAI 规范一致）
        description: 工具描述（会给 LLM 看）
        fn: 真正执行的 Python 函数
        parameters_schema: JSON Schema（OpenAI tools 格式 parameters 字段）
        permission: 权限等级
        category: 分类（例如 ``lighting`` / ``scene`` / ``render``）
        tags: 额外标签（供 Supervisor 路由使用）
        verify_with: 该工具执行成功后建议调用的"验证类"工具名列表。
            例如 ``modify_light`` 修改完应该用 ``get_light_info`` 读回校验。
            AgentNode 在 MUTATE 工具成功后会把这个 hint 注入到 ToolMessage 给 LLM。
        phase_hint: 工具典型出现在哪个 phase（用于 UI 标注，不做硬性约束）：
            ``plan`` / ``gather`` / ``act`` / ``verify``
    """
    name: str
    description: str
    fn: Callable[..., Any]
    parameters_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    permission: ToolPermission = ToolPermission.READ_ONLY
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    verify_with: List[str] = field(default_factory=list)
    phase_hint: str = ""

    # ----- OpenAI tools 格式 -----
    def to_openai_tool(self) -> Dict[str, Any]:
        """
        输出 OpenAI/Kimi ``tools`` 字段期望的格式。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    # ----- Gemini function_declarations 格式 -----
    def to_gemini_function(self) -> Dict[str, Any]:
        """
        输出 Gemini ``function_declarations`` 期望的格式。

        注意：Gemini 不接受某些 JSON Schema 关键字（如 ``additionalProperties``），
        这里做一次 sanitize。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": _sanitize_schema_for_gemini(self.parameters_schema),
        }


# =============================================================================
# ToolRegistry
# =============================================================================

class ToolRegistry:
    """
    全局工具注册器（进程单例）。
    """

    _instance_lock = threading.Lock()
    _instance: Optional["ToolRegistry"] = None

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDef] = {}

    # ---------- 单例 ----------

    @classmethod
    def instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------- 注册与查询 ----------

    def register(self, tool_def: ToolDef) -> None:
        """
        注册一个工具（同名覆盖）。
        """
        _validate_tool_name(tool_def.name)
        self._tools[tool_def.name] = tool_def

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def clear(self) -> None:
        self._tools.clear()

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def all_tools(self) -> List[ToolDef]:
        return list(self._tools.values())

    def tools_by_category(self, category: str) -> List[ToolDef]:
        return [t for t in self._tools.values() if t.category == category]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# =============================================================================
# @tool 装饰器
# =============================================================================

def tool(
    name: Optional[str] = None,
    description: str = "",
    permission: ToolPermission = ToolPermission.READ_ONLY,
    category: str = "general",
    tags: Optional[List[str]] = None,
    parameters_schema: Optional[Dict[str, Any]] = None,
    verify_with: Optional[List[str]] = None,
    phase_hint: str = "",
    register: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    装饰器：把 Python 函数注册成 LLM 工具。

    Args:
        name: 工具名，默认取函数名
        description: 工具描述（建议显式提供，LLM 会据此决定何时使用）
        permission: 权限等级
        category: 分类（lighting/scene/render/asset/geometry 等）
        tags: 额外标签
        parameters_schema: 显式指定 JSON Schema；为 None 时自动从签名 + docstring 生成
        verify_with: 成功执行后建议调用的验证工具名列表（仅 MUTATE/DESTRUCTIVE 有意义）
        phase_hint: 该工具典型属于哪个 phase（plan/gather/act/verify），仅作 UI 标注
        register: 是否立即注册到全局 Registry

    用法示例::

        @tool(
            description="Create a new light",
            permission=ToolPermission.MUTATE,
            category="lighting",
            verify_with=["get_light_info"],
        )
        def create_light(light_type: str, name: str, intensity: float = 1000.0) -> dict:
            ...
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        desc = description or (fn.__doc__ or "").strip().split("\n\n")[0].strip() or tool_name

        schema = parameters_schema or _generate_schema_from_signature(fn)

        tool_def = ToolDef(
            name=tool_name,
            description=desc,
            fn=fn,
            parameters_schema=schema,
            permission=permission,
            category=category,
            tags=list(tags or []),
            verify_with=list(verify_with or []),
            phase_hint=phase_hint,
        )

        setattr(fn, "__tool_def__", tool_def)

        if register:
            ToolRegistry.instance().register(tool_def)

        return fn

    return decorator


# =============================================================================
# Schema 生成
# =============================================================================

_PRIMITIVE_TYPE_MAP: Dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    type(None): "null",
}


def _generate_schema_from_signature(fn: Callable[..., Any]) -> Dict[str, Any]:
    """
    从函数签名与 docstring 生成 JSON Schema（OpenAI tools 格式 parameters 字段）。
    """
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    param_docs = _parse_param_docs(fn.__doc__ or "")

    for pname, param in sig.parameters.items():
        if pname in ("self", "cls"):
            continue
        # *args / **kwargs 忽略
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annot = hints.get(pname, param.annotation)
        prop_schema = _annotation_to_schema(annot)

        # 加上 description
        if pname in param_docs:
            prop_schema["description"] = param_docs[pname]

        properties[pname] = prop_schema

        if param.default is inspect.Parameter.empty:
            required.append(pname)

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _annotation_to_schema(annot: Any) -> Dict[str, Any]:
    """把 Python 类型注解转成 JSON Schema 片段。"""
    # 未注解 → 当字符串
    if annot is inspect.Parameter.empty or annot is None:
        return {"type": "string"}

    # 基本类型
    if annot in _PRIMITIVE_TYPE_MAP:
        t = _PRIMITIVE_TYPE_MAP[annot]
        if t == "null":
            return {"type": "string"}
        return {"type": t}

    origin = get_origin(annot)
    args = get_args(annot)

    # Optional[T] / Union[T, None]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _annotation_to_schema(non_none[0])
        # Union[A, B, ...] 退化为 anyOf
        return {"anyOf": [_annotation_to_schema(a) for a in non_none] or [{"type": "string"}]}

    # list / List[T] / tuple
    if origin in (list, List, tuple):
        items_schema: Dict[str, Any] = {"type": "string"}
        if args:
            items_schema = _annotation_to_schema(args[0])
        return {"type": "array", "items": items_schema}

    # dict / Dict[K, V]
    if origin in (dict, Dict):
        return {"type": "object"}

    # 兜底
    return {"type": "string"}


_PARAM_DOC_PATTERNS = (
    # Google 风格：    pname: description
    # reStructuredText :param pname: description
    # 我们做一个宽松匹配
)


def _parse_param_docs(docstring: str) -> Dict[str, str]:
    """
    从 docstring 中尽力抽取 ``param_name: description`` 风格的参数说明。

    仅用于帮助 LLM 理解参数，失败无伤大雅。
    """
    if not docstring:
        return {}

    result: Dict[str, str] = {}
    lines = docstring.splitlines()
    in_args_block = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        # Google 风格 Args / Parameters 块
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args_block = True
            continue
        if stripped.endswith(":") and stripped.lower().split(":")[0] in (
            "returns", "return", "raises", "yields", "note", "notes", "example", "examples"
        ):
            in_args_block = False
            continue

        # reST 风格 :param xxx: desc
        if stripped.startswith(":param "):
            try:
                head, desc = stripped[len(":param "):].split(":", 1)
                result[head.strip()] = desc.strip()
            except ValueError:
                pass
            continue

        if in_args_block and ":" in stripped:
            head, _, desc = stripped.partition(":")
            head = head.strip().split(" ")[0]  # 去掉类型标注
            if head and head.replace("_", "").isalnum():
                result[head] = desc.strip()

    return result


# =============================================================================
# Schema sanitize
# =============================================================================

def _sanitize_schema_for_gemini(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gemini function declarations 对 JSON Schema 的支持比 OpenAI 严格，
    这里移除 ``additionalProperties`` / ``anyOf`` 等 Gemini 不支持的关键字（退化处理）。
    """
    if not isinstance(schema, dict):
        return schema

    STRIP_KEYS = {"additionalProperties", "$schema", "$ref", "definitions", "default"}
    result: Dict[str, Any] = {}

    for k, v in schema.items():
        if k in STRIP_KEYS:
            continue
        if k == "anyOf" and isinstance(v, list) and v:
            # 退化为第一个分支
            return _sanitize_schema_for_gemini(v[0])
        if isinstance(v, dict):
            result[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            result[k] = [_sanitize_schema_for_gemini(x) if isinstance(x, dict) else x for x in v]
        else:
            result[k] = v

    return result


# =============================================================================
# 校验
# =============================================================================

import re as _re

_TOOL_NAME_RE = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]{2,63}$")


def _validate_tool_name(name: str) -> None:
    if not _TOOL_NAME_RE.match(name):
        raise ValueError(
            f"Invalid tool name: {name!r}. "
            f"Must match ^[a-zA-Z_][a-zA-Z0-9_-]{{2,63}}$ (OpenAI/Kimi spec)."
        )
