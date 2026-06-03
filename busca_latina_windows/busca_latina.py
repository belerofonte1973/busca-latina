#!/usr/bin/env python3
"""
busca_latina.py — Busca em corpus latino offline
Windows 11 ARM / Snapdragon X

Corpora disponíveis (instalar via CLTK ou copiar manualmente):
  • Latin Library  (~2100 textos em %USERPROFILE%\\cltk_data\\lat\\text\\lat_text_latin_library)
  • Perseus/CLTK   (~173 textos em  %USERPROFILE%\\cltk_data\\lat\\text\\lat_text_perseus)

Sintaxe de busca:
  amor        palavra exata e isolada
  amor-       prefixo: palavras que começam com "amor"
  -que        sufixo:  palavras que terminam em "que"
  -amor-      infixo:  palavras que contêm "amor"
  "carpe diem"  expressão
  virtut\\w+  expressão regular pura
"""

import re
import sys
import argparse
from pathlib import Path

# Forçar UTF-8 no terminal Windows (compatível com PowerShell e Windows Terminal)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _proteger_sufixo():
    """Argparse confunde termos com '-' inicial com flags. Pré-processa argv."""
    OPTIONS       = {'-h', '--help', '-i', '--ignorar', '-l', '--listar',
                     '--ll', '--perseus'}
    VALUE_OPTIONS = {'-c', '--contexto', '-m', '--max'}

    argv = sys.argv[1:]
    if '--' in argv or not argv:
        return

    result, term = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if term is None and a.startswith('-') and a not in OPTIONS and a not in VALUE_OPTIONS:
            term = a
        else:
            result.append(a)
            if a in VALUE_OPTIONS and i + 1 < len(argv):
                i += 1
                result.append(argv[i])
        i += 1

    if term is not None:
        sys.argv[1:] = result + ['--', term]

_proteger_sufixo()

LATIN_LIB = Path.home() / "cltk_data/lat/text/lat_text_latin_library"
PERSEUS    = Path.home() / "cltk_data/lat/text/lat_text_perseus"

STRIP_TAGS   = re.compile(r"<[^>]+>")
STRIP_WS     = re.compile(r"[ \t]+")
_REGEX_CHARS = re.compile(r'[.^$*+?\[\]\\|()\{\}]')


def build_pattern(term: str, ignore_case: bool = True) -> re.Pattern:
    flags = re.IGNORECASE if ignore_case else 0
    is_suffix = term.startswith("-") and len(term) > 1
    is_prefix = term.endswith("-")   and len(term) > 1
    core = term
    if is_suffix:
        core = core[1:]
    if is_prefix:
        core = core[:-1]
    if _REGEX_CHARS.search(core):
        return re.compile(term, flags)
    esc = re.escape(core)
    if is_suffix and is_prefix:
        pat = rf"\b\w*{esc}\w*\b"
    elif is_suffix:
        pat = rf"\b\w*{esc}\b"
    elif is_prefix:
        pat = rf"\b{esc}\w*\b"
    else:
        pat = rf"\b{esc}\b"
    return re.compile(pat, flags)


