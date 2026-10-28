# AGENTS.md — wb-trampo

Robô em Python que coleta vagas **públicas** do LinkedIn e da Gupy (sem login), guarda em SQLite e Excel e envia as vagas novas para uma planilha Google Sheets.

Este arquivo tem duas partes:
- **Parte 1 — Ler os dados:** onde estão as vagas e como consultá-las.
- **Parte 2 — Mexer no código:** como o projeto está organizado, as decisões já tomadas com o usuário e o que ficou pendente.

O uso do dia a dia (comandos, configuração, Google Sheets, problemas comuns) está no [`README.md`](README.md).

## Regras para agentes (leia antes de tudo)

- **Fale com o usuário em português**, de forma simples. Ele prefere respostas curtas e diretas.
- **Dados são só leitura.** Não edite, apague nem mova nada em `data/`, nem na planilha Google, sem o usuário pedir.
- **Nunca leia, mostre ou copie `google_sheets.toml`.** Ele tem o link e a senha do Apps Script do usuário.
- **Não rode `buscar` sem o usuário pedir.** Ele acessa o LinkedIn, pode causar bloqueio do IP (HTTP 429/999) e pode levar mais de 20 minutos por causa das pausas. Para testar coisas que acessam a internet, prefira a Gupy (é barata) e uma **cópia** do banco (`--banco caminho/copia.db`).
- **Não rode `enviar-sheets` sem o usuário pedir.** Ele escreve na planilha dele.
- **Não faça commit sem o usuário pedir.**
- **Nunca tente burlar bloqueios** (proxy, troca de IP, CAPTCHA, verificação Cloudflare, disfarce de navegador). Isso foi decidido com o usuário: se o site bloquear, o robô para.
- **Mostre vagas sempre com `titulo`, `empresa` e `url`.**
- Para regenerar o Excel a partir do banco (sem internet): `.venv\Scripts\python -m wb_trampo exportar`.

---

# Parte 1 — Ler os dados

## Onde estão os dados

| Onde | O que é |
|---|---|
| `data/vagas.db` | **Fonte da verdade.** SQLite com todas as vagas já vistas. |
| `data/vagas.xlsx` | Cópia para humanos (abas `Novas` e `Todas`). Descrição cortada em 500 caracteres. |
| `data/vagas_AAAA-MM-DD_HHMM.xlsx` | Cópias geradas quando o `vagas.xlsx` estava aberto no Excel. |
| `data/logs/wb_trampo_AAAA-MM-DD.log` | Log de cada execução (o que foi buscado, erros, bloqueios, nº de requisições). |
| Planilha Google (configurada em `google_sheets.toml`) | Uma aba por site e dia da busca (`AAAA-MM-DD Gupy`, `AAAA-MM-DD LinkedIn`) com as vagas **novas**: Título, Empresa, Site, Local, Modalidade, Contrato, Link, Publicada em (sem descrição). É uma cópia para humanos; prefira o banco. |
| `config.toml` | As buscas configuradas (site, palavra-chave, local, filtros) e os limites. |

Se `data/vagas.db` não existir, o robô ainda não foi executado.

## Schema

### Tabela `vagas` (uma linha por vaga, sem duplicatas)

