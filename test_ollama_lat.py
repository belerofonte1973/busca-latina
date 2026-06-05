"""Tests for ollama_lat.py — all HTTP calls are mocked."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

import ollama_lat as ol


# ── helpers ───────────────────────────────────────────────────────────────────

def _tags_response(names: list[str]) -> MagicMock:
    """Build a mock GET /api/tags response."""
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json.return_value = {"models": [{"name": n} for n in names]}
    return r


def _stream_lines(chunks: list[str], done_index: int | None = None) -> list[bytes]:
    """Build a list of NDJSON lines as Ollama would stream them."""
    lines = []
    for i, text in enumerate(chunks):
        done = (done_index is not None and i == done_index) or i == len(chunks) - 1
        lines.append(json.dumps({"response": text, "done": done}).encode())
    return lines


# ── listar_modelos ─────────────────────────────────────────────────────────────

class TestListarModelos:
    def test_returns_model_names(self):
        with patch("ollama_lat.requests.get", return_value=_tags_response(["llama3.1:latest", "phi3:latest"])):
            assert ol.listar_modelos() == ["llama3.1:latest", "phi3:latest"]

    def test_empty_when_no_models(self):
        with patch("ollama_lat.requests.get", return_value=_tags_response([])):
            assert ol.listar_modelos() == []

    def test_empty_on_connection_error(self):
        with patch("ollama_lat.requests.get", side_effect=requests.exceptions.ConnectionError):
            assert ol.listar_modelos() == []

    def test_empty_on_generic_exception(self):
        with patch("ollama_lat.requests.get", side_effect=RuntimeError("boom")):
            assert ol.listar_modelos() == []

    def test_raises_on_http_error(self):
        r = MagicMock()
        r.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("ollama_lat.requests.get", return_value=r):
            assert ol.listar_modelos() == []


# ── modelo_disponivel ──────────────────────────────────────────────────────────

class TestModeloDisponivel:
    MODELOS = ["llama3.1:latest", "phi3:latest", "gemma2:9b"]

    def _patch(self):
        return patch("ollama_lat.listar_modelos", return_value=self.MODELOS)

    def test_exact_match(self):
        with self._patch():
            assert ol.modelo_disponivel("llama3.1:latest") == "llama3.1:latest"

    def test_prefix_match_with_colon(self):
        with self._patch():
            assert ol.modelo_disponivel("llama3.1") == "llama3.1:latest"

    def test_prefix_match_without_colon(self):
        with self._patch():
            assert ol.modelo_disponivel("phi") == "phi3:latest"

    def test_not_found_returns_none(self):
        with self._patch():
            assert ol.modelo_disponivel("mistral") is None

    def test_empty_list_returns_none(self):
        with patch("ollama_lat.listar_modelos", return_value=[]):
            assert ol.modelo_disponivel("llama3.1") is None


# ── _melhor_modelo ─────────────────────────────────────────────────────────────

class TestMelhorModelo:
    def test_prefers_best_recommended(self):
        # gemma2 is the best in the list; it should be chosen over phi3/llama3.1
        with patch("ollama_lat.listar_modelos", return_value=["phi3:latest", "gemma2:9b"]):
            assert ol.modelo_disponivel("gemma2") == "gemma2:9b"
            result = ol._melhor_modelo()
            assert result == "gemma2:9b"

    def test_falls_back_to_lower_ranked(self):
        with patch("ollama_lat.listar_modelos", return_value=["phi3:latest"]):
            result = ol._melhor_modelo()
            assert result == "phi3:latest"

    def test_falls_back_to_first_available(self):
        # nothing from the recommended list installed
        with patch("ollama_lat.listar_modelos", return_value=["mistral:latest"]):
            result = ol._melhor_modelo()
            assert result == "mistral:latest"

    def test_returns_none_when_no_models(self):
        with patch("ollama_lat.listar_modelos", return_value=[]):
            assert ol._melhor_modelo() is None


# ── precarregar_modelo ─────────────────────────────────────────────────────────

class TestPrecarregarModelo:
    def test_success(self):
        r = MagicMock()
        r.status_code = 200
        with patch("ollama_lat.requests.post", return_value=r):
            ok, nome = ol.precarregar_modelo("llama3.1:latest")
        assert ok is True
        assert nome == "llama3.1:latest"

    def test_failure_non_200(self):
        r = MagicMock()
        r.status_code = 500
        with patch("ollama_lat.requests.post", return_value=r):
            ok, nome = ol.precarregar_modelo("llama3.1:latest")
        assert ok is False

    def test_connection_error(self):
        with patch("ollama_lat.requests.post", side_effect=requests.exceptions.ConnectionError):
            ok, nome = ol.precarregar_modelo("llama3.1:latest")
        assert ok is False
        assert nome == "llama3.1:latest"

    def test_no_model_available(self):
        with patch("ollama_lat.listar_modelos", return_value=[]):
            ok, nome = ol.precarregar_modelo(None)
        assert ok is False
        assert nome == ""

    def test_auto_selects_best_model(self):
        r = MagicMock()
        r.status_code = 200
        with patch("ollama_lat.requests.post", return_value=r), \
             patch("ollama_lat.listar_modelos", return_value=["phi3:latest"]):
            ok, nome = ol.precarregar_modelo(None)
        assert ok is True
        assert nome == "phi3:latest"


# ── traduzir_stream ────────────────────────────────────────────────────────────

class TestTraduzirStream:
    def _mock_stream(self, chunks: list[str], status: int = 200):
        r = MagicMock()
        r.status_code = status
        r.raise_for_status = MagicMock()
        r.iter_lines.return_value = _stream_lines(chunks)
        return r

    def test_yields_translation_chunks(self):
        chunks = ["Gália ", "é toda ", "dividida."]
        with patch("ollama_lat.requests.post", return_value=self._mock_stream(chunks)), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            result = list(ol.traduzir_stream("Gallia est omnis divisa", modelo="llama3.1:latest"))
        assert result == chunks

    def test_no_model_yields_error_message(self):
        with patch("ollama_lat.listar_modelos", return_value=[]):
            result = list(ol.traduzir_stream("Gallia est"))
        assert len(result) == 1
        assert "ollama pull" in result[0]

    def test_connection_error_yields_message(self):
        with patch("ollama_lat.requests.post", side_effect=requests.exceptions.ConnectionError), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            result = list(ol.traduzir_stream("Gallia est", modelo="llama3.1:latest"))
        assert any("ollama serve" in r for r in result)

    def test_generic_error_yields_message(self):
        with patch("ollama_lat.requests.post", side_effect=RuntimeError("boom")), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            result = list(ol.traduzir_stream("Gallia est", modelo="llama3.1:latest"))
        assert any("Erro" in r for r in result)

    def test_incomplete_stream_yields_warning(self):
        # Build a stream that never sets done=True
        lines = [json.dumps({"response": "partial", "done": False}).encode()]
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.iter_lines.return_value = lines
        with patch("ollama_lat.requests.post", return_value=r), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            result = list(ol.traduzir_stream("Gallia", modelo="llama3.1:latest"))
        full = "".join(result)
        assert "interrompida" in full or "partial" in full

    def test_greek_uses_grc_prompt(self):
        captured = {}
        def fake_post(url, json=None, **kw):
            captured["payload"] = json
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_lines.return_value = _stream_lines(["ok"])
            return r

        with patch("ollama_lat.requests.post", side_effect=fake_post), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            list(ol.traduzir_stream("μῆνιν", lingua="grc", modelo="llama3.1:latest"))

        assert "grego antigo" in captured["payload"]["prompt"]

    def test_unknown_lingua_defaults_to_latin_prompt(self):
        captured = {}
        def fake_post(url, json=None, **kw):
            captured["payload"] = json
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_lines.return_value = _stream_lines(["ok"])
            return r

        with patch("ollama_lat.requests.post", side_effect=fake_post), \
             patch("ollama_lat.listar_modelos", return_value=["llama3.1:latest"]):
            list(ol.traduzir_stream("Arma", lingua="xx", modelo="llama3.1:latest"))

        assert "latim" in captured["payload"]["prompt"]

    def test_stream_true_in_request(self):
        captured = {}
        def fake_post(url, json=None, **kw):
            captured["payload"] = json
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_lines.return_value = _stream_lines(["ok"])
            return r

        with patch("ollama_lat.requests.post", side_effect=fake_post), \
             patch("ollama_lat.listar_modelos", return_value=["phi3:latest"]):
            list(ol.traduzir_stream("Arma", modelo="phi3:latest"))

        assert captured["payload"]["stream"] is True


# ── traduzir ──────────────────────────────────────────────────────────────────

class TestTraduzir:
    def test_joins_chunks(self):
        chunks = ["Gália ", "é toda ", "dividida."]
        with patch("ollama_lat.traduzir_stream", return_value=iter(chunks)):
            assert ol.traduzir("Gallia est") == "Gália é toda dividida."

    def test_passes_lingua_and_modelo(self):
        with patch("ollama_lat.traduzir_stream", return_value=iter(["ok"])) as mock_stream:
            ol.traduzir("txt", lingua="grc", modelo="gemma2")
        mock_stream.assert_called_once_with("txt", "grc", "gemma2")


# ── comentario ────────────────────────────────────────────────────────────────

class TestComentario:
    def test_joins_chunks(self):
        chunks = ["Arma virumque: ", "acusativo directo."]
        with patch("ollama_lat.traduzir_stream", return_value=iter(chunks)):
            assert ol.comentario("Arma virumque cano") == "Arma virumque: acusativo directo."

    def test_uses_comentario_lingua(self):
        with patch("ollama_lat.traduzir_stream", return_value=iter(["ok"])) as mock_stream:
            ol.comentario("Arma", modelo="phi3")
        mock_stream.assert_called_once_with("Arma", "comentario", "phi3")

    def test_comentario_prompt_in_request(self):
        captured = {}
        def fake_post(url, json=None, **kw):
            captured["payload"] = json
            r = MagicMock()
            r.raise_for_status = MagicMock()
            r.iter_lines.return_value = _stream_lines(["ok"])
            return r

        with patch("ollama_lat.requests.post", side_effect=fake_post), \
             patch("ollama_lat.listar_modelos", return_value=["phi3:latest"]):
            ol.comentario("Arma virumque", modelo="phi3:latest")

        assert "filológico" in captured["payload"]["prompt"]
