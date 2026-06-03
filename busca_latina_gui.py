#!/usr/bin/env python3
"""Busca Latina — interface gráfica (PyQt5)"""

import sys
import re
import json
from pathlib import Path

SETTINGS_FILE = Path.home() / ".config" / "busca_latina" / "settings.json"

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QSpinBox, QCheckBox,
    QButtonGroup, QRadioButton, QGroupBox, QSplitter, QListWidget,
    QListWidgetItem, QStatusBar, QFrame, QSizePolicy, QComboBox, QSlider,
    QInputDialog, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QPalette

# módulo de tradução e dicionário
sys.path.insert(0, str(Path.home()))
try:
    from traduzir_lat_grc import traduzir_para_pt, lookup_ls, lookup_lsj
    _TRADUCAO_OK = True
except ImportError:
    _TRADUCAO_OK = False

try:
    from ollama_lat import (traduzir_stream, comentario, listar_modelos,
                            modelo_disponivel, _melhor_modelo, MODELOS_RECOMENDADOS,
                            precarregar_modelo)
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

try:
    from pronunciar_latim import pronunciar, parar, ipa_classico, esta_a_falar, VOZES
    _PRONUNCIA_OK = True
except ImportError:
    VOZES = []
    _PRONUNCIA_OK = False

try:
    from claude_lat import (traduzir_stream as claude_stream, guardar_chave,
                            obter_chave, MODELOS_CLAUDE, MODELO_DEFAULT)
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

LATIN_LIB = Path.home() / "cltk_data/lat/text/lat_text_latin_library"
PERSEUS    = Path.home() / "cltk_data/lat/text/lat_text_perseus"

STRIP_TAGS   = re.compile(r"<[^>]+>")
_REGEX_CHARS = re.compile(r'[.^$*+?\[\]\\|()\{\}]')


def build_pattern(term: str, ignore_case: bool = True) -> re.Pattern:
    """
    -x   → sufixo  (palavras terminadas em x)
    x-   → prefixo (palavras iniciadas por x)
    -x-  → infixo  (palavras contendo x)
    x    → exato   (palavra isolada)
    Regex pura se o núcleo contiver metacaracteres.
    """
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


# ── leitura ───────────────────────────────────────────────────────────────────

