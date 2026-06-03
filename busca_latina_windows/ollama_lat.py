#!/usr/bin/env python3
"""
ollama_lat.py — Tradução de latim/grego para português com IA local (Ollama)
Windows 11 ARM / Snapdragon X

Requer:
  • Ollama para Windows instalado e a correr:  ollama serve
  • Um modelo descarregado, ex:  ollama pull llama3.2

Ollama para Windows: https://ollama.com/download/windows
"""

import json
import sys
from typing import Iterator

import requests

OLLAMA_URL = "http://localhost:11434"

NUM_CTX    = 2048   # KV-cache limitado a ~24 MB (vs ~1,5 GB do padrão)
KEEP_ALIVE = "5m"   # descarregar modelo da RAM após 5 min de inatividade

MODELOS_RECOMENDADOS = [
    ("phi3",      "Phi-3 Mini 3.8B  — rápido, leve"),
    ("llama3.2",  "Llama 3.2 3B     — bom equilíbrio"),
    ("mistral",   "Mistral 7B       — boa qualidade"),
    ("llama3.1",  "Llama 3.1 8B     — excelente qualidade"),
    ("gemma2",    "Gemma 2 9B       — muito boa qualidade"),
]

PROMPTS = {
    "la": (
        "És um especialista em latim clássico e língua portuguesa europeia. "
        "Traduz o seguinte texto do latim para português de Portugal, "
        "de forma fluente e fiel ao original. "
        "Regras obrigatórias: "
        "(1) usa apenas palavras que existem em português; "
        "(2) mantém concordância gramatical rigorosa em género e número; "
        "(3) fornece apenas a tradução, sem comentários, notas ou explicações.\n\n"
        "Texto latino:\n{texto}\n\nTradução:"
    ),
    "grc": (
        "És um especialista em grego antigo (clássico e helenístico) e língua portuguesa europeia. "
        "Traduz o seguinte texto do grego antigo para português de Portugal, "
        "de forma fluente e fiel ao original. "
        "Regras obrigatórias: "
        "(1) usa apenas palavras que existem em português; "
        "(2) mantém concordância gramatical rigorosa em género e número; "
        "(3) fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto grego:\n{texto}\n\nTradução:"
    ),
    "comentario": (
        "És um professor de latim clássico. "
        "Faz um comentário filológico breve (3-5 frases) do seguinte trecho latino, "
        "em português de Portugal, cobrindo: estrutura gramatical, vocabulário notável e contexto literário. "
        "Usa apenas palavras que existem em português; não uses termos inventados.\n\n"
        "Trecho:\n{texto}\n\nComentário:"
    ),
}


# ── API Ollama ────────────────────────────────────────────────────────────────

def listar_modelos() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def modelo_disponivel(nome: str) -> str | None:
    for m in listar_modelos():
        if m == nome or m.startswith(nome + ":") or m.startswith(nome):
            return m
    return None


def _melhor_modelo() -> str | None:
    for nome, _ in reversed(MODELOS_RECOMENDADOS):
        m = modelo_disponivel(nome)
        if m:
            return m
    mods = listar_modelos()
    return mods[0] if mods else None


def precarregar_modelo(modelo: str | None = None) -> tuple[bool, str]:
    modelo = modelo or _melhor_modelo()
    if not modelo:
        return False, ""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "keep_alive": KEEP_ALIVE,
                  "options": {"num_ctx": NUM_CTX}},
            timeout=(15, 300),
        )
        return r.status_code == 200, modelo
    except requests.exceptions.ConnectionError:
        return False, modelo
    except Exception:
        return False, modelo


def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str | None = None) -> Iterator[str]:
    modelo = modelo or _melhor_modelo()
    if not modelo:
        yield "[Nenhum modelo Ollama disponível — execute: ollama pull llama3.2]"
        return

    prompt = PROMPTS.get(lingua, PROMPTS["la"]).format(texto=texto.strip())

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "prompt": prompt, "stream": True,
                  "keep_alive": KEEP_ALIVE,
                  "options": {"num_ctx": NUM_CTX}},
            stream=True,
            timeout=(15, None),
        )
        resp.raise_for_status()
        concluido = False
        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    concluido = True
                    break
        if not concluido:
            yield (
                "\n\n⚠ [Tradução interrompida — stream fechado sem sinal de conclusão.\n"
                "Possível causa: memória insuficiente. Tente um texto mais curto.]"
            )
    except requests.exceptions.ConnectionError:
        yield "\n[Ollama não está a correr — abra o Ollama e execute: ollama serve]"
    except Exception as e:
        yield f"\n[Erro: {e}]"


def traduzir(texto: str,
             lingua: str = "la",
             modelo: str | None = None) -> str:
    return "".join(traduzir_stream(texto, lingua, modelo))


def comentario(texto: str, modelo: str | None = None) -> str:
    return "".join(traduzir_stream(texto, "comentario", modelo))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Tradução latim/grego → PT com Ollama")
    ap.add_argument("texto", nargs="*")
    ap.add_argument("--lingua",    "-l", default="la", choices=["la", "grc"])
    ap.add_argument("--modelo",    "-m", default=None)
    ap.add_argument("--comentario","-c", action="store_true")
    ap.add_argument("--listar",    action="store_true")
    args = ap.parse_args()

    if args.listar:
        mods = listar_modelos()
        if not mods:
            print("Ollama não responde ou sem modelos instalados.")
            print("Instale Ollama: https://ollama.com/download/windows")
            print("Depois execute: ollama pull llama3.2")
        else:
            print("Modelos instalados:")
            for m in mods:
                print(f"  {m}")
        sys.exit(0)

    if not args.texto:
        ap.print_help()
        sys.exit(1)

    texto = " ".join(args.texto)
    print(f"[modelo: {args.modelo or _melhor_modelo() or '?'}]\n")

    lingua = "comentario" if args.comentario else args.lingua
    for chunk in traduzir_stream(texto, lingua, args.modelo):
        print(chunk, end="", flush=True)
    print()
