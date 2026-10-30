import re

import nh3
from django.conf import settings

# Lista branca de tags (parecida com a do AO3)
BASE_TAGS = {
    "a", "abbr", "b", "big", "blockquote", "br", "caption", "center", "cite", "code", "col",
    "colgroup", "dd", "del", "dfn", "div", "dl", "dt", "em", "h1", "h2", "h3", "h4", "h5", "h6",
    "hr", "i", "ins", "kbd", "li", "ol", "p", "pre", "q", "s", "samp", "small", "span", "strike",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "tt", "u",
    "ul", "var",
}  # fmt: skip

ATTRIBUTES = {
    "*": {"title", "dir", "align", "lang"},
    "a": {"href", "name"},
    "img": {"src", "alt", "width", "height"},
    "ol": {"start", "type"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
    "blockquote": {"cite"},
    "q": {"cite"},
}

BLOCK_RE = re.compile(r"<(p|div|br|ul|ol|blockquote|h[1-6]|table|pre|hr)\b", re.IGNORECASE)


def image_prefix():
    return f"{settings.MEDIA_URL}imagens/"


def _filter_attribute(element, attribute, value):
    if element == "img":
        if attribute == "src":
            # Só imagens enviadas ao próprio site (nada de rastrear leitores por link externo)
            return value if value.startswith(image_prefix()) and ".." not in value else None
        if attribute in ("width", "height"):
            return value if value.isdigit() else None
    return value


def clean_html(html, allow_images=False):
    tags = (BASE_TAGS | {"img"}) if allow_images else BASE_TAGS
    attributes = ATTRIBUTES if allow_images else {k: v for k, v in ATTRIBUTES.items() if k != "img"}
    return nh3.clean(
        html or "",
        tags=tags,
        attributes=attributes,
        url_schemes={"http", "https", "mailto"},
        link_rel="nofollow noopener noreferrer ugc",
        attribute_filter=_filter_attribute,
        strip_comments=True,
    )


def autoparagraph(text):
    # Texto puro colado no modo HTML: linha em branco vira parágrafo, quebra simples vira <br>
    text = (text or "").replace("\r\n", "\n").strip()
    if not text or BLOCK_RE.search(text):
        return text
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return "".join(f"<p>{block.replace(chr(10), '<br>')}</p>" for block in paragraphs)
