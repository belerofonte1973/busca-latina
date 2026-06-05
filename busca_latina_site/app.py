#!/usr/bin/env python3
"""Busca Greco-Latina — servidor web (Flask)"""

import csv
import json
import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, Response, stream_with_context, jsonify

ROOT = Path(__file__).parent
sys.path.insert(0, str(Path.home()))

# ── imports opcionais ─────────────────────────────────────────────────────────

from busca_latina import (
    build_pattern, read_latin_lib, read_perseus_xml,
    label_ll, label_perseus, first_line_title,
    LATIN_LIB, PERSEUS,
)

try:
    import perseus_api as _papi
    _PERSEUS_OK = True
except ImportError:
    _PERSEUS_OK = False

try:
    import sefaria_api as _sapi
    _SEFARIA_OK = True
except ImportError:
    _SEFARIA_OK = False

try:
    import apibible_api as _abapi
    _APIBIBLE_OK = True
except ImportError:
    _APIBIBLE_OK = False

try:
    from ollama_lat import traduzir_stream as _ollama_stream, comentario as _ollama_comentario, listar_modelos
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False
    def listar_modelos(): return []

try:
    from gemini_lat import (
        traduzir_stream as _gemini_stream,
        obter_chave as gemini_obter_chave,
        guardar_chave as gemini_guardar_chave,
        MODELOS_GEMINI, MODELO_DEFAULT as GEMINI_DEFAULT,
    )
    _GEMINI_OK = True
except ImportError:
    _GEMINI_OK = False
    MODELOS_GEMINI = []
    GEMINI_DEFAULT = "gemini-2.0-flash"
    def gemini_obter_chave(): return ""
    def gemini_guardar_chave(_): pass

OGL_GREGO = Path.home() / "cltk_data/grc/text/first1kgreek"
_OGL_META: dict | None = None


def _carregar_meta_ogl() -> dict:
    global _OGL_META
    if _OGL_META is not None:
        return _OGL_META
    csv_path = OGL_GREGO / "data" / "edition_metadata.csv"
    meta = {}
    if csv_path.exists():
        try:
            with open(csv_path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh, delimiter="\t"):
                    stem = Path(row.get("Filename", "")).stem
                    meta[stem] = {
                        "author": (row.get("Author", "") or "").strip(),
                        "title":  (row.get("Title",  "") or "").strip(),
                    }
        except Exception:
            pass
    _OGL_META = meta
    return meta


def label_ogl(path: Path) -> tuple[str, str]:
    info = _carregar_meta_ogl().get(path.stem, {})
    return (info.get("author") or path.parts[-2],
            info.get("title")  or path.stem)


# ── app ────────────────────────────────────────────────────────────────────────

app = Flask(__name__)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── página principal ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        ollama_models=listar_modelos() if _OLLAMA_OK else [],
        gemini_models=MODELOS_GEMINI,
        gemini_key_set=bool(gemini_obter_chave()) if _GEMINI_OK else False,
        perseus_ok=_PERSEUS_OK,
        sefaria_ok=_SEFARIA_OK,
        apibible_ok=_APIBIBLE_OK,
        apibible_key_set=bool(_abapi.obter_chave()) if _APIBIBLE_OK else False,
    )


# ── busca SSE ─────────────────────────────────────────────────────────────────

