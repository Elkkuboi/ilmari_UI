"""Yöajon julkaisun tulkinta aiops-repon `apps/ilmari-selain/MUODOT.md`:n mukaan (kohdat 2, 3, 7 ja 8).

Kaikki kentät ovat valinnaisia ja tyyppitarkistettuja. Puuttuva tai vääräntyyppinen kenttä näkyy tilana "Ei saatavilla";
mitään ei päätellä eikä täydennetä. Tämä moduuli ei lue tiedostoja: se saa RunReaderin jo rajaamat ja jäsentämät arvot.

Lähteet (MUODOT.md):
- meta.json (kohta 2): alku (ISO-aika ilman aikavyöhykettä, työaseman paikallinen aika), malli, ctx, ajattelu, painopiste,
  suunnitelma, repo_commit, taso ("T0"/"T1"), virhe ja lopetus (syy, askelia, kesto_s, nollauksia).
- ehdotukset.jsonl (kohta 3): patka, askel, aika, otsikko, perustelu, ehdotus, tiedostot.
- sol-tulos.json (kohta 7): versio "aiops-sol-tulos-v1", malli, paattely, erat[] (era, ehdotukset, tila, selite,
  kustannus_eur, tuomiot[] (nro, tuomio, korjaus_tarpeen, perustelu, lahde, virhe)).
- Julkaisu (kohta 8): julkaisija takaa, että tuomion nro N viittaa ehdotukset.jsonl:n N:nteen riviin.

Tuomioluokat (aiops ADR-0011 kohta 12): T väite on totta ja otteet perustelevat sen; O totta, mutta ei virhe tai
korjattavaa; V väite on väärä otteiden perusteella; E otteet eivät riitä ratkaisemaan.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

HELSINKI = ZoneInfo("Europe/Helsinki")
SOL_VERSION = "aiops-sol-tulos-v1"
VERDICTS = ("T", "O", "V", "E")
VERDICT_LABELS = {
    "T": "Totta",
    "O": "Totta, ei korjattavaa",
    "V": "Väärä",
    "E": "Otteet eivät riitä",
}
TEXT_LIMIT = 4000
# Julkaisija jättää nämä pois, kun niitä ei ole (aiops scripts/julkaise.py, MUODOT.md kohta 8): puuttuminen ei ole virhe.
OPTIONAL_FILES = frozenset({"ehdotukset.jsonl", "sol-tulos.json", "luonnos.patch"})


def _text(value: Any, limit: int = TEXT_LIMIT) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and abs(value) < 1e9 else None  # ei NaN eikä ääretöntä


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def local_time(value: Any) -> datetime | None:
    """meta.json:n alku on työaseman paikallista aikaa ilman aikavyöhykettä (ilmari_yo.py), joten se on Helsingin aikaa."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=HELSINKI)


def _number_fi(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0")


def run_facts(run_id: str, meta: dict | None) -> dict[str, Any]:
    """Ajon yhteenveto meta.json:sta. Avaimet vastaavat Hubin aiempaa run_view-muotoa ja lisäkenttiä."""
    meta = meta if isinstance(meta, dict) else {}
    end = _dict(meta.get("lopetus"))
    started = local_time(meta.get("alku"))
    duration = _number(end.get("kesto_s"))
    ended = started + timedelta(seconds=duration) if started is not None and duration is not None and duration >= 0 else None

    model_parts = [p for p in (_text(meta.get("malli"), 60),) if p]
    ctx = _int(meta.get("ctx"))
    if model_parts and ctx is not None:
        model_parts.append(f"ctx {_number_fi(ctx)}")
    thinking = _text(meta.get("ajattelu"), 20)
    if model_parts and thinking:
        model_parts.append(f"ajattelu {thinking}")

    plan = _text(meta.get("suunnitelma"), 120)
    focus = _text(meta.get("painopiste"))
    first_line = focus.splitlines()[0] if focus else None
    title = plan or (first_line[:70] + "…" if first_line and len(first_line) > 70 else first_line) or run_id
    # ilmari_yo.py kirjoittaa "virhe": str(virhe), joten virheettömässä ajossa arvo on merkkijono "None".
    error = _text(meta.get("virhe"), 600)
    error = None if error == "None" else error

    level = meta.get("taso") if meta.get("taso") in ("T0", "T1") else None
    commit = meta.get("repo_commit")
    commit = commit[:12] if isinstance(commit, str) and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit) else None

    return {
        "title": title,
        "plan": plan,
        "focus": focus,
        "started_at": started,
        "ended_at": ended,
        "duration_s": duration,
        "model": " · ".join(model_parts) or None,
        "level": level,
        "stop_reason": _text(end.get("syy"), 80),
        "steps": _int(end.get("askelia")),
        "resets": _int(end.get("nollauksia")),
        "error": error,
        "commit": commit,
    }


