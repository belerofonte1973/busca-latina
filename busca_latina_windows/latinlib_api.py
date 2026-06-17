"""The Latin Library — local CLTK corpus + fallback online (thelatinlibrary.com)."""
import json
import re
import time
import urllib.request
from pathlib import Path

BASE   = "http://www.thelatinlibrary.com"
_CLTK  = Path.home() / "cltk_data" / "lat" / "text" / "lat_text_latin_library"
_CACHE = Path.home() / ".config" / "classicus"
_TTL   = 7 * 86400

# ── cache ─────────────────────────────────────────────────────────────────────

def _cp(name: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE / name

def _load(name: str):
    p = _cp(name)
    if p.exists() and time.time() - p.stat().st_mtime < _TTL:
        return json.loads(p.read_text("utf-8"))
    return None

def _save(name: str, data) -> None:
    _cp(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")

# ── fonte local ───────────────────────────────────────────────────────────────

def _nome_legivel(path: Path) -> str:
    """Converte nome de ficheiro num título legível."""
    stem = path.stem
    # ex: caes_gal → Caes Gal | cicero → Cicero
    return " ".join(w.capitalize() for w in re.split(r"[_\-\.]", stem))


def _cat_local(forcar: bool = False) -> list[dict] | None:
    """Catálogo a partir do CLTK local. None se não existir."""
    if not _CLTK.exists():
        return None
    key = "latinlib_local_cat.json"
    if not forcar and (c := _load(key)) is not None:
        return c
    obras = []
    # ficheiros .txt directamente na raiz → obras únicas (ex: catullus.txt)
    for f in sorted(_CLTK.glob("*.txt")):
        obras.append({
            "display":    _nome_legivel(f),
            "path":       str(f),
            "edicao_urn": f"latinlib:{f.name}",
            "tipo":       "local_file",
        })
    # directórios → agrupar como "Autor (N obras)"
    for d in sorted(_CLTK.iterdir()):
        if not d.is_dir():
            continue
        txts = sorted(d.glob("**/*.txt"))
        if not txts:
            continue
        nome = d.name.capitalize()
        if len(txts) == 1:
            obras.append({
                "display":    nome,
                "path":       str(txts[0]),
                "edicao_urn": f"latinlib:{d.name}/",
                "tipo":       "local_file",
            })
        else:
            obras.append({
                "display":    f"{nome}  ({len(txts)} obras)",
                "path":       str(d),
                "edicao_urn": f"latinlib:{d.name}/",
                "tipo":       "local_dir",
                "sub_paths":  [str(t) for t in txts],
            })
    _save(key, obras)
    return obras

# ── fonte online ──────────────────────────────────────────────────────────────

_SKIP_ONLINE = {
    "credits", "about these texts", "technical notes", "index",
    "epubs", "latin 101", "latin 102", "caesar's gallic wars",
    "cicero's phillipics", "livy's ab urbe condita",
    "sallust's bellum catilinae", "roman satire", "vergil's aeneid ii",
    "greek and roman historians", "imperialisms, ancient and modern",
    "roman law and society", "catullus:",
}

def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Classicus/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("latin-1", errors="replace")

def _links(html: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(
            r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>((?:[^<]|<(?!/?a[\s>]))+?)</a>',
            html, re.I | re.S):
        href = m.group(1).strip()
        txt  = re.sub(r"<[^>]+>", "", m.group(2))
        txt  = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append((href, txt))
    return out

def _full_url(href: str) -> str:
    if href.startswith("http"): return href
    if href.startswith("/"): return BASE + href
    return BASE + "/" + href

def _cat_online(forcar: bool = False) -> list[dict]:
    key = "latinlib_online_cat.json"
    if not forcar and (c := _load(key)) is not None:
        return c
    html = _fetch(BASE)
    autores = []
    seen: set[str] = set()
    for href, name in _links(html):
        if not name or name.lower() in _SKIP_ONLINE: continue
        if len(name) < 2 or len(name) > 60: continue
        url = _full_url(href)
        if url in seen: continue
        if not any(c.isalpha() for c in name): continue
        seen.add(url)
        autores.append({
            "display":    name,
            "url":        url,
            "edicao_urn": f"latinlib:{href.lstrip('/')}",
            "tipo":       "online_author",
        })
    _save(key, autores)
    return autores

def obter_obras_online(author_url: str) -> list[dict]:
    """Works for a given online author page."""
    html = _fetch(author_url)
    obras, seen = [], set()
    for href, name in _links(html):
        if not name or len(name) < 2: continue
        url = href if href.startswith("http") else _full_url(href)
        if "thelatinlibrary.com" not in url: continue
        if url in seen or url in (BASE, BASE + "/"): continue
        seen.add(url)
        obras.append({
            "display":    name,
            "url":        url,
            "edicao_urn": f"latinlib:{href.lstrip('/')}",
            "tipo":       "online_work",
        })
    return obras

# ── API pública ───────────────────────────────────────────────────────────────

def tem_local() -> bool:
    return _CLTK.exists()

def obter_catalogo(forcar: bool = False) -> list[dict]:
    """Catálogo completo: local CLTK (preferencial) ou online."""
    local = _cat_local(forcar)
    if local is not None:
        return local
    return _cat_online(forcar)

def _clean_text(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>",  " ", html, flags=re.S | re.I)
    html = re.sub(r"<(?:p|br|div|h[1-6])[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = (html.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">")
                .replace("&nbsp;"," ").replace("&#160;"," "))
    html = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), html)
    lines  = [l.strip() for l in html.split("\n")]
    out, prev_empty = [], True
    for line in lines:
        if not line:
            if not prev_empty: out.append("")
            prev_empty = True
        else:
            out.append(line); prev_empty = False
    return "\n".join(out).strip()

def obter_texto(item: dict) -> str:
    """Recupera o texto: local ou online conforme o tipo do item."""
    tipo = item.get("tipo", "")
    if tipo == "local_file":
        return Path(item["path"]).read_text(errors="replace").strip()
    if tipo == "local_dir":
        # Multiple files: retorna o primeiro (refs carregarão os outros)
        subs = item.get("sub_paths", [])
        if subs:
            return Path(subs[0]).read_text(errors="replace").strip()
        return ""
    # online
    url = item.get("url", "")
    if not url:
        return ""
    return _clean_text(_fetch(url))

def obter_sub_obras(item: dict) -> list[dict]:
    """Para um item 'local_dir', devolve lista de obras individuais."""
    if item.get("tipo") != "local_dir":
        return []
    d = Path(item["path"])
    return [{
        "display":    _nome_legivel(p),
        "path":       str(p),
        "edicao_urn": f"latinlib:{p.name}",
        "tipo":       "local_file",
    } for p in sorted(d.glob("**/*.txt"))]
