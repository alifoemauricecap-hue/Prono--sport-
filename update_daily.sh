#!/usr/bin/env bash
# PRONO SPORT 2.0 — pipeline quotidien de rafraîchissement (cron-ready, GRATUIT)
set -euo pipefail
cd "$(dirname "$0")/backend"
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate
export PYTHONIOENCODING=utf-8
export DATABASE_URL="${DATABASE_URL:-sqlite:///$(pwd)/../data/prono_sport.db}"

echo "=== $(date -u '+%Y-%m-%d %H:%M UTC') — update PRONO SPORT ==="
python -m app.cli ingest-fduk-fixtures                 # prochains matchs + cotes du jour
python -m app.cli ingest-espn --leagues eng.1 eng.2 eng.3 eng.4 eng.5 esp.1 esp.2 ger.1 ger.2 ita.1 ita.2 fra.1 fra.2 por.1 ned.1 tur.1 bel.1 sco.1 gre.1 usa.1 ksa.1 bra.1 arg.1 --days-back 3 --days-ahead 2 || true
python -m app.cli sweep-stale                          # statuts périmés → UNKNOWN (jamais de score inventé)
python -m app.cli verify                               # vérification croisée multi-sources
python -m app.cli espn-media                           # logos nouveaux (équipes + ligues)
python -m app.cli compute-analytics                    # Elo + forme recalculés
python -m app.cli compute-predictions                  # modèles + value bets (purge auto)
echo "=== update terminé ==="
