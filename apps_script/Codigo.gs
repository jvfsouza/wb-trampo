/**
 * wb-trampo: recebe as vagas novas do robô e grava numa aba do dia desta planilha.
 *
 * Como instalar (uma vez só):
 *  1. Na planilha: Extensões > Apps Script. Apague o que estiver lá e cole este arquivo inteiro.
 *  2. Troque a SENHA abaixo por uma senha sua (a mesma vai no google_sheets.toml do robô).
 *  3. Salve (ícone de disquete).
 *  4. Implantar > Nova implantação > tipo "App da Web":
 *       - Executar como: Eu
 *       - Quem pode acessar: Qualquer pessoa
 *     Clique em Implantar, autorize com a sua conta e copie o "URL do app da Web" (termina em /exec).
 *
 * Se editar este script depois: Implantar > Gerenciar implantações > lápis > Versão: "Nova versão"
 * > Implantar. Assim o link continua o mesmo.
 */

const SENHA = 'troque-esta-senha';

// Largura de cada coluna em pixels (pelo nome do cabeçalho). Ajuste à vontade.
const LARGURAS = {
  'Título': 300,
  'Empresa': 200,
  'Site': 70,
  'Local': 170,
  'Modalidade': 100,
  'Contrato': 110,
  'Link': 280,
  'Publicada em': 130,
};

function doPost(e) {
  let dados;
  try {
    dados = JSON.parse(e.postData.contents);
  } catch (erro) {
    return resposta({ ok: false, erro: 'corpo da requisição não é JSON' });
  }
  if (SENHA === 'troque-esta-senha') {
    return resposta({ ok: false, erro: 'troque a SENHA no Apps Script antes de usar' });
  }
  if (dados.senha !== SENHA) {
    return resposta({ ok: false, erro: 'senha incorreta' });
  }

  const trava = LockService.getScriptLock();
  trava.waitLock(30000); // evita duas execuções escrevendo ao mesmo tempo
  try {
    const planilha = SpreadsheetApp.getActiveSpreadsheet();
    const cabecalho = dados.cabecalho;
    let aba = planilha.getSheetByName(dados.aba);
    let criada = false;
    if (!aba) {
      aba = planilha.insertSheet(dados.aba);
      aba.getRange(1, 1, 1, cabecalho.length).setValues([cabecalho]).setFontWeight('bold');
      aba.setFrozenRows(1);
      cabecalho.forEach(function (nome, i) {
        if (LARGURAS[nome]) aba.setColumnWidth(i + 1, LARGURAS[nome]);
      });
      criada = true;
    }

    // não repete vagas cujo link já está na aba
    const colunaLink = cabecalho.indexOf('Link') + 1;
    const ultima = aba.getLastRow();
    const existentes = new Set(
      ultima > 1 ? aba.getRange(2, colunaLink, ultima - 1, 1).getValues().map(function (l) { return String(l[0]); }) : []
    );
    const novas = dados.linhas.filter(function (l) { return !existentes.has(String(l[colunaLink - 1])); });
    if (novas.length) {
      // a aba nasce com 1000 linhas; cria mais se precisar
      const faltam = ultima + novas.length - aba.getMaxRows();
      if (faltam > 0) aba.insertRowsAfter(aba.getMaxRows(), faltam);
      aba.getRange(ultima + 1, 1, novas.length, cabecalho.length)
        .setValues(novas)
        // CLIP: texto longo (descrição) fica cortado na célula em vez de esticar a linha;
        // clique na célula para ler tudo
        .setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP)
        .setVerticalAlignment('top');
    }
    return resposta({
      ok: true,
      aba: dados.aba,
      criada: criada,
      adicionadas: novas.length,
      repetidas: dados.linhas.length - novas.length,
    });
  } finally {
    trava.releaseLock();
  }
}

function resposta(objeto) {
  return ContentService.createTextOutput(JSON.stringify(objeto)).setMimeType(ContentService.MimeType.JSON);
}
