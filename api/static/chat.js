"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { conversations: [], currentId: null, apiKey: "", busy: false, health: null };
  const routeNames = { preventa: "Preventa", postventa: "Postventa", generica: "Consulta general" };
  const stepNames = {
    router: "Clasifica tu mensaje",
    agente_preventa: "Agente de preventa",
    agente_postventa: "Agente de postventa",
    respuesta_generica: "Respuesta general",
    buscar_productos: "Busca en el catálogo",
    ver_producto: "Consulta un producto",
    mejores_ofertas: "Busca las mejores ofertas",
    consultar_redes: "Consulta redes sociales (A2A)",
    estado_pedido: "Consulta el pedido",
    politica: "Consulta las políticas",
    crear_reclamo: "Registra el reclamo",
  };
  const nodeNames = new Set(["router", "agente_preventa", "agente_postventa", "respuesta_generica"]);
  const clock = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });
  let toastTimer;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function icon(name, small = false) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", small ? "icon small" : "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }

  function current() {
    return state.conversations.find((conversation) => conversation.id === state.currentId);
  }

  function toast(text) {
    clearTimeout(toastTimer);
    $("toast").textContent = text;
    $("toast").hidden = false;
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3500);
  }

  function toggleTrace(open) {
    $("workspace").classList.toggle("show-trace", open);
    $("workspace").classList.remove("show-chats");
    $("trace-toggle").setAttribute("aria-expanded", String(open));
    $("chats-toggle").setAttribute("aria-expanded", "false");
  }

  function newConversation() {
    if (state.busy) return;
    const conversation = { id: `web-${crypto.randomUUID()}`, messages: [], selectedTrace: null, createdAt: Date.now() };
    state.conversations.unshift(conversation);
    state.currentId = conversation.id;
    $("message-input").value = "";
    $("workspace").classList.remove("show-chats");
    $("chats-toggle").setAttribute("aria-expanded", "false");
    render();
    $("message-input").focus();
  }

  function renderConversations() {
    const list = $("conversations");
    list.replaceChildren();
    for (const conversation of state.conversations) {
      const first = conversation.messages.find((message) => message.role === "user");
      const last = conversation.messages.at(-1);
      const button = element("button", `conversation${conversation.id === state.currentId ? " active" : ""}`);
      button.type = "button";
      button.disabled = state.busy;
      button.setAttribute("aria-current", String(conversation.id === state.currentId));
      const avatar = element("span", "conversation-avatar");
      avatar.append(icon("bot"));
      const copy = element("span", "conversation-copy");
      copy.append(element("span", "conversation-title", first?.text || "Nueva conversación"));
      copy.append(element("span", "conversation-preview", last?.text || "¿En qué puedo ayudarte hoy?"));
      button.append(avatar, copy, element("span", "conversation-time", clock.format(last?.time || conversation.createdAt)));
      button.addEventListener("click", () => {
        state.currentId = conversation.id;
        $("workspace").classList.remove("show-chats");
        $("chats-toggle").setAttribute("aria-expanded", "false");
        $("message-input").value = "";
        render();
      });
      list.append(button);
    }
  }

  function routeBadge(route) {
    const badge = element("span", "route-badge", routeNames[route] || route);
    badge.dataset.route = route;
    return badge;
  }

  // Nunca interpretar la salida del modelo como HTML. Solo enlazar URLs HTTP(S).
  function appendText(node, text) {
    const pattern = /https?:\/\/[^\s<>]+/g;
    let start = 0;
    for (const match of text.matchAll(pattern)) {
      node.append(document.createTextNode(text.slice(start, match.index)));
      const url = match[0].replace(/[),.;!?\]]+$/, "");
      const link = element("a", "", url);
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      node.append(link);
      start = match.index + url.length;
    }
    node.append(document.createTextNode(text.slice(start)));
  }

  function renderMessages() {
    const conversation = current();
    $("welcome").hidden = conversation.messages.length > 0;
    const list = $("messages");
    list.replaceChildren();
    for (const message of conversation.messages) {
      if (message.role === "error") {
        list.append(element("div", "message error", message.text));
        continue;
      }
      const article = element("article", `message ${message.role}`);
      if (message.role === "assistant") article.append(element("div", "message-author", "Asistente de la tienda"));
      const bubble = element("div", "bubble");
      const text = element("p", "bubble-text");
      appendText(text, message.text);
      bubble.append(text);
      const meta = element("div", "message-meta");
      meta.append(element("time", "", clock.format(message.time)));
      if (message.role === "user" && message.delivered) meta.append(icon("check", true));
      bubble.append(meta);
      article.append(bubble);
      if (message.role === "assistant") {
        const footer = element("div", "message-trace");
        const button = element("button", "jump-button");
        button.type = "button";
        button.append(icon("route", true), document.createTextNode(`Ver ${message.saltos.length} saltos`));
        button.addEventListener("click", () => {
          conversation.selectedTrace = message.id;
          renderTrace();
          toggleTrace(true);
        });
        footer.append(routeBadge(message.ruta), button);
        article.append(footer);
      }
      list.append(article);
    }
    if (state.busy) {
      const article = element("article", "message assistant");
      article.append(element("div", "message-author", "Tu agente está respondiendo…"));
      const bubble = element("div", "bubble");
      const typing = element("div", "typing");
      typing.setAttribute("role", "status");
      typing.setAttribute("aria-label", "Esperando respuesta del agente");
      typing.append(element("span"), element("span"), element("span"));
      bubble.append(typing);
      article.append(bubble);
      list.append(article);
    }
    $("message-area").scrollTop = $("message-area").scrollHeight;
  }

  function renderTrace() {
    const conversation = current();
    const message = conversation.messages.find((item) => item.id === conversation.selectedTrace);
    const panel = $("trace-content");
    panel.replaceChildren();
    if (state.busy || !message) {
      const empty = element("div", "trace-empty");
      const illustration = element("div", "trace-empty-icon");
      illustration.append(icon("route"));
      empty.append(illustration);
      empty.append(element("h3", "", state.busy ? "Tu agente está trabajando" : "Cada mensaje tiene su camino"));
      empty.append(element("p", "", state.busy
        ? "Al terminar verás los nodos y herramientas registrados para esta respuesta."
        : "Envía un mensaje y descubre qué ruta toma tu agente para ayudarte."));
      const example = element("div", "trace-example");
      example.append(element("span", "", "mensaje"), icon("arrow", true), element("span", "", "router"), icon("arrow", true), element("span", "", "agente"));
      empty.append(example);
      panel.append(empty);
    } else {
      const summary = element("div", "trace-summary");
      summary.append(routeBadge(message.ruta), element("span", "", `${(message.duration / 1000).toFixed(1)} s · ${message.saltos.length} saltos`));
      panel.append(summary, element("div", "trace-label", "MOTIVO DE LA RUTA"), element("p", "trace-reason", message.motivo));
      const timeline = element("ol", "timeline");
      message.saltos.forEach((name, index) => {
        const step = element("li");
        const copy = element("div", "step-copy");
        copy.append(element("strong", "", stepNames[name] || name), element("code", "", name));
        const stepType = name === "consultar_redes" ? "AGENTE EXTERNO · A2A" : nodeNames.has(name) ? "NODO DEL GRAFO" : "HERRAMIENTA";
        copy.append(element("span", "step-type", stepType));
        step.append(element("span", "step-number", String(index + 1).padStart(2, "0")), copy);
        timeline.append(step);
      });
      panel.append(timeline);
      if (!message.saltos.length) panel.append(element("p", "trace-reason", "Esta respuesta no incluye saltos registrados."));
      const finish = element("div", "trace-finish");
      finish.append(icon("check", true), document.createTextNode("Respuesta entregada"));
      panel.append(finish);
    }
    panel.append(element("div", "trace-label", "HILO DE CONVERSACIÓN"), element("code", "thread-id", conversation.id));
  }

  function updateComposer() {
    const input = $("message-input");
    $("send-button").disabled = state.busy || !input.value.trim();
    $("new-chat").disabled = state.busy;
    input.disabled = state.busy;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }

  function render() {
    renderConversations();
    renderMessages();
    renderTrace();
    updateComposer();
  }

  function showSettings() {
    $("api-key").value = "";
    $("api-key").required = !state.apiKey;
    $("api-key").placeholder = state.apiKey ? "Introduce otra clave para reemplazarla" : "Tu API_KEY";
    if (!$("settings-dialog").open) $("settings-dialog").showModal();
  }

  async function sendMessage(event) {
    event.preventDefault();
    const text = $("message-input").value.trim();
    if (!text || state.busy) return;
    if (!state.apiKey) {
      showSettings();
      return;
    }
    const conversation = current();
    const userMessage = { role: "user", text, time: Date.now(), delivered: false };
    conversation.messages.push(userMessage);
    state.busy = true;
    $("message-input").value = "";
    render();
    const started = performance.now();
    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": state.apiKey },
        body: JSON.stringify({ user_id: conversation.id, texto: text }),
        cache: "no-store",
        redirect: "error",
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          state.apiKey = "";
          $("key-status").textContent = "La clave no es válida. Revisa API_KEY.";
          showSettings();
        }
        throw new Error(typeof data.detail === "string" ? data.detail : `La API respondió con error ${response.status}.`);
      }
      const message = {
        id: crypto.randomUUID(), role: "assistant", text: data.respuesta,
        ruta: data.ruta, motivo: data.motivo, saltos: Array.isArray(data.saltos) ? data.saltos : [],
        time: Date.now(), duration: performance.now() - started,
      };
      userMessage.delivered = true;
      conversation.messages.push(message);
      conversation.selectedTrace = message.id;
    } catch (error) {
      conversation.selectedTrace = null;
      const detail = error instanceof TypeError ? "No se pudo conectar con el servidor. Comprueba que sigue encendido." : error.message;
      conversation.messages.push({ role: "error", text: `${detail} Tu mensaje no se reenvió automáticamente.`, time: Date.now() });
      $("message-input").value = text;
    } finally {
      state.busy = false;
      render();
      if (!$("settings-dialog").open) $("message-input").focus();
    }
  }

  async function checkHealth() {
    try {
      const response = await fetch("/health", { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!response.ok) throw new Error("API no disponible");
      state.health = await response.json();
      $("connection-status").textContent = "En línea · Preventa, postventa y consultas";
      $("connection-status").title = `Modelo: ${state.health.modelo}`;
      $("memory-label").textContent = state.health.memoria === "postgres" ? "Memoria en Postgres" : "Memoria temporal · RAM";
      $("memory-dot").dataset.mode = state.health.memoria;
      $("memory-label").title = state.health.memoria === "postgres" ? "El historial del agente persiste entre reinicios." : "El historial del agente se pierde al reiniciar el servidor.";
      $("connection-error").hidden = true;
    } catch {
      $("connection-status").textContent = "Sin conexión con el servidor";
      $("memory-label").textContent = "Sin conexión";
      $("connection-error").textContent = "El servidor no responde. Comprueba la conexión antes de enviar.";
      $("connection-error").hidden = false;
    }
  }

  $("new-chat").addEventListener("click", newConversation);
  $("message-form").addEventListener("submit", sendMessage);
  $("message-input").addEventListener("input", updateComposer);
  $("message-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $("message-form").requestSubmit();
    }
  });
  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      $("message-input").value = button.dataset.suggestion;
      updateComposer();
      $("message-input").focus();
    });
  });
  $("trace-toggle").addEventListener("click", () => toggleTrace(!$("workspace").classList.contains("show-trace")));
  $("close-trace").addEventListener("click", () => toggleTrace(false));
  $("screen-overlay").addEventListener("click", () => toggleTrace(false));
  $("chats-toggle").addEventListener("click", () => {
    toggleTrace(false);
    const open = $("workspace").classList.toggle("show-chats");
    $("chats-toggle").setAttribute("aria-expanded", String(open));
  });
  $("settings-button").addEventListener("click", showSettings);
  $("close-settings").addEventListener("click", () => $("settings-dialog").close());
  $("settings-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const key = $("api-key").value.trim();
    if (key) state.apiKey = key;
    if (!state.apiKey) return;
    $("api-key").value = "";
    $("settings-dialog").close();
    $("key-status").textContent = "Clave configurada en esta pestaña";
    toast("Acceso configurado. Ya puedes enviar tu mensaje.");
    $("message-input").focus();
  });
  $("settings-dialog").addEventListener("close", () => { $("api-key").value = ""; });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("settings-dialog").open) toggleTrace(false);
  });
  if (matchMedia("(max-width: 1200px)").matches) toggleTrace(false);
  newConversation();
  checkHealth();
  setInterval(checkHealth, 30000);
})();
