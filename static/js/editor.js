// Editor de texto com duas abas, como no AO3: "Texto formatado" (visual) e "HTML".
// Vale para toda caixa com data-editor (capítulo, resumo e notas). O servidor filtra o HTML de qualquer jeito.
(() => {
  const labelsElement = document.getElementById("editor-labels");
  const labels = labelsElement ? JSON.parse(labelsElement.textContent) || {} : {};
  const STORAGE_KEY = "arquivo-editor-mode"; // lembra a aba preferida neste navegador
  let counter = 0;

  const exec = (command, value = null) => document.execCommand(command, false, value);

  const escapeAttr = (text) =>
    text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  function savedMode() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "html" ? "html" : "visual";
    } catch {
      return "visual";
    }
  }

  function saveMode(mode) {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* navegador sem armazenamento: só não lembra */
    }
  }

  function setupEditor(textarea) {
    const id = ++counter;
    // A caixa do capítulo já vem dentro de .editor-host; resumo e notas ganham um agora
    let host = textarea.closest(".editor-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "editor-host";
      textarea.before(host);
      host.append(textarea);
    }
    const small = textarea.dataset.editor === "small";
    if (small) host.classList.add("editor-small");
    const form = textarea.form;
    const uploadUrl = host.dataset.uploadUrl;

    // Abas
    const tabs = document.createElement("div");
    tabs.className = "editor-tabs";
    tabs.setAttribute("role", "tablist");
    const makeTab = (mode, text) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.id = `editor-${id}-tab-${mode}`;
      tab.textContent = text;
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", () => setMode(mode, true));
      tabs.append(tab);
      return tab;
    };
    const visualTab = makeTab("visual", labels.visual || "Texto formatado");
    const htmlTab = makeTab("html", labels.html || "HTML");

    const toolbar = document.createElement("div");
    toolbar.className = "editor-toolbar";
    toolbar.setAttribute("role", "toolbar");

    const area = document.createElement("div");
    area.className = "editor-area userstuff";
    area.contentEditable = "true";
    area.setAttribute("role", "textbox");
    area.setAttribute("aria-multiline", "true");
    const label = document.querySelector(`label[for="${textarea.id}"]`);
    if (label) area.setAttribute("aria-label", label.textContent.trim());
    area.innerHTML = textarea.value;

    const status = document.createElement("span");
    status.className = "editor-status";
    status.setAttribute("role", "status");

    let mode = "visual";
    let savedRange = null;

    function addButton(title, text, action) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.title = title || text;
      button.setAttribute("aria-label", title || text);
      // Não deixa o clique tirar a seleção do texto
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        area.focus();
        action();
      });
      toolbar.append(button);
    }

    function saveSelection() {
      const selection = window.getSelection();
      savedRange =
        selection.rangeCount && area.contains(selection.anchorNode) ? selection.getRangeAt(0).cloneRange() : null;
    }

    function restoreSelection() {
      area.focus();
      const selection = window.getSelection();
      selection.removeAllRanges();
      if (savedRange) {
        selection.addRange(savedRange);
      } else {
        const range = document.createRange();
        range.selectNodeContents(area);
        range.collapse(false);
        selection.addRange(range);
      }
    }

    function pickImage() {
      saveSelection();
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.addEventListener("change", async () => {
        const file = input.files[0];
        if (!file) return;
        const alt = window.prompt(labels.image_alt, "") ?? "";
        const data = new FormData();
        data.append("image", file);
        status.textContent = labels.uploading;
        try {
          const response = await fetch(uploadUrl, {
            method: "POST",
            body: data,
            credentials: "same-origin",
            headers: { "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
          });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || labels.upload_error);
          restoreSelection();
          exec(
            "insertHTML",
            `<img src="${escapeAttr(result.url)}" alt="${escapeAttr(alt)}" width="${result.width}" height="${result.height}">`
          );
        } catch (error) {
          window.alert(error.message || labels.upload_error);
        } finally {
          status.textContent = "";
        }
      });
      input.click();
    }

    function setMode(next, remember) {
      if (next === mode && remember) return;
      if (next === "html") {
        if (mode === "visual") textarea.value = area.innerHTML;
      } else if (mode === "html") {
        area.innerHTML = textarea.value;
      }
      mode = next;
      const html = mode === "html";
      area.hidden = html;
      toolbar.hidden = html;
      textarea.hidden = !html;
      visualTab.setAttribute("aria-selected", String(!html));
      htmlTab.setAttribute("aria-selected", String(html));
      visualTab.classList.toggle("is-active", !html);
      htmlTab.classList.toggle("is-active", html);
      if (remember) saveMode(mode);
    }

    addButton(labels.bold, "B", () => exec("bold"));
    addButton(labels.italic, "I", () => exec("italic"));
    addButton(labels.underline, "U", () => exec("underline"));
    addButton(labels.strike, "S", () => exec("strikeThrough"));
    if (!small) addButton(labels.heading, "H", () => exec("formatBlock", "<h3>"));
    addButton(labels.paragraph, "¶", () => exec("formatBlock", "<p>"));
    addButton(labels.quote, "❝", () => exec("formatBlock", "<blockquote>"));
    addButton(labels.bullets, "•", () => exec("insertUnorderedList"));
    addButton(labels.numbers, "1.", () => exec("insertOrderedList"));
    addButton(labels.link, "🔗", () => {
      const url = window.prompt(labels.link_prompt, "https://");
      if (url && /^(https?:|mailto:)/i.test(url)) exec("createLink", url);
    });
    if (!small) addButton(labels.rule, "—", () => exec("insertHorizontalRule"));
    if (uploadUrl) addButton(labels.image, "🖼", pickImage);
    toolbar.append(status);

    host.prepend(tabs, toolbar);
    textarea.before(area);
    setMode(savedMode(), false);

    form.addEventListener("submit", () => {
      if (mode === "visual") textarea.value = area.innerHTML;
    });
  }

  // Enter cria <p> em vez de <div>
  document.execCommand("defaultParagraphSeparator", false, "p");
  document.querySelectorAll("textarea[data-editor]").forEach(setupEditor);
})();
