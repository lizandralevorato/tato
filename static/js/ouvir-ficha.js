/*
 * "Ouvir ficha": lê em voz alta, frase por frase, exatamente o texto que está na tela
 * (títulos e itens de #resumo-ficha, na ordem). Com Pausar/Continuar e Repetir.
 *
 * Pausar cancela a fala e guarda a frase em que parou; Continuar recomeça dessa frase.
 * Não usa speechSynthesis.pause(), que não funciona em parte dos aparelhos Android.
 * Usa a velocidade e a voz das preferências da pessoa (Anunciador).
 * Sem voz no navegador, os botões continuam escondidos e a ficha se lê normalmente.
 */
(function () {
  "use strict";

  var bloco = document.querySelector("[data-ficha-voz]");
  var resumo = document.getElementById("resumo-ficha");
  if (!bloco || !resumo || !window.Anunciador || !window.Anunciador.temFala) return;

  var botaoOuvir = bloco.querySelector("[data-ficha-ouvir]");
  var botaoPausar = bloco.querySelector("[data-ficha-pausar]");
  var botaoRepetir = bloco.querySelector("[data-ficha-repetir]");
  var aviso = bloco.querySelector("[data-aviso-fones]");
  var continuar = bloco.querySelector("[data-aviso-continuar]");
  var cancelar = bloco.querySelector("[data-aviso-cancelar]");
  var naoMostrar = bloco.querySelector("[data-nao-mostrar-aviso]");
  var regiaoAviso = document.getElementById("anuncio-educado");
  var mostrarAviso = bloco.dataset.mostrarAviso === "1";

  var frases = [];
  var indice = 0;
  var emFala = false;   // há leitura em andamento (ou pausada)
  var pausado = false;
  var rodada = 0;       // invalida callbacks de falas canceladas
  var falaAtual = null; // o Chrome para de disparar onend se a fala for coletada pelo GC

  function lerTela() {
    // Os mesmos elementos que a pessoa vê, na ordem do documento.
    return Array.prototype.slice
      .call(resumo.querySelectorAll("h2, li"))
      .map(function (el) { return el.textContent.replace(/\s+/g, " ").trim(); })
      .filter(Boolean);
  }

  function avisar(texto) {
    if (!regiaoAviso) return;
    regiaoAviso.textContent = "";
    window.setTimeout(function () { regiaoAviso.textContent = texto; }, 100);
  }

  function mostrarControles() {
    botaoPausar.hidden = !emFala;
    botaoRepetir.hidden = !emFala;
    botaoPausar.textContent = pausado ? "Continuar" : "Pausar";
  }

  function falarDe(inicio) {
    window.speechSynthesis.cancel();
    rodada += 1;
    var minha = rodada;
    indice = inicio;
    pausado = false;
    emFala = true;
    mostrarControles();

    function proxima() {
      if (minha !== rodada) return;
      if (indice >= frases.length) {
        emFala = false;
        mostrarControles();
        botaoRepetir.hidden = false;
        avisar("Fim da ficha.");
        return;
      }
      var texto = frases[indice];
      // Título termina com ponto para a voz fazer a pausa certa.
      var fala = window.Anunciador.criarFala(/[.!?]$/.test(texto) ? texto : texto + ".");
      fala.onend = function () { if (minha === rodada) { indice += 1; proxima(); } };
      fala.onerror = function () { if (minha === rodada) { indice += 1; proxima(); } };
      falaAtual = fala;
      window.speechSynthesis.resume();
      window.speechSynthesis.speak(fala);
    }
    // O Chrome ignora speak() logo depois de cancel().
    window.setTimeout(proxima, 80);
  }

  function comecar() {
    frases = lerTela();
    falarDe(0);
    botaoPausar.focus();
  }

  botaoOuvir.addEventListener("click", function () {
    if (mostrarAviso) {
      aviso.hidden = false;
      aviso.focus();
      return;
    }
    comecar();
  });

  continuar.addEventListener("click", function () {
    if (naoMostrar.checked) {
      mostrarAviso = false;
      var token = document.querySelector("meta[name=csrf-token]");
      if (window.fetch) {
        fetch(bloco.dataset.urlOcultarAviso, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRFToken": token ? token.content : "" },
        }).catch(function () { /* sem conexão: o aviso volta na próxima vez */ });
      }
    }
    aviso.hidden = true;
    comecar();
  });

  cancelar.addEventListener("click", function () {
    aviso.hidden = true;
    botaoOuvir.focus();
  });

  botaoPausar.addEventListener("click", function () {
    if (!emFala) return;
    if (!pausado) {
      rodada += 1;
      window.speechSynthesis.cancel();
      pausado = true;
      mostrarControles();
      avisar("Pausado.");
    } else {
      avisar("Continuando.");
      falarDe(indice);
    }
  });

  botaoRepetir.addEventListener("click", function () {
    frases = lerTela();
    avisar("Repetindo a ficha desde o início.");
    falarDe(0);
  });

  window.addEventListener("pagehide", function () { window.speechSynthesis.cancel(); });

  bloco.hidden = false;
})();
