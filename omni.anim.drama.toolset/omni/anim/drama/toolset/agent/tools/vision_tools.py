# -*- coding: utf-8 -*-
"""
Vision Tools - reference image -> structured SceneGraph
=======================================================

The anime agent's text-only chat backend cannot ``see`` images. This module
fills that gap by exposing a single READ_ONLY tool, ``describe_reference_image``,
that POSTs the image to a vision-capable LLM provider and returns a fixed-shape
SceneGraph JSON.

The output schema is consumed by:

- ``search_usd_assets``  -> ``subjects[*].search_queries``
- ``pick_best_asset``    -> per-subject picks
- ``propose_layout``     -> grid-based xforms from ``rough_position`` /
                            ``rough_scale`` / ``facing``
- ``create_camera_for_view`` -> framing & FOV
- ``create_light``       -> key light direction / temperature

Provider selection (carb settings + env fallback):

  /exts/omni.anim.drama.toolset/agent/vision/provider     gemini|openai_compat|nvidia_nim
  /exts/omni.anim.drama.toolset/agent/vision/model        e.g. gemini-2.0-flash, gpt-4o, etc.
  /exts/omni.anim.drama.toolset/agent/vision/api_key
  /exts/omni.anim.drama.toolset/agent/vision/base_url     optional override
  /exts/omni.anim.drama.toolset/agent/vision/timeout      seconds, default 90

  env: VISION_API_KEY > GEMINI_API_KEY (gemini) | OPENAI_API_KEY (openai_compat) | NVIDIA_API_KEY (nvidia_nim)

This file is intentionally self-contained: it does NOT use ``LLMBackend`` so a
user can run a different vision provider from the chat provider without
fighting the existing chat config.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..tool_registry import ToolPermission, tool


SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent/vision"
CHAT_SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent"

DEFAULT_BASE_URL_BY_PROVIDER = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openai_compat": "https://api.openai.com/v1",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1",
}

DEFAULT_MODEL_BY_PROVIDER = {
    "gemini": "gemini-2.0-flash",
    "openai_compat": "gpt-4o",
    "nvidia_nim": "meta/llama-3.2-90b-vision-instruct",
}

ENV_KEY_FALLBACKS_BY_PROVIDER = {
    "gemini": ("VISION_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai_compat": ("VISION_API_KEY", "OPENAI_API_KEY"),
    "nvidia_nim": ("VISION_API_KEY", "NVIDIA_API_KEY"),
}

# Map a chat provider (set in CopilotSettingsDialog) to the vision protocol it
# uses. Most chat providers expose an OpenAI-compatible /chat/completions
# endpoint that accepts image_url parts, so vision can reuse the same
# base_url + api_key + model. Gemini uses its own native protocol.
_CHAT_PROVIDER_TO_VISION_PROVIDER = {
    "siliconflow": "openai_compat",
    "kimi_official": "openai_compat",
    "openai": "openai_compat",
    "deepseek": "openai_compat",
    "custom": "openai_compat",
    "gemini": "gemini",
}


# =============================================================================
# Settings helpers
# =============================================================================

def _get_setting(path: str, default: Any = None) -> Any:
    try:
        import carb.settings  # type: ignore

        value = carb.settings.get_settings().get(path)
        return default if value in (None, "") else value
    except Exception:
        return default


def _decode_chat_api_key(encoded: str) -> str:
    """Mirror of CopilotViewModel._decode (base64). Empty in/out is safe."""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def _get_chat_backend_config() -> Dict[str, str]:
    """Read the chat backend config the user already set via CopilotSettingsDialog."""
    return {
        "provider": str(_get_setting(f"{CHAT_SETTINGS_PREFIX}/provider") or "").strip().lower(),
        "base_url": str(_get_setting(f"{CHAT_SETTINGS_PREFIX}/base_url") or "").strip(),
        "api_key": _decode_chat_api_key(_get_setting(f"{CHAT_SETTINGS_PREFIX}/api_key") or ""),
        "model": str(_get_setting(f"{CHAT_SETTINGS_PREFIX}/model") or "").strip(),
    }


def _resolve_timeout(default: int = 90) -> int:
    raw = (
        _get_setting(f"{SETTINGS_PREFIX}/timeout")
        or os.environ.get("ANIM_VISION_TIMEOUT")
        or default
    )
    try:
        return max(5, min(int(raw), 600))
    except Exception:
        return default


def _get_vision_config() -> Dict[str, Any]:
    """
    Resolve vision provider configuration.

    Modes (in priority order):

    1. Explicit vision settings under /exts/.../agent/vision/{provider, model,
       base_url, api_key, timeout}. Use these as-is.
    2. provider == "auto" (or unset): inherit from the chat backend the user
       configured in the Anime Agent Settings dialog. Multimodal chat models
       like Kimi K2.6 / GPT-4o / Gemini-2.0 can serve as vision providers
       directly, so the user does not need to configure two API keys.
    3. Final fallback: provider defaults to "gemini" with env-var keys.

    Vision-specific overrides (model, base_url, api_key) always win over
    inherited chat values, so the user can run a different model for vision
    if they want (e.g. cheap Gemini for vision + Kimi for chat).
    """
    raw_provider = (
        _get_setting(f"{SETTINGS_PREFIX}/provider")
        or os.environ.get("ANIM_VISION_PROVIDER")
        or "auto"
    )
    raw_provider = str(raw_provider).strip().lower()

    explicit_model = _get_setting(f"{SETTINGS_PREFIX}/model") or os.environ.get("ANIM_VISION_MODEL") or ""
    explicit_base_url = _get_setting(f"{SETTINGS_PREFIX}/base_url") or os.environ.get("ANIM_VISION_BASE_URL") or ""
    explicit_api_key = _get_setting(f"{SETTINGS_PREFIX}/api_key") or ""

    # ---------- AUTO: inherit from the user's chat backend ----------
    if raw_provider == "auto":
        chat = _get_chat_backend_config()
        if chat["api_key"]:
            vision_provider = _CHAT_PROVIDER_TO_VISION_PROVIDER.get(chat["provider"], "openai_compat")
            return {
                "provider": vision_provider,
                "model": (
                    explicit_model
                    or chat["model"]
                    or DEFAULT_MODEL_BY_PROVIDER[vision_provider]
                ),
                "base_url": (
                    str(explicit_base_url or chat["base_url"] or DEFAULT_BASE_URL_BY_PROVIDER[vision_provider]).rstrip("/")
                ),
                "api_key": str(explicit_api_key or chat["api_key"]),
                "timeout": _resolve_timeout(),
                "auto_inherited_from_chat": True,
                "inherited_chat_provider": chat["provider"],
            }
        # No chat key configured either; fall through to gemini default below.
        raw_provider = "gemini"

    # ---------- Explicit provider ----------
    provider = raw_provider if raw_provider in DEFAULT_BASE_URL_BY_PROVIDER else "gemini"

    api_key = explicit_api_key
    if not api_key:
        for env_name in ENV_KEY_FALLBACKS_BY_PROVIDER[provider]:
            api_key = os.environ.get(env_name) or ""
            if api_key:
                break

    return {
        "provider": provider,
        "model": str(explicit_model or DEFAULT_MODEL_BY_PROVIDER[provider]),
        "base_url": str(explicit_base_url or DEFAULT_BASE_URL_BY_PROVIDER[provider]).rstrip("/"),
        "api_key": str(api_key),
        "timeout": _resolve_timeout(),
        "auto_inherited_from_chat": False,
    }


# =============================================================================
# Image loading
# =============================================================================

_SUPPORTED_MIME = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
}


def _load_image(image_path: str) -> Dict[str, str]:
    path = (image_path or "").strip().strip('"').strip("'")
    if not path:
        raise ValueError("image_path is empty")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Image not found: {path}")

    mime, _ = mimetypes.guess_type(path)
    if mime not in _SUPPORTED_MIME:
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        if ext in {"jpg", "jpeg"}:
            mime = "image/jpeg"
        elif ext in {"png", "webp", "gif", "bmp"}:
            mime = f"image/{ext}"
        else:
            raise ValueError(f"Unsupported image format: .{ext}")

    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Image larger than 20 MB")

    return {"b64": base64.b64encode(raw).decode("ascii"), "mime": mime}


# =============================================================================
# Prompt + schema
# =============================================================================

_FOCUS_BLURBS = {
    "general": (
        "Cover all three: subjects, environment, camera framing, and lighting."
    ),
    "subjects_only": (
        "Focus on the foreground subjects only. Keep environment terse."
    ),
    "lighting": (
        "Focus on the lighting (key direction, color temperature, mood) and the "
        "environment. Keep subjects terse."
    ),
}


def _build_prompt(focus: str, user_hint: str) -> str:
    focus = focus or "general"
    blurb = _FOCUS_BLURBS.get(focus, _FOCUS_BLURBS["general"])
    hint = (user_hint or "").strip()

    return (
        "You are a layout assistant for an Omniverse animation tool. Look at "
        "the attached reference image and output a JSON SceneGraph that the "
        "downstream tools will consume to build a USD scene from a USD asset "
        "library. Be honest about uncertainty; never invent assets that are "
        "not visible.\n\n"
        f"Focus: {blurb}\n"
        + (f"User hint: {hint}\n" if hint else "")
        + "\nReturn ONLY valid JSON matching this schema (no markdown, no comments):\n"
        + "{\n"
        '  "subjects": [\n'
        '    {\n'
        '      "label": "<short noun phrase, e.g. wooden chair>",\n'
        '      "search_queries": ["<2-4 short queries an asset library would understand>"],\n'
        '      "rough_position": "front-left|front-center|front-right|center-left|center|center-right|back-left|back-center|back-right",\n'
        '      "rough_scale": "small|human|large|xl",\n'
        '      "facing": "camera|left|right|away"\n'
        '    }\n'
        '  ],\n'
        '  "environment": {\n'
        '    "label": "<short noun phrase, e.g. wooden cabin interior>",\n'
        '    "search_queries": ["<1-3 queries>"]\n'
        '  },\n'
        '  "camera": {\n'
        '    "angle_deg_pitch": <number, negative looks down>,\n'
        '    "framing": "close|medium|wide",\n'
        '    "fov_estimate_deg": <number, 20-80>\n'
        '  },\n'
        '  "lighting": {\n'
        '    "key": {\n'
        '      "direction": "left|right|top|back|front",\n'
        '      "color_kelvin": <number 2000-12000>,\n'
        '      "mood": "warm|neutral|cool"\n'
        '    },\n'
        '    "ambient": {\n'
        '      "hdri_hint": "<short phrase, e.g. warm sunset>"\n'
        '    }\n'
        '  }\n'
        "}\n"
    )


# =============================================================================
# Provider HTTP calls
# =============================================================================

def _http_post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {detail[:500]}") from e
    except Exception as e:
        raise RuntimeError(f"Vision request failed: {e}") from e

    try:
        return json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Vision response parse failed: {e}; body={raw[:500]}") from e


def _call_gemini(cfg: Dict[str, Any], image: Dict[str, str], prompt: str) -> str:
    base = cfg["base_url"]
    is_google_endpoint = "generativelanguage.googleapis.com" in base
    if is_google_endpoint:
        url = f"{base}/models/{cfg['model']}:generateContent?key={cfg['api_key']}"
        headers = {"Content-Type": "application/json"}
    else:
        url = f"{base}/models/{cfg['model']}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
            "x-api-key": cfg["api_key"],
        }

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": image["mime"], "data": image["b64"]}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    data = _http_post_json(url, headers, payload, cfg["timeout"])
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {str(data)[:300]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    chunks = [p.get("text", "") for p in parts if "text" in p]
    text = "".join(chunks).strip()
    if not text:
        raise RuntimeError("Gemini returned empty content")
    return text


def _call_openai_compat(cfg: Dict[str, Any], image: Dict[str, str], prompt: str) -> str:
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        # Cap completion length. Kimi K2.6 in JSON mode happily generates 5000+
        # tokens to fill in every nested array field; without a cap a typical
        # SceneGraph response takes 90+ seconds, which is right at our timeout
        # cliff. 2000 tokens is plenty for ~15 subjects with full schema and
        # cuts vision latency back to ~30s. Documented in test_kimi_vision.py.
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{image['mime']};base64,{image['b64']}"},
                    },
                ],
            }
        ],
    }
    data = _http_post_json(url, headers, payload, cfg["timeout"])
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenAI-compat returned no choices: {str(data)[:300]}")
    msg = (choices[0].get("message") or {})
    content = msg.get("content")
    if isinstance(content, list):
        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
    else:
        text = (content or "").strip()
    if not text:
        raise RuntimeError("OpenAI-compat returned empty content")
    return text


def _call_nvidia_nim(cfg: Dict[str, Any], image: Dict[str, str], prompt: str) -> str:
    # NVIDIA NIM exposes an OpenAI-compatible chat/completions surface. We call
    # the same path as openai_compat but keep this branch so we can specialise
    # if NVIDIA's payload diverges (e.g. their VLM expects an explicit
    # response format change).
    return _call_openai_compat(cfg, image, prompt)


def _call_provider(cfg: Dict[str, Any], image: Dict[str, str], prompt: str) -> str:
    provider = cfg["provider"]
    if provider == "gemini":
        return _call_gemini(cfg, image, prompt)
    if provider == "openai_compat":
        return _call_openai_compat(cfg, image, prompt)
    if provider == "nvidia_nim":
        return _call_nvidia_nim(cfg, image, prompt)
    raise RuntimeError(f"Unknown vision provider: {provider}")


# =============================================================================
# Output normalisation
# =============================================================================

_VALID_POSITIONS = {
    "front-left", "front-center", "front-right",
    "center-left", "center", "center-right",
    "back-left", "back-center", "back-right",
}
_VALID_SCALES = {"small", "human", "large", "xl"}
_VALID_FACINGS = {"camera", "left", "right", "away"}
_VALID_FRAMINGS = {"close", "medium", "wide"}
_VALID_KEY_DIRECTIONS = {"left", "right", "top", "back", "front"}
_VALID_MOODS = {"warm", "neutral", "cool"}


def _strip_json_fence(text: str) -> str:
    text = (text or "").strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Some providers prepend chatter; attempt to find the first {...} blob.
    if not text.startswith("{"):
        idx = text.find("{")
        if idx != -1:
            text = text[idx:]
    return text


def _coerce_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _coerce_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        # Sometimes providers return comma-separated strings.
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            s = _coerce_str(item, "")
            if s:
                out.append(s)
        return out
    return []


def _coerce_enum(value: Any, allowed: set, default: str) -> str:
    s = _coerce_str(value).lower()
    return s if s in allowed else default


def _coerce_number(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        f = float(value)
    except Exception:
        return default
    if f < lo:
        return lo
    if f > hi:
        return hi
    return f


def _normalize_scene_graph(parsed: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {
            "subjects": [],
            "environment": None,
            "camera": None,
            "lighting": None,
            "_warning": "Provider response was not a JSON object",
        }

    subjects_in = parsed.get("subjects") or []
    if not isinstance(subjects_in, list):
        subjects_in = []

    subjects: List[Dict[str, Any]] = []
    for item in subjects_in:
        if not isinstance(item, dict):
            continue
        label = _coerce_str(item.get("label"))
        if not label:
            continue
        queries = _coerce_str_list(item.get("search_queries"))
        if not queries:
            queries = [label]
        subjects.append(
            {
                "label": label,
                "search_queries": queries[:6],
                "rough_position": _coerce_enum(item.get("rough_position"), _VALID_POSITIONS, "center"),
                "rough_scale": _coerce_enum(item.get("rough_scale"), _VALID_SCALES, "human"),
                "facing": _coerce_enum(item.get("facing"), _VALID_FACINGS, "camera"),
            }
        )

    environment_in = parsed.get("environment")
    environment: Optional[Dict[str, Any]] = None
    if isinstance(environment_in, dict):
        env_label = _coerce_str(environment_in.get("label"))
        if env_label:
            queries = _coerce_str_list(environment_in.get("search_queries")) or [env_label]
            environment = {"label": env_label, "search_queries": queries[:4]}

    camera_in = parsed.get("camera")
    camera: Optional[Dict[str, Any]] = None
    if isinstance(camera_in, dict):
        camera = {
            "angle_deg_pitch": _coerce_number(camera_in.get("angle_deg_pitch"), 0.0, -90.0, 90.0),
            "framing": _coerce_enum(camera_in.get("framing"), _VALID_FRAMINGS, "medium"),
            "fov_estimate_deg": _coerce_number(camera_in.get("fov_estimate_deg"), 35.0, 10.0, 120.0),
        }

    lighting_in = parsed.get("lighting")
    lighting: Optional[Dict[str, Any]] = None
    if isinstance(lighting_in, dict):
        key_in = lighting_in.get("key")
        ambient_in = lighting_in.get("ambient")
        key_out: Optional[Dict[str, Any]] = None
        ambient_out: Optional[Dict[str, Any]] = None
        if isinstance(key_in, dict):
            key_out = {
                "direction": _coerce_enum(key_in.get("direction"), _VALID_KEY_DIRECTIONS, "front"),
                "color_kelvin": _coerce_number(key_in.get("color_kelvin"), 5500.0, 1500.0, 15000.0),
                "mood": _coerce_enum(key_in.get("mood"), _VALID_MOODS, "neutral"),
            }
        if isinstance(ambient_in, dict):
            hint = _coerce_str(ambient_in.get("hdri_hint"))
            if hint:
                ambient_out = {"hdri_hint": hint}
        if key_out or ambient_out:
            lighting = {"key": key_out, "ambient": ambient_out}

    return {
        "subjects": subjects,
        "environment": environment,
        "camera": camera,
        "lighting": lighting,
    }


# =============================================================================
# Tool
# =============================================================================

@tool(
    description=(
        "Describe a reference image as a structured SceneGraph JSON for the "
        "anime agent's reference-scene pipeline. The output schema is fixed: "
        "subjects[*].(label, search_queries, rough_position, rough_scale, facing), "
        "environment, camera (pitch/framing/fov), lighting (key direction / "
        "color_kelvin / mood + ambient hint). Downstream tools (search_usd_assets, "
        "pick_best_asset, propose_layout, create_camera_for_view, create_light) "
        "consume this directly. Configure the vision provider via "
        "/exts/omni.anim.drama.toolset/agent/vision/* settings or the "
        "VISION_API_KEY / GEMINI_API_KEY / NVIDIA_API_KEY env vars."
    ),
    permission=ToolPermission.READ_ONLY,
    category="vision",
    tags=["vision", "reference-image", "scene-graph", "perceive"],
    phase_hint="gather",
    parameters_schema={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Local path to the reference image (png/jpg/webp/gif/bmp, <=20 MB).",
            },
            "focus": {
                "type": "string",
                "enum": ["general", "subjects_only", "lighting"],
                "description": "Bias the description towards subjects, lighting, or a balanced view.",
            },
            "user_hint": {
                "type": "string",
                "description": "Optional one-line user hint to bias interpretation (e.g. 'cozy living room').",
            },
        },
        "required": ["image_path"],
    },
)
def describe_reference_image(
    image_path: str,
    focus: str = "general",
    user_hint: str = "",
) -> Dict[str, Any]:
    """
    Convert a reference image into a structured SceneGraph JSON via a
    vision-capable LLM.
    """
    cfg = _get_vision_config()
    if not cfg["api_key"]:
        return {
            "ok": False,
            "error": "Vision provider API key is not configured.",
            "hint": (
                "Vision tools default to provider='auto', which reuses the chat backend "
                "you set in the Anime Agent Settings dialog. Either: (a) configure a chat "
                "backend (Settings -> LLM Provider) and use a multimodal model "
                "(e.g. Kimi K2.6, GPT-4o, Gemini-2.0); OR (b) set "
                "/exts/omni.anim.drama.toolset/agent/vision/api_key explicitly; OR (c) set "
                "one of the env vars: " + ", ".join(ENV_KEY_FALLBACKS_BY_PROVIDER[cfg["provider"]])
            ),
            "provider": cfg["provider"],
            "auto_inherited_from_chat": cfg.get("auto_inherited_from_chat", False),
        }

    try:
        image = _load_image(image_path)
    except Exception as e:
        return {"ok": False, "error": f"Failed to load image: {e}", "image_path": image_path}

    prompt = _build_prompt(focus, user_hint)

    try:
        raw_text = _call_provider(cfg, image, prompt)
    except Exception as e:
        return {
            "ok": False,
            "error": f"Vision provider call failed: {e}",
            "provider": cfg["provider"],
            "model": cfg["model"],
        }

    cleaned = _strip_json_fence(raw_text)
    try:
        parsed = json.loads(cleaned)
    except Exception as e:
        return {
            "ok": False,
            "error": f"Vision response was not valid JSON: {e}",
            "raw_excerpt": cleaned[:500],
            "provider": cfg["provider"],
            "model": cfg["model"],
        }

    scene_graph = _normalize_scene_graph(parsed)
    return {
        "ok": True,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "auto_inherited_from_chat": cfg.get("auto_inherited_from_chat", False),
        "focus": focus,
        "image_path": image_path,
        "scene_graph": scene_graph,
        "subject_count": len(scene_graph["subjects"]),
        "next_action_hint": (
            "For each scene_graph.subjects[i], call search_usd_assets(query=subjects[i].search_queries[0]). "
            "Then pick_best_asset, propose_layout, reference_usd_asset, create_camera_for_view, create_light."
        ),
    }