@app.route("/api/buscar")
def api_buscar():
    q         = request.args.get("q", "").strip()
    ignore    = request.args.get("ignore", "1") == "1"
    ctx       = max(0, min(10, int(request.args.get("ctx", 2))))
    max_res   = max(0, int(request.args.get("max", 100)))
    corpus_id = int(request.args.get("corpus", 0))

    def generate():
        if not q:
            yield sse("erro", {"msg": "Termo vazio"})
            return
        try:
            pattern = build_pattern(q, ignore)
        except re.error as e:
            yield sse("erro", {"msg": f"Regex inválida: {e}"})
            return

        total    = 0
        do_ll    = corpus_id in (0, 1)
        do_perc  = corpus_id in (0, 2)
        do_ogl   = corpus_id == 3

        if do_ll and LATIN_LIB.exists():
            for path in sorted(LATIN_LIB.rglob("*.txt")):
                yield sse("status", {"msg": f"Latin Library: {path.name}…"})
                lines  = read_latin_lib(path)
                author, work = label_ll(path)
                title = first_line_title(path)
                if title and title.lower() not in work.lower():
                    work = f"{work} [{title[:50]}]"
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse("result", {
                            "corpus": "Latin Library", "author": author, "work": work,
                            "line_idx": i,
                            "lines": [lines[j].rstrip() for j in range(s, e)],
                            "match_offset": i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse("done", {"total": total, "truncated": True}); return

        if do_perc and PERSEUS.exists():
            for path in sorted(PERSEUS.rglob("*_lat.xml")):
                yield sse("status", {"msg": f"Perseus: {path.name}…"})
                lines  = read_perseus_xml(path)
                author, work = label_perseus(path)
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse("result", {
                            "corpus": "Perseus", "author": author, "work": work,
                            "line_idx": i,
                            "lines": [lines[j].rstrip() for j in range(s, e)],
                            "match_offset": i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse("done", {"total": total, "truncated": True}); return

        if do_ogl and OGL_GREGO.exists():
            ogl_files = sorted(
                p for p in OGL_GREGO.rglob("*.xml")
                if not any(s in p.stem for s in
                           ("_eng", "_intro", "textcrit", "appcrit", "index"))
            )
            for path in ogl_files:
                yield sse("status", {"msg": f"OGL: {path.name}…"})
                lines  = read_perseus_xml(path)
                author, work = label_ogl(path)
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse("result", {
                            "corpus": "Open Greek & Latin", "author": author, "work": work,
                            "line_idx": i,
                            "lines": [lines[j].rstrip() for j in range(s, e)],
                            "match_offset": i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse("done", {"total": total, "truncated": True}); return

        yield sse("done", {"total": total, "truncated": False})

    return Response(stream_with_context(generate()),
                    content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── tradução SSE ───────────────────────────────────────────────────────────────

@app.route("/api/traduzir", methods=["POST"])
def api_traduzir():
    data   = request.get_json(force=True, silent=True) or {}
    texto  = (data.get("texto") or "").strip()
    lingua = data.get("lingua", "la")
    motor  = data.get("motor", "gemini")
    modelo = data.get("modelo") or None

    def generate():
        if not texto:
            yield sse("erro", {"msg": "Texto vazio"}); return

        if motor in ("ollama", "comentario"):
            if not _OLLAMA_OK:
                yield sse("erro", {"msg": "ollama_lat.py não encontrado"}); return
            fn = _ollama_comentario if motor == "comentario" else _ollama_stream
            try:
                for frag in fn(texto, *([modelo] if motor != "comentario" else [modelo])):
                    yield sse("chunk", {"text": frag})
            except Exception as ex:
                yield sse("erro", {"msg": str(ex)})

        else:  # gemini
            if not _GEMINI_OK:
                yield sse("erro", {"msg": "gemini_lat.py não encontrado"}); return
            chave = gemini_obter_chave()
            if not chave:
                yield sse("erro", {"msg": "Chave Gemini não configurada"}); return
            mod = modelo or GEMINI_DEFAULT
            try:
                for frag in _gemini_stream(texto, lingua, mod, chave):
                    if frag.startswith("\x01retry:"):
                        yield sse("status", {"msg": frag[7:]})
                    else:
                        yield sse("chunk", {"text": frag})
            except Exception as ex:
                yield sse("erro", {"msg": str(ex)})

        yield sse("done", {})

    return Response(stream_with_context(generate()),
                    content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Gemini chave ───────────────────────────────────────────────────────────────

@app.route("/api/gemini_chave", methods=["POST"])
def api_gemini_chave():
    if not _GEMINI_OK:
        return jsonify({"ok": False, "msg": "gemini_lat.py não disponível"})
    chave = ((request.get_json(force=True, silent=True) or {}).get("chave") or "").strip()
    if not chave:
        return jsonify({"ok": False, "msg": "Chave vazia"})
    gemini_guardar_chave(chave)
    return jsonify({"ok": True})


# ── Ollama modelos ─────────────────────────────────────────────────────────────

@app.route("/api/modelos_ollama")
def api_modelos_ollama():
    return jsonify(listar_modelos() if _OLLAMA_OK else [])


# ── Perseus API ────────────────────────────────────────────────────────────────

@app.route("/api/perseus/catalogo")
def api_perseus_catalogo():
    if not _PERSEUS_OK:
        return jsonify({"erro": "perseus_api.py não disponível"})
    lingua = request.args.get("lingua", "grc")
    forcar = request.args.get("forcar", "0") == "1"
    try:
        return jsonify(_papi.obter_catalogo(lingua, forcar=forcar))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/perseus/refs")
def api_perseus_refs():
    if not _PERSEUS_OK:
        return jsonify({"erro": "perseus_api.py não disponível"})
    urn = request.args.get("urn", "")
    if not urn:
        return jsonify({"erro": "URN em falta"}), 400
    try:
        return jsonify(_papi.obter_referencias(urn, nivel=1))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/perseus/passagem")
def api_perseus_passagem():
    if not _PERSEUS_OK:
        return jsonify({"erro": "perseus_api.py não disponível"})
    urn = request.args.get("urn", "")
    if not urn:
        return jsonify({"erro": "URN em falta"}), 400
    try:
        return jsonify({"texto": _papi.obter_passagem(urn)})
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/perseus/obra")
def api_perseus_obra():
    """SSE: descarrega obra completa com progresso."""
    if not _PERSEUS_OK:
        return Response(sse("erro", {"msg": "perseus_api.py não disponível"}),
                        content_type="text/event-stream")
    urn = request.args.get("urn", "")

    def generate():
        if not urn:
            yield sse("erro", {"msg": "URN em falta"}); return
        try:
            refs  = _papi.obter_referencias(urn, nivel=1)
            total = len(refs)
            yield sse("status", {"msg": f"0/{total} secções…"})
            resultados = [None] * total
            with ThreadPoolExecutor(max_workers=5) as exe:
                futuros = {exe.submit(_papi.obter_passagem, ref): i
                           for i, ref in enumerate(refs)}
                concluidos = 0
                for fut in as_completed(futuros):
                    i = futuros[fut]
                    try:
                        resultados[i] = fut.result()
                    except Exception as ex:
                        resultados[i] = f"[Erro — {_papi.label_referencia(refs[i])}: {ex}]"
                    concluidos += 1
                    yield sse("progress", {"atual": concluidos, "total": total})
            yield sse("done", {"texto": "\n\n".join(r for r in resultados if r)})
        except Exception as ex:
            yield sse("erro", {"msg": str(ex)})

    return Response(stream_with_context(generate()),
                    content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Sefaria API ────────────────────────────────────────────────────────────────

@app.route("/api/sefaria/catalogo")
def api_sefaria_catalogo():
    if not _SEFARIA_OK:
        return jsonify({"erro": "sefaria_api.py não disponível"})
    categoria = request.args.get("categoria", "Tanakh")
    forcar    = request.args.get("forcar", "0") == "1"
    try:
        return jsonify(_sapi.obter_catalogo(categoria, forcar=forcar))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/sefaria/refs")
def api_sefaria_refs():
    if not _SEFARIA_OK:
        return jsonify({"erro": "sefaria_api.py não disponível"})
    titulo = request.args.get("titulo", "")
    if not titulo:
        return jsonify({"erro": "titulo em falta"}), 400
    try:
        return jsonify(_sapi.obter_refs(titulo))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/sefaria/passagem")
def api_sefaria_passagem():
    if not _SEFARIA_OK:
        return jsonify({"erro": "sefaria_api.py não disponível"})
    ref = request.args.get("ref", "")
    if not ref:
        return jsonify({"erro": "ref em falta"}), 400
    try:
        return jsonify(_sapi.obter_passagem(ref))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/sefaria/obra")
def api_sefaria_obra():
    """SSE: descarrega obra completa capítulo a capítulo."""
    if not _SEFARIA_OK:
        return Response(sse("erro", {"msg": "sefaria_api.py não disponível"}),
                        content_type="text/event-stream")
    titulo = request.args.get("titulo", "")

    def generate():
        if not titulo:
            yield sse("erro", {"msg": "titulo em falta"}); return
        try:
            refs  = _sapi.obter_refs(titulo)
            total = len(refs)
            yield sse("status", {"msg": f"0/{total} capítulos…"})
            resultados = [None] * total
            with ThreadPoolExecutor(max_workers=5) as exe:
                futuros = {exe.submit(_sapi.obter_passagem, ref): i
                           for i, ref in enumerate(refs)}
                concluidos = 0
                for fut in as_completed(futuros):
                    i = futuros[fut]
                    try:
                        d = fut.result()
                        resultados[i] = d["texto_heb"]
                    except Exception as ex:
                        resultados[i] = f"[Erro: {ex}]"
                    concluidos += 1
                    yield sse("progress", {"atual": concluidos, "total": total})
            yield sse("done", {"texto": "\n\n".join(r for r in resultados if r)})
        except Exception as ex:
            yield sse("erro", {"msg": str(ex)})

    return Response(stream_with_context(generate()),
                    content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── API.Bible ──────────────────────────────────────────────────────────────────

@app.route("/api/apibible/chave", methods=["GET", "POST"])
def api_apibible_chave():
    if not _APIBIBLE_OK:
        return jsonify({"ok": False, "msg": "apibible_api.py não disponível"})
    if request.method == "POST":
        chave = ((request.get_json(force=True, silent=True) or {}).get("chave") or "").strip()
        if not chave:
            return jsonify({"ok": False, "msg": "Chave vazia"})
        _abapi.guardar_chave(chave)
        return jsonify({"ok": True})
    return jsonify({"tem_chave": bool(_abapi.obter_chave())})


@app.route("/api/apibible/biblias")
def api_apibible_biblias():
    if not _APIBIBLE_OK:
        return jsonify({"erro": "apibible_api.py não disponível"})
    forcar = request.args.get("forcar", "0") == "1"
    try:
        return jsonify(_abapi.listar_biblias_heb(forcar=forcar))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/apibible/livros")
def api_apibible_livros():
    if not _APIBIBLE_OK:
        return jsonify({"erro": "apibible_api.py não disponível"})
    biblia_id = request.args.get("biblia_id", "")
    if not biblia_id:
        return jsonify({"erro": "biblia_id em falta"}), 400
    try:
        return jsonify(_abapi.listar_livros(biblia_id))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/apibible/capitulos")
def api_apibible_capitulos():
    if not _APIBIBLE_OK:
        return jsonify({"erro": "apibible_api.py não disponível"})
    biblia_id = request.args.get("biblia_id", "")
    livro_id  = request.args.get("livro_id", "")
    if not biblia_id or not livro_id:
        return jsonify({"erro": "biblia_id e livro_id obrigatórios"}), 400
    try:
        return jsonify(_abapi.listar_capitulos(biblia_id, livro_id))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


@app.route("/api/apibible/passagem")
def api_apibible_passagem():
    if not _APIBIBLE_OK:
        return jsonify({"erro": "apibible_api.py não disponível"})
    biblia_id   = request.args.get("biblia_id", "")
    passagem_id = request.args.get("passagem_id", "")
    if not biblia_id or not passagem_id:
        return jsonify({"erro": "biblia_id e passagem_id obrigatórios"}), 400
    try:
        return jsonify(_abapi.obter_passagem(biblia_id, passagem_id))
    except Exception as ex:
        return jsonify({"erro": str(ex)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
