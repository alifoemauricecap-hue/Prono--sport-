"""Fusion des compétitions ORPHELINES (créées avant la table canonique) vers leur
code canonique interne (§5 entity resolution — un match = une compétition unique).

Règles :
- SP1-SP1  -> ESP-SP1   (fduk SP1, code canonique connu)
- SP2-SP2  -> ESP-SP2
- FDUK-SC2 -> SCO-SC2   (ajout DIVISIONS SC2/SC3)
- FDUK-SC3 -> SCO-SC3
Après réassignation des fixtures + mappings, l'orpheline vide est supprimée.
Aucune donnée inventée : on ne déplace que des enregistrements existants.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from app.config import DATABASE_URL  # noqa: E402
from app.db.base import make_engine, make_session_factory  # noqa: E402
from app.db.models import Competition, EntityMapping, Fixture, Prediction, ValueBet  # noqa: E402

MERGES = {
    "SP1-SP1": ("ESP-SP1", "La Liga", "Espagne"),
    "SP2-SP2": ("ESP-SP2", "La Liga 2", "Espagne"),
    "FDUK-SC2": ("SCO-SC2", "League One", "Écosse"),
    "FDUK-SC3": ("SCO-SC3", "League Two", "Écosse"),
}


def main() -> int:
    sf = make_session_factory(make_engine(DATABASE_URL))
    s = sf()
    for src_code, (dst_code, dst_name, dst_area) in MERGES.items():
        src = s.query(Competition).filter_by(code=src_code).one_or_none()
        if src is None:
            print(f"[skip] {src_code} inexistante")
            continue
        dst = s.query(Competition).filter_by(code=dst_code).one_or_none()
        if dst is None:
            dst = Competition(code=dst_code, name=dst_name, area=dst_area)
            s.add(dst)
            s.flush()
            print(f"[create] {dst_code}")
        n = s.query(Fixture).filter_by(competition_id=src.id).update(
            {Fixture.competition_id: dst.id}, synchronize_session=False)
        for m in s.query(EntityMapping).filter_by(
                entity_type="competition", entity_id=src.id).all():
            exists = s.query(EntityMapping).filter_by(
                entity_type="competition", entity_id=dst.id,
                provider=m.provider, provider_id=m.provider_id).one_or_none()
            if exists is None:
                m.entity_id = dst.id
            else:
                s.delete(m)
        s.query(Competition).filter_by(id=src.id).delete()
        s.commit()
        print(f"[merge] {src_code} -> {dst_code} : {n} fixtures réassignées")
    # garde-fou : liste des codes non canoniques restants
    from app.ingest.resolution import CANON_BY_PROVIDER_COMP
    canon_codes = {v["code"] for v in CANON_BY_PROVIDER_COMP.values()}
    leftovers = [c.code for c in s.query(Competition).all() if c.code not in canon_codes]
    print("codes hors canon restants:", sorted(leftovers))
    s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
