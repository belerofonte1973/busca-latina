#!/usr/bin/env python3
"""
baixar_dicionario_pt.py — Descarrega e indexa o Wikcionário Português
para consulta offline de entradas latinas no Busca Latina.

Uso:
  python3 ~/baixar_dicionario_pt.py

O ficheiro comprimido (~69 MB) é guardado em:
  ~/.cache/busca_latina/ptwiktionary.xml.bz2
A base de dados SQLite final fica em:
  ~/.cache/busca_latina/wiktionary_pt.db
"""

import bz2
import re
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DUMP_URL = (
    "https://dumps.wikimedia.org/ptwiktionary/latest/"
    "ptwiktionary-latest-pages-articles.xml.bz2"
)
CACHE_DIR = Path.home() / ".cache" / "busca_latina"
DUMP_PATH = CACHE_DIR / "ptwiktionary.xml.bz2"
DB_PATH   = CACHE_DIR / "wiktionary_pt.db"

_MW_NS = "http://www.mediawiki.org/xml/Export-0.11/"


# ── parsing de wikitext ───────────────────────────────────────────────────────

def _extrair_defs_latim(wikitext: str) -> str | None:
    """Extrai definições PT da secção latina de um artigo do Wikcionário."""
    # Cabeçalho da secção latina: =={{-la-}}== ou ==Latim==
    m = re.search(
        r"==\s*(?:\{\{-la-\}\}|Latim|{{la}})\s*==",
        wikitext,
        re.IGNORECASE,
    )
    if not m:
        return None

    # Delimita a secção latina até ao próximo == de nível 2
    start = m.end()
    fim = re.search(r"\n==[^=]", wikitext[start:])
    secao = wikitext[start : start + fim.start()] if fim else wikitext[start:]

    defs = []
    for linha in secao.splitlines():
        s = linha.strip()
        # Definições: linhas que começam com # mas não #: #* #; (exemplos/notas)
        if re.match(r"^#[^:#*;]", s):
            d = s[1:].strip()
            # Remove markup wiki
            d = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", d)
            d = re.sub(r"\{\{[^}]*\}\}", "", d)
            d = re.sub(r"''+", "", d)
            d = d.strip(" ;.,")
            if len(d) > 2:
                defs.append(d)

    return "; ".join(defs) if defs else None


# ── download ──────────────────────────────────────────────────────────────────

def _baixar(url: str, destino: Path) -> None:
    print(f"A descarregar {url}")
    total_baixado = 0

    def progresso(blocos, tam_bloco, total):
        nonlocal total_baixado
        total_baixado = blocos * tam_bloco
        if total > 0:
            pct = min(100, total_baixado * 100 // total)
            mb  = total_baixado / 1_048_576
            print(f"\r  {pct}%  ({mb:.1f} MB)", end="", flush=True)

    urllib.request.urlretrieve(url, str(destino), progresso)
    print(f"\r  100%  ({destino.stat().st_size / 1_048_576:.1f} MB)")


# ── processamento XML ─────────────────────────────────────────────────────────

def _processar(dump: Path, conn: sqlite3.Connection) -> int:
    count = 0
    tag_page  = f"{{{_MW_NS}}}page"
    tag_title = f"{{{_MW_NS}}}title"
    tag_text  = f"{{{_MW_NS}}}text"
    tag_ns    = f"{{{_MW_NS}}}ns"

    with bz2.open(str(dump), "rb") as fh:
        for event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != tag_page:
                continue

            ns_elem = elem.find(tag_ns)
            if ns_elem is None or ns_elem.text != "0":
                elem.clear()
                continue

            title_elem = elem.find(tag_title)
            text_elem  = elem.find(f".//{tag_text}")
            if title_elem is None or text_elem is None:
                elem.clear()
                continue

            title   = (title_elem.text or "").strip()
            wikitext = text_elem.text or ""

            if "{{-la-}}" in wikitext or "==Latim==" in wikitext:
                defs = _extrair_defs_latim(wikitext)
                if defs:
                    conn.execute(
                        "INSERT OR REPLACE INTO entradas (palavra, definicao) VALUES (?, ?)",
                        (title, defs),
                    )
                    count += 1
                    if count % 200 == 0:
                        conn.commit()
                        print(f"\r  {count} entradas indexadas…", end="", flush=True)

            elem.clear()

    conn.commit()
    return count


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not DUMP_PATH.exists():
        _baixar(DUMP_URL, DUMP_PATH)
    else:
        print(f"Ficheiro em cache: {DUMP_PATH}  ({DUMP_PATH.stat().st_size / 1_048_576:.1f} MB)")

    print("A indexar entradas latinas…")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entradas (
            palavra   TEXT PRIMARY KEY,
            definicao TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_palavra ON entradas (palavra COLLATE NOCASE)"
    )

    n = _processar(DUMP_PATH, conn)
    conn.close()

    print(f"\n✓ {n} entradas latinas indexadas em {DB_PATH}")
    print("  Reinicie o Busca Latina para activar o botão 'Wikt.PT'.")


if __name__ == "__main__":
    main()
