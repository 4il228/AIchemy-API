import hashlib
import json
import re

# ГОСТ 7.79-2000 (система B) — для читаемых имён файлов без кириллицы в URL
_CYR_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shh",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate(text: str) -> str:
    return "".join(_CYR_TO_LAT.get(ch, ch) for ch in text.lower())


def make_image_filename(result_name: str, element_a: str, element_b: str) -> str:
    """Слаг из транслита + короткий hash пары: без кириллицы в URL и без коллизий."""
    slug = re.sub(r"[^a-z0-9]+", "_", transliterate(result_name)).strip("_") or "element"
    pair_hash = hashlib.sha1(f"{element_a}+{element_b}".encode()).hexdigest()[:8]
    return f"{slug}_{pair_hash}.png"


def extract_json(raw: str) -> dict:
    """Достаёт JSON-объект даже если модель обернула его в markdown или добавила текст."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise json.JSONDecodeError("No JSON object found", raw, 0)
