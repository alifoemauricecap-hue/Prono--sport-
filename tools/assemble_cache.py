#!/usr/bin/env python3
"""Assembleur de cache (sandbox) : reconstruit les réponses brutes des sources
depuis les chunks fetchés, puis les écrit dans le cache providers (PS_CACHE_DIR).

Usage :
  python assemble_cache.py <job.json>
job.json : { "kind": "csv"|"json", "url": "...", "params": {...}|null,
             "parts": ["raw/E0-2526-0.txt", ...] }

Règle §1 : on ne transforme QUE des données réelles déjà obtenues ; aucun
contenu n'est inventé ici (seul le format markdown→CSV/JSON est normalisé).
"""
import json
import os
import sys

RAW_DIR = os.path.dirname(os.path.abspath(__file__))


def load_parts(names):
    out = []
    for n in names:
        p = os.path.join(RAW_DIR, n)
        with open(p, "r", encoding="utf-8") as f:
            out.append(f.read())
    return "".join(out)


def to_csv(md_text: str) -> str:
    """Tableau markdown GitHub (| a | b |) → CSV.

    Gère les lignes COUPÉES entre chunks : si la ligne accumulée est incomplète
    (moins de colonnes que l'en-tête), la ligne suivante — même si elle commence
    par '|' (le chunk s'est coupé juste avant/après un séparateur) — est FUSIONNÉE
    dans la ligne en cours.
    """
    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = None
    out = []
    cur = ""
    merged = 0

    def finalize(row):
        nonlocal header, out
        c = cells(row)
        if header is None:
            header = c
            out.append(",".join(header))
        elif all(x.startswith("-") and x for x in c):
            pass  # ligne de séparation ---
        elif len(c) == len(header):
            out.append(",".join(c))
        else:
            # ligne résiduelle incomplète (fin de fichier) → alignée
            print(f"  ⚠️ ligne incomplète {len(c)}/{len(header)} → alignée", file=sys.stderr)
            out.append(",".join((c + [""] * len(header))[: len(header)]))

    for ln in md_text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if not s.startswith("|"):
            if cur and header is not None and len(cells(cur)) < len(header):
                cur += s  # fragment de continuation d'une ligne tronquée
            else:
                if cur:
                    finalize(cur)
                cur = s  # début de nouvelle ligne (cellule coupée à la frontière)
            continue
        if cur and header is not None and len(cells(cur)) < len(header):
            n_cur = len(cells(cur))
            missing = len(header) - n_cur
            n_next = len(cells(s))
            # Un fragment de continuation porte ~`missing` cellules (±2 : certaines
            # lignes fduk sont réellement plus courtes en queue). Au-delà, la ligne
            # suivante est une ligne COMPLÈTE → on finalise la tronquée (padding).
            if n_next > missing + 2:
                print(f"  ⚠️ ligne tronquée ({n_cur}/{len(header)}) finalisée avec padding",
                      file=sys.stderr)
                finalize(cur)
                cur = s
                continue
            merged += 1
            cur += s
            continue
        if cur:
            finalize(cur)
        cur = s
    if cur:
        finalize(cur)
    if merged:
        print(f"  ({merged} fragment(s) de lignes coupées fusionnés)", file=sys.stderr)
    if not out:
        raise SystemExit("pas de tableau détecté")
    if len(out) < 2:
        raise SystemExit("aucune ligne de données")
    return "\n".join(out) + "\n"


def to_json(txt: str):
    t = txt.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1]
    if t.endswith("```"):
        t = t[: t.rfind("```")]
    return json.loads(t.strip())


def main():
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        job = json.load(f)

    # clé identique à app.providers.cache.cache_path_for
    sys.path.insert(0, os.path.join(os.path.dirname(RAW_DIR), "backend"))
    os.environ.setdefault("PS_CACHE_DIR", os.path.join(os.path.dirname(RAW_DIR), "data", "cache"))
    from app.providers.cache import cache_path_for  # noqa: E402

    text = load_parts(job["parts"])
    path = cache_path_for(job["url"], job.get("params"))
    assert path, "PS_CACHE_DIR non défini"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    if job["kind"] == "csv":
        csv_text = to_csv(text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(csv_text)
        print(f"CSV écrit : {os.path.basename(path)} ({len(csv_text)} octets)")
    else:
        data = to_json(text)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"JSON écrit : {os.path.basename(path)} (events={len(data.get('events', []))})")


if __name__ == "__main__":
    main()
