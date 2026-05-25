# -*- coding: utf-8 -*-
"""
USD Code Tools - minimal ChatUSD-like stage code execution
=========================================================

This module gives the anime agent a generic USD action surface without
depending on NVIDIA USD Code NIM. It is intentionally conservative: the tool
is MUTATE, requires the existing approval UI, performs a syntax/safety pass,
and dry-runs against an isolated in-memory stage before touching the live
stage. Live runs are wrapped in `omni.kit.undo.group` so users can roll back
with Ctrl+Z.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import io
import json
import re
from typing import Any, Dict, Optional

from ..tool_registry import ToolPermission, tool
from ...core.stage_utils import get_stage, run_on_main_thread


# =============================================================================
# Sandbox policy (M1 P0-1)
# =============================================================================
#
# We switched from a tight whitelist of builtins to a permissive blacklist.
# The previous whitelist made common USD snippets fail with NameError on
# `Exception`, `getattr`, `hasattr`, `setattr`, `type`, `iter`, `next`, etc.
# The threat model here is "stop the LLM from doing accidental damage", not
# "fully sandbox an adversarial Python program" - the agent's tool layer is
# already the trust boundary. So we keep the AST-level blocks for IO/network
# entry points and the import-root whitelist, but otherwise expose all builtins.

_ALLOWED_IMPORT_ROOTS = {
    "pxr",
    "omni",
    "carb",
    "math",
    "json",
    "typing",
    "collections",
    "itertools",
    "functools",
    "re",
    "usdcode",
    "uicode",
}

_DENIED_CALL_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "input",
    "__import__",
    "breakpoint",
}

_DENIED_BUILTIN_NAMES = {
    "open",
    "eval",
    "exec",
    "compile",
    "input",
    "__import__",
    "breakpoint",
    "quit",
    "exit",
    "help",
    "copyright",
    "credits",
    "license",
}

_DENIED_IMPORT_ROOTS = {
    "os",
    "sys",
    "subprocess",
    "shutil",
    "socket",
    "pathlib",
    "glob",
    "tempfile",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "pickle",
    "ctypes",
    "importlib",
}


def _strip_code_fence(code: str) -> str:
    text = (code or "").strip()
    match = re.match(r"^```(?:python)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if text.lower().startswith("python\n"):
        return text.split("\n", 1)[1].strip()
    return text


def _import_root(module_name: str) -> str:
    return (module_name or "").split(".", 1)[0]


def _validate_code(code: str) -> Optional[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif node.module:
                names = [node.module]
            for name in names:
                root = _import_root(name)
                if root in _DENIED_IMPORT_ROOTS:
                    return f"Import of '{root}' is not allowed in execute_usd_python."
                if root and root not in _ALLOWED_IMPORT_ROOTS:
                    return f"Import of '{root}' is not in the allowed USD/Kit module list."

        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _DENIED_CALL_NAMES:
                return f"Call to '{fn.id}' is not allowed in execute_usd_python."

    return None


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = _import_root(name)
    if root in _DENIED_IMPORT_ROOTS or root not in _ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"Import of '{root}' is not allowed in execute_usd_python")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> Dict[str, Any]:
    """Expose the builtin namespace minus the IO/process/exit entry points."""
    out: Dict[str, Any] = {}
    for name in dir(builtins):
        if name.startswith("_"):
            # We selectively re-add a few dunders below.
            continue
        if name in _DENIED_BUILTIN_NAMES:
            continue
        try:
            out[name] = getattr(builtins, name)
        except AttributeError:
            continue

    # Re-add the dunder entries the runtime actually needs.
    for name in ("__build_class__", "__name__", "__doc__", "__package__", "__loader__", "__spec__"):
        value = getattr(builtins, name, None)
        if value is not None:
            out[name] = value

    out["__import__"] = _guarded_import
    return out


# =============================================================================
# Dry-run stage isolation (M1 P0-2)
# =============================================================================

def _create_dry_run_stage():
    """
    Create an isolated dry-run stage that mirrors the current live stage.

    Strategy:
    - If the live root layer is a real disk layer, open it under a fresh
      anonymous session layer and force EditTarget to that session, so writes
      stay in-memory.
    - If the live root layer is anonymous (common for unsaved scenes), copy
      its content to a new anonymous layer and create a stage on top of it.

    Compared with the previous implementation that did
    ``new_stage.GetRootLayer().subLayerPaths.append(root_layer.identifier)``,
    this one is reliable across anonymous layers, payloads, and clip stages,
    and it also keeps the live stage untouched.
    """
    from pxr import Sdf, Usd, UsdGeom

    current_stage = get_stage()
    if current_stage is None:
        return None

    root_layer = current_stage.GetRootLayer()
    if root_layer is None:
        return None

    try:
        anonymous_root = bool(root_layer.anonymous)
    except Exception:
        anonymous_root = True

    if anonymous_root:
        copied_root = Sdf.Layer.CreateAnonymous(root_layer.GetDisplayName() or "dryrun")
        try:
            copied_root.TransferContent(root_layer)
        except Exception:
            return None
        new_stage = Usd.Stage.Open(copied_root, Sdf.Layer.CreateAnonymous("session"))
    else:
        try:
            new_stage = Usd.Stage.Open(root_layer, Sdf.Layer.CreateAnonymous("session"))
        except Exception:
            copied_root = Sdf.Layer.CreateAnonymous(root_layer.GetDisplayName() or "dryrun")
            try:
                copied_root.TransferContent(root_layer)
            except Exception:
                return None
            new_stage = Usd.Stage.Open(copied_root, Sdf.Layer.CreateAnonymous("session"))

    try:
        session_layer = current_stage.GetSessionLayer()
        if session_layer:
            new_stage.GetSessionLayer().TransferContent(session_layer)
    except Exception:
        pass

    try:
        axis = UsdGeom.GetStageUpAxis(current_stage)
        if axis:
            UsdGeom.SetStageUpAxis(new_stage, axis)
    except Exception:
        pass

    try:
        new_stage.SetStartTimeCode(current_stage.GetStartTimeCode())
        new_stage.SetEndTimeCode(current_stage.GetEndTimeCode())
    except Exception:
        pass

    # Force writes to land in the new (anonymous) session layer instead of the
    # original disk layer. This is the actual "isolation" guarantee.
    try:
        new_stage.SetEditTarget(new_stage.GetSessionLayer())
    except Exception:
        pass

    return new_stage


# =============================================================================
# Code execution
# =============================================================================

def _make_omni_stub(stage):
    """
    Build a minimal `omni` stub whose `omni.usd.get_context().get_stage()`
    returns the given (dry-run) stage.

    Why a stub instead of string-replacing the snippet: the previous
    `_prepare_code_for_dry_run` only matched the literal expression and was
    bypassed by aliases such as ``ctx = omni.usd.get_context(); ctx.get_stage()``
    or ``getattr(__import__('omni').usd, 'get_context')``. By replacing the
    entire `omni` module reference inside the dry-run globals, we shut all
    those side-channels in one place.
    """
    class _StubSelection:
        def get_selected_prim_paths(self):
            return []

        def set_selected_prim_paths(self, *args, **kwargs):
            return False

    class _StubContext:
        def get_stage(self):
            return stage

        def get_selection(self):
            return _StubSelection()

    class _StubUsdModule:
        @staticmethod
        def get_context(*args, **kwargs):
            return _StubContext()

    class _StubOmni:
        usd = _StubUsdModule

    return _StubOmni()


def _execute_code(
    code: str,
    stage,
    max_output_chars: int,
    *,
    is_dry_run: bool,
) -> Dict[str, Any]:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade  # noqa: F401

    globals_dict: Dict[str, Any] = {
        "__builtins__": _safe_builtins(),
        "stage": stage,
        "Gf": Gf,
        "Sdf": Sdf,
        "Usd": Usd,
        "UsdGeom": UsdGeom,
        "UsdLux": UsdLux,
        "UsdShade": UsdShade,
        "json": json,
    }

    if is_dry_run:
        # Plug a stub `omni` so `omni.usd.get_context().get_stage()` still
        # resolves but points at the dry-run stage instead of the live one.
        globals_dict["omni"] = _make_omni_stub(stage)
    else:
        try:
            import omni.usd  # noqa: F401

            globals_dict["omni"] = __import__("omni")
        except Exception:
            pass

    stream = io.StringIO()
    try:
        with contextlib.redirect_stdout(stream):
            exec(compile(code, "<execute_usd_python>", "exec"), globals_dict, globals_dict)
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "stdout": stream.getvalue()[:max_output_chars],
        }

    stdout = stream.getvalue()
    truncated = len(stdout) > max_output_chars
    return {
        "ok": True,
        "stdout": stdout[:max_output_chars],
        "stdout_truncated": truncated,
    }


def _short_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", errors="replace")).hexdigest()[:8]


@tool(
    description=(
        "Execute a small USD Python snippet in the current Omniverse stage. "
        "Use this as a generic ChatUSD-like fallback for camera/material/layout changes "
        "when no high-level tool exists. Prefer reference_usd_asset for importing assets "
        "and lighting tools for light edits. The snippet gets a predefined `stage` variable "
        "and common pxr modules; do not read/write files or use network/process APIs. "
        "Live runs are wrapped in an omni.kit.undo group so the user can revert with Ctrl+Z; "
        "writes do NOT go into the relight layer."
    ),
    permission=ToolPermission.MUTATE,
    category="usd_code",
    tags=["usd", "python", "stage", "chatusd", "layout"],
    phase_hint="act",
    verify_with=["get_scene_summary", "inspect_prim", "get_scene_bounds"],
    parameters_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet. A `stage` variable is already provided.",
            },
            "dry_run_first": {
                "type": "boolean",
                "description": "Run on an in-memory stage first before touching the live stage. Default true.",
            },
            "max_output_chars": {
                "type": "integer",
                "description": "Maximum captured stdout characters to return. Default 4000.",
            },
        },
        "required": ["code"],
    },
)
def execute_usd_python(
    code: str,
    dry_run_first: bool = True,
    max_output_chars: int = 4000,
) -> Dict[str, Any]:
    """
    Execute controlled USD Python against the current stage.
    """
    stage = get_stage()
    if stage is None:
        return {"ok": False, "error": "No USD stage is currently open."}

    snippet = _strip_code_fence(code)
    if not snippet:
        return {"ok": False, "error": "code is empty."}

    validation_error = _validate_code(snippet)
    if validation_error:
        return {"ok": False, "error": validation_error}

    cap = max(200, min(int(max_output_chars or 4000), 20000))

    dry_result: Optional[Dict[str, Any]] = None
    if dry_run_first:
        dry_stage = _create_dry_run_stage()
        if dry_stage is None:
            return {"ok": False, "error": "Failed to create dry-run stage."}
        dry_result = _execute_code(snippet, dry_stage, cap, is_dry_run=True)
        if not dry_result.get("ok"):
            return {
                "ok": False,
                "phase": "dry_run",
                "error": dry_result.get("error"),
                "stdout": dry_result.get("stdout", ""),
                "hint": "The live stage was not modified. Fix the snippet and retry.",
            }

    # Live execution: wrap in omni.kit.undo.group so a single Ctrl+Z reverts
    # everything the snippet authored. We fall back to a plain run when undo
    # is unavailable (e.g. headless test environments).
    #
    # The whole live block is marshalled to Kit's main thread because USD
    # composition/Hydra invalidation can deadlock with the render thread when
    # invoked from the agent worker thread.
    undo_group_name = f"[execute_usd_python] {_short_hash(snippet)}"

    def _do_live_run() -> Dict[str, Any]:
        try:
            import omni.kit.undo as _undo  # type: ignore

            with _undo.group():
                return _execute_code(snippet, stage, cap, is_dry_run=False)
        except Exception:
            return _execute_code(snippet, stage, cap, is_dry_run=False)

    live_result: Dict[str, Any]
    try:
        live_result = run_on_main_thread(_do_live_run, timeout=180.0)
    except Exception as e:
        live_result = {"ok": False, "error": f"main-thread marshal failed: {e}", "stdout": ""}

    if not live_result.get("ok"):
        return {
            "ok": False,
            "phase": "live_run",
            "error": live_result.get("error"),
            "stdout": live_result.get("stdout", ""),
            "dry_run": dry_result,
            "undo_group": undo_group_name,
        }

    return {
        "ok": True,
        "dry_run": dry_result,
        "live_run": live_result,
        "undo_group": undo_group_name,
        "verify_hint": (
            "Call get_scene_summary, inspect_prim, or get_scene_bounds to confirm the change. "
            "execute_usd_python writes are NOT in the relight layer; revert via Ctrl+Z if needed."
        ),
    }
