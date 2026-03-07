"""Pure helpers for Local List Assist voice/list matching."""

from __future__ import annotations

import re
from typing import Any


def normalize_term(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", str(value).lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_voice_list_name(value: str) -> str:
    normalized = normalize_term(value)
    normalized = re.sub(r"\b(my|the)\b", " ", normalized).strip()
    normalized = re.sub(r"\s+'?s\b", "", normalized).strip()
    normalized = re.sub(r"\s+s\b", "", normalized).strip()
    normalized = re.sub(r"\blist\b", " ", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def voice_list_name_variants(value: str) -> set[str]:
    normalized = normalize_voice_list_name(value)
    if not normalized:
        return set()

    variants: set[str] = {normalized}
    tokens = [token for token in normalized.split(" ") if token]
    if not tokens:
        return variants

    def add_candidate(parts: list[str]) -> None:
        candidate = " ".join(part for part in parts if part).strip()
        if candidate:
            variants.add(candidate)

    add_candidate(tokens)

    shortened_all: list[str] = []
    for token in tokens:
        if len(token) > 3 and token.endswith("s"):
            shortened_all.append(token[:-1])
        else:
            shortened_all.append(token)
    add_candidate(shortened_all)

    last_trimmed = list(tokens)
    if len(last_trimmed[-1]) > 3 and last_trimmed[-1].endswith("s"):
        last_trimmed[-1] = last_trimmed[-1][:-1]
        add_candidate(last_trimmed)

    compact = normalized.replace(" ", "")
    if compact:
        variants.add(compact)
        if len(compact) > 3 and compact.endswith("s"):
            variants.add(compact[:-1])

    return {candidate for candidate in variants if candidate}


def resolve_list_id_from_voice_name(list_name: str, lists: dict[str, Any]) -> str:
    if not list_name:
        return ""
    requested_variants = voice_list_name_variants(list_name)
    if not requested_variants:
        return ""

    for list_id, list_obj in lists.items():
        if not isinstance(list_obj, dict):
            continue
        current_name_variants = voice_list_name_variants(str(list_obj.get("name", "")).strip())
        id_variants = voice_list_name_variants(str(list_id))
        alias_variants: set[str] = set()
        for alias in list_obj.get("voice_aliases", []):
            if isinstance(alias, str):
                alias_variants.update(voice_list_name_variants(alias))
        if requested_variants.intersection(current_name_variants):
            return str(list_id)
        if requested_variants.intersection(id_variants):
            return str(list_id)
        if requested_variants.intersection(alias_variants):
            return str(list_id)
    return ""