def read_latin_lib(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.readlines()

def read_perseus_xml(path):
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    raw = re.sub(r"<teiHeader[^>]*>.*?</teiHeader>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
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
    rel = path.relative_to(LATIN_LIB)
    parts = rel.parts
    if len(parts) == 1:
        return "Latin Library", parts[0].removesuffix(".txt")
    return str(parts[0]).capitalize(), "/".join(parts[1:]).removesuffix(".txt")

def label_perseus(path):
    rel = path.relative_to(PERSEUS)
    parts = rel.parts
    author = parts[0]
    work = path.stem.removesuffix("_lat").removesuffix("_grc")
    return author, work

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
    result    = pyqtSignal(str, str, str, int, list, bool)   # corpus, author, work, line_idx, lines, is_xml
    finished  = pyqtSignal(int)
    status    = pyqtSignal(str)

    def __init__(self, pattern, ctx, do_ll, do_perseus, max_results):
        super().__init__()
        self.pattern     = pattern
        self.ctx         = ctx
        self.do_ll       = do_ll
        self.do_perseus  = do_perseus
        self.max_results = max_results
        self._stop       = False

    def stop(self):
        self._stop = True

    def run(self):
        total = 0
        sources = []
        if self.do_ll and LATIN_LIB.exists():
            sources.append((sorted(LATIN_LIB.rglob("*.txt")), False))
        if self.do_perseus and PERSEUS.exists():
            sources.append((sorted(PERSEUS.rglob("*_lat.xml")), True))

        for files, is_xml in sources:
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

        self.finished.emit(total)


# ── thread de tradução ────────────────────────────────────────────────────────

class GeminiThread(QThread):
    chunk  = pyqtSignal(str)
    status = pyqtSignal(str)   # mensagens de estado (ex: retry)
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
    """Tradução via API Claude com streaming."""
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
    """Carrega o modelo Ollama em memória em background ao iniciar a app."""
    pronto = pyqtSignal(str)   # emite o nome do modelo quando carregado
    falhou = pyqtSignal(str)   # emite mensagem de erro

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
    """Tradução com Ollama em streaming — emite fragmentos à medida que chegam."""
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
    """Gera o áudio em background para não bloquear a GUI."""
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


class TranslateThread(QThread):
    done = pyqtSignal(str)

    def __init__(self, texto, modo, lingua):
        super().__init__()
        self.texto  = texto
        self.modo   = modo   # 'traduzir' | 'ls' | 'lsj'
        self.lingua = lingua

    def run(self):
        if not _TRADUCAO_OK:
            self.done.emit("[Módulo traduzir_lat_grc.py não encontrado]")
            return
        try:
            if self.modo == "ls":
                # só definição inglesa — sem Google Translate
                self.done.emit(lookup_ls(self.texto.strip(), traduzir_pt=False))
            elif self.modo == "lsj":
                self.done.emit(lookup_lsj(self.texto.strip(), traduzir_pt=False))
            else:
                self.done.emit("[modo desativado]")
        except Exception as e:
            self.done.emit(f"[Erro: {e}]")


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
        self._texto_pronunciar    = ""   # primeiro bloco (pronúncia automática)
        self._texto_pronunciando  = ""   # texto em curso (para reinício por velocidade)
        self._selecao_salva       = ""   # última selecção antes de perder foco
        self._settings_timer      = None
        self._reiniciar_timer     = None
        self._build_ui()
        self._carregar_settings()

    # ── construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Busca Latina")
        self.resize(1000, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 6)

        # ── barra de busca ────────────────────────────────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("amor=exato · amor-=prefixo · -que=sufixo · -amor-=infixo · regex puro se usar . * + [ \\")
        self.entry.setFont(QFont("monospace", 11))
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

        # ── opções ────────────────────────────────────────────────────────────
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)

        self.chk_ignore = QCheckBox("Ignorar maiúsculas")
        self.chk_ignore.setChecked(True)
        opts_row.addWidget(self.chk_ignore)

        opts_row.addWidget(self._sep())

        ctx_lbl = QLabel("Contexto:")
        opts_row.addWidget(ctx_lbl)
        self.spin_ctx = QSpinBox()
        self.spin_ctx.setRange(0, 10)
        self.spin_ctx.setValue(2)
        self.spin_ctx.setFixedWidth(50)
        opts_row.addWidget(self.spin_ctx)

        opts_row.addWidget(self._sep())

        max_lbl = QLabel("Máx. resultados:")
        opts_row.addWidget(max_lbl)
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
        for i, lbl in enumerate(["Ambos", "Latin Library", "Perseus"]):
            rb = QRadioButton(lbl)
            self.bg.addButton(rb, i)
            cg_layout.addWidget(rb)
        self.bg.button(0).setChecked(True)
        opts_row.addWidget(corpus_grp)

        opts_row.addStretch()
        root.addLayout(opts_row)

        # ── splitter: lista de obras | resultado ──────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # painel esquerdo: lista de obras
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

        # painel direito: texto dos resultados
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("monospace", 10))
        # guarda a selecção sempre que muda — evita perda ao clicar botões
        self.text.selectionChanged.connect(self._on_selecao_mudada)
        splitter.addWidget(self.text)

        splitter.setSizes([250, 750])

        # ── splitter vertical: resultados | tradução ──────────────────────────
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(splitter_widget := QWidget())
        # reatribui o splitter horizontal ao widget contentor
        lay_top = QVBoxLayout(splitter_widget)
        lay_top.setContentsMargins(0, 0, 0, 0)
        lay_top.addWidget(splitter)

        # painel de tradução
        trans_panel = QWidget()
        trans_layout = QVBoxLayout(trans_panel)
        trans_layout.setContentsMargins(0, 4, 0, 0)
        trans_layout.setSpacing(4)

        # ── linha 1: IA (Ollama) ──────────────────────────────────────────────
        ctrl_ia = QHBoxLayout()
        ctrl_ia.setSpacing(6)

        ctrl_ia.addWidget(QLabel("Língua:"))
        self.combo_lingua = QComboBox()
        self.combo_lingua.addItems(["Latim", "Grego Antigo"])
        self.combo_lingua.setFixedWidth(120)
        ctrl_ia.addWidget(self.combo_lingua)

        ctrl_ia.addWidget(QLabel("Modelo:"))
        self.combo_modelo = QComboBox()
        self.combo_modelo.setMinimumWidth(180)
        self.combo_modelo.setToolTip(
            "Modelos Ollama instalados\n"
            "Para instalar: ollama pull llama3.2"
        )
        self.combo_modelo.addItem("(sem modelos — instale Ollama)", None)
        self.combo_modelo.currentIndexChanged.connect(self._on_modelo_mudado)
        ctrl_ia.addWidget(self.combo_modelo)

        self.btn_ollama = QPushButton("🤖 Traduzir →PT")
        self.btn_ollama.setToolTip(
            "Traduz a seleção com IA local (Ollama)\n"
            "Selecione o texto nos resultados primeiro"
        )
        self.btn_ollama.clicked.connect(self._on_ollama_traduzir)
        ctrl_ia.addWidget(self.btn_ollama)

        self.btn_comentario = QPushButton("📖 Comentário")
        self.btn_comentario.setToolTip(
            "Comentário filológico com IA:\n"
            "gramática, vocabulário e contexto literário"
        )
        self.btn_comentario.clicked.connect(self._on_ollama_comentario)
        ctrl_ia.addWidget(self.btn_comentario)

        self.btn_parar_ia = QPushButton("⏹ Parar")
        self.btn_parar_ia.setFixedWidth(70)
        self.btn_parar_ia.setToolTip("Interrompe a geração de texto")
        self.btn_parar_ia.clicked.connect(self._on_parar_ia)
        ctrl_ia.addWidget(self.btn_parar_ia)

        ctrl_ia.addWidget(self._sep())

        # ── Claude API ─────────────────────────────────────────────────────────
        self.btn_claude = QPushButton("✨ Claude →PT")
        self.btn_claude.setToolTip(
            "Traduz com a API Claude (Anthropic)\n"
            "Requer chave API em ANTHROPIC_API_KEY ou nas definições"
        )
        self.btn_claude.clicked.connect(self._on_claude_traduzir)
        ctrl_ia.addWidget(self.btn_claude)

        self.combo_claude_modelo = QComboBox()
        self.combo_claude_modelo.setMinimumWidth(160)
        for mid, rotulo in MODELOS_CLAUDE:
            self.combo_claude_modelo.addItem(rotulo, mid)
        # Selecciona Haiku por omissão (mais rápido e económico para uso frequente)
        for i in range(self.combo_claude_modelo.count()):
            if "haiku" in self.combo_claude_modelo.itemData(i).lower():
                self.combo_claude_modelo.setCurrentIndex(i)
                break
        ctrl_ia.addWidget(self.combo_claude_modelo)

        self.btn_claude_chave = QPushButton("🔑")
        self.btn_claude_chave.setFixedWidth(30)
        self.btn_claude_chave.setToolTip("Configurar chave API Claude")
        self.btn_claude_chave.clicked.connect(self._on_configurar_chave_claude)
        ctrl_ia.addWidget(self.btn_claude_chave)

        ctrl_ia.addWidget(self._sep())

        # ── Gemini ─────────────────────────────────────────────────────────────
        self.btn_gemini = QPushButton("🌟 Gemini →PT")
        self.btn_gemini.setToolTip(
            "Traduz com a API Gemini (Google)\n"
            "Chave gratuita em: aistudio.google.com"
        )
        self.btn_gemini.clicked.connect(self._on_gemini_traduzir)
        ctrl_ia.addWidget(self.btn_gemini)

        self.combo_gemini_modelo = QComboBox()
        self.combo_gemini_modelo.setMinimumWidth(160)
        for mid, rotulo in MODELOS_GEMINI:
            self.combo_gemini_modelo.addItem(rotulo, mid)
        ctrl_ia.addWidget(self.combo_gemini_modelo)

        self.btn_gemini_chave = QPushButton("🔑")
        self.btn_gemini_chave.setFixedWidth(30)
        self.btn_gemini_chave.setToolTip("Configurar chave API Gemini")
        self.btn_gemini_chave.clicked.connect(self._on_configurar_chave_gemini)
        ctrl_ia.addWidget(self.btn_gemini_chave)

        ctrl_ia.addWidget(self._sep())

        # ── Whitaker's Words ───────────────────────────────────────────────────
        self.btn_whitaker = QPushButton("📖 Whitaker")
        self.btn_whitaker.setToolTip(
            "Análise morfológica palavra a palavra (Whitaker's Words)\n"
            "Forma, declensão/conjugação e significado — requer internet"
        )
        self.btn_whitaker.clicked.connect(self._on_whitaker)
        ctrl_ia.addWidget(self.btn_whitaker)

        ctrl_ia.addWidget(self._sep())

        # ── dicionários offline ────────────────────────────────────────────────
        ctrl_ia.addWidget(QLabel("Dicionário:"))

        self.btn_ls = QPushButton("L&S")
        self.btn_ls.setToolTip(
            "Lewis & Short — latim → inglês (offline)\n"
            "Duplo-clique numa palavra activa automaticamente"
        )
        self.btn_ls.clicked.connect(lambda: self._on_dicionario("ls"))
        ctrl_ia.addWidget(self.btn_ls)

        self.btn_lsj = QPushButton("LSJ")
        self.btn_lsj.setToolTip("Liddell-Scott-Jones — grego → inglês (offline)")
        self.btn_lsj.clicked.connect(lambda: self._on_dicionario("lsj"))
        ctrl_ia.addWidget(self.btn_lsj)

        self.btn_limpar_tr = QPushButton("Limpar")
        self.btn_limpar_tr.setFixedWidth(60)
        self.btn_limpar_tr.clicked.connect(lambda: self.trans_out.clear())
        ctrl_ia.addWidget(self.btn_limpar_tr)

        ctrl_ia.addStretch()
        trans_layout.addLayout(ctrl_ia)

        # carrega modelos Ollama em background ao iniciar
        QTimer.singleShot(2000, self._atualizar_modelos_ollama)

        # ── linha de pronúncia ────────────────────────────────────────────────
        pron_row = QHBoxLayout()
        pron_row.setSpacing(6)

        pron_row.addWidget(QLabel("Pronúncia:"))

        self.btn_pronunciar = QPushButton("🔊 Pronunciar")
        self.btn_pronunciar.setToolTip("Pronuncia o texto seleccionado (ou a passagem actual)")
        self.btn_pronunciar.clicked.connect(self._on_pronunciar)
        self.btn_pronunciar.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_pronunciar)

        self.btn_parar_som = QPushButton("■ Parar")
        self.btn_parar_som.setFixedWidth(70)
        self.btn_parar_som.clicked.connect(self._on_parar_som)
        self.btn_parar_som.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_parar_som)

        self.btn_ipa = QPushButton("IPA")
        self.btn_ipa.setToolTip("Mostra transcrição fonética (IPA) do texto seleccionado")
        self.btn_ipa.setFixedWidth(50)
        self.btn_ipa.clicked.connect(self._on_ipa)
        self.btn_ipa.setEnabled(_PRONUNCIA_OK)
        pron_row.addWidget(self.btn_ipa)

        pron_row.addWidget(self._sep())

        pron_row.addWidget(QLabel("Voz:"))
        self.combo_voz = QComboBox()
        self.combo_voz.setMinimumWidth(230)
        for vid, rotulo, *_ in VOZES:
            self.combo_voz.addItem(rotulo, vid)
        self.combo_voz.currentIndexChanged.connect(self._salvar_settings)
        pron_row.addWidget(self.combo_voz)

        pron_row.addWidget(self._sep())

        pron_grp = QGroupBox("Variante")
        pron_grp.setFlat(True)
        pg_lay = QHBoxLayout(pron_grp)
        pg_lay.setContentsMargins(0, 0, 0, 0)
        pg_lay.setSpacing(6)
        self.bg_pron = QButtonGroup(self)
        for i, lbl in enumerate(["Clássico", "Eclesiástico"]):
            rb = QRadioButton(lbl)
            self.bg_pron.addButton(rb, i)
            pg_lay.addWidget(rb)
        self.bg_pron.button(0).setChecked(True)
        self.bg_pron.buttonClicked.connect(self._salvar_settings)
        pron_row.addWidget(pron_grp)

        pron_row.addWidget(self._sep())

        pron_row.addWidget(QLabel("Velocidade:"))
        self.slider_vel = QSlider(Qt.Horizontal)
        self.slider_vel.setRange(70, 220)
        self.slider_vel.setValue(130)
        self.slider_vel.setFixedWidth(100)
        self.slider_vel.setTickInterval(30)
        self.slider_vel.setTickPosition(QSlider.TicksBelow)
        self.lbl_vel = QLabel("130")
        self.slider_vel.valueChanged.connect(self._on_velocidade_mudada)
        pron_row.addWidget(self.slider_vel)
        pron_row.addWidget(self.lbl_vel)

        pron_row.addStretch()
        trans_layout.addLayout(pron_row)

        self.trans_out = QTextEdit()
        self.trans_out.setReadOnly(True)
        self.trans_out.setFont(QFont("serif", 10))
        self.trans_out.setPlaceholderText(
            "🤖 Traduzir →PT  — tradução com IA local (Ollama)\n"
            "📖 Comentário    — análise filológica com IA\n"
            "L&S / LSJ        — dicionário offline (duplo-clique numa palavra)\n\n"
            "Selecione texto nos resultados e use os botões acima."
        )
        trans_layout.addWidget(self.trans_out)

        vsplit.addWidget(trans_panel)
        vsplit.setSizes([480, 200])
        root.addWidget(vsplit, 1)

        # duplo-clique no texto de resultados → dicionário automático
        self.text.mouseDoubleClickEvent = self._on_text_dblclick

        # menu de contexto (botão direito) com opções de tradução
        self.text.contextMenuEvent = self._on_text_context_menu

        # ── barra de status ───────────────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        msg = "Pronto." if _TRADUCAO_OK else "Aviso: módulo traduzir_lat_grc.py não encontrado — tradução indisponível."
        self.status_bar.showMessage(msg)

        # armazenamento interno: {obra_key: [(line_idx, lines, is_xml), ...]}
        self._work_data   = {}
        self._work_order  = []
        self._pattern     = None

    def _sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        return sep

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

        # limpa estado anterior
        self.text.clear()
        self.list_works.clear()
        self._work_data      = {}
        self._work_order     = []
        self._texto_pronunciar = ""
        self._selecao_salva  = ""
        self.total = 0

        corpus_id = self.bg.checkedId()
        do_ll      = corpus_id in (0, 1)
        do_perseus = corpus_id in (0, 2)

        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait()

        self.thread = SearchThread(
            self._pattern,
            self.spin_ctx.value(),
            do_ll, do_perseus,
            self.spin_max.value(),
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
            item.setData(Qt.UserRole, key)
            self.list_works.addItem(item)

        self._work_data[key].append((line_idx, lines, is_xml))

        # mostra no texto somente se esta obra estiver selecionada (ou nenhuma)
        current = self.list_works.currentItem()
        if current is None or current.data(Qt.UserRole) == key:
            if current is None:
                self._append_result(key, line_idx, lines, is_xml)
            else:
                self._append_result(key, line_idx, lines, is_xml)

        self.status_bar.showMessage(
            f"{self.total} ocorrência(s) encontrada(s)…"
        )

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
        key = current.data(Qt.UserRole)
        self.text.clear()
        self._texto_pronunciar = ""   # limpa enquanto recarrega
        for line_idx, lines, is_xml in self._work_data.get(key, []):
            self._append_result(key, line_idx, lines, is_xml)
            # só a 1.ª passagem serve de texto activo; _append_result actualiza sempre

    def _append_result(self, key, line_idx, lines, is_xml):
        ctx = self.spin_ctx.value()
        start = max(0, line_idx - ctx)
        end   = min(len(lines), line_idx + ctx + 1)

        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)

        # cabeçalho
        hdr_fmt = QTextCharFormat()
        hdr_fmt.setForeground(QColor("#1a6fa8"))
        hdr_fmt.setFontWeight(700)
        cursor.insertText(f"\n{key}  (linha {line_idx + 1})\n", hdr_fmt)

        # linhas de contexto
        normal_fmt = QTextCharFormat()
        normal_fmt.setForeground(QColor("#dddddd") if self._is_dark() else QColor("#222222"))

        hi_fmt = QTextCharFormat()
        hi_fmt.setBackground(QColor("#2d5a8e") if self._is_dark() else QColor("#d6eaf8"))
        hi_fmt.setForeground(QColor("#ffffff") if self._is_dark() else QColor("#000000"))

        for j in range(start, end):
            line = lines[j].rstrip()
            if j == line_idx:
                # destaca o termo dentro da linha
                self._insert_highlighted_line(cursor, line, hi_fmt, normal_fmt)
            else:
                cursor.insertText(f"  {line}\n", normal_fmt)

        sep_fmt = QTextCharFormat()
        sep_fmt.setForeground(QColor("#555555"))
        cursor.insertText("─" * 60 + "\n", sep_fmt)

        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

        # guarda apenas o PRIMEIRO bloco; os seguintes não sobrepõem
        if not self._texto_pronunciar:
            passagem = " ".join(lines[j].rstrip() for j in range(start, end))
            self._texto_pronunciar = re.sub(r'\s+', ' ', passagem).strip()

    def _insert_highlighted_line(self, cursor, line, hi_fmt, normal_fmt):
        """Insere a linha com o termo buscado realçado."""
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
            f"Chave actual: {placeholder}\n\n"
            "Obtenha gratuitamente em aistudio.google.com\n\n"
            "Insira a nova chave:",
            QLineEdit.Password,
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
                                "Configure a chave Gemini clicando no botão 🔑 ao lado.\n"
                                "Obtenha gratuitamente em aistudio.google.com")
            return
        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\n"
                "Seleccione texto no painel de resultados e clique novamente."
            )
            return
        modelo = self.combo_gemini_modelo.currentData() or GEMINI_DEFAULT
        lingua = self._lingua_ollama()

        if self._gemini_thread is not None and self._gemini_thread.isRunning():
            self._gemini_thread.stop()
            self._gemini_thread.wait(1000)

        self.trans_out.setPlainText(f"🌟 Gemini ({modelo})…\n\n")
        self._gemini_thread = GeminiThread(texto, lingua, modelo, chave)
        self._gemini_thread.chunk.connect(self._on_ollama_chunk)
        self._gemini_thread.status.connect(self.status_bar.showMessage)
        self._gemini_thread.done.connect(
            lambda: self.status_bar.showMessage("✓ Tradução Gemini concluída."))
        self._gemini_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Gemini: {e}"))
        self._gemini_thread.start()
        self.status_bar.showMessage("Gemini a traduzir…")

    # ── Whitaker's Words ──────────────────────────────────────────────────────

    def _on_whitaker(self):
        if not _WHITAKER_OK:
            self.trans_out.setPlainText("⚠ whitakers_words.py não encontrado.")
            return
        texto = self._texto_selecionado()
        # Para Whitaker, usa só a primeira palavra se for uma selecção longa
        palavras = texto.split()
        if len(palavras) > 6:
            # frase curta — analisa tudo; texto longo — mostra aviso
            self.trans_out.setPlainText(
                "⚠ Seleccione uma palavra ou frase curta (até 6 palavras) para análise Whitaker."
            )
            return
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Seleccione texto (palavra ou frase curta) nos resultados primeiro."
            )
            return

        self.trans_out.setPlainText(f"📖 Whitaker's Words: «{texto.strip()}»\n\n⏳ A consultar…")

        if self._whitaker_thread is not None and self._whitaker_thread.isRunning():
            self._whitaker_thread.wait(2000)

        self._whitaker_thread = WhitakerThread(texto.strip())
        self._whitaker_thread.resultado.connect(
            lambda r: self.trans_out.setPlainText(
                f"📖 Whitaker's Words — «{texto.strip()}»\n\n{r}"
            )
        )
        self._whitaker_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Whitaker: {e}"))
        self._whitaker_thread.start()
        self.status_bar.showMessage("Whitaker's Words a analisar…")

    # ── Claude API ────────────────────────────────────────────────────────────

    def _on_configurar_chave_claude(self):
        """Diálogo para inserir/actualizar a chave API Claude."""
        chave_actual = (obter_chave() if _CLAUDE_OK else "") or ""
        placeholder  = chave_actual[:8] + "…" if chave_actual else "(não definida)"
        texto, ok = QInputDialog.getText(
            self,
            "Chave API Claude (Anthropic)",
            f"Chave actual: {placeholder}\n\nInsira a nova chave (ou cancele para manter):",
            QLineEdit.Password,
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
            QMessageBox.warning(
                self, "Chave API em falta",
                "Configure a chave API Claude clicando no botão 🔑 ao lado.",
            )
            return
        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\n"
                "Seleccione texto no painel de resultados e clique novamente."
            )
            return

        modelo = self.combo_claude_modelo.currentData() or MODELO_DEFAULT
        lingua = self._lingua_ollama()   # reutiliza o selector Latim/Grego

        if self._claude_thread is not None and self._claude_thread.isRunning():
            self._claude_thread.stop()
            self._claude_thread.wait(1000)

        self.trans_out.setPlainText(f"✨ Claude ({modelo})…\n\n")
        self._claude_thread = ClaudeThread(texto, lingua, modelo, chave)
        self._claude_thread.chunk.connect(self._on_ollama_chunk)  # mesmo handler
        self._claude_thread.done.connect(
            lambda: self.status_bar.showMessage("✓ Tradução Claude concluída.")
        )
        self._claude_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Claude: {e}")
        )
        self._claude_thread.start()
        self.status_bar.showMessage(f"Claude a traduzir…")

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
            # Pré-carrega o melhor modelo automaticamente
            self._iniciar_precarregamento(mods[0])
        else:
            self.combo_modelo.addItem("(Ollama sem modelos)", None)
            self.status_bar.showMessage(
                "Ollama sem modelos. Execute: ollama pull llama3.2"
            )

    def _iniciar_precarregamento(self, modelo: str):
        """Lança o thread de pré-carregamento do modelo Ollama."""
        if self._precarregar_thread is not None and self._precarregar_thread.isRunning():
            return  # já a carregar
        self.status_bar.showMessage(f"⏳ A carregar modelo IA ({modelo})…")
        self.btn_ollama.setEnabled(False)
        self.btn_comentario.setEnabled(False)
        self._precarregar_thread = PrecarregarThread(modelo)
        self._precarregar_thread.pronto.connect(self._on_modelo_pronto)
        self._precarregar_thread.falhou.connect(self._on_modelo_falhou)
        self._precarregar_thread.start()

    def _on_modelo_mudado(self, _idx: int):
        """Quando o utilizador muda de modelo, pré-carrega o novo."""
        modelo = self._modelo_ollama()
        if modelo:  # None = "melhor disponível", não dispara pré-carregamento extra
            if self._precarregar_thread is not None and self._precarregar_thread.isRunning():
                self._precarregar_thread.terminate()
                self._precarregar_thread.wait(500)
            self._iniciar_precarregamento(modelo)

    def _on_modelo_pronto(self, nome: str):
        self.status_bar.showMessage(f"✓ Modelo IA pronto: {nome}")
        self.btn_ollama.setEnabled(True)
        self.btn_comentario.setEnabled(True)

    def _on_modelo_falhou(self, nome: str):
        self.status_bar.showMessage(
            "⚠ Ollama não responde — inicie com: ollama serve"
        )
        self.btn_ollama.setEnabled(True)
        self.btn_comentario.setEnabled(True)

    def _modelo_ollama(self) -> str | None:
        return self.combo_modelo.currentData()

    def _lingua_ollama(self) -> str:
        return "la" if self.combo_lingua.currentIndex() == 0 else "grc"

    def _iniciar_ollama(self, modo: str):
        if not _OLLAMA_OK:
            self.trans_out.setPlainText("⚠ ollama_lat.py não encontrado.")
            return

        texto = self._texto_selecionado()
        if not texto.strip():
            self.trans_out.setPlainText(
                "⚠ Nenhum texto seleccionado.\n"
                "Seleccione texto no painel de resultados e clique novamente."
            )
            return

        modelo = self._modelo_ollama()
        lingua = "comentario" if modo == "comentario" else self._lingua_ollama()

        # cancela thread anterior (sem chamar isRunning() em None)
        if self._ollama_thread is not None and self._ollama_thread.isRunning():
            self._ollama_thread.stop()
            self._ollama_thread.wait(1000)

        # feedback imediato antes de iniciar o thread
        rotulo = "Comentário" if modo == "comentario" else "Tradução →PT"
        self.trans_out.setPlainText(
            f"⏳ {rotulo} com {modelo or 'llama3.2'}…\n\n"
            f"(1.ª vez pode demorar 30–60 s enquanto o modelo carrega)"
        )

        self._ollama_thread = OllamaThread(texto, lingua, modelo)
        self._ollama_thread.chunk.connect(self._on_ollama_chunk)
        self._ollama_thread.done.connect(
            lambda: self.status_bar.showMessage("✓ Tradução IA concluída.")
        )
        self._ollama_thread.erro.connect(
            lambda e: self.trans_out.setPlainText(f"⚠ Erro Ollama: {e}")
        )
        self._ollama_thread.start()
        self.status_bar.showMessage(f"Ollama a processar…")

    def _on_ollama_chunk(self, frag: str):
        """Recebe cada fragmento do modelo e acrescenta ao campo de saída."""
        cursor = self.trans_out.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.trans_out.setTextCursor(cursor)
        self.trans_out.insertPlainText(frag)

    def _on_ollama_traduzir(self):
        self._iniciar_ollama("traduzir")

    def _on_ollama_comentario(self):
        self._iniciar_ollama("comentario")

    # ── pronúncia ─────────────────────────────────────────────────────────────

    def _texto_para_pronunciar(self) -> str:
        # 1. Selecção manual tem prioridade
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            sel = re.sub(r'^[▶■─=\s]+', '', sel, flags=re.MULTILINE)
            return sel.strip()
        # 2. Passagem activa (último resultado exibido / obra seleccionada)
        if self._texto_pronunciar:
            return self._texto_pronunciar
        # 3. Fallback: todo o texto visível
        txt = re.sub(r'^[▶■─=\s]+', '', self.text.toPlainText(), flags=re.MULTILINE)
        return txt.strip()[:3000]

    def _variante_pron(self) -> str:
        return 'eclesiastico' if self.bg_pron.checkedId() == 1 else 'classico'

    def _voz_selecionada(self) -> str:
        return self.combo_voz.currentData() or "it-IT-DiegoNeural"

    def _on_pronunciar(self):
        if not _PRONUNCIA_OK:
            return
        texto = self._texto_para_pronunciar()
        if not texto:
            return
        self._lancar_pronuncia(texto)

    def _lancar_pronuncia(self, texto: str):
        """Inicia (ou reinicia) a pronúncia com o texto e parâmetros actuais."""
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
        """Chamado em cada tick do slider de velocidade."""
        self.lbl_vel.setText(str(valor))
        self._agenda_salvar_settings()

        # Se estiver a reproduzir, agenda reinício com a nova velocidade
        if _PRONUNCIA_OK and self._texto_pronunciando:
            if self._reiniciar_timer is None:
                self._reiniciar_timer = QTimer(self)
                self._reiniciar_timer.setSingleShot(True)
                self._reiniciar_timer.timeout.connect(self._reiniciar_pronuncia)
            self._reiniciar_timer.start(400)   # 400 ms de debounce

    def _reiniciar_pronuncia(self):
        """Reinicia a pronúncia em curso com a velocidade actual."""
        if _PRONUNCIA_OK and self._texto_pronunciando:
            self._lancar_pronuncia(self._texto_pronunciando)

    def _on_parar_som(self):
        if _PRONUNCIA_OK:
            parar()                                   # mata edge-tts e ffplay
        if self.pron_thread and self.pron_thread.isRunning():
            self.pron_thread.terminate()              # força encerramento do thread

    def _on_ipa(self):
        if not _PRONUNCIA_OK:
            return
        texto = self._texto_para_pronunciar()
        if not texto:
            return
        ipa = ipa_classico(texto[:300])
        self.trans_out.setPlainText(f"IPA (clássico):\n{ipa}")

    # ── tradução e dicionário ─────────────────────────────────────────────────

    def _on_selecao_mudada(self):
        """Guarda a selecção actual antes de ela ser perdida ao clicar botões."""
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            self._selecao_salva = sel

    def _texto_selecionado(self) -> str:
        """
        Devolve o texto a traduzir/pronunciar.
        Prioridade:
          1. Selecção activa no widget
          2. Última selecção guardada (antes de perder foco ao clicar botão)
          3. Primeiro bloco limpo do resultado actual
        """
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            return sel
        if self._selecao_salva:
            return self._selecao_salva
        # Usa o primeiro bloco limpo (sem marcadores de formatação)
        return self._texto_pronunciar

    def _lingua_api(self) -> str:
        return "la" if self.combo_lingua.currentIndex() == 0 else "grc"

    def _rodar_traducao(self, texto: str, modo: str):
        if not texto.strip():
            return
        self.trans_out.setPlaceholderText("")
        self.trans_out.setText("⏳ Processando…")
        if self.trans_thread and self.trans_thread.isRunning():
            self.trans_thread.terminate()
        self.trans_thread = TranslateThread(texto, modo, self._lingua_api())
        self.trans_thread.done.connect(self.trans_out.setPlainText)
        self.trans_thread.start()

    def _on_dicionario(self, modo: str):
        """Consulta L&S ou LSJ (offline, definição em inglês)."""
        palavra = self.text.textCursor().selectedText().strip().split()[0] if \
                  self.text.textCursor().selectedText().strip() else ""
        if not palavra:
            self.trans_out.setPlainText("Selecione uma palavra no painel de resultados primeiro.")
            return
        self._rodar_traducao(palavra, modo)

    def _on_text_dblclick(self, event):
        """Duplo-clique: consulta automaticamente o dicionário (L&S ou LSJ)."""
        QTextEdit.mouseDoubleClickEvent(self.text, event)
        palavra = self.text.textCursor().selectedText().strip()
        if not palavra:
            return
        modo = "lsj" if self.combo_lingua.currentIndex() == 1 else "ls"
        self._rodar_traducao(palavra, modo)

    def _on_text_context_menu(self, event):
        """Menu de contexto com opções de tradução para o texto seleccionado."""
        menu = self.text.createStandardContextMenu()
        sel = self.text.textCursor().selectedText().strip()
        if sel:
            menu.addSeparator()
            if _OLLAMA_OK:
                menu.addAction("🤖 Traduzir →PT (Ollama)").triggered.connect(
                    self._on_ollama_traduzir)
                menu.addAction("📖 Comentário (Ollama)").triggered.connect(
                    self._on_ollama_comentario)
            if _CLAUDE_OK:
                menu.addAction("✨ Traduzir →PT (Claude)").triggered.connect(
                    self._on_claude_traduzir)
            if _GEMINI_OK:
                menu.addAction("🌟 Traduzir →PT (Gemini)").triggered.connect(
                    self._on_gemini_traduzir)
            menu.addSeparator()
            menu.addAction("L&S (Lewis & Short)").triggered.connect(
                lambda: self._on_dicionario("ls"))
            menu.addAction("LSJ (Liddell-Scott-Jones)").triggered.connect(
                lambda: self._on_dicionario("lsj"))
        menu.exec_(event.globalPos())

    def _on_parar_ia(self):
        if hasattr(self, '_ollama_thread') and self._ollama_thread.isRunning():
            self._ollama_thread.stop()
            self.status_bar.showMessage("Geração interrompida.")

    # ── persistência de configurações ────────────────────────────────────────

    def _carregar_settings(self):
        try:
            s = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return

        # voz
        voz = s.get("voz", "")
        for i in range(self.combo_voz.count()):
            if self.combo_voz.itemData(i) == voz:
                self.combo_voz.setCurrentIndex(i)
                break

        # variante (clássico / eclesiástico)
        variante = s.get("variante", 0)
        btn = self.bg_pron.button(variante)
        if btn:
            btn.setChecked(True)

        # velocidade
        self.slider_vel.setValue(s.get("velocidade", 130))

    def _salvar_settings(self, *_):
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            s = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            s = {}
        s["voz"]        = self._voz_selecionada()
        s["variante"]   = self.bg_pron.checkedId()
        s["velocidade"] = self.slider_vel.value()
        SETTINGS_FILE.write_text(json.dumps(s, indent=2))

    def _agenda_salvar_settings(self):
        """Debounce: grava 600 ms após o utilizador parar de mover o slider."""
        if self._settings_timer is None:
            self._settings_timer = QTimer(self)
            self._settings_timer.setSingleShot(True)
            self._settings_timer.timeout.connect(self._salvar_settings)
        self._settings_timer.start(600)

    def _is_dark(self):
        bg = self.palette().color(QPalette.Window)
        return bg.lightness() < 128


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Busca Latina")
    app.setOrganizationName("belerofonte")
    win = BuscaLatina()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
