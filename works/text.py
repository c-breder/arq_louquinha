import html
import re

TAG_RE = re.compile(r"<[^>]*>")
# Palavra: letras/números, aceitando hífen e apóstrofo internos (ex.: "guarda-chuva", "d'água")
WORD_RE = re.compile(r"\w+(?:[-'’]\w+)*")


def count_words(text):
    # Troca cada tag por espaço para não grudar palavras de parágrafos vizinhos
    plain = html.unescape(TAG_RE.sub(" ", text or ""))
    return len(WORD_RE.findall(plain))
