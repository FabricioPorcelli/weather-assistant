"""Tests del punto de entrada del CLI."""

import pytest

import app.cli as cli
from app.agent.llm import LLMError
from app.config import Settings


def test_cli_prints_answer(monkeypatch, capsys):
    async def fake_run(question, settings):
        assert question == "¿Llevo paraguas?"
        return "Sí, llevá paraguas."

    monkeypatch.setattr(cli, "_run", fake_run)

    exit_code = cli.main(["¿Llevo", "paraguas?"])

    assert exit_code == 0
    assert "Sí, llevá paraguas." in capsys.readouterr().out


def test_cli_reports_configuration_error(monkeypatch, capsys):
    async def fake_run(question, settings):
        raise ValueError("configurá LLM_BASE_URL")

    monkeypatch.setattr(cli, "_run", fake_run)

    exit_code = cli.main(["Hola"])

    assert exit_code == 2
    assert "Error de configuración" in capsys.readouterr().err


def test_cli_reports_llm_error(monkeypatch, capsys):
    async def fake_run(question, settings):
        raise LLMError("proveedor caído")

    monkeypatch.setattr(cli, "_run", fake_run)

    exit_code = cli.main(["Hola"])

    assert exit_code == 1
    assert "Error del LLM" in capsys.readouterr().err


def test_cli_requires_question():
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 2


async def test_run_requires_llm_configuration():
    settings = Settings(
        _env_file=None,
        llm_base_url="",
        llm_model="",
    )

    with pytest.raises(ValueError):
        await cli._run("Hola", settings)