def verdicts_by_number(sol: Any) -> dict[int, dict[str, Any]]:
    """Tuomiot ehdotusnumeron mukaan. Vain versio aiops-sol-tulos-v1 ja erät, joiden tila on "ok"."""
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(sol, dict) or sol.get("versio") != SOL_VERSION:
        return result
    for batch in sol.get("erat") if isinstance(sol.get("erat"), list) else []:
        if not isinstance(batch, dict) or batch.get("tila") != "ok" or not isinstance(batch.get("tuomiot"), list):
            continue
        for item in batch["tuomiot"]:
            if not isinstance(item, dict):
                continue
            number = _int(item.get("nro"))
            if number is None or number < 1 or number in result:
                continue
            verdict = item.get("tuomio") if item.get("tuomio") in VERDICTS else None
            result[number] = {
                "verdict": verdict,
                "label": VERDICT_LABELS.get(verdict) if verdict else "Ei tuomiota",
                "correction_needed": item.get("korjaus_tarpeen") if isinstance(item.get("korjaus_tarpeen"), bool) else None,
                "reason": _text(item.get("perustelu"), 600),
                "source": _text(item.get("lahde"), 300),
                "error": _text(item.get("virhe"), 80),
            }
    return result


def verdict_counts(sol: Any) -> dict[str, int] | None:
    found = verdicts_by_number(sol)
    if not found:
        return None
    counts = {key: 0 for key in VERDICTS}
    for item in found.values():
        if item["verdict"]:
            counts[item["verdict"]] += 1
    return counts


def proposals(lines: tuple | list, sol: Any) -> list[dict[str, Any]]:
    """ehdotukset.jsonl:n rivit järjestyksessä; rivi N saa Solin tuomion numero N (MUODOT.md kohta 8)."""
    verdicts = verdicts_by_number(sol)
    result = []
    for number, line in enumerate(lines, start=1):
        line = line if isinstance(line, dict) else {}
        files = line.get("tiedostot")
        files = [f for f in files if isinstance(f, str)][:5] if isinstance(files, list) else []
        result.append({
            "number": number,
            "title": _text(line.get("otsikko"), 200),
            "reasoning": _text(line.get("perustelu")),
            "proposal": _text(line.get("ehdotus")),
            "files": files,
            "segment": _text(line.get("patka"), 80),
            "step": _int(line.get("askel")),
            "time": local_time(line.get("aika")),
            "verdict": verdicts.get(number),
            "raw": line,
        })
    return result


def sol_summary(sol: Any) -> dict[str, Any] | None:
    """Solin tarkastuksen yhteenveto: malli, päättely, erät tiloineen ja tuomioiden määrät."""
    if not isinstance(sol, dict) or sol.get("versio") != SOL_VERSION:
        return None
    batches = []
    for batch in sol.get("erat") if isinstance(sol.get("erat"), list) else []:
        if not isinstance(batch, dict):
            continue
        numbers = batch.get("ehdotukset")
        numbers = [n for n in numbers if _int(n) is not None] if isinstance(numbers, list) else []
        batches.append({
            "batch": _int(batch.get("era")),
            "state": _text(batch.get("tila"), 40) or "tuntematon",
            "ok": batch.get("tila") == "ok",
            "numbers": numbers,
            "note": _text(batch.get("selite"), 300),
            "cost_eur": _text(batch.get("kustannus_eur"), 20),
        })
    return {
        "model": _text(sol.get("malli"), 60),
        "effort": _text(sol.get("paattely"), 20),
        "batches": batches,
        "counts": verdict_counts(sol),
    }


def relevant_errors(errors: tuple) -> tuple:
    """Lukuvirheet ilman valinnaisten tiedostojen normaalia puuttumista (code "not_found")."""
    return tuple(e for e in errors if not (getattr(e, "code", None) == "not_found" and getattr(e, "file", None) in OPTIONAL_FILES))
