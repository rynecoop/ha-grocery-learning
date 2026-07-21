"""Parse recipe data out of a web page's embedded schema.org metadata.

Pure, Home-Assistant-independent so it can be unit tested without HA. Given the
HTML of a recipe page, pull out the recipe name, ingredient lines and direction
steps from the ``schema.org/Recipe`` JSON-LD block that virtually every recipe
site embeds (AllRecipes, NYT Cooking, Food Network, Serious Eats, …).

Nothing here reaches the network: the caller fetches the page and hands us the
markup, keeping the parsing logic testable and the "local only" promise intact.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

# JSON-LD lives in <script type="application/ld+json"> blocks. Match loosely so
# extra attributes (e.g. an id) on the tag don't defeat us.
_LD_JSON_RE = re.compile(
    r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value: Any) -> str:
    """Collapse a JSON-LD string value to clean single-line text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    # Recipe JSON occasionally carries inline HTML tags or entities.
    text = _TAG_RE.sub(" ", value)
    text = unescape(text)
    return " ".join(text.split()).strip()


def _iter_json_objects(raw: Any):
    """Yield every dict nested anywhere inside a decoded JSON-LD value.

    Handles the common ``@graph`` wrapper and top-level arrays by walking the
    whole structure rather than assuming the recipe is at the root.
    """
    if isinstance(raw, dict):
        yield raw
        for value in raw.values():
            yield from _iter_json_objects(value)
    elif isinstance(raw, list):
        for value in raw:
            yield from _iter_json_objects(value)


def _has_recipe_type(obj: dict) -> bool:
    """True when a JSON-LD object is (or includes) a schema.org Recipe."""
    type_value = obj.get("@type")
    if isinstance(type_value, str):
        return type_value.strip().lower() == "recipe"
    if isinstance(type_value, list):
        return any(
            isinstance(entry, str) and entry.strip().lower() == "recipe"
            for entry in type_value
        )
    return False


def _extract_ingredients(recipe: dict) -> list[str]:
    raw = recipe.get("recipeIngredient")
    if raw is None:
        raw = recipe.get("ingredients")  # legacy key some sites still use
    if isinstance(raw, str):
        raw = [raw]
    out: list[str] = []
    if isinstance(raw, list):
        for entry in raw:
            text = _clean_text(entry)
            if text:
                out.append(text)
    return out


def _extract_directions(recipe: dict) -> list[str]:
    out: list[str] = []

    def _add(value: Any) -> None:
        text = _clean_text(value)
        if text:
            out.append(text)

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            # A single instructions string can hold several steps separated by
            # newlines; split conservatively so each step lands on its own line.
            for line in re.split(r"[\r\n]+", value):
                _add(line)
        elif isinstance(value, dict):
            type_value = value.get("@type")
            is_section = (
                isinstance(type_value, str)
                and type_value.strip().lower() == "howtosection"
            )
            if is_section or "itemListElement" in value:
                _walk(value.get("itemListElement"))
            else:
                _add(value.get("text") or value.get("name"))
        elif isinstance(value, list):
            for entry in value:
                _walk(entry)

    _walk(recipe.get("recipeInstructions"))
    return out


def parse_recipe(html: str) -> dict[str, Any]:
    """Return ``{"name", "ingredients", "directions"}`` parsed from page HTML.

    Scans every ``application/ld+json`` block, finds the first object typed as a
    schema.org Recipe (even nested inside an ``@graph`` array) that carries
    ingredients or directions, and pulls its name, ingredient lines and step
    text. Returns empty fields when the page has no recognizable recipe data.
    """
    name = ""
    empty = {"name": "", "ingredients": [], "directions": []}
    if not isinstance(html, str) or not html:
        return dict(empty)

    for block in _LD_JSON_RE.findall(html):
        text = block.strip()
        # Some CMSes wrap JSON-LD in an HTML comment or CDATA guard.
        if text.startswith("<!--"):
            text = text[4:]
        if text.endswith("-->"):
            text = text[:-3]
        text = text.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        for obj in _iter_json_objects(data):
            if not isinstance(obj, dict) or not _has_recipe_type(obj):
                continue
            ingredients = _extract_ingredients(obj)
            directions = _extract_directions(obj)
            candidate_name = _clean_text(obj.get("name"))
            if ingredients or directions:
                return {
                    "name": candidate_name,
                    "ingredients": ingredients,
                    "directions": directions,
                }
            # Remember a bare name in case no fuller recipe object turns up.
            if candidate_name and not name:
                name = candidate_name

    return {"name": name, "ingredients": [], "directions": []}
