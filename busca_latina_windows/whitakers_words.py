#!/usr/bin/env python3
"""
whitakers_words.py — Análise morfológica de latim via Whitaker's Words
Windows 11 ARM / Snapdragon X (sem alterações funcionais — requer internet)
"""

import re
import sys
from typing import Iterator

import requests

_API = "https://latin-words.com/cgi-bin/translate.cgi"


def analisar_raw(texto: str) -> str:
    try:
        r = requests.get(_API, params={"query": texto.strip()}, timeout=15)
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "ok":
            return d.get("message", "").strip()
        return f"[Erro Whitaker: {d}]"
    except requests.exceptions.ConnectionError:
        return "[Sem ligação. Verifique a internet.]"
    except Exception as e:
        return f"[Erro: {e}]"


def _limpar(raw: str) -> str:
    raw = re.sub(r'MORE - hit RETURN.*', '', raw)
    raw = re.sub(r'Unexpected exception.*', '', raw)
    raw = re.sub(r'\r\n', '\n', raw)
    raw = re.sub(r' {3,}', '  ', raw)
    return raw.strip()


def analisar(texto: str) -> str:
    return _limpar(analisar_raw(texto))


def analisar_por_palavra(frase: str) -> Iterator[tuple[str, str]]:
    palavras = re.findall(r'[a-zA-ZÀ-ÿ]+', frase)
    for p in palavras:
        yield p, analisar(p)


if __name__ == "__main__":
    import argparse

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Análise morfológica latina (Whitaker's Words)")
    ap.add_argument("texto", nargs="+")
    ap.add_argument("--formato", choices=["raw", "tabela"], default="raw")
    args = ap.parse_args()

    frase = " ".join(args.texto)
    if args.formato == "tabela" and len(frase.split()) > 1:
        for palavra, analise in analisar_por_palavra(frase):
            print(f"\n{'─'*50}")
            print(f"  {palavra.upper()}")
            print('─'*50)
            print(analise)
    else:
        print(analisar(frase))
