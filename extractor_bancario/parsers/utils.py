"""Utilidades comunes para parsear extractos bancarios argentinos."""
import re
from datetime import datetime


def parse_monto_ar(texto):
    """Convierte un monto en formato argentino ('1.234.567,89' o '1234567.89' o
    con signo al final '1.234,56-') a float. Devuelve None si no se puede parsear."""
    if texto is None:
        return None
    s = str(texto).strip()
    if s == "" or s == "-":
        return None

    negativo = False
    if s.endswith("-"):
        negativo = True
        s = s[:-1].strip()
    if s.startswith("-"):
        negativo = True
        s = s[1:].strip()
    if s.startswith("(") and s.endswith(")"):
        negativo = True
        s = s[1:-1].strip()

    s = s.replace("$", "").replace("U$S", "").replace(" ", "").strip()

    # Formato argentino: punto = miles, coma = decimal -> 1.234.567,89
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        # Solo coma: es el separador decimal (formato AR)
        s = s.replace(",", ".")
    # Si solo tiene puntos (formato US, como Banco Provincia) lo dejamos tal cual
    # siempre que tenga como máximo un punto seguido de 1-2 dígitos al final
    elif s.count(".") > 1:
        # múltiples puntos sin coma -> son separadores de miles
        partes = s.split(".")
        s = "".join(partes[:-1]) + "." + partes[-1]

    try:
        valor = float(s)
    except ValueError:
        return None

    return -valor if negativo else valor


def parse_fecha(texto, anio_default=None):
    """Intenta parsear una fecha en varios formatos comunes de extractos AR.
    Devuelve un datetime.date o None."""
    if not texto:
        return None
    s = str(texto).strip()

    formatos = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
    ]
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Formato DD/MM sin año (ej: Galicia usa DD/MM/AA, BBVA usa DD/MM solo)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})$", s)
    if m and anio_default:
        dia, mes = int(m.group(1)), int(m.group(2))
        try:
            return datetime(anio_default, mes, dia).date()
        except ValueError:
            return None

    return None


def limpiar_espacios(texto):
    return re.sub(r"\s+", " ", texto or "").strip()
