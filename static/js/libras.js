/*
 * VLibras (tradutor de Libras do Governo Federal), carregado só quando a pessoa pede
 * ou quando ligou "abrir o tradutor de Libras" nas preferências. Carregar sempre
 * deixaria todas as telas mais lentas e o botão flutuante atrapalharia o leitor de tela.
 */
(function () {
  "use strict";

  var ENDERECO = "https://vlibras.gov.br/app";
  var estado = "parado";

  function abrirJanela() {
    if (window.VLibrasWidget && typeof window.VLibrasWidget.open === "function") window.VLibrasWidget.open();
  }

  function carregar(abrir) {
    if (estado === "pronto") {
      if (abrir) abrirJanela();
      return;
    }
    if (estado === "carregando") return;
    estado = "carregando";
    var script = document.createElement("script");
    script.src = ENDERECO + "/vlibras-plugin.js";
    script.onload = function () {
      new window.VLibras.Widget(ENDERECO);
      estado = "pronto";
      if (abrir) abrirJanela();
    };
    script.onerror = function () {
      estado = "parado";
      if (window.Anunciador) {
        window.Anunciador.anunciar("Não foi possível abrir o tradutor de Libras. Verifique a internet e tente de novo.");
      }
    };
    document.body.appendChild(script);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var botao = document.querySelector("[data-abrir-libras]");
    if (botao) {
      botao.hidden = false;
      botao.addEventListener("click", function () { carregar(true); });
    }
    if (document.documentElement.dataset.libras === "1") carregar(false);
  });
})();