| Coluna | Significado |
|---|---|
| `job_id` | Chave primária. LinkedIn: só o número (`4483215258`). Outros sites: com prefixo (`gupy:12786122`). |
| `site` | De onde veio a vaga: `linkedin` ou `gupy`. |
| `titulo`, `empresa`, `local` | Como aparecem no site. Na Gupy, `local` é `Cidade - UF`. |
| `url` | Link da vaga, sempre preenchido. LinkedIn: `https://www.linkedin.com/jobs/view/<id>/`. Gupy: `https://<empresa>.gupy.io/job/<código>`. |
| `publicada_em` | LinkedIn: só o dia (`AAAA-MM-DD`). Gupy: dia e hora local (`AAAA-MM-DD HH:MM`). Pode ser NULL. |
| `nivel`, `tipo_contrato`, `area`, `candidatos` | **LinkedIn:** vêm da página da vaga e são NULL se a busca rodou sem descrição (ex.: `Assistente`, `Pleno-sênior`, `Não aplicável`). **Gupy:** `tipo_contrato` = `Estágio`, `Efetivo`, `PJ`, `Trainee`, `Temporário`, `Aprendiz`, `Autônomo`, `Terceirizado` ou `Banco de talentos`; `nivel` = `Estágio` ou NULL; `area` e `candidatos` sempre NULL. |
| `descricao` | Descrição completa em texto puro. No LinkedIn é NULL se a busca rodou sem descrição. |
| `modalidade` | **LinkedIn:** o **filtro usado na busca** (ex.: `presencial, hibrido`), não um dado da vaga. **Gupy:** dado real da vaga (`Presencial`, `Híbrido`, `Remoto`). |
| `busca` | Palavra-chave da busca que encontrou a vaga **pela primeira vez**. |
| `primeiro_visto_em` / `visto_em` | Primeira e última vez em que a vaga apareceu (`AAAA-MM-DD HH:MM:SS`, hora local). |
| `execucao` | ID da execução em que a vaga apareceu **pela primeira vez**. |

### Tabela `execucoes` (uma linha por vez que o robô rodou)

`id`, `iniciada_em`, `terminada_em`. `terminada_em` é NULL se a execução foi interrompida no meio.

### Conceitos

- **Novas da última execução:** `execucao = (SELECT MAX(id) FROM execucoes)`.
- **Encontradas na última execução** (novas e já conhecidas): `visto_em >= iniciada_em` da última execução.
- **Vaga já vista não é reaberta.** O robô só atualiza `visto_em`. Uma vaga do LinkedIn salva sem descrição continua sem descrição. O usuário escolheu manter assim, para economizar requisições.
- **Os filtros do LinkedIn nem sempre são respeitados.** Podem aparecer vagas fora do nível ou da modalidade pedidos. Confira `nivel` e `titulo`.
- **As vagas da Gupy não são pré-filtradas** por nível nem por data. O robô salva tudo o que a busca retornou.
  - Para responder "quais estágios", filtre por `tipo_contrato = 'Estágio'` ou por `nivel = 'Estágio'`, que também pega vagas com "estagiário" no nome.
  - Para "publicadas recentemente", filtre por `publicada_em`.

## Como consultar

Sempre abra o banco **somente leitura** (`mode=ro`). No Windows, defina `PYTHONIOENCODING=utf-8`, senão os acentos saem errados no terminal.

Modelo (PowerShell, na raiz do projeto):
```powershell
$env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python -c "import sqlite3,pandas as pd; c=sqlite3.connect('file:data/vagas.db?mode=ro',uri=True); print(pd.read_sql('''SELECT titulo, empresa, url FROM vagas LIMIT 10''', c).to_string())"
```
Troque o SQL entre `'''` pelas consultas abaixo. Para resultados grandes, grave em arquivo com `.to_csv('saida.csv', index=False)`.

### Consultas prontas

