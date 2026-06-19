#!/usr/bin/env python3
"""
openai_lat.py — Tradução de latim/grego/hebraico para português via API OpenAI

Chave em: platform.openai.com/api-keys
"""

import os
import json
import sys
from pathlib import Path
from typing import Iterator

import requests

if sys.platform == "win32":
    _cfg_dir = Path(os.environ.get("APPDATA", Path.home())) / "BuscaLatina"
else:
    _cfg_dir = Path.home() / ".config" / "busca_latina"

SETTINGS_FILE = _cfg_dir / "settings.json"

MODELOS_OPENAI = [
    ("gpt-4o",      "GPT-4o      — máxima qualidade"),
    ("gpt-4o-mini", "GPT-4o mini — rápido, económico"),
    ("gpt-4-turbo", "GPT-4 Turbo — alternativa robusta"),
]
MODELO_DEFAULT = "gpt-4o"

_URL = "https://api.openai.com/v1/chat/completions"

_LINGUA_NOME = {"la": "latim clássico", "grc": "grego antigo", "hbo": "hebraico bíblico"}

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
    "hbo": (
        "És um especialista em hebraico bíblico e língua portuguesa. "
        "Traduz o seguinte texto do hebraico para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto hebraico:\n{texto}\n\nTradução:"
    ),
}


def obter_chave() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return s.get("openai_api_key", "").strip()
    except Exception:
        return ""


def guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s["openai_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False),
                             encoding="utf-8")


def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str = MODELO_DEFAULT,
                    api_key: str | None = None,
                    should_stop=None) -> Iterator[str]:
    chave = api_key or obter_chave()
    if not chave:
        yield "[Chave OpenAI não configurada. Obtenha em platform.openai.com/api-keys]"
        return

    prompt = PROMPTS.get(lingua, PROMPTS["la"]).format(texto=texto.strip())
    headers = {"Authorization": f"Bearer {chave}",
               "Content-Type": "application/json"}
    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 2048,
    }

    try:
        with requests.post(_URL, json=payload, headers=headers,
                           stream=True, timeout=(10, None)) as resp:
            if resp.status_code == 401:
                yield "[Chave OpenAI inválida ou expirada.]"; return
            if resp.status_code == 429:
                yield "[Limite de taxa OpenAI. Aguarde alguns segundos.]"; return
            if resp.status_code == 402:
                yield "[Saldo OpenAI insuficiente. Verifique platform.openai.com]"; return
            resp.raise_for_status()

            for line in resp.iter_lines():
                if should_stop and should_stop():
                    break
                if not line:
                    continue
                raw = line.decode("utf-8") if isinstance(line, bytes) else line
                if not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    pass

    except requests.exceptions.ConnectionError:
        yield "[Sem ligação à API OpenAI. Verifique a internet.]"
    except Exception as e:
        yield f"[Erro OpenAI: {e}]"
