"""
Las imágenes subidas NUNCA se guardan tal cual: se validan, se re-codifican a WEBP (elimina EXIF/GPS
y cualquier carga oculta) y se reducen. El nombre final es un UUID.
"""
import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_BYTES = 3 * 1024 * 1024
MAX_LADO = 1024
MAX_PIXELES = 25_000_000
FORMATOS = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELES  # defensa contra "decompression bombs"


def procesar_imagen(archivo):
    if archivo.size > MAX_BYTES:
        raise ValidationError("La imagen no puede superar 3 MB.")
    try:
        Image.open(archivo).verify()
        archivo.seek(0)
        img = Image.open(archivo)
        if img.format not in FORMATOS:
            raise ValidationError("Formato no permitido. Use JPG, PNG o WEBP.")
        if img.width * img.height > MAX_PIXELES:
            raise ValidationError("Imagen demasiado grande.")
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if ("A" in img.getbands() or img.mode == "P") else "RGB")
        img.thumbnail((MAX_LADO, MAX_LADO))
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=82)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError("El archivo no es una imagen válida.")
    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.webp")