```sql
-- Vagas novas da última execução
SELECT titulo, empresa, local, url FROM vagas
WHERE execucao = (SELECT MAX(id) FROM execucoes);

-- Todas as vagas encontradas na última execução (novas + já conhecidas)
SELECT titulo, empresa, local, url FROM vagas
WHERE visto_em >= (SELECT iniciada_em FROM execucoes ORDER BY id DESC LIMIT 1)
ORDER BY titulo;

-- Busca por texto no título ou descrição
-- (LIKE não ignora acentos: procure as duas formas, ex. 'estágio' e 'estagio')
SELECT titulo, empresa, url FROM vagas
WHERE titulo LIKE '%estágio%' OR titulo LIKE '%estagio%'
   OR descricao LIKE '%estágio%' OR descricao LIKE '%estagio%';

-- Publicadas nos últimos 7 dias
SELECT titulo, empresa, publicada_em, url FROM vagas
WHERE publicada_em >= date('now', '-7 days')
ORDER BY publicada_em DESC;

-- Vagas por site
SELECT site, COUNT(*) AS vagas FROM vagas GROUP BY site;

-- Estágios da Gupy publicados nas últimas 24h (a Gupy guarda a hora)
SELECT titulo, empresa, local, publicada_em, url FROM vagas
WHERE site = 'gupy' AND tipo_contrato = 'Estágio'
  AND publicada_em >= strftime('%Y-%m-%d %H:%M', 'now', 'localtime', '-1 day')
ORDER BY publicada_em DESC;

-- Vagas por empresa
SELECT empresa, COUNT(*) AS vagas FROM vagas GROUP BY empresa ORDER BY vagas DESC;

-- Vagas por nível
SELECT nivel, COUNT(*) AS vagas FROM vagas GROUP BY nivel ORDER BY vagas DESC;

-- Histórico de execuções e quantas vagas novas cada uma trouxe
SELECT e.id, e.iniciada_em, e.terminada_em, COUNT(v.job_id) AS novas
FROM execucoes e LEFT JOIN vagas v ON v.execucao = e.id
GROUP BY e.id ORDER BY e.id DESC;
```

## Lendo pelo Excel

```python
import pandas as pd
todas = pd.read_excel("data/vagas.xlsx", sheet_name="Todas")
novas = pd.read_excel("data/vagas.xlsx", sheet_name="Novas")
```
Colunas: `Título, Empresa, Site, Local, Modalidade, Nível, Contrato, Área, Publicada em, Candidatos, Link, Busca, Visto pela 1ª vez, Descrição`.

A planilha pode estar desatualizada ou cortada. Prefira o banco.

---

# Parte 2 — Mexer no código

## Como o código está organizado

```
src/wb_trampo/
  __main__.py      CLI (argparse): buscar, exportar, enviar-sheets; códigos de saída; intervalo mínimo
  config.py        lê config.toml (Limites, Busca) e google_sheets.toml (GoogleSheets); valida tudo
  scraper.py       orquestra: para cada busca -> fonte.listar() -> já vista? -> fonte.detalhar() -> banco.salvar()
  cliente.py       HTTP "educado": pausa por host, teto de requisições, 429/999, contagem por host
  banco.py         SQLite: schema, migração (coluna site), upsert com COALESCE, execuções
  exportar.py      Excel (abas Novas/Todas, links, filtros, larguras)
  sheets.py        envio ao Google Sheets via Apps Script (POST JSON com senha), uma aba por site e dia
  logs.py          log na tela (INFO) e em arquivo diário (DEBUG)
  urls.py          URLs e filtros do LinkedIn (tabelas NIVEL, MODALIDADE, PUBLICADA; segundos())
  parser.py        HTML do LinkedIn -> dicts (seletores no topo); html_para_texto()
  fontes/
    __init__.py    FONTES = {"linkedin": LinkedIn(), "gupy": Gupy()}; NAO_SUPORTADOS (indeed)
    base.py        Protocol Fonte: nome, validar(busca), listar(busca, cliente, limite), detalhar(vaga, cliente)
    linkedin.py    endpoints públicos "jobs-guest" (lista e detalhe)
    gupy.py        API pública do portal da Gupy (sem detalhe: a lista já traz tudo)
apps_script/Codigo.gs   script colado na planilha Google (doPost: senha, aba, sem repetir links, larguras)
tests/                  pytest, sem internet (fixtures em tests/fixtures/, clientes falsos)
```

### Fluxo de uma execução (`buscar`)

