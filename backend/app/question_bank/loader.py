from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .schema import Bank, Question, validate_question

DEFAULT_CORE_PATH = Path("question_bank/core.yaml")
DEFAULT_META_DIR = Path("meta")

def load_bank(path: Path = DEFAULT_CORE_PATH) -> Bank:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions: List[Question] = []
    for item in raw.get("questions", []):
        q = Question(
            id=item["id"],
            domain=item["domain"],
            signal=item["signal"],
            question=item["question"],
            answers=item["answers"],
        )
        validate_question(q)
        questions.append(q)

    return Bank(
        version=str(raw.get("version", "")),
        name=str(raw.get("name", "Question Bank")),
        questions=questions,
    )

def load_meta(meta_dir: Path = DEFAULT_META_DIR) -> Dict[str, Any]:
    def _read(name: str) -> Dict[str, Any]:
        p = meta_dir / name
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    return {
        "flow_rules": _read("flow_rules.yaml"),
        "states": _read("states.yaml"),
        "collisions": _read("collisions.yaml"),
    }
