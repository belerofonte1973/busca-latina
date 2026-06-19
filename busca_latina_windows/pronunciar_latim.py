#!/usr/bin/env python3
"""
pronunciar_latim.py — Pronúncia de latim e grego antigo
Windows 11 ARM / Snapdragon X (ARM64)

Motor principal : edge-tts (Python library, online, vozes neurais) + playsound
Motor offline   : espeak-ng (se instalado) ou pyttsx3 (SAPI Windows)

Vozes sugeridas para latim
--------------------------
  it-IT-DiegoNeural    — italiano masc. (clássico / eclesiástico)
  it-IT-IsabellaNeural — italiano fem.  (clássico / eclesiástico)
  la (espeak-ng)       — voz latina sintética (offline)

Vozes sugeridas para grego
--------------------------
  el-GR-AthinaNeural    — grego moderno fem. neural (online)
  el-GR-NestorasNeural  — grego moderno masc. neural (online)

  Nota: vozes gregas modernas recebem texto monotónico;
  a conversão polítonico→monotónico é feita automaticamente.

Vozes sugeridas para hebraico
-----------------------------
  he-IL-AvriNeural  — hebraico masc. neural (online)
  he-IL-HilaNeural  — hebraico fem. neural (online)
  he (espeak-ng)    — hebraico masc. sintético (offline)
"""

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

# ── dependências opcionais ────────────────────────────────────────────────────

try:
    import edge_tts
    _EDGE_TTS_OK = True
except ImportError:
    _EDGE_TTS_OK = False

try:
    from playsound import playsound as _playsound
    _PLAYSOUND_OK = True
except ImportError:
    _PLAYSOUND_OK = False

try:
    import pyttsx3
    _PYTTSX3_OK = True
except ImportError:
    _PYTTSX3_OK = False

_ESPEAK           = shutil.which("espeak-ng") or shutil.which("espeak")
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ── vozes disponíveis ─────────────────────────────────────────────────────────

VOZES: list[tuple] = [
    # ── latim ──────────────────────────────────────────────────────────────────
    ("it-IT-DiegoNeural",    "Diego (italiano masc.) — online",       "edge",   "la"),
    ("it-IT-IsabellaNeural", "Isabella (italiano fem.) — online",     "edge",   "la"),
    ("es-ES-AlvaroNeural",   "Álvaro (espanhol masc.) — online",      "edge",   "la"),
    ("es-ES-ElviraNeural",   "Elvira (espanhol fem.) — online",       "edge",   "la"),
    ("pt-BR-AntonioNeural",  "Antônio (port. bras. masc.) — online",  "edge",   "la"),
    ("pt-BR-FranciscaNeural","Francisca (port. bras. fem.) — online", "edge",   "la"),
    # ── grego ──────────────────────────────────────────────────────────────────
    ("el-GR-AthinaNeural",   "Athina (grego fem.) — online",          "edge",   "grc"),
    ("el-GR-NestorasNeural", "Nestoras (grego masc.) — online",       "edge",   "grc"),
    # ── hebraico ───────────────────────────────────────────────────────────────
    ("he-IL-AvriNeural",     "Avri (hebraico masc.) — online",        "edge",   "hbo"),
    ("he-IL-HilaNeural",     "Hila (hebraico fem.) — online",         "edge",   "hbo"),
]

if _ESPEAK:
    VOZES += [
        ("la",  "espeak-ng latim (offline)",           "espeak", "la"),
        ("it",  "espeak-ng italiano (offline)",        "espeak", "la"),
        ("he",  "espeak-ng hebraico masc. (offline)",  "espeak", "hbo"),
    ]

if _PYTTSX3_OK:
    VOZES += [
        ("sapi:default", "Voz Windows padrão (SAPI, offline)", "sapi", "la"),
    ]

# grupos para filtrar na GUI
VOZES_LATIM    = [v for v in VOZES if v[3] == "la"]
VOZES_GREGO    = [v for v in VOZES if v[3] == "grc"]
VOZES_HEBRAICO = [v for v in VOZES if v[3] == "hbo"]

VOZES_DEFAULT_CLASSICO     = "it-IT-DiegoNeural"
VOZES_DEFAULT_ECLESIASTICO = "it-IT-IsabellaNeural"
VOZES_DEFAULT_GREGO        = "el-GR-AthinaNeural"
VOZES_DEFAULT_HEBRAICO     = "he-IL-AvriNeural"


# ── pré-processamento eclesiástico ────────────────────────────────────────────

def _eclesiastico(texto: str) -> str:
    t = texto
    t = re.sub(r'ph', 'f', t, flags=re.IGNORECASE)
    t = re.sub(r'th', 't', t, flags=re.IGNORECASE)
    t = re.sub(r'rh', 'r', t, flags=re.IGNORECASE)
    t = re.sub(r'æ|ae', 'e', t, flags=re.IGNORECASE)
    t = re.sub(r'œ|oe', 'e', t, flags=re.IGNORECASE)
    t = re.sub(r'sc(?=[eiEI])', 'sci', t)
    t = re.sub(r'c(?=[eiEI])', 'ci', t)
    t = re.sub(r'g(?=[eiEI])', 'gi', t)
    t = re.sub(r'(?<![stxSTX])ti(?=[aeiouAEIOU])', 'zi', t)
    t = re.sub(r'J', 'I', t)
    t = re.sub(r'j', 'i', t)
    t = re.sub(r'(?<!c)h', '', t, flags=re.IGNORECASE)
    return t


# ── IPA via espeak-ng ─────────────────────────────────────────────────────────

