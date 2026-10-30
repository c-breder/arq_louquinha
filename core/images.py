from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps

# Recusa imagens gigantes (bomba de descompressão)
Image.MAX_IMAGE_PIXELS = 40_000_000


def process_image(upload, max_width=None, square=None):
    """Valida, reduz e converte para WebP. Regravar a imagem descarta os metadados (GPS etc.)."""
    try:
        Image.open(upload).verify()
        upload.seek(0)
        image = Image.open(upload)
        image.seek(0)  # GIF animado: fica só o primeiro quadro
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
    except Exception as error:
        raise ValidationError(_("Arquivo de imagem inválido.")) from error

    if square:
        image = ImageOps.fit(image, (square, square))
    elif max_width and image.width > max_width:
        image.thumbnail((max_width, max_width * 20))

    buffer = BytesIO()
    image.save(buffer, "WEBP", quality=80, method=4)
    return ContentFile(buffer.getvalue()), image.width, image.height
