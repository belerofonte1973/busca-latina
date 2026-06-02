#!/bin/bash
clear
echo "═══════════════════════════════════════════════════════════"
echo "  BUSCA LATINA  —  Latin Library + Perseus/CLTK"
echo "  Corpus: ~2300 textos latinos offline"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Uso:  python3 ~/busca_latina.py TERMO [opções]"
echo ""
echo "  Exemplos:"
echo '    python3 ~/busca_latina.py "carpe diem" -i -m 10'
echo '    python3 ~/busca_latina.py "arma virumque" -i -c 5 --perseus'
echo '    python3 ~/busca_latina.py Catilina -l --ll'
echo '    python3 ~/busca_latina.py "virtut\w+" -i'
echo ""
echo "  Opções:"
echo "    -i          ignorar maiúsculas/minúsculas"
echo "    -c N        N linhas de contexto (padrão: 2)"
echo "    -l          listar apenas obras com ocorrências"
echo "    -m N        parar após N resultados"
echo "    --ll        buscar só na Latin Library"
echo "    --perseus   buscar só no Perseus/CLTK"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo ""
exec bash
