#!/usr/bin/env python3
"""Busca Greco-Latina — interface gráfica (Windows 11 ARM / Snapdragon X, PyQt6)"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

# ── configuração ──────────────────────────────────────────────────────────────
if sys.platform == "win32":
    _cfg_dir = Path(os.environ.get("APPDATA", Path.home())) / "BuscaLatina"
else:
    _cfg_dir = Path.home() / ".config" / "busca_latina"

SETTINGS_FILE = _cfg_dir / "settings.json"
CACHE_FILE    = _cfg_dir / "traducoes.json"

_MONO  = "Consolas" if sys.platform == "win32" else "monospace"
_SERIF = "Georgia"  if sys.platform == "win32" else "serif"


def _detectar_lingua(texto: str) -> str | None:
    """Detecta língua pelo perfil Unicode: 'grc', 'la', 'hbo' ou None."""
    grego    = sum(1 for c in texto if 'Ͱ' <= c <= 'Ͽ' or 'ἀ' <= c <= '῿')
    hebraico = sum(1 for c in texto if 'א' <= c <= 'ת')
    latino   = sum(1 for c in texto if c.isalpha() and ord(c) < 0x0370)
    total = grego + hebraico + latino
    if total < 4:
        return None
    if hebraico / total >= 0.40:
        return "hbo"
    if grego / total >= 0.60:
        return "grc"
    if latino / total >= 0.60:
        return "la"
    return None


# ── PyQt6 ─────────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QSpinBox, QCheckBox,
    QButtonGroup, QRadioButton, QGroupBox, QSplitter, QListWidget,
    QListWidgetItem, QStatusBar, QFrame, QComboBox, QSlider,
    QInputDialog, QMessageBox, QTabWidget, QDialog, QDialogButtonBox,
)
from PyQt6.QtCore  import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui   import QFont, QTextCharFormat, QColor, QTextCursor, QPalette

# ── módulos auxiliares ────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

try:
    from traduzir_lat_grc import (lookup_ls, lookup_lsj,
                                   lookup_collatinus_pt, lookup_wikt_pt)
    _TRADUCAO_OK = True
except ImportError:
    lookup_collatinus_pt = lookup_wikt_pt = None
    _TRADUCAO_OK = False

try:
    from ollama_lat import (traduzir_stream, listar_modelos, precarregar_modelo)
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

try:
    from pronunciar_latim import (pronunciar, parar, ipa_classico,
                                   VOZES, VOZES_LATIM, VOZES_GREGO, VOZES_HEBRAICO,
                                   VOZES_DEFAULT_GREGO, VOZES_DEFAULT_HEBRAICO)
    _PRONUNCIA_OK = True
except ImportError:
    VOZES = VOZES_LATIM = VOZES_GREGO = VOZES_HEBRAICO = []
    VOZES_DEFAULT_GREGO    = "el-GR-AthinaNeural"
    VOZES_DEFAULT_HEBRAICO = "he-IL-AvriNeural"
    _PRONUNCIA_OK = False

try:
    from pronunciar_latim import ipa_grego
except (ImportError, AttributeError):
    def ipa_grego(t: str) -> str:
        return f"[ipa_grego não disponível nesta plataforma]\n{t[:200]}"

try:
    from pronunciar_latim import baixar_modelo_piper
except (ImportError, AttributeError):
    baixar_modelo_piper = None

try:
    from claude_lat import (traduzir_stream as claude_stream,
                             guardar_chave, obter_chave,
                             MODELOS_CLAUDE, MODELO_DEFAULT)
    _CLAUDE_OK = True
except ImportError:
    MODELOS_CLAUDE = []
    MODELO_DEFAULT = "claude-opus-4-8"
    _CLAUDE_OK = False

try:
    from gemini_lat import (traduzir_stream as gemini_stream,
                             guardar_chave as gemini_guardar_chave,
                             obter_chave as gemini_obter_chave,
                             MODELOS_GEMINI, MODELO_DEFAULT as GEMINI_DEFAULT)
    _GEMINI_OK = True
except ImportError:
    MODELOS_GEMINI = []
    GEMINI_DEFAULT = "gemini-2.0-flash"
    _GEMINI_OK = False

try:
    from whitakers_words import analisar as whitaker_analisar
    _WHITAKER_OK = True
except ImportError:
    _WHITAKER_OK = False

try:
    import perseus_api as _papi
    _PERSEUS_API_OK = True
except ImportError:
    _PERSEUS_API_OK = False

try:
    import sefaria_api as _sapi
    _SEFARIA_OK = True
except ImportError:
    _SEFARIA_OK = False

try:
    import apibible_api as _abapi
    _APIBIBLE_OK = True
except ImportError:
    _APIBIBLE_OK = False

# ── corpora ───────────────────────────────────────────────────────────────────
LATIN_LIB = Path.home() / "cltk_data/lat/text/lat_text_latin_library"
PERSEUS    = Path.home() / "cltk_data/lat/text/lat_text_perseus"
OGL_GREGO  = Path.home() / "cltk_data/grc/text/first1kgreek"

STRIP_TAGS   = re.compile(r"<[^>]+>")
_REGEX_CHARS = re.compile(r'[.^$*+?\[\]\\|()\{\}]')

_OGL_META: dict | None = None


def _carregar_meta_ogl() -> dict:
    import csv as _csv
    csv_path = OGL_GREGO / "data" / "edition_metadata.csv"
    if not csv_path.exists():
        return {}
    meta = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = _csv.DictReader(fh, delimiter="\t")
            for row in reader:
                stem = Path(row.get("Filename", "")).stem
                meta[stem] = {
                    "author": (row.get("Author", "") or "").strip(),
                    "title":  (row.get("Title",  "") or "").strip(),
                }
    except Exception:
        pass
    return meta


# ── padrão de busca ───────────────────────────────────────────────────────────

def build_pattern(term: str, ignore_case: bool = True) -> re.Pattern:
    flags = re.IGNORECASE if ignore_case else 0
    is_suffix = term.startswith("-") and len(term) > 1
    is_prefix = term.endswith("-")   and len(term) > 1
    core = term
    if is_suffix:
        core = core[1:]
    if is_prefix:
        core = core[:-1]
    if _REGEX_CHARS.search(core):
        return re.compile(term, flags)
    esc = re.escape(core)
    if is_suffix and is_prefix:
        pat = rf"\b\w*{esc}\w*\b"
    elif is_suffix:
        pat = rf"\b\w*{esc}\b"
    elif is_prefix:
        pat = rf"\b{esc}\w*\b"
    else:
        pat = rf"\b{esc}\b"
    return re.compile(pat, flags)


# ── leitura de ficheiros ──────────────────────────────────────────────────────

def read_latin_lib(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.readlines()

def read_perseus_xml(path):
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    raw = re.sub(r"<teiHeader[^>]*>.*?</teiHeader>", " ", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    raw = STRIP_TAGS.sub(" ", raw)
    words = raw.split()
    lines, buf, length = [], [], 0
    for w in words:
        buf.append(w)
        length += len(w) + 1
        if length >= 120:
            lines.append(" ".join(buf))
            buf, length = [], 0
    if buf:
        lines.append(" ".join(buf))
    return lines

def label_ll(path):
    rel   = path.relative_to(LATIN_LIB)
    parts = rel.parts
    if len(parts) == 1:
        return "Latin Library", parts[0].removesuffix(".txt")
    return str(parts[0]).capitalize(), "/".join(parts[1:]).removesuffix(".txt")

def label_perseus(path):
    rel    = path.relative_to(PERSEUS)
    parts  = rel.parts
    author = parts[0]
    work   = path.stem.removesuffix("_lat").removesuffix("_grc")
    return author, work

def label_ogl(path) -> tuple[str, str]:
    global _OGL_META
    if _OGL_META is None:
        _OGL_META = _carregar_meta_ogl()
    info   = _OGL_META.get(path.stem, {})
    autor  = info.get("author") or path.parts[-2]
    titulo = info.get("title")  or path.stem
    return autor, titulo

def first_line_title(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                t = line.strip()
                if t:
                    return t[:80]
    except OSError:
        pass
    return ""


# ── thread de busca ───────────────────────────────────────────────────────────

class SearchThread(QThread):
    result   = pyqtSignal(str, str, str, int, list, bool)
    finished = pyqtSignal(int)
    status   = pyqtSignal(str)

    def __init__(self, pattern, ctx, do_ll, do_perseus, do_ogl, max_results):
        super().__init__()
        self.pattern     = pattern
        self.ctx         = ctx
        self.do_ll       = do_ll
        self.do_perseus  = do_perseus
        self.do_ogl      = do_ogl
        self.max_results = max_results
        self._stop       = False

    def stop(self):
        self._stop = True

    def run(self):
        total = 0

        lat_sources = []
        if self.do_ll and LATIN_LIB.exists():
            lat_sources.append((sorted(LATIN_LIB.rglob("*.txt")), False))
        if self.do_perseus and PERSEUS.exists():
            lat_sources.append((sorted(PERSEUS.rglob("*_lat.xml")), True))

        for files, is_xml in lat_sources:
            for path in files:
                if self._stop:
                    self.finished.emit(total)
                    return
                corpus = "Perseus" if is_xml else "Latin Library"
                self.status.emit(f"Varrendo {corpus}: {path.name}…")
                lines = read_perseus_xml(path) if is_xml else read_latin_lib(path)
                if is_xml:
                    author, work = label_perseus(path)
                else:
                    author, work = label_ll(path)
                    title = first_line_title(path)
                    if title and title.lower() not in work.lower():
                        work = f"{work} [{title[:50]}]"

                for i, line in enumerate(lines):
                    if self._stop:
                        self.finished.emit(total)
                        return
                    if self.pattern.search(line):
                        self.result.emit(corpus, author, work, i, lines, is_xml)
                        total += 1
                        if self.max_results and total >= self.max_results:
                            self.finished.emit(total)
                            return

        if self.do_ogl and OGL_GREGO.exists():
            ogl_files = sorted(
                p for p in OGL_GREGO.rglob("*.xml")
                if not any(s in p.stem for s in ("_eng", "_intro", "textcrit",
                                                  "appcrit", "index"))
            )
            for path in ogl_files:
                if self._stop:
                    self.finished.emit(total)
                    return
                self.status.emit(f"Varrendo OGL: {path.name}…")
                lines  = read_perseus_xml(path)
                author, work = label_ogl(path)

                for i, line in enumerate(lines):
                    if self._stop:
                        self.finished.emit(total)
                        return
                    if self.pattern.search(line):
                        self.result.emit("Open Greek & Latin", author, work,
                                         i, lines, True)
                        total += 1
                        if self.max_results and total >= self.max_results:
                            self.finished.emit(total)
                            return

        self.finished.emit(total)


# ── threads de tradução / IA ──────────────────────────────────────────────────

class GeminiThread(QThread):
    chunk  = pyqtSignal(str)
    status = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, texto, lingua, modelo, api_key):
        super().__init__()
        self.texto   = texto
        self.lingua  = lingua
        self.modelo  = modelo
        self.api_key = api_key
        self._stop   = False

    def stop(self):
        self._stop = True

    def run(self):
        if not _GEMINI_OK:
            self.erro.emit("gemini_lat.py não encontrado")
            return
        try:
            for frag in gemini_stream(self.texto, self.lingua,
                                      self.modelo, self.api_key,
                                      should_stop=lambda: self._stop):
                if self._stop:
                    break
                if frag.startswith("\x01retry:"):
                    self.status.emit(frag[7:])
                else:
                    self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class WhitakerThread(QThread):
    resultado = pyqtSignal(str)
    erro      = pyqtSignal(str)

    def __init__(self, texto):
        super().__init__()
        self.texto = texto

    def run(self):
        if not _WHITAKER_OK:
            self.erro.emit("whitakers_words.py não encontrado")
            return
        try:
            self.resultado.emit(whitaker_analisar(self.texto))
        except Exception as e:
            self.erro.emit(str(e))


class ClaudeThread(QThread):
    chunk  = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, texto, lingua, modelo, api_key):
        super().__init__()
        self.texto   = texto
        self.lingua  = lingua
        self.modelo  = modelo
        self.api_key = api_key
        self._stop   = False

    def stop(self):
        self._stop = True

    def run(self):
        if not _CLAUDE_OK:
            self.erro.emit("claude_lat.py não encontrado")
            return
        try:
            for frag in claude_stream(self.texto, self.lingua,
                                      self.modelo, self.api_key):
                if self._stop:
                    break
                self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class PrecarregarThread(QThread):
    pronto = pyqtSignal(str)
    falhou = pyqtSignal(str)

    def __init__(self, modelo=None):
        super().__init__()
        self.modelo = modelo

    def run(self):
        if not _OLLAMA_OK:
            return
        ok, nome = precarregar_modelo(self.modelo)
        if ok:
            self.pronto.emit(nome)
        else:
            self.falhou.emit(nome)


class OllamaThread(QThread):
    chunk  = pyqtSignal(str)
    done   = pyqtSignal()
    erro   = pyqtSignal(str)

    def __init__(self, texto, lingua, modelo):
        super().__init__()
        self.texto  = texto
        self.lingua = lingua
        self.modelo = modelo
        self._stop  = False

    def stop(self):
        self._stop = True

    def run(self):
        if not _OLLAMA_OK:
            self.erro.emit("ollama_lat.py não encontrado")
            return
        try:
            for frag in traduzir_stream(self.texto, self.lingua, self.modelo):
                if self._stop:
                    break
                self.chunk.emit(frag)
            self.done.emit()
        except Exception as e:
            self.erro.emit(str(e))


class PronunciaThread(QThread):
    erro = pyqtSignal(str)

    def __init__(self, texto, voz, variante, velocidade):
        super().__init__()
        self.texto      = texto
        self.voz        = voz
        self.variante   = variante
        self.velocidade = velocidade

    def run(self):
        if not _PRONUNCIA_OK:
            return
        try:
            pronunciar(self.texto, self.voz, self.variante, self.velocidade)
        except Exception as e:
            self.erro.emit(str(e))


class DownloadPiperThread(QThread):
    pronto    = pyqtSignal()
    erro      = pyqtSignal(str)
    progresso = pyqtSignal(str)

    def __init__(self, nome_voz: str):
        super().__init__()
        self.nome_voz = nome_voz

    def run(self):
        if baixar_modelo_piper is None:
            self.erro.emit("Download de vozes Piper não disponível nesta plataforma.")
            return
        try:
            ok = baixar_modelo_piper(
                self.nome_voz,
                progresso_cb=lambda msg: self.progresso.emit(msg),
            )
            if ok:
                self.pronto.emit()
            else:
                self.erro.emit(f"Falha ao descarregar {self.nome_voz}")
        except Exception as e:
            self.erro.emit(str(e))


class TranslateThread(QThread):
    done = pyqtSignal(str)

    def __init__(self, texto, modo):
        super().__init__()
        self.texto = texto
        self.modo  = modo

    def run(self):
        if not _TRADUCAO_OK:
            self.done.emit("[Módulo traduzir_lat_grc.py não encontrado]")
            return
        try:
            if self.modo == "ls":
                self.done.emit(lookup_ls(self.texto.strip(), traduzir_pt=False))
            elif self.modo == "lsj":
                self.done.emit(lookup_lsj(self.texto.strip(), traduzir_pt=False))
            elif self.modo == "collatinus_pt":
                if lookup_collatinus_pt:
                    self.done.emit(lookup_collatinus_pt(self.texto.strip()))
                else:
                    self.done.emit("[Collatinus PT não disponível — atualize traduzir_lat_grc.py]")
            elif self.modo == "wikt_pt":
                if lookup_wikt_pt:
                    self.done.emit(lookup_wikt_pt(self.texto.strip()))
                else:
                    self.done.emit("[Wikcionário PT não disponível — atualize traduzir_lat_grc.py]")
            else:
                self.done.emit("[modo desativado]")
        except Exception as e:
            self.done.emit(f"[Erro: {e}]")


# ── threads Perseus Online ────────────────────────────────────────────────────

class PercCatalogThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, lingua: str, forcar: bool = False):
        super().__init__()
        self.lingua = lingua
        self.forcar = forcar

    def run(self):
        try:
            self.pronto.emit(_papi.obter_catalogo(self.lingua, forcar=self.forcar))
        except Exception as e:
            self.erro.emit(str(e))


class PercRefsThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, edicao_urn: str):
        super().__init__()
        self.edicao_urn = edicao_urn

    def run(self):
        try:
            self.pronto.emit(_papi.obter_referencias(self.edicao_urn, nivel=1))
        except Exception as e:
            self.erro.emit(str(e))


class PercPassThread(QThread):
    pronto = pyqtSignal(str)
    erro   = pyqtSignal(str)

    def __init__(self, urn: str):
        super().__init__()
        self.urn = urn

    def run(self):
        try:
            self.pronto.emit(_papi.obter_passagem(self.urn))
        except Exception as e:
            self.erro.emit(str(e))


class PercObraCompletaThread(QThread):
    progresso = pyqtSignal(int, int)
    pronto    = pyqtSignal(str)
    erro      = pyqtSignal(str)

    def __init__(self, edicao_urn: str):
        super().__init__()
        self._urn  = edicao_urn
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            texto = _papi.obter_obra_completa(
                self._urn,
                progresso_cb=lambda a, t: self.progresso.emit(a, t),
                should_stop=lambda: self._stop,
            )
            if not self._stop:
                self.pronto.emit(texto)
        except Exception as e:
            self.erro.emit(str(e))


class SefariaCatalogThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, categoria: str, forcar: bool = False):
        super().__init__()
        self.categoria = categoria
        self.forcar    = forcar

    def run(self):
        try:
            self.pronto.emit(_sapi.obter_catalogo(self.categoria, forcar=self.forcar))
        except Exception as e:
            self.erro.emit(str(e))


class SefariaRefsThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, titulo: str):
        super().__init__()
        self.titulo = titulo

    def run(self):
        try:
            self.pronto.emit(_sapi.obter_refs(self.titulo))
        except Exception as e:
            self.erro.emit(str(e))


class SefariaPassThread(QThread):
    pronto = pyqtSignal(dict)
    erro   = pyqtSignal(str)

    def __init__(self, ref: str):
        super().__init__()
        self.ref = ref

    def run(self):
        try:
            self.pronto.emit(_sapi.obter_passagem(self.ref))
        except Exception as e:
            self.erro.emit(str(e))


class ApibibleLivrosThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, biblia_id: str):
        super().__init__()
        self.biblia_id = biblia_id

    def run(self):
        try:
            self.pronto.emit(_abapi.listar_livros(self.biblia_id))
        except Exception as e:
            self.erro.emit(str(e))


class ApibibleCapsThread(QThread):
    pronto = pyqtSignal(list)
    erro   = pyqtSignal(str)

    def __init__(self, biblia_id: str, livro_id: str):
        super().__init__()
        self.biblia_id = biblia_id
        self.livro_id  = livro_id

    def run(self):
        try:
            self.pronto.emit(_abapi.listar_capitulos(self.biblia_id, self.livro_id))
        except Exception as e:
            self.erro.emit(str(e))


class ApibiblePassThread(QThread):
    pronto = pyqtSignal(dict)
    erro   = pyqtSignal(str)

    def __init__(self, biblia_id: str, passagem_id: str):
        super().__init__()
        self.biblia_id   = biblia_id
        self.passagem_id = passagem_id

    def run(self):
        try:
            self.pronto.emit(_abapi.obter_passagem(self.biblia_id, self.passagem_id))
        except Exception as e:
            self.erro.emit(str(e))


# ── Alpheios morphology ───────────────────────────────────────────────────────

class AlpheiosMorphThread(QThread):
    """Chama a API Alpheios/Morpheus e devolve a análise morfológica em JSON."""
    pronto = pyqtSignal(str, str)  # (json_text, word)
    erro   = pyqtSignal(str)

    def __init__(self, word: str, lang: str):
        super().__init__()
        self.word = word
        self.lang = lang  # 'grc' ou 'lat'

    def run(self):
        import urllib.request
        import urllib.parse
        word = self.word.strip()
        if self.lang == 'grc':
            params = urllib.parse.urlencode({'word': word, 'lang': 'grc', 'engine': 'morpheusgrc'})
            url = f'http://morph.alpheios.net/api/v1/analysis/word?{params}'
        else:
            params = urllib.parse.urlencode({'word': word, 'lang': 'lat', 'engine': 'morpheuslat'})
            url = f'http://services.perseids.org/bsp/morphologyservice/analysis/word?{params}'
        try:
            req = urllib.request.Request(url, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read().decode('utf-8')
            self.pronto.emit(data, word)
        except Exception as e:
            self.erro.emit(str(e))


def _alpheios_parse(json_text: str) -> str:
    """Formata a resposta JSON da API Alpheios em texto legível."""
    try:
        d = json.loads(json_text)
    except Exception:
        return "Resposta inválida."

    if 'error' in d:
        return f"API: {d['error'].get('$', d['error'])}"

    try:
        annotation = d['RDF']['Annotation']
        body = annotation.get('Body', [])
    except (KeyError, TypeError):
        return "Estrutura de resposta inesperada."

    if isinstance(body, dict):
        body = [body]
    if not body:
        return "Sem análise disponível."

    _LABELS = {
        'pofs': 'classe', 'decl': 'declinação', 'gend': 'género',
        'case': 'caso', 'num': 'número', 'tense': 'tempo',
        'mood': 'modo', 'voice': 'voz', 'pers': 'pessoa',
        'stemtype': 'tipo de tema',
    }

    def val(obj):
        return obj.get('$', '') if isinstance(obj, dict) else str(obj)

    lines = []
    for b in body:
        entry = b.get('rest', {}).get('entry', {})
        if not entry:
            continue
        d_info = entry.get('dict', {})
        hdwd   = val(d_info.get('hdwd', {}))
        if hdwd:
            lines.append(f"Lema: {hdwd}")
        for k in ('pofs', 'decl', 'gend'):
            v = val(d_info.get(k, {}))
            if v:
                lines.append(f"  {_LABELS.get(k, k)}: {v}")

        infls = entry.get('infl', [])
        if isinstance(infls, dict):
            infls = [infls]
        for infl in infls:
            parts = []
            for k in ('case', 'num', 'gend', 'pers', 'tense', 'mood', 'voice', 'stemtype'):
                v = val(infl.get(k, {}))
                if v:
                    parts.append(f"{_LABELS.get(k, k)}: {v}")
            if parts:
                lines.append("  → " + " | ".join(parts))
        lines.append("")

    return "\n".join(lines).strip() or "Sem análise disponível."


# ── widget Textos Online ──────────────────────────────────────────────────────

class PerseusOnlineWidget(QWidget):
    """Navegador de textos online: Perseus (grc/lat), Sefaria (heb), API.Bible (heb)."""

    traduzir_pedido = pyqtSignal(str, str)   # (texto, lingua)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._obras    = []
        self._cat_thr  = None
        self._refs_thr = None
        self._pass_thr = None
        self._obra_completa_thr = None
        self._edicao_urn_sel = ""
        self._refs    = []
        self._sefaria_titulo  = ""
        self._apibible_livro  = ""
        self._apibible_biblia = ""
        self.pron_thread               = None
        self._download_thr             = None
        self._texto_pronunciando_online = ""
        self._ultimo_texto_online       = ""
        self._reiniciar_timer_online   = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        split = QSplitter(Qt.Orientation.Horizontal)

        # ── painel esquerdo: catálogo ─────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(4)

        fonte_row = QHBoxLayout()
        fonte_row.addWidget(QLabel("Fonte:"))
        self.combo_fonte = QComboBox()
        if _PERSEUS_API_OK:
            self.combo_fonte.addItem("Perseus (grc/lat)", "perseus")
        if _SEFARIA_OK:
            self.combo_fonte.addItem("🕎 Sefaria (heb)", "sefaria")
        if _APIBIBLE_OK:
            self.combo_fonte.addItem("📖 API.Bible (heb)", "apibible")
        self.combo_fonte.currentIndexChanged.connect(self._on_fonte_mudada)
        fonte_row.addWidget(self.combo_fonte)

        self.combo_lingua = QComboBox()
        self.combo_lingua.addItem("Grego (grc)", "grc")
        self.combo_lingua.addItem("Latim (lat)", "lat")
        self.combo_lingua.currentIndexChanged.connect(self._on_lingua_mudada)
        fonte_row.addWidget(self.combo_lingua)

        self.combo_cat_sefaria = QComboBox()
        for cat in ["Tanakh", "Talmud", "Midrash", "Halakhah", "Liturgy", "Jewish Thought"]:
            self.combo_cat_sefaria.addItem(cat, cat)
        self.combo_cat_sefaria.currentIndexChanged.connect(self._on_cat_sefaria_mudada)
        self.combo_cat_sefaria.hide()
        fonte_row.addWidget(self.combo_cat_sefaria)

        fonte_row.addStretch()
        self.btn_reload = QPushButton("⟳")
        self.btn_reload.setFixedWidth(32)
        self.btn_reload.setToolTip("Forçar actualização do catálogo")
        self.btn_reload.clicked.connect(self._carregar_catalogo_forcar)
        fonte_row.addWidget(self.btn_reload)
        ll.addLayout(fonte_row)

        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("Filtrar autor ou obra…")
        self.filtro.textChanged.connect(self._filtrar)
        ll.addWidget(self.filtro)

        self.lista_obras = QListWidget()
        self.lista_obras.currentRowChanged.connect(self._on_obra_sel)
        ll.addWidget(self.lista_obras, 1)

        self.lbl_cat_status = QLabel("A carregar catálogo…")
        self.lbl_cat_status.setWordWrap(True)
        ll.addWidget(self.lbl_cat_status)

        left.setMinimumWidth(280)
        split.addWidget(left)

        # ── painel direito: leitor ────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(4)

        self.lbl_obra_sel = QLabel("<i>(nenhuma obra selecionada)</i>")
        self.lbl_obra_sel.setWordWrap(True)
        rl.addWidget(self.lbl_obra_sel)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Referência (livro/secção):"))
        self.combo_refs = QComboBox()
        self.combo_refs.setMinimumWidth(120)
        self.combo_refs.currentIndexChanged.connect(self._carregar_passagem)
        ref_row.addWidget(self.combo_refs, 1)
        rl.addLayout(ref_row)

        self.texto_passagem = QTextEdit()
        self.texto_passagem.setReadOnly(True)
        self.texto_passagem.setFont(QFont(_SERIF, 11))
        self.texto_passagem.setPlaceholderText(
            "Selecione uma obra à esquerda e depois uma referência acima."
        )

        self.trans_out_online = QTextEdit()
        self.trans_out_online.setReadOnly(True)
        self.trans_out_online.setFont(QFont(_SERIF, 10))
        self.trans_out_online.setPlaceholderText(
            "🌟 Tradução →PT — seleccione texto e clique em «Traduzir →PT»"
        )
        self.trans_out_online.setMaximumHeight(220)

        vsplit_online = QSplitter(Qt.Orientation.Vertical)
        vsplit_online.addWidget(self.texto_passagem)
        vsplit_online.addWidget(self.trans_out_online)
        vsplit_online.setSizes([400, 150])
        rl.addWidget(vsplit_online, 1)

        btn_row = QHBoxLayout()
        self.btn_obra_completa = QPushButton("📥 Obra completa")
        self.btn_obra_completa.setEnabled(False)
        self.btn_obra_completa.setToolTip(
            "Descarrega todas as secções da obra e apresenta o texto integral"
        )
        self.btn_obra_completa.clicked.connect(self._on_obra_completa)
        btn_row.addWidget(self.btn_obra_completa)

        self.btn_traduzir = QPushButton("🌟 Traduzir →PT")
        self.btn_traduzir.setEnabled(False)
        self.btn_traduzir.setToolTip(
            "Traduz o texto seleccionado (ou toda a passagem) com Gemini"
        )
        self.btn_traduzir.clicked.connect(self._on_traduzir)
        btn_row.addWidget(self.btn_traduzir)

        self.btn_copiar = QPushButton("Copiar texto")
        self.btn_copiar.setEnabled(False)
        self.btn_copiar.clicked.connect(self._copiar_texto)
        btn_row.addWidget(self.btn_copiar)

        self.btn_alpheios = QPushButton("🏛 Alpheios")
        self.btn_alpheios.setEnabled(False)
        self.btn_alpheios.setToolTip(
            "Análise morfológica da palavra seleccionada (Morpheus / Perseus)"
        )
        self.btn_alpheios.clicked.connect(self._on_alpheios)
        btn_row.addWidget(self.btn_alpheios)
        btn_row.addStretch()

        self.lbl_pass_status = QLabel("")
        btn_row.addWidget(self.lbl_pass_status)
        rl.addLayout(btn_row)

        # barra de pronúncia
        pron_row = QHBoxLayout()
        pron_row.setSpacing(6)
        pron_row.addWidget(QLabel("Pronúncia:"))

        self.btn_pronunciar_online = QPushButton("🔊 Pronunciar")
        self.btn_pronunciar_online.setEnabled(_PRONUNCIA_OK)
        self.btn_pronunciar_online.clicked.connect(self._on_pronunciar_online)
        pron_row.addWidget(self.btn_pronunciar_online)

        self.btn_parar_som_online = QPushButton("■ Parar")
        self.btn_parar_som_online.setFixedWidth(70)
        self.btn_parar_som_online.setEnabled(_PRONUNCIA_OK)
        self.btn_parar_som_online.clicked.connect(self._on_parar_som_online)
        pron_row.addWidget(self.btn_parar_som_online)

        pron_row.addWidget(self._sep())
        pron_row.addWidget(QLabel("Voz:"))
        self.combo_voz_online = QComboBox()
        self.combo_voz_online.setMinimumWidth(250)
        pron_row.addWidget(self.combo_voz_online)

        self.btn_baixar_voz = QPushButton("⬇ Baixar voz offline")
        self.btn_baixar_voz.setEnabled(_PRONUNCIA_OK and baixar_modelo_piper is not None)
        self.btn_baixar_voz.setVisible(baixar_modelo_piper is not None)
        self.btn_baixar_voz.clicked.connect(self._on_baixar_voz)
        pron_row.addWidget(self.btn_baixar_voz)

        pron_row.addWidget(self._sep())
        pron_row.addWidget(QLabel("Velocidade:"))
        self.slider_vel_online = QSlider(Qt.Orientation.Horizontal)
        self.slider_vel_online.setRange(70, 220)
        self.slider_vel_online.setValue(130)
        self.slider_vel_online.setFixedWidth(110)
        self.slider_vel_online.setTickInterval(30)
        self.slider_vel_online.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.lbl_vel_online = QLabel("0%")
        self.slider_vel_online.valueChanged.connect(self._on_velocidade_online_mudada)
        pron_row.addWidget(self.slider_vel_online)
        pron_row.addWidget(self.lbl_vel_online)

        pron_row.addStretch()
        rl.addLayout(pron_row)

        split.addWidget(right)
        split.setSizes([300, 750])
        root.addWidget(split, 1)

        nota = QLabel(
            "<small>TLG (Thesaurus Linguae Graecae) requer subscrição institucional. "
            "Acesso web: <a href='https://stephanus.tlg.uci.edu'>stephanus.tlg.uci.edu</a></small>"
        )
        nota.setOpenExternalLinks(True)
        root.addWidget(nota)

        self._atualizar_vozes_online()
        self._carregar_catalogo()

    # ── catálogo ──────────────────────────────────────────────────────────────

    def _fonte(self) -> str:
        return self.combo_fonte.currentData() or "perseus"

    def _lingua(self) -> str:
        return self.combo_lingua.currentData()

    def _reset_leitor(self):
        self.lista_obras.clear()
        self.combo_refs.clear()
        self.texto_passagem.clear()
        self.lbl_obra_sel.setText("<i>(nenhuma obra selecionada)</i>")
        self.btn_obra_completa.setEnabled(False)
        self.btn_traduzir.setEnabled(False)
        self.btn_copiar.setEnabled(False)
        self.btn_alpheios.setEnabled(False)

    def _carregar_catalogo(self, forcar: bool = False):
        if self._cat_thr is not None:
            try:
                self._cat_thr.pronto.disconnect(self._on_catalogo_pronto)
                self._cat_thr.erro.disconnect(self._on_catalogo_erro)
            except (RuntimeError, TypeError):
                pass
        self._reset_leitor()
        fonte = self._fonte()
        if fonte == "perseus":
            self.lbl_cat_status.setText("⏳ A carregar catálogo Perseus…")
            self._cat_thr = PercCatalogThread(self._lingua(), forcar)
        elif fonte == "sefaria":
            cat = self.combo_cat_sefaria.currentData() or "Tanakh"
            self.lbl_cat_status.setText(f"⏳ A carregar catálogo Sefaria ({cat})…")
            self._cat_thr = SefariaCatalogThread(cat, forcar)
        else:
            self.lbl_cat_status.setText("⚠ API.Bible: configure chave e selecione versão.")
            return
        self._cat_thr.pronto.connect(self._on_catalogo_pronto)
        self._cat_thr.erro.connect(self._on_catalogo_erro)
        self._cat_thr.start()

    def _carregar_catalogo_forcar(self):
        self._carregar_catalogo(forcar=True)

    def _on_catalogo_pronto(self, obras: list):
        self._obras = obras
        self._filtrar(self.filtro.text())
        self.lbl_cat_status.setText(f"✓ {len(obras)} obras disponíveis.")

    def _on_catalogo_erro(self, msg: str):
        self.lbl_cat_status.setText(f"⚠ Erro: {msg}")

    def _filtrar(self, query: str = ""):
        self.lista_obras.blockSignals(True)
        self.lista_obras.clear()
        q = query.lower()
        for o in self._obras:
            if not q or q in o["display"].lower():
                item = QListWidgetItem(o["display"])
                item.setData(Qt.ItemDataRole.UserRole, o)
                self.lista_obras.addItem(item)
        self.lista_obras.blockSignals(False)

    def _on_fonte_mudada(self):
        fonte = self._fonte()
        self.combo_lingua.setVisible(fonte == "perseus")
        self.combo_cat_sefaria.setVisible(fonte == "sefaria")
        self.texto_passagem.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if fonte != "perseus"
            else Qt.LayoutDirection.LeftToRight
        )
        self.filtro.clear()
        self._obras = []
        self._refs  = []
        self._atualizar_vozes_online()
        self._carregar_catalogo()

    def _on_lingua_mudada(self):
        self.filtro.clear()
        self._obras = []
        self._refs  = []
        self.combo_refs.clear()
        self.texto_passagem.clear()
        self.lbl_obra_sel.setText("<i>(nenhuma obra selecionada)</i>")
        self.btn_obra_completa.setEnabled(False)
        self.btn_traduzir.setEnabled(False)
        self.btn_copiar.setEnabled(False)
        self.btn_alpheios.setEnabled(False)
        self._atualizar_vozes_online()
        self._carregar_catalogo()

    def _on_cat_sefaria_mudada(self):
        self._on_lingua_mudada()

    # ── obra selecionada ──────────────────────────────────────────────────────

    def _on_obra_sel(self, row: int):
        item = self.lista_obras.item(row)
        if item is None:
            return
        obra = item.data(Qt.ItemDataRole.UserRole)
        if not obra:
            return

        self.combo_refs.clear()
        self.combo_refs.addItem("(a carregar…)", "")
        self.lbl_pass_status.setText("A carregar referências…")

        fonte = self._fonte()
        if fonte == "sefaria":
            self._sefaria_titulo = obra["titulo"]
            self.lbl_obra_sel.setText(f"<b>{obra['display']}</b>")
            self._refs_thr = SefariaRefsThread(obra["titulo"])
            self._refs_thr.pronto.connect(self._on_sefaria_refs_prontas)
            self._refs_thr.erro.connect(self._on_refs_erro)
            self._refs_thr.start()
        elif fonte == "apibible":
            self._apibible_livro = obra.get("id", "")
            self.lbl_obra_sel.setText(f"<b>{obra['display']}</b>")
            self._refs_thr = ApibibleCapsThread(self._apibible_biblia, self._apibible_livro)
            self._refs_thr.pronto.connect(self._on_apibible_caps_prontas)
            self._refs_thr.erro.connect(self._on_refs_erro)
            self._refs_thr.start()
        else:
            self._edicao_urn_sel = obra["edicao_urn"]
            self.lbl_obra_sel.setText(
                f"<b>{obra['display']}</b><br>"
                f"<small>{obra['edicao_urn']}</small>"
            )
            self._refs_thr = PercRefsThread(obra["edicao_urn"])
            self._refs_thr.pronto.connect(self._on_refs_prontas)
            self._refs_thr.erro.connect(self._on_refs_erro)
            self._refs_thr.start()

    def _on_refs_prontas(self, refs: list):
        self._refs = refs
        self.combo_refs.blockSignals(True)
        self.combo_refs.clear()
        for urn in refs:
            lbl = _papi.label_referencia(urn)
            self.combo_refs.addItem(lbl, urn)
        self.combo_refs.blockSignals(False)
        tem_refs = bool(refs)
        self.btn_obra_completa.setEnabled(tem_refs)
        self.lbl_pass_status.setText(
            f"✓ {len(refs)} referências." if refs else "Sem referências."
        )
        if tem_refs:
            self._carregar_passagem()

    def _on_refs_erro(self, msg: str):
        self.combo_refs.clear()
        self.btn_obra_completa.setEnabled(False)
        self.lbl_pass_status.setText(f"⚠ Refs: {msg}")

    def _on_sefaria_refs_prontas(self, refs: list):
        self._refs = refs
        self.combo_refs.blockSignals(True)
        self.combo_refs.clear()
        for ref in refs:
            self.combo_refs.addItem(ref.split(" ")[-1], ref)
        self.combo_refs.blockSignals(False)
        has = bool(refs)
        self.btn_obra_completa.setEnabled(has)
        self.lbl_pass_status.setText(f"✓ {len(refs)} capítulos." if has else "Sem capítulos.")
        if has:
            self._carregar_passagem()

    def _on_apibible_caps_prontas(self, caps: list):
        self._refs = [c["id"] for c in caps]
        self.combo_refs.blockSignals(True)
        self.combo_refs.clear()
        for c in caps:
            self.combo_refs.addItem(str(c["numero"]), c["id"])
        self.combo_refs.blockSignals(False)
        has = bool(caps)
        self.lbl_pass_status.setText(f"✓ {len(caps)} capítulos." if has else "Sem capítulos.")
        if has:
            self._carregar_passagem()

    # ── carregar passagem ─────────────────────────────────────────────────────

    def _carregar_passagem(self):
        fonte = self._fonte()
        if fonte == "sefaria":
            ref = self.combo_refs.currentData()
            if not ref:
                return
            self.texto_passagem.setPlainText("⏳ A carregar…")
            self.lbl_pass_status.setText("A buscar…")
            self._pass_thr = SefariaPassThread(ref)
            self._pass_thr.pronto.connect(self._on_sefaria_passagem_pronta)
            self._pass_thr.erro.connect(self._on_passagem_erro)
            self._pass_thr.start()
        elif fonte == "apibible":
            passagem_id = self.combo_refs.currentData()
            if not passagem_id or not self._apibible_biblia:
                return
            self.texto_passagem.setPlainText("⏳ A carregar…")
            self.lbl_pass_status.setText("A buscar…")
            self._pass_thr = ApibiblePassThread(self._apibible_biblia, passagem_id)
            self._pass_thr.pronto.connect(self._on_apibible_passagem_pronta)
            self._pass_thr.erro.connect(self._on_passagem_erro)
            self._pass_thr.start()
        else:
            urn = self.combo_refs.currentData()
            if not urn:
                urn = self._edicao_urn_sel
            if not urn:
                return
            self.texto_passagem.setPlainText("⏳ A carregar passagem…")
            self.lbl_pass_status.setText("A buscar…")
            self._pass_thr = PercPassThread(urn)
            self._pass_thr.pronto.connect(self._on_passagem_pronta)
            self._pass_thr.erro.connect(self._on_passagem_erro)
            self._pass_thr.start()

    def _on_sefaria_passagem_pronta(self, d: dict):
        texto = d.get("texto_heb", "")
        self.texto_passagem.setPlainText(texto)
        tem = bool(texto.strip())
        self.btn_traduzir.setEnabled(tem)
        self.btn_copiar.setEnabled(tem)
        self.btn_alpheios.setEnabled(False)  # hebraico não suportado
        ref_heb = d.get("ref_heb", d.get("ref", ""))
        self.lbl_pass_status.setText(f"✓ {ref_heb} — {len(texto.split())} palavras.")

    def _on_apibible_passagem_pronta(self, d: dict):
        texto = d.get("texto", "")
        self.texto_passagem.setPlainText(texto)
        tem = bool(texto.strip())
        self.btn_traduzir.setEnabled(tem)
        self.btn_copiar.setEnabled(tem)
        self.btn_alpheios.setEnabled(False)  # hebraico não suportado
        self.lbl_pass_status.setText(f"✓ {d.get('ref', '')} — {len(texto.split())} palavras.")

    def _on_passagem_pronta(self, texto: str):
        self.texto_passagem.setPlainText(texto)
        tem = bool(texto.strip())
        self.btn_traduzir.setEnabled(tem)
        self.btn_copiar.setEnabled(tem)
        self.btn_alpheios.setEnabled(tem)
        self.lbl_pass_status.setText(f"✓ {len(texto.split())} palavras.")

    def _on_passagem_erro(self, msg: str):
        self.texto_passagem.setPlainText(f"⚠ Erro ao carregar passagem:\n{msg}")
        self.lbl_pass_status.setText("⚠ Erro.")

    # ── Alpheios ──────────────────────────────────────────────────────────────

    def _on_alpheios(self):
        word = self.texto_passagem.textCursor().selectedText().strip()
        if not word:
            QMessageBox.information(self, "Alpheios", "Seleccione uma palavra no texto.")
            return
        if ' ' in word:
            word = word.split()[0]

        lang = self.combo_lingua.currentData() or 'grc'
        self.btn_alpheios.setEnabled(False)
        self.btn_alpheios.setText("⏳ A analisar…")
        self._alpheios_thr = AlpheiosMorphThread(word, lang)
        self._alpheios_thr.pronto.connect(self._on_alpheios_pronto)
        self._alpheios_thr.erro.connect(self._on_alpheios_erro)
        self._alpheios_thr.start()

    def _on_alpheios_pronto(self, json_text: str, word: str):
        self.btn_alpheios.setEnabled(True)
        self.btn_alpheios.setText("🏛 Alpheios")
        resultado = _alpheios_parse(json_text)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Alpheios — {word}")
        dlg.resize(420, 300)
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFont(QFont("serif", 11))
        txt.setPlainText(resultado)
        lay.addWidget(txt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()

    def _on_alpheios_erro(self, msg: str):
        self.btn_alpheios.setEnabled(True)
        self.btn_alpheios.setText("🏛 Alpheios")
        QMessageBox.warning(self, "Alpheios", f"Erro ao contactar API:\n{msg}")

    # ── ações ─────────────────────────────────────────────────────────────────

    def _texto_activo(self) -> str:
        sel = self.texto_passagem.textCursor().selectedText().strip()
        return sel if sel else self.texto_passagem.toPlainText().strip()

    def _on_obra_completa(self):
        if not self._edicao_urn_sel:
            return
        if self._obra_completa_thr and self._obra_completa_thr.isRunning():
            self._obra_completa_thr.stop()
            self._obra_completa_thr.wait(2000)
        n = len(self._refs)
        self.texto_passagem.setPlainText(f"⏳ A descarregar obra completa… 0/{n} secções")
        self.btn_obra_completa.setEnabled(False)
        self._obra_completa_thr = PercObraCompletaThread(self._edicao_urn_sel)
        self._obra_completa_thr.progresso.connect(self._on_obra_progresso)
        self._obra_completa_thr.pronto.connect(self._on_obra_pronta)
        self._obra_completa_thr.erro.connect(self._on_obra_erro)
        self._obra_completa_thr.start()

    def _on_obra_progresso(self, atual: int, total: int):
        self.lbl_pass_status.setText(f"⏳ {atual}/{total} secções…")

    def _on_obra_pronta(self, texto: str):
        self.texto_passagem.setPlainText(texto)
        self.btn_obra_completa.setEnabled(True)
        tem = bool(texto.strip())
        self.btn_traduzir.setEnabled(tem)
        self.btn_copiar.setEnabled(tem)
        self.btn_alpheios.setEnabled(tem)
        self.lbl_pass_status.setText(f"✓ Obra completa — {len(texto.split())} palavras.")
        if tem:
            cursor = self.texto_passagem.textCursor()
            cursor.setPosition(0)
            cursor.setPosition(min(400, len(texto)), QTextCursor.MoveMode.KeepAnchor)
            self.texto_passagem.setTextCursor(cursor)

    def _on_obra_erro(self, msg: str):
        self.texto_passagem.setPlainText(f"⚠ Erro ao descarregar obra:\n{msg}")
        self.btn_obra_completa.setEnabled(True)
        self.lbl_pass_status.setText("⚠ Erro.")

    def _lingua_traducao(self) -> str:
        fonte = self._fonte()
        if fonte != "perseus":
            return "hbo"
        return self.combo_lingua.currentData() or "la"

    def _on_traduzir(self):
        texto = self._texto_activo()
        if texto:
            self.traduzir_pedido.emit(texto, self._lingua_traducao())

    def _copiar_texto(self):
        QApplication.clipboard().setText(self.texto_passagem.toPlainText())
        self.lbl_pass_status.setText("✓ Copiado.")

    # ── pronúncia ─────────────────────────────────────────────────────────────

    def _sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _atualizar_vozes_online(self):
        fonte = self._fonte()
        if fonte != "perseus":
            vozes = VOZES_HEBRAICO or []
        elif self._lingua() == "grc":
            vozes = VOZES_GREGO or []
        else:
            vozes = VOZES_LATIM or []
        if not vozes:
            vozes = VOZES or []
        self.combo_voz_online.clear()
        for vid, rotulo, *_ in vozes:
            self.combo_voz_online.addItem(rotulo, vid)

    def _lancar_pronuncia_online(self, texto: str):
        if self.pron_thread and self.pron_thread.isRunning():
            parar()
            self.pron_thread.terminate()
            self.pron_thread.wait(2000)
        self._texto_pronunciando_online = texto
        self._ultimo_texto_online = texto
        voz = self.combo_voz_online.currentData() or VOZES_DEFAULT_HEBRAICO
        velocidade = self.slider_vel_online.value() - 130
        self.pron_thread = PronunciaThread(texto, voz, 'classico', velocidade)
        self.pron_thread.erro.connect(
            lambda e: self.lbl_pass_status.setText(f"Pronúncia: {e}")
        )
        self.pron_thread.finished.connect(
            lambda: setattr(self, '_texto_pronunciando_online', '')
        )
        self.pron_thread.start()

    def _on_pronunciar_online(self):
        if not _PRONUNCIA_OK:
            return
        sel = self.texto_passagem.textCursor().selectedText().strip()
        texto = sel if sel else self.texto_passagem.toPlainText().strip()[:3000]
        if not texto:
            return
        self._lancar_pronuncia_online(texto)

    def _on_parar_som_online(self):
        if _PRONUNCIA_OK:
            parar()
        if self.pron_thread and self.pron_thread.isRunning():
            self.pron_thread.terminate()
        self._texto_pronunciando_online = ""

    def _on_velocidade_online_mudada(self, valor: int):
        delta = valor - 130
        sinal = "+" if delta >= 0 else ""
        self.lbl_vel_online.setText(f"{sinal}{delta}%")
        if _PRONUNCIA_OK and self._ultimo_texto_online:
            if self._reiniciar_timer_online is None:
                self._reiniciar_timer_online = QTimer(self)
                self._reiniciar_timer_online.setSingleShot(True)
                self._reiniciar_timer_online.timeout.connect(
                    self._reiniciar_pronuncia_online
                )
            self._reiniciar_timer_online.start(400)

    def _reiniciar_pronuncia_online(self):
        if _PRONUNCIA_OK and self._ultimo_texto_online:
            self._lancar_pronuncia_online(self._ultimo_texto_online)

    def _on_baixar_voz(self):
        if baixar_modelo_piper is None:
            QMessageBox.information(self, "Não disponível",
                                    "Download de vozes Piper não está disponível nesta plataforma.")
            return
        if not _PRONUNCIA_OK:
            QMessageBox.warning(self, "Indisponível",
                                "Módulo pronunciar_latim.py não encontrado.")
            return
        voz_id = self.combo_voz_online.currentData()
        if not voz_id:
            return
        voz_info = next((v for v in VOZES if v[0] == voz_id), None)
        motor = voz_info[2] if voz_info else ""
        if motor == "edge":
            QMessageBox.information(self, "Voz online",
                                    "Esta é uma voz online (edge-tts) e não precisa de download.\n"
                                    "Selecione uma voz '— offline' para descarregar.")
            return
        if motor == "espeak" and voz_id == "he":
            QMessageBox.information(self, "Já disponível",
                                    "A voz espeak-ng hebraico já está instalada.")
            return
        if self._download_thr is not None and self._download_thr.isRunning():
            return
        self.btn_baixar_voz.setEnabled(False)
        self.lbl_pass_status.setText(f"⬇ A descarregar {voz_id}…")
        self._download_thr = DownloadPiperThread(voz_id)
        self._download_thr.pronto.connect(self._on_download_pronto)
        self._download_thr.erro.connect(self._on_download_erro)
        self._download_thr.progresso.connect(
            lambda msg: self.lbl_pass_status.setText(f"⬇ {msg}")
        )
        self._download_thr.start()

    def _on_download_pronto(self):
        self.btn_baixar_voz.setEnabled(True)
        self.lbl_pass_status.setText("✓ Voz descarregada.")
        QMessageBox.information(self, "Download concluído",
                                "Modelo de voz Piper descarregado com sucesso.")

    def _on_download_erro(self, msg: str):
        self.btn_baixar_voz.setEnabled(True)
        self.lbl_pass_status.setText(f"⚠ Erro: {msg}")
        QMessageBox.warning(self, "Erro de download", msg)


# ── janela principal ──────────────────────────────────────────────────────────

class BuscaLatina(QMainWindow):
    def __init__(self):
        super().__init__()
        self.thread               = None
        self.trans_thread         = None
        self.pron_thread          = None
        self._ollama_thread       = None
        self._claude_thread       = None
        self._gemini_thread       = None
        self._whitaker_thread     = None
        self._precarregar_thread  = None
        self.total                = 0
        self._texto_pronunciar    = ""
        self._texto_pronunciando  = ""
        self._selecao_salva       = ""
        self._settings_timer      = None
        self._reiniciar_timer     = None
        self._cache               = self._cache_carregar()
        self._perseus_widget      = None
        self._build_ui()
        self._carregar_settings()

    # ── construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Busca Greco-Latina")
        self.resize(1200, 750)

        central = QWidget()
        self.setCentralWidget(central)
        _main = QVBoxLayout(central)
        _main.setContentsMargins(0, 0, 0, 0)
        _main.setSpacing(0)

        self.tabs = QTabWidget()
        _main.addWidget(self.tabs)

        tab_busca = QWidget()
        self.tabs.addTab(tab_busca, "🔍 Busca")
        root = QVBoxLayout(tab_busca)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 6)

        # barra de busca
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText(
            "amor=exato · amor-=prefixo · -que=sufixo · -amor-=infixo · regex: . * + [ \\"
        )
        self.entry.setFont(QFont(_MONO, 11))
        self.entry.returnPressed.connect(self._on_search)
        search_row.addWidget(self.entry, 1)
        self.btn_search = QPushButton("Buscar")
        self.btn_search.setFixedWidth(90)
        self.btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self.btn_search)
        self.btn_stop = QPushButton("Parar")
        self.btn_stop.setFixedWidth(70)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        search_row.addWidget(self.btn_stop)
        root.addLayout(search_row)

        # opções
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)
        self.chk_ignore = QCheckBox("Ignorar maiúsculas")
        self.chk_ignore.setChecked(True)
        opts_row.addWidget(self.chk_ignore)
        opts_row.addWidget(self._sep())
        opts_row.addWidget(QLabel("Contexto:"))
        self.spin_ctx = QSpinBox()
        self.spin_ctx.setRange(0, 10)
        self.spin_ctx.setValue(2)
        self.spin_ctx.setFixedWidth(50)
        opts_row.addWidget(self.spin_ctx)
        opts_row.addWidget(self._sep())
        opts_row.addWidget(QLabel("Máx. resultados:"))
        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 9999)
        self.spin_max.setValue(100)
        self.spin_max.setSpecialValueText("Todos")
        self.spin_max.setFixedWidth(70)
        opts_row.addWidget(self.spin_max)
        opts_row.addWidget(self._sep())
        corpus_grp = QGroupBox("Corpus")
        corpus_grp.setFlat(True)
        cg_layout = QHBoxLayout(corpus_grp)
        cg_layout.setContentsMargins(0, 0, 0, 0)
        cg_layout.setSpacing(8)
        self.bg = QButtonGroup(self)
        for i, lbl in enumerate(["Latim (ambos)", "Latin Library",
                                  "Perseus (lat)", "Open Greek & Latin"]):
            rb = QRadioButton(lbl)
            self.bg.addButton(rb, i)
            cg_layout.addWidget(rb)
        self.bg.button(0).setChecked(True)
        opts_row.addWidget(corpus_grp)
        opts_row.addStretch()
        root.addLayout(opts_row)

        # splitter obras | resultado
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(QLabel("Obras com ocorrências:"))
        self.list_works = QListWidget()
        self.list_works.setMaximumWidth(280)
        self.list_works.currentItemChanged.connect(self._on_work_selected)
        left_layout.addWidget(self.list_works)
        splitter.addWidget(left)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont(_MONO, 10))
        self.text.selectionChanged.connect(self._on_selecao_mudada)
        splitter.addWidget(self.text)
        splitter.setSizes([250, 750])

        # splitter vertical resultados | tradução
        vsplit  = QSplitter(Qt.Orientation.Vertical)
        top_wgt = QWidget()
        top_lay = QVBoxLayout(top_wgt)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.addWidget(splitter)
        vsplit.addWidget(top_wgt)

        # painel de tradução
        trans_panel  = QWidget()
        trans_layout = QVBoxLayout(trans_panel)
        trans_layout.setContentsMargins(0, 4, 0, 0)
        trans_layout.setSpacing(4)

        # linha IA
        ctrl_ia = QHBoxLayout()
        ctrl_ia.setSpacing(6)

        ctrl_ia.addWidget(QLabel("Língua:"))
        self.combo_lingua = QComboBox()
        self.combo_lingua.addItems(["Latim", "Grego Antigo", "Hebraico"])
        self.combo_lingua.setFixedWidth(120)
        ctrl_ia.addWidget(self.combo_lingua)

        ctrl_ia.addWidget(QLabel("Modelo:"))
        self.combo_modelo = QComboBox()
        self.combo_modelo.setMinimumWidth(180)
        self.combo_modelo.setToolTip("Modelos Ollama instalados\nPara instalar: ollama pull phi3")
        self.combo_modelo.addItem("(sem modelos — instale Ollama)", None)
        self.combo_modelo.currentIndexChanged.connect(self._on_modelo_mudado)
        ctrl_ia.addWidget(self.combo_modelo)

        self.btn_ollama = QPushButton("🤖 Traduzir →PT")
        self.btn_ollama.setToolTip("Traduz a seleção com IA local (Ollama)")
        self.btn_ollama.clicked.connect(self._on_ollama_traduzir)
        ctrl_ia.addWidget(self.btn_ollama)

        self.btn_comentario = QPushButton("📖 Comentário")
        self.btn_comentario.setToolTip("Comentário filológico com IA")
        self.btn_comentario.clicked.connect(self._on_ollama_comentario)
        ctrl_ia.addWidget(self.btn_comentario)

        self.btn_parar_ia = QPushButton("⏹ Parar")
        self.btn_parar_ia.setFixedWidth(70)
        self.btn_parar_ia.clicked.connect(self._on_parar_ia)
        ctrl_ia.addWidget(self.btn_parar_ia)

        ctrl_ia.addWidget(self._sep())

        # Claude
        self.btn_claude = QPushButton("Claude →PT")
        self.btn_claude.setToolTip("Traduz com a API Claude (Anthropic)")
        self.btn_claude.clicked.connect(self._on_claude_traduzir)
        ctrl_ia.addWidget(self.btn_claude)

        self.combo_claude_modelo = QComboBox()
        self.combo_claude_modelo.setMinimumWidth(160)
        for mid, rotulo in MODELOS_CLAUDE:
            self.combo_claude_modelo.addItem(rotulo, mid)
        for i in range(self.combo_claude_modelo.count()):
            if "haiku" in (self.combo_claude_modelo.itemData(i) or "").lower():
                self.combo_claude_modelo.setCurrentIndex(i)
                break
        ctrl_ia.addWidget(self.combo_claude_modelo)

        self.btn_claude_chave = QPushButton("Chave")
        self.btn_claude_chave.setFixedWidth(50)
        self.btn_claude_chave.clicked.connect(self._on_configurar_chave_claude)
        ctrl_ia.addWidget(self.btn_claude_chave)

        ctrl_ia.addWidget(self._sep())

        # Gemini
        self.btn_gemini = QPushButton("🌟 Gemini →PT")
        self.btn_gemini.setToolTip("Traduz com a API Gemini (Google)\nChave gratuita em aistudio.google.com")
        self.btn_gemini.clicked.connect(self._on_gemini_traduzir)
        ctrl_ia.addWidget(self.btn_gemini)

        self.combo_gemini_modelo = QComboBox()
        self.combo_gemini_modelo.setMinimumWidth(160)
        for mid, rotulo in MODELOS_GEMINI:
            self.combo_gemini_modelo.addItem(rotulo, mid)
        ctrl_ia.addWidget(self.combo_gemini_modelo)

        self.btn_gemini_chave = QPushButton("🔑")
        self.btn_gemini_chave.setFixedWidth(30)
        self.btn_gemini_chave.clicked.connect(self._on_configurar_chave_gemini)
        ctrl_ia.addWidget(self.btn_gemini_chave)

        ctrl_ia.addWidget(self._sep())

        # Whitaker
        self.btn_whitaker = QPushButton("📖 Whitaker")
        self.btn_whitaker.setToolTip("Análise morfológica Whitaker's Words")
        self.btn_whitaker.clicked.connect(self._on_whitaker)
        ctrl_ia.addWidget(self.btn_whitaker)

        ctrl_ia.addWidget(self._sep())

        # Dicionários
        ctrl_ia.addWidget(QLabel("Dicionário:"))
        self.btn_ls = QPushButton("L&S")
        self.btn_ls.setToolTip("Lewis & Short — latim → inglês (offline)")
        self.btn_ls.clicked.connect(lambda: self._on_dicionario("ls"))
        ctrl_ia.addWidget(self.btn_ls)

        self.btn_lsj = QPushButton("LSJ")
        self.btn_lsj.setToolTip("Liddell-Scott-Jones — grego → inglês (offline)")
        self.btn_lsj.clicked.connect(lambda: self._on_dicionario("lsj"))
        ctrl_ia.addWidget(self.btn_lsj)

        self.btn_collatinus_pt = QPushButton("Coll.PT")
        self.btn_collatinus_pt.setToolTip("Collatinus — latim → português (offline)")
        self.btn_collatinus_pt.clicked.connect(lambda: self._on_dicionario("collatinus_pt"))
        ctrl_ia.addWidget(self.btn_collatinus_pt)

        self.btn_wikt_pt = QPushButton("Wikt.PT")
        self.btn_wikt_pt.setToolTip("Wikcionário Português — latim → português (offline)")
        self.btn_wikt_pt.clicked.connect(lambda: self._on_dicionario("wikt_pt"))
        ctrl_ia.addWidget(self.btn_wikt_pt)

        self.btn_limpar_tr = QPushButton("Limpar")
        self.btn_limpar_tr.setFixedWidth(60)
        self.btn_limpar_tr.clicked.connect(lambda: self.trans_out.clear())
        ctrl_ia.addWidget(self.btn_limpar_tr)

        ctrl_ia.addStretch()
        trans_layout.addLayout(ctrl_ia)

        QTimer.singleShot(2000, self._atualizar_modelos_ollama)

        # linha de pronúncia
        pron_row = QHBoxLayout()
        pron_row.setSpacing(6)
        pron_row.addWidget(QLabel("Pronúncia:"))

        self.btn_pronunciar = QPushButton("🔊 Pronunciar")
        self.btn_pronunciar.setToolTip("Pronuncia o texto seleccionado")
        self.btn_pronunciar.clicked.connect(self._on_pronunciar)
        self.btn_pronunciar.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_pronunciar)

        self.btn_parar_som = QPushButton("■ Parar")
        self.btn_parar_som.setFixedWidth(70)
        self.btn_parar_som.clicked.connect(self._on_parar_som)
        self.btn_parar_som.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_parar_som)

        self.btn_ipa = QPushButton("IPA")
        self.btn_ipa.setToolTip("Transcrição IPA fonética do texto seleccionado")
        self.btn_ipa.setFixedWidth(50)
        self.btn_ipa.clicked.connect(self._on_ipa)
        self.btn_ipa.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_ipa)

        pron_row.addWidget(self._sep())
        pron_row.addWidget(QLabel("Voz:"))
        self.combo_voz = QComboBox()
        self.combo_voz.setMinimumWidth(240)
        for vid, rotulo, *_ in (VOZES_LATIM or VOZES):
            self.combo_voz.addItem(rotulo, vid)
        self.combo_voz.currentIndexChanged.connect(self._salvar_settings)
        pron_row.addWidget(self.combo_voz)

        pron_row.addWidget(self._sep())

        self.pron_grp = QGroupBox("Variante")
        self.pron_grp.setFlat(True)
        pg_lay = QHBoxLayout(self.pron_grp)
        pg_lay.setContentsMargins(0, 0, 0, 0)
        pg_lay.setSpacing(6)
        self.bg_pron = QButtonGroup(self)
        for i, lbl in enumerate(["Clássico", "Eclesiástico"]):
            rb = QRadioButton(lbl)
            self.bg_pron.addButton(rb, i)
            pg_lay.addWidget(rb)
        self.bg_pron.button(0).setChecked(True)
        self.bg_pron.buttonClicked.connect(self._salvar_settings)
        pron_row.addWidget(self.pron_grp)

        self.combo_lingua.currentIndexChanged.connect(self._on_lingua_pron_mudada)

        pron_row.addWidget(self._sep())
        pron_row.addWidget(QLabel("Velocidade:"))
        self.slider_vel = QSlider(Qt.Orientation.Horizontal)
        self.slider_vel.setRange(70, 220)
        self.slider_vel.setValue(130)
        self.slider_vel.setFixedWidth(100)
        self.slider_vel.setTickInterval(30)
        self.slider_vel.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.lbl_vel = QLabel("130")
        self.slider_vel.valueChanged.connect(self._on_velocidade_mudada)
        pron_row.addWidget(self.slider_vel)
        pron_row.addWidget(self.lbl_vel)
        pron_row.addStretch()
        trans_layout.addLayout(pron_row)

        self.trans_out = QTextEdit()
        self.trans_out.setReadOnly(True)
        self.trans_out.setFont(QFont(_SERIF, 10))
        self.trans_out.setPlaceholderText(
            "🤖 Traduzir →PT  — tradução com IA local (Ollama)\n"
            "Claude / Gemini  — tradução com API cloud\n"
            "L&S / LSJ        — dicionário offline\n\n"
            "Selecione texto nos resultados e use os botões acima."
        )
        trans_layout.addWidget(self.trans_out)

        vsplit.addWidget(trans_panel)
        vsplit.setSizes([480, 220])
        root.addWidget(vsplit, 1)

        self.text.mouseDoubleClickEvent = self._on_text_dblclick
        self.text.contextMenuEvent = self._on_text_context_menu

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        msg = ("Pronto." if _TRADUCAO_OK
               else "Aviso: traduzir_lat_grc.py não encontrado — tradução offline indisponível.")
        self.status_bar.showMessage(msg)

        self._work_data  = {}
        self._work_order = []
        self._pattern    = None

        # aba Textos Online
        if _PERSEUS_API_OK or _SEFARIA_OK or _APIBIBLE_OK:
            self._perseus_widget = PerseusOnlineWidget(self)
            self._perseus_widget.traduzir_pedido.connect(self._traduzir_texto_online)
            self._perseus_widget.texto_passagem.selectionChanged.connect(
                self._on_selecao_dialog_mudada
            )
            self.tabs.addTab(self._perseus_widget, "🌐 Textos Online")

    def _sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _traduzir_texto_online(self, texto: str, lingua: str = "la"):
        self._selecao_salva = texto
        destino = (self._perseus_widget.trans_out_online
                   if self._perseus_widget is not None else self.trans_out)
        self._lancar_gemini(texto, lingua, destino=destino)

    def _on_selecao_dialog_mudada(self):
        if self._perseus_widget is None:
            return
        sel = self._perseus_widget.texto_passagem.textCursor().selectedText().strip()
        if sel:
            self._sincronizar_lingua(sel)

    # ── busca ─────────────────────────────────────────────────────────────────

    def _on_search(self):
        term = self.entry.text().strip()
        if not term:
            return
        try:
            self._pattern = build_pattern(term, self.chk_ignore.isChecked())
        except re.error as e:
            self.status_bar.showMessage(f"Regex inválida: {e}")
            return

        self.text.clear()
        self.list_works.clear()
        self._work_data      = {}
        self._work_order     = []
        self._texto_pronunciar = ""
        self._selecao_salva  = ""
        self.total = 0

        corpus_id  = self.bg.checkedId()
        do_ll      = corpus_id in (0, 1)
        do_perseus = corpus_id in (0, 2)
        do_ogl     = corpus_id == 3

        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()

        self.thread = SearchThread(
            self._pattern, self.spin_ctx.value(),
            do_ll, do_perseus, do_ogl, self.spin_max.value(),
        )
        self.thread.result.connect(self._on_result)
        self.thread.finished.connect(self._on_finished)
        self.thread.status.connect(lambda s: self.status_bar.showMessage(s))
        self.btn_search.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.thread.start()

    def _on_stop(self):
        if self.thread:
            self.thread.stop()

    def _on_result(self, corpus, author, work, line_idx, lines, is_xml):
        self.total += 1
        key = f"[{corpus}] {author} — {work}"
        if key not in self._work_data:
            self._work_data[key] = []
            self._work_order.append(key)
            item = QListWidgetItem(key)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list_works.addItem(item)
        self._work_data[key].append((line_idx, lines, is_xml))
        current = self.list_works.currentItem()
        if current is None or current.data(Qt.ItemDataRole.UserRole) == key:
            self._append_result(key, line_idx, lines, is_xml)
        self.status_bar.showMessage(f"{self.total} ocorrência(s) encontrada(s)…")

    def _on_finished(self, total):
        self.btn_search.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if total == 0:
            self.text.setPlainText(f'Nenhuma ocorrência encontrada para "{self.entry.text()}".')
            self.status_bar.showMessage("Busca concluída — sem resultados.")
        else:
            self.status_bar.showMessage(
                f"Busca concluída — {total} ocorrência(s) em {len(self._work_data)} obra(s)."
            )

    # ── exibição ──────────────────────────────────────────────────────────────

    def _on_work_selected(self, current, _previous):
        if current is None:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        self.text.clear()
        self._texto_pronunciar = ""
        for line_idx, lines, is_xml in self._work_data.get(key, []):
            self._append_result(key, line_idx, lines, is_xml)

    def _append_result(self, key, line_idx, lines, is_xml):
        ctx   = self.spin_ctx.value()
        start = max(0, line_idx - ctx)
        end   = min(len(lines), line_idx + ctx + 1)

        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        hdr_fmt = QTextCharFormat()
        hdr_fmt.setForeground(QColor("#1a6fa8"))
        hdr_fmt.setFontWeight(700)
        cursor.insertText(f"\n{key}  (linha {line_idx + 1})\n", hdr_fmt)

        normal_fmt = QTextCharFormat()
        normal_fmt.setForeground(
            QColor("#dddddd") if self._is_dark() else QColor("#222222")
        )
        hi_fmt = QTextCharFormat()
        hi_fmt.setBackground(
            QColor("#2d5a8e") if self._is_dark() else QColor("#d6eaf8")
        )
        hi_fmt.setForeground(
            QColor("#ffffff") if self._is_dark() else QColor("#000000")
        )

        for j in range(start, end):
            line = lines[j].rstrip()
            if j == line_idx:
                self._insert_highlighted_line(cursor, line, hi_fmt, normal_fmt)
            else:
                cursor.insertText(f"  {line}\n", normal_fmt)

        sep_fmt = QTextCharFormat()
        sep_fmt.setForeground(QColor("#555555"))
        cursor.insertText("─" * 60 + "\n", sep_fmt)
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

        if not self._texto_pronunciar:
            passagem = " ".join(lines[j].rstrip() for j in range(start, end))
            self._texto_pronunciar = re.sub(r'\s+', ' ', passagem).strip()

    def _insert_highlighted_line(self, cursor, line, hi_fmt, normal_fmt):
        cursor.insertText("▶ ", hi_fmt)
        if self._pattern is None:
            cursor.insertText(line + "\n", hi_fmt)
            return
        last = 0
        for m in self._pattern.finditer(line):
            if m.start() > last:
                cursor.insertText(line[last:m.start()], hi_fmt)
            term_fmt = QTextCharFormat(hi_fmt)
            term_fmt.setFontUnderline(True)
            term_fmt.setForeground(QColor("#ffdd00"))
            cursor.insertText(m.group(), term_fmt)
            last = m.end()
        if last < len(line):
            cursor.insertText(line[last:], hi_fmt)
        cursor.insertText("\n", normal_fmt)

    # ── Gemini ────────────────────────────────────────────────────────────────

    def _on_configurar_chave_gemini(self):
        chave_actual = (gemini_obter_chave() if _GEMINI_OK else "") or ""
        placeholder  = chave_actual[:8] + "…" if chave_actual else "(não definida)"
        texto, ok = QInputDialog.getText(
            self, "Chave API Gemini (Google)",
            f"Chave actual: {placeholder}\n\nObtenha gratuitamente em aistudio.google.com\n\nInsira a nova chave:",
            QLineEdit.EchoMode.Password,
        )
        if ok and texto.strip():
            if _GEMINI_OK:
                gemini_guardar_chave(texto.strip())
            self.status_bar.showMessage("✓ Chave API Gemini guardada.")

    def _on_gemini_traduzir(self):
        if not _GEMINI_OK:
            self.trans_out.setPlainText("⚠ gemini_lat.py não encontrado.")
            return
        chave = gemini_obter_chave()
        if not chave:
            QMessageBox.warning(self, "Chave API em falta",
                                "Configure a chave Gemini clicando em 🔑.\n"
                                "Obtenha gratuitamente em aistudio.google.com")
            return
        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\nSeleccione texto nos resultados e clique novamente."
            )
            return
        self._lancar_gemini(texto)

    def _lancar_gemini(self, texto: str, lingua: str | None = None, destino=None):
        destino = destino or self.trans_out
        if not _GEMINI_OK:
            destino.setPlainText("⚠ gemini_lat.py não encontrado.")
            return
        chave = gemini_obter_chave()
        if not chave:
            QMessageBox.warning(self, "Chave API em falta",
                                "Configure a chave Gemini clicando em 🔑.\n"
                                "Obtenha gratuitamente em aistudio.google.com")
            return
        modelo = self.combo_gemini_modelo.currentData() or GEMINI_DEFAULT
        lingua = lingua or self._lingua_ollama()

        cached = self._cache_verificar(texto, lingua, modelo)
        if cached:
            destino.setPlainText(cached)
            self.status_bar.showMessage("✓ Tradução do histórico.")
            return

        if self._gemini_thread is not None and self._gemini_thread.isRunning():
            self._gemini_thread.stop()
            self._gemini_thread.wait(1000)

        destino.setPlainText(f"🌟 Gemini ({modelo})…\n\n")
        self._gemini_thread = GeminiThread(texto, lingua, modelo, chave)
        self._gemini_thread.chunk.connect(
            lambda frag, d=destino: self._append_chunk(frag, d))
        self._gemini_thread.status.connect(self.status_bar.showMessage)
        self._gemini_thread.done.connect(
            lambda: (
                self._cache_guardar(texto, lingua, modelo, destino.toPlainText()),
                self.status_bar.showMessage("✓ Tradução Gemini concluída."),
            )
        )
        self._gemini_thread.erro.connect(
            lambda e: destino.setPlainText(f"⚠ Erro Gemini: {e}"))
        self._gemini_thread.start()
        self.status_bar.showMessage("Gemini a traduzir…")

    # ── Whitaker ──────────────────────────────────────────────────────────────

    def _on_whitaker(self):
        if not _WHITAKER_OK:
            self.trans_out.setPlainText("⚠ whitakers_words.py não encontrado.")
            return
        texto = self._texto_selecionado()
        palavras = texto.split()
        if len(palavras) > 6:
            self.trans_out.setPlainText(
                "⚠ Seleccione uma palavra ou frase curta (até 6 palavras) para análise Whitaker."
            )
            return
        if not texto.strip():
            self.trans_out.setPlainText("⚠ Seleccione texto nos resultados primeiro.")
            return
        self.trans_out.setPlainText(f"📖 Whitaker's Words: «{texto.strip()}»\n\n⏳ A consultar…")
        if self._whitaker_thread is not None and self._whitaker_thread.isRunning():
            self._whitaker_thread.wait(2000)
        self._whitaker_thread = WhitakerThread(texto.strip())
        self._whitaker_thread.resultado.connect(
            lambda r: self.trans_out.setPlainText(f"📖 Whitaker's Words — «{texto.strip()}»\n\n{r}")
        )
        self._whitaker_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Whitaker: {e}"))
        self._whitaker_thread.start()
        self.status_bar.showMessage("Whitaker's Words a analisar…")

    # ── Claude ────────────────────────────────────────────────────────────────

    def _on_configurar_chave_claude(self):
        chave_actual = (obter_chave() if _CLAUDE_OK else "") or ""
        placeholder  = chave_actual[:8] + "…" if chave_actual else "(não definida)"
        texto, ok = QInputDialog.getText(
            self, "Chave API Claude (Anthropic)",
            f"Chave actual: {placeholder}\n\nInsira a nova chave (ou cancele para manter):",
            QLineEdit.EchoMode.Password,
        )
        if ok and texto.strip():
            if _CLAUDE_OK:
                guardar_chave(texto.strip())
            self.status_bar.showMessage("✓ Chave API Claude guardada.")

    def _on_claude_traduzir(self):
        if not _CLAUDE_OK:
            self.trans_out.setPlainText("⚠ claude_lat.py não encontrado.")
            return
        chave = obter_chave()
        if not chave:
            QMessageBox.warning(self, "Chave API em falta",
                                "Configure a chave API Claude clicando em «Chave» ao lado.")
            return
        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\nSeleccione texto nos resultados e clique novamente."
            )
            return
        modelo = self.combo_claude_modelo.currentData() or MODELO_DEFAULT
        lingua = self._lingua_ollama()
        if self._claude_thread is not None and self._claude_thread.isRunning():
            self._claude_thread.stop()
            self._claude_thread.wait(1000)
        self.trans_out.setPlainText(f"Claude ({modelo})…\n\n")
        self._claude_thread = ClaudeThread(texto, lingua, modelo, chave)
        self._claude_thread.chunk.connect(self._on_ollama_chunk)
        self._claude_thread.done.connect(
            lambda: self.status_bar.showMessage("✓ Tradução Claude concluída.")
        )
        self._claude_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Claude: {e}")
        )
        self._claude_thread.start()
        self.status_bar.showMessage("Claude a traduzir…")

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _atualizar_modelos_ollama(self):
        if not _OLLAMA_OK:
            self.combo_modelo.clear()
            self.combo_modelo.addItem("(ollama_lat.py não encontrado)", None)
            return
        mods = listar_modelos()
        self.combo_modelo.clear()
        if mods:
            self.combo_modelo.addItem("(melhor disponível)", None)
            for m in mods:
                self.combo_modelo.addItem(m, m)
            self._iniciar_precarregamento(mods[0])
        else:
            self.combo_modelo.addItem("(Ollama sem modelos)", None)
            self.status_bar.showMessage("Ollama sem modelos. Execute: ollama pull phi3")

    def _iniciar_precarregamento(self, modelo: str):
        if self._precarregar_thread is not None and self._precarregar_thread.isRunning():
            return
        self.status_bar.showMessage(f"⏳ A carregar modelo IA ({modelo})…")
        self.btn_ollama.setEnabled(False)
        self.btn_comentario.setEnabled(False)
        self._precarregar_thread = PrecarregarThread(modelo)
        self._precarregar_thread.pronto.connect(self._on_modelo_pronto)
        self._precarregar_thread.falhou.connect(self._on_modelo_falhou)
        self._precarregar_thread.start()

    def _on_modelo_mudado(self, _idx: int):
        modelo = self._modelo_ollama()
        if modelo:
            if self._precarregar_thread is not None and self._precarregar_thread.isRunning():
                self._precarregar_thread.terminate()
                self._precarregar_thread.wait(500)
            self._iniciar_precarregamento(modelo)

    def _on_modelo_pronto(self, nome: str):
        self.status_bar.showMessage(f"✓ Modelo IA pronto: {nome}")
        self.btn_ollama.setEnabled(True)
        self.btn_comentario.setEnabled(True)

    def _on_modelo_falhou(self, _nome: str):
        self.status_bar.showMessage("⚠ Ollama não responde — inicie com: ollama serve")
        self.btn_ollama.setEnabled(True)
        self.btn_comentario.setEnabled(True)

    def _modelo_ollama(self) -> str | None:
        return self.combo_modelo.currentData()

    def _lingua_ollama(self) -> str:
        return ("la", "grc", "hbo")[min(self.combo_lingua.currentIndex(), 2)]

    def _iniciar_ollama(self, modo: str):
        if not _OLLAMA_OK:
            self.trans_out.setPlainText("⚠ ollama_lat.py não encontrado.")
            return
        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\nSeleccione texto nos resultados e clique novamente."
            )
            return
        modelo = self._modelo_ollama()
        lingua = "comentario" if modo == "comentario" else self._lingua_ollama()

        cached = self._cache_verificar(texto, lingua, modelo)
        if cached:
            self.trans_out.setPlainText(cached)
            self.status_bar.showMessage("✓ Tradução do histórico.")
            return

        if self._ollama_thread is not None and self._ollama_thread.isRunning():
            self._ollama_thread.stop()
            self._ollama_thread.wait(1000)

        rotulo = "Comentário" if modo == "comentario" else "Tradução →PT"
        self.trans_out.setPlainText(
            f"⏳ {rotulo} com {modelo or 'phi3'}…\n\n"
            f"(1.ª vez pode demorar 30–60 s enquanto o modelo carrega)"
        )
        self._ollama_thread = OllamaThread(texto, lingua, modelo)
        self._ollama_thread.chunk.connect(self._on_ollama_chunk)
        self._ollama_thread.done.connect(
            lambda: (
                self._cache_guardar(texto, lingua, modelo, self.trans_out.toPlainText()),
                self.status_bar.showMessage("✓ Tradução IA concluída."),
            )
        )
        self._ollama_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Ollama: {e}")
        )
        self._ollama_thread.start()
        self.status_bar.showMessage("Ollama a processar…")

    def _append_chunk(self, frag: str, destino=None):
        d = destino or self.trans_out
        cursor = d.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        d.setTextCursor(cursor)
        d.insertPlainText(frag)

    def _on_ollama_chunk(self, frag: str):
        self._append_chunk(frag, self.trans_out)

    def _on_ollama_traduzir(self):
        self._iniciar_ollama("traduzir")

    def _on_ollama_comentario(self):
        self._iniciar_ollama("comentario")

    # ── pronúncia ─────────────────────────────────────────────────────────────

    def _texto_para_pronunciar(self) -> str:
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            sel = re.sub(r'^[▶■─=\s]+', '', sel, flags=re.MULTILINE)
            return sel.strip()
        if self._perseus_widget is not None:
            sel_online = self._perseus_widget.texto_passagem.textCursor().selectedText().strip()
            if sel_online:
                return sel_online
        if self._texto_pronunciar:
            return self._texto_pronunciar
        txt = re.sub(r'^[▶■─=\s]+', '', self.text.toPlainText(), flags=re.MULTILINE)
        return txt.strip()[:3000]

    def _variante_pron(self) -> str:
        return 'eclesiastico' if self.bg_pron.checkedId() == 1 else 'classico'

    def _voz_selecionada(self) -> str:
        return self.combo_voz.currentData() or "it-IT-DiegoNeural"

    def _on_lingua_pron_mudada(self):
        idx        = self.combo_lingua.currentIndex()
        e_grego    = idx == 1
        e_hebraico = idx == 2
        voz_actual = self.combo_voz.currentData()

        if e_hebraico:
            vozes_filtradas = VOZES_HEBRAICO or VOZES
        elif e_grego:
            vozes_filtradas = VOZES_GREGO or VOZES
        else:
            vozes_filtradas = VOZES_LATIM or VOZES

        self.combo_voz.blockSignals(True)
        self.combo_voz.clear()
        idx_default = 0
        for i, (vid, rotulo, *_) in enumerate(vozes_filtradas):
            self.combo_voz.addItem(rotulo, vid)
            if vid == voz_actual:
                idx_default = i
        self.combo_voz.setCurrentIndex(idx_default)
        self.combo_voz.blockSignals(False)

        btn_0 = self.bg_pron.button(0)
        btn_1 = self.bg_pron.button(1)
        if e_grego:
            btn_0.setText("Offline")
            btn_1.setText("Online")
            self.pron_grp.setTitle("Pronúncia")
            btn_0.clicked.connect(self._on_pron_grega_reconstituida)
            btn_1.clicked.connect(self._on_pron_grega_moderna)
            btn_0.setChecked(True)
            self._on_pron_grega_reconstituida()
        else:
            try:
                btn_0.clicked.disconnect(self._on_pron_grega_reconstituida)
                btn_1.clicked.disconnect(self._on_pron_grega_moderna)
            except (RuntimeError, TypeError):
                pass
            if e_hebraico:
                btn_0.setText("Online")
                btn_1.setText("Offline")
                self.pron_grp.setTitle("Voz")
            else:
                btn_0.setText("Clássico")
                btn_1.setText("Eclesiástico")
                self.pron_grp.setTitle("Variante")

    def _on_pron_grega_reconstituida(self):
        """Selecciona primeira voz grega disponível (Piper offline se existir, senão Nestoras)."""
        preferencias = ["el_GR-rapunzelina-low", "el-GR-NestorasNeural", "el-GR-AthinaNeural"]
        for voz_pref in preferencias:
            for i in range(self.combo_voz.count()):
                if self.combo_voz.itemData(i) == voz_pref:
                    self.combo_voz.setCurrentIndex(i)
                    return

    def _on_pron_grega_moderna(self):
        """Selecciona Athina (online) para grego moderno."""
        for i in range(self.combo_voz.count()):
            if self.combo_voz.itemData(i) == "el-GR-AthinaNeural":
                self.combo_voz.setCurrentIndex(i)
                return

    def _on_pronunciar(self):
        if not _PRONUNCIA_OK:
            return
        texto = self._texto_para_pronunciar()
        if not texto:
            return
        self._lancar_pronuncia(texto)

    def _lancar_pronuncia(self, texto: str):
        if self.pron_thread and self.pron_thread.isRunning():
            parar()
            self.pron_thread.terminate()
            self.pron_thread.wait(2000)
        self._texto_pronunciando = texto
        velocidade = self.slider_vel.value() - 130
        self.pron_thread = PronunciaThread(
            texto, self._voz_selecionada(), self._variante_pron(), velocidade
        )
        self.pron_thread.erro.connect(
            lambda e: self.status_bar.showMessage(f"Pronúncia: {e}")
        )
        self.pron_thread.finished.connect(
            lambda: setattr(self, '_texto_pronunciando', '')
        )
        self.pron_thread.start()

    def _on_velocidade_mudada(self, valor: int):
        self.lbl_vel.setText(str(valor))
        self._agenda_salvar_settings()
        if _PRONUNCIA_OK and self._texto_pronunciando:
            if self._reiniciar_timer is None:
                self._reiniciar_timer = QTimer(self)
                self._reiniciar_timer.setSingleShot(True)
                self._reiniciar_timer.timeout.connect(self._reiniciar_pronuncia)
            self._reiniciar_timer.start(400)

    def _reiniciar_pronuncia(self):
        if _PRONUNCIA_OK and self._texto_pronunciando:
            self._lancar_pronuncia(self._texto_pronunciando)

    def _on_parar_som(self):
        if _PRONUNCIA_OK:
            parar()
        if self.pron_thread and self.pron_thread.isRunning():
            self.pron_thread.terminate()

    def _on_ipa(self):
        if not _PRONUNCIA_OK:
            return
        texto = self._texto_para_pronunciar()
        if not texto:
            return
        if self.combo_lingua.currentIndex() == 1:
            ipa = ipa_grego(texto[:300])
            self.trans_out.setPlainText(f"IPA (grego antigo reconstituído):\n{ipa}")
        else:
            ipa = ipa_classico(texto[:300])
            self.trans_out.setPlainText(f"IPA (clássico):\n{ipa}")

    # ── tradução e dicionário ─────────────────────────────────────────────────

    def _sincronizar_lingua(self, texto: str):
        lingua = _detectar_lingua(texto)
        if lingua is None:
            return
        idx = {"la": 0, "grc": 1, "hbo": 2}.get(lingua, 0)
        if self.combo_lingua.currentIndex() != idx:
            self.combo_lingua.setCurrentIndex(idx)

    def _on_selecao_mudada(self):
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            self._selecao_salva = sel
            self._sincronizar_lingua(sel)

    def _texto_selecionado(self) -> str:
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            return sel
        if self._perseus_widget is not None:
            sel_online = self._perseus_widget.texto_passagem.textCursor().selectedText().strip()
            if sel_online:
                return sel_online
        if self._selecao_salva:
            return self._selecao_salva
        return self._texto_pronunciar

    def _rodar_traducao(self, texto: str, modo: str):
        if not texto.strip():
            return
        self.trans_out.setPlaceholderText("")
        self.trans_out.setText("⏳ Processando…")
        if self.trans_thread and self.trans_thread.isRunning():
            self.trans_thread.terminate()
        self.trans_thread = TranslateThread(texto, modo)
        self.trans_thread.done.connect(self.trans_out.setPlainText)
        self.trans_thread.start()

    def _on_dicionario(self, modo: str):
        palavra = self.text.textCursor().selectedText().strip().split()[0] if \
                  self.text.textCursor().selectedText().strip() else ""
        if not palavra:
            self.trans_out.setPlainText("Selecione uma palavra no painel de resultados primeiro.")
            return
        self._rodar_traducao(palavra, modo)

    def _on_text_dblclick(self, event):
        QTextEdit.mouseDoubleClickEvent(self.text, event)
        palavra = self.text.textCursor().selectedText().strip()
        if not palavra:
            return
        idx  = self.combo_lingua.currentIndex()
        modo = "lsj" if idx == 1 else "ls"
        if idx == 2:
            return
        self._rodar_traducao(palavra, modo)

    def _on_text_context_menu(self, event):
        menu = self.text.createStandardContextMenu()
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            menu.addSeparator()
            if _OLLAMA_OK:
                menu.addAction("🤖 Traduzir →PT (Ollama)").triggered.connect(
                    self._on_ollama_traduzir)
                menu.addAction("📖 Comentário (Ollama)").triggered.connect(
                    self._on_ollama_comentario)
            if _GEMINI_OK:
                menu.addAction("🌟 Traduzir →PT (Gemini)").triggered.connect(
                    self._on_gemini_traduzir)
            if _CLAUDE_OK:
                menu.addAction("Claude →PT").triggered.connect(
                    self._on_claude_traduzir)
            menu.addSeparator()
            menu.addAction("L&S (Lewis & Short)").triggered.connect(
                lambda: self._on_dicionario("ls"))
            menu.addAction("LSJ (Liddell-Scott-Jones)").triggered.connect(
                lambda: self._on_dicionario("lsj"))
            menu.addAction("Coll.PT (Collatinus latim→PT)").triggered.connect(
                lambda: self._on_dicionario("collatinus_pt"))
            menu.addAction("Wikt.PT (Wikcionário latim→PT)").triggered.connect(
                lambda: self._on_dicionario("wikt_pt"))
        menu.exec(event.globalPos())

    def _on_parar_ia(self):
        if self._ollama_thread is not None and self._ollama_thread.isRunning():
            self._ollama_thread.stop()
        if self._gemini_thread is not None and self._gemini_thread.isRunning():
            self._gemini_thread.stop()
        if self._claude_thread is not None and self._claude_thread.isRunning():
            self._claude_thread.stop()
        self.status_bar.showMessage("Geração interrompida.")

    # ── cache de traduções ────────────────────────────────────────────────────

    @staticmethod
    def _cache_chave(texto: str, lingua: str, modelo: str) -> str:
        raw = f"{texto.strip()}|||{lingua}|||{modelo}"
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    def _cache_carregar(self) -> dict:
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _cache_verificar(self, texto: str, lingua: str, modelo: str) -> str | None:
        entrada = self._cache.get(self._cache_chave(texto, lingua, modelo))
        return entrada["traducao"] if entrada else None

    def _cache_guardar(self, texto: str, lingua: str, modelo: str, traducao: str):
        if not traducao.strip():
            return
        marcadores_erro = ("[Chave API", "[Quota", "[Sem ligação", "[Erro", "[Limite")
        trad_limpa = traducao.strip()
        if any(m in trad_limpa for m in marcadores_erro):
            return
        if len(texto) > 300 and len(trad_limpa) < len(texto) * 0.15:
            return
        chave = self._cache_chave(texto, lingua, modelo)
        self._cache[chave] = {
            "texto":    texto.strip(),
            "lingua":   lingua,
            "modelo":   modelo,
            "traducao": traducao,
        }
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── persistência de configurações ─────────────────────────────────────────

    def _carregar_settings(self):
        try:
            s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        voz = s.get("voz", "")
        for i in range(self.combo_voz.count()):
            if self.combo_voz.itemData(i) == voz:
                self.combo_voz.setCurrentIndex(i)
                break
        variante = s.get("variante", 0)
        btn = self.bg_pron.button(variante)
        if btn:
            btn.setChecked(True)
        self.slider_vel.setValue(s.get("velocidade", 130))

    def _salvar_settings(self, *_):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            s = {}
        s["voz"]        = self._voz_selecionada()
        s["variante"]   = self.bg_pron.checkedId()
        s["velocidade"] = self.slider_vel.value()
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")

    def _agenda_salvar_settings(self):
        if self._settings_timer is None:
            self._settings_timer = QTimer(self)
            self._settings_timer.setSingleShot(True)
            self._settings_timer.timeout.connect(self._salvar_settings)
        self._settings_timer.start(600)

    def _is_dark(self) -> bool:
        bg = self.palette().color(QPalette.ColorRole.Window)
        return bg.lightness() < 128


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    app = QApplication(sys.argv)
    app.setApplicationName("Busca Greco-Latina")
    app.setOrganizationName("belerofonte")
    win = BuscaLatina()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
