#!/usr/bin/env python3
"""
traduzir_lat_grc.py — Tradução de latim/grego + dicionários L&S, LSJ, Collatinus PT, Wikt PT
Windows 11 ARM / Snapdragon X

Fontes:
  • Google Translate (gratuito, requer internet)
  • Lewis & Short (offline) — requer Diogenes instalado
  • LSJ — Liddell-Scott-Jones (offline) — requer Diogenes instalado
  • Collatinus latim→PT (offline, ~9900 entradas)
  • Wikcionário PT latim→PT (offline, requer download prévio)
"""

import os
import re
import sys
import unicodedata
from pathlib import Path

import requests

GTRANS = "https://translate.googleapis.com/translate_a/single"


# ── localização do Diogenes (Windows) ────────────────────────────────────────

def _encontrar_dados_diogenes() -> Path | None:
    """Procura o directório de dados do Diogenes nas localizações comuns do Windows."""
    candidatos = [
        # Instalador standard Windows
        Path(os.environ.get("LOCALAPPDATA", ""))  / "Programs" / "Diogenes" / "dependencies" / "data",
        Path(os.environ.get("PROGRAMFILES", ""))  / "Diogenes" / "dependencies" / "data",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Diogenes" / "dependencies" / "data",
        # Diogenes portátil ao lado deste script
        Path(__file__).parent / "diogenes_data",
        # Localização Linux (para compatibilidade se correr com WSL/wine)
        Path("/usr/local/diogenes/dependencies/data"),
    ]
    for p in candidatos:
        if p.exists():
            return p
    return None


_DIOGENES_DATA = _encontrar_dados_diogenes()

LS_XML  = (_DIOGENES_DATA / "lat.ls.perseus-eng1.xml") if _DIOGENES_DATA else Path("/dev/null")
LSJ_XML = (_DIOGENES_DATA / "grc.lsj.xml")             if _DIOGENES_DATA else Path("/dev/null")

# ── Dicionários PT ─────────────────────────────────────────────────────────────
if sys.platform == "win32":
    _cache_dir = Path(os.environ.get("APPDATA", Path.home())) / "BuscaLatina"
else:
    _cache_dir = Path.home() / ".cache" / "busca_latina"

WIKT_PT_DB = _cache_dir / "wiktionary_pt.db"

_COLLATINUS_DATA: dict | None = None
_COLLATINUS_CSV = Path(__file__).parent / "collatinus_pt.csv"
# fallback: mesma localização do módulo principal no Linux
_COLLATINUS_CSV_FALLBACK = Path.home() / ".local/share/collatinus/collatinus_pt.csv"

_ls_bytes:  bytes | None = None
_lsj_bytes: bytes | None = None


# ── utilitários XML ───────────────────────────────────────────────────────────

def _limpar_xml(texto: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", texto)
    txt = re.sub(r"&[a-zA-Z]+;", "", txt)
    return re.sub(r" {2,}", " ", txt).strip()


def _load_ls() -> bytes:
    global _ls_bytes
    if _ls_bytes is None:
        _ls_bytes = LS_XML.read_bytes()
    return _ls_bytes


def _load_lsj() -> bytes:
    global _lsj_bytes
    if _lsj_bytes is None:
        _lsj_bytes = LSJ_XML.read_bytes()
    return _lsj_bytes


def _extrair_entrada(data: bytes, marcador: bytes) -> str | None:
    pos = data.lower().find(marcador.lower())
    if pos == -1:
        return None
    start = -1
    for tag in (b'<div1', b'<div2'):
        s = data.rfind(tag, 0, pos)
        if s != -1:
            start = s
            break
    if start == -1:
        return None
    close = b'</div1>' if b'<div1' in data[start:start + 6] else b'</div2>'
    end   = data.find(close, pos) + len(close)
    if end <= len(close):
        return None
    raw = data[start:end].decode("utf-8", errors="replace")
    return _limpar_xml(raw)


# ── Google Translate ──────────────────────────────────────────────────────────

def traduzir_para_pt(texto: str, lingua: str = "la") -> str:
    if not texto.strip():
        return ""
    if lingua in ("grc", "el", "grego"):
        texto_api = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if not unicodedata.combining(c)
        )
        lang_api = "el"
    elif lingua in ("en", "inglês"):
        texto_api, lang_api = texto, "en"
    else:
        texto_api, lang_api = texto, "la"

    try:
        r = requests.get(GTRANS, params={
            "client": "gtx", "sl": lang_api, "tl": "pt",
            "dt": "t", "q": texto_api,
        }, timeout=15)
        r.raise_for_status()
        return "".join(p[0] for p in r.json()[0] if p[0])
    except requests.exceptions.ConnectionError:
        return "[Sem ligação à internet]"
    except Exception as e:
        return f"[Erro na tradução: {e}]"


# ── Lewis & Short ─────────────────────────────────────────────────────────────

