#!/usr/bin/env python3
"""
claude_lat.py — Tradução de latim/grego para português via Claude / OpenRouter

Suporta dois provedores (detectado automaticamente pelo prefixo da chave):
  sk-ant-...  →  API Anthropic direta   (console.anthropic.com)
  sk-or-...   →  OpenRouter             (openrouter.ai/keys)

Configuração da chave de API:
  1. Variável de ambiente:  export ANTHROPIC_API_KEY="sk-ant-..."
                        ou  export ANTHROPIC_API_KEY="sk-or-..."
  2. Ficheiro de config:    ~/.config/busca_latina/settings.json  →  "claude_api_key": "..."

CLI:
  python3 claude_lat.py "Gallia est omnis divisa in partes tres"
  python3 claude_lat.py "arma virumque cano" --lingua la --modelo claude-haiku-4-5
  python3 claude_lat.py "amor" --comentario
  python3 claude_lat.py --guardar-chave "sk-or-..."
"""

import os
import json
from pathlib import Path
from typing import Iterator

SETTINGS_FILE = Path.home() / ".config" / "busca_latina" / "settings.json"

# Modelos disponíveis (do mais rápido/barato ao mais capaz)
MODELOS_CLAUDE = [
    ("claude-haiku-4-5",   "Haiku 4.5  — rápido, económico"),
    ("claude-sonnet-4-6",  "Sonnet 4.6 — equilíbrio"),
    ("claude-opus-4-8",    "Opus 4.8   — máxima qualidade"),
]
MODELO_DEFAULT = "claude-opus-4-8"

# URLs dos provedores
_URL_ANTHROPIC   = None                       # padrão do SDK
_URL_OPENROUTER  = "https://openrouter.ai/api"


def _detetar_provedor(chave: str) -> tuple[str | None, str]:
    """
    Devolve (base_url, provedor_nome) com base no prefixo da chave.
      sk-ant-...  → API Anthropic direta
      sk-or-...   → OpenRouter (camada Anthropic-compatível)
    """
    if chave.startswith("sk-or-"):
        return _URL_OPENROUTER, "OpenRouter"
    return _URL_ANTHROPIC, "Anthropic"

PROMPTS = {
    "la": (
        "És um especialista em latim clássico e língua portuguesa. "
        "Traduz o seguinte texto do latim para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem comentários ou explicações.\n\n"
        "Texto latino:\n{texto}\n\nTradução:"
    ),
    "grc": (
        "És um especialista em grego antigo e língua portuguesa. "
        "Traduz o seguinte texto do grego antigo para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto grego:\n{texto}\n\nTradução:"
    ),
    "comentario": (
        "És um professor de latim clássico. "
        "Faz um comentário filológico breve (3–5 frases) do seguinte trecho, "
        "em português do Brasil, cobrindo: estrutura gramatical, "
        "vocabulário notável e contexto literário.\n\n"
        "Trecho:\n{texto}\n\nComentário:"
    ),
}


# ── gestão da chave API ───────────────────────────────────────────────────────

def obter_chave() -> str | None:
    """Lê a chave API de (1) env var ou (2) ficheiro de configuração."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text())
        return s.get("claude_api_key", "").strip() or None
    except Exception:
        return None


def guardar_chave(chave: str) -> None:
    """Guarda a chave API no ficheiro de configuração."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        s = {}
    s["claude_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


# ── tradução com streaming ────────────────────────────────────────────────────

def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str = MODELO_DEFAULT,
                    api_key: str | None = None) -> Iterator[str]:
    """
    Traduz via Claude com streaming.
    Yield: fragmentos de texto à medida que chegam.
    """
    key = api_key or obter_chave()
    if not key:
        yield "[Chave API Claude não configurada. Insira-a nas definições.]"
        return

    try:
        import anthropic
    except ImportError:
        yield "[Erro: instale o SDK — pip install anthropic]"
        return

    prompt_tmpl = PROMPTS.get(lingua, PROMPTS["la"])
    prompt = prompt_tmpl.format(texto=texto.strip())

    base_url, provedor = _detetar_provedor(key)

    # Cabeçalhos extra para OpenRouter (identificação recomendada)
    kwargs_extra: dict = {}
    if base_url:
        kwargs_extra["default_headers"] = {
            "HTTP-Referer": "https://github.com/belerofonte1973/gbww",
            "X-Title":      "Busca Latina",
        }

    try:
        client = anthropic.Anthropic(
            api_key=key,
            **({"base_url": base_url} if base_url else {}),
            **kwargs_extra,
        )
        with client.messages.stream(
            model=modelo,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except anthropic.AuthenticationError:
        yield f"[Chave {provedor} inválida. Verifique as definições.]"
    except anthropic.RateLimitError:
        yield "[Limite de taxa excedido. Aguarde e tente novamente.]"
    except anthropic.APIConnectionError:
        yield f"[Sem ligação à API {provedor}. Verifique a internet.]"
    except Exception as e:
        yield f"[Erro {provedor}: {e}]"


def traduzir(texto: str,
             lingua: str = "la",
             modelo: str = MODELO_DEFAULT,
             api_key: str | None = None) -> str:
    """Traduz (bloqueante) e devolve a tradução completa."""
    return "".join(traduzir_stream(texto, lingua, modelo, api_key))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Tradução latim/grego → PT via Claude")
    ap.add_argument("texto", nargs="*")
    ap.add_argument("--lingua", "-l", default="la", choices=["la", "grc"])
    ap.add_argument("--modelo", "-m", default=MODELO_DEFAULT)
    ap.add_argument("--comentario", "-c", action="store_true")
    ap.add_argument("--chave", help="Chave API (sobrepõe env/config)")
    ap.add_argument("--guardar-chave", metavar="KEY",
                    help="Guarda a chave API no config e sai")
    args = ap.parse_args()

    if args.guardar_chave:
        guardar_chave(args.guardar_chave)
        print("Chave guardada em", SETTINGS_FILE)
        sys.exit(0)

    if not args.texto:
        ap.print_help()
        sys.exit(1)

    lingua = "comentario" if args.comentario else args.lingua
    texto  = " ".join(args.texto)
    print(f"[Claude {args.modelo}]\n")
    for frag in traduzir_stream(texto, lingua, args.modelo, args.chave):
        print(frag, end="", flush=True)
    print()
