#!/usr/bin/env python3
"""Memória de Tradução (TM) — SQLite + busca fuzzy + export TMX."""

import sqlite3
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS segmentos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lingua     TEXT NOT NULL,
    texto_src  TEXT NOT NULL,
    texto_tgt  TEXT NOT NULL,
    modelo     TEXT DEFAULT '',
    fonte      TEXT DEFAULT '',
    criado_em  TEXT DEFAULT (strftime('%Y-%m-%d %H:%M', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_lingua ON segmentos(lingua);
"""

_LINGUA_TMX = {"la": "la", "grc": "el", "hbo": "he"}
_TMX_LINGUA  = {"la": "la", "el": "grc", "he": "hbo", "iw": "hbo", "heb": "hbo"}


class MemoriaTraducao:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)
        self._con.commit()

    # ── escrita ───────────────────────────────────────────────────────────────

    def salvar(self, lingua: str, src: str, tgt: str,
               modelo: str = "", fonte: str = "") -> int:
        src, tgt = src.strip(), tgt.strip()
        if not src or not tgt:
            return -1
        row = self._con.execute(
            "SELECT id FROM segmentos WHERE lingua=? AND texto_src=?",
            (lingua, src),
        ).fetchone()
        if row:
            self._con.execute(
                "UPDATE segmentos SET texto_tgt=?, modelo=?, "
                "criado_em=strftime('%Y-%m-%d %H:%M','now') WHERE id=?",
                (tgt, modelo, row["id"]),
            )
            self._con.commit()
            return row["id"]
        cur = self._con.execute(
            "INSERT INTO segmentos (lingua,texto_src,texto_tgt,modelo,fonte) "
            "VALUES (?,?,?,?,?)",
            (lingua, src, tgt, modelo, fonte),
        )
        self._con.commit()
        return cur.lastrowid

    def apagar(self, id_: int):
        self._con.execute("DELETE FROM segmentos WHERE id=?", (id_,))
        self._con.commit()

    def apagar_todos(self, lingua: str | None = None):
        if lingua:
            self._con.execute("DELETE FROM segmentos WHERE lingua=?", (lingua,))
        else:
            self._con.execute("DELETE FROM segmentos")
        self._con.commit()

    # ── leitura ───────────────────────────────────────────────────────────────

    def contar(self, lingua: str | None = None) -> int:
        if lingua:
            return self._con.execute(
                "SELECT COUNT(*) FROM segmentos WHERE lingua=?", (lingua,)
            ).fetchone()[0]
        return self._con.execute("SELECT COUNT(*) FROM segmentos").fetchone()[0]

    def listar(self, lingua: str | None = None, limite: int = 200) -> list[dict]:
        if lingua:
            rows = self._con.execute(
                "SELECT id,lingua,texto_src,texto_tgt,modelo,criado_em "
                "FROM segmentos WHERE lingua=? ORDER BY id DESC LIMIT ?",
                (lingua, limite),
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT id,lingua,texto_src,texto_tgt,modelo,criado_em "
                "FROM segmentos ORDER BY id DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(r) for r in rows]

    def buscar(self, lingua: str, texto: str,
               limite: int = 5, limiar: float = 0.40) -> list[dict]:
        texto = texto.strip()
        if not texto:
            return []
        rows = self._con.execute(
            "SELECT id,texto_src,texto_tgt,modelo,criado_em "
            "FROM segmentos WHERE lingua=? ORDER BY id DESC LIMIT 600",
            (lingua,),
        ).fetchall()
        resultados = []
        texto_l = texto.lower()
        for r in rows:
            sim = SequenceMatcher(None, texto_l, r["texto_src"].lower()).ratio()
            if sim >= limiar:
                resultados.append({
                    "id":     r["id"],
                    "sim":    sim,
                    "src":    r["texto_src"],
                    "tgt":    r["texto_tgt"],
                    "modelo": r["modelo"] or "",
                    "data":   (r["criado_em"] or "")[:10],
                })
        resultados.sort(key=lambda x: x["sim"], reverse=True)
        return resultados[:limite]

    # ── TMX ───────────────────────────────────────────────────────────────────

    def exportar_tmx(self, path: Path) -> int:
        rows = self.listar(limite=99999)
        root = ET.Element("tmx", version="1.4")
        ET.SubElement(root, "header",
                      creationtool="Classicus", adminlang="pt-BR",
                      srclang="*all*", datatype="plaintext")
        body = ET.SubElement(root, "body")
        for r in rows:
            tu = ET.SubElement(body, "tu", tuid=str(r["id"]))
            tu.set("creationdate", r.get("criado_em", ""))
            slang = _LINGUA_TMX.get(r["lingua"], r["lingua"])
            tuv_s = ET.SubElement(tu, "tuv", attrib={"xml:lang": slang})
            ET.SubElement(tuv_s, "seg").text = r["texto_src"]
            tuv_t = ET.SubElement(tu, "tuv", attrib={"xml:lang": "pt-BR"})
            ET.SubElement(tuv_t, "seg").text = r["texto_tgt"]
        try:
            ET.indent(root, space="  ")
        except AttributeError:
            pass
        tree = ET.ElementTree(root)
        tree.write(str(path), encoding="utf-8", xml_declaration=True)
        return len(rows)

    def importar_tmx(self, path: Path) -> int:
        try:
            tree = ET.parse(str(path))
        except ET.ParseError:
            return 0
        root = tree.getroot()
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag[1:root.tag.index("}")]

        def tag(n): return f"{{{ns}}}{n}" if ns else n

        _XML_NS = "{http://www.w3.org/XML/1998/namespace}"

        def _get_lang(el) -> str:
            # xml:lang pode aparecer como '{xml-ns}lang' ou 'xml:lang' ou 'lang'
            return (el.get(f"{_XML_NS}lang")
                    or el.get("xml:lang")
                    or el.get("lang")
                    or "").lower()

        count = 0
        for tu in root.iter(tag("tu")):
            src_txt = tgt_txt = src_lang = ""
            for tuv in tu.iter(tag("tuv")):
                lang = _get_lang(tuv)
                seg  = tuv.find(tag("seg"))
                text = (seg.text or "").strip() if seg is not None else ""
                if not text:
                    continue
                if lang.startswith("pt"):
                    tgt_txt = text
                elif lang in _TMX_LINGUA:
                    src_txt  = text
                    src_lang = _TMX_LINGUA[lang]
            if src_txt and tgt_txt and src_lang:
                self.salvar(src_lang, src_txt, tgt_txt, fonte="tmx")
                count += 1
        return count
