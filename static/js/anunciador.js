/*
 * Anunciador: um único ponto para avisar a pessoa de algo que mudou.
 *
 *  - Escreve na região aria-live (lida por TalkBack, VoiceOver e NVDA).
 *  - Fala em voz alta com a Web Speech API (gratuita, do próprio navegador),
 *    somente se a pessoa ligou "avisos falados" nas preferências.
 *  - Vibra (Android) e toca um bipe curto (Web Audio), se ligados.
 *
 * O site funciona sem este arquivo; ele só acrescenta avisos.
 */
(function () {
  "use strict";

  var html = document.documentElement;
  var config = {
    fala: html.dataset.fala === "1",
    velocidade: (parseInt(html.dataset.falaVelocidade, 10) || 100) / 100,
    vibracao: html.dataset.vibracao === "1",
    som: html.dataset.som === "1",
  };
  var temFala = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

  function regiao(urgente) {
    return document.getElementById(urgente ? "anuncio-urgente" : "anuncio-educado");
  }

  function escreverNaRegiao(texto, urgente) {
    var alvo = regiao(urgente);
    if (!alvo) return;
    // Limpa e reescreve para que o leitor de tela anuncie mesmo textos repetidos.
    alvo.textContent = "";
    window.setTimeout(function () { alvo.textContent = texto; }, 100);
  }

  function vozPortugues() {
    var vozes = window.speechSynthesis.getVoices();
    return vozes.find(function (v) { return /^pt(-|_)BR/i.test(v.lang); }) ||
           vozes.find(function (v) { return /^pt/i.test(v.lang); }) || null;
  }

  function falar(texto, forcar) {
    if (!temFala || (!config.fala && !forcar)) return false;
    var fala = new SpeechSynthesisUtterance(texto);
    fala.lang = "pt-BR";
    fala.rate = config.velocidade;
    var voz = vozPortugues();
    if (voz) fala.voice = voz;
    window.speechSynthesis.speak(fala);
    return true;
  }

  function pararFala() {
    if (temFala) window.speechSynthesis.cancel();
  }

  var PADROES_VIBRACAO = {
    info: [150],
    chegada: [150, 100, 150],
    cancelamento: [600],
    alerta: [300, 100, 300, 100, 300],
  };

  function vibrar(tipo) {
    if (config.vibracao && navigator.vibrate) navigator.vibrate(PADROES_VIBRACAO[tipo] || PADROES_VIBRACAO.info);
  }

  var audio = null;
  function bipe(tipo) {
    if (!config.som) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      var oscilador = audio.createOscillator();
      var volume = audio.createGain();
      oscilador.frequency.value = tipo === "cancelamento" ? 440 : 880;
      volume.gain.value = 0.15;
      oscilador.connect(volume).connect(audio.destination);
      oscilador.start();
      oscilador.stop(audio.currentTime + 0.2);
    } catch (e) { /* sem som disponível */ }
  }

  function anunciar(texto, opcoes) {
    opcoes = opcoes || {};
    var tipo = opcoes.tipo || "info";
    escreverNaRegiao(texto, !!opcoes.urgente);
    bipe(tipo);
    vibrar(tipo);
    falar(texto);
  }

  // Navegadores só liberam som e fala depois de um toque na página.
  function liberarAudio() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
    } catch (e) { /* ignora */ }
    if (temFala && config.fala) {
      var silencio = new SpeechSynthesisUtterance(" ");
      silencio.volume = 0;
      window.speechSynthesis.speak(silencio);
    }
  }

  window.Anunciador = {
    anunciar: anunciar,
    falar: falar,
    pararFala: pararFala,
    liberarAudio: liberarAudio,
    temFala: temFala,
    config: config,
  };

  document.addEventListener("DOMContentLoaded", function () {
    // Foco inicial: resumo de erros ou mensagem do servidor, para ser lido primeiro.
    var alvo = document.querySelector("[data-focar-ao-carregar]");
    if (alvo) alvo.focus();

    // Mensagens do servidor também são faladas, se a pessoa quiser.
    document.querySelectorAll("[data-mensagem]").forEach(function (el) {
      falar(el.textContent.trim());
    });

    // Botões "Ouvir ..." (só aparecem se o navegador tem voz).
    document.querySelectorAll("[data-ouvir]").forEach(function (botao) {
      if (!temFala) return;
      botao.hidden = false;
      botao.addEventListener("click", function () {
        pararFala();
        var origem = document.getElementById(botao.dataset.ouvir);
        if (origem) falar(origem.dataset.textoFalado || origem.innerText, true);
      });
    });
    document.querySelectorAll("[data-parar-fala]").forEach(function (botao) {
      if (!temFala) return;
      botao.hidden = false;
      botao.addEventListener("click", pararFala);
    });

    // Botão "Ativar avisos" (libera áudio com um toque).
    document.querySelectorAll("[data-ativar-avisos]").forEach(function (botao) {
      if (!config.fala && !config.som) return;
      botao.hidden = false;
      botao.addEventListener("click", function () {
        liberarAudio();
        botao.hidden = true;
        anunciar("Avisos ativados nesta tela.");
        var titulo = document.querySelector("h1");
        if (titulo) titulo.focus();
      });
    });

    // Mostrar senha (o bloco fica escondido quando não há JavaScript).
    document.querySelectorAll("[data-mostrar-senha]").forEach(function (bloco) {
      var campo = document.getElementById(bloco.dataset.mostrarSenha);
      var caixa = bloco.querySelector("input[type=checkbox]");
      if (!campo || !caixa) return;
      bloco.hidden = false;
      caixa.addEventListener("change", function () {
        campo.type = caixa.checked ? "text" : "password";
      });
    });
  });
})();
