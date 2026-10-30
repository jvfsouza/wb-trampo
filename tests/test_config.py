from pathlib import Path

import pytest

from wb_trampo.config import carregar
from wb_trampo.urls import parametros

RAIZ = Path(__file__).parent.parent


def _toml(tmp_path, texto):
    caminho = tmp_path / "config.toml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_config_do_projeto_carrega():
    config = carregar(RAIZ / "config.toml")
    assert config.buscas


def test_publicada_inteiro(tmp_path):
    config = carregar(_toml(tmp_path, '[[buscas]]\nsite = "linkedin"\npalavra_chave = "py"\npublicada = 3600\n'))
    assert parametros(config.buscas[0])["f_TPR"] == "r3600"


def test_erro_indica_qual_busca(tmp_path):
    texto = (
        '[[buscas]]\nsite = "linkedin"\npalavra_chave = "ok"\n\n'
        '[[buscas]]\nsite = "linkedin"\npalavra_chave = "estagio dados"\nmodalidade = ["home office"]\n'
    )
    with pytest.raises(ValueError, match=r'busca 2 \[linkedin\] \("estagio dados"\): modalidade desconhecido'):
        carregar(_toml(tmp_path, texto))


def test_campo_com_erro_de_digitacao(tmp_path):
    with pytest.raises(ValueError, match="busca 1: campo desconhecido 'palavra_chav'"):
        carregar(_toml(tmp_path, '[[buscas]]\nsite = "linkedin"\npalavra_chav = "py"\n'))


def test_limites_campo_desconhecido(tmp_path):
    with pytest.raises(ValueError, match=r"\[limites\]: campo desconhecido 'max_vagas'"):
        carregar(_toml(tmp_path, '[limites]\nmax_vagas = 5\n\n[[buscas]]\nsite = "linkedin"\npalavra_chave = "py"\n'))


def test_toml_mal_escrito(tmp_path):
    with pytest.raises(ValueError, match="erro de escrita"):
        carregar(_toml(tmp_path, '[[buscas]]\nsite = "linkedin"\npalavra_chave = "sem fechar aspas\n'))


def test_sem_buscas_ativas(tmp_path):
    with pytest.raises(ValueError, match="Nenhuma"):
        carregar(_toml(tmp_path, '# [[buscas]]\n# palavra_chave = "py"\n'))


@pytest.mark.parametrize("busca, erro", [
    ('palavra_chave = "py"\n', "falta o campo 'site'"),
    ('site = "catho"\npalavra_chave = "py"\n', "site desconhecido 'catho'. Use um de: linkedin, gupy"),
    ('site = "indeed"\npalavra_chave = "py"\n', "não é suportado: o Indeed bloqueia robôs"),
    ('site = "gupy"\npalavra_chave = "py"\nmodalidade = ["home office"]\n', r"busca 1 \[gupy\].*modalidade desconhecido"),
])
def test_erros_de_site(tmp_path, busca, erro):
    with pytest.raises(ValueError, match=erro):
        carregar(_toml(tmp_path, "[[buscas]]\n" + busca))


def test_site_aceita_maiusculas(tmp_path):
    config = carregar(_toml(tmp_path, '[[buscas]]\nsite = "Gupy"\npalavra_chave = "py"\n'))
    assert config.buscas[0].site == "gupy"


BUSCA_OK = '[[buscas]]\nsite = "gupy"\npalavra_chave = "py"\n'
URL_OK = "https://script.google.com/macros/s/AKfy-123/exec"


def test_sem_google_sheets(tmp_path):
    assert carregar(_toml(tmp_path, BUSCA_OK)).google_sheets is None


def test_google_sheets_do_arquivo_separado(tmp_path):
    (tmp_path / "google_sheets.toml").write_text(f'url_script = "{URL_OK}"\nsenha = "s3nha"\n', encoding="utf-8")
    sheets = carregar(_toml(tmp_path, BUSCA_OK)).google_sheets
    assert (sheets.url_script, sheets.senha) == (URL_OK, "s3nha")


