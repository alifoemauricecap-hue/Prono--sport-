from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        engine = create_engine(url, **kwargs)
        # WAL + busy_timeout : l'API lit pendant que les boucles auto écrivent (serveur 24/7).
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _sqlite_pragma(dbapi_conn, _rec):  # pragma: no cover - réglage runtime, testé via API
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        return engine
    return create_engine(url, **kwargs)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def ensure_schema(engine) -> None:
    """Migrations légères SQLite : crée les tables manquantes et ajoute les colonnes
    3.0 absentes dans une base 2.0 existante (create_all ne met jamais à jour).
    PostgreSQL : laisser Alembic/CREATE TABLE gérer (les colonnes sont new dans ce dépôt).
    """
    from sqlalchemy import inspect, text

    Base.metadata.create_all(engine)
    if not str(engine.url).startswith("sqlite"):
        return
    from sqlalchemy import select, func

    with engine.begin() as conn:
        insp = inspect(engine)
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            # nombre de lignes (une colonne NOT NULL ajoutée exige un DEFAULT si la table n'est pas vide)
            n_rows = conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar() or 0
            for col in table.columns:
                if col.name in existing or col.primary_key:
                    continue
                coltype = str(col.type).upper()
                if col.nullable:
                    ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                else:
                    # valeur neutre par type (jamais de donnée inventée : valeur nulle du type)
                    dflt = "0" if coltype in ("INTEGER", "FLOAT", "NUMERIC", "BOOLEAN") else "NULL"
                    ddl = (f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype} '
                           f'DEFAULT {dflt}')
                conn.execute(text(ddl))
