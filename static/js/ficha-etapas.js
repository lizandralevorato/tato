/*
 * Ficha de saúde em etapas.
 *
 * Sem este arquivo, as três etapas aparecem na mesma página e o formulário funciona
 * normalmente. Com ele, mostra uma etapa por vez, move o foco para o título da etapa,
 * anuncia "Etapa 2 de 3" e só mostra intensidade e frequência das regiões marcadas.
 */
(function () {
  "use strict";

  var form = document.querySelector("[data-ficha-etapas]");
  if (!form) return;

  var etapas = Array.prototype.slice.call(form.querySelectorAll("[data-etapa]"));
  var controles = form.querySelector("[data-etapas-controles]");
  var enviar = form.querySelector("[data-etapas-enviar]");
  var voltar = form.querySelector("[data-etapa-voltar]");
  var proxima = form.querySelector("[data-etapa-proxima]");
  var regiaoAviso = document.getElementById("anuncio-educado");
  var atual = 0;

  function titulo(etapa) { return etapa.querySelector("h2"); }

  function mostrar(indice, mover) {
    atual = Math.max(0, Math.min(indice, etapas.length - 1));
    etapas.forEach(function (etapa, i) { etapa.hidden = i !== atual; });
    voltar.hidden = atual === 0;
    proxima.hidden = atual === etapas.length - 1;
    enviar.hidden = atual !== etapas.length - 1;
    if (mover) {
      var h2 = titulo(etapas[atual]);
      // Sem rolagem animada: a página pula direto para o topo da nova etapa (o CSS usa rolagem suave).
      h2.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
      if (regiaoAviso) {
        regiaoAviso.textContent = "";
        window.setTimeout(function () { regiaoAviso.textContent = h2.textContent; }, 100);
      }
    }
  }

  function etapaDe(elemento) {
    for (var i = 0; i < etapas.length; i++) if (etapas[i].contains(elemento)) return i;
    return -1;
  }

  // Intensidade e frequência só aparecem para a região marcada (sem JS aparecem todas).
  // aria-controls liga a caixa ao bloco; aria-expanded não existe para caixas de marcar (checkbox).
  function ligarRegiao(bloco) {
    var caixa = bloco.querySelector("input[type=checkbox]");
    var detalhes = bloco.querySelector("[data-regiao-detalhes]");
    if (!caixa || !detalhes) return;
    caixa.setAttribute("aria-controls", detalhes.id);
    function atualizar() { detalhes.hidden = !caixa.checked; }
    caixa.addEventListener("change", atualizar);
    atualizar();
  }
  form.querySelectorAll("[data-regiao]").forEach(ligarRegiao);

  controles.hidden = false;
  voltar.addEventListener("click", function () { mostrar(atual - 1, true); });
  proxima.addEventListener("click", function () { mostrar(atual + 1, true); });

  // Com erro, abre a etapa do primeiro problema. Os links do resumo de erros também abrem a etapa certa.
  var comErro = form.querySelector("[aria-invalid=true], .erro-campo");
  mostrar(comErro ? Math.max(etapaDe(comErro), 0) : 0, false);

  document.addEventListener("click", function (evento) {
    var link = evento.target.closest && evento.target.closest(".resumo-erros a[href^='#']");
    if (!link) return;
    var alvo = document.getElementById(link.getAttribute("href").slice(1));
    var indice = alvo ? etapaDe(alvo) : -1;
    if (indice < 0) return;
    evento.preventDefault();
    mostrar(indice, false);
    alvo.focus();
  });
})();