def lookup_ls(palavra: str, traduzir_pt: bool = True) -> str:
    if not LS_XML.exists():
        return (
            "Lewis & Short não disponível.\n"
            "Instale o Diogenes em: https://community.dur.ac.uk/p.j.heslin/Software/Diogenes/"
        )
    data    = _load_ls()
    marcador = f">{palavra.strip()}</head>".encode("utf-8")
    entrada  = _extrair_entrada(data, marcador)
    if not entrada:
        marcador2 = f">{palavra.strip().lower()}</head>".encode("utf-8")
        entrada   = _extrair_entrada(data, marcador2)
    if not entrada:
        return f'"{palavra}" não encontrado no Lewis & Short.'

    entrada = entrada[:2000] + ("…" if len(entrada) > 2000 else "")
    if traduzir_pt:
        pt = traduzir_para_pt(entrada[:800], lingua="en")
        return (
            f"── Lewis & Short (EN) ──────────────────────\n{entrada}\n\n"
            f"── Tradução para PT ────────────────────────\n{pt}"
        )
    return entrada


# ── LSJ — Liddell-Scott-Jones ─────────────────────────────────────────────────

def lookup_lsj(palavra: str, traduzir_pt: bool = True) -> str:
    if not LSJ_XML.exists():
        return (
            "LSJ não disponível.\n"
            "Instale o Diogenes em: https://community.dur.ac.uk/p.j.heslin/Software/Diogenes/"
        )
    data    = _load_lsj()
    marcador = f">{palavra.strip()}</head>".encode("utf-8")
    entrada  = _extrair_entrada(data, marcador)
    if not entrada:
        sem_diac = "".join(
            c for c in unicodedata.normalize("NFD", palavra.strip())
            if not unicodedata.combining(c)
        )
        marcador2 = f">{sem_diac}</head>".encode("utf-8")
        entrada   = _extrair_entrada(data, marcador2)
    if not entrada:
        return f'"{palavra}" não encontrado no LSJ.'

    entrada = entrada[:2000] + ("…" if len(entrada) > 2000 else "")
    if traduzir_pt:
        pt = traduzir_para_pt(entrada[:800], lingua="en")
        return (
            f"── LSJ (EN) ────────────────────────────────\n{entrada}\n\n"
            f"── Tradução para PT ────────────────────────\n{pt}"
        )
    return entrada


# ── Collatinus PT ─────────────────────────────────────────────────────────────

def _load_collatinus_pt() -> dict[str, str]:
    global _COLLATINUS_DATA
    if _COLLATINUS_DATA is not None:
        return _COLLATINUS_DATA
    csv_path = _COLLATINUS_CSV if _COLLATINUS_CSV.exists() else _COLLATINUS_CSV_FALLBACK
    if not csv_path.exists():
        _COLLATINUS_DATA = {}
        return _COLLATINUS_DATA
    import csv
    data: dict[str, str] = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) >= 2:
                    data[row[0].strip().lower()] = row[1].strip()
    except Exception:
        pass
    _COLLATINUS_DATA = data
    return data


def lookup_collatinus_pt(palavra: str) -> str:
    data = _load_collatinus_pt()
    if not data:
        return (
            "Collatinus PT não disponível.\n"
            "Coloque o ficheiro collatinus_pt.csv na pasta do programa."
        )
    chave = palavra.strip().lower()
    if chave in data:
        return f"Collatinus — «{palavra}»\n\n{data[chave]}"
    # tenta forma sem diacríticos
    sem = "".join(
        c for c in unicodedata.normalize("NFD", chave)
        if not unicodedata.combining(c)
    )
    if sem in data:
        return f"Collatinus — «{palavra}»\n\n{data[sem]}"
    return f'"{palavra}" não encontrado no Collatinus PT.'


# ── Wikcionário PT ─────────────────────────────────────────────────────────────

def lookup_wikt_pt(palavra: str) -> str:
    if not WIKT_PT_DB.exists():
        return (
            "Wikcionário PT não disponível.\n"
            "Execute: python3 baixar_dicionario_pt.py   (requer internet)"
        )
    try:
        import sqlite3
        chave = palavra.strip().lower()
        with sqlite3.connect(str(WIKT_PT_DB)) as con:
            row = con.execute(
                "SELECT definicao FROM entradas WHERE lemma = ? COLLATE NOCASE LIMIT 1",
                (chave,)
            ).fetchone()
        if row:
            return f"Wikcionário PT — «{palavra}»\n\n{row[0]}"
        return f'"{palavra}" não encontrado no Wikcionário PT.'
    except Exception as e:
        return f"[Erro Wikcionário PT: {e}]"


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Tradução e dicionário latim/grego → PT")
    ap.add_argument("texto", nargs="+")
    ap.add_argument("--lingua", "-l", default="la", choices=["la", "grc", "en"])
    ap.add_argument("--dic", "-d", action="store_true",
                    help="Consultar dicionário (L&S ou LSJ)")
    args = ap.parse_args()
    texto = " ".join(args.texto)

    if args.dic:
        print(lookup_lsj(texto) if args.lingua == "grc" else lookup_ls(texto))
    else:
        print(traduzir_para_pt(texto, args.lingua))
