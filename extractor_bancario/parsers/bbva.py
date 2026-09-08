"""
Parser de extractos de BBVA Argentina (Cuenta Pyme Persona Jurídica / similares).

El PDF puede contener varias sub-cuentas (ej: CC $ 093-322407/8, CC $ 093-322408/5,
CC U$S 093-055920/7), cada una con su propia tabla:

    CC $ 093-322407/8 (Cta.Cte.Bancaria) - Iva-Responsable Inscripto
    FECHA ORIGEN CONCEPTO DÉBITO CRÉDITO SALDO
    SALDO ANTERIOR 3.618,45
    01/04 D INTERES SALDO DEUDOR EXCEDI -0,12 3.618,33
    01/04 D COM MANT MENS FRANCES PROYE 03/26 -59.000,00 -55.381,70
    09/04 D 587 TR.NE3378363 TE FITI S A 259.823,92 183.314,33
    SALDO AL 30 DE ABRIL 10.000,00
    TOTAL MOVIMIENTOS -253.442,37 259.823,92

Cada línea de movimiento: FECHA(DD/MM) [D] [concepto...] IMPORTE SALDO
El importe lleva su propio signo (negativo = débito, positivo = crédito).
Algunos conceptos incluyen un código de "origen" numérico pegado al concepto
(ej. "587", "0001") que dejamos como parte del concepto.
Las líneas de concepto pueden continuar en la línea siguiente sin fecha
(ej. "Marzo 2026", número de CUIT, "BANCO BBVA ARGENTINA", etc. en otros bancos,
pero en BBVA el concepto normalmente cabe en una sola línea).
"""
import re
import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

LINEA_CUENTA_RE = re.compile(r"^(CC\s+[\$U].*?)\s*\(Cta\.Cte\.Bancaria\)")
LINEA_MOV_RE = re.compile(
    r"^(\d{2}/\d{2})\s+(.*?)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s*$"
)
SALDO_ANTERIOR_RE = re.compile(r"^SALDO ANTERIOR\s+(-?[\d.,]+)\s*$")
SALDO_AL_RE = re.compile(r"^SALDO AL\b")
TOTAL_MOV_RE = re.compile(r"^TOTAL MOVIMIENTOS\b")
SIN_MOVIMIENTOS_RE = re.compile(r"SIN MOVIMIENTOS")


def _extraer_lineas(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas.extend(texto.split("\n"))
    return lineas


def parse(pdf_path):
    """Devuelve lista de dicts: cuenta, fecha, concepto, importe, saldo."""
    lineas = _extraer_lineas(pdf_path)
    movimientos = []
    cuenta_actual = None
    dentro_tabla = False

    for linea in lineas:
        linea = linea.rstrip()
        ls = linea.strip()
        if not ls:
            continue

        m_cuenta = LINEA_CUENTA_RE.match(ls)
        if m_cuenta:
            cuenta_actual = limpiar_espacios(m_cuenta.group(1))
            dentro_tabla = False
            continue

        if ls.startswith("FECHA ORIGEN CONCEPTO"):
            dentro_tabla = True
            continue

        if not dentro_tabla:
            continue

        if SIN_MOVIMIENTOS_RE.search(ls):
            continue
        if SALDO_ANTERIOR_RE.match(ls):
            continue
        if SALDO_AL_RE.match(ls) or TOTAL_MOV_RE.match(ls):
            dentro_tabla = False
            continue

        m = LINEA_MOV_RE.match(ls)
        if m:
            fecha = m.group(1)
            concepto = limpiar_espacios(m.group(2))
            importe = parse_monto_ar(m.group(3))
            saldo = parse_monto_ar(m.group(4))

            # El concepto puede empezar con "D " (marca de impuesto a débitos/créditos)
            # o con un código de origen numérico (ej. "587", "0001"); se deja tal cual
            # para no perder información, salvo la marca D/C suelta al inicio.
            concepto = re.sub(r"^([DC])\s+", "", concepto)

            movimientos.append({
                "cuenta": cuenta_actual,
                "fecha": fecha,
                "concepto": concepto,
                "importe": importe,
                "saldo": saldo,
            })

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
            "Cuenta": m["cuenta"],
            "Banco": "BBVA",
        })
    return pd.DataFrame(filas)