1. `config.carregar("config.toml")` valida as buscas e os limites e lê o `google_sheets.toml` ao lado, se existir.
2. Se a última execução começou há menos de `intervalo_minimo_min`, o robô para com código 0. `--forcar` ignora essa regra.
3. É criado um `Cliente`, com pausa de `pausa_linkedin_*` para `www.linkedin.com` e de `pausa_*` para os demais hosts, além do `max_requisicoes`.
4. `scraper.executar()`:
   - cria uma linha em `execucoes`;
   - para cada busca, `FONTES[busca.site].listar()` devolve dicts de vagas (gerador, página a página);
   - **vaga já no banco** só ganha `marcar_visto`;
   - **vaga nova** passa por `detalhar()` (só se `buscar_descricao` estiver ligado) e por `salvar()`.
5. Exceções:
   - `LimiteRequisicoes` encerra normalmente;
   - `Bloqueado` (HTTP 999, ou 429 persistente) dá código 2;
   - o que foi coletado fica salvo em todos os casos.
6. Excel (`exportar`), depois Sheets (`sheets.enviar_novas`). Os dois rodam mesmo depois de um bloqueio.

### Endpoints usados

- **LinkedIn**, lista (~10 cards por chamada; não há parâmetro que aumente esse número):
  `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords&location&f_TPR=r<segundos>&f_E&f_WT&start`
- **LinkedIn**, detalhe: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}`
- **Gupy**: `GET https://portal.gupy.io/api/job-search/jobs`
  - parâmetros: `jobName`, `limit` (≤ 50), `offset`, `state` (nome completo com acento), `city` (**com acento**), `workplaceType` (`remote`, `hybrid` ou `on-site`, só um valor);
  - `pagination.total` tem teto de 100;
  - `jobName` casa com o **nome** da vaga, então "estagio backend" retorna 0;
  - o filtro `type` não funciona.

### Como adicionar um site novo

1. Crie `src/wb_trampo/fontes/<site>.py` com uma classe que siga o `Protocol` de `fontes/base.py`:
   - `validar(busca)` levanta `ValueError` com uma mensagem clara;
   - `listar(...)` é um gerador de dicts com `job_id` (com prefixo `<site>:`), `url`, `titulo`, `empresa`, `local`, `modalidade`, `publicada_em`, `tipo_contrato`, `nivel` e `descricao`;
   - `detalhar(...)` devolve `{}` se a lista já traz tudo.
2. Registre a fonte em `FONTES`, em `fontes/__init__.py`.
3. Use `cliente.get()` / `cliente.get_json()`, que já fazem pausa, teto e tratamento de 429/999. Para dar pausa própria ao host, adicione-o em `pausas_por_host` em `__main__.py`.
4. Se o site precisar de um nome bonito na aba do Sheets, adicione-o em `sheets.NOME_SITE`.
5. Crie `tests/test_<site>.py` com uma fixture JSON ou HTML. Os testes não acessam a internet.
6. Atualize o README (tabela de sites e comentários do `config.toml`) e este arquivo.

### Google Sheets (detalhes)

- `sheets.enviar_novas()` agrupa as vagas novas da última execução por site e faz 1 POST por site para o `url_script`. O corpo é `{senha, aba, cabecalho, linhas}`.
- O nome da aba é o dia de `execucoes.iniciada_em` mais o nome do site (`2026-10-27 Gupy`).
- O Apps Script compara links pela posição da coluna `Link` no cabeçalho enviado. **Não mude a ordem das colunas antes de "Link"**: abas que já existem passariam a repetir vagas. Colunas novas entram **depois** de "Link".
- Células que começam com `=`, `+`, `-` ou `@` ganham um `'` na frente, para não virarem fórmula. Textos com mais de 45.000 caracteres são cortados.
- Mudanças no `apps_script/Codigo.gs` só valem na planilha depois que o usuário cola o código e implanta uma **nova versão**. Lembre o usuário disso.

### Testes

```powershell
.venv\Scripts\python -m pytest
```
Todos os testes devem passar (100 na última contagem). Os testes não acessam a internet. Para testes reais, use uma cópia do banco no diretório temporário, nunca `data/vagas.db`.

