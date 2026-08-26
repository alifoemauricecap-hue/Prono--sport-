# PRONO SPORT 3.0 — image backend (build local GRATUIT : docker build ./backend)
FROM python:3.13-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY make_snapshot.py start_server.sh bootstrap_data.sh ./
RUN chmod +x start_server.sh bootstrap_data.sh

ENV PYTHONIOENCODING=utf-8 \
    DATABASE_URL=sqlite:////data/prono_sport.db \
    AUTO_INGEST=1 AUTO_LIVE=1 AUTO_COMPUTE=1
VOLUME ["/data"]
EXPOSE 8000

# start_server.sh : init-db idempotent + bootstrap auto si base vide + API sur ${PORT:-8000}
CMD ["./start_server.sh"]
