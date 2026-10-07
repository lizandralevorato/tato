/*
 * Registra o service worker (site instalável e notificações) e cuida do
 * painel "Ativar notificações neste aparelho".
 *
 * Tudo é opcional: sem suporte, o painel explica o motivo com texto claro.
 */
(function () {
  "use strict";

  if (!("serviceWorker" in navigator)) {
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll("[data-painel-push]").forEach(function (painel) {
        escreverEstado(painel, "Este navegador não permite notificações. Use o Chrome (Android) ou o Safari (iPhone).");
      });
    });
    return;
  }

  var registro = navigator.serviceWorker.register("/sw.js", { scope: "/" });

  // Avisos que chegam com o site aberto: o service worker repassa para cá.
  navigator.serviceWorker.addEventListener("message", function (evento) {
    var dados = evento.data || {};
    if (dados.origem !== "aviso-push") return;
    document.dispatchEvent(new CustomEvent("aviso-push", { detail: dados }));
    // A agenda do massoterapeuta faz o próprio anúncio ao atualizar; nas outras telas, anunciamos aqui.
    if (!document.getElementById("agenda-ao-vivo") && window.Anunciador) {
      window.Anunciador.anunciar(dados.corpo, { tipo: dados.tipo, urgente: dados.urgente });
    }
  });

  function ehIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function instaladoNaTelaInicial() {
    return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  }

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function postarJSON(url, corpo) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), Accept: "application/json" },
      body: JSON.stringify(corpo || {}),
    });
  }

  function chaveParaBytes(base64) {
    var preenchimento = "=".repeat((4 - (base64.length % 4)) % 4);
    var bruto = window.atob((base64 + preenchimento).replace(/-/g, "+").replace(/_/g, "/"));
    var bytes = new Uint8Array(bruto.length);
    for (var i = 0; i < bruto.length; i++) bytes[i] = bruto.charCodeAt(i);
    return bytes;
  }

  function escreverEstado(painel, texto) {
    var alvo = painel.querySelector("[data-push-estado]");
    if (alvo) alvo.textContent = texto;
  }

  function mostrar(painel, botoes) {
    ["ativar", "testar", "desativar"].forEach(function (nome) {
      var botao = painel.querySelector("[data-push-" + nome + "]");
      if (botao) botao.hidden = botoes.indexOf(nome) === -1;
    });
  }

  function atualizar(painel) {
    var chave = painel.dataset.chavePublica;
    if (!("PushManager" in window) || !("Notification" in window)) {
      if (ehIOS() && !instaladoNaTelaInicial()) {
        // Instrução útil: aparece até nas telas em que o painel começa escondido.
        escreverEstado(painel,
          "No iPhone, as notificações só funcionam com o site na Tela de Início. " +
          "Toque em Compartilhar, depois em Adicionar à Tela de Início, e abra o site pelo novo ícone.");
        painel.hidden = false;
      } else {
        escreverEstado(painel, "Este navegador não permite notificações. Use o Chrome (Android) ou o Safari (iPhone).");
      }
      mostrar(painel, []);
      return Promise.resolve();
    }
    if (!chave) {
      // Problema do servidor: só aparece em Preferências, não nas telas do dia a dia.
      escreverEstado(painel, "As notificações ainda não foram configuradas no servidor. Avise a recepção.");
      mostrar(painel, []);
      return Promise.resolve();
    }
    if (Notification.permission === "denied") {
      escreverEstado(painel,
        "As notificações estão bloqueadas para este site. Libere nas configurações do navegador " +
        "(ícone ao lado do endereço do site, depois Notificações) e recarregue a página.");
      mostrar(painel, []);  // quem bloqueou por escolha não é incomodado nas telas do dia a dia
      return Promise.resolve();
    }
    return registro
      .then(function (reg) { return reg.pushManager.getSubscription(); })
      .then(function (inscricao) {
        if (inscricao) {
          // Garante que o servidor conhece este aparelho (é idempotente).
          postarJSON(painel.dataset.urlInscrever, inscricao.toJSON());
          escreverEstado(painel, "Notificações ativadas neste aparelho.");
          mostrar(painel, ["testar", "desativar"]);
          if (painel.hasAttribute("data-ocultar-se-ativo")) painel.hidden = true;
        } else {
          escreverEstado(painel, "As notificações estão desligadas neste aparelho.");
          mostrar(painel, ["ativar"]);
          painel.hidden = false;
        }
      });
  }

  function ativar(painel) {
    escreverEstado(painel, "Aguardando sua permissão…");
    return Notification.requestPermission()
      .then(function (permissao) {
        if (permissao !== "granted") throw new Error("negada");
        return registro;
      })
      .then(function (reg) {
        return reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: chaveParaBytes(painel.dataset.chavePublica),
        });
      })
      .then(function (inscricao) { return postarJSON(painel.dataset.urlInscrever, inscricao.toJSON()); })
      .then(function (resposta) {
        if (!resposta.ok) throw new Error("servidor");
        painel.removeAttribute("data-ocultar-se-ativo"); // mantém visível para a pessoa ouvir o resultado
        return atualizar(painel);
      })
      .then(function () {
        if (window.Anunciador) window.Anunciador.anunciar("Notificações ativadas neste aparelho.");
      })
      .catch(function (erro) {
        if (erro && erro.message === "negada") {
          escreverEstado(painel, "Você não permitiu as notificações. Para ativar depois, libere nas configurações do navegador.");
        } else {
          escreverEstado(painel, "Não foi possível ativar agora. Tente de novo em instantes.");
        }
      });
  }

  function desativar(painel) {
    return registro
      .then(function (reg) { return reg.pushManager.getSubscription(); })
      .then(function (inscricao) {
        if (!inscricao) return;
        return postarJSON(painel.dataset.urlRemover, { endpoint: inscricao.endpoint }).then(function () {
          return inscricao.unsubscribe();
        });
      })
      .then(function () { return atualizar(painel); })
      .then(function () {
        if (window.Anunciador) window.Anunciador.anunciar("Notificações desativadas neste aparelho.");
      });
  }

  function testar(painel) {
    escreverEstado(painel, "Enviando notificação de teste…");
    return postarJSON(painel.dataset.urlTeste)
      .then(function (resposta) { return resposta.json(); })
      .then(function (resultado) {
        escreverEstado(painel, resultado.ok
          ? "Notificação de teste enviada. Ela deve aparecer em alguns segundos."
          : "A notificação não foi entregue: " + (resultado.erro || "erro desconhecido") + ".");
      })
      .catch(function () { escreverEstado(painel, "Não foi possível enviar o teste agora."); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-painel-push]").forEach(function (painel) {
      painel.querySelector("[data-push-ativar]").addEventListener("click", function () { ativar(painel); });
      painel.querySelector("[data-push-desativar]").addEventListener("click", function () { desativar(painel); });
      painel.querySelector("[data-push-testar]").addEventListener("click", function () { testar(painel); });
      atualizar(painel);
    });
  });
})();
