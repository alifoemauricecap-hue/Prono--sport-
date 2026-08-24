"""Génère app/static/snapshot.html : l'interface PRONO SPORT autonome,
avec un instantané des données réelles de l'API encapsulé (visualisable hors-serveur).
Les logos (équipes + compétitions) sont téléchargés et inline en data-URI : l'aperçu
dans la conversation n'a pas d'accès réseau — sans cela ils resteraient invisibles."""
import base64
import concurrent.futures as cf
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("SNAPSHOT_BASE", "http://localhost:8000")
ROOT = Path(__file__).parent / "app" / "static"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


data = {
    "upcoming": get("/v1/fixtures?tab=upcoming&limit=400"),
    "live": get("/v1/fixtures?tab=live&limit=200"),
    "finished": get("/v1/fixtures?tab=finished&limit=80"),   # aperçu : les plus récents suffisent
    "competitions": get("/v1/competitions"),
    "health": get("/v1/health/providers"),
    "value_bets": get("/v1/value-bets?limit=200"),
}


# ---------- logos -> data URI ----------
def _collect_urls(node, out: set):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "logo_url" and isinstance(v, str) and v.startswith("http"):
                out.add(v)
            else:
                _collect_urls(v, out)
    elif isinstance(node, list):
        for it in node:
            _collect_urls(it, out)


def _fetch_datauri(url: str):
    """Télécharge un logo, le réduit à 64×64 (l'UI l'affiche à 40 px) et l'inline en
    data URI — sinon l'instantané pèserait des centaines de Mo et les logos resteraient
    invisibles dans l'aperçu sans réseau."""
    try:
        from PIL import Image
        import io as _io
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=8) as r:
            blob = r.read(2_000_000)
        if not blob:
            return url, None
        img = Image.open(_io.BytesIO(blob)).convert("RGBA")
        img.thumbnail((64, 64), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return url, "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return url, None  # en cas d'échec : URL externe conservée (dégradation gracieuse)


def _rewrite(node, mapping: dict):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "logo_url" and isinstance(v, str) and v in mapping:
                node[k] = mapping[v]
            else:
                _rewrite(v, mapping)
    elif isinstance(node, list):
        for it in node:
            _rewrite(it, mapping)


urls: set = set()
_collect_urls(data, urls)
mapping = {}
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for url, datauri in ex.map(_fetch_datauri, urls):
        if datauri:
            mapping[url] = datauri
_rewrite(data, mapping)
print(f"logos embarqués : {len(mapping)}/{len(urls)}")

# L'API renvoie count = total brut en base ; l'instantané n'embarque que `returned`
# cartes → aligner le compteur affiché avec le contenu réellement présent (§1 : pas de tromperie).
for tab in ("upcoming", "live", "finished"):
    data[tab]["count"] = len(data[tab]["fixtures"])

# ---------- M7 : fiches match pré-calculées (mode hors-ligne) ----------
# Les 45 prochains matchs AVEC prédiction → fiche complète incluse dans l'instantané.
from concurrent.futures import ThreadPoolExecutor

def _fx_for_report(fx):
    return fx["id"]

candidates = [f for f in data["upcoming"]["fixtures"] if f.get("prediction")][:45] \
    + [f for f in data["live"]["fixtures"]][:10]

def _load_report(fid):
    try:
        return fid, get(f"/v1/fixtures/{fid}/analysis")
    except Exception:
        return fid, None

reports = {}
with ThreadPoolExecutor(max_workers=8) as ex:
    for fid, rep in ex.map(_load_report, [_fx_for_report(f) for f in candidates]):
        if rep is not None:
            reports[fid] = rep
data["reports"] = reports
print(f"fiches M7 embarquées : {len(reports)} "
      f"(météo : {sum(1 for r in reports.values() if r.get('weather'))})")

html = (ROOT / "index.html").read_text(encoding="utf-8")

# Injection : une variable EMBED rend l'interface 100 % autonome (aucun réseau requis).
inject = "<script>\nconst EMBED = " + json.dumps(data, ensure_ascii=False) + ";\n</script>"
html = html.replace("<script>", inject + "\n<script>", 1)

# loadTab : EMBED d'abord, sinon fetch (comportement live inchangé sur le serveur).
html = html.replace(
    "const r = await fetch(url); const d = await r.json();",
    "const d = (typeof EMBED !== 'undefined' && EMBED[tab]) ? EMBED[tab] "
    ": await (await fetch(url)).json();",
)
# boot : compétitions + santé depuis EMBED si présent.
html = html.replace(
    "const [c, h] = await Promise.all([fetch('/v1/competitions'), fetch('/v1/health/providers')]);",
    "const embedMode = (typeof EMBED !== 'undefined');\n"
    "  const [c, h] = embedMode ? [{json: async () => EMBED.competitions}, {json: async () => EMBED.health}]"
    " : await Promise.all([fetch('/v1/competitions'), fetch('/v1/health/providers')]);",
)
html = html.replace(
    "refresh(); setInterval(refresh, 60000);",
    "refresh(); if (!(typeof EMBED !== 'undefined')) setInterval(refresh, 60000);",
)
# Mention instantané dans le pied de page.
stamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
html = html.replace(
    "<footer>PRONO SPORT",
    f"<footer>Instantané autonome — données réelles au {stamp}. Version live : panneau PRONO SPORT (auto-refresh).<br>PRONO SPORT",
)

(ROOT / "snapshot.html").write_text(html, encoding="utf-8")
print(json.dumps({
    "snapshot": str(ROOT / "snapshot.html"),
    "upcoming": data["upcoming"]["count"],
    "live": data["live"]["count"],
    "finished": data["finished"]["count"],
}, ensure_ascii=False))
