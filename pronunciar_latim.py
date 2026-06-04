#!/usr/bin/env python3
"""
pronunciar_latim.py — Pronúncia de latim e grego antigo com múltiplos motores

Motores disponíveis
-------------------
  edge-tts   (online, gratuito, voz neural — recomendado)
  espeak-ng  (offline, voz sintética — fallback)

Vozes sugeridas para latim
--------------------------
  it-IT-DiegoNeural    — italiano masc. (clássico / eclesiástico)
  it-IT-IsabellaNeural — italiano fem.  (clássico / eclesiástico)
  es-ES-AlvaroNeural   — espanhol masc. (bom para eclesiástico)
  es-ES-ElviraNeural   — espanhol fem.  (bom para eclesiástico)
  la (espeak-ng)       — voz latina sintética (offline)

Vozes sugeridas para grego antigo
----------------------------------
  grc (espeak-ng)          — pronúncia reconstituída (offline, recomendado)
  el-GR-NestorasNeural     — grego moderno masc. neural (online)
  el-GR-AthinaNeural       — grego moderno fem. neural (online)
  el (espeak-ng)           — grego moderno sintético (offline)

  Nota: edge-tts com vozes gregas recebe texto monotónico (sem diacríticos
  antigos); espeak-ng grc aceita texto polítonico directamente.

CLI:
  python3 pronunciar_latim.py "Arma virumque cano"
  python3 pronunciar_latim.py "Gloria in excelsis" --ecl
  python3 pronunciar_latim.py "amor" --ipa
  python3 pronunciar_latim.py "Gallia est omnis" --voz it-IT-IsabellaNeural
  python3 pronunciar_latim.py "Ἄνδρα μοι ἔννεπε" --voz grc
  python3 pronunciar_latim.py "Ἄνδρα μοι ἔννεπε" --voz el-GR-NestorasNeural
"""

import re
import unicodedata
import subprocess
import signal
import os
import tempfile
import shutil
from pathlib import Path

# caminho do edge-tts (instalado pelo pipx/pip)
_EDGE_TTS = str(Path.home() / ".local/share/pipx/venvs/pip/bin/edge-tts")
_FFPLAY    = shutil.which("ffplay")
_ESPEAK    = shutil.which("espeak-ng")

# processos em curso
_proc_tts:   subprocess.Popen | None = None
_proc_audio: subprocess.Popen | None = None


# ── vozes disponíveis ─────────────────────────────────────────────────────────

VOZES = [
    # (id, rótulo, motor, grupo_lingua)
    # ── latim ──────────────────────────────────────────────────────────────────
    ("it-IT-DiegoNeural",    "Diego (italiano masc.) — online",       "edge",   "la"),
    ("it-IT-IsabellaNeural", "Isabella (italiano fem.) — online",     "edge",   "la"),
    ("es-ES-AlvaroNeural",   "Álvaro (espanhol masc.) — online",      "edge",   "la"),
    ("es-ES-ElviraNeural",   "Elvira (espanhol fem.) — online",       "edge",   "la"),
    ("pt-BR-AntonioNeural",  "Antônio (port. bras. masc.) — online",  "edge",   "la"),
    ("pt-BR-FranciscaNeural","Francisca (port. bras. fem.) — online", "edge",   "la"),
    ("la",                   "espeak-ng latim (offline)",              "espeak", "la"),
    ("it",                   "espeak-ng italiano (offline)",           "espeak", "la"),
    # ── grego ──────────────────────────────────────────────────────────────────
    ("grc",                  "espeak-ng grego antigo (offline)",      "espeak", "grc"),
    ("el-GR-NestorasNeural", "Nestoras (grego mod. masc.) — online",  "edge",   "grc"),
    ("el-GR-AthinaNeural",   "Athina (grego mod. fem.) — online",     "edge",   "grc"),
    ("el",                   "espeak-ng grego moderno (offline)",      "espeak", "grc"),
]

# grupos para filtrar na GUI
VOZES_LATIM = [v for v in VOZES if v[3] == "la"]
VOZES_GREGO = [v for v in VOZES if v[3] == "grc"]

VOZES_DEFAULT_CLASSICO     = "it-IT-DiegoNeural"
VOZES_DEFAULT_ECLESIASTICO = "it-IT-IsabellaNeural"
VOZES_DEFAULT_GREGO        = "grc"


# ── pré-processamento eclesiástico ────────────────────────────────────────────

def _eclesiastico(texto: str) -> str:
    """
    Adapta grafia latina para pronúncia eclesiástica (vaticana).
    O resultado é enviado para a voz italiana/espanhola do motor TTS.

      ph → f        ae/oe → e     sc+e/i → sci
      c+e/i → ci    g+e/i → gi    ti+V → zi
      J → I / j → i               h mudo (exceto ch)
    """
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


# ── pré-processamento grego ───────────────────────────────────────────────────

def _para_monotono(texto: str) -> str:
    """
    Converte texto grego polítonico para monotónico (sem espíritos, sem acentos
    adicionais), de modo a ser aceite por vozes de grego moderno (edge-tts).
    Usa decomposição NFD para separar diacríticos e remove todos os combining
    marks do bloco Unicode «Combining Diacritical Marks» e «Greek Extended».
    """
    norm = unicodedata.normalize('NFD', texto)
    resultado = []
    for ch in norm:
        cat = unicodedata.category(ch)
        # Remove todo o tipo de combining mark (Mn = Mark, Nonspacing; Mc, Me)
        if cat.startswith('M'):
            continue
        resultado.append(ch)
    return unicodedata.normalize('NFC', ''.join(resultado))


