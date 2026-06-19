#!/usr/bin/env python3
"""
deepl_lat.py — Tradução de latim/grego/hebraico para português via API DeepL

Chave gratuita em: deepl.com/pro-api  (500 000 chars/mês)
Chaves gratuitas terminam em ':fx'; chaves Pro não têm esse sufixo.
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

# DeepL suporta Latim nativamente; grego/hebraico usam deteção automática
_LANG_MAP = {"la": "LA", "grc": None, "hbo": None}


def _base_url(chave: str) -> str:
    return ("https://api-free.deepl.com" if chave.endswith(":fx")
            else "https://api.deepl.com")


def obter_chave() -> str:
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return s.get("deepl_api_key", "").strip()
    except Exception:
        return ""


def guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s["deepl_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False),
                             encoding="utf-8")


def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str = "",
                    api_key: str | None = None,
                    should_stop=None) -> Iterator[str]:
    chave = api_key or obter_chave()
    if not chave:
        yield "[Chave DeepL não configurada. Obtenha em deepl.com/pro-api]"
        return

    src_lang = _LANG_MAP.get(lingua)
    payload: dict = {"text": [texto.strip()], "target_lang": "PT-BR"}
    if src_lang:
        payload["source_lang"] = src_lang

    url = _base_url(chave) + "/v2/translate"
    headers = {"Authorization": f"DeepL-Auth-Key {chave}",
               "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=(10, 30))
        if resp.status_code == 403:
            yield "[Chave DeepL inválida ou expirada.]"; return
        if resp.status_code == 456:
            yield "[Quota mensal DeepL esgotada (500 000 chars/mês).]"; return
        resp.raise_for_status()
        traducao = resp.json()["translations"][0]["text"]
        yield traducao
    except requests.exceptions.ConnectionError:
        yield "[Sem ligação à API DeepL. Verifique a internet.]"
    except Exception as e:
        yield f"[Erro DeepL: {e}]"
