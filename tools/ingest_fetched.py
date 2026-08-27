#!/usr/bin/env python3
"""Ingestion des données RÉELLES fetchées (chunks fetch_page) → base PRONO SPORT.

Assemble les tableaux pipe (chunks fetch_page) en CSV, puis ingère via les
providers fduk (parse), et entraîne analytics + prédictions + value bets.

Usage :
  python ingest_fetched.py
"""
import os
import sys

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:////home/user/Prono--sport-/data/prono_sport.db",
)


def load(parts):
    out = []
    for n in parts:
        with open(os.path.join(RAW, n), "r", encoding="utf-8") as f:
            out.append(f.read())
    return "".join(out)


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def to_csv(md_text):
    header = None
    out = []
    cur = ""

    def finalize(row):
        nonlocal header, out
        c = cells(row)
        if header is None:
            header = c
            out.append(",".join(header))
        elif all(x.startswith("-") and x for x in c):
            pass
        elif len(c) == len(header):
            out.append(",".join(c))
        else:
            out.append(",".join((c + [""] * len(header))[: len(header)]))

    for ln in md_text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if not s.startswith("|"):
            if cur and header is not None and len(cells(cur)) < len(header):
                cur += s
            else:
                if cur:
                    finalize(cur)
                cur = s
            continue
        if cur and header is not None and len(cells(cur)) < len(header):
            n_cur = len(cells(cur))
            missing = len(header) - n_cur
            n_next = len(cells(s))
            if n_next > missing + 2:
                finalize(cur)
                cur = s
                continue
            cur += s
            continue
        if cur:
            finalize(cur)
        cur = s
    if cur:
        finalize(cur)
    if len(out) < 2:
        raise SystemExit("aucune ligne de données")
    return "\n".join(out) + "\n"


def main():
    import csv
    import io

    from app.db.base import Base, make_engine, make_session_factory
    import app.db.models  # noqa: F401  (registre toutes les tables)
    from app.config import DATABASE_URL
    from app.providers.football_data_uk import FootballDataUKProvider
    from app.ingest.service import run_ingestion

    eng = make_engine(DATABASE_URL)
    Base.metadata.create_all(eng)
    sf = make_session_factory(eng)
    provider = FootballDataUKProvider()

    # (div, season, [part files])
    jobs = [
        ("E0", "2526", ["E0-2526-0.txt", "E0-2526-1.txt", "E0-2526-2.txt", "E0-2526-3.txt"]),
        ("E0", "2627", ["E0-2627-0.txt", "E0-2627-1.txt"]),
        ("SP1", "2526", ["SP1-2526-0.txt", "SP1-2526-1.txt", "SP1-2526-2.txt", "SP1-2526-3.txt"]),
    ]

    total_created = 0
    for div, season, parts in jobs:
        csv_text = to_csv(load(parts))
        rows = 0
        with sf() as s:
            raws = list(provider.parse(csv_text, div=div, season=season,
                                       source_url=f"mmz4281/{season}/{div}.csv"))
            rep = run_ingestion(s, provider, raws)
            rows = len(raws)
        print(f"{div} {season}: {rows} lignes, created={rep.created} "
              f"updated={rep.updated} skipped={rep.skipped_unchanged} rejected={rep.rejected}")
        total_created += rep.created

    # fixtures.csv : matchs À VENIR + cotes actuelles
    csv_text = to_csv(load(["fixtures-0.txt"]))
    with sf() as s:
        raws = list(provider.parse_fixtures_csv(csv_text))
        rep = run_ingestion(s, provider, raws)
        print(f"fixtures.csv: {len(raws)} lignes, created={rep.created} "
              f"updated={rep.updated} skipped={rep.skipped_unchanged} rejected={rep.rejected}")

    # Analytics + prédictions + value bets
    from app.analytics.engine import compute_all
    from app.ml.engine import predict_upcoming
    with sf() as s:
        ar = compute_all(s)
        print(f"analytics: {ar.as_dict()}")
    with sf() as s:
        reports = predict_upcoming(s)
        for r in reports:
            print(f"predicte {r.competition_code}: {r.as_dict()}")
    print("INGESTION TERMINÉE")


if __name__ == "__main__":
    main()
