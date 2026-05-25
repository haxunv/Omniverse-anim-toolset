# -*- coding: utf-8 -*-
"""
Asset Tools - ChatUSD-like USD asset search and referencing
===========================================================

Small, dependency-light tools for the anime agent MVP:

- search_usd_assets: search a USD asset library, either via a USD Search
  compatible HTTP endpoint OR by scanning a local directory tree.
- reference_usd_asset: add a searched USD asset as a reference in the current stage.

`search_usd_assets` auto-detects which mode to use from `search_path`:

- Remote modes (USD Search HTTP API):
  - `omniverse://...`  /  `http(s)://...`  /  `s3://...`
  - empty (uses host_url default search index)
- Local mode (filesystem scan, no API key needed):
  - any existing local directory (e.g. `E:\\usd\\ppty_mod`).

Local mode does name/path token matching against `query` and is intentionally
simple. Image-similarity search is only available in remote mode.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from ..tool_registry import ToolPermission, tool
from ...core.stage_utils import get_context, get_stage, run_on_main_thread


SETTINGS_PREFIX = "/exts/omni.anim.drama.toolset/agent/usd_search"
DEFAULT_USD_SEARCH_HOST_URL = "https://ai.api.nvidia.com/v1/omniverse/nvidia/usdsearch"


def _get_setting(path: str, default: Any = None) -> Any:
    try:
        import carb.settings

        value = carb.settings.get_settings().get(path)
        return default if value in (None, "") else value
    except Exception:
        return default


def _get_usd_search_config() -> Dict[str, Any]:
    host_url = (
        _get_setting(f"{SETTINGS_PREFIX}/host_url")
        or os.environ.get("USDSEARCH_HOST_URL")
        or DEFAULT_USD_SEARCH_HOST_URL
    )
    api_key = (
        _get_setting(f"{SETTINGS_PREFIX}/api_key")
        or os.environ.get("USDSEARCH_API_KEY")
        or os.environ.get("NVIDIA_API_KEY")
        or ""
    )
    username = _get_setting(f"{SETTINGS_PREFIX}/username") or os.environ.get("USDSEARCH_USERNAME") or ""
    search_path = _get_setting(f"{SETTINGS_PREFIX}/search_path") or os.environ.get("USDSEARCH_SEARCH_PATH") or ""
    return {
        "host_url": str(host_url).rstrip("/"),
        "api_key": str(api_key),
        "username": str(username),
        "search_path": str(search_path),
    }


def _basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _read_image_base64(image_path: str) -> str:
    path = (image_path or "").strip().strip('"')
    if not path:
        raise ValueError("image_path is empty")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# =============================================================================
# Local filesystem search (fallback when search_path is a local directory)
# =============================================================================

_REMOTE_PROTOCOLS = ("omniverse://", "http://", "https://", "s3://", "ftp://", "ftps://")
_USD_EXTENSIONS = (".usd", ".usda", ".usdc", ".usdz")
_TOKEN_SPLIT_RE = re.compile(r"[\s_\-./\\]+")
_LOCAL_INDEX_HARD_CAP = 20000  # protect against indexing huge drives by mistake


def _is_remote_search_path(path: str) -> bool:
    return bool(path) and path.lower().startswith(_REMOTE_PROTOCOLS)


def _is_local_search_path(path: str) -> bool:
    """A non-remote, existing directory on disk."""
    if not path:
        return False
    if _is_remote_search_path(path):
        return False
    try:
        return os.path.isdir(path)
    except Exception:
        return False


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [tok.lower() for tok in _TOKEN_SPLIT_RE.split(text) if tok]


def _index_local_usd_library(root: str) -> List[Dict[str, Any]]:
    """One pass walk; returns lightweight records used for scoring."""
    entries: List[Dict[str, Any]] = []
    root = os.path.abspath(root)

    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _USD_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, fname)
            stem = os.path.splitext(fname)[0]
            try:
                rel = os.path.relpath(full_path, root)
            except Exception:
                rel = fname
            ancestor_dirs = []
            head = os.path.dirname(rel)
            while head:
                ancestor_dirs.append(os.path.basename(head))
                head_parent = os.path.dirname(head)
                if head_parent == head:
                    break
                head = head_parent
            entries.append(
                {
                    "abs_path": full_path,
                    "rel_path": rel.replace("\\", "/"),
                    "stem": stem,
                    "stem_tokens": _tokenize(stem),
                    "ancestor_tokens": [t for d in ancestor_dirs for t in _tokenize(d)],
                    "size_bytes": os.path.getsize(full_path) if os.path.isfile(full_path) else 0,
                }
            )
            if len(entries) >= _LOCAL_INDEX_HARD_CAP:
                return entries
    return entries


def _score_local_entry(entry: Dict[str, Any], query_tokens: List[str]) -> float:
    if not query_tokens:
        return 0.0
    score = 0.0
    stem_tokens = set(entry.get("stem_tokens", []))
    ancestor_tokens = set(entry.get("ancestor_tokens", []))
    stem_lower = entry.get("stem", "").lower()
    rel_lower = entry.get("rel_path", "").lower()

    for tok in query_tokens:
        if tok in stem_tokens:
            score += 5.0
        elif tok in stem_lower:
            score += 3.0
        if tok in ancestor_tokens:
            score += 2.0
        elif tok in rel_lower:
            score += 1.0
    # All-tokens-present bonus
    if all(tok in rel_lower for tok in query_tokens):
        score += 1.5
    return score


def _to_file_url(abs_path: str) -> str:
    p = abs_path.replace("\\", "/")
    # USD/Sdf accepts plain absolute paths and file:// URLs. Keep file:// for
    # explicit clarity in tool output.
    if not p.startswith("/"):
        p = "/" + p
    return f"file://{p}"


def _search_local_usd_library(
    root: str,
    query: str,
    limit: int,
    min_score: Optional[float] = None,
) -> Dict[str, Any]:
    if not _is_local_search_path(root):
        return {
            "ok": False,
            "error": f"Local search_path is not an existing directory: {root}",
        }

    if not (query or "").strip():
        return {"ok": False, "error": "Local mode requires a non-empty query."}

    query_tokens = _tokenize(query)
    if not query_tokens:
        return {"ok": False, "error": f"Query did not yield searchable tokens: {query!r}"}

    try:
        entries = _index_local_usd_library(root)
    except Exception as e:
        return {"ok": False, "error": f"Failed to index {root}: {e}"}

    scored: List[Dict[str, Any]] = []
    for entry in entries:
        s = _score_local_entry(entry, query_tokens)
        if s <= 0:
            continue
        if min_score is not None:
            try:
                if s < float(min_score):
                    continue
            except Exception:
                pass
        scored.append((s, entry))  # type: ignore[arg-type]

    scored.sort(key=lambda x: (-x[0], x[1]["rel_path"]))  # type: ignore[index]
    top = scored[: max(1, min(limit, 50))]

    results: List[Dict[str, Any]] = []
    for score, entry in top:  # type: ignore[misc]
        results.append(
            {
                "url": _to_file_url(entry["abs_path"]),
                "abs_path": entry["abs_path"],
                "name": entry["stem"],
                "rel_path": entry["rel_path"],
                "size_bytes": entry["size_bytes"],
                "score": round(float(score), 3),
            }
        )

    return {
        "ok": True,
        "mode": "local",
        "search_path": root,
        "indexed_files": len(entries),
        "indexed_capped": len(entries) >= _LOCAL_INDEX_HARD_CAP,
        "count": len(results),
        "results": results,
    }


# =============================================================================
# Remote (USD Search HTTP) result cleaning
# =============================================================================

def _clean_search_results(items: Any, max_items: int) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue

        out: Dict[str, Any] = {}
        for key in (
            "url",
            "name",
            "title",
            "description",
            "bbox_dimension",
            "bbox_dimension_x",
            "bbox_dimension_y",
            "bbox_dimension_z",
            "metadata",
        ):
            if key in item:
                out[key] = item[key]

        if "url" in out:
            out["url"] = (
                str(out["url"])
                .replace(
                    "s3://deepsearch-demo-content/",
                    "https://omniverse-content-production.s3.us-west-2.amazonaws.com/",
                )
                .replace(
                    "s3://deepsearch-content-staging-bucket/",
                    "https://deepsearch-content-staging-bucket.s3.us-east-2.amazonaws.com/",
                )
            )

        if "image" in item:
            try:
                with tempfile.NamedTemporaryFile(prefix="anim_asset_", suffix=".png", delete=False) as temp_file:
                    temp_file.write(base64.b64decode(item["image"]))
                    out["thumbnail_path"] = temp_file.name
            except Exception as e:
                out["thumbnail_error"] = str(e)

        if "bbox_dimension" not in out and all(k in out for k in ("bbox_dimension_x", "bbox_dimension_y", "bbox_dimension_z")):
            out["bbox_dimension"] = [
                out.pop("bbox_dimension_x"),
                out.pop("bbox_dimension_y"),
                out.pop("bbox_dimension_z"),
            ]

        if out:
            cleaned.append(out)

    return cleaned


@tool(
    description=(
        "Search a USD asset library. Auto-routes by search_path: an existing LOCAL directory "
        "(e.g. 'E:\\\\usd\\\\my_library') triggers a fast filesystem name/path token match "
        "(no API key needed); otherwise the call goes to a USD Search HTTP endpoint and uses "
        "the configured api_key. Use query for text search; image_path for image-similarity "
        "search (REMOTE mode only). Optionally override search_path per call to swap libraries "
        "without touching settings. Returns asset URLs (file:// for local, https/omniverse for "
        "remote) plus optional thumbnails that pick_best_asset and reference_usd_asset consume."
    ),
    permission=ToolPermission.READ_ONLY,
    category="asset",
    tags=["asset", "usd", "search", "reference-image", "chatusd"],
    phase_hint="gather",
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Text description to search for, e.g. 'green dinosaur cactus character'.",
            },
            "image_path": {
                "type": "string",
                "description": "Optional local reference image path for image-similarity search.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum assets to return. Default 10, hard cap 50. Alias: top_k_per_query.",
            },
            "top_k_per_query": {
                "type": "integer",
                "description": "Alias for limit, kept for symmetry with describe_reference_image's per-subject loop.",
            },
            "search_path": {
                "type": "string",
                "description": (
                    "Per-call override for the asset library search root. Either a local "
                    "directory (e.g. 'E:\\\\usd\\\\my_library' -> filesystem mode, no API key needed), "
                    "or a remote URL like 'omniverse://...' / 'https://...' / 's3://...' "
                    "(remote mode, USD Search API). Empty = use settings default."
                ),
            },
            "min_score": {
                "type": "number",
                "description": "Optional minimum similarity score [0..1]; results below are dropped.",
            },
            "return_metadata": {
                "type": "boolean",
                "description": "Whether to ask the search service to include metadata.",
            },
        },
    },
)
def search_usd_assets(
    query: str = "",
    image_path: str = "",
    limit: int = 10,
    top_k_per_query: Optional[int] = None,
    search_path: str = "",
    min_score: Optional[float] = None,
    return_metadata: bool = False,
) -> Dict[str, Any]:
    """
    Search USD assets by text and/or image.

    Args:
        query: Text description. Optional when image_path is provided.
        image_path: Local image path for visual search.
        limit: Max result count.
        top_k_per_query: Alias for limit (whichever is set takes effect).
        search_path: Per-call override for the asset library search root.
        min_score: Optional minimum similarity score; results below this are dropped.
        return_metadata: Include metadata if supported by the endpoint.
    """
    cfg = _get_usd_search_config()
    effective_limit = top_k_per_query if top_k_per_query else limit
    cap = max(1, min(int(effective_limit or 10), 50))
    effective_search_path = (search_path or "").strip() or cfg["search_path"]

    # ---------- Local-filesystem fallback ----------
    # When search_path points at an existing local directory, skip the HTTP
    # endpoint entirely and walk the tree. This unblocks users who have a
    # fixed local asset library (e.g. `E:\\usd\\my_library`) without standing
    # up a USD Search server.
    if _is_local_search_path(effective_search_path):
        if image_path:
            return {
                "ok": False,
                "error": (
                    "image_similarity_search is only supported in remote USD Search mode. "
                    "Local-folder search_path uses filename/path token matching only."
                ),
                "search_path": effective_search_path,
                "mode": "local",
                "hint": "Either describe the asset in 'query' as text, or point search_path at a remote USD Search server.",
            }
        local = _search_local_usd_library(
            root=effective_search_path,
            query=query,
            limit=cap,
            min_score=min_score,
        )
        if not local.get("ok"):
            return local
        local.update(
            {
                "query": query,
                "image_path": image_path,
                "min_score": min_score,
                "next_action_hint": (
                    "Call pick_best_asset(subject_label, candidates=results) to commit one, "
                    "or directly pass result.url (file:// URL) to reference_usd_asset."
                ),
            }
        )
        return local

    # ---------- Remote USD Search HTTP endpoint ----------
    if not cfg["api_key"]:
        return {
            "ok": False,
            "error": "USD Search API key is not configured (and search_path is not a local directory).",
            "hint": (
                "Either: (a) set /exts/omni.anim.drama.toolset/agent/usd_search/api_key "
                "(or USDSEARCH_API_KEY / NVIDIA_API_KEY) to use NVIDIA's hosted USD Search, "
                "OR (b) set search_path to a local directory like 'E:\\\\usd\\\\my_library' "
                "to use filename-based local search instead."
            ),
        }

    payload: Dict[str, Any] = {
        "return_metadata": bool(return_metadata),
        "limit": cap,
        "file_extension_include": "usd*",
        "return_images": True,
        "return_root_prims": False,
    }
    if effective_search_path:
        payload["search_path"] = effective_search_path

    search_mode = "text"
    if image_path:
        try:
            payload["image_similarity_search"] = _read_image_base64(image_path)
        except Exception as e:
            return {"ok": False, "error": f"Failed to read image_path: {e}", "image_path": image_path}
        if query:
            payload["description"] = query
        search_mode = "image"
    else:
        if not (query or "").strip():
            return {"ok": False, "error": "Either query or image_path is required."}
        payload["description"] = query.strip()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if cfg["username"]:
        headers["Authorization"] = _basic_auth(cfg["username"], cfg["api_key"])
    else:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    request = urllib.request.Request(
        cfg["host_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "ok": False,
            "error": f"USD Search HTTP {e.code}: {detail[:500]}",
            "host_url": cfg["host_url"],
            "mode": search_mode,
        }
    except Exception as e:
        return {"ok": False, "error": f"USD Search request failed: {e}", "host_url": cfg["host_url"], "mode": search_mode}

    results = _clean_search_results(data, cap)

    if min_score is not None:
        try:
            threshold = float(min_score)
        except Exception:
            threshold = 0.0
        kept: List[Dict[str, Any]] = []
        for item in results:
            score = item.get("score") or item.get("similarity") or item.get("metadata", {}).get("score")
            try:
                score_f = float(score) if score is not None else None
            except Exception:
                score_f = None
            if score_f is None or score_f >= threshold:
                kept.append(item)
        results = kept

    return {
        "ok": True,
        "mode": search_mode,
        "query": query,
        "image_path": image_path,
        "search_path": effective_search_path,
        "min_score": min_score,
        "host_url": cfg["host_url"],
        "count": len(results),
        "results": results,
        "next_action_hint": (
            "Call pick_best_asset(subject_label, candidates=results) to commit one, "
            "or directly pass result.url to reference_usd_asset."
        ),
    }


def _make_valid_identifier(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name or "Asset").strip("_")
    if not name:
        name = "Asset"
    if name[0].isdigit():
        name = f"Asset_{name}"
    return name


def _ensure_xform_ancestors(stage, prim_path: str) -> None:
    from pxr import Sdf, UsdGeom

    path = Sdf.Path(prim_path)
    ancestors = []
    parent = path.GetParentPath()
    while parent and str(parent) not in ("", "/"):
        ancestors.append(parent)
        parent = parent.GetParentPath()
    for ancestor in reversed(ancestors):
        if not stage.GetPrimAtPath(ancestor).IsValid():
            UsdGeom.Xform.Define(stage, ancestor)


def _unique_path(stage, prim_path: str) -> str:
    from pxr import Sdf

    path = Sdf.Path(prim_path)
    if not stage.GetPrimAtPath(path).IsValid():
        return str(path)
    base = str(path)
    index = 1
    while True:
        candidate = f"{base}_{index:02d}"
        if not stage.GetPrimAtPath(candidate).IsValid():
            return candidate
        index += 1


def _vec3(value: Any, default: float = 0.0) -> List[float]:
    if isinstance(value, (int, float)):
        v = float(value)
        return [v, v, v]
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [float(value[0]), float(value[1]), float(value[2])]
    return [default, default, default]


@tool(
    description=(
        "Reference a USD asset URL/path into the current stage under a new Xform prim, "
        "then optionally set translation, Euler rotation, and scale. Use this after "
        "search_usd_assets has returned a result URL."
    ),
    permission=ToolPermission.MUTATE,
    category="asset",
    tags=["asset", "usd", "reference", "layout"],
    phase_hint="act",
    verify_with=["inspect_prim", "get_scene_bounds"],
    parameters_schema={
        "type": "object",
        "properties": {
            "asset_url": {
                "type": "string",
                "description": "USD asset URL/path to reference, e.g. omniverse://.../asset.usd or https://.../asset.usd.",
            },
            "prim_path": {
                "type": "string",
                "description": "Target prim path. If omitted, creates one under /World/Assets.",
            },
            "translation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ translation.",
            },
            "rotation": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ Euler rotation in degrees.",
            },
            "scale": {
                "type": "array",
                "items": {"type": "number"},
                "description": "XYZ scale. A single uniform number is also accepted by the tool runtime.",
            },
            "select_new": {
                "type": "boolean",
                "description": "Select the newly referenced prim in the viewport.",
            },
        },
        "required": ["asset_url"],
    },
)
def reference_usd_asset(
    asset_url: str,
    prim_path: str = "",
    translation: Optional[List[float]] = None,
    rotation: Optional[List[float]] = None,
    scale: Optional[List[float]] = None,
    select_new: bool = True,
) -> Dict[str, Any]:
    """
    Add a USD reference into the current stage.
    """
    stage = get_stage()
    if stage is None:
        return {"ok": False, "error": "No USD stage is currently open."}

    asset_url = (asset_url or "").strip()
    if not asset_url:
        return {"ok": False, "error": "asset_url is required."}

    if not prim_path:
        stem = os.path.splitext(os.path.basename(asset_url.rstrip("/")))[0] or "Asset"
        prim_path = f"/World/Assets/{_make_valid_identifier(stem)}"

    # USD writes (Xform.Define / AddReference / xform ops / selection) MUST run
    # on Kit's main thread, otherwise they race with the render thread and can
    # deadlock the whole UI. We marshal the entire mutation block via
    # run_on_main_thread; the worker thread blocks until the tick completes.
    def _do_reference() -> Dict[str, Any]:
        from pxr import Gf, Sdf, UsdGeom

        target_path = Sdf.Path(prim_path)
        if not target_path.IsAbsolutePath() or str(target_path) == "/":
            return {"ok": False, "error": f"prim_path must be an absolute prim path: {prim_path}"}

        _ensure_xform_ancestors(stage, str(target_path))
        final_path = _unique_path(stage, str(target_path))
        xform = UsdGeom.Xform.Define(stage, final_path)
        prim = xform.GetPrim()
        prim.GetReferences().AddReference(asset_url)

        # M1 P1-1: only author xform ops the caller actually asked for. The
        # previous behaviour cleared the order and authored zero translate /
        # zero rotate / unit scale unconditionally, which made every default
        # call slam the asset to the world origin and overwrote any transform
        # baked into the referenced layer. Now, when no transform argument is
        # given, we leave the new prim's xformOpOrder untouched so the
        # asset's intrinsic transform (if any) survives the reference.
        xformable = UsdGeom.Xformable(prim)
        any_transform = (
            translation is not None
            or rotation is not None
            or scale is not None
        )
        applied_translation: Optional[List[float]] = None
        applied_rotation: Optional[List[float]] = None
        applied_scale: Optional[List[float]] = None
        if any_transform:
            xformable.ClearXformOpOrder()
            if translation is not None:
                applied_translation = _vec3(translation, 0.0)
                xformable.AddTranslateOp().Set(Gf.Vec3d(*applied_translation))
            if rotation is not None:
                applied_rotation = _vec3(rotation, 0.0)
                xformable.AddRotateXYZOp().Set(Gf.Vec3f(*applied_rotation))
            if scale is not None:
                applied_scale = _vec3(scale, 1.0)
                xformable.AddScaleOp().Set(Gf.Vec3f(*applied_scale))

        if select_new:
            try:
                get_context().get_selection().set_selected_prim_paths([final_path], True)
            except Exception:
                pass

        return {
            "ok": True,
            "prim_path": final_path,
            "asset_url": asset_url,
            "translation": applied_translation,
            "rotation": applied_rotation,
            "scale": applied_scale,
            "transform_authored": any_transform,
            "verify_hint": (
                f"Call inspect_prim('{final_path}') and get_scene_bounds() to verify placement. "
                "When transform_authored is false the asset uses its own intrinsic transform."
            ),
        }

    try:
        return run_on_main_thread(_do_reference, timeout=180.0)
    except Exception as e:
        return {"ok": False, "error": f"Failed to reference asset: {e}", "asset_url": asset_url, "prim_path": prim_path}