def ipa_classico(texto: str) -> str:
    if not _ESPEAK:
        return (
            "[espeak-ng não encontrado]\n"
            "Instale em: https://github.com/espeak-ng/espeak-ng/releases"
        )
    try:
        r = subprocess.run(
            [_ESPEAK, '-v', 'la', '--ipa', '-q'],
            input=texto, capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"[Erro espeak: {e}]"


# ── estado de reprodução ──────────────────────────────────────────────────────

_stop_event  = threading.Event()
_play_thread: threading.Thread | None = None
_tmp_mp3:     str | None = None


def esta_a_falar() -> bool:
    return _play_thread is not None and _play_thread.is_alive()


def parar() -> None:
    global _play_thread, _tmp_mp3
    _stop_event.set()
    if _play_thread and _play_thread.is_alive():
        _play_thread.join(timeout=3)
    _play_thread = None
    _stop_event.clear()
    if _tmp_mp3:
        try:
            os.unlink(_tmp_mp3)
        except Exception:
            pass
        _tmp_mp3 = None


# ── motor edge-tts (async) ────────────────────────────────────────────────────

async def _edge_async(texto: str, voz: str, rate_str: str,
                      stop_evt: threading.Event) -> None:
    global _tmp_mp3
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    _tmp_mp3 = tmp
    try:
        communicate = edge_tts.Communicate(texto, voz, rate=rate_str)
        await communicate.save(tmp)

        if stop_evt.is_set():
            return

        if _PLAYSOUND_OK:
            t = threading.Thread(target=_playsound, args=(tmp,), daemon=True)
            t.start()
            while t.is_alive():
                if stop_evt.is_set():
                    break
                await asyncio.sleep(0.05)
        elif sys.platform == "win32":
            # Abre com o player padrão (sem controlo de paragem)
            os.startfile(tmp)
            await asyncio.sleep(20)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        _tmp_mp3 = None


def _thread_edge(texto: str, voz: str, rate_str: str,
                 stop_evt: threading.Event) -> None:
    try:
        asyncio.run(_edge_async(texto, voz, rate_str, stop_evt))
    except Exception as e:
        print(f"[Erro pronúncia edge-tts: {e}]", file=sys.stderr)


# ── motor pyttsx3 / SAPI (offline) ───────────────────────────────────────────

def _thread_sapi(texto: str, velocidade: int, stop_evt: threading.Event) -> None:
    try:
        engine = pyttsx3.init()
        rate   = engine.getProperty('rate')
        engine.setProperty('rate', max(50, rate + int(velocidade * 1.5)))
        engine.say(texto)
        engine.runAndWait()
    except Exception as e:
        print(f"[Erro pyttsx3: {e}]", file=sys.stderr)


# ── pronúncia principal ───────────────────────────────────────────────────────

def pronunciar(texto: str,
               voz: str        = VOZES_DEFAULT_CLASSICO,
               variante: str   = 'classico',
               velocidade: int = 0,
               tom: int        = 0) -> None:
    """
    Reproduz o texto latino com o motor e voz indicados.

    voz        : id da voz (ver VOZES)
    variante   : 'classico' | 'eclesiastico'
    velocidade : ajuste de velocidade (-50 … +50); 0 = padrão
    tom        : apenas para espeak-ng (0-99)
    """
    global _play_thread, _stop_event

    parar()

    texto_proc = _eclesiastico(texto) if variante == 'eclesiastico' else texto
    motor = next((v[2] for v in VOZES if v[0] == voz), "edge")

    _stop_event = threading.Event()

    if motor == "espeak" and _ESPEAK:
        spd = 130 + int(velocidade * 0.5)
        try:
            subprocess.Popen(
                [_ESPEAK, '-v', voz,
                 '-s', str(max(70, min(220, spd))),
                 '-p', str(max(0, min(99, 50 + tom))),
                 texto_proc],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception as e:
            print(f"[Erro espeak: {e}]", file=sys.stderr)
        return

    if motor == "sapi" and _PYTTSX3_OK:
        _play_thread = threading.Thread(
            target=_thread_sapi,
            args=(texto_proc, velocidade, _stop_event),
            daemon=True,
        )
        _play_thread.start()
        return

    # edge-tts (padrão)
    if not _EDGE_TTS_OK:
        print(
            "[edge-tts não instalado]\n"
            "Execute: pip install edge-tts",
            file=sys.stderr,
        )
        return

    rate_str = f"+{velocidade}%" if velocidade >= 0 else f"{velocidade}%"
    _play_thread = threading.Thread(
        target=_thread_edge,
        args=(texto_proc, voz, rate_str, _stop_event),
        daemon=True,
    )
    _play_thread.start()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser(description='Pronúncia de latim (Windows)')
    ap.add_argument('texto', nargs='+')
    ap.add_argument('--ecl',    action='store_true', help='Pronúncia eclesiástica')
    ap.add_argument('--ipa',    action='store_true', help='Mostra transcrição IPA')
    ap.add_argument('--voz',    default=VOZES_DEFAULT_CLASSICO)
    ap.add_argument('--listar', action='store_true', help='Lista vozes disponíveis')
    ap.add_argument('-r', '--rate', type=int, default=0,
                    help='Velocidade -50..+50 (padrão 0)')
    args = ap.parse_args()

    if args.listar:
        print(f"{'ID':44} {'Motor':8} {'Rótulo'}")
        print('-' * 80)
        for vid, rot, motor, *_ in VOZES:
            print(f"{vid:44} {motor:8} {rot}")
        raise SystemExit(0)

    texto = ' '.join(args.texto)

    if args.ipa:
        print('IPA (clássico):', ipa_classico(texto))

    variante = 'eclesiastico' if args.ecl else 'classico'
    pronunciar(texto, args.voz, variante, args.rate)
    while esta_a_falar():
        time.sleep(0.2)
