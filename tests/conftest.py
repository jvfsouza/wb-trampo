from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def html_lista() -> str:
    return (FIXTURES / "lista.html").read_text(encoding="utf-8")


@pytest.fixture
def html_detalhe() -> str:
    return (FIXTURES / "detalhe.html").read_text(encoding="utf-8")
