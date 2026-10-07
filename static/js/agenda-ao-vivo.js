/*
 * Agenda ao vivo do massoterapeuta.
 *
 * A cada 20 s consulta um JSON pequeno. Se algo mudou (novo agendamento,
 * chegada, cancelamento), anuncia a mudança e atualiza a lista SEM tirar o
 * foco de onde a pessoa está (essencial para quem usa leitor de tela).
 * Também avisa quando o próximo atendimento está a 5 minutos.
 */
(function () {
  "use strict";

  var INTERVALO_MS = 20000;
  var AVISO_ANTES_MIN = 5;

  var container = document.getElementById("agenda-ao-vivo");
  var estadoInicial = document.getElementById("estado-inicial");
  if (!container || !estadoInicial || !window.fetch) return;

  var dados = JSON.parse(estadoInicial.textContent);
  var versao = dados.versao;
  var anteriores = mapear(dados.itens);
  var jaAvisados = {};

  function mapear(itens) {
    var mapa = {};
    itens.forEach(function (item) { mapa[item.id] = item; });
    return mapa;
  }

  function diferencas(antes, itens) {
    var avisos = [];
    itens.forEach(function (item) {
      var antigo = antes[item.id];
      if (!antigo) {
        if (item.status !== "cancelado" && item.status !== "expirado") {
          avisos.push({ texto: "Novo agendamento: " + item.hora + ", " + item.nome + ".", tipo: "info" });
        }
        return;
      }
      if (antigo.status === item.status) return;
      if (item.status === "chegou") {
        avisos.push({ texto: item.nome + " chegou. Atendimento das " + item.hora + ".", tipo: "chegada", urgente: true });
      } else if (item.status === "cancelado") {
        avisos.push({ texto: "Cancelado: " + item.hora + ", " + item.nome + ". O horário ficou livre.", tipo: "cancelamento", urgente: true });
      } else if (item.status === "expirado") {
        avisos.push({ texto: "Liberado: " + item.hora + ", " + item.nome + " não fez check-in. O horário está livre.", tipo: "cancelamento", urgente: true });
      } else if (item.status === "confirmado") {
        avisos.push({ texto: item.nome + " fez check-in para as " + item.hora + ".", tipo: "info" });
      }
    });
    return avisos;
  }

  function avisarProximo(itens) {
    var agora = Date.now();
    itens.forEach(function (item) {
      if (["agendado", "confirmado"].indexOf(item.status) === -1 || jaAvisados[item.id]) return;
      var minutos = (new Date(item.inicio).getTime() - agora) / 60000;
      if (minutos > 0 && minutos <= AVISO_ANTES_MIN) {
        jaAvisados[item.id] = true;
        window.Anunciador.anunciar(
          "Próximo atendimento em " + Math.ceil(minutos) + " minutos: " + item.hora + ", " + item.nome + ".",
          { tipo: "alerta" }
        );
      }
    });
  }

  function atualizarTela() {
    var focado = document.activeElement;
    var idFocado = focado && container.contains(focado) ? focado.id : null;
    return fetch(container.dataset.urlParcial, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (htmlNovo) {
        if (htmlNovo === null) return;
        container.innerHTML = htmlNovo;
        if (idFocado) {
          var alvo = document.getElementById(idFocado) || container.querySelector("h2");
          if (alvo) {
            if (!alvo.hasAttribute("tabindex") && alvo.tagName === "H2") alvo.setAttribute("tabindex", "-1");
            alvo.focus();
          }
        }
      });
  }

  function verificar() {
    fetch(container.dataset.urlEstado, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (novo) {
        if (!novo) return;
        var avisos = diferencas(anteriores, novo.itens);
        var mudou = novo.versao !== versao;
        anteriores = mapear(novo.itens);
        versao = novo.versao;
        var atualizacao = mudou ? atualizarTela() : Promise.resolve();
        return atualizacao.then(function () {
          avisos.forEach(function (a) { window.Anunciador.anunciar(a.texto, a); });
          avisarProximo(novo.itens);
        });
      })
      .catch(function () { /* sem conexão: tenta de novo no próximo ciclo */ });
  }

  // Mantém "começa em X minutos" atualizado entre uma consulta e outra.
  function atualizarContagens() {
    container.querySelectorAll("[data-contagem]").forEach(function (el) {
      var minutos = Math.floor((new Date(el.dataset.contagem).getTime() - Date.now()) / 60000);
      if (minutos <= 0) { el.textContent = "agora"; return; }
      var horas = Math.floor(minutos / 60), resto = minutos % 60, partes = [];
      if (horas) partes.push(horas + (horas > 1 ? " horas" : " hora"));
      if (resto) partes.push(resto + (resto > 1 ? " minutos" : " minuto"));
      el.textContent = "em " + partes.join(" e ");
    });
  }

  window.setInterval(verificar, INTERVALO_MS);
  window.setInterval(atualizarContagens, 30000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) verificar(); });
  // Notificação chegou com a tela aberta: atualiza e anuncia na hora, sem esperar o próximo ciclo.
  document.addEventListener("aviso-push", verificar);
  avisarProximo(dados.itens);
})();
