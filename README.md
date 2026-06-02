# Busca Latina

Ferramenta de busca em corpora latinos e gregos com interface gráfica (PyQt5), tradução por IA e análise morfológica.

![Busca Latina](https://img.shields.io/badge/Python-3.10%2B-blue) ![License](https://img.shields.io/badge/licença-MIT-green)

## Funcionalidades

- **Busca** em dois corpora offline:
  - Latin Library (~2100 textos)
  - Perseus/CLTK (~173 textos)
- **Sintaxe de busca** flexível: palavra exata, prefixo (`amor-`), sufixo (`-que`), infixo (`-amor-`), expressão entre aspas, regex pura
- **Tradução latim/grego → português** por três motores de IA:
  - 🌟 **Gemini** (Google) — Flash 2.0/2.5, Pro 2.5 — chave gratuita em [aistudio.google.com](https://aistudio.google.com)
  - ✨ **Claude** (Anthropic / OpenRouter) — Haiku, Sonnet, Opus
  - 🦙 **Ollama** — modelos locais (Llama, Mistral, etc.)
- **Análise morfológica** via Whitaker's Words (online)
- **Dicionários** Lewis & Short (LS) e Liddell-Scott-Jones (LSJ) para grego
- **Pronúncia** do latim clássico (TTS, se disponível)
- **Comentário filológico** (estrutura gramatical, vocabulário, contexto literário)

## Requisitos

```bash
pip install PyQt5 requests
```

Os corpora são instalados via [CLTK](https://cltk.org):

```python
from cltk.data.fetch import FetchCorpus
FetchCorpus(language="lat").import_corpus("lat_text_latin_library")
FetchCorpus(language="lat").import_corpus("lat_text_perseus")
```

## Utilização

### Interface gráfica

```bash
python3 busca_latina_gui.py
```

### Linha de comandos

```bash
# Busca simples
python3 busca_latina.py amor

# Todas as formas de "amor" (prefixo)
python3 busca_latina.py amor- -i

# Palavras terminadas em -que
python3 busca_latina.py -que -i -m 20

# Expressão exata
python3 busca_latina.py "carpe diem" -i
```

### Tradução via Gemini (CLI)

```bash
# Configurar chave
python3 gemini_lat.py --guardar-chave "AIza..."

# Traduzir
python3 gemini_lat.py "Gallia est omnis divisa in partes tres"
python3 gemini_lat.py "μῆνιν ἄειδε θεά" --lingua grc
python3 gemini_lat.py "arma virumque cano" --comentario
```

### Tradução via Claude (CLI)

```bash
python3 claude_lat.py --guardar-chave "sk-ant-..."
python3 claude_lat.py "Gallia est omnis divisa in partes tres"
```

### Tradução via Ollama (local, CLI)

```bash
ollama pull llama3.2
python3 ollama_lat.py "Gallia est omnis divisa in partes tres"
```

## Configuração das chaves de API

As chaves são guardadas em `~/.config/busca_latina/settings.json` e podem ser configuradas pelo botão 🔑 na GUI ou via CLI (`--guardar-chave`). Também é possível usar variáveis de ambiente:

```bash
export GEMINI_API_KEY="AIza..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Módulos

| Ficheiro | Função |
|---|---|
| `busca_latina_gui.py` | Interface gráfica PyQt5 |
| `busca_latina.py` | Motor de busca nos corpora |
| `gemini_lat.py` | Tradução via API Gemini (Google) |
| `claude_lat.py` | Tradução via Claude / OpenRouter |
| `ollama_lat.py` | Tradução via Ollama (local) |
| `whitakers_words.py` | Análise morfológica (Whitaker's Words) |
| `pronunciar_latim.py` | Pronúncia TTS do latim clássico |
| `traduzir_lat_grc.py` | Tradutor offline (dicionário) |
