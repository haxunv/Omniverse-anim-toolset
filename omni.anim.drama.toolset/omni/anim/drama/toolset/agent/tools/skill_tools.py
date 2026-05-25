# -*- coding: utf-8 -*-
"""
Skill Tools - 领域知识"工作手册"按需检索
=========================================

把 OV / OpenUSD / 动画工作流的常识、坑、最佳实践写成一组 markdown 文件，
让 Agent 通过 ``list_skills`` / ``search_skills`` / ``read_skill`` 按需检索，
而不是塞进一坨巨大的 system prompt。

Skill 文件布局（约定）::

    agent/skills/
        usd-fundamentals/
            SKILL.md              # 短摘要 + 触发条件，<= 800 字
            layers.md             # 详细内容，按需 read_skill 读
            xform-ops.md
        animation-keyframes/
            SKILL.md
            time-samples.md
            ...

SKILL.md 的格式（YAML-ish frontmatter，可选）::

    ---
    id: usd-fundamentals
    title: USD Fundamentals
    triggers: [usd, layer, prim, schema, stage]
    related_files: [layers.md, xform-ops.md]
    ---

    （正文短摘要：什么时候读我？我覆盖了什么？需要更深入读哪个 related_file？）

如果没有 frontmatter，工具会用目录名当 id、用第一行非空文本当 title。

读取规则：
- ``list_skills``: 列出所有 SKILL.md 的 id / title / triggers / 字数；不返回正文
- ``search_skills(query)``: 在 SKILL.md 的 title + triggers + 正文中做大小写不敏感匹配
- ``read_skill(skill_id, file)``: 读取某个 skill 目录下的 SKILL.md 或某个 related_file

正文限制：单文件正文截断到 12_000 字符，避免一次塞爆 context。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..tool_registry import tool, ToolPermission


# =============================================================================
# Skill 目录定位（默认相对于本文件 ../skills）
# =============================================================================

_DEF_SKILLS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "skills")
)

# 允许通过 env 覆盖
SKILLS_DIR = os.environ.get("ANIM_DRAMA_AGENT_SKILLS_DIR", _DEF_SKILLS_DIR)

# 单文件正文最大长度
_MAX_BODY_CHARS = 12_000


# =============================================================================
# Skill 数据结构
# =============================================================================

@dataclass
class SkillEntry:
    """一个 skill = 目录 + SKILL.md + 0~N 个关联 md 文件。"""
    id: str
    title: str
    triggers: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)
    summary: str = ""
    skill_md_path: str = ""
    dir_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "triggers": list(self.triggers),
            "related_files": list(self.related_files),
            "summary_chars": len(self.summary),
        }


# =============================================================================
# 解析 SKILL.md
# =============================================================================

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<body>.*?)\n---\s*\n(?P<rest>.*)$",
    re.DOTALL,
)


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    """
    YAML-ish 简单解析：仅支持 ``key: value`` 与 ``key: [a, b, c]``。
    不依赖 pyyaml。
    """
    out: Dict[str, Any] = {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {"_body": text}
    body = m.group("body")
    rest = m.group("rest")

    for line in body.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if v.startswith("[") and v.endswith("]"):
            items = [s.strip().strip("'\"") for s in v[1:-1].split(",")]
            out[k] = [s for s in items if s]
        else:
            out[k] = v.strip("'\"")

    out["_body"] = rest
    return out


def _load_skill_dir(dir_path: str) -> Optional[SkillEntry]:
    skill_md = os.path.join(dir_path, "SKILL.md")
    if not os.path.isfile(skill_md):
        return None

    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    parsed = _parse_frontmatter(text)
    body = parsed.pop("_body", "") or ""

    skill_id = str(parsed.get("id") or os.path.basename(dir_path)).strip()
    title = str(parsed.get("title") or "").strip()
    if not title:
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            title = line.lstrip("#").strip()
            break
        if not title:
            title = skill_id

    triggers_val = parsed.get("triggers") or []
    if isinstance(triggers_val, str):
        triggers_val = [s.strip() for s in triggers_val.split(",") if s.strip()]

    related_val = parsed.get("related_files") or []
    if isinstance(related_val, str):
        related_val = [s.strip() for s in related_val.split(",") if s.strip()]

    # 自动补充：目录下其它 .md 文件（非 SKILL.md）
    auto_related: List[str] = []
    try:
        for fname in sorted(os.listdir(dir_path)):
            if fname.lower().endswith(".md") and fname != "SKILL.md":
                auto_related.append(fname)
    except Exception:
        pass
    related = list(dict.fromkeys(list(related_val) + auto_related))

    return SkillEntry(
        id=skill_id,
        title=title,
        triggers=list(triggers_val),
        related_files=related,
        summary=body.strip(),
        skill_md_path=skill_md,
        dir_path=dir_path,
    )


def _load_all_skills() -> List[SkillEntry]:
    """扫描 SKILLS_DIR 下所有 skill 目录。"""
    out: List[SkillEntry] = []
    if not os.path.isdir(SKILLS_DIR):
        return out
    for name in sorted(os.listdir(SKILLS_DIR)):
        sub = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(sub):
            continue
        entry = _load_skill_dir(sub)
        if entry:
            out.append(entry)
    return out


def _find_skill(skill_id: str) -> Optional[SkillEntry]:
    sid = (skill_id or "").strip()
    if not sid:
        return None
    for s in _load_all_skills():
        if s.id == sid:
            return s
    return None


def _truncate(text: str, n: int = _MAX_BODY_CHARS) -> str:
    if len(text) <= n:
        return text
    return text[:n] + f"\n\n[... truncated, full file is {len(text)} chars ...]"


# =============================================================================
# Tools
# =============================================================================

@tool(
    description=(
        "List all available skills (compressed domain manuals). Each entry has "
        "id, title, triggers (when to read me), and related_files. Returned text "
        "is intentionally short; use read_skill to get a specific file's body. "
        "Skills cover OpenUSD basics, layer composition, time samples / xformOps, "
        "lighting recipes, common pitfalls, etc. ALWAYS skim this list at the "
        "start of any non-trivial task; pull only the skills you actually need."
    ),
    permission=ToolPermission.READ_ONLY,
    category="meta",
    tags=["skill", "knowledge", "meta"],
    phase_hint="gather",
)
def list_skills() -> Dict[str, Any]:
    """List all skills (id / title / triggers, no body)."""
    skills = _load_all_skills()
    return {
        "skills_dir": SKILLS_DIR,
        "count": len(skills),
        "skills": [s.to_dict() for s in skills],
        "hint": (
            "Use search_skills(query) to find candidates by keyword, "
            "or read_skill(skill_id) to load a skill's SKILL.md, "
            "or read_skill(skill_id, file='xxx.md') to load a related deep-dive file."
        ),
    }


@tool(
    description=(
        "Search skills by case-insensitive keyword. Matches against skill title, "
        "triggers, and the SKILL.md summary body. Use this when you have a fuzzy "
        "concept (e.g. 'keyframe', 'layer mute', 'up axis') and want to find which "
        "skill explains it. Returns ranked candidates (best first) with short snippets."
    ),
    permission=ToolPermission.READ_ONLY,
    category="meta",
    tags=["skill", "knowledge", "search"],
    phase_hint="gather",
)
def search_skills(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search skills.

    Args:
        query: Case-insensitive keyword.
        limit: Max number of results (default 5, hard cap 20).
    """
    if not query or not query.strip():
        return {"error": "query must be non-empty."}

    cap = max(1, min(int(limit), 20))
    needle = query.lower().strip()

    skills = _load_all_skills()
    scored: List[Dict[str, Any]] = []
    for s in skills:
        score = 0
        if needle in s.title.lower():
            score += 5
        for t in s.triggers:
            if needle in t.lower():
                score += 3
        # body
        body_l = s.summary.lower()
        body_hits = body_l.count(needle)
        score += body_hits

        if score == 0:
            continue

        # 抓一段 snippet
        snippet = ""
        idx = body_l.find(needle)
        if idx >= 0:
            start = max(0, idx - 80)
            end = min(len(s.summary), idx + 200)
            snippet = s.summary[start:end].replace("\n", " ").strip()

        scored.append({
            "id": s.id,
            "title": s.title,
            "score": score,
            "triggers": list(s.triggers),
            "snippet": snippet,
            "related_files": list(s.related_files),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return {
        "query": query,
        "count": len(scored),
        "results": scored[:cap],
        "hint": "Call read_skill(skill_id) for full SKILL.md body.",
    }


@tool(
    description=(
        "Read the body of a skill: SKILL.md by default, or a specific related_file "
        "(e.g. 'time-samples.md') when you need a deep-dive. The returned body is "
        "truncated to 12000 chars per call. ONLY read the skills you actually need; "
        "do not preload everything."
    ),
    permission=ToolPermission.READ_ONLY,
    category="meta",
    tags=["skill", "knowledge", "read"],
    phase_hint="gather",
)
def read_skill(skill_id: str, file: str = "") -> Dict[str, Any]:
    """
    Read SKILL.md or a related deep-dive file.

    Args:
        skill_id: Skill id (matches what list_skills returns).
        file: If set, read this file inside the skill directory instead of SKILL.md.
              Must be a basename, no directory traversal.
    """
    entry = _find_skill(skill_id)
    if entry is None:
        return {"error": f"Skill not found: {skill_id}", "available": [s.id for s in _load_all_skills()]}

    target = file.strip()
    if not target:
        return {
            "id": entry.id,
            "title": entry.title,
            "triggers": list(entry.triggers),
            "related_files": list(entry.related_files),
            "file": "SKILL.md",
            "body": _truncate(entry.summary),
        }

    # 安全：禁止路径穿越
    if "/" in target or "\\" in target or target.startswith("..") or os.path.isabs(target):
        return {"error": "file must be a basename (no path separators / no '..')."}

    if not target.lower().endswith(".md"):
        return {"error": "file must be a .md file."}

    full = os.path.join(entry.dir_path, target)
    if not os.path.isfile(full):
        return {
            "error": f"File not found in skill '{entry.id}': {target}",
            "available": list(entry.related_files),
        }

    try:
        with open(full, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

    return {
        "id": entry.id,
        "title": entry.title,
        "file": target,
        "body": _truncate(text),
        "total_chars": len(text),
    }
