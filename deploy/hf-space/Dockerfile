# PRONO SPORT 2.0 — image HUGGING FACE SPACES (port officiel : 7860)
# Le code est récupéré depuis TON dépôt GitHub (tu ne changes qu'UNE ligne ci-dessous).
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ====================================================================
# ⚠️ REMPLACE « TON-COMPTE » PAR TON NOM D'UTILISATEUR GITHUB ⚠️
# Exemple : si ton GitHub est https://github.com/koffi95/prono-sport
#           écris : https://github.com/koffi95/prono-sport.git
# ====================================================================
ARG REPO_URL=https://github.com/TON-COMPTE/prono-sport.git

WORKDIR /srv
RUN git clone --depth 1 "$REPO_URL" repo

WORKDIR /srv/repo/backend
RUN pip install --no-cache-dir -r requirements.txt \
    && chmod +x start_server.sh bootstrap_data.sh

ENV PYTHONIOENCODING=utf-8 \
    DATABASE_URL=sqlite:////srv/repo/data/prono_sport.db \
    AUTO_INGEST=1 AUTO_INGEST_SECONDS=300 \
    AUTO_LIVE=1 AUTO_LIVE_SECONDS=75 \
    AUTO_COMPUTE=1 AUTO_COMPUTE_SECONDS=3600 \
    PORT=7860

EXPOSE 7860
CMD ["./start_server.sh"]
