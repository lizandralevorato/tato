/**
 * Antes de cada URL de lighthouserc.js, o Lighthouse CI chama este script para deixar o navegador
 * com a pessoa certa logada (ou sem login, nas páginas públicas).
 *
 * Usa as contas de `manage.py popular_demo`. A senha vem de SENHA_DEMO em
 * apps/agenda/management/commands/popular_demo.py (ou da variável LHCI_SENHA).
 */
const fs = require("node:fs");
const path = require("node:path");

// Primeiro prefixo que casar decide quem entra. Sem conta = página pública.
const CONTA_POR_CAMINHO = [
  ["/massoterapeuta/", "carlos@demo.local"], // alto contraste escuro, texto 200%
  ["/administrador/", "administrador@demo.local"],
  ["/comunicados/gerenciar/", "administrador@demo.local"],
  ["/comunicados/novo/", "administrador@demo.local"],
  ["/painel/", "gestao@demo.local"],
  ["/meus-agendamentos/", "ana@demo.local"],
  ["/agendar/", "ana@demo.local"],
  ["/comunicados/", "ana@demo.local"],
  ["/preferencias/", "ana@demo.local"],
];

function senhaDemo() {
  if (process.env.LHCI_SENHA) return process.env.LHCI_SENHA;
  const arquivo = path.join(__dirname, "..", "apps", "agenda", "management", "commands", "popular_demo.py");
  const achado = fs.readFileSync(arquivo, "utf8").match(/^SENHA_DEMO\s*=\s*"([^"]+)"/m);
  if (!achado) throw new Error(`SENHA_DEMO não encontrada em ${arquivo}`);
  return achado[1];
}

module.exports = async (browser, { url }) => {
  const alvo = new URL(url);
  const conta = CONTA_POR_CAMINHO.find(([prefixo]) => alvo.pathname.startsWith(prefixo))?.[1];

  const page = await browser.newPage();
  try {
    // Sai de quem estava logado na URL anterior.
    const cookies = await browser.cookies();
    if (cookies.length) await browser.deleteCookie(...cookies);
    if (!conta) return;

    await page.goto(new URL("/entrar/", alvo).href, { waitUntil: "networkidle0" });
    await page.type("#id_username", conta);
    await page.type("#id_password", senhaDemo());
    await Promise.all([page.waitForNavigation({ waitUntil: "networkidle0" }), page.click("button[type=submit]")]);

    if (new URL(page.url()).pathname.startsWith("/entrar/")) {
      throw new Error(`Não consegui entrar como ${conta}. Rodou "manage.py popular_demo"?`);
    }
  } finally {
    await page.close();
  }
};
