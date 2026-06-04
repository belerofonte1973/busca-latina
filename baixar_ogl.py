#!/usr/bin/env python3
"""
baixar_ogl.py — Descarrega o corpus Open Greek and Latin (First1KGreek)
                e instala em ~/cltk_data/grc/text/first1kgreek/

Tamanho: ~917 MB (zip) · ~1.5 GB descomprimido · ~3 100 ficheiros XML
Cobre: literatura grega dos sécs. VIII a.C.–XIV d.C. (autores TLG, Stoa, etc.)

Uso:
    python3 baixar_ogl.py            # descarrega e instala
    python3 baixar_ogl.py --forcar   # re-descarrega mesmo se já instalado
    python3 baixar_ogl.py --lista    # lista obras instaladas
    python3 baixar_ogl.py --resumo   # mostra contagens por tipo de autor
"""

import sys
import csv
import zipfile
import shutil
import time
from pathlib import Path

import requests

URL_ZIP = (
    "https://codeload.github.com/OpenGreekAndLatin/First1KGreek"
    "/legacy.zip/refs/heads/master"
)
DESTINO  = Path.home() / "cltk_data" / "grc" / "text" / "first1kgreek"
ZIP_TMP  = Path.home() / ".config" / "busca_latina" / "first1kgreek_download.zip"


# ── descarga ──────────────────────────────────────────────────────────────────

def baixar():
    print(f"A descarregar corpus First1KGreek (~917 MB)…")
    print(f"  Fonte: {URL_ZIP}")
    ZIP_TMP.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(URL_ZIP, stream=True,
                        headers={"User-Agent": "BuscaLatina/2.0"},
                        timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    baixado = 0
    t0 = time.time()

    with open(ZIP_TMP, "wb") as f:
        for chunk in resp.iter_content(chunk_size=512 * 1024):
            f.write(chunk)
            baixado += len(chunk)
            elapsed = time.time() - t0 or 0.001
            mbps    = baixado / elapsed / 1e6
            mb      = baixado / 1e6
            pct     = baixado / total * 100 if total else 0
            tot_str = f"/{total/1e6:.0f}" if total else ""
            print(f"\r  {pct:5.1f}%  {mb:.0f}{tot_str} MB  {mbps:.1f} MB/s",
                  end="", flush=True)

    print(f"\n  Download completo: {baixado/1e6:.1f} MB")


def extrair():
    print(f"A extrair para {DESTINO}…")
    DESTINO.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(ZIP_TMP, "r") as zf:
        membros = zf.namelist()
        # o zip do GitHub tem um prefixo: OpenGreekAndLatin-First1KGreek-XXXXXXX/
        prefixo = membros[0].split("/")[0] + "/"
        total   = len(membros)

        for i, membro in enumerate(membros):
            if not membro.startswith(prefixo):
                continue
            rel = membro[len(prefixo):]
            if not rel:
                continue
            alvo = DESTINO / rel
            if membro.endswith("/"):
                alvo.mkdir(parents=True, exist_ok=True)
            else:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(membro) as src, open(alvo, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            if i % 300 == 0:
                print(f"\r  {i}/{total} ficheiros…", end="", flush=True)

    print(f"\r  Extracção completa ({total} entradas).          ")


# ── metadados ─────────────────────────────────────────────────────────────────

def carregar_metadata() -> dict:
    """Devolve {stem_filename: {author, title}}."""
    csv_path = DESTINO / "data" / "edition_metadata.csv"
    if not csv_path.exists():
        return {}
    meta = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                nome = Path(row.get("Filename", "")).stem
                meta[nome] = {
                    "author": row.get("Author", "").strip(),
                    "title":  row.get("Title",  "").strip(),
                }
    except Exception:
        pass
    return meta


# ── comandos ──────────────────────────────────────────────────────────────────

def cmd_lista():
    if not DESTINO.exists():
        print("Corpus não instalado. Execute: python3 baixar_ogl.py")
        return
    meta = carregar_metadata()
    xmls = sorted(DESTINO.rglob("*.xml"))
    print(f"{'Ficheiro':<45} {'Autor':<30} {'Obra'}")
    print("-" * 110)
    for p in xmls:
        stem = p.stem
        info = meta.get(stem, {})
        autor = info.get("author", "?")[:29]
        titulo = info.get("title",  "?")[:50]
        print(f"{p.name:<45} {autor:<30} {titulo}")
    print(f"\nTotal: {len(xmls)} ficheiros.")


def cmd_resumo():
    if not DESTINO.exists():
        print("Corpus não instalado.")
        return
    xmls  = list(DESTINO.rglob("*.xml"))
    tipos = {}
    for p in xmls:
        prefixo = p.name.split(".")[0][:3]
        tipos[prefixo] = tipos.get(prefixo, 0) + 1
    print(f"Total: {len(xmls)} ficheiros XML")
    for t, n in sorted(tipos.items(), key=lambda x: -x[1]):
        print(f"  {t}xxxx : {n}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if "--lista" in sys.argv:
        cmd_lista()
        return
    if "--resumo" in sys.argv:
        cmd_resumo()
        return

    forcar = "--forcar" in sys.argv

    if DESTINO.exists() and any(DESTINO.iterdir()) and not forcar:
        n = sum(1 for _ in DESTINO.rglob("*.xml"))
        print(f"✓ Corpus já instalado em {DESTINO}")
        print(f"  {n} ficheiros XML.")
        print("  Use --forcar para re-descarregar.")
        return

    baixar()
    extrair()
    ZIP_TMP.unlink(missing_ok=True)

    n = sum(1 for _ in DESTINO.rglob("*.xml"))
    print(f"\n✓ Corpus Open Greek and Latin instalado em {DESTINO}")
    print(f"  {n} ficheiros XML prontos para uso.")
    print("\nNo Busca Latina, seleccione «Open Greek & Latin» no selector de corpus.")


if __name__ == "__main__":
    main()
