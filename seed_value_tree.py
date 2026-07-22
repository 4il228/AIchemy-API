"""Быстрый путь AIchemist до V >= 200.

- V = V_a + V_b, базы V=1
- Никогда A+A
- По одному крафту за раз (не раздуваем низкие тиры)
- Dual-spine: либо скрещиваем два max-V, либо создаём напарника того же V
- Разнообразие: предпочитаем пары с малым пересечением стихийных тегов
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_TIMEOUT", "90")

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import select

load_dotenv()

from app.config import settings
from app.services import craft as craft_service
from db import Recipe, async_session, init_db

TARGET_V = 200
MAX_ATTEMPTS = 14
PAUSE_BETWEEN_CRAFTS_SEC = 10.0

BASE_TAGS: dict[str, frozenset[str]] = {
    "Огонь": frozenset({"огонь"}),
    "Вода": frozenset({"вода"}),
    "Земля": frozenset({"земля"}),
    "Воздух": frozenset({"воздух"}),
}


def _norm(name: str) -> str:
    return name.strip().lower()


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((_norm(a), _norm(b))))  # type: ignore[return-value]


def _is_rate_limited(detail: object) -> bool:
    t = str(detail).lower()
    return "429" in t or "rate-limited" in t or "rate limit" in t


def _lookup_name(pool: dict[str, object], name: str) -> str | None:
    if name in pool:
        return name
    key = _norm(name)
    for known in pool:
        if _norm(known) == key:
            return known
    return None


def _jaccard_overlap(ta: frozenset[str], tb: frozenset[str]) -> float:
    if not ta and not tb:
        return 0.0
    union = ta | tb
    if not union:
        return 0.0
    return len(ta & tb) / len(union)


async def craft_once(e1: str, e2: str):
    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            print(f"  → попытка {attempt}/{MAX_ATTEMPTS}: {e1} + {e2}", flush=True)
            return await craft_service.craft_elements(e1, e2, settings.seed_user_id)
        except HTTPException as e:
            last_err = e
            print(f"  ! HTTP {e.status_code}: {e.detail}", flush=True)
            if e.status_code != 502 or attempt >= MAX_ATTEMPTS:
                raise
            delay = min(120.0, 20.0 * attempt) if _is_rate_limited(e.detail) else min(60.0, 5.0 * attempt)
            print(f"  … ждём {delay:.0f}с", flush=True)
            await asyncio.sleep(delay)
        except Exception as e:
            last_err = e
            print(f"  ! {type(e).__name__}: {e}", flush=True)
            if attempt >= MAX_ATTEMPTS:
                raise
            delay = min(60.0, 5.0 * attempt)
            print(f"  … ждём {delay:.0f}с", flush=True)
            await asyncio.sleep(delay)
    assert last_err is not None
    raise last_err


async def load_state() -> tuple[
    dict[str, int],
    dict[str, frozenset[str]],
    set[tuple[str, str]],
]:
    values: dict[str, int] = {n: 1 for n in BASE_TAGS}
    tags: dict[str, frozenset[str]] = dict(BASE_TAGS)
    done: set[tuple[str, str]] = set()

    async with async_session() as session:
        recipes = (await session.execute(select(Recipe).order_by(Recipe.id))).scalars().all()

    changed = True
    while changed:
        changed = False
        for r in recipes:
            if r.element_a.startswith("_base_"):
                continue
            key = _pair_key(r.element_a, r.element_b)
            done.add(key)
            if _norm(r.element_a) == _norm(r.element_b):
                continue
            ca = _lookup_name(values, r.element_a)
            cb = _lookup_name(values, r.element_b)
            if ca is None or cb is None:
                continue
            result = r.result.strip()
            if _lookup_name(values, result) is None:
                values[result] = values[ca] + values[cb]
                tags[result] = tags[ca] | tags[cb]
                changed = True
    return values, tags, done


def pick_next_pair(
    values: dict[str, int],
    tags: dict[str, frozenset[str]],
    done: set[tuple[str, str]],
) -> tuple[str, str] | None:
    """Один следующий крафт: рост max V или напарник того же V; макс. разнообразие тегов."""
    max_v = max(values.values())
    names = list(values.keys())

    def candidates(predicate) -> list[tuple[float, int, float, str, str]]:
        """Список (priority, sum_v, -overlap, a, b) — больше лучше."""
        out: list[tuple[float, int, float, str, str]] = []
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                if _norm(a) == _norm(b):
                    continue
                if _pair_key(a, b) in done:
                    continue
                if not predicate(a, b):
                    continue
                s = values[a] + values[b]
                overlap = _jaccard_overlap(tags[a], tags[b])
                # Сильный штраф за почти одинаковые стихии (вода+роса и т.п.)
                diversity = 1.0 - overlap
                out.append((diversity, s, -overlap, a, b))
        out.sort(reverse=True)
        return out

    at_max = [n for n, v in values.items() if v == max_v]
    # Уникальные по нормализованному имени
    seen: set[str] = set()
    tops: list[str] = []
    for n in sorted(at_max, key=lambda x: (-len(tags[x]), x)):
        k = _norm(n)
        if k in seen:
            continue
        seen.add(k)
        tops.append(n)

    if len(tops) >= 2:
        # Скрещиваем два max — самый быстрый скачок (2*max)
        pool = set(tops)
        ranked = candidates(lambda a, b: a in pool and b in pool)
        # Если все пары «слишком похожи», всё равно берём лучшую из tops
        if ranked:
            # Среди tops предпочитаем мин. overlap, сумма и так одинакова
            ranked.sort(key=lambda t: (t[2], t[0], t[1]), reverse=True)
            # t[2] is -overlap, higher = less overlap. Sort reverse on -overlap means less overlap first... 
            # Actually -overlap: less overlap → overlap 0 → -0=0; overlap 1 → -1. reverse=True puts 0 first. Good.
            _d, _s, _o, a, b = ranked[0]
            return a, b

    # Нужен напарник с V == max_v (чтобы потом скрестить)
    target_sum = max_v
    ranked = candidates(lambda a, b: values[a] + values[b] == target_sum)
    if ranked:
        # Сначала разнообразие, потом ок
        _d, _s, _o, a, b = ranked[0]
        # Если лучшая пара совсем гомогенная, а есть хоть чуть лучше по сумме на будущее —
        # для напарника оставляем diversity-first
        if _o > -0.99 or len(ranked) == 1:  # -overlap > -0.99 means overlap < 0.99
            return a, b
        return a, b

    # Fallback: любая пара, дающая новый рекорд или близко к нему
    ranked = candidates(lambda a, b: values[a] + values[b] >= max_v)
    if ranked:
        # Максимум суммы, затем разнообразие
        ranked.sort(key=lambda t: (t[1], t[0], t[2]), reverse=True)
        return ranked[0][3], ranked[0][4]

    ranked = candidates(lambda _a, _b: True)
    if not ranked:
        return None
    ranked.sort(key=lambda t: (t[1], t[0], t[2]), reverse=True)
    return ranked[0][3], ranked[0][4]


async def craft_and_track(
    e1: str,
    e2: str,
    values: dict[str, int],
    tags: dict[str, frozenset[str]],
    done: set[tuple[str, str]],
) -> None:
    if _norm(e1) == _norm(e2):
        raise RuntimeError(f"Запрещено A+A: {e1} + {e2}")
    c1 = _lookup_name(values, e1)
    c2 = _lookup_name(values, e2)
    assert c1 and c2
    v_new = values[c1] + values[c2]
    overlap = _jaccard_overlap(tags[c1], tags[c2])
    print(
        f"\n[{len(done) + 1}] {c1} (V={values[c1]}, {set(tags[c1])}) + "
        f"{c2} (V={values[c2]}, {set(tags[c2])}) → V={v_new} | overlap={overlap:.2f}",
        flush=True,
    )

    resp = await craft_once(c1, c2)
    done.add(_pair_key(c1, c2))
    name = resp.result.strip()
    canon = _lookup_name(values, name)
    if canon is None:
        values[name] = v_new
        tags[name] = tags[c1] | tags[c2]
        canon = name
    else:
        print(f"  ~ «{name}» уже был (V={values[canon]})", flush=True)

    img = settings.images_dir / Path(resp.image_url).name
    ok = img.exists() and img.stat().st_size > 0
    desc = resp.description or ""
    preview = desc if len(desc) <= 120 else desc[:120] + "…"
    print(f"  ✓ «{canon}» V={values[canon]} | img={'ok' if ok else 'MISSING'}", flush=True)
    print(f"    {preview}", flush=True)
    await asyncio.sleep(PAUSE_BETWEEN_CRAFTS_SEC)


async def main() -> int:
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY не задан", file=sys.stderr)
        return 1

    settings.images_dir.mkdir(exist_ok=True)
    await init_db()
    values, tags, done = await load_state()

    print(
        f"Старт: AIchemist, цель V>={TARGET_V}, модель={settings.llm_model}",
        flush=True,
    )
    print(
        f"Пул: {len(values)} имён, пар={len(done)}, max V={max(values.values())}",
        flush=True,
    )
    print(
        "⚠️ Free-модель/Pollinations могут rate-limit'ить — будут длинные паузы и ретраи.",
        flush=True,
    )

    while max(values.values()) < TARGET_V:
        nxt = pick_next_pair(values, tags, done)
        if nxt is None:
            print("Нет доступных разных пар", file=sys.stderr)
            return 2
        await craft_and_track(nxt[0], nxt[1], values, tags, done)

    ranked = sorted(values.items(), key=lambda x: (-x[1], x[0]))
    print("\n=== Пул ===", flush=True)
    for name, v in ranked:
        mark = " ★" if v >= TARGET_V else ""
        print(f"  V={v:4d}  {name}  {set(tags[name])}{mark}", flush=True)
    top, tv = ranked[0]
    print(f"\nГотово: крафтов≈{len(done)}, max V={tv} («{top}»)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
