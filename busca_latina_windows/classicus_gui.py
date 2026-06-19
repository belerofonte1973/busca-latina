#!/usr/bin/env python3
"""Classicus — busca, análise morfológica e tradução de textos clássicos
Hebraico · Grego Antigo · Latim  →  Português Brasileiro
Offline via Ollama (qwen2.5:14b)  ·  Windows 11 ARM, PyQt6
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator

# ── caminhos ──────────────────────────────────────────────────────────────────

if sys.platform == "win32":
    _cfg_dir = Path(os.environ.get("APPDATA", Path.home())) / "Classicus"
else:
    _cfg_dir = Path.home() / ".config" / "classicus"

SETTINGS_FILE = _cfg_dir / "settings.json"
TM_DB_FILE    = _cfg_dir / "memoria_traducao.db"

_MONO  = "Consolas" if sys.platform == "win32" else "monospace"
_SERIF = "Georgia"  if sys.platform == "win32" else "serif"

MODELO_PADRAO   = "qwen2.5:14b"
OLLAMA_URL      = "http://localhost:11434"
OLLAMA_NUM_CTX  = 4096
OLLAMA_KEEP_ALV = "10m"

# ── PyQt6 ─────────────────────────────────────────────────────────────────────

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QSpinBox, QCheckBox,
    QSplitter, QListWidget, QListWidgetItem, QStatusBar, QFrame,
    QComboBox, QSlider, QInputDialog, QMessageBox, QTabWidget,
    QDialog, QDialogButtonBox, QFileDialog, QGroupBox, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu,
)
from PyQt6.QtCore  import Qt, QThread, pyqtSignal, QTimer, pyqtSlot, QObject
from PyQt6.QtGui   import (QFont, QTextCharFormat, QColor, QTextCursor,
                            QPalette, QAction)

# ── módulos opcionais do mesmo directório ─────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))

try:
    from memoria_traducao import MemoriaTraducao
    _TM_OK = True
except ImportError:
    _TM_OK = False

try:
    from pronunciar_latim import (pronunciar as _pronunciar_base, parar,
                                   ipa_classico,
                                   VOZES, VOZES_LATIM, VOZES_GREGO,
                                   VOZES_HEBRAICO)
    _PRONUNCIA_OK = True
except ImportError:
    _PRONUNCIA_OK = False
    VOZES = VOZES_LATIM = VOZES_GREGO = VOZES_HEBRAICO = []
    def parar(): pass
    def ipa_classico(t): return t

try:
    from pronunciar_latim import ipa_grego
except (ImportError, AttributeError):
    def ipa_grego(t): return t

try:
    from pronunciar_latim import baixar_modelo_piper
except (ImportError, AttributeError):
    baixar_modelo_piper = None

try:
    import perseus_api as _papi
    _PERSEUS_OK = True
except ImportError:
    _PERSEUS_OK = False

try:
    import sefaria_api as _sapi
    _SEFARIA_OK = True
except ImportError:
    _SEFARIA_OK = False

try:
    import latinlib_api as _llapi
    _LATINLIB_OK = True
except ImportError:
    _LATINLIB_OK = False

try:
    import phi_api as _phiapi
    _PHI_OK = True
except ImportError:
    _PHI_OK = False

try:
    import apibible_api as _abapi
    _APIBIBLE_OK = True
except ImportError:
    _APIBIBLE_OK = False

try:
    from gemini_lat import (traduzir_stream as _gemini_traduzir_stream,
                             MODELOS_GEMINI as _MODELOS_GEMINI)
    _GEMINI_OK = True
except ImportError:
    _GEMINI_OK = False
    _MODELOS_GEMINI = [
        ("gemini-2.5-flash", "Flash 2.5 — melhor qualidade, gratuito"),
        ("gemini-2.0-flash", "Flash 2.0 — rápido, gratuito"),
    ]

try:
    from claude_lat import (traduzir_stream as _claude_traduzir_stream,
                             MODELOS_CLAUDE as _MODELOS_CLAUDE)
    _CLAUDE_OK = True
except ImportError:
    _CLAUDE_OK = False
    _MODELOS_CLAUDE = [
        ("claude-haiku-4-5",  "Haiku 4.5  — rápido, económico"),
        ("claude-sonnet-4-6", "Sonnet 4.6 — melhor qualidade"),
    ]
    def _claude_traduzir_stream(t, l, m, k): return iter(["[claude_lat não disponível]"])

try:
    import traduzir_lat_grc as _trad
    _TRAD_OK = True
except ImportError:
    _TRAD_OK = False
    _trad = None

try:
    from nomes_pt import traduzir_catalogo as _traduzir_catalogo
    _NOMES_PT_OK = True
except ImportError:
    _NOMES_PT_OK = False
    def _traduzir_catalogo(cat): return cat

# ── chave Gemini (armazenada no settings.json do Classicus) ──────────────────

def _gemini_obter_chave() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return s.get("gemini_api_key", "").strip()
    except Exception:
        return ""

def _gemini_salvar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s["gemini_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(
        json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

def _claude_obter_chave() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return s.get("claude_api_key", "").strip() or None
    except Exception:
        return None

def _claude_guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s["claude_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(
        json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

# ── vozes Classicus (M/F explícito) ──────────────────────────────────────────

_VOZES_FALLBACK = {
    "la":  [
        ("it-IT-DiegoNeural",    "Diego — italiano masc. [online]",   "edge",   "M"),
        ("it-IT-IsabellaNeural", "Isabella — italiana fem. [online]",  "edge",   "F"),
        ("la",                   "espeak-ng latim [offline]",          "espeak", "M"),
    ],
    "grc": [
        ("el-GR-NestorasNeural", "Nestoras — grego masc. [online]",   "edge",   "M"),
        ("el-GR-AthinaNeural",   "Athina — grega fem. [online]",      "edge",   "F"),
        ("el",                   "espeak-ng grego [offline]",          "espeak", "M"),
    ],
    "hbo": [
        ("he-IL-AvriNeural",  "Avri — hebraico masc. [online]",   "edge",   "M"),
        ("he-IL-HilaNeural",  "Hila — hebraica fem. [online]",    "edge",   "F"),
        ("he",                "espeak-ng hebraico [offline]",      "espeak", "M"),
    ],
}

def _vozes_para_lingua(lingua: str) -> list[tuple]:
    mapa = {"la": VOZES_LATIM, "grc": VOZES_GREGO, "hbo": VOZES_HEBRAICO}
    lst = mapa.get(lingua, []) or []
    if lst:
        return [v[:4] if len(v) >= 4 else (*v, "M")[:4] for v in lst]
    return _VOZES_FALLBACK.get(lingua, _VOZES_FALLBACK["la"])

# ── prompts PT-BR ─────────────────────────────────────────────────────────────

_LINGUA_NOME = {"la": "latim", "grc": "grego antigo", "hbo": "hebraico bíblico"}

def _prompt_traduzir(lingua: str, texto: str) -> str:
    nome = _LINGUA_NOME.get(lingua, lingua)
    return (
        f"Você é um especialista em {nome} e em língua portuguesa. "
        f"Traduza o seguinte texto do {nome} para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Forneça apenas a tradução, sem comentários, transliteração ou notas.\n\n"
        f"Texto em {nome}:\n{texto.strip()}\n\nTradução para o português brasileiro:"
    )

def _prompt_morfo(lingua: str, texto: str) -> str:
    nome = _LINGUA_NOME.get(lingua, lingua)
    if lingua == "hbo":
        instrucao = (
            "Para cada palavra: raiz trilítera, classe gramatical, binyan (se verbo), "
            "tempo/pessoa/número/gênero (verbos) ou estado/número/gênero (nomes)."
        )
    elif lingua == "grc":
        instrucao = (
            "Para cada palavra: lema, classe gramatical, caso/número/gênero (nomes/adj) "
            "ou tempo/modo/voz/pessoa/número (verbos)."
        )
    else:
        instrucao = (
            "Para cada palavra: lema, classe gramatical, declinação/conjugação, "
            "caso/número/gênero (nomes/adj) ou tempo/modo/voz/pessoa/número (verbos)."
        )
    return (
        f"Você é um professor de {nome}. "
        f"Analise morfologicamente cada palavra do seguinte texto em {nome}. "
        f"{instrucao} "
        "Escreva em português brasileiro, uma linha por palavra.\n\n"
        f"Texto: {texto.strip()}\n\nAnálise morfológica:"
    )

def _prompt_sintatico(lingua: str, texto: str) -> str:
    nome = _LINGUA_NOME.get(lingua, lingua)
    return (
        f"Você é um professor de línguas clássicas. "
        f"Analise a estrutura sintática do seguinte trecho em {nome}. "
        "Identifique: sujeito, predicado, objetos direto e indireto, adjuntos, "
        "orações subordinadas e as principais relações gramaticais. "
        "Escreva em português brasileiro, de forma clara e didática.\n\n"
        f"Trecho em {nome}: {texto.strip()}\n\nAnálise sintática:"
    )

def _prompt_comentario(lingua: str, texto: str) -> str:
    nome = _LINGUA_NOME.get(lingua, lingua)
    return (
        f"Você é um professor de línguas clássicas. "
        f"Faça um comentário filológico breve (4–6 frases) do seguinte trecho em {nome}, "
        "em português brasileiro, cobrindo: estrutura gramatical, vocabulário notável e contexto literário.\n\n"
        f"Trecho: {texto.strip()}\n\nComentário:"
    )

# ── detecção de língua ────────────────────────────────────────────────────────

def _detectar_lingua(texto: str) -> str:
    heb = sum(1 for c in texto if 'א' <= c <= 'ת')
    grc = sum(1 for c in texto if 'Ͱ' <= c <= 'Ͽ' or 'ἀ' <= c <= '῿')
    lat = sum(1 for c in texto if c.isalpha() and ord(c) < 0x0300)
    total = heb + grc + lat or 1
    if heb / total >= 0.35: return "hbo"
    if grc / total >= 0.50: return "grc"
    return "la"

# ── Ollama — funções inline (PT-BR) ──────────────────────────────────────────

try:
    import requests as _req
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False
    _req = None  # type: ignore

def _ollama_modelos() -> list[str]:
    if not _REQUESTS_OK: return []
    try:
        r = _req.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []

def _ollama_stream(prompt: str, modelo: str | None) -> Iterator[str]:
    if not _REQUESTS_OK:
        yield "[requests não instalado — execute: pip install requests]"; return
    modelo = modelo or MODELO_PADRAO
    try:
        resp = _req.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "prompt": prompt, "stream": True,
                  "keep_alive": OLLAMA_KEEP_ALV,
                  "options": {"num_ctx": OLLAMA_NUM_CTX}},
            stream=True, timeout=(12, None),
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    break
    except _req.exceptions.ConnectionError:
        yield "\n[Ollama não está rodando — execute: ollama serve]"
    except Exception as e:
        yield f"\n[Erro: {e}]"

def _ollama_precarregar(modelo: str) -> bool:
    if not _REQUESTS_OK: return False
    try:
        r = _req.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "keep_alive": OLLAMA_KEEP_ALV,
                  "options": {"num_ctx": OLLAMA_NUM_CTX}},
            timeout=(10, 180),
        )
        return r.status_code == 200
    except Exception:
        return False

# ── separador visual ──────────────────────────────────────────────────────────

def _sep_v():
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken); return f

def _sep_h():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken); return f

# ─────────────────────────────────────────────────────────────────────────────
# THREADS
# ─────────────────────────────────────────────────────────────────────────────

class OllamaThread(QThread):
    chunk  = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, prompt: str, modelo: str | None):
        super().__init__()
        self._prompt = prompt
        self._modelo = modelo
        self._stop   = False

    def stop(self): self._stop = True

    def run(self):
        try:
            for frag in _ollama_stream(self._prompt, self._modelo):
                if self._stop: break
                self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class PrecarregarThread(QThread):
    pronto = pyqtSignal(str)
    falhou = pyqtSignal(str)

    def __init__(self, modelo: str):
        super().__init__()
        self._modelo = modelo

    def run(self):
        ok = _ollama_precarregar(self._modelo)
        if ok: self.pronto.emit(self._modelo)
        else:  self.falhou.emit(self._modelo)


class AlpheiosMorphThread(QThread):
    pronto = pyqtSignal(str, str)
    erro   = pyqtSignal(str)

    def __init__(self, word: str, lang: str):
        super().__init__()
        self._word = word.strip()
        self._lang = lang

    def run(self):
        try:
            if self._lang == "grc":
                params = urllib.parse.urlencode(
                    {"word": self._word, "lang": "grc", "engine": "morpheusgrc"})
                url = f"http://morph.alpheios.net/api/v1/analysis/word?{params}"
            else:
                params = urllib.parse.urlencode(
                    {"word": self._word, "lang": "lat", "engine": "morpheuslat"})
                url = (f"http://services.perseids.org/bsp/morphologyservice"
                       f"/analysis/word?{params}")
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read().decode("utf-8")
            self.pronto.emit(data, self._word)
        except Exception as e:
            self.erro.emit(str(e))


class AlpheiosLexThread(QThread):
    """Busca definição lexicográfica via Alpheios (LSJ para grc, L&S para lat)."""
    pronto = pyqtSignal(str, str)   # (definicao, lema)
    erro   = pyqtSignal(str)

    _LEX = {"grc": "lsj", "lat": "ls"}
    _URL = ("http://repos1.alpheios.net/exist/rest/db/xq/"
            "lexi-get.xq?lx={lx}&lg={lg}&out=html&l={l}")

    def __init__(self, lema: str, lang: str):
        super().__init__()
        self._lema = lema.strip()
        self._lang = lang

    @staticmethod
    def _limpar_html(html: str) -> str:
        import re
        html = re.sub(r"<[^>]+>", " ", html)
        html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#160;", " ")
        html = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), html)
        lines = [l.strip() for l in html.splitlines()]
        out, prev = [], True
        for l in lines:
            if not l:
                if not prev: out.append("")
                prev = True
            else:
                out.append(l); prev = False
        return "\n".join(out).strip()

    def run(self):
        lx = self._LEX.get(self._lang, "ls")
        url = self._URL.format(lx=lx, lg=self._lang,
                               l=urllib.parse.quote(self._lema))
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/html",
                                                       "User-Agent": "Classicus/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode("utf-8", errors="replace")
            texto = self._limpar_html(html)
            self.pronto.emit(texto, self._lema)
        except Exception as e:
            self.erro.emit(str(e))


def _alpheios_lema(json_text: str) -> str:
    """Extrai o primeiro lema da resposta JSON do Alpheios."""
    try:
        d = json.loads(json_text)
        body = d["RDF"]["Annotation"].get("Body", [])
        if isinstance(body, dict): body = [body]
        for b in body:
            entry = b.get("rest", {}).get("entry", {})
            hdwd = entry.get("dict", {}).get("hdwd", {})
            lema = hdwd.get("$", "") if isinstance(hdwd, dict) else str(hdwd)
            if lema: return lema
    except Exception:
        pass
    return ""


def _alpheios_parse(json_text: str) -> str:
    try:
        d = json.loads(json_text)
    except Exception:
        return "Resposta inválida."
    if "error" in d:
        err = d["error"]
        return f"API: {err.get('$', err) if isinstance(err, dict) else err}"
    try:
        body = d["RDF"]["Annotation"].get("Body", [])
    except (KeyError, TypeError):
        return "Estrutura inesperada."
    if isinstance(body, dict): body = [body]
    if not body: return "Sem análise disponível."
    _L = {"pofs":"classe","decl":"declinação","gend":"gênero","case":"caso",
          "num":"número","tense":"tempo","mood":"modo","voice":"voz",
          "pers":"pessoa","stemtype":"tipo de tema"}
    def val(o): return o.get("$","") if isinstance(o,dict) else str(o)
    lines = []
    for b in body:
        entry = b.get("rest",{}).get("entry",{})
        if not entry: continue
        di = entry.get("dict",{})
        hdwd = val(di.get("hdwd",{}))
        if hdwd: lines.append(f"Lema: {hdwd}")
        for k in ("pofs","decl","gend"):
            v = val(di.get(k,{}))
            if v: lines.append(f"  {_L.get(k,k)}: {v}")
        infls = entry.get("infl",[])
        if isinstance(infls,dict): infls=[infls]
        for infl in infls:
            parts = []
            for k in ("case","num","gend","pers","tense","mood","voice","stemtype"):
                v = val(infl.get(k,{}))
                if v: parts.append(f"{_L.get(k,k)}: {v}")
            if parts: lines.append("  → " + " | ".join(parts))
        lines.append("")
    return "\n".join(lines).strip() or "Sem análise disponível."


class PronunciaThread(QThread):
    erro = pyqtSignal(str)

    def __init__(self, texto: str, voz: str, variante: str, velocidade: int):
        super().__init__()
        self._texto      = texto
        self._voz        = voz
        self._variante   = variante
        self._velocidade = velocidade

    def run(self):
        if not _PRONUNCIA_OK: return
        try:
            _pronunciar_base(self._texto, self._voz,
                             self._variante, self._velocidade)
        except Exception as e:
            self.erro.emit(str(e))


class DownloadVozThread(QThread):
    progresso = pyqtSignal(str)
    pronto    = pyqtSignal()
    erro      = pyqtSignal(str)

    def __init__(self, voz: str):
        super().__init__()
        self._voz = voz

    def run(self):
        if baixar_modelo_piper is None:
            self.erro.emit("Download de vozes Piper não disponível."); return
        try:
            ok = baixar_modelo_piper(self._voz,
                                     progresso_cb=lambda m: self.progresso.emit(m))
            if ok: self.pronto.emit()
            else:  self.erro.emit(f"Falha ao baixar {self._voz}")
        except Exception as e:
            self.erro.emit(str(e))


class PercCatalogThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, lingua, forcar=False):
        super().__init__(); self._lingua=lingua; self._forcar=forcar
    def run(self):
        try: self.pronto.emit(_papi.obter_catalogo(self._lingua, forcar=self._forcar))
        except Exception as e: self.erro.emit(str(e))

class PercRefsThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, urn):
        super().__init__(); self._urn=urn
    def run(self):
        try: self.pronto.emit(_papi.obter_referencias(self._urn, nivel=1))
        except Exception as e: self.erro.emit(str(e))

class PercPassThread(QThread):
    pronto = pyqtSignal(str); erro = pyqtSignal(str)
    def __init__(self, urn):
        super().__init__(); self._urn=urn
    def run(self):
        try: self.pronto.emit(_papi.obter_passagem(self._urn))
        except Exception as e: self.erro.emit(str(e))

class ListarModelosThread(QThread):
    pronto = pyqtSignal(list)
    def run(self): self.pronto.emit(_ollama_modelos())


class SefariaThread(QThread):
    catalogo = pyqtSignal(list); refs = pyqtSignal(list)
    passagem = pyqtSignal(dict); erro = pyqtSignal(str)
    def __init__(self, modo, arg="", forcar=False):
        super().__init__(); self._modo=modo; self._arg=arg; self._forcar=forcar
    def run(self):
        try:
            if self._modo == "cat":
                self.catalogo.emit(_sapi.obter_catalogo(self._arg, forcar=self._forcar))
            elif self._modo == "refs":
                self.refs.emit(_sapi.obter_refs(self._arg))
            elif self._modo == "pass":
                self.passagem.emit(_sapi.obter_passagem(self._arg))
        except Exception as e: self.erro.emit(str(e))


# ── Latin Library threads ─────────────────────────────────────────────────────

class LatinLibCatThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, forcar=False): super().__init__(); self._forcar=forcar
    def run(self):
        try: self.pronto.emit(_llapi.obter_catalogo(self._forcar))
        except Exception as e: self.erro.emit(str(e))

class LatinLibObrasThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, item: dict): super().__init__(); self._item=item
    def run(self):
        try:
            tipo = self._item.get("tipo","")
            if tipo == "local_dir":
                self.pronto.emit(_llapi.obter_sub_obras(self._item))
            elif tipo == "online_author":
                self.pronto.emit(_llapi.obter_obras_online(self._item["url"]))
            else:
                self.pronto.emit([])
        except Exception as e: self.erro.emit(str(e))

class LatinLibTextThread(QThread):
    pronto = pyqtSignal(str); erro = pyqtSignal(str)
    def __init__(self, item: dict): super().__init__(); self._item=item
    def run(self):
        try: self.pronto.emit(_llapi.obter_texto(self._item))
        except Exception as e: self.erro.emit(str(e))


# ── PHI Latin threads ─────────────────────────────────────────────────────────

class PhiCatThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def run(self):
        try: self.pronto.emit(_phiapi.obter_catalogo_flat())
        except Exception as e: self.erro.emit(str(e))

class PhiTextThread(QThread):
    pronto = pyqtSignal(str); erro = pyqtSignal(str)
    def __init__(self, autor_id: str, obra_id: str):
        super().__init__(); self._aid=autor_id; self._oid=obra_id
    def run(self):
        try: self.pronto.emit(_phiapi.obter_texto(self._aid, self._oid))
        except Exception as e: self.erro.emit(str(e))


# ── API.Bible threads ─────────────────────────────────────────────────────────

class ApibibleBibliaThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, forcar=False): super().__init__(); self._forcar=forcar
    def run(self):
        try: self.pronto.emit(_abapi.listar_biblias_heb(self._forcar))
        except Exception as e: self.erro.emit(str(e))

class ApibibleLivrosThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, biblia_id: str): super().__init__(); self._bid=biblia_id
    def run(self):
        try: self.pronto.emit(_abapi.listar_livros(self._bid))
        except Exception as e: self.erro.emit(str(e))

class ApibibleCapsThread(QThread):
    pronto = pyqtSignal(list); erro = pyqtSignal(str)
    def __init__(self, biblia_id: str, livro_id: str):
        super().__init__(); self._bid=biblia_id; self._lid=livro_id
    def run(self):
        try: self.pronto.emit(_abapi.listar_capitulos(self._bid, self._lid))
        except Exception as e: self.erro.emit(str(e))

class ApibiblePassThread(QThread):
    pronto = pyqtSignal(dict); erro = pyqtSignal(str)
    def __init__(self, biblia_id: str, passagem_id: str):
        super().__init__(); self._bid=biblia_id; self._pid=passagem_id
    def run(self):
        try: self.pronto.emit(_abapi.obter_passagem(self._bid, self._pid))
        except Exception as e: self.erro.emit(str(e))


class GeminiThread(QThread):
    chunk  = pyqtSignal(str)
    status = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, texto: str, lingua: str, modelo: str, api_key: str):
        super().__init__()
        self._texto   = texto
        self._lingua  = lingua
        self._modelo  = modelo
        self._api_key = api_key
        self._stop    = False

    def stop(self): self._stop = True

    def run(self):
        if not _GEMINI_OK:
            self.erro.emit("gemini_lat não disponível — execute: pip install requests")
            return
        try:
            for frag in _gemini_traduzir_stream(
                    self._texto, self._lingua, self._modelo, self._api_key,
                    should_stop=lambda: self._stop):
                if self._stop:
                    break
                if isinstance(frag, str) and frag.startswith("\x01retry:"):
                    self.status.emit(frag[7:])
                else:
                    self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class ClaudeThread(QThread):
    chunk  = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, texto: str, lingua: str, modelo: str, api_key: str):
        super().__init__()
        self._texto   = texto
        self._lingua  = lingua
        self._modelo  = modelo
        self._api_key = api_key
        self._stop    = False

    def stop(self): self._stop = True

    def run(self):
        try:
            for frag in _claude_traduzir_stream(
                    self._texto, self._lingua, self._modelo, self._api_key):
                if self._stop:
                    break
                self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class InterlinearThread(QThread):
    pronto = pyqtSignal(list)   # lista de {'palavra': str, 'glosa': str}
    erro   = pyqtSignal(str)

    def __init__(self, texto: str, lingua: str):
        super().__init__()
        self._texto  = texto
        self._lingua = lingua

    def run(self):
        if not _TRAD_OK:
            self.erro.emit("traduzir_lat_grc não disponível"); return
        tokens = re.findall(r"[\wͰ-Ͽἀ-῿א-ת]+|[^\w\s]", self._texto)
        linhas = []
        for tok in tokens:
            if not tok.isalpha():
                linhas.append({"palavra": tok, "glosa": ""})
                continue
            glosa = ""
            try:
                if self._lingua == "la":
                    glosa = _trad.lookup_collatinus_pt(tok) or ""
                    if not glosa or glosa.startswith("(não encontrado)"):
                        glosa = (_trad.lookup_ls(tok, traduzir_pt=False) or "")[:120]
                elif self._lingua == "grc":
                    glosa = (_trad.lookup_lsj(tok, traduzir_pt=False) or "")[:120]
            except Exception:
                pass
            linhas.append({"palavra": tok, "glosa": glosa.strip()})
        self.pronto.emit(linhas)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — TEXTOS ONLINE
# ─────────────────────────────────────────────────────────────────────────────

class BuscaOnlineWidget(QWidget):
    texto_carregado = pyqtSignal(str, str, str)   # (texto, lingua, destino)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._obras           = []
        self._cat_thr         = None
        self._refs_thr        = None
        self._pass_thr        = None
        self._edicao_urn      = ""
        self._pron_thr        = None
        self._ultimo_texto    = ""
        self._reiniciar_timer = None
        self._sefaria_titulo  = ""
        # Latin Library
        self._ll_item         = {}   # item do catálogo LL seleccionado
        # PHI
        self._phi_autor_id    = ""
        self._phi_obra_id     = ""
        # API.Bible
        self._abiblia_id      = ""   # Bible version ID
        self._ab_livro_id     = ""   # Book ID
        self._alph_thr        = None
        self._lex_thr         = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(6)
        split = QSplitter(Qt.Orientation.Horizontal)

        # ── painel esquerdo ───────────────────────────────────────────────────
        left = QWidget(); ll = QVBoxLayout(left)
        ll.setContentsMargins(0,0,4,0); ll.setSpacing(4)

        fr = QHBoxLayout(); fr.addWidget(QLabel("Língua:"))

        self.combo_lingua_perc = QComboBox()
        _tem_lat = _PERSEUS_OK or _LATINLIB_OK or _PHI_OK
        if _PERSEUS_OK:
            self.combo_lingua_perc.addItem("Grego Antigo (grc)", "grc")
        if _tem_lat:
            self.combo_lingua_perc.addItem("Latim (lat)", "lat")
        if _SEFARIA_OK or _APIBIBLE_OK:
            self.combo_lingua_perc.addItem("Hebraico (hbo)", "hbo")
        if self.combo_lingua_perc.count() == 0:
            self.combo_lingua_perc.addItem("(módulos não encontrados)", "")
        self.combo_lingua_perc.currentIndexChanged.connect(self._on_lingua_mudada)
        fr.addWidget(self.combo_lingua_perc)

        fr.addWidget(_sep_v())
        fr.addWidget(QLabel("Fonte:"))
        self.combo_fonte = QComboBox(); self.combo_fonte.setMinimumWidth(160)
        self.combo_fonte.currentIndexChanged.connect(self._on_fonte_mudada)
        fr.addWidget(self.combo_fonte)

        # Categoria Sefaria (visível só para fonte=sefaria)
        self.combo_cat_sef = QComboBox()
        for cat in ["Tanakh","Talmud","Midrash","Halakhah","Liturgy"]:
            self.combo_cat_sef.addItem(cat, cat)
        self.combo_cat_sef.currentIndexChanged.connect(self._on_cat_sef_mudada)
        self.combo_cat_sef.hide()
        fr.addWidget(self.combo_cat_sef)

        # API.Bible: versão da Bíblia + chave (visíveis só para fonte=apibible)
        self.combo_biblia = QComboBox(); self.combo_biblia.setMinimumWidth(150)
        self.combo_biblia.currentIndexChanged.connect(self._on_biblia_mudada)
        self.combo_biblia.hide(); fr.addWidget(self.combo_biblia)

        self.btn_ab_chave = QPushButton("🔑 Chave")
        self.btn_ab_chave.setToolTip("Configurar chave gratuita da API.Bible (scripture.api.bible)")
        self.btn_ab_chave.clicked.connect(self._on_apibible_chave)
        self.btn_ab_chave.hide(); fr.addWidget(self.btn_ab_chave)

        fr.addStretch()
        btn_reload = QPushButton("⟳"); btn_reload.setFixedWidth(30)
        btn_reload.clicked.connect(lambda: self._carregar_catalogo(forcar=True))
        fr.addWidget(btn_reload); ll.addLayout(fr)

        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("Filtrar autor / obra…")
        self.filtro.textChanged.connect(self._filtrar)
        ll.addWidget(self.filtro)

        self.lista_obras = QListWidget()
        self.lista_obras.currentRowChanged.connect(self._on_obra_sel)
        ll.addWidget(self.lista_obras, 1)

        self.lbl_cat = QLabel(""); self.lbl_cat.setWordWrap(True)
        ll.addWidget(self.lbl_cat)
        left.setMinimumWidth(260); split.addWidget(left)

        # ── painel direito ────────────────────────────────────────────────────
        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(4,0,0,0); rl.setSpacing(4)

        self.lbl_obra = QLabel("<i>(nenhuma obra selecionada)</i>")
        self.lbl_obra.setWordWrap(True); rl.addWidget(self.lbl_obra)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Referência:"))
        self.combo_refs = QComboBox(); self.combo_refs.setMinimumWidth(120)
        self.combo_refs.currentIndexChanged.connect(self._carregar_passagem)
        ref_row.addWidget(self.combo_refs, 1); rl.addLayout(ref_row)

        self._vsplit_texto = QSplitter(Qt.Orientation.Vertical)

        self.texto_passagem = QTextEdit()
        self.texto_passagem.setReadOnly(True)
        self.texto_passagem.setFont(QFont(_SERIF, 11))
        self.texto_passagem.mouseDoubleClickEvent = self._on_dblclick_texto
        self._vsplit_texto.addWidget(self.texto_passagem)

        self.alph_panel = QTextEdit()
        self.alph_panel.setReadOnly(True)
        self.alph_panel.setFont(QFont(_MONO, 10))
        self.alph_panel.setPlaceholderText(
            "Alpheios — duplo clique numa palavra (grc/lat) para análise morfológica inline")
        self._vsplit_texto.addWidget(self.alph_panel)
        self._vsplit_texto.setSizes([500, 0])
        rl.addWidget(self._vsplit_texto, 1)

        # ── barra de ações ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_env_morfo = QPushButton("→ Morfologia")
        self.btn_env_morfo.setEnabled(False)
        self.btn_env_morfo.clicked.connect(self._env_morfo)
        btn_row.addWidget(self.btn_env_morfo)

        self.btn_env_trad = QPushButton("→ Tradução")
        self.btn_env_trad.setEnabled(False)
        self.btn_env_trad.clicked.connect(self._env_trad)
        btn_row.addWidget(self.btn_env_trad)

        self.btn_env_pron = QPushButton("→ Pronúncia")
        self.btn_env_pron.setEnabled(False)
        self.btn_env_pron.clicked.connect(self._env_pron)
        btn_row.addWidget(self.btn_env_pron)

        self.btn_alpheios = QPushButton("🏛 Alpheios")
        self.btn_alpheios.setEnabled(False)
        self.btn_alpheios.setToolTip(
            "Análise morfológica da palavra selecionada via Alpheios API (grc/lat)\n"
            "Atalho: duplo clique na palavra")
        self.btn_alpheios.clicked.connect(self._on_alpheios)
        btn_row.addWidget(self.btn_alpheios)

        btn_row.addStretch()
        self.lbl_pass_st = QLabel(""); btn_row.addWidget(self.lbl_pass_st)
        rl.addLayout(btn_row)

        # ── pronúncia rápida ──────────────────────────────────────────────────
        pr = QHBoxLayout(); pr.setSpacing(6)
        pr.addWidget(QLabel("Voz:"))
        self.combo_voz_b = QComboBox(); self.combo_voz_b.setMinimumWidth(260)
        pr.addWidget(self.combo_voz_b)
        self.btn_ouvir = QPushButton("🔊"); self.btn_ouvir.setFixedWidth(36)
        self.btn_ouvir.setEnabled(_PRONUNCIA_OK)
        self.btn_ouvir.clicked.connect(self._on_pronunciar)
        pr.addWidget(self.btn_ouvir)
        self.btn_parar_b = QPushButton("■"); self.btn_parar_b.setFixedWidth(28)
        self.btn_parar_b.setEnabled(_PRONUNCIA_OK)
        self.btn_parar_b.clicked.connect(self._parar)
        pr.addWidget(self.btn_parar_b)
        pr.addWidget(_sep_v()); pr.addWidget(QLabel("Velocidade:"))
        self.slider_vel_b = QSlider(Qt.Orientation.Horizontal)
        self.slider_vel_b.setRange(70,220); self.slider_vel_b.setValue(130)
        self.slider_vel_b.setFixedWidth(100)
        self.lbl_vel_b = QLabel("+0%")
        self.slider_vel_b.valueChanged.connect(
            lambda v: self.lbl_vel_b.setText(f"{v-130:+}%"))
        pr.addWidget(self.slider_vel_b); pr.addWidget(self.lbl_vel_b)
        pr.addStretch(); rl.addLayout(pr)

        split.addWidget(right); split.setSizes([280, 720])
        root.addWidget(split, 1)
        # Inicializar combo_fonte com a língua padrão
        lingua_inicial = self.combo_lingua_perc.currentData() or "grc"
        self._preencher_combo_fonte(lingua_inicial)
        self._atualizar_controles_fonte()
        self._atualizar_vozes_b()
        self._carregar_catalogo()

    # ── catálogo ──────────────────────────────────────────────────────────────

    def _fonte(self):
        return self.combo_fonte.currentData() or ""

    def _lingua_perc(self): return self.combo_lingua_perc.currentData() or "grc"

    def _preencher_combo_fonte(self, lingua: str) -> None:
        """Atualiza as opções do combo_fonte conforme a língua selecionada."""
        self.combo_fonte.blockSignals(True)
        self.combo_fonte.clear()
        if lingua == "grc":
            if _PERSEUS_OK:
                self.combo_fonte.addItem("Perseus", "perseus")
        elif lingua == "lat":
            if _PERSEUS_OK:
                self.combo_fonte.addItem("Perseus", "perseus")
            if _LATINLIB_OK:
                label = "Latin Library (local)" if _llapi.tem_local() else "Latin Library (online)"
                self.combo_fonte.addItem(label, "latinlib")
            if _PHI_OK:
                self.combo_fonte.addItem("PHI Latin (Diogenes)", "phi")
        elif lingua == "hbo":
            if _SEFARIA_OK:
                self.combo_fonte.addItem("Sefaria", "sefaria")
            if _APIBIBLE_OK:
                self.combo_fonte.addItem("API.Bible", "apibible")
        self.combo_fonte.blockSignals(False)

    def _atualizar_controles_fonte(self) -> None:
        """Mostra/oculta controlos secundários conforme a fonte."""
        fonte = self._fonte()
        lingua = self._lingua_perc()
        hbo = (lingua == "hbo")
        # Sefaria: categoria
        self.combo_cat_sef.setVisible(fonte == "sefaria")
        # API.Bible: versão + chave
        self.combo_biblia.setVisible(fonte == "apibible")
        self.btn_ab_chave.setVisible(fonte == "apibible")
        # Layout RTL apenas para hebraico
        self.texto_passagem.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if hbo
            else Qt.LayoutDirection.LeftToRight)

    def _on_lingua_mudada(self):
        lingua = self.combo_lingua_perc.currentData() or ""
        self._preencher_combo_fonte(lingua)
        self._atualizar_controles_fonte()
        self.filtro.clear(); self._obras = []
        self.combo_refs.clear(); self.texto_passagem.clear()
        self._set_botoes_passagem(False)
        self._atualizar_vozes_b()
        # Pré-carregar versões API.Bible se necessário
        if self._fonte() == "apibible" and not self.combo_biblia.count():
            self._carregar_biblias_api()
        else:
            self._carregar_catalogo()

    def _on_fonte_mudada(self):
        self._atualizar_controles_fonte()
        self.filtro.clear(); self._obras = []
        self.combo_refs.clear(); self.texto_passagem.clear()
        self._set_botoes_passagem(False)
        self._atualizar_vozes_b()
        fonte = self._fonte()
        if fonte == "apibible":
            if not self.combo_biblia.count():
                self._carregar_biblias_api()
            elif self.combo_biblia.currentData():
                self._carregar_catalogo()
        else:
            self._carregar_catalogo()

    def _on_cat_sef_mudada(self):
        self.filtro.clear(); self._obras = []
        self.combo_refs.clear(); self.texto_passagem.clear()
        self._set_botoes_passagem(False)
        self._carregar_catalogo()

    # ── carregar catálogo ─────────────────────────────────────────────────────

    def _carregar_catalogo(self, forcar=False):
        fonte = self._fonte()
        self.lista_obras.clear(); self.combo_refs.clear()
        self.texto_passagem.clear(); self._obras = []
        self._set_botoes_passagem(False)
        if not fonte:
            return
        if fonte == "perseus":
            self.lbl_cat.setText("⏳ Carregando catálogo Perseus…")
            self._cat_thr = PercCatalogThread(self._lingua_perc(), forcar)
            self._cat_thr.pronto.connect(self._on_cat_pronto)
            self._cat_thr.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ {e}"))
            self._cat_thr.start()
        elif fonte == "sefaria":
            cat = self.combo_cat_sef.currentData() or "Tanakh"
            self.lbl_cat.setText(f"⏳ Carregando Sefaria ({cat})…")
            t = SefariaThread("cat", cat, forcar)
            t.catalogo.connect(self._on_cat_pronto_sef)
            t.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ {e}"))
            self._cat_thr = t; t.start()
        elif fonte == "latinlib":
            self.lbl_cat.setText("⏳ Carregando Latin Library…")
            t = LatinLibCatThread(forcar)
            t.pronto.connect(self._on_cat_pronto)
            t.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ {e}"))
            self._cat_thr = t; t.start()
        elif fonte == "phi":
            self.lbl_cat.setText("⏳ Carregando catálogo PHI Latin…")
            t = PhiCatThread()
            t.pronto.connect(self._on_cat_pronto)
            t.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ {e}"))
            self._cat_thr = t; t.start()
        elif fonte == "apibible":
            bid = self.combo_biblia.currentData()
            if not bid:
                self.lbl_cat.setText("⚠ Selecione uma versão bíblica no combo acima.")
                return
            self.lbl_cat.setText(f"⏳ Carregando livros API.Bible…")
            t = ApibibleLivrosThread(bid)
            t.pronto.connect(self._on_cat_pronto_ab)
            t.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ API.Bible: {e}"))
            self._cat_thr = t; t.start()

    def _on_cat_pronto(self, obras):
        self._obras = _traduzir_catalogo(obras); self._filtrar(self.filtro.text())
        self.lbl_cat.setText(f"✓ {len(obras)} obras disponíveis.")

    def _on_cat_pronto_sef(self, obras):
        self._obras = obras; self._filtrar(self.filtro.text())
        self.lbl_cat.setText(f"✓ {len(obras)} textos disponíveis.")

    def _on_cat_pronto_ab(self, livros):
        obras = [{"display": l["nome"], "id": l["id"],
                  "edicao_urn": f"apibible:{l['id']}"} for l in livros]
        self._obras = obras; self._filtrar(self.filtro.text())
        self.lbl_cat.setText(f"✓ {len(obras)} livros disponíveis.")

    def _filtrar(self, q=""):
        self.lista_obras.blockSignals(True); self.lista_obras.clear()
        ql = q.lower()
        for o in self._obras:
            disp = o.get("display","")
            if not ql or ql in disp.lower():
                item = QListWidgetItem(disp)
                item.setData(Qt.ItemDataRole.UserRole, o)
                self.lista_obras.addItem(item)
        self.lista_obras.blockSignals(False)

    # ── API.Bible: Bíblias disponíveis ────────────────────────────────────────

    def _carregar_biblias_api(self):
        if not _APIBIBLE_OK: return
        key = _abapi.obter_chave()
        if not key:
            self.lbl_cat.setText(
                "⚠ API.Bible: configure a chave gratuita clicando em 🔑 Chave")
            return
        self.lbl_cat.setText("⏳ Carregando versões da API.Bible…")
        t = ApibibleBibliaThread()
        t.pronto.connect(self._on_biblias_prontas)
        t.erro.connect(lambda e: self.lbl_cat.setText(f"⚠ API.Bible: {e}"))
        self._cat_thr = t; t.start()

    def _on_biblias_prontas(self, biblias: list):
        self.combo_biblia.blockSignals(True); self.combo_biblia.clear()
        for b in biblias:
            self.combo_biblia.addItem(b["nome"], b["id"])
        self.combo_biblia.blockSignals(False)
        if biblias:
            self._carregar_catalogo()
        else:
            self.lbl_cat.setText("⚠ Nenhuma Bíblia hebraica disponível com esta chave.")

    def _on_biblia_mudada(self):
        self._abiblia_id = self.combo_biblia.currentData() or ""
        self._carregar_catalogo()

    def _on_apibible_chave(self):
        if not _APIBIBLE_OK: return
        atual = _abapi.obter_chave()
        nova, ok = QInputDialog.getText(
            self, "Chave API.Bible",
            "Cole a chave gratuita de scripture.api.bible:",
            text=atual or "")
        if ok and nova.strip():
            _abapi.guardar_chave(nova.strip())
            self.combo_biblia.clear()
            self._carregar_biblias_api()

    # ── obra selecionada ──────────────────────────────────────────────────────

    def _on_obra_sel(self, row):
        item = self.lista_obras.item(row)
        if not item: return
        obra = item.data(Qt.ItemDataRole.UserRole)
        if not obra: return
        # Bloquear sinais de thread anterior para evitar colisão entre autores
        if hasattr(self, '_refs_thr') and self._refs_thr is not None:
            self._refs_thr.blockSignals(True)
        self.combo_refs.clear(); self.combo_refs.addItem("(carregando…)","")
        self.lbl_pass_st.setText("Carregando…")
        fonte = self._fonte()
        self.lbl_obra.setText(f"<b>{obra.get('display','')}</b>")

        if fonte == "sefaria":
            self._sefaria_titulo = obra.get("titulo", obra.get("display",""))
            t = SefariaThread("refs", self._sefaria_titulo)
            t.refs.connect(self._on_sef_refs); t.erro.connect(self._on_refs_erro)
            self._refs_thr = t; t.start()

        elif fonte == "perseus":
            urn = obra.get("edicao_urn","")
            self._edicao_urn = urn
            self.lbl_obra.setText(
                f"<b>{obra.get('display','')}</b><br><small>{urn}</small>")
            t = PercRefsThread(urn)
            t.pronto.connect(self._on_perc_refs); t.erro.connect(self._on_refs_erro)
            self._refs_thr = t; t.start()

        elif fonte == "latinlib":
            tipo = obra.get("tipo","")
            self._ll_item = obra
            if tipo in ("local_dir", "online_author"):
                # Carregar sub-obras
                t = LatinLibObrasThread(obra)
                t.pronto.connect(self._on_ll_obras); t.erro.connect(self._on_refs_erro)
                self._refs_thr = t; t.start()
            else:
                # Ficheiro único: texto directo (sem refs intermédias)
                self.combo_refs.clear()
                self.combo_refs.addItem(obra.get("display","texto"), obra)
                self.lbl_pass_st.setText("✓ obra única.")

        elif fonte == "phi":
            self._phi_autor_id = obra.get("autor_id","")
            self._phi_obra_id  = obra.get("obra_id","")
            # PHI usa catálogo flat: refs = 1 entrada
            self.combo_refs.clear()
            self.combo_refs.addItem(obra.get("display", "texto completo"), obra)
            self.lbl_pass_st.setText("↵ Enter para carregar via Diogenes.")

        elif fonte == "apibible":
            self._ab_livro_id = obra.get("id","")
            bid = self._abiblia_id or self.combo_biblia.currentData() or ""
            if not bid:
                self.lbl_pass_st.setText("⚠ Selecione uma versão bíblica."); return
            t = ApibibleCapsThread(bid, self._ab_livro_id)
            t.pronto.connect(self._on_ab_caps); t.erro.connect(self._on_refs_erro)
            self._refs_thr = t; t.start()

    def _on_perc_refs(self, refs):
        self.combo_refs.blockSignals(True); self.combo_refs.clear()
        for urn in refs:
            self.combo_refs.addItem(_papi.label_referencia(urn), urn)
        self.combo_refs.blockSignals(False)
        self.lbl_pass_st.setText(f"✓ {len(refs)} referências.")
        if refs: self._carregar_passagem()

    def _on_sef_refs(self, refs):
        self.combo_refs.blockSignals(True); self.combo_refs.clear()
        for ref in refs:
            self.combo_refs.addItem(ref.split(" ")[-1], ref)
        self.combo_refs.blockSignals(False)
        self.lbl_pass_st.setText(f"✓ {len(refs)} capítulos.")
        if refs: self._carregar_passagem()

    def _on_ll_obras(self, obras):
        self.combo_refs.blockSignals(True); self.combo_refs.clear()
        for o in obras:
            self.combo_refs.addItem(o.get("display","?"), o)
        self.combo_refs.blockSignals(False)
        self.lbl_pass_st.setText(f"✓ {len(obras)} obras.")
        if obras: self._carregar_passagem()

    def _on_ab_caps(self, caps):
        self.combo_refs.blockSignals(True); self.combo_refs.clear()
        for c in caps:
            self.combo_refs.addItem(str(c.get("numero", c["id"])), c["id"])
        self.combo_refs.blockSignals(False)
        self.lbl_pass_st.setText(f"✓ {len(caps)} capítulos.")
        if caps: self._carregar_passagem()

    def _on_refs_erro(self, e):
        self.combo_refs.clear(); self.lbl_pass_st.setText(f"⚠ {e}")

    # ── carregar passagem ─────────────────────────────────────────────────────

    def _carregar_passagem(self):
        fonte = self._fonte()
        if fonte == "sefaria":
            ref = self.combo_refs.currentData()
            if not ref: return
            self.texto_passagem.setPlainText("⏳ Carregando…")
            t = SefariaThread("pass", ref); t.passagem.connect(self._on_sef_pass)
            t.erro.connect(self._on_pass_erro); self._pass_thr = t; t.start()

        elif fonte == "perseus":
            urn = self.combo_refs.currentData() or self._edicao_urn
            if not urn: return
            self.texto_passagem.setPlainText("⏳ Carregando…")
            t = PercPassThread(urn); t.pronto.connect(self._on_perc_pass)
            t.erro.connect(self._on_pass_erro); self._pass_thr = t; t.start()

        elif fonte == "latinlib":
            item = self.combo_refs.currentData()
            if item is None:
                item = self._ll_item
            if not item: return
            self.texto_passagem.setPlainText("⏳ Carregando…")
            t = LatinLibTextThread(item)
            t.pronto.connect(self._on_ll_texto)
            t.erro.connect(self._on_pass_erro); self._pass_thr = t; t.start()

        elif fonte == "phi":
            aid = self._phi_autor_id
            oid = self._phi_obra_id
            if not aid or not oid: return
            self.texto_passagem.setPlainText("⏳ Carregando via Diogenes…")
            t = PhiTextThread(aid, oid)
            t.pronto.connect(self._on_perc_pass)  # mesmo handler (texto puro)
            t.erro.connect(self._on_pass_erro); self._pass_thr = t; t.start()

        elif fonte == "apibible":
            pid = self.combo_refs.currentData()
            bid = self._abiblia_id or self.combo_biblia.currentData() or ""
            if not pid or not bid: return
            self.texto_passagem.setPlainText("⏳ Carregando…")
            t = ApibiblePassThread(bid, pid)
            t.pronto.connect(self._on_ab_pass)
            t.erro.connect(self._on_pass_erro); self._pass_thr = t; t.start()

    def _on_perc_pass(self, texto):
        self.texto_passagem.setPlainText(texto)
        self._ultimo_texto = texto
        self._set_botoes_passagem(bool(texto.strip()))
        self.lbl_pass_st.setText(f"✓ {len(texto.split())} palavras.")
        self.btn_alpheios.setEnabled(True)

    def _on_sef_pass(self, d):
        texto = d.get("texto_heb","")
        self.texto_passagem.setPlainText(texto)
        self._ultimo_texto = texto
        self._set_botoes_passagem(bool(texto.strip()))
        self.btn_alpheios.setEnabled(False)
        self.lbl_pass_st.setText(f"✓ {len(texto.split())} palavras.")

    def _on_ll_texto(self, texto):
        self.texto_passagem.setPlainText(texto)
        self._ultimo_texto = texto
        self._set_botoes_passagem(bool(texto.strip()))
        lingua = self._lingua_perc()
        self.btn_alpheios.setEnabled(lingua in ("la", "lat"))
        self.lbl_pass_st.setText(f"✓ {len(texto.split())} palavras.")

    def _on_ab_pass(self, d):
        texto = d.get("texto","")
        self.texto_passagem.setPlainText(texto)
        self._ultimo_texto = texto
        self._set_botoes_passagem(bool(texto.strip()))
        self.btn_alpheios.setEnabled(False)
        ref = d.get("ref","")
        self.lbl_pass_st.setText(f"✓ {ref} — {len(texto.split())} palavras.")

    def _on_pass_erro(self, e):
        self.texto_passagem.setPlainText(f"⚠ Erro: {e}")
        self.lbl_pass_st.setText("⚠ Erro.")

    def _set_botoes_passagem(self, ok):
        for b in (self.btn_env_morfo, self.btn_env_trad, self.btn_env_pron):
            b.setEnabled(ok)

    # ── envio para outras abas ────────────────────────────────────────────────

    def _texto_ativo(self):
        sel = self.texto_passagem.textCursor().selectedText().strip()
        return sel or self._ultimo_texto

    def _lingua_atual(self):
        return self.combo_lingua_perc.currentData() or "grc"

    def _env_morfo(self):
        t = self._texto_ativo()
        if t: self.texto_carregado.emit(t, self._lingua_atual(), "morfo")

    def _env_trad(self):
        t = self._texto_ativo()
        if t: self.texto_carregado.emit(t, self._lingua_atual(), "trad")

    def _env_pron(self):
        t = self._texto_ativo()
        if t: self.texto_carregado.emit(t, self._lingua_atual(), "pron")

    # ── Alpheios ──────────────────────────────────────────────────────────────

    def _on_alpheios(self):
        word = self.texto_passagem.textCursor().selectedText().strip().split()[0] \
               if self.texto_passagem.textCursor().selectedText().strip() else ""
        if not word:
            QMessageBox.information(self,"Alpheios","Selecione uma palavra no texto.")
            return
        lang = self._lingua_atual()
        if lang not in ("grc","la","lat"):
            QMessageBox.information(self,"Alpheios",
                "Alpheios suporta grego e latim.\nUse Ollama para hebraico."); return
        self.btn_alpheios.setEnabled(False)
        self.btn_alpheios.setText("⏳")
        t = AlpheiosMorphThread(word, "grc" if lang=="grc" else "lat")
        t.pronto.connect(self._on_alph_pronto)
        t.erro.connect(lambda e: (self.btn_alpheios.setEnabled(True),
                                  self.btn_alpheios.setText("🏛 Alpheios"),
                                  QMessageBox.warning(self,"Alpheios",e)))
        self._alph_thr = t; t.start()

    def _on_dblclick_texto(self, event):
        QTextEdit.mouseDoubleClickEvent(self.texto_passagem, event)
        lang = self._lingua_atual()
        if lang in ("grc", "la", "lat"):
            self._on_alpheios()

    def _on_alph_pronto(self, json_text, word):
        self.btn_alpheios.setEnabled(True); self.btn_alpheios.setText("🏛 Alpheios")
        resultado = _alpheios_parse(json_text)
        self.alph_panel.setPlainText(f"Alpheios — {word}\n\n{resultado}")
        sizes = self._vsplit_texto.sizes()
        total = sum(sizes)
        panel_h = min(200, max(140, total // 3))
        self._vsplit_texto.setSizes([total - panel_h, panel_h])
        # Dispara lookup lexicográfico com o lema detectado
        lema = _alpheios_lema(json_text)
        if lema:
            lang = self._lingua_atual()
            lg = "grc" if lang == "grc" else "lat"
            if self._lex_thr and self._lex_thr.isRunning():
                self._lex_thr.terminate()
            self._lex_thr = AlpheiosLexThread(lema, lg)
            self._lex_thr.pronto.connect(self._on_lex_pronto)
            self._lex_thr.erro.connect(lambda _: None)  # silencioso se léxico offline
            self._lex_thr.start()

    def _on_lex_pronto(self, definicao: str, lema: str):
        if not definicao.strip(): return
        atual = self.alph_panel.toPlainText()
        sep = "\n" + "─" * 40 + "\n"
        self.alph_panel.setPlainText(atual + sep + f"Léxico ({lema}):\n\n{definicao[:1200]}")

    # ── pronúncia ─────────────────────────────────────────────────────────────

    def _atualizar_vozes_b(self):
        l = self.combo_lingua_perc.currentData() or "grc"
        lingua = l if l == "hbo" else ("grc" if l == "grc" else "la")
        vozes = _vozes_para_lingua(lingua)
        self.combo_voz_b.blockSignals(True); self.combo_voz_b.clear()
        for vid,rot,*_ in vozes:
            self.combo_voz_b.addItem(rot, vid)
        self.combo_voz_b.blockSignals(False)

    def _on_pronunciar(self):
        if not _PRONUNCIA_OK: return
        sel = self.texto_passagem.textCursor().selectedText().strip()
        texto = sel or self._ultimo_texto[:3000]
        if not texto: return
        self._lancar_pronuncia(texto)

    def _lancar_pronuncia(self, texto):
        if self._pron_thr and self._pron_thr.isRunning():
            parar(); self._pron_thr.terminate(); self._pron_thr.wait(1500)
        self._ultimo_texto = texto
        voz = self.combo_voz_b.currentData() or "it-IT-DiegoNeural"
        velocidade = self.slider_vel_b.value() - 130
        self._pron_thr = PronunciaThread(texto, voz, "classico", velocidade)
        self._pron_thr.erro.connect(lambda e: self.lbl_pass_st.setText(f"Áudio: {e}"))
        self._pron_thr.start()

    def _parar(self):
        parar()
        if self._pron_thr and self._pron_thr.isRunning():
            self._pron_thr.terminate()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — MORFOLOGIA & SINTAXE
# ─────────────────────────────────────────────────────────────────────────────

class MorfologiaWidget(QWidget):
    def __init__(self, modelo_getter, status_cb, parent=None):
        super().__init__(parent)
        self._modelo_getter = modelo_getter
        self._status_cb     = status_cb
        self._ollama_thr    = None
        self._alph_thr      = None
        self._build()

    def set_texto(self, texto: str, lingua: str = ""):
        self.texto_in.setPlainText(texto)
        if lingua:
            idx = {"la":1,"grc":2,"hbo":3}.get(lingua, 0)
            self.combo_lingua_m.setCurrentIndex(idx)

    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(6)

        # ── barra de controles ────────────────────────────────────────────────
        bar = QHBoxLayout(); bar.setSpacing(6)
        bar.addWidget(QLabel("Língua:"))
        self.combo_lingua_m = QComboBox()
        for lbl, cod in [("Auto",""),("Latim","la"),
                          ("Grego Antigo","grc"),("Hebraico","hbo")]:
            self.combo_lingua_m.addItem(lbl, cod)
        bar.addWidget(self.combo_lingua_m)
        bar.addWidget(_sep_v())

        self.btn_morfo = QPushButton("🔬 Análise morfológica")
        self.btn_morfo.clicked.connect(self._on_morfo)
        bar.addWidget(self.btn_morfo)

        self.btn_sint = QPushButton("🌐 Análise sintática")
        self.btn_sint.clicked.connect(self._on_sint)
        bar.addWidget(self.btn_sint)

        self.btn_coment = QPushButton("📖 Comentário filológico")
        self.btn_coment.clicked.connect(self._on_coment)
        bar.addWidget(self.btn_coment)

        bar.addWidget(_sep_v())
        self.btn_alpheios_m = QPushButton("🏛 Alpheios (palavra)")
        self.btn_alpheios_m.setToolTip(
            "Selecione uma palavra no texto e clique para análise Alpheios (grc/lat)")
        self.btn_alpheios_m.clicked.connect(self._on_alpheios_m)
        bar.addWidget(self.btn_alpheios_m)

        self.btn_parar_m = QPushButton("⏹")
        self.btn_parar_m.setFixedWidth(30)
        self.btn_parar_m.clicked.connect(self._parar_ollama)
        bar.addWidget(self.btn_parar_m)
        bar.addStretch(); root.addLayout(bar)

        # ── splitter texto | análise ──────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)

        self.texto_in = QTextEdit()
        self.texto_in.setFont(QFont(_SERIF, 11))
        self.texto_in.setPlaceholderText(
            "Cole ou escreva o texto aqui.\n"
            "Clique duas vezes em uma palavra para análise rápida Alpheios (grc/lat).")
        self.texto_in.mouseDoubleClickEvent = self._on_dblclick
        vsplit.addWidget(self.texto_in)

        self.analise_out = QTextEdit()
        self.analise_out.setReadOnly(True)
        self.analise_out.setFont(QFont(_MONO, 10))
        self.analise_out.setPlaceholderText(
            "Resultado da análise morfológica / sintática aparece aqui.")
        vsplit.addWidget(self.analise_out)

        vsplit.setSizes([280, 320]); root.addWidget(vsplit, 1)

        nota = QLabel(
            "<small>Análise morfológica offline: Ollama + Gemma (todas as línguas). "
            "Alpheios: API online para grego e latim.</small>")
        nota.setWordWrap(True); root.addWidget(nota)

    def _lingua(self) -> str:
        cod = self.combo_lingua_m.currentData()
        if not cod:
            txt = self.texto_in.toPlainText()
            return _detectar_lingua(txt) if txt.strip() else "la"
        return cod

    def _texto(self) -> str:
        sel = self.texto_in.textCursor().selectedText().strip()
        return sel or self.texto_in.toPlainText().strip()

    def _iniciar_ollama(self, prompt: str, rotulo: str):
        if self._ollama_thr and self._ollama_thr.isRunning():
            self._ollama_thr.stop(); self._ollama_thr.wait(800)
        self.analise_out.setPlainText(f"⏳ {rotulo}…\n(Gemma pode demorar 20–60 s na 1ª chamada)")
        self._status_cb(f"{rotulo}…")
        modelo = self._modelo_getter()
        self._ollama_thr = OllamaThread(prompt, modelo)
        self._ollama_thr.chunk.connect(self._append_chunk)
        self._ollama_thr.done.connect(lambda: self._status_cb("✓ Análise concluída."))
        self._ollama_thr.erro.connect(lambda e: (
            self.analise_out.appendPlainText(f"\n⚠ Erro: {e}"),
            self._status_cb(f"⚠ {e}")))
        self._ollama_thr.start()

    def _append_chunk(self, frag):
        cur = self.analise_out.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.analise_out.setTextCursor(cur)
        self.analise_out.insertPlainText(frag)

    def _parar_ollama(self):
        if self._ollama_thr and self._ollama_thr.isRunning():
            self._ollama_thr.stop()
        self._status_cb("Interrompido.")

    def _on_morfo(self):
        txt = self._texto()
        if not txt.strip():
            self.analise_out.setPlainText("⚠ Nenhum texto para analisar."); return
        lingua = self._lingua()
        self._iniciar_ollama(_prompt_morfo(lingua, txt[:2000]), "Análise morfológica")

    def _on_sint(self):
        txt = self._texto()
        if not txt.strip():
            self.analise_out.setPlainText("⚠ Nenhum texto para analisar."); return
        lingua = self._lingua()
        self._iniciar_ollama(_prompt_sintatico(lingua, txt[:2000]), "Análise sintática")

    def _on_coment(self):
        txt = self._texto()
        if not txt.strip():
            self.analise_out.setPlainText("⚠ Nenhum texto para analisar."); return
        lingua = self._lingua()
        self._iniciar_ollama(_prompt_comentario(lingua, txt[:1500]), "Comentário filológico")

    def _on_dblclick(self, event):
        QTextEdit.mouseDoubleClickEvent(self.texto_in, event)
        word = self.texto_in.textCursor().selectedText().strip().split()[0] \
               if self.texto_in.textCursor().selectedText().strip() else ""
        if not word: return
        lingua = self._lingua()
        if lingua not in ("la", "grc"):
            return
        self._on_alpheios_m()

    def _on_alpheios_m(self):
        word = self.texto_in.textCursor().selectedText().strip().split()[0] \
               if self.texto_in.textCursor().selectedText().strip() else ""
        if not word:
            QMessageBox.information(self,"Alpheios","Selecione uma palavra no texto."); return
        lingua = self._lingua()
        if lingua not in ("la","grc"):
            QMessageBox.information(self,"Alpheios",
                "Alpheios funciona apenas com grego e latim.\n"
                "Para hebraico, use Análise morfológica (Ollama).")
            return
        self.btn_alpheios_m.setEnabled(False); self.btn_alpheios_m.setText("⏳")
        t = AlpheiosMorphThread(word, "grc" if lingua=="grc" else "lat")
        t.pronto.connect(self._on_alph_pronto_m)
        t.erro.connect(lambda e: (self.btn_alpheios_m.setEnabled(True),
                                  self.btn_alpheios_m.setText("🏛 Alpheios (palavra)"),
                                  self.analise_out.setPlainText(f"⚠ Alpheios: {e}")))
        self._alph_thr = t; t.start()

    def _on_alph_pronto_m(self, json_text, word):
        self.btn_alpheios_m.setEnabled(True)
        self.btn_alpheios_m.setText("🏛 Alpheios (palavra)")
        resultado = _alpheios_parse(json_text)
        self.analise_out.setPlainText(f"Alpheios — {word}\n\n{resultado}")
        self._status_cb(f"✓ Alpheios: {word}")
        # Lookup lexicográfico automático
        lema = _alpheios_lema(json_text)
        if lema:
            lingua = self._lingua()
            lg = "grc" if lingua == "grc" else "lat"
            if hasattr(self, "_lex_thr") and self._lex_thr and self._lex_thr.isRunning():
                self._lex_thr.terminate()
            self._lex_thr = AlpheiosLexThread(lema, lg)
            self._lex_thr.pronto.connect(self._on_lex_pronto_m)
            self._lex_thr.erro.connect(lambda _: None)
            self._lex_thr.start()

    def _on_lex_pronto_m(self, definicao: str, lema: str):
        if not definicao.strip(): return
        atual = self.analise_out.toPlainText()
        sep = "\n" + "─" * 40 + "\n"
        self.analise_out.setPlainText(atual + sep + f"Léxico ({lema}):\n\n{definicao[:1200]}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — TRADUÇÃO + MEMÓRIA DE TRADUÇÃO
# ─────────────────────────────────────────────────────────────────────────────

class TraducaoWidget(QWidget):
    def __init__(self, modelo_getter, status_cb, tm: "MemoriaTraducao | None", parent=None):
        super().__init__(parent)
        self._modelo_getter = modelo_getter
        self._status_cb     = status_cb
        self._tm            = tm
        self._ollama_thr         = None
        self._gemini_thr         = None
        self._claude_thr         = None
        self._interlinear_thr    = None
        self._ultimo_modelo_trad = MODELO_PADRAO
        self._tm_timer           = QTimer(self)
        self._tm_timer.setSingleShot(True)
        self._tm_timer.timeout.connect(self._buscar_tm)
        self._build()

    def set_texto(self, texto: str, lingua: str = ""):
        self.texto_src.setPlainText(texto)
        if lingua:
            idx = {"la":0,"grc":1,"hbo":2}.get(lingua, 0)
            self.combo_lingua_t.setCurrentIndex(idx)
        self._tm_timer.start(600)

    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(6)

        # ── barra de controles ────────────────────────────────────────────────
        bar = QHBoxLayout(); bar.setSpacing(6)
        bar.addWidget(QLabel("Língua:"))
        self.combo_lingua_t = QComboBox()
        for lbl, cod in [("Latim","la"),("Grego Antigo","grc"),("Hebraico","hbo")]:
            self.combo_lingua_t.addItem(lbl, cod)
        bar.addWidget(self.combo_lingua_t)
        bar.addWidget(_sep_v())

        bar.addWidget(QLabel("Modelo Ollama:"))
        self.combo_modelo_t = QComboBox(); self.combo_modelo_t.setMinimumWidth(180)
        self.combo_modelo_t.addItem(MODELO_PADRAO, MODELO_PADRAO)
        bar.addWidget(self.combo_modelo_t)

        self.btn_traduzir = QPushButton("🤖 Traduzir →PT-BR")
        self.btn_traduzir.clicked.connect(self._on_traduzir)
        bar.addWidget(self.btn_traduzir)

        self.btn_parar_t = QPushButton("⏹")
        self.btn_parar_t.setFixedWidth(30)
        self.btn_parar_t.clicked.connect(self._parar)
        bar.addWidget(self.btn_parar_t)
        bar.addWidget(_sep_v())

        self.btn_salvar_tm = QPushButton("💾 Salvar na MT")
        self.btn_salvar_tm.setToolTip("Salva o par (original → tradução) na Memória de Tradução")
        self.btn_salvar_tm.clicked.connect(self._salvar_tm)
        bar.addWidget(self.btn_salvar_tm)
        bar.addStretch(); root.addLayout(bar)

        # ── barra Gemini ──────────────────────────────────────────────────────
        bar2 = QHBoxLayout(); bar2.setSpacing(6)
        self.btn_gemini = QPushButton("🌟 Gemini →PT-BR")
        self.btn_gemini.setToolTip("Traduzir via API Gemini (online)")
        self.btn_gemini.clicked.connect(self._on_gemini_traduzir)
        bar2.addWidget(self.btn_gemini)

        self.combo_gemini_modelo = QComboBox()
        self.combo_gemini_modelo.setMinimumWidth(220)
        _gemini_default = "gemini-2.5-flash"
        _gemini_default_idx = 0
        for i, (mid, mlbl) in enumerate(_MODELOS_GEMINI):
            self.combo_gemini_modelo.addItem(f"{mid}  [{mlbl}]", mid)
            if mid == _gemini_default:
                _gemini_default_idx = i
        self.combo_gemini_modelo.setCurrentIndex(_gemini_default_idx)
        bar2.addWidget(self.combo_gemini_modelo)

        self.btn_gemini_chave = QPushButton("🔑 Chave")
        self.btn_gemini_chave.setToolTip("Configurar chave da API Gemini")
        self.btn_gemini_chave.clicked.connect(self._on_gemini_chave)
        bar2.addWidget(self.btn_gemini_chave)
        bar2.addStretch(); root.addLayout(bar2)

        # ── barra Claude ──────────────────────────────────────────────────────
        bar3 = QHBoxLayout(); bar3.setSpacing(6)
        self.btn_claude = QPushButton("🔷 Claude →PT-BR")
        self.btn_claude.setToolTip("Traduzir via API Claude / Anthropic (online)")
        self.btn_claude.clicked.connect(self._on_claude_traduzir)
        bar3.addWidget(self.btn_claude)

        self.combo_claude_modelo = QComboBox()
        self.combo_claude_modelo.setMinimumWidth(220)
        for mid, mlbl in _MODELOS_CLAUDE:
            self.combo_claude_modelo.addItem(f"{mid}  [{mlbl}]", mid)
        bar3.addWidget(self.combo_claude_modelo)

        self.btn_claude_chave = QPushButton("🔑 Chave")
        self.btn_claude_chave.setToolTip("Configurar chave da API Claude (Anthropic ou OpenRouter)")
        self.btn_claude_chave.clicked.connect(self._on_claude_chave)
        bar3.addWidget(self.btn_claude_chave)

        bar3.addWidget(_sep_v())
        self.btn_interlinear = QPushButton("📖 Interlinear (offline)")
        self.btn_interlinear.setToolTip("Tradução palavra-a-palavra via dicionários locais (Collatinus/LS/LSJ)")
        self.btn_interlinear.setEnabled(_TRAD_OK)
        self.btn_interlinear.clicked.connect(self._on_interlinear)
        bar3.addWidget(self.btn_interlinear)
        bar3.addStretch(); root.addLayout(bar3)

        # ── área principal ────────────────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)

        hsplit = QSplitter(Qt.Orientation.Horizontal)

        # fonte
        src_widget = QWidget(); sl = QVBoxLayout(src_widget)
        sl.setContentsMargins(0,0,0,0)
        sl.addWidget(QLabel("Texto original:"))
        self.texto_src = QTextEdit()
        self.texto_src.setFont(QFont(_SERIF, 11))
        self.texto_src.setPlaceholderText("Cole aqui o texto a traduzir.")
        self.texto_src.textChanged.connect(lambda: self._tm_timer.start(700))
        sl.addWidget(self.texto_src)
        hsplit.addWidget(src_widget)

        # tradução
        tgt_widget = QWidget(); tl = QVBoxLayout(tgt_widget)
        tl.setContentsMargins(0,0,0,0)
        tl.addWidget(QLabel("Tradução →PT-BR:"))
        self.texto_tgt = QTextEdit()
        self.texto_tgt.setFont(QFont(_SERIF, 11))
        self.texto_tgt.setReadOnly(False)
        self.texto_tgt.setPlaceholderText("Tradução aparece aqui (editável).")
        tl.addWidget(self.texto_tgt)
        hsplit.addWidget(tgt_widget)

        hsplit.setSizes([500, 500]); vsplit.addWidget(hsplit)

        # ── painel MT ─────────────────────────────────────────────────────────
        tm_panel = QWidget(); tml = QVBoxLayout(tm_panel)
        tml.setContentsMargins(0,4,0,0); tml.setSpacing(4)

        tm_hdr = QHBoxLayout()
        tm_hdr.addWidget(QLabel("<b>Memória de Tradução — sugestões:</b>"))
        tm_hdr.addStretch()

        self.btn_ver_tm = QPushButton("Gerenciar MT")
        self.btn_ver_tm.clicked.connect(self._ver_tm)
        tm_hdr.addWidget(self.btn_ver_tm)

        self.btn_exp_tmx = QPushButton("Exportar TMX")
        self.btn_exp_tmx.clicked.connect(self._exportar_tmx)
        tm_hdr.addWidget(self.btn_exp_tmx)

        self.btn_imp_tmx = QPushButton("Importar TMX")
        self.btn_imp_tmx.clicked.connect(self._importar_tmx)
        tm_hdr.addWidget(self.btn_imp_tmx)
        tml.addLayout(tm_hdr)

        self.lista_tm = QListWidget()
        self.lista_tm.setMaximumHeight(160)
        self.lista_tm.itemDoubleClicked.connect(self._usar_sugestao_tm)
        self.lista_tm.setToolTip("Clique duplo para usar a tradução sugerida.")
        tml.addWidget(self.lista_tm)

        self.lbl_tm_info = QLabel("")
        self.lbl_tm_info.setWordWrap(True); tml.addWidget(self.lbl_tm_info)
        vsplit.addWidget(tm_panel)

        vsplit.setSizes([380, 220]); root.addWidget(vsplit, 1)

    # ── tradução ──────────────────────────────────────────────────────────────

    def _lingua(self): return self.combo_lingua_t.currentData() or "la"

    def _on_traduzir(self):
        txt = self.texto_src.toPlainText().strip()
        if not txt:
            self.texto_tgt.setPlainText("⚠ Sem texto para traduzir."); return
        if self._ollama_thr and self._ollama_thr.isRunning():
            self._ollama_thr.stop(); self._ollama_thr.wait(800)
        lingua = self._lingua()
        modelo = self.combo_modelo_t.currentData() or MODELO_PADRAO
        self._ultimo_modelo_trad = modelo
        prompt = _prompt_traduzir(lingua, txt)
        self.texto_tgt.setPlainText(f"⏳ Traduzindo com {modelo}…\n")
        self._status_cb(f"Ollama traduzindo ({modelo})…")
        self._ollama_thr = OllamaThread(prompt, modelo)
        self._ollama_thr.chunk.connect(self._append_tgt)
        self._ollama_thr.done.connect(lambda: self._status_cb("✓ Tradução concluída."))
        self._ollama_thr.erro.connect(lambda e: (
            self.texto_tgt.appendPlainText(f"\n⚠ Erro: {e}"),
            self._status_cb(f"⚠ {e}")))
        self._ollama_thr.start()

    def _on_gemini_traduzir(self):
        txt = self.texto_src.toPlainText().strip()
        if not txt:
            self.texto_tgt.setPlainText("⚠ Sem texto para traduzir."); return
        key = _gemini_obter_chave()
        if not key:
            QMessageBox.warning(
                self, "Chave Gemini",
                "Chave da API Gemini não configurada.\n"
                "Clique em 🔑 Chave para inserir a chave.\n"
                "Obtenha gratuitamente em aistudio.google.com")
            return
        self._parar()
        lingua = self._lingua()
        modelo = self.combo_gemini_modelo.currentData() or "gemini-2.5-flash"
        self._ultimo_modelo_trad = modelo
        self.texto_tgt.setPlainText(f"⏳ Traduzindo com {modelo}…\n")
        self._status_cb(f"Gemini traduzindo ({modelo})…")
        self._gemini_thr = GeminiThread(txt, lingua, modelo, key)
        self._gemini_thr.chunk.connect(self._append_tgt)
        self._gemini_thr.status.connect(lambda m: self._status_cb(f"Gemini: {m}"))
        self._gemini_thr.done.connect(lambda: self._status_cb("✓ Tradução Gemini concluída."))
        self._gemini_thr.erro.connect(lambda e: (
            self.texto_tgt.appendPlainText(f"\n⚠ Erro Gemini: {e}"),
            self._status_cb(f"⚠ Gemini: {e}")))
        self._gemini_thr.start()

    def _on_gemini_chave(self):
        atual = _gemini_obter_chave()
        nova, ok = QInputDialog.getText(
            self, "Chave API Gemini",
            "Cole aqui a chave da API Gemini\n(obtenha em aistudio.google.com):",
            text=atual or "")
        if ok and nova.strip():
            _gemini_salvar_chave(nova.strip())
            self._status_cb("✓ Chave Gemini guardada.")

    def _on_claude_traduzir(self):
        txt = self.texto_src.toPlainText().strip()
        if not txt:
            self.texto_tgt.setPlainText("⚠ Sem texto para traduzir."); return
        key = _claude_obter_chave()
        if not key:
            QMessageBox.warning(
                self, "Chave Claude",
                "Chave da API Claude não configurada.\n"
                "Clique em 🔑 Chave para inserir a chave.\n"
                "Obtenha em console.anthropic.com (pago)\n"
                "ou use uma chave OpenRouter (sk-or-…) de openrouter.ai")
            return
        self._parar()
        lingua = self._lingua()
        modelo = self.combo_claude_modelo.currentData() or "claude-haiku-4-5"
        self._ultimo_modelo_trad = modelo
        self.texto_tgt.setPlainText(f"⏳ Traduzindo com Claude {modelo}…\n")
        self._status_cb(f"Claude traduzindo ({modelo})…")
        self._claude_thr = ClaudeThread(txt, lingua, modelo, key)
        self._claude_thr.chunk.connect(self._append_tgt)
        self._claude_thr.done.connect(lambda: self._status_cb("✓ Tradução Claude concluída."))
        self._claude_thr.erro.connect(lambda e: (
            self.texto_tgt.appendPlainText(f"\n⚠ Erro Claude: {e}"),
            self._status_cb(f"⚠ Claude: {e}")))
        self._claude_thr.start()

    def _on_claude_chave(self):
        atual = _claude_obter_chave() or ""
        nova, ok = QInputDialog.getText(
            self, "Chave API Claude",
            "Cole aqui a chave da API Claude:\n"
            "• Anthropic: sk-ant-… (console.anthropic.com)\n"
            "• OpenRouter: sk-or-… (openrouter.ai/keys)",
            text=atual)
        if ok and nova.strip():
            _claude_guardar_chave(nova.strip())
            self._status_cb("✓ Chave Claude guardada.")

    def _on_interlinear(self):
        txt = self.texto_src.toPlainText().strip()
        if not txt:
            self.texto_tgt.setPlainText("⚠ Sem texto para traduzir."); return
        lingua = self._lingua()
        if lingua == "hbo":
            self.texto_tgt.setPlainText("⚠ Tradução interlinear não disponível para Hebraico."); return
        self.texto_tgt.setPlainText("⏳ Consultando dicionários…")
        self._status_cb("Interlinear: a consultar dicionários…")
        self._interlinear_thr = InterlinearThread(txt, lingua)
        self._interlinear_thr.pronto.connect(self._on_interlinear_pronto)
        self._interlinear_thr.erro.connect(lambda e: (
            self.texto_tgt.setPlainText(f"⚠ Erro: {e}"),
            self._status_cb(f"⚠ {e}")))
        self._interlinear_thr.start()

    def _on_interlinear_pronto(self, linhas: list):
        linhas_fmt = []
        for item in linhas:
            p, g = item["palavra"], item["glosa"]
            if g:
                linhas_fmt.append(f"{p}\n  [{g}]")
            else:
                linhas_fmt.append(p)
        self.texto_tgt.setPlainText("\n".join(linhas_fmt))
        self._status_cb(f"✓ Interlinear: {len(linhas)} tokens.")

    def _append_tgt(self, frag):
        cur = self.texto_tgt.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.texto_tgt.setTextCursor(cur)
        self.texto_tgt.insertPlainText(frag)

    def _parar(self):
        if self._ollama_thr and self._ollama_thr.isRunning():
            self._ollama_thr.stop()
        if self._gemini_thr and self._gemini_thr.isRunning():
            self._gemini_thr.stop()
        if self._claude_thr and self._claude_thr.isRunning():
            self._claude_thr.stop()
        self._status_cb("Interrompido.")

    # ── memória de tradução ───────────────────────────────────────────────────

    def _buscar_tm(self):
        if not self._tm: return
        txt = self.texto_src.toPlainText().strip()
        if len(txt) < 10: self.lista_tm.clear(); return
        lingua = self._lingua()
        resultados = self._tm.buscar(lingua, txt, limite=5, limiar=0.35)
        self.lista_tm.clear()
        if not resultados:
            self.lista_tm.addItem("(nenhuma sugestão na memória de tradução)")
            return
        for r in resultados:
            pct = int(r["sim"] * 100)
            cor = "#00aa00" if pct>=85 else "#cc7700" if pct>=60 else "#888888"
            lbl = (f"[{pct}%] {r['data']} | "
                   f"SRC: {r['src'][:60]}{'…' if len(r['src'])>60 else ''} | "
                   f"TGT: {r['tgt'][:60]}{'…' if len(r['tgt'])>60 else ''}")
            item = QListWidgetItem(lbl)
            item.setForeground(QColor(cor))
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.lista_tm.addItem(item)
        n = self._tm.contar(lingua)
        self.lbl_tm_info.setText(
            f"MT: {len(resultados)} sugestão(ões) — "
            f"{n} entradas para {_LINGUA_NOME.get(lingua,lingua)}. "
            "Clique duplo para usar.")

    def _usar_sugestao_tm(self, item: QListWidgetItem):
        r = item.data(Qt.ItemDataRole.UserRole)
        if not r: return
        resposta = QMessageBox.question(
            self, "Usar sugestão da MT",
            f"Similaridade: {int(r['sim']*100)}%\n\n"
            f"SRC: {r['src'][:200]}\n\nTGT: {r['tgt'][:200]}\n\n"
            "Substituir a tradução atual por esta sugestão?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.texto_tgt.setPlainText(r["tgt"])

    def _salvar_tm(self):
        if not self._tm:
            QMessageBox.warning(self,"MT","Módulo de memória de tradução não disponível."); return
        src = self.texto_src.toPlainText().strip()
        tgt = self.texto_tgt.toPlainText().strip()
        if not src or not tgt:
            QMessageBox.warning(self,"MT","Preencha o texto original e a tradução."); return
        marcadores_erro = ("⚠","[Erro","[Ollama","⏳","[Sem")
        if any(tgt.startswith(m) for m in marcadores_erro):
            QMessageBox.warning(self,"MT","A tradução parece incompleta ou com erros."); return
        lingua = self._lingua()
        modelo = self._ultimo_modelo_trad or self.combo_modelo_t.currentData() or MODELO_PADRAO
        id_ = self._tm.salvar(lingua, src, tgt, modelo)
        self._status_cb(f"✓ Salvo na MT (id={id_}).")
        self._buscar_tm()

    def _ver_tm(self):
        if not self._tm:
            QMessageBox.warning(self,"MT","Módulo não disponível."); return
        dlg = GerenciarTMDialog(self._tm, self)
        dlg.exec()
        self._buscar_tm()

    def _exportar_tmx(self):
        if not self._tm: return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar TMX", "memoria_traducao.tmx",
            "TMX (*.tmx);;Todos (*)")
        if not path: return
        n = self._tm.exportar_tmx(Path(path))
        QMessageBox.information(self,"Exportar TMX",f"✓ {n} entradas exportadas para:\n{path}")

    def _importar_tmx(self):
        if not self._tm: return
        path, _ = QFileDialog.getOpenFileName(
            self,"Importar TMX","","TMX (*.tmx);;Todos (*)")
        if not path: return
        n = self._tm.importar_tmx(Path(path))
        QMessageBox.information(self,"Importar TMX",f"✓ {n} entradas importadas.")
        self._buscar_tm()

    def atualizar_modelos(self, modelos: list[str]):
        atual = self.combo_modelo_t.currentData()
        self.combo_modelo_t.blockSignals(True); self.combo_modelo_t.clear()
        if MODELO_PADRAO not in modelos:
            self.combo_modelo_t.addItem(f"{MODELO_PADRAO} (não instalado)",MODELO_PADRAO)
        for m in modelos:
            self.combo_modelo_t.addItem(m, m)
        for i in range(self.combo_modelo_t.count()):
            if self.combo_modelo_t.itemData(i) == atual:
                self.combo_modelo_t.setCurrentIndex(i); break
        self.combo_modelo_t.blockSignals(False)


# ── diálogo gerenciar MT ──────────────────────────────────────────────────────

class GerenciarTMDialog(QDialog):
    def __init__(self, tm: "MemoriaTraducao", parent=None):
        super().__init__(parent); self._tm = tm
        self.setWindowTitle("Gerenciar Memória de Tradução")
        self.resize(900, 500)
        self._build()
        self._carregar()

    def _build(self):
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Filtrar língua:"))
        self.combo_f = QComboBox()
        self.combo_f.addItem("Todas","")
        for cod,nom in [("la","Latim"),("grc","Grego"),("hbo","Hebraico")]:
            self.combo_f.addItem(nom,cod)
        self.combo_f.currentIndexChanged.connect(self._carregar)
        bar.addWidget(self.combo_f)
        bar.addStretch()
        btn_del = QPushButton("Apagar selecionado")
        btn_del.clicked.connect(self._apagar); bar.addWidget(btn_del)
        btn_clear = QPushButton("Limpar todos")
        btn_clear.clicked.connect(self._limpar_todos); bar.addWidget(btn_clear)
        lay.addLayout(bar)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["ID","Língua","Original","Tradução PT-BR","Data"])
        self.tabela.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.tabela.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self.tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.tabela, 1)

        self.lbl_total = QLabel(""); lay.addWidget(self.lbl_total)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.accept); lay.addWidget(bb)

    def _carregar(self):
        lingua = self.combo_f.currentData()
        rows = self._tm.listar(lingua or None, limite=500)
        self.tabela.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(r["id"])))
            self.tabela.setItem(i, 1, QTableWidgetItem(r["lingua"]))
            self.tabela.setItem(i, 2, QTableWidgetItem(r["texto_src"][:120]))
            self.tabela.setItem(i, 3, QTableWidgetItem(r["texto_tgt"][:120]))
            self.tabela.setItem(i, 4, QTableWidgetItem(r.get("criado_em","")[:10]))
        self.lbl_total.setText(
            f"Total: {self._tm.contar(lingua or None)} entradas.")

    def _apagar(self):
        row = self.tabela.currentRow()
        if row < 0: return
        id_ = int(self.tabela.item(row, 0).text())
        self._tm.apagar(id_)
        self._carregar()

    def _limpar_todos(self):
        lingua = self.combo_f.currentData() or None
        resp = QMessageBox.question(
            self, "Limpar MT",
            f"Apagar {'todas as entradas' if not lingua else f'entradas de {lingua}'}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resp == QMessageBox.StandardButton.Yes:
            self._tm.apagar_todos(lingua)
            self._carregar()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — PRONÚNCIA
# ─────────────────────────────────────────────────────────────────────────────

class PronunciaWidget(QWidget):
    def __init__(self, status_cb, parent=None):
        super().__init__(parent)
        self._status_cb   = status_cb
        self._pron_thr    = None
        self._dl_thr      = None
        self._ultimo_texto = ""
        self._reiniciar_timer = QTimer(self)
        self._reiniciar_timer.setSingleShot(True)
        self._reiniciar_timer.timeout.connect(self._reiniciar_pronuncia)
        self._build()

    def set_texto(self, texto: str, lingua: str = "la"):
        self.texto_pron.setPlainText(texto)
        idx = {"la":0,"grc":1,"hbo":2}.get(lingua, 0)
        self.combo_lingua_p.setCurrentIndex(idx)

    def _build(self):
        root = QVBoxLayout(self); root.setSpacing(8)

        # ── controles ─────────────────────────────────────────────────────────
        c1 = QHBoxLayout(); c1.setSpacing(8)
        c1.addWidget(QLabel("Língua:"))
        self.combo_lingua_p = QComboBox()
        for lbl,cod in [("Latim","la"),("Grego Antigo","grc"),("Hebraico","hbo")]:
            self.combo_lingua_p.addItem(lbl,cod)
        self.combo_lingua_p.currentIndexChanged.connect(self._on_lingua_mudada)
        c1.addWidget(self.combo_lingua_p)
        c1.addWidget(_sep_v())

        c1.addWidget(QLabel("Voz (sexo):"))
        self.combo_voz_p = QComboBox(); self.combo_voz_p.setMinimumWidth(300)
        c1.addWidget(self.combo_voz_p)

        self.btn_ouvir_p = QPushButton("🔊 Pronunciar")
        self.btn_ouvir_p.setEnabled(_PRONUNCIA_OK)
        self.btn_ouvir_p.clicked.connect(self._on_pronunciar)
        c1.addWidget(self.btn_ouvir_p)

        self.btn_parar_p = QPushButton("■ Parar")
        self.btn_parar_p.setFixedWidth(70)
        self.btn_parar_p.setEnabled(_PRONUNCIA_OK)
        self.btn_parar_p.clicked.connect(self._parar)
        c1.addWidget(self.btn_parar_p)
        c1.addStretch(); root.addLayout(c1)

        c2 = QHBoxLayout(); c2.setSpacing(8)
        c2.addWidget(QLabel("Velocidade:"))
        self.slider_vel_p = QSlider(Qt.Orientation.Horizontal)
        self.slider_vel_p.setRange(70, 220); self.slider_vel_p.setValue(130)
        self.slider_vel_p.setFixedWidth(140)
        self.slider_vel_p.setTickInterval(25)
        self.slider_vel_p.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.lbl_vel_p = QLabel("+0%")
        self.slider_vel_p.valueChanged.connect(self._on_velocidade_mudada)
        c2.addWidget(self.slider_vel_p); c2.addWidget(self.lbl_vel_p)
        c2.addWidget(_sep_v())

        # variante (latim: Clássico/Eclesiástico)
        self.grp_variante = QGroupBox("Variante")
        self.grp_variante.setFlat(True)
        gv = QHBoxLayout(self.grp_variante); gv.setContentsMargins(0,0,0,0)
        self.bg_var = QButtonGroup(self)
        self.rb_classico = QRadioButton("Clássico"); self.rb_classico.setChecked(True)
        self.rb_eclesiastico = QRadioButton("Eclesiástico")
        self.bg_var.addButton(self.rb_classico, 0)
        self.bg_var.addButton(self.rb_eclesiastico, 1)
        gv.addWidget(self.rb_classico); gv.addWidget(self.rb_eclesiastico)
        c2.addWidget(self.grp_variante); c2.addWidget(_sep_v())

        self.btn_ipa = QPushButton("IPA"); self.btn_ipa.setFixedWidth(50)
        self.btn_ipa.setToolTip("Exibe transcrição fonética IPA")
        self.btn_ipa.setEnabled(_PRONUNCIA_OK)
        self.btn_ipa.clicked.connect(self._on_ipa)
        c2.addWidget(self.btn_ipa)

        if baixar_modelo_piper is not None:
            self.btn_baixar_voz = QPushButton("⬇ Baixar voz offline")
            self.btn_baixar_voz.clicked.connect(self._on_baixar_voz)
            c2.addWidget(self.btn_baixar_voz)

        c2.addStretch(); root.addLayout(c2)

        root.addWidget(_sep_h())

        # ── texto ─────────────────────────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)

        txt_widget = QWidget(); tl = QVBoxLayout(txt_widget); tl.setContentsMargins(0,0,0,0)
        tl.addWidget(QLabel("Texto a pronunciar:"))
        self.texto_pron = QTextEdit()
        self.texto_pron.setFont(QFont(_SERIF, 12))
        self.texto_pron.setPlaceholderText(
            "Cole aqui o texto para ouvir a pronúncia.\n"
            "Pode também selecionar parte do texto para pronunciar apenas o trecho.")
        tl.addWidget(self.texto_pron)
        vsplit.addWidget(txt_widget)

        ipa_widget = QWidget(); il = QVBoxLayout(ipa_widget); il.setContentsMargins(0,0,0,0)
        il.addWidget(QLabel("Transcrição fonética IPA:"))
        self.ipa_out = QTextEdit()
        self.ipa_out.setReadOnly(True)
        self.ipa_out.setFont(QFont(_MONO, 11))
        self.ipa_out.setPlaceholderText("IPA aparece aqui após clicar em IPA.")
        il.addWidget(self.ipa_out)
        vsplit.addWidget(ipa_widget)
        vsplit.setSizes([320, 160]); root.addWidget(vsplit, 1)

        if not _PRONUNCIA_OK:
            aviso = QLabel(
                "<b>⚠ Módulo pronunciar_latim.py não encontrado.</b><br>"
                "Copie o arquivo do diretório original para ativar a pronúncia.")
            aviso.setStyleSheet("color:#cc4400;"); root.addWidget(aviso)

        self._atualizar_vozes_p()

    # ── vozes ─────────────────────────────────────────────────────────────────

    def _lingua_p(self): return self.combo_lingua_p.currentData() or "la"

    def _atualizar_vozes_p(self):
        lingua = self._lingua_p()
        vozes  = _vozes_para_lingua(lingua)
        atual  = self.combo_voz_p.currentData()
        self.combo_voz_p.blockSignals(True); self.combo_voz_p.clear()
        idx_sel = 0
        for i, (vid, rot, *rest) in enumerate(vozes):
            sexo = rest[1] if len(rest)>=2 else ("F" if "fem" in rot.lower() else "M")
            self.combo_voz_p.addItem(rot, vid)
            if vid == atual: idx_sel = i
        self.combo_voz_p.setCurrentIndex(idx_sel)
        self.combo_voz_p.blockSignals(False)
        self.grp_variante.setVisible(lingua == "la")

    def _on_lingua_mudada(self): self._atualizar_vozes_p()

    # ── pronúncia ─────────────────────────────────────────────────────────────

    def _texto_ativo(self) -> str:
        sel = self.texto_pron.textCursor().selectedText().strip()
        return sel if sel else self.texto_pron.toPlainText().strip()

    def _variante(self) -> str:
        return "eclesiastico" if self.bg_var.checkedId()==1 else "classico"

    def _on_pronunciar(self):
        if not _PRONUNCIA_OK:
            QMessageBox.warning(self,"Pronúncia","pronunciar_latim.py não encontrado."); return
        texto = self._texto_ativo()[:3000]
        if not texto: return
        self._lancar_pronuncia(texto)

    def _lancar_pronuncia(self, texto: str):
        if self._pron_thr and self._pron_thr.isRunning():
            parar(); self._pron_thr.terminate(); self._pron_thr.wait(1500)
        self._ultimo_texto = texto
        voz = self.combo_voz_p.currentData() or "it-IT-DiegoNeural"
        velocidade = self.slider_vel_p.value() - 130
        self._pron_thr = PronunciaThread(texto, voz, self._variante(), velocidade)
        self._pron_thr.erro.connect(lambda e: self._status_cb(f"⚠ Pronúncia: {e}"))
        self._pron_thr.start()
        self._status_cb(f"Pronunciando com {voz}…")

    def _parar(self):
        parar()
        if self._pron_thr and self._pron_thr.isRunning():
            self._pron_thr.terminate()
        self._ultimo_texto = ""
        self._status_cb("Pronúncia parada.")

    def _on_velocidade_mudada(self, v):
        self.lbl_vel_p.setText(f"{v-130:+}%")
        if self._ultimo_texto:
            self._reiniciar_timer.start(450)

    def _reiniciar_pronuncia(self):
        if self._ultimo_texto:
            self._lancar_pronuncia(self._ultimo_texto)

    def _on_ipa(self):
        if not _PRONUNCIA_OK: return
        texto = self._texto_ativo()[:300]
        if not texto: return
        lingua = self._lingua_p()
        if lingua == "grc":
            ipa = ipa_grego(texto)
            self.ipa_out.setPlainText(f"IPA (grego antigo reconstituído):\n{ipa}")
        else:
            ipa = ipa_classico(texto)
            self.ipa_out.setPlainText(f"IPA (clássico):\n{ipa}")

    def _on_baixar_voz(self):
        if baixar_modelo_piper is None: return
        voz = self.combo_voz_p.currentData()
        if not voz: return
        if self._dl_thr and self._dl_thr.isRunning(): return
        self._dl_thr = DownloadVozThread(voz)
        self._dl_thr.progresso.connect(self._status_cb)
        self._dl_thr.pronto.connect(lambda: QMessageBox.information(
            self,"Download","✓ Voz baixada com sucesso!"))
        self._dl_thr.erro.connect(lambda e: QMessageBox.warning(self,"Erro",e))
        self._dl_thr.start()
        self._status_cb(f"Baixando voz {voz}…")


# ─────────────────────────────────────────────────────────────────────────────
# JANELA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class Classicus(QMainWindow):
    def __init__(self):
        super().__init__()
        self._tm              = MemoriaTraducao(TM_DB_FILE) if _TM_OK else None
        self._precarregar_thr = None
        self._modelo_atual    = MODELO_PADRAO
        self._settings_timer  = QTimer(self); self._settings_timer.setSingleShot(True)
        self._settings_timer.timeout.connect(self._salvar_settings)
        self._build()
        self._carregar_settings()
        QTimer.singleShot(1500, self._iniciar_ollama)

    def _build(self):
        self.setWindowTitle("Classicus — Hebraico · Grego Antigo · Latim  →  PT-BR")
        self.resize(1280, 780)
        central = QWidget(); self.setCentralWidget(central)
        lay = QVBoxLayout(central); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)

        # ── barra superior: modelo Ollama ─────────────────────────────────────
        top = QHBoxLayout(); top.setContentsMargins(8,4,8,4); top.setSpacing(6)
        top.addWidget(QLabel("Modelo Ollama:"))
        self.combo_modelo_global = QComboBox(); self.combo_modelo_global.setMinimumWidth(200)
        self.combo_modelo_global.addItem(MODELO_PADRAO, MODELO_PADRAO)
        self.combo_modelo_global.currentIndexChanged.connect(self._on_modelo_global)
        top.addWidget(self.combo_modelo_global)

        self.btn_atualizar_ollama = QPushButton("⟳ Verificar Ollama")
        self.btn_atualizar_ollama.clicked.connect(self._iniciar_ollama)
        top.addWidget(self.btn_atualizar_ollama)

        self.lbl_ollama_st = QLabel("⏳ Verificando Ollama…")
        top.addWidget(self.lbl_ollama_st)
        top.addStretch()

        if self._tm:
            n = self._tm.contar()
            self.lbl_tm_cnt = QLabel(f"MT: {n} entradas")
            top.addWidget(self.lbl_tm_cnt)

        top_widget = QWidget(); top_widget.setLayout(top)
        lay.addWidget(top_widget)
        lay.addWidget(_sep_h())

        # ── abas ──────────────────────────────────────────────────────────────
        self.tabs = QTabWidget(); lay.addWidget(self.tabs, 1)

        # Tab 1: Textos Online
        self.w_busca = BuscaOnlineWidget(self)
        self.w_busca.texto_carregado.connect(self._rotear_texto)
        self.tabs.addTab(self.w_busca, "🔎 Textos Online")

        # Tab 2: Morfologia
        self.w_morfo = MorfologiaWidget(
            modelo_getter=self._modelo_global,
            status_cb=self._status_bar_msg)
        self.tabs.addTab(self.w_morfo, "🔬 Morfologia")

        # Tab 3: Tradução + MT
        self.w_trad = TraducaoWidget(
            modelo_getter=self._modelo_global,
            status_cb=self._status_bar_msg,
            tm=self._tm)
        self.tabs.addTab(self.w_trad, "📜 Tradução + MT")

        # Tab 4: Pronúncia
        self.w_pron = PronunciaWidget(status_cb=self._status_bar_msg)
        self.tabs.addTab(self.w_pron, "🔊 Pronúncia")

        # ── status bar ────────────────────────────────────────────────────────
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Pronto.")

    # ── roteador de texto entre abas ─────────────────────────────────────────

    def _rotear_texto(self, texto: str, lingua: str, destino: str):
        if destino == "morfo":
            self.w_morfo.set_texto(texto, lingua)
            self.tabs.setCurrentIndex(1)
        elif destino == "trad":
            self.w_trad.set_texto(texto, lingua)
            self.tabs.setCurrentIndex(2)
        elif destino == "pron":
            self.w_pron.set_texto(texto, lingua)
            self.tabs.setCurrentIndex(3)

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _modelo_global(self) -> str:
        return self.combo_modelo_global.currentData() or MODELO_PADRAO

    def _on_modelo_global(self):
        modelo = self._modelo_global()
        self._modelo_atual = modelo
        self._sincronizar_modelo_trad(modelo)
        self._precarregar_modelo(modelo)
        self._agenda_salvar_settings()

    def _sincronizar_modelo_trad(self, modelo: str):
        cb = self.w_trad.combo_modelo_t
        for i in range(cb.count()):
            if cb.itemData(i) == modelo:
                cb.setCurrentIndex(i); return

    def _iniciar_ollama(self):
        self._listar_thr = ListarModelosThread(self)
        self._listar_thr.pronto.connect(self._on_ollama_modelos)
        self._listar_thr.start()

    @pyqtSlot(list)
    def _on_ollama_modelos(self, mods: list):
        self.combo_modelo_global.blockSignals(True)
        atual = self.combo_modelo_global.currentData()
        self.combo_modelo_global.clear()
        if not mods:
            self.combo_modelo_global.addItem(MODELO_PADRAO, MODELO_PADRAO)
            self.lbl_ollama_st.setText("⚠ Ollama não responde — execute: ollama serve")
        else:
            if MODELO_PADRAO not in mods:
                self.combo_modelo_global.addItem(
                    f"{MODELO_PADRAO} (não instalado)", MODELO_PADRAO)
            for m in mods:
                self.combo_modelo_global.addItem(m, m)
            idx_sel = 0
            for i in range(self.combo_modelo_global.count()):
                if self.combo_modelo_global.itemData(i) == (atual or MODELO_PADRAO):
                    idx_sel = i; break
            self.combo_modelo_global.setCurrentIndex(idx_sel)
            self.lbl_ollama_st.setText(f"✓ {len(mods)} modelo(s) disponível(eis).")
        self.combo_modelo_global.blockSignals(False)
        self.w_trad.atualizar_modelos(mods)
        if mods:
            modelo = self._modelo_global()
            self._sincronizar_modelo_trad(modelo)
            self._precarregar_modelo(modelo)

    def _precarregar_modelo(self, modelo: str):
        if self._precarregar_thr and self._precarregar_thr.isRunning(): return
        self.lbl_ollama_st.setText(f"⏳ Carregando {modelo}…")
        self._precarregar_thr = PrecarregarThread(modelo)
        self._precarregar_thr.pronto.connect(
            lambda m: self.lbl_ollama_st.setText(f"✓ Modelo pronto: {m}"))
        self._precarregar_thr.falhou.connect(
            lambda m: self.lbl_ollama_st.setText(f"⚠ Ollama não respondeu para {m}"))
        self._precarregar_thr.start()

    # ── settings ──────────────────────────────────────────────────────────────

    def _status_bar_msg(self, msg: str):
        self.status_bar.showMessage(msg)
        if self._tm:
            self.lbl_tm_cnt.setText(f"MT: {self._tm.contar()} entradas")

    def _agenda_salvar_settings(self):
        self._settings_timer.start(800)

    def _salvar_settings(self):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) \
                if SETTINGS_FILE.exists() else {}
        except Exception: s = {}
        s["modelo"] = self._modelo_global()
        SETTINGS_FILE.write_text(
            json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

    def _carregar_settings(self):
        if not SETTINGS_FILE.exists(): return
        try:
            s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception: return
        modelo = s.get("modelo", MODELO_PADRAO)
        for i in range(self.combo_modelo_global.count()):
            if self.combo_modelo_global.itemData(i) == modelo:
                self.combo_modelo_global.setCurrentIndex(i); break

    def closeEvent(self, event):
        parar()
        for attr in ("_listar_thr", "_precarregar_thr"):
            thr = getattr(self, attr, None)
            if thr and thr.isRunning():
                thr.terminate(); thr.wait(800)
        for w in (self.w_morfo, self.w_trad, self.w_busca):
            thr = getattr(w, "_ollama_thr", None) or getattr(w, "_cat_thr", None)
            if thr and thr.isRunning():
                getattr(thr, "stop", thr.terminate)(); thr.wait(800)
            gem = getattr(w, "_gemini_thr", None)
            if gem and gem.isRunning():
                gem.stop(); gem.wait(800)
            pron = getattr(w, "_pron_thr", None)
            if pron and pron.isRunning():
                pron.terminate(); pron.wait(800)
        pron = getattr(self.w_pron, "_pron_thr", None)
        if pron and pron.isRunning():
            pron.terminate(); pron.wait(800)
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    app = QApplication(sys.argv)
    app.setApplicationName("Classicus")
    app.setOrganizationName("belerofonte")
    win = Classicus()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
