"""
Parser de extractos de Banco Galicia (Cuenta Corriente en Pesos).

Formato observado:
    Fecha Descripción Origen Crédito Débito Saldo
    01/04/26 TRANSFERENCIA DE CUENTA 00D5 5.000.000,00 115.670.225,85-
    PROPIA
    TE FITI SA
    30716505851
    01403242016782053329
    678205332980
    5046200141543070
    VARIOS
    01/04/26 TRANSFERENCIA A TERCEROS -1.318.000,00 116.988.225,85-
    Marino Damian Frangi
    20288727709
    HONORARIOS
    BANCO DE GALICIA Y B

Cada movimiento inicia con fecha DD/MM/AA. En la misma línea viene el inicio del
concepto, un código de origen opcional (ej "00D5", "0373", "0001"), el importe
(crédito sin signo, débito con signo "-") y el saldo (con "-" final si es negativo).
El resto del concepto (nombre de contraparte, CUIT, banco, leyenda "VARIOS", etc.)
viene en líneas de continuación sin fecha, hasta el siguiente movimiento.
"""
import re
import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

FECHA_INICIO_RE = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.*)$")
# Captura: [concepto inicial] [origen opcional] [importe] [saldo-con-guion-opcional]
COLA_RE = re.compile(
    r"^(.*?)\s+(?:(\d{4})\s+)?(-?[\d.,]+)\s+([\d.,]+-?)\s*$"
)

ENCABEZADOS_IGNORAR = (
    "Resumen de Cuenta Corriente",
    "Fecha Descripción Origen",
    "Página",
    "TE FITI S.A",
    "CUIT del Responsable",
    "IVA: Responsable",
    "Cantidad de cotitulares",
)


def _extraer_lineas(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas.extend(texto.split("\n"))
    return lineas


def _es_encabezado_o_ruido(ls):
    if any(ls.startswith(enc) for enc in ENCABEZADOS_IGNORAR):
        return True
    if re.match(r"^\d{15,20}H?$", ls):  # código de barras/identificador de página
        return True
    if ls == "Movimientos":
        return True
    return False


def parse(pdf_path):
    """Devuelve lista de dicts: fecha, concepto, importe, saldo, origen."""
    lineas = _extraer_lineas(pdf_path)
    movimientos = []
    cont_actual = None
    seccion_movimientos_terminada = False

    for linea in lineas:
        linea = linea.rstrip()
        ls = linea.strip()
        if not ls:
            continue
        if ls.startswith("Total ") or ls.startswith("Consolidado de retención"):
            seccion_movimientos_terminada = True
        if seccion_movimientos_terminada:
            continue
        if _es_encabezado_o_ruido(ls):
            continue

        m_inicio = FECHA_INICIO_RE.match(ls)
        if m_inicio:
            fecha = m_inicio.group(1)
            resto = m_inicio.group(2)
            m_cola = COLA_RE.match(resto)
            if m_cola:
                concepto = limpiar_espacios(m_cola.group(1))
                origen = m_cola.group(2) or ""
                importe = parse_monto_ar(m_cola.group(3))
                saldo = parse_monto_ar(m_cola.group(4))

                mov = {
                    "fecha": fecha,
                    "concepto": concepto,
                    "origen": origen,
                    "importe": importe,
                    "saldo": saldo,
                }
                movimientos.append(mov)
                cont_actual = mov
            else:
                cont_actual = None
        else:
            # línea de continuación del concepto (nombre contraparte, CUIT, banco, etc.)
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
            "Banco": "Galicia",
        })
    return pd.DataFrame(filas)
