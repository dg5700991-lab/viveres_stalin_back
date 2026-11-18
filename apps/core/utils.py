import uuid
from datetime import date

from rest_framework.exceptions import ValidationError


def parse_uuid(valor, campo):
    try:
        return uuid.UUID(str(valor))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError({campo: "Identificador inválido."})


def parse_fecha(valor, campo):
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        raise ValidationError({campo: "Use el formato AAAA-MM-DD."})
