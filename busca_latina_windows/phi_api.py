"""PHI Latin Texts — acesso via Diogenes local (http://localhost:8888).

O site http://latin.packhum.org/ é inteiramente renderizado em JavaScript
(Scala Lift) e não é acessível com um scraper simples.  A forma correcta de
aceder aos dados PHI sem browser headless é através do Diogenes (Peter Heslin),
que serve o corpus PHI num servidor HTTP local na porta 8888.

Instalar e iniciar o Diogenes: https://d.iogen.es/d/
"""
import re
import urllib.request
import urllib.error
from pathlib import Path

DIOGENES_URL = "http://localhost:8888"

# ── catálogo hardcoded dos principais autores PHI (IDs PHI5) ─────────────────
# Fonte: PHI5 author numbers (Packard Humanities Institute corpus)

CATALOG: list[dict] = [
    {"autor": "Virgil",           "id": "0690", "obras": [
        {"titulo": "Aeneis",       "id": "001"},
        {"titulo": "Georgica",     "id": "002"},
        {"titulo": "Eclogae",      "id": "003"},
    ]},
    {"autor": "Cicero",           "id": "0474", "obras": [
        {"titulo": "De Re Publica",    "id": "001"},
        {"titulo": "De Legibus",       "id": "002"},
        {"titulo": "De Officiis",      "id": "003"},
        {"titulo": "De Amicitia",      "id": "004"},
        {"titulo": "De Senectute",     "id": "005"},
        {"titulo": "Tusculanae",       "id": "006"},
        {"titulo": "De Natura Deorum", "id": "007"},
        {"titulo": "De Divinatione",   "id": "008"},
        {"titulo": "De Fato",          "id": "009"},
        {"titulo": "Orationes",        "id": "010"},
    ]},
    {"autor": "Caesar",           "id": "0448", "obras": [
        {"titulo": "De Bello Gallico",   "id": "001"},
        {"titulo": "De Bello Civili",    "id": "002"},
    ]},
    {"autor": "Ovid",             "id": "0959", "obras": [
        {"titulo": "Metamorphoses",  "id": "006"},
        {"titulo": "Amores",         "id": "001"},
        {"titulo": "Ars Amatoria",   "id": "002"},
        {"titulo": "Fasti",          "id": "004"},
        {"titulo": "Tristia",        "id": "007"},
    ]},
    {"autor": "Horace",           "id": "0893", "obras": [
        {"titulo": "Carmina",     "id": "001"},
        {"titulo": "Epodi",       "id": "002"},
        {"titulo": "Sermones",    "id": "003"},
        {"titulo": "Epistulae",   "id": "004"},
        {"titulo": "Ars Poetica", "id": "005"},
    ]},
    {"autor": "Livy",             "id": "0914", "obras": [
        {"titulo": "Ab Urbe Condita I",    "id": "001"},
        {"titulo": "Ab Urbe Condita II",   "id": "002"},
        {"titulo": "Ab Urbe Condita III",  "id": "003"},
        {"titulo": "Ab Urbe Condita XXI",  "id": "021"},
        {"titulo": "Ab Urbe Condita XXII", "id": "022"},
    ]},
    {"autor": "Tacitus",          "id": "1351", "obras": [
        {"titulo": "Annales",    "id": "001"},
        {"titulo": "Historiae",  "id": "002"},
        {"titulo": "Germania",   "id": "003"},
        {"titulo": "Agricola",   "id": "004"},
        {"titulo": "Dialogus",   "id": "005"},
    ]},
    {"autor": "Sallust",          "id": "1320", "obras": [
        {"titulo": "Bellum Catilinae",  "id": "001"},
        {"titulo": "Bellum Iugurthinum","id": "002"},
    ]},
    {"autor": "Lucretius",        "id": "0550", "obras": [
        {"titulo": "De Rerum Natura", "id": "001"},
    ]},
    {"autor": "Catullus",         "id": "0472", "obras": [
        {"titulo": "Carmina", "id": "001"},
    ]},
    {"autor": "Pliny the Elder",  "id": "0978", "obras": [
        {"titulo": "Naturalis Historia", "id": "001"},
    ]},
    {"autor": "Pliny the Younger","id": "0901", "obras": [
        {"titulo": "Epistulae", "id": "001"},
        {"titulo": "Panegyricus", "id": "002"},
    ]},
    {"autor": "Seneca",           "id": "1017", "obras": [
        {"titulo": "Epistulae Morales",   "id": "001"},
        {"titulo": "De Beneficiis",       "id": "002"},
        {"titulo": "De Clementia",        "id": "003"},
        {"titulo": "Tragoediae",          "id": "004"},
    ]},
    {"autor": "Plautus",          "id": "0119", "obras": [
        {"titulo": "Amphitruo", "id": "001"},
        {"titulo": "Asinaria",  "id": "002"},
        {"titulo": "Aulularia", "id": "003"},
        {"titulo": "Miles Gloriosus", "id": "009"},
        {"titulo": "Pseudolus", "id": "014"},
    ]},
    {"autor": "Terence",          "id": "0156", "obras": [
        {"titulo": "Andria",         "id": "001"},
        {"titulo": "Hecyra",         "id": "002"},
        {"titulo": "Heautontimorumenos","id": "003"},
        {"titulo": "Eunuchus",       "id": "004"},
        {"titulo": "Phormio",        "id": "005"},
        {"titulo": "Adelphi",        "id": "006"},
    ]},
    {"autor": "Juvenal",          "id": "0837", "obras": [
        {"titulo": "Saturae", "id": "001"},
    ]},
    {"autor": "Martial",          "id": "0836", "obras": [
        {"titulo": "Epigrammata", "id": "001"},
    ]},
    {"autor": "Tibullus",         "id": "0660", "obras": [
        {"titulo": "Elegiae", "id": "001"},
    ]},
    {"autor": "Propertius",       "id": "0666", "obras": [
        {"titulo": "Elegiae", "id": "001"},
    ]},
    {"autor": "Lucan",            "id": "0917", "obras": [
        {"titulo": "Bellum Civile", "id": "001"},
    ]},
    {"autor": "Statius",          "id": "0003", "obras": [
        {"titulo": "Thebais",    "id": "001"},
        {"titulo": "Achilleis",  "id": "002"},
        {"titulo": "Silvae",     "id": "003"},
    ]},
    {"autor": "Quintilian",       "id": "1002", "obras": [
        {"titulo": "Institutio Oratoria", "id": "001"},
    ]},
    {"autor": "Suetonius",        "id": "1348", "obras": [
        {"titulo": "De Vita Caesarum", "id": "001"},
    ]},
    {"autor": "Apuleius",         "id": "0212", "obras": [
        {"titulo": "Metamorphoses",  "id": "001"},
        {"titulo": "Apologia",       "id": "002"},
        {"titulo": "Florida",        "id": "003"},
    ]},
    {"autor": "Varro",            "id": "0684", "obras": [
        {"titulo": "De Lingua Latina", "id": "001"},
        {"titulo": "Rerum Rusticarum", "id": "002"},
    ]},
    {"autor": "Columella",        "id": "0845", "obras": [
        {"titulo": "De Re Rustica", "id": "001"},
    ]},
    {"autor": "Velleius Paterculus","id":"1683","obras": [
        {"titulo": "Historiae Romanae", "id": "001"},
    ]},
]