def read_latin_lib(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.readlines()


def read_perseus_xml(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    raw = re.sub(r"<teiHeader[^>]*>.*?</teiHeader>", " ", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    raw = STRIP_TAGS.sub(" ", raw)
    words = raw.split()
    lines, buf, length = [], [], 0
    for w in words:
        buf.append(w)
        length += len(w) + 1
        if length >= 120:
            lines.append(" ".join(buf))
            buf, length = [], 0
    if buf:
        lines.append(" ".join(buf))
    return lines


def label_ll(path: Path) -> tuple[str, str]:
    rel   = path.relative_to(LATIN_LIB)
    parts = rel.parts
    if len(parts) == 1:
        return "Latin Library", parts[0].removesuffix(".txt")
    return parts[0], "/".join(parts[1:]).removesuffix(".txt")


def label_perseus(path: Path) -> tuple[str, str]:
    rel    = path.relative_to(PERSEUS)
    parts  = rel.parts
    author = parts[0]
    work   = path.stem.removesuffix("_lat").removesuffix("_grc")
    return author, work


def first_line_title(path: Path) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                t = line.strip()
                if t:
                    return t[:80]
    except OSError:
        pass
    return ""


def search_corpus(files, pattern, ctx_size, is_xml):
    for path in sorted(files):
        lines = read_perseus_xml(path) if is_xml else read_latin_lib(path)
        for i, line in enumerate(lines):
            if pattern.search(line):
                yield path, i, lines


def format_match(path, line_idx, lines, is_xml, ctx_size):
    if is_xml:
        corpus, (author, work) = "Perseus", label_perseus(path)
    else:
        corpus, (author, work) = "Latin Library", label_ll(path)
        title = first_line_title(path)
        if title and title.lower() not in author.lower() and title.lower() not in work.lower():
            work = f"{work}  [{title}]"

    start = max(0, line_idx - ctx_size)
    end   = min(len(lines), line_idx + ctx_size + 1)

    header = f"\n{'─'*64}\n[{corpus}] {author} — {work}  (linha {line_idx + 1})"
    ctx = []
    for j in range(start, end):
        marker = ">>" if j == line_idx else "  "
        ctx.append(f"  {marker} {lines[j].rstrip()}")
    return header + "\n" + "\n".join(ctx)


def main():
    ap = argparse.ArgumentParser(
        description="Busca em corpus latino offline (Latin Library + Perseus/CLTK)",
        epilog=(
            "Exemplos:\n"
            "  %(prog)s amor\n"
            "  %(prog)s 'carpe diem' -i -m 10\n"
            "  %(prog)s 'dum spiro' -c 4 --perseus\n"
            "  %(prog)s Catilina --ll -l"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("termo",    help="Palavra / frase / expressão regular")
    ap.add_argument("-c", "--contexto", type=int, default=2, metavar="N",
                    help="Linhas de contexto (padrão: 2)")
    ap.add_argument("-i", "--ignorar",  action="store_true",
                    help="Ignorar maiúsculas/minúsculas")
    ap.add_argument("-l", "--listar",   action="store_true",
                    help="Listar apenas obras com ocorrências")
    ap.add_argument("-m", "--max",      type=int, default=0, metavar="N",
                    help="Parar após N ocorrências (0 = sem limite)")
    ap.add_argument("--ll",     action="store_true", help="Buscar só na Latin Library")
    ap.add_argument("--perseus",action="store_true", help="Buscar só no Perseus/CLTK")
    args = ap.parse_args()

    try:
        pat = build_pattern(args.termo, args.ignorar)
    except re.error as e:
        print(f"Expressão regular inválida: {e}", file=sys.stderr)
        sys.exit(1)

    do_ll      = not args.perseus
    do_perseus = not args.ll

    sources = []
    if do_ll and LATIN_LIB.exists():
        sources.append((LATIN_LIB.rglob("*.txt"), False))
    elif do_ll:
        print(f"Latin Library não encontrada em {LATIN_LIB}", file=sys.stderr)
        print("Copie os textos para essa pasta ou instale via CLTK.", file=sys.stderr)

    if do_perseus and PERSEUS.exists():
        sources.append((PERSEUS.rglob("*_lat.xml"), True))
    elif do_perseus:
        print(f"Perseus não encontrado em {PERSEUS}", file=sys.stderr)

    total        = 0
    listed_works = set()

    for files, is_xml in sources:
        for path, line_idx, lines in search_corpus(files, pat, args.contexto, is_xml):
            if args.listar:
                work_id = str(path)
                if work_id not in listed_works:
                    listed_works.add(work_id)
                    if is_xml:
                        corpus, (author, work) = "Perseus", label_perseus(path)
                    else:
                        corpus, (author, work) = "Latin Library", label_ll(path)
                    print(f"[{corpus}] {author} — {work}")
            else:
                print(format_match(path, line_idx, lines, is_xml, args.contexto))
                total += 1
                if args.max and total >= args.max:
                    print(f"\n[Parado em {args.max} resultado(s). Use -m 0 para ver todos.]")
                    sys.exit(0)

    if args.listar:
        n = len(listed_works)
        print(f"\n{n} obra(s) com ocorrências de '{args.termo}'.")
    else:
        if total == 0:
            print(f"Nenhuma ocorrência encontrada para: '{args.termo}'")
        else:
            print(f"\n{'─'*64}\nTotal: {total} ocorrência(s)  (use -m N para limitar)")


if __name__ == "__main__":
    main()
