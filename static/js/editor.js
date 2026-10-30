// Editor de texto: modo visual (contenteditable) e modo HTML (textarea).
// O servidor filtra o HTML de qualquer jeito; aqui é só conforto para quem escreve.
(() => {
  const labelsElement = document.getElementById("editor-labels");
  const labels = labelsElement ? JSON.parse(labelsElement.textContent) : {};

  const exec = (command, value = null) => document.execCommand(command, false, value);

  const escapeAttr = (text) =>
    text.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

  function setupEditor(host) {
    const textarea = host.querySelector("textarea");
    if (!textarea) return;
    const form = textarea.form;
    const uploadUrl = host.dataset.uploadUrl;

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

    let htmlMode = false;
    let savedRange = null;
    const formatButtons = [];

    function addButton(title, text, action, isFormat = true) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.title = title;
      button.setAttribute("aria-label", title);
      // Não deixa o clique tirar a seleção do texto
      button.addEventListener("mousedown", (event) => event.preventDefault());
      button.addEventListener("click", () => {
        if (isFormat) area.focus();
        action();
      });
      toolbar.append(button);
      if (isFormat) formatButtons.push(button);
      return button;
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

    function toggleMode() {
      if (htmlMode) {
        area.innerHTML = textarea.value;
        toggle.textContent = labels.html;
      } else {
        textarea.value = area.innerHTML;
        toggle.textContent = labels.visual;
      }
      htmlMode = !htmlMode;
      area.hidden = htmlMode;
      textarea.hidden = !htmlMode;
      toggle.setAttribute("aria-pressed", String(htmlMode));
      formatButtons.forEach((button) => (button.disabled = htmlMode));
    }

    addButton(labels.bold, "B", () => exec("bold"));
    addButton(labels.italic, "I", () => exec("italic"));
    addButton(labels.underline, "U", () => exec("underline"));
    addButton(labels.strike, "S", () => exec("strikeThrough"));
    addButton(labels.heading, "H", () => exec("formatBlock", "<h3>"));
    addButton(labels.paragraph, "¶", () => exec("formatBlock", "<p>"));
    addButton(labels.quote, "❝", () => exec("formatBlock", "<blockquote>"));
    addButton(labels.bullets, "•", () => exec("insertUnorderedList"));
    addButton(labels.numbers, "1.", () => exec("insertOrderedList"));
    addButton(labels.link, "🔗", () => {
      const url = window.prompt(labels.link_prompt, "https://");
      if (url && /^(https?:|mailto:)/i.test(url)) exec("createLink", url);
    });
    addButton(labels.rule, "—", () => exec("insertHorizontalRule"));
    if (uploadUrl) addButton(labels.image, "🖼", pickImage);
    const toggle = addButton(labels.html, labels.html, toggleMode, false);
    toggle.classList.add("editor-toggle");
    toggle.setAttribute("aria-pressed", "false");
    toolbar.append(status);

    host.prepend(toolbar);
    textarea.before(area);
    textarea.hidden = true;

    form.addEventListener("submit", () => {
      if (!htmlMode) textarea.value = area.innerHTML;
    });
  }

  // Enter cria <p> em vez de <div>
  document.execCommand("defaultParagraphSeparator", false, "p");
  document.querySelectorAll(".editor-host").forEach(setupEditor);
})();
