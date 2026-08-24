import os
import tempfile

# Base de test isolée — posée AVANT tout import de app.* (config lit l'env à l'import).
# Fichier temporaire (et non :memory:) car API/TestClient utilisent plusieurs connexions.
_TEST_DB = os.path.join(tempfile.gettempdir(), "prono_sport_pytest.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest

from app.db.base import Base, make_engine, make_session_factory
import app.db.models  # noqa: F401  (enregistre TOUTES les tables dans Base.metadata avant create_all)


@pytest.fixture()
def session():
    # StaticPool : une seule connexion :memory: partagée — create_all et la session
    # voient GARANTI la même base (sinon QueuePool peut router vers une connexion vierge).
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool, future=True)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    s = factory()
    yield s
    s.rollback()
    s.close()
