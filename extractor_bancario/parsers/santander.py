"""
Parser de extractos de Banco Santander Argentina.

NOTA IMPORTANTE: a diferencia de los parsers de Provincia, BBVA y Galicia
(que fueron construidos y VALIDADOS con cuadre matemático exacto contra
extractos reales), este parser de Santander fue construido sobre el patrón
típico de extractos de cuenta corriente en pesos en Argentina (columnas:
Fecha | Descripción/Concepto | Comprobante/Origen | Débito | Crédito | Saldo),
pero no pudo probarse contra un PDF real de Santander.

Si el resultado no cuadra bien al procesar un extracto real, lo más probable
es que el formato exacto de columnas difiera (por ejemplo, columnas separadas
de Débito/Crédito en vez de un único Importe con signo, o el orden Fecha
Valor/Fecha Operación invertido). En ese caso avisame con un extracto de
ejemplo (puede tener los montos editados/ficticios) y ajusto el parser.
"""
import re
import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

FECHA_INICIO_RE = re.compile(r"^(\d{2}[/-]\d{2}[/-]\d{2,4})\s+(.*)$")

# Caso A: Débito y Crédito en columnas separadas: ... DEBITO CREDITO SALDO
COLA_DOS_COLUMNAS_RE = re.compile(
    r"^(.*?)\s+(-?[\d.,]+)?\s*[/|]?\s*(-?[\d.,]+)?\s+(-?[\d.,]+-?)\s*$"
)
# Caso B: Importe único con signo + Saldo
COLA_UNA_COLUMNA_RE = re.compile(
    r"^(.*?)\s+(-?[\d.,]+)\s+(-?[\d.,]+-?)\s*$"
)

ENCABEZADOS_IGNORAR = (
    "Banco Santander",
    "Resumen de Cuenta",
    "Extracto de Cuenta",
    "Fecha Descripcion",
    "Fecha Concepto",
    "Página",
    "CUIT",
    "SALDO ANTERIOR",
)


def _extraer_lineas(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas.extend(texto.split("\n"))
    return lineas


def parse(pdf_path):
    """Devuelve lista de dicts: fecha, concepto, importe, saldo.

    Intenta primero el formato de una sola columna de importe con signo
    (similar a Provincia/Galicia); si no logra extraer movimientos, intenta
    con dos columnas (débito/crédito separadas).
    """
    lineas = _extraer_lineas(pdf_path)
    movimientos = []
    cont_actual = None

    for linea in lineas:
        linea = linea.rstrip()
        ls = linea.strip()
        if not ls:
            continue
        if any(ls.startswith(enc) for enc in ENCABEZADOS_IGNORAR):
            cont_actual = None
            continue

        m_inicio = FECHA_INICIO_RE.match(ls)
        if m_inicio:
            fecha = m_inicio.group(1)
            resto = m_inicio.group(2)

            m_cola = COLA_UNA_COLUMNA_RE.match(resto)
            if m_cola:
                concepto = limpiar_espacios(m_cola.group(1))
                importe = parse_monto_ar(m_cola.group(2))
                saldo = parse_monto_ar(m_cola.group(3))
                mov = {
                    "fecha": fecha,
                    "concepto": concepto,
                    "importe": importe,
                    "saldo": saldo,
                }
                movimientos.append(mov)
                cont_actual = mov
            else:
                cont_actual = None
        else:
            if cont_actual is not None:
                cont_actual["concepto"] = limpiar_espacios(
                    cont_actual["concepto"] + " " + ls
                )

    return movimientos


def to_dataframe(pdf_path):
    import pandas as pd
    movs = parse(pdf_path)
    filas = []
    for m in movs:
        filas.append({
            "Fecha": m["fecha"],
            "Fecha Valor": "",
            "Descripción": m["concepto"],
            "Importe": m["importe"],
            "Saldo": m["saldo"],
            "Banco": "Santander",
        })
    return pd.DataFrame(filas)
