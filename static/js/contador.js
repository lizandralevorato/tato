/*
 * Contador de caracteres acessível.
 *
 * O texto visível ("Faltam 120 caracteres") muda a cada tecla, mas não é uma região
 * aria-live: o leitor de tela não fica falando a cada letra. Só avisa ao cruzar
 * 50, 20, 10 ou 0 caracteres restantes. Sem JS, o limite vale pelo atributo maxlength.
 */
(function () {
  "use strict";

  var LIMIARES = [50, 20, 10, 0];

  document.querySelectorAll("textarea[data-contador]").forEach(function (campo) {
    var visivel = document.getElementById(campo.dataset.contador);
    var aviso = document.getElementById(campo.dataset.contador + "-aviso");
    var limite = parseInt(campo.getAttribute("maxlength"), 10);
    if (!visivel || !limite) return;

    function texto(restam) {
      if (restam === 0) return "Limite de " + limite + " caracteres atingido.";
      return "Faltam " + restam + " caractere" + (restam === 1 ? "" : "s") + ".";
    }

    // Menor limiar já cruzado (ou null se ainda sobram mais de 50).
    function limiarDe(restam) {
      var cruzados = LIMIARES.filter(function (l) { return restam <= l; });
      return cruzados.length ? cruzados[cruzados.length - 1] : null;
    }

    function restantes() { return Math.max(limite - campo.value.length, 0); }

    var ultimo = limiarDe(restantes());
    visivel.textContent = texto(restantes());

    campo.addEventListener("input", function () {
      var restam = restantes();
      var limiar = limiarDe(restam);
      visivel.textContent = texto(restam);
      if (aviso && limiar !== null && limiar !== ultimo) aviso.textContent = texto(restam);
      ultimo = limiar;
    });
  });
})();
