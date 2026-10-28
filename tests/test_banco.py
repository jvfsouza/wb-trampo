from wb_trampo.banco import Banco


def _banco() -> Banco:
    return Banco(":memory:")


def test_salva_com_url_limpa_e_sem_duplicar():
    b = _banco()
    ex = b.iniciar_execucao()
    b.salvar({"job_id": "123456", "titulo": "Dev"}, ex)
    b.salvar({"job_id": "123456", "titulo": "Outro título"}, ex)
    linhas = b.con.execute("SELECT job_id, titulo, url FROM vagas").fetchall()
    assert linhas == [("123456", "Dev", "https://www.linkedin.com/jobs/view/123456/")]


def test_upsert_preenche_campos_vazios_e_mantem_execucao_original():
    b = _banco()
    ex1 = b.iniciar_execucao()
    b.salvar({"job_id": "1", "titulo": "Dev"}, ex1)
    ex2 = b.iniciar_execucao()
    b.salvar({"job_id": "1", "titulo": "Dev", "descricao": "texto"}, ex2)
    desc, execucao = b.con.execute("SELECT descricao, execucao FROM vagas").fetchone()
    assert desc == "texto"
    assert execucao == ex1


def test_existe_e_ultima_execucao():
    b = _banco()
    assert b.ultima_execucao() is None
    ex = b.iniciar_execucao()
    assert not b.existe("9")
    b.salvar({"job_id": "9"}, ex)
    assert b.existe("9")
    assert b.ultima_execucao() == ex
    assert b.contar() == 1


def test_migra_banco_antigo_sem_coluna_site(tmp_path):
    import sqlite3

    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE execucoes (id INTEGER PRIMARY KEY AUTOINCREMENT, iniciada_em TEXT NOT NULL, terminada_em TEXT);
        CREATE TABLE vagas (job_id TEXT PRIMARY KEY, titulo TEXT, empresa TEXT, local TEXT, modalidade TEXT,
            nivel TEXT, tipo_contrato TEXT, area TEXT, publicada_em TEXT, candidatos TEXT,
            url TEXT NOT NULL UNIQUE, descricao TEXT, busca TEXT, primeiro_visto_em TEXT NOT NULL,
            visto_em TEXT NOT NULL, execucao INTEGER);
        INSERT INTO vagas (job_id, titulo, url, primeiro_visto_em, visto_em)
            VALUES ('111', 'Dev', 'https://www.linkedin.com/jobs/view/111/', 'x', 'x');
    """)
    con.commit()
    con.close()

    b = Banco(caminho)
    assert b.con.execute("SELECT job_id, titulo, site FROM vagas").fetchall() == [("111", "Dev", "linkedin")]
    Banco(caminho).fechar()  # abrir de novo não tenta migrar outra vez


def test_salva_site_e_url_de_outra_fonte():
    b = _banco()
    b.salvar({"job_id": "gupy:42", "site": "gupy", "url": "https://acme.gupy.io/job/abc"})
    assert b.con.execute("SELECT site, url FROM vagas").fetchone() == ("gupy", "https://acme.gupy.io/job/abc")
