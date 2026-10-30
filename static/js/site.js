// Troca o idioma assim que a pessoa escolhe na lista
document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("language-select");
  if (select) {
    select.addEventListener("change", () => select.form.submit());
  }

  // Menu lateral no celular/tablet: abre e fecha pelo botão, pelo fundo escuro ou pela tecla Esc
  const toggle = document.querySelector(".menu-toggle");
  const backdrop = document.querySelector(".sidebar-backdrop");
  const setMenu = (open) => {
    document.body.classList.toggle("nav-open", open);
    toggle?.setAttribute("aria-expanded", String(open));
    if (backdrop) backdrop.hidden = !open;
  };
  toggle?.addEventListener("click", () => setMenu(!document.body.classList.contains("nav-open")));
  backdrop?.addEventListener("click", () => setMenu(false));

  // Menu do perfil fecha ao clicar fora
  const userMenu = document.querySelector(".user-menu");
  document.addEventListener("click", (event) => {
    if (userMenu?.open && !userMenu.contains(event.target)) userMenu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    setMenu(false);
    if (userMenu?.open) {
      userMenu.open = false;
      userMenu.querySelector("summary")?.focus();
    }
  });
});
