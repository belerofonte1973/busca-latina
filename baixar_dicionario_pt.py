#!/usr/bin/env python3
"""
baixar_dicionario_pt.py — Descarrega e indexa o Wikcionário Português
para consulta offline de entradas latinas no Busca Latina.

Uso:
  python3 ~/baixar_dicionario_pt.py

Ficheiro comprimido (~69 MB) guardado em:
  ~/.cache/busca_latina/ptwiktionary.xml.bz2
Base de dados SQLite em:
  ~/.cache/busca_latina/wiktionary_pt.db
"""

import re
import sqlite3
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DUMP_URL  = (
    "https://dumps.wikimedia.org/ptwiktionary/latest/"
    "ptwiktionary-latest-pages-articles.xml.bz2"
)
CACHE_DIR = Path.home() / ".cache" / "busca_latina"
DUMP_PATH = CACHE_DIR / "ptwiktionary.xml.bz2"
DB_PATH   = CACHE_DIR / "wiktionary_pt.db"
_MW_NS    = "http://www.mediawiki.org/xml/export-0.11/"


# ── wikitext parser ───────────────────────────────────────────────────────────

def _extrair_defs_latim(wikitext: str) -> str | None:
    """
    Extrai definições PT da secção latina de um artigo do Wikcionário.
    O pt.wiktionary usa o formato  ={{-la-}}=  (um = de cada lado).
    """
    m = re.search(r"=+\s*\{\{-la-\}\}\s*=+", wikitext)
    if not m:
        return None

    # Conteúdo desde o cabeçalho até ao próximo ={{-xx-}}= (secção de outra língua)
    # Secções internas (==Substantivo==, ===Declinação===) usam == ou ===; não terminam aqui.
    start   = m.end()
    proximo = re.search(r"\n=[^=\n]", wikitext[start:])
    secao   = wikitext[start : start + proximo.start()] if proximo else wikitext[start:]

    defs = []
    for linha in secao.splitlines():
        s = linha.strip()
        # Definições: linhas que começam com # mas não #: #* #; (exemplos/notas)
        if not re.match(r"^#[^:#*;]", s):
            continue
        d = s[1:].strip()
        # [[texto|display]] → display  ;  [[texto]] → texto
        d = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", d)
        # remove referencias de lingua tipo #Português, #{{pt}}, etc.
        d = re.sub(r"#(?:\{\{[^}]+\}\}|[A-ZÀ-ÿa-z]+)", "", d)
        # remove templates {{...}}
        d = re.sub(r"\{\{[^}]*\}\}", "", d)
        # remove marcação wiki restante
        d = re.sub(r"''+", "", d)
        d = re.sub(r"\s{2,}", " ", d).strip(" ;.,")
        if len(d) > 2:
            defs.append(d)

    return "; ".join(defs) if defs else None


# ── download ──────────────────────────────────────────────────────────────────

def _baixar(url: str, destino: Path) -> None:
    print(f"A descarregar {url}")

    def progresso(blocos, tam, total):
        if total > 0:
            pct = min(100, blocos * tam * 100 // total)
            mb  = blocos * tam / 1_048_576
            print(f"\r  {pct}%  ({mb:.1f} MB)", end="", flush=True)

    urllib.request.urlretrieve(url, str(destino), progresso)
    print(f"\r  100%  ({destino.stat().st_size / 1_048_576:.1f} MB)")


# ── processamento XML ─────────────────────────────────────────────────────────

def _processar(dump: Path, conn: sqlite3.Connection) -> int:
    tag_page  = f"{{{_MW_NS}}}page"
    tag_ns    = f"{{{_MW_NS}}}ns"
    tag_title = f"{{{_MW_NS}}}title"
    tag_text  = f"{{{_MW_NS}}}text"

    count = 0
    # bzip2 -dc via subprocess — necessário para multi-stream bz2 do Wikimedia
    proc = subprocess.Popen(["bzip2", "-dc", str(dump)], stdout=subprocess.PIPE)
    try:
        for event, elem in ET.iterparse(proc.stdout, events=("start", "end")):
            if event != "end" or elem.tag != tag_page:
                continue  # não limpar elementos filhos antes da page os ler

            ns_elem = elem.find(tag_ns)
            if ns_elem is None or ns_elem.text != "0":
                elem.clear()
                continue

            title_elem = elem.find(tag_title)
            text_elem  = elem.find(f".//{tag_text}")
            if title_elem is None or text_elem is None:
                elem.clear()
                continue

            titulo   = (title_elem.text or "").strip()
            wikitext = text_elem.text or ""

            if "{{-la-}}" in wikitext:
                defs = _extrair_defs_latim(wikitext)
                if defs:
                    conn.execute(
                        "INSERT OR REPLACE INTO entradas (palavra, definicao) VALUES (?, ?)",
                        (titulo, defs),
                    )
                    count += 1
                    if count % 200 == 0:
                        conn.commit()
                        print(f"\r  {count} entradas indexadas…", end="", flush=True)

            elem.clear()
    finally:
        proc.terminate()

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
    if n > 0:
        print("  Reinicie o Busca Latina para activar o botão 'Wikt.PT'.")
    else:
        print("  Nenhuma entrada encontrada — verifique o formato do dump.")


if __name__ == "__main__":
    main()