# ── acesso ao Diogenes ────────────────────────────────────────────────────────

def diogenes_disponivel(timeout: int = 3) -> bool:
    """Verifica se o Diogenes está a correr em localhost:8888."""
    try:
        urllib.request.urlopen(f"{DIOGENES_URL}/", timeout=timeout)
        return True
    except Exception:
        return False


def _diog_fetch(path: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        f"{DIOGENES_URL}{path}",
        headers={"User-Agent": "Classicus/1.0", "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean_html(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<p[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    html = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), html)
    lines = [l.strip() for l in html.split("\n")]
    out, prev = [], True
    for l in lines:
        if not l:
            if not prev: out.append("")
            prev = True
        else:
            out.append(l); prev = False
    return "\n".join(out).strip()


def obter_texto(author_id: str, work_id: str) -> str:
    """Obtém texto via Diogenes.  Levanta RuntimeError se Diogenes offline."""
    if not diogenes_disponivel():
        raise RuntimeError(
            "PHI Latin requer o Diogenes em execução.\n"
            "Inicie o Diogenes e tente novamente.\n"
            f"Diogenes: {DIOGENES_URL}"
        )
    # Diogenes 4.x CGI pattern (tenta variantes comuns)
    paths = [
        f"/cgi-bin/diogenes.pl?JumpTo=phi:{author_id}:{work_id}&action=browser",
        f"/cgi-bin/diogenes.pl?corpus=phi&author_num={author_id}&work_num={work_id}&action=browser",
        f"/diogenes.cgi?JumpTo=phi:{author_id}:{work_id}",
    ]
    last_err = ""
    for path in paths:
        try:
            html = _diog_fetch(path)
            text = _clean_html(html)
            if len(text) > 100:
                return text
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"Não foi possível obter texto via Diogenes: {last_err}")


def obter_catalogo_flat() -> list[dict]:
    """Catálogo plano: [{display, autor_id, obra_id, edicao_urn}, ...]"""
    items = []
    for a in CATALOG:
        for o in a["obras"]:
            items.append({
                "display":    f"{a['autor']} — {o['titulo']}",
                "autor":      a["autor"],
                "obra":       o["titulo"],
                "autor_id":   a["id"],
                "obra_id":    o["id"],
                "edicao_urn": f"phi:{a['id']}/{o['id']}",
            })
    return items


def obter_obras_autor(autor_id: str) -> list[dict]:
    """Obras de um autor pelo PHI ID."""
    for a in CATALOG:
        if a["id"] == autor_id:
            return [{"titulo": o["titulo"], "id": o["id"]} for o in a["obras"]]
    return []
