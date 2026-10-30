// Sugestões de tags canônicas enquanto a pessoa digita.
// data-tag-autocomplete="<tipo>"; com data-tag-multiple, completa só o trecho depois da última vírgula.
(() => {
  const URL_BASE = "/tags/autocompletar/";
  let counter = 0;

  function setup(input) {
    const multiple = input.hasAttribute("data-tag-multiple");
    const list = document.createElement("ul");
    list.className = "autocomplete-list";
    list.id = `autocomplete-${++counter}`;
    list.setAttribute("role", "listbox");
    list.hidden = true;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);
    input.parentElement.classList.add("autocomplete-wrap");
    input.after(list);

    let timer = null;
    let active = -1;
    let items = [];

    const currentTerm = () => (multiple ? input.value.split(",").pop() : input.value).trim();

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function choose(name) {
      if (multiple) {
        const parts = input.value.split(",");
        parts[parts.length - 1] = ` ${name}`;
        input.value = `${parts.join(",").replace(/^\s+/, "")}, `;
      } else {
        input.value = name;
      }
      close();
      input.focus();
    }

    function highlight(index) {
      items.forEach((item, i) => item.setAttribute("aria-selected", String(i === index)));
      active = index;
      if (items[index]) input.setAttribute("aria-activedescendant", items[index].id);
    }

    function render(names) {
      list.replaceChildren();
      items = names.map((name, i) => {
        const item = document.createElement("li");
        item.id = `${list.id}-${i}`;
        item.setAttribute("role", "option");
        item.textContent = name;
        item.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(name);
        });
        list.append(item);
        return item;
      });
      list.hidden = items.length === 0;
      input.setAttribute("aria-expanded", String(!list.hidden));
      active = -1;
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      const term = currentTerm();
      if (term.length < 2) return close();
      timer = setTimeout(async () => {
        const params = new URLSearchParams({ q: term, tipo: input.dataset.tagAutocomplete });
        const response = await fetch(`${URL_BASE}?${params}`);
        if (response.ok) render((await response.json()).results);
      }, 200);
    });

    input.addEventListener("keydown", (event) => {
      if (list.hidden) return;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        highlight(Math.min(active + 1, items.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        highlight(Math.max(active - 1, 0));
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        choose(items[active].textContent);
      } else if (event.key === "Escape") {
        close();
      }
    });

    input.addEventListener("blur", () => setTimeout(close, 100));
  }

  document.querySelectorAll("[data-tag-autocomplete]").forEach(setup);
})();