## Decisões tomadas com o usuário (não desfazer sem perguntar)

| Decisão | Motivo |
|---|---|
| Sem login no LinkedIn; só páginas públicas | O usuário não quer arriscar a conta dele. |
| `requests` (não Playwright) | Escolha do usuário; mais leve. |
| Sem burlar bloqueio (proxy, IP, CAPTCHA, Cloudflare) | Regra do projeto. Por isso o Indeed não é suportado. |
| Gupy salva **tudo** o que a busca retornar | O usuário filtra na planilha. `nivel` e `publicada` são ignorados na Gupy (o log avisa). |
| `publicada` em **segundos** no `config.toml`, com tabela nos comentários | Pedido do usuário. |
| Uma busca por site (`site = ...` em cada `[[buscas]]`) | Pedido do usuário. |
| Só vagas brasileiras por enquanto | Pedido do usuário (por isso o Remotive foi descartado). |
| Pausa por host, teto de requisições, intervalo mínimo, parar em 999 | Proteger o IP do usuário. Ele aumentou as pausas do LinkedIn no próprio `config.toml`. |
| **Não** parar a busca ao achar vagas conhecidas | O usuário preferiu ler todas as páginas. |
| **Não** reabrir vagas já vistas para completar a descrição | O usuário preferiu economizar requisições. |
| Google Sheets via **Apps Script** (não conta de serviço nem OAuth) | Configuração mais simples; o usuário tentou e preferiu essa. |
| Sheets: abas por **site e dia da busca**, **sem descrição**, com **Publicada em** | Pedidos do usuário. |
| Link e senha do Sheets em `google_sheets.toml` (fora do git) | Segurança: o `config.toml` pode ir para o git. |

## Pendências e ideias (ainda não feitas)

- **Ordenar o LinkedIn por mais recentes** (`sortBy=DD`), com um campo `ordem = "recentes" | "relevancia"` na busca. Foi planejado, mas o usuário interrompeu antes da implementação. Pergunte antes de fazer.
- **Mais sites brasileiros:** Vagas.com.br, Greenhouse e Lever (filtrando o Brasil) e páginas de carreira de empresas. O Itaú usa a Gupy (`vemproitau.gupy.io`); a plataforma do Bradesco não foi identificada.
- **Planilha Google:** há uma aba antiga `2026-10-27` (formato de antes da separação por site) e a aba `2026-10-27 Gupy` tem descrições na coluna H (de antes da troca por "Publicada em"). Não mexa sem o usuário pedir.
- O usuário precisa colar o `apps_script/Codigo.gs` atual na planilha e implantar uma **nova versão**, para as abas novas nascerem com as larguras certas.

## Comandos do projeto

| Comando | O que faz |
|---|---|
| `.venv\Scripts\python -m wb_trampo buscar` | Roda as buscas do `config.toml` e atualiza banco, Excel e Sheets (acessa a internet; só se o usuário pedir). |
| `.venv\Scripts\python -m wb_trampo buscar --sem-descricao --sem-sheets` | Busca mais barata, sem enviar ao Sheets. |
| `.venv\Scripts\python -m wb_trampo buscar --forcar` | Ignora o intervalo mínimo entre execuções. |
| `.venv\Scripts\python -m wb_trampo --banco copia.db buscar` | Busca usando outro banco (bom para testes). |
| `.venv\Scripts\python -m wb_trampo exportar [--filtro texto] [--saida arq.xlsx]` | Gera o Excel a partir do banco (sem internet). |
| `.venv\Scripts\python -m wb_trampo enviar-sheets` | Reenvia ao Sheets as vagas novas da última execução (só se o usuário pedir). |
| `.venv\Scripts\python -m wb_trampo -v buscar` | Mostra cada requisição na tela. |
| `.venv\Scripts\python -m pytest` | Testes (sem internet). |
