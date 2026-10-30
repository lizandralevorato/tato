/**
 * Lighthouse CI: `npm run lighthouse` sobe um servidor próprio na porta 8020,
 * entra com a conta demo certa para cada página (lighthouse/entrar.js) e falha
 * se alguma página ficar abaixo de 100 em acessibilidade (PLANO.md, seção 7).
 *
 * Pré-requisito: banco com `manage.py popular_demo`.
 */
const path = require("node:path");

const PORTA = 8020;
const BASE = `http://localhost:${PORTA}`;

const python =
  process.env.LHCI_PYTHON ||
  (process.platform === "win32" ? path.join(".venv", "Scripts", "python.exe") : path.join(".venv", "bin", "python"));

// Quem entra em cada página está em lighthouse/entrar.js.
const PAGINAS = [
  // Públicas
  "/entrar/",
  "/como-funciona/",
  "/acessibilidade/",
  "/offline/",
  // Colaborador
  "/meus-agendamentos/",
  "/agendar/",
  "/comunicados/",
  "/preferencias/",
  // Massoterapeuta
  "/massoterapeuta/",
  "/massoterapeuta/disponibilidade/",
  // Administrador
  "/administrador/",
  "/administrador/agendar/",
  "/administrador/pessoas/",
  "/administrador/pessoas/nova/",
  "/administrador/regras/",
  "/comunicados/gerenciar/",
  "/comunicados/novo/",
  // SESMT
  "/painel/",
  "/painel/historico/",
];

module.exports = {
  ci: {
    collect: {
      // -u: sem buffer, para o LHCI ver a linha "Quit the server" e saber que subiu.
      startServerCommand: `${python} -u manage.py runserver ${PORTA} --noreload`,
      startServerReadyPattern: "Quit the server",
      url: PAGINAS.map((caminho) => BASE + caminho),
      puppeteerScript: "lighthouse/entrar.js",
      // Acessibilidade não varia entre execuções; use --collect.numberOfRuns=3 para medir desempenho.
      numberOfRuns: 1,
      settings: {
        // Sem isso o Lighthouse apaga o cookie de sessão e cai na tela de login.
        disableStorageReset: true,
        locale: "pt-BR",
      },
    },
    assert: {
      assertions: {
        "categories:accessibility": ["error", { minScore: 1 }],
        "categories:best-practices": ["warn", { minScore: 0.9 }],
        "categories:seo": ["warn", { minScore: 0.9 }],
        // Servidor de desenvolvimento (DEBUG, sem compressão): só como referência.
        "categories:performance": ["warn", { minScore: 0.8 }],
      },
    },
    upload: {
      target: "filesystem",
      outputDir: ".lighthouseci/relatorios",
    },
  },
};
