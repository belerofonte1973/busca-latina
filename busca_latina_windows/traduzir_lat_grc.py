#!/usr/bin/env python3
"""
traduzir_lat_grc.py — Tradução de latim/grego + dicionários L&S e LSJ
Windows 11 ARM / Snapdragon X

Fontes:
  • Google Translate (gratuito, requer internet)
  • Lewis & Short (offline) — requer Diogenes instalado
  • LSJ — Liddell-Scott-Jones (offline) — requer Diogenes instalado
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
