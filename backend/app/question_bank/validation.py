from __future__ import annotations

from typing import Dict, Any, Set, Optional

from .constants import ALL_ALLOWED

class ValidationError(ValueError):
    pass

def validate_answer_value(answer: str) -> None:
    if answer not in ALL_ALLOWED:
        raise ValidationError(f"invalid_answer_value: {answer}")

def validate_signal_exists(signal: str, signal_set: Set[str]) -> None:
    if signal not in signal_set:
        raise ValidationError(f"unknown_signal: {signal}")

def build_signal_set_from_bank(bank_yaml: Dict[str, Any]) -> Set[str]:
    sigs = set()
    for q in bank_yaml.get("questions", []):
        sigs.add(q["signal"])
    return sigs
