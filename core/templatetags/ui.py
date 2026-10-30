from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince

register = template.Library()

# Ícones de traço fino (24×24), desenhados no estilo do mockup
ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/>',
    "file": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>'
    '<path d="M9 3v6l1.5-1L12 9V3"/>',
    "file-text": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>'
    '<path d="M8.5 13h7M8.5 16.5h7M8.5 9.5h2"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 19.5a6 6 0 0 1 12 0"/><path d="M15.5 4.9a3.2 3.2 0 0 1 0 6.2"/>'
    '<path d="M17.5 13.6a6 6 0 0 1 3.5 5.9"/>',
    "book": '<path d="M12 6.5C10.5 5 8 4 3 4v14c5 0 7.5 1 9 2.5 1.5-1.5 4-2.5 9-2.5V4c-5 0-7.5 1-9 2.5z"/>'
    '<path d="M12 6.5v14"/>',
    "tag": '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "user": '<circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="10" r="3.2"/><path d="M6.4 18.3a7 7 0 0 1 11.2 0"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.6h.01"/>',
    "terms": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M8.5 8h7M8.5 12h7M8.5 16h4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3.5 7 8.5 6 8.5-6"/>',
    "heart": '<path d="M12 20s-7-4.4-9-9a4.8 4.8 0 0 1 9-3 4.8 4.8 0 0 1 9 3c-2 4.6-9 9-9 9z"/>',
    "sparkles": '<path d="M11 3l1.8 5.2L18 10l-5.2 1.8L11 17l-1.8-5.2L4 10l5.2-1.8z"/>'
    '<path d="M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15.6 8.4-2.2 5-5 2.2 2.2-5z"/>',
    "library": '<rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M8 7.5v9M10.7 7.5v9M13.3 7.5v9"/>'
    '<path d="m15.6 7.8 1.6 8.6"/><path d="M4 18.5h16"/>',
    "tags": '<path d="M3 11V4a1 1 0 0 1 1-1h7l8.5 8.5-7.5 7.5z"/><circle cx="7" cy="7" r="1.3"/>'
    '<path d="m14 3 7.5 7.5a1.5 1.5 0 0 1 0 2.1L16 18"/>',
    "flame": '<path d="M12 21c4 0 7-2.7 7-6.5 0-3.3-2.2-5.4-3.5-7.5-.3 2-1.3 3-2.5 3.5C13 7 11.5 4.5 9 3c.3 3-3 5.5-3 9.5'
    'C6 16.6 8.4 21 12 21z"/><path d="M12 21c-1.7 0-3-1.3-3-3.2 0-2 1.6-3 3-4.8 1.4 1.8 3 2.8 3 4.8 0 1.9-1.3 3.2-3 3.2z"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "menu": '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18 14 14 0 0 1 0-18z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "upload": '<path d="M12 15V4"/><path d="m7 9 5-5 5 5"/><path d="M5 15v4a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4"/>',
    "message": '<path d="M4 5h16v11H9l-5 4z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1'
    'M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "shield": '<path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z"/>',
    "logout": '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="m10 17-5-5 5-5"/><path d="M5 12h11"/>',
    "login": '<path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3"/><path d="m14 17 5-5-5-5"/><path d="M19 12H8"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
}


@register.simple_tag
def icon(name, size=20, label=""):
    """Ícone SVG embutido. Sem label, fica escondido dos leitores de tela (é só enfeite)."""
    attributes = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true" focusable="false"'
    return mark_safe(
        f'<svg class="icon icon-{name}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" {attributes}>'
        f"{ICONS[name]}</svg>"
    )


@register.filter
def ago(value):
    """Tempo desde a data com uma só unidade ("2 dias", "3 horas"), como no mockup."""
    return timesince(value, depth=1) if value else ""


SECTIONS = {
    "inicio": lambda path: path == "/",
    "obras": lambda path: path.startswith(("/obras", "/minhas-obras", "/series")),
    "fandoms": lambda path: path.startswith("/fandoms"),
    "colecoes": lambda path: path.startswith("/colecoes"),
    "tags": lambda path: path.startswith(("/tags", "/wrangling")),
    "sobre": lambda path: path.startswith("/sobre"),
    "termos": lambda path: path.startswith("/termos"),
    "contato": lambda path: path.startswith("/contato"),
}


@register.simple_tag(takes_context=True)
def nav_state(context, section):
    """Marca o item do menu da página atual (classe + aria-current)."""
    request = context.get("request")
    if request is not None and SECTIONS[section](request.path):
        return mark_safe('class="is-active" aria-current="page"')
    return ""