@pytest.mark.parametrize("conteudo, erro", [
    (f'url_script = "{URL_OK}"\n', "falta o campo 'senha'"),
    (f'url_script = "{URL_OK}"\nsenha = "troque-esta-senha"\n', "escolha uma senha"),
    ('url_script = "https://docs.google.com/spreadsheets/d/x/edit"\nsenha = "s"\n', "URL do app da Web"),
    (f'url_script = "{URL_OK}"\nsenha = "s"\nplanilha = "x"\n', "campo desconhecido 'planilha'"),
])
def test_google_sheets_erros(tmp_path, conteudo, erro):
    (tmp_path / "google_sheets.toml").write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match=erro):
        carregar(_toml(tmp_path, BUSCA_OK))


def test_secao_antiga_no_config_avisa(tmp_path):
    with pytest.raises(ValueError, match="mudou para o arquivo google_sheets.toml"):
        carregar(_toml(tmp_path, BUSCA_OK + '\n[google_sheets]\nplanilha = "x"\n'))


def test_exemplo_do_projeto_e_valido_menos_a_senha():
    from wb_trampo.config import carregar_sheets

    with pytest.raises(ValueError, match="escolha uma senha"):
        carregar_sheets(RAIZ / "google_sheets.exemplo.toml")


def test_sem_filtro_sheets_envia_tudo(tmp_path):
    assert carregar(_toml(tmp_path, BUSCA_OK)).filtro_sheets.filtro_sql == ""


def test_filtro_sheets_do_arquivo_separado(tmp_path):
    (tmp_path / "filtro_sheets.toml").write_text(
        "filtro_sql = '''\ntipo_contrato = 'Estágio'\n'''\n", encoding="utf-8"
    )
    assert carregar(_toml(tmp_path, BUSCA_OK)).filtro_sheets.filtro_sql == "tipo_contrato = 'Estágio'"


@pytest.mark.parametrize("conteudo, erro", [
    ("filtro_sql = \"titulo = 'x'; DROP TABLE vagas\"\n", "não pode ter ';'"),
    ("filtro_sql = \"titulo = \"\n", "filtro_sql inválido"),
    ("filtro_sql = \"coluna_que_nao_existe = 1\"\n", "filtro_sql inválido"),
    ("filtro_sql = \"titulo = 'x'\"\nsql = 'x'\n", "campo desconhecido 'sql'"),
])
def test_filtro_sheets_erros(tmp_path, conteudo, erro):
    (tmp_path / "filtro_sheets.toml").write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match=erro):
        carregar(_toml(tmp_path, BUSCA_OK))


def test_exemplo_de_filtro_do_projeto_e_valido():
    from wb_trampo.config import carregar_filtro

    assert carregar_filtro(RAIZ / "filtro_sheets.exemplo.toml").filtro_sql == ""


def test_limites_novos(tmp_path):
    texto = (
        "[limites]\npausa_linkedin_min_s = 5\npausa_linkedin_max_s = 10\n"
        "max_requisicoes = 0\nintervalo_minimo_min = 0\n\n"
        '[[buscas]]\nsite = "gupy"\npalavra_chave = "py"\n'
    )
    lim = carregar(_toml(tmp_path, texto)).limites
    assert (lim.pausa_linkedin_min_s, lim.pausa_linkedin_max_s, lim.max_requisicoes) == (5, 10, 0)


@pytest.mark.parametrize("limites, erro", [
    ("pausa_linkedin_min_s = 20\n", "pausa_linkedin_min_s não pode ser maior"),
    ("max_requisicoes = -1\n", "max_requisicoes não pode ser negativo"),
])
def test_limites_invalidos(tmp_path, limites, erro):
    texto = f'[limites]\n{limites}\n[[buscas]]\nsite = "gupy"\npalavra_chave = "py"\n'
    with pytest.raises(ValueError, match=erro):
        carregar(_toml(tmp_path, texto))
