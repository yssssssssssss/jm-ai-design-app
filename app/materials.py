from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
MATERIALS_DIR = ROOT_DIR / "assets" / "spec-materials"
MATERIALS_PATH = MATERIALS_DIR / "materials.json"


def _issue_text(issue: dict[str, Any]) -> str:
    return " ".join(
        str(issue.get(key) or "")
        for key in [
            "category",
            "location",
            "current_observation",
            "spec_expectation",
            "recommendation",
            "component_type",
            "violation_type",
            "target_solution",
            "target_tokens",
        ]
    ).lower()


def _issue_tokens(text: str) -> set[str]:
    tokens = {match.upper() for match in re.findall(r"#[0-9a-fA-F]{6}\b", text)}
    tokens.update(match.lower() for match in re.findall(r"\bai/[a-z0-9-]+\b", text))
    tokens.update(
        match.lower() for match in re.findall(r"\bgradient/ai/[a-z0-9-]+\b", text)
    )
    return tokens


def _normal_token(token: Any) -> str:
    value = str(token or "").strip()
    return value.upper() if value.startswith("#") else value.lower()


@lru_cache(maxsize=1)
def load_materials() -> tuple[dict[str, Any], ...]:
    if not MATERIALS_PATH.exists():
        return ()
    data = json.loads(MATERIALS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return ()
    return tuple(item for item in data if isinstance(item, dict))


def material_url(material: dict[str, Any]) -> str | None:
    crop_path = str(material.get("crop_path") or "").strip()
    if not crop_path or crop_path.startswith("/") or ".." in Path(crop_path).parts:
        return None
    return f"/materials/{crop_path}"


def _material_score(material: dict[str, Any], text: str, tokens: set[str]) -> int:
    score = 0
    component = str(material.get("component") or "").lower()
    if component and component in text:
        score += 8

    keywords = [str(item).lower() for item in material.get("keywords", [])]
    score += sum(3 for keyword in keywords if keyword and keyword in text)

    material_tokens = {_normal_token(token) for token in material.get("tokens", [])}
    score += 10 * len(tokens & material_tokens)

    rule_ids = [str(item).lower() for item in material.get("rule_ids", [])]
    score += sum(2 for rule_id in rule_ids if rule_id and rule_id in text)
    return score


def match_material(issue: dict[str, Any]) -> dict[str, Any] | None:
    text = _issue_text(issue)
    tokens = _issue_tokens(text)
    candidates = []
    for material in load_materials():
        score = _material_score(material, text, tokens)
        if score > 0 and material_url(material):
            candidates.append((score, str(material.get("id") or ""), material))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]