# ── IPA ───────────────────────────────────────────────────────────────────────

def ipa_classico(texto: str) -> str:
    """Transcrição IPA da pronúncia latina clássica (via espeak-ng)."""
    if not _ESPEAK:
        return "[espeak-ng não encontrado]"
    resultado = subprocess.run(
        [_ESPEAK, '-v', 'la', '--ipa', '-q'],
        input=texto, capture_output=True, text=True
    )
    return resultado.stdout.strip()


def ipa_grego(texto: str) -> str:
    """Transcrição IPA do grego antigo reconstituído (via espeak-ng grc)."""
    if not _ESPEAK:
        return "[espeak-ng não encontrado]"
    resultado = subprocess.run(
        [_ESPEAK, '-v', 'grc', '--ipa', '-q'],
        input=texto, capture_output=True, text=True
    )
    return resultado.stdout.strip()


# ── controlo de reprodução ────────────────────────────────────────────────────

def parar():
    """Interrompe TTS e reprodução em curso."""
    global _proc_tts, _proc_audio
    for p in (_proc_tts, _proc_audio):
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
            except Exception:
                pass
    _proc_tts   = None
    _proc_audio = None


def esta_a_falar() -> bool:
    return ((_proc_tts   and _proc_tts.poll()   is None) or
            (_proc_audio and _proc_audio.poll() is None))


# ── pronúncia principal ───────────────────────────────────────────────────────

def pronunciar(texto: str,
               voz: str        = VOZES_DEFAULT_CLASSICO,
               variante: str   = 'classico',
               velocidade: int = 0,
               tom: int        = 0) -> None:
    """
    Reproduz texto latino ou grego com o motor e voz indicados.

    Parâmetros
    ----------
    texto      : texto a pronunciar (latim ou grego polítonico)
    voz        : id da voz (ver VOZES)
    variante   : 'classico' | 'eclesiastico'  (só relevante para latim)
    velocidade : ajuste de velocidade em % relativa (-50 a +50); 0 = padrão
    tom        : apenas para espeak-ng (0-99)
    """
    global _proc_tts, _proc_audio
    parar()

    # determina o motor e grupo de língua
    voz_info  = next((v for v in VOZES if v[0] == voz), None)
    motor     = voz_info[2] if voz_info else "edge"
    grupo_ling = voz_info[3] if voz_info else "la"

    if grupo_ling == "grc":
        # Grego: espeak-ng grc aceita polítonico; edge-tts precisa de monotónico
        if motor == "edge":
            texto_proc = _para_monotono(texto)
        else:
            texto_proc = texto   # espeak-ng grc lida com polítonico directamente
    elif variante == 'eclesiastico':
        texto_proc = _eclesiastico(texto)
    else:
        texto_proc = texto

    if motor == "espeak":
        # espeak-ng: offline
        spd = 130 + int(velocidade * 0.5)
        _proc_tts = subprocess.Popen(
            [_ESPEAK, '-v', voz, '-s', str(max(70, min(220, spd))),
             '-p', str(max(0, min(99, 50 + tom))), texto_proc],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    else:
        # edge-tts: gera MP3 e reproduz com ffplay
        if not Path(_EDGE_TTS).exists():
            print(f"[Erro: edge-tts não encontrado em {_EDGE_TTS}]")
            return
        tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        tmp.close()

        # Bug: '--rate', '-30%' → argparse do edge-tts confunde '-30%' com flag.
        # Solução: passar '--rate=-30%' como argumento único (formato com '=').
        rate_str = f"+{velocidade}%" if velocidade >= 0 else f"{velocidade}%"

        cmd_edge = [_EDGE_TTS,
                    '--voice', voz,
                    f'--rate={rate_str}',       # '=' evita ambiguidade com valores negativos
                    '--text', texto_proc,
                    '--write-media', tmp.name]

        # Usar Popen (não subprocess.run) para que parar() possa matar o processo
        _proc_tts = subprocess.Popen(
            cmd_edge,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _proc_tts.wait()          # bloqueia o thread PronunciaThread até gerar o MP3
        ret_code = _proc_tts.returncode
        _proc_tts = None          # edge-tts concluiu; liberta o handle

        if ret_code == 0 and _FFPLAY:
            _proc_audio = subprocess.Popen(
                [_FFPLAY, '-nodisp', '-autoexit', tmp.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser(description='Pronúncia de latim')
    ap.add_argument('texto', nargs='+')
    ap.add_argument('--ecl',  action='store_true', help='Pronúncia eclesiástica')
    ap.add_argument('--ipa',  action='store_true', help='Mostra IPA (clássico)')
    ap.add_argument('--voz',  default=VOZES_DEFAULT_CLASSICO,
                    help=f'Voz (padrão: {VOZES_DEFAULT_CLASSICO})')
    ap.add_argument('--listar', action='store_true', help='Lista vozes disponíveis')
    ap.add_argument('-r', '--rate', type=int, default=0,
                    help='Velocidade relativa -50..+50 (padrão 0)')
    args = ap.parse_args()

    if args.listar:
        print(f"{'ID':40} {'Motor':8} {'Rótulo'}")
        print('-' * 80)
        for vid, rot, motor, *_ in VOZES:
            print(f"{vid:40} {motor:8} {rot}")
        raise SystemExit(0)

    texto = ' '.join(args.texto)
    if args.ipa:
        print('IPA (clássico):', ipa_classico(texto))

    variante = 'eclesiastico' if args.ecl else 'classico'
    pronunciar(texto, args.voz, variante, args.rate)

    # espera fim da reprodução
    import time
    while esta_a_falar():
        time.sleep(0.2)
