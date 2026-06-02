#!/usr/bin/env python3
"""
whitakers_words.py — Análise morfológica de latim via Whitaker's Words

Usa a API online latin-words.com, que corre o motor original de Whitaker.
Análise palavra a palavra: forma, declensão/conjugação, significado.

CLI:
  python3 whitakers_words.py amor
  python3 whitakers_words.py "Gallia est omnis divisa in partes tres"
  python3 whitakers_words.py --formato tabela amor
"""

import re
import requests
from typing import Iterator

_API = "https://latin-words.com/cgi-bin/translate.cgi"


# ── chamada à API ─────────────────────────────────────────────────────────────

def analisar_raw(texto: str) -> str:
    """
    Devolve a saída bruta da análise Whitaker's Words para o texto dado.
    O texto pode ser uma palavra ou uma frase curta.
    """
    try:
        r = requests.get(_API, params={"query": texto.strip()},
                         timeout=15)
        r.raise_for_status()
        d = r.json()
        if d.get("status") == "ok":
            return d.get("message", "").strip()
        return f"[Erro Whitaker: {d}]"
    except requests.exceptions.ConnectionError:
        return "[Sem ligação. Verifique a internet.]"
    except Exception as e:
        return f"[Erro: {e}]"


# ── formatação ────────────────────────────────────────────────────────────────

def _limpar(raw: str) -> str:
    """Remove artefactos da saída do programa original (prompts, etc.)."""
    raw = re.sub(r'MORE - hit RETURN.*', '', raw)
    raw = re.sub(r'Unexpected exception.*', '', raw)
    raw = re.sub(r'\r\n', '\n', raw)
    raw = re.sub(r' {3,}', '  ', raw)
    return raw.strip()


def analisar(texto: str) -> str:
    """Análise formatada, pronta para mostrar na GUI."""
    raw = analisar_raw(texto)
    return _limpar(raw)


def analisar_por_palavra(frase: str) -> Iterator[tuple[str, str]]:
    """
    Para cada palavra da frase, devolve (palavra, análise).
    Útil para mostrar a análise por partes.
    """
    palavras = re.findall(r'[a-zA-ZÀ-ÿ]+', frase)
    for p in palavras:
        yield p, analisar(p)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(
        description="Análise morfológica latina (Whitaker's Words)")
    ap.add_argument("texto", nargs="+")
    ap.add_argument("--formato", choices=["raw", "tabela"], default="raw",
                    help="Formato de saída (padrão: raw)")
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
