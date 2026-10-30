{% load static %}/*
 * Service worker do TATO (versão {{ versao }}).
 *
 *  - Recebe as notificações (Web Push) e mostra com texto completo, vibração e
 *    botões "Fazer check-in / Não vou" nos lembretes. TalkBack e VoiceOver leem a notificação.
 *  - Se o site estiver aberto e visível, não duplica: repassa o aviso para a
 *    página, que anuncia pelo leitor de tela / voz e atualiza a agenda na hora.
 *  - Sem internet, mostra uma página explicando em vez de um erro do navegador.
 */
"use strict";

const VERSAO = "{{ versao|escapejs }}";
const CACHE = "massagem-" + VERSAO;
const PAGINA_OFFLINE = "{% url 'notificacoes:offline' %}";
const ESSENCIAIS = [
  PAGINA_OFFLINE,
  "{% static 'css/tokens.css' %}",
  "{% static 'css/base.css' %}",
  "{% static 'css/componentes.css' %}",
  "{% static 'img/icone.svg' %}",
];
const ICONE = "{% static 'img/icone-192.png' %}";
const EMBLEMA = "{% static 'img/emblema-96.png' %}";

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ESSENCIAIS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim())
  );
});

// Sempre busca da rede (a agenda precisa estar atualizada); o cache é só plano B.
self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET" || new URL(pedido.url).origin !== self.location.origin) return;
  if (pedido.mode === "navigate") {
    evento.respondWith(fetch(pedido).catch(() => caches.match(PAGINA_OFFLINE)));
    return;
  }
  if (ESSENCIAIS.includes(new URL(pedido.url).pathname)) {
    evento.respondWith(fetch(pedido).catch(() => caches.match(pedido)));
  }
});

self.addEventListener("push", (evento) => {
  let dados = {};
  try { dados = evento.data ? evento.data.json() : {}; } catch (e) { dados = { corpo: evento.data && evento.data.text() }; }
  const titulo = dados.titulo || "TATO";

  evento.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
      const visiveis = janelas.filter((j) => j.visibilityState === "visible");
      // Avisos com botões (check-in) sempre viram notificação.
      if (visiveis.length && !(dados.acoes || []).length) {
        visiveis.forEach((j) => j.postMessage(Object.assign({ origem: "aviso-push" }, dados)));
        return;
      }
      return self.registration.showNotification(titulo, {
        body: dados.corpo || "",
        lang: "pt-BR",
        dir: "ltr",
        icon: ICONE,
        badge: EMBLEMA,
        tag: dados.tag,
        renotify: Boolean(dados.tag),
        requireInteraction: Boolean(dados.urgente || (dados.acoes || []).length),
        vibrate: dados.vibrar || [],
        silent: Boolean(dados.silencioso),
        data: dados,
        actions: (dados.acoes || []).map((a) => ({ action: a.id, title: a.titulo })),
      });
    })
  );
});

self.addEventListener("notificationclick", (evento) => {
  const notificacao = evento.notification;
  const dados = notificacao.data || {};
  notificacao.close();

  const acao = (dados.acoes || []).find((a) => a.id === evento.action);
  if (acao) {
    evento.waitUntil(responderLembrete(acao, dados));
    return;
  }
  evento.waitUntil(abrir(dados.url || "/"));
});

function responderLembrete(acao, dados) {
  return fetch(acao.url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
    body: "acao=" + encodeURIComponent(acao.id),
  })
    .then((r) => r.json())
    .catch(() => ({ ok: false, mensagem: "Sem conexão. Abra o site para responder." }))
    .then((resultado) =>
      self.registration.showNotification(resultado.ok ? "Pronto" : "Não foi possível", {
        body: resultado.mensagem,
        lang: "pt-BR",
        icon: ICONE,
        badge: EMBLEMA,
        tag: dados.tag,
        data: { url: resultado.ok ? "/" : acao.url },
      })
    );
}

function abrir(url) {
  const destino = new URL(url, self.location.origin);
  return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((janelas) => {
    const mesma = janelas.find((j) => new URL(j.url).pathname === destino.pathname);
    if (mesma) return mesma.focus();
    const qualquer = janelas.find((j) => "navigate" in j);
    if (qualquer) return qualquer.navigate(destino.href).then((j) => j && j.focus());
    return self.clients.openWindow(destino.href);
  });
}
