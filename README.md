# wb-trampo

Robô em Python que busca vagas de emprego **públicas** no **LinkedIn** e na **Gupy**, sem login e sem usar a sua conta. Ele:

- salva tudo num banco **SQLite** (`data/vagas.db`), sem duplicar vagas;
- gera uma planilha **Excel** (`data/vagas.xlsx`) com as vagas novas e todas as vagas;
- envia as vagas **novas** para uma planilha **Google Sheets**, numa aba por site e dia (opcional);
- grava **logs** de cada execução, para saber até onde foi e onde falhou.

---

## Sumário

1. [Instalação](#instalação)
2. [Uso rápido](#uso-rápido)
3. [Configurando as buscas (`config.toml`)](#configurando-as-buscas-configtoml)
4. [Sites suportados](#sites-suportados)
5. [Comandos](#comandos)
6. [O que é gerado](#o-que-é-gerado)
7. [Google Sheets](#google-sheets)
8. [Limites e bloqueios (proteger o seu IP)](#limites-e-bloqueios-proteger-o-seu-ip)
9. [Logs e códigos de saída](#logs-e-códigos-de-saída)
10. [Arquivos do projeto](#arquivos-do-projeto)
11. [Testes](#testes)
12. [Problemas comuns](#problemas-comuns)

---

## Instalação

Requer **Python 3.11+** (testado no 3.13, Windows).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

O `requirements.txt` instala o projeto em modo editável, com as dependências de teste: requests, beautifulsoup4, lxml, pandas, openpyxl e pytest.

## Uso rápido

1. Edite as buscas no `config.toml` ([veja como](#configurando-as-buscas-configtoml)).
2. Rode:

   ```powershell
   .venv\Scripts\python -m wb_trampo buscar
   ```

3. Veja o resultado em `data/vagas.xlsx`, na aba **Novas**, ou na sua planilha Google, se estiver [configurada](#google-sheets).

---

## Configurando as buscas (`config.toml`)

O arquivo tem duas partes: os **limites**, que valem para todas as buscas, e as **buscas**, cada uma num bloco `[[buscas]]`. Cada campo tem uma explicação logo acima dele, no próprio arquivo.

### Buscas

Cada bloco `[[buscas]]` é **uma busca em um site**. Para ter mais buscas, copie o bloco e cole embaixo. Para desativar uma busca sem apagar, coloque `#` no início de todas as linhas do bloco.

```toml
[[buscas]]
site = "linkedin"                    # obrigatório: linkedin | gupy
palavra_chave = "estagio backend"    # obrigatório
local = "São Paulo"                  # opcional
modalidade = ["presencial", "hibrido"]   # opcional: presencial | hibrido | remoto
nivel = ["estagio", "junior"]        # opcional (só LinkedIn): estagio | junior | associado | pleno | senior | diretor | executivo
publicada = 86400                    # opcional (só LinkedIn): há quanto tempo, EM SEGUNDOS
```

| Campo | Valores | Observações |
|---|---|---|
| `site` | `linkedin`, `gupy` | Obrigatório. |
| `palavra_chave` | texto | Obrigatório. No LinkedIn pode ter várias palavras e operadores (`"estágio" OR "junior"`, `AND`, `NOT`); use aspas simples por fora quando o texto tiver aspas duplas. Na Gupy, use **uma palavra**, porque ela é procurada no nome da vaga. |
| `local` | texto | LinkedIn: cidade, estado ou país em texto livre. Gupy: estado (`"SP"` ou `"São Paulo"`) ou cidade **com acento** (`"São José dos Campos"`). |
| `modalidade` | `presencial`, `hibrido`, `remoto` | Lista ou texto. Na Gupy, com **um** valor ela filtra; com vários, vêm todas. |
| `nivel` | `estagio`, `junior`, `associado`, `pleno`, `senior`, `diretor`, `executivo` | Só LinkedIn (no LinkedIn, `pleno` e `senior` são o mesmo filtro). Na Gupy é ignorado. |
| `publicada` | segundos, ou `"24h"`, `"semana"`, `"mes"` | Só LinkedIn. Na Gupy é ignorado. |

Tabela de segundos para `publicada`:

| Segundos | Período | Segundos | Período |
|---|---|---|---|
| `3600` | 1 hora | `86400` | 24 horas |
| `7200` | 2 horas | `172800` | 2 dias |
| `21600` | 6 horas | `604800` | 7 dias |
| `43200` | 12 horas | `2592000` | 30 dias |

Acentos são opcionais em tudo (`"hibrido"` e `"híbrido"` funcionam igual). A exceção é a **cidade na Gupy**, que precisa ir com acento.

Se algo estiver errado (campo com erro de digitação, valor inválido, aspas sem fechar), o robô para antes de buscar e diz **qual busca e qual campo** tem o problema.

### Limites (`[limites]`)

| Campo | Padrão | O que faz |
|---|---|---|
| `max_vagas_por_busca` | 100 | Quantas vagas ler, no máximo, em cada busca. O LinkedIn manda cerca de 10 por página; a Gupy não passa de 100. |
| `pausa_linkedin_min_s` / `pausa_linkedin_max_s` | 8 / 15 | Pausa aleatória entre requisições ao **LinkedIn**, em segundos. |
| `pausa_min_s` / `pausa_max_s` | 2 / 5 | Pausa entre requisições aos outros sites (Gupy). |
| `max_requisicoes` | 200 | Teto de requisições por execução, somando todos os sites. `0` = sem teto. |
| `intervalo_minimo_min` | 30 | Minutos mínimos entre uma execução e outra. `0` = desliga. |
| `buscar_descricao` | `true` | No LinkedIn, abre cada vaga nova para pegar descrição, nível, contrato, área e nº de candidatos (1 requisição a mais por vaga). Na Gupy a descrição já vem junto. |

Os padrões acima valem quando o campo não está no arquivo. O seu `config.toml` pode ter outros valores.

---

## Sites suportados

| Site | Como funciona | O que vem | Limitações |
|---|---|---|---|
| **LinkedIn** (`linkedin`) | Páginas públicas de vagas (as mesmas que aparecem sem login). Os filtros são aplicados pelo próprio LinkedIn. | Título, empresa, local, data (só o dia) e link. Com descrição: também descrição, nível, contrato, área e candidatos. | Às vezes ignora os filtros de nível e modalidade. Cerca de 10 vagas por página (não dá para aumentar). Bloqueia quem faz muitas requisições: [veja os limites](#limites-e-bloqueios-proteger-o-seu-ip). |
| **Gupy** (`gupy`) | API pública do portal [portal.gupy.io](https://portal.gupy.io), que reúne vagas de muitas empresas brasileiras (Itaú, Ambev, Boticário...). | Título, empresa, cidade/UF, modalidade real, tipo de contrato, data **com hora**, descrição completa e link. | **Salva tudo o que a busca retornar**: o robô não descarta nada, e você filtra na planilha. Palavra-chave só no nome da vaga. Máximo de 100 vagas por busca (para pegar mais, faça várias buscas: por estado, modalidade ou palavra). |
| Indeed | **Não suportado** | | Bloqueia robôs com uma verificação (Cloudflare), e o robô não tenta burlar isso. |

Na Gupy, o tipo de contrato vem traduzido: Estágio, Efetivo, PJ, Trainee, Temporário, Aprendiz, Autônomo, Terceirizado, Banco de talentos. A coluna **Nível** fica "Estágio" quando a vaga é de estágio ou tem "estagiário" no nome.

---

## Comandos

Rode sempre na raiz do projeto: `.venv\Scripts\python -m wb_trampo <comando>`, ou só `python -m wb_trampo <comando>` com a venv ativada.

| Comando | O que faz |
|---|---|
| `buscar` | Roda as buscas do `config.toml`, atualiza o banco, gera o Excel e envia ao Google Sheets. |
| `buscar --sem-descricao` | Não abre cada vaga do LinkedIn (bem menos requisições; fica sem descrição, nível, contrato, área e candidatos). |
| `buscar --sem-excel` | Não gera a planilha Excel. |
| `buscar --sem-sheets` | Não envia ao Google Sheets. |
| `buscar --forcar` | Busca mesmo se a última execução foi há menos de `intervalo_minimo_min` minutos. |
| `buscar --config outro.toml` | Usa outro arquivo de buscas. |
| `buscar --excel caminho.xlsx` | Salva a planilha em outro lugar. |
| `exportar` | Gera a planilha Excel a partir do banco (sem internet). |
| `exportar --filtro django --saida django.xlsx` | Planilha só com vagas que citam "django" no título ou na descrição. |
| `enviar-sheets` | Envia de novo ao Google Sheets as vagas novas da última busca (útil se o envio falhou). Não repete o que já está lá. |

Opções gerais (vão **antes** do comando): `--banco caminho.db`, `--logs pasta` e `-v` (mostra cada requisição na tela). Exemplo: `python -m wb_trampo -v buscar`.

---

## O que é gerado

| Arquivo | Conteúdo |
|---|---|
| `data/vagas.db` | Banco SQLite com **todas** as vagas já vistas, uma linha por vaga. É a fonte da verdade. |
| `data/vagas.xlsx` | Planilha com as abas **Novas** (vagas que apareceram pela 1ª vez na última execução) e **Todas**. Links clicáveis, cabeçalho fixo, filtro em todas as colunas e descrição cortada em 500 caracteres. |
| `data/vagas_AAAA-MM-DD_HHMM.xlsx` | Cópia criada quando o `vagas.xlsx` estava aberto no Excel (o robô não falha por isso). |
| `data/logs/wb_trampo_AAAA-MM-DD.log` | Log do dia ([veja abaixo](#logs-e-códigos-de-saída)). |
| `data/debug/*.html` | Cópia de uma página do LinkedIn que veio sem nenhuma vaga reconhecida (sinal de que o layout mudou). |

Colunas do Excel: Título, Empresa, Site, Local, Modalidade, Nível, Contrato, Área, Publicada em, Candidatos, Link, Busca, Visto pela 1ª vez, Descrição.

**Vaga já vista não é aberta de novo.** Se ela aparecer em outra busca, o robô só registra que a viu (`visto_em`) e não gasta requisição. Por isso, uma vaga do LinkedIn salva sem descrição continua sem descrição.

A coluna **Modalidade** do LinkedIn mostra o filtro usado na busca, não um dado da vaga. O cartão do LinkedIn não informa a modalidade. Na Gupy é a modalidade real da vaga.

---

## Google Sheets

No fim de cada busca, as vagas **novas** vão para a sua planilha Google, em **abas separadas por site, com o dia da busca no nome**, por exemplo `2026-10-27 Gupy` e `2026-10-27 LinkedIn`.

- Colunas: **Título, Empresa, Site, Local, Modalidade, Contrato, Link, Publicada em**. Na Gupy a data vem com hora; no LinkedIn, só o dia.
- **A descrição não vai para o Sheets.** Ela fica no banco e no Excel.
- Se a busca rodar de novo no mesmo dia, as vagas entram no fim da mesma aba, **sem repetir links**.
- A aba usa o dia da **busca**, não o do envio: um `enviar-sheets` no dia seguinte manda para a aba do dia em que a busca rodou.
- Cada aba nova nasce formatada: cabeçalho em negrito e fixo, larguras ajustadas, texto longo cortado na célula e alinhado no topo.

### Como funciona

O envio é feito por um pequeno **Apps Script** ([`apps_script/Codigo.gs`](apps_script/Codigo.gs)) instalado **dentro da própria planilha** e publicado como "App da Web". O robô manda as vagas para o link desse script junto com uma senha; o script cria a aba e grava as linhas. Não precisa de Google Cloud, de credenciais nem de login no terminal.

### Instalação (uma vez só, ~5 minutos)

1. Abra a planilha no Google Sheets e vá em **Extensões > Apps Script**.
2. Apague o código que aparecer e cole **todo** o conteúdo de `apps_script/Codigo.gs`.
3. Na linha `const SENHA = 'troque-esta-senha';`, troque pela sua senha (um texto longo qualquer). Salve (ícone de disquete).
4. Clique em **Implantar > Nova implantação**, depois na engrenagem > **App da Web**:
   - **Executar como:** Eu
   - **Quem pode acessar:** Qualquer pessoa
5. Clique em **Implantar** e autorize com a sua conta. Se aparecer "O Google não verificou este app", clique em **Avançado > Acessar ... (não seguro)**: o script é seu.
6. Copie o **URL do app da Web**, que termina em `/exec`.
7. No projeto, copie `google_sheets.exemplo.toml` para **`google_sheets.toml`** e preencha:

   ```toml
   url_script = "https://script.google.com/macros/s/.../exec"
   senha = "a mesma senha do passo 3"
   ```

8. Teste com `python -m wb_trampo enviar-sheets`.

### Depois de instalado

- **Mudou o script** (por exemplo, uma versão nova do `Codigo.gs`)? Cole o código novo e vá em **Implantar > Gerenciar implantações > lápis > Versão: Nova versão > Implantar**. Assim o link continua o mesmo. Sem isso, a planilha continua rodando a versão antiga.
- **Larguras das colunas:** ajuste os números em `LARGURAS`, no topo do script.
- **Desligar o envio:** apague ou renomeie o `google_sheets.toml`, ou use `buscar --sem-sheets` só uma vez.
- **Segurança:** o `google_sheets.toml` está no `.gitignore`. Não compartilhe o link nem a senha: quem tiver os dois consegue escrever na planilha.
- **Se o envio falhar:** o banco e o Excel continuam salvos, o log explica o motivo (senha errada, implantação sem "Qualquer pessoa", sem internet...) e o código de saída é `1`. Corrija e rode `enviar-sheets`.

---

## Limites e bloqueios (proteger o seu IP)

O LinkedIn bloqueia quem faz muitas requisições em pouco tempo. O robô **não** usa proxy, troca de IP nem nenhum disfarce. Ele protege o seu IP indo devagar e parando quando o site pede:

- **Pausa entre requisições:** maior no LinkedIn (`pausa_linkedin_*`) e curta na Gupy (`pausa_*`). A pausa conta desde a última requisição ao **mesmo** site, então alternar entre sites não encurta o descanso do LinkedIn.
- **Estimativa de tempo:** no começo de cada busca do LinkedIn, o log mostra quanto ela pode levar. Por exemplo: `até ~110 requisições ≈ 21 min`.
- **Teto por execução** (`max_requisicoes`): ao chegar nele, o robô salva o que coletou e termina normalmente; as buscas que faltaram ficam para a próxima vez.
- **Intervalo mínimo** (`intervalo_minimo_min`): se você rodar de novo cedo demais, ele avisa e não busca. Para rodar mesmo assim, use `--forcar`.
- **Quando o site recusa:**
  - **HTTP 999** (o LinkedIn recusando robôs): para na hora.
  - **HTTP 429** (muitas requisições): espera o tempo que o site pedir (ou 60 s e depois 180 s) e para se continuar recusando.
  - O que já foi coletado fica salvo, e o Excel e o Sheets são gerados. Espere algumas horas antes de rodar de novo.
- No fim, o log mostra quantas requisições foram feitas em cada site.

**Quanto custa uma busca no LinkedIn** (cerca de 10 vagas por página, mais 1 requisição por vaga nova quando há descrição):

| Vagas | Sem descrição | Com descrição |
|---|---|---|
| 100 | ~10 requisições | ~110 requisições |
| 300 | ~30 requisições | ~330 requisições |

Com pausa de 8–15 s, isso dá cerca de 2 min e 21 min para 100 vagas. O tempo cresce na mesma proporção da pausa.

**Para fazer menos requisições no LinkedIn:**
- Use `publicada` curta (ex.: `86400`): menos vagas, menos páginas.
- Use `buscar_descricao = false` ou `--sem-descricao`: corta 1 requisição por vaga nova.
- Diminua `max_vagas_por_busca` e rode poucas vezes por dia.
- Se subir `max_vagas_por_busca`, suba também `max_requisicoes`, senão o robô para no meio.
- Prefira a Gupy quando a vaga estiver lá: ela faz no máximo 2 requisições por busca.

---

## Logs e códigos de saída

Cada execução mostra o progresso na tela e grava tudo em `data/logs/wb_trampo_AAAA-MM-DD.log` (um arquivo por dia, acumulando as execuções).

- **Na tela:** busca atual, página, cada vaga (`+ NOVA` ou `= já vista`, com título e empresa), avisos e erros.
- **No arquivo:** tudo isso, mais cada requisição (URL, status HTTP, tamanho, tempo), pausas e o traceback completo de qualquer erro.
- `-v` mostra na tela também o que normalmente só vai para o arquivo.

Para saber onde parou, procure no arquivo por `ERROR` ou `WARNING`. As últimas linhas `Busca X/Y` e `Página N` antes do erro mostram até onde o robô chegou.

| Código de saída | Significado |
|---|---|
| `0` | Tudo certo. Também quando parou no teto de requisições ou não rodou por causa do intervalo mínimo. |
| `1` | Erro (configuração inválida, falha no Excel ou no envio ao Sheets, erro inesperado). |
| `2` | O site recusou as requisições (bloqueio). |
| `130` | Interrompido com Ctrl+C. |

---

## Arquivos do projeto

| Arquivo | Para quê |
|---|---|
| `config.toml` | Suas buscas e limites. |
| `google_sheets.toml` | Link e senha do Apps Script. **Fora do git**; o modelo é `google_sheets.exemplo.toml`. |
| `apps_script/Codigo.gs` | O script que você cola na planilha Google. |
| `src/wb_trampo/` | Código do robô ([detalhes no AGENTS.md](AGENTS.md#como-o-código-está-organizado)). |
| `tests/` | Testes automáticos (não acessam a internet). |
| `AGENTS.md` | Guia para outros agentes de IA: como ler os dados, arquitetura e decisões do projeto. |
| `data/` | Tudo o que o robô gera (banco, Excel, logs). **Fora do git.** |

---

## Testes

```powershell
.venv\Scripts\python -m pytest
```

Os testes não acessam a internet. Usam HTML e JSON de exemplo em `tests/fixtures/` e clientes falsos para HTTP, LinkedIn, Gupy e o Apps Script.

---

## Problemas comuns

| Sintoma | Causa provável e solução |
|---|---|
| `Problema no arquivo de configuração: ...` | O `config.toml` tem um erro, e a mensagem diz qual busca e qual campo. Muitas vezes é uma linha sem `#` no meio de um bloco comentado, ou uma linha de enfeite (`-----`) sem `#`. |
| "A última busca foi há X min..." | É o intervalo mínimo entre execuções. Espere, ou rode com `--forcar`. |
| `HTTP 429` / `HTTP 999` / código de saída `2` | O LinkedIn está limitando o seu IP. Espere algumas horas e aumente as pausas ou diminua `max_vagas_por_busca`. |
| Gupy retorna 0 vagas | A palavra-chave tem mais de uma palavra ("estagio backend"), ou a cidade está sem acento ("sao paulo" em vez de "São Paulo"). |
| LinkedIn traz vagas fora do nível pedido | O LinkedIn às vezes ignora o filtro. Confira as colunas Nível e Título (Nível só vem com descrição). |
| "Nenhuma vaga reconhecida no HTML" | O LinkedIn mudou o layout. Veja o HTML em `data/debug/` e ajuste os seletores no topo de `src/wb_trampo/parser.py`. |
| Google Sheets: "não respondeu com JSON" | A implantação do Apps Script não está com "Quem pode acessar: Qualquer pessoa", ou o `url_script` não termina em `/exec`. |
| Google Sheets: "senha incorreta" | A senha do `google_sheets.toml` é diferente da `SENHA` do script, ou o script foi editado sem implantar uma **nova versão**. |
| Aba nova no Sheets sem formatação | A planilha ainda roda a versão antiga do script. Cole o `apps_script/Codigo.gs` atual e implante uma **nova versão**. |
| O Excel não atualizou | Ele estava aberto. Veja a cópia `data/vagas_AAAA-MM-DD_HHMM.xlsx`. |
