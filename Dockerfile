# PRONO SPORT 3.0 — image UNIVERSELLE (contexte de build = racine du repo)
# Fonctionne tel quel sur Back4App, Koyeb, et tout hébergeur Docker.
FROM python:3.13-slim

WORKDIR /srv/repo
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
RUN chmod +x backend/start_server.sh backend/bootstrap_data.sh

# Rendu par la plateforme (ex. Render : DATABASE_URL=sqlite:////data/prono_sport.db
# avec disque persistant monté sur /data). Sans variable, SQLite dans /srv/repo/data.
ENV PYTHONIOENCODING=utf-8 \
    DATABASE_URL=sqlite:////srv/repo/data/prono_sport.db \
    AUTO_INGEST=1 AUTO_INGEST_SECONDS=300 \
    AUTO_LIVE=1 AUTO_LIVE_SECONDS=75 \
    AUTO_COMPUTE=1 AUTO_COMPUTE_SECONDS=3600 \
    PORT=8000

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=300s --retries=3 \
    CMD sh -c "python -c 'import os,httpx;httpx.get(\"http://127.0.0.1:\"+os.environ.get(\"PORT\",\"8000\")+\"/v1/health\",timeout=4)'"

CMD ["backend/start_server.sh"]
