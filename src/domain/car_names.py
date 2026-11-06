"""Matching brand/model names in free text against the real catalog.

Pure functions: comparison ignores case, spaces, hyphens and punctuation, so
``Toyota Rav4``, ``toyota rav-4`` and ``RAV 4`` all resolve to catalog ``RAV4``.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

_WORDS = re.compile(r"[^\W_]+")
_BRAND_ALIASES = {"volkswagen": ("vw",)}

Names = Sequence[tuple[str, str]]  # (brand, model) of active catalog cars


@dataclass(frozen=True)
class NameMatch:
    models: tuple[tuple[str, str], ...]
    brands: tuple[str, ...]


def norm(value: str) -> str:
    return "".join(_WORDS.findall(value.casefold()))


def _phrases(texts: Iterable[str | None]) -> set[str]:
    """Every run of up to three consecutive words, joined without separators."""
    phrases: set[str] = set()
    for text in texts:
        words = _WORDS.findall(text.casefold()) if text else []
        for start in range(len(words)):
            joined = ""
            for word in words[start : start + 3]:
                joined += word
                phrases.add(joined)
    return phrases


def _brand_keys(brand: str) -> set[str]:
    key = norm(brand)
    keys = {key, *_BRAND_ALIASES.get(key, ())}
    parts = [norm(part) for part in re.split(r"[\W_]+", brand) if part]
    if len(parts) > 1 and len(parts[0]) >= 4:  # "Mercedes" for "Mercedes-Benz"
        keys.add(parts[0])
    return keys


def match_names(names: Names, *texts: str | None) -> NameMatch:
    phrases = _phrases(texts)
    brands = tuple(sorted(b for b in {b for b, _ in names} if _brand_keys(b) & phrases))
    models = []
    for brand, model in sorted(set(names)):
        name = norm(model)
        if not name:
            continue
        adjacent = any(key + name in phrases for key in _brand_keys(brand))
        # Short names such as "6" or "530" must be written next to the brand.
        distinctive = len(name) >= 4 or (
            len(name) >= 3
            and any(c.isdigit() for c in name)
            and any(c.isalpha() for c in name)
        )
        if adjacent or (distinctive and name in phrases):
            models.append((brand, model))
    return NameMatch(tuple(models), brands)


def canonical_brand(names: Names, value: str) -> str | None:
    wanted = norm(value)
    return next((b for b, _ in names if norm(b) == wanted), None)


def without_brand_words(value: str, names: Names) -> str:
    """Drop brand words ("Toyota Supra" -> "Supra") so only a model name remains."""
    brand_words: set[str] = set()
    for brand in {b for b, _ in names}:
        brand_words.update(_WORDS.findall(brand.casefold()))
        brand_words.update(_BRAND_ALIASES.get(norm(brand), ()))
    return " ".join(w for w in _WORDS.findall(value) if w.casefold() not in brand_words)


def known_words(names: Names) -> set[str]:
    words: set[str] = set()
    for brand, model in names:
        words.update(_WORDS.findall(f"{brand} {model}".casefold()))
    return words


def same_car_name(brand: str, model: str, other_brand: str, other_model: str) -> bool:
    return norm(brand) == norm(other_brand) and norm(model) == norm(other_model)
