"""
Parser de extractos de Banco Santander Argentina (Cuenta Corriente, resumen mensual).

Formato observado (texto extraído línea a línea):
    Fecha Comprobante Movimiento Débito Crédito Saldo en cuenta
    01/07/25 Saldo Inicial $ 14.071.472,13
    01/07/25 12145989 Pago comercios frst data visa nro.liq.
    00335994/0012145989
    $ 21.906,73 $ 14.078.727,83
    01/07/25 Impuesto ley 25.413 debito 0,6% $ 87,91 $ 24.088.279,15
    ...
     Saldo total $ 1.351.907,79

Cada movimiento termina en la línea que trae los dos montos: el importe (en la
columna Débito o Crédito) y el saldo. Como en el texto no se distingue en qué
columna estaba el importe, el signo se deduce de la variación del saldo.
Si una fila no trae fecha, se usa la del movimiento anterior.
"""
import re
import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

_MONTO = r"-?\s?\$\s?-?[\d.]+,\d{2}"

FECHA_RE = re.compile(r"^(\d{2}/\d{2}/\d{2,4})\s+(.*)$")
MONTOS_RE = re.compile(rf"^(.*?)\s*({_MONTO})\s+({_MONTO})$")
SALDO_INICIAL_RE = re.compile(rf"Saldo Inicial\s+({_MONTO})$")


def _extraer_lineas(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            lineas.extend(texto.split("\n"))
    return lineas


def _es_ruido(ls):
    return bool(
        ls.startswith("Cuenta Corriente N")
        or ls.startswith("Fecha Comprobante")
        or ls.startswith("* Salvo error")
        or re.match(r"^\d+\s*-\s*\d+$", ls)          # número de página "3 - 13"
    )


def parse_lineas(lineas):
    """Devuelve lista de dicts: fecha, concepto, importe, saldo."""
    movimientos = []
    activo = False          # dentro de una tabla de movimientos en pesos
    moneda = "ARS"
    saldo_prev = None
    fecha_actual = None
    pendiente = []          # líneas de descripción del movimiento en curso

    for linea in lineas:
        ls = linea.strip()
        if not ls:
            continue

        if ls.startswith("Movimientos en pesos"):
            moneda = "ARS"
        elif ls.startswith("Movimientos en d"):
            moneda = "USD"

        if not activo:
            m_ini = SALDO_INICIAL_RE.search(ls)
            if m_ini and moneda == "ARS":
                activo = True
                saldo_prev = parse_monto_ar(m_ini.group(1))
                m_fecha = FECHA_RE.match(ls)
                fecha_actual = m_fecha.group(1) if m_fecha else None
                pendiente = []
            continue

        if ls.startswith("Saldo total"):
            activo = False
            continue
        if _es_ruido(ls):
            continue

        m_fecha = FECHA_RE.match(ls)
        if m_fecha:
            fecha_actual = m_fecha.group(1)
            ls = m_fecha.group(2)
            pendiente = []

        m_montos = MONTOS_RE.match(ls)
        if not m_montos:
            pendiente.append(ls)
            continue

        pendiente.append(m_montos.group(1))
        monto = abs(parse_monto_ar(m_montos.group(2)))
        saldo = parse_monto_ar(m_montos.group(3))
        if saldo_prev is not None and saldo < saldo_prev:
            importe = -monto
        else:
            importe = monto

        movimientos.append({
            "fecha": fecha_actual,
            "concepto": limpiar_espacios(" ".join(pendiente)),
            "importe": importe,
            "saldo": saldo,
        })
        saldo_prev = saldo
        pendiente = []

    return movimientos


def parse(pdf_path):
    return parse_lineas(_extraer_lineas(pdf_path))


def to_dataframe(pdf_path):
    import pandas as pd
    movs = parse(pdf_path)
    return pd.DataFrame([
        {
            "Fecha": m["fecha"],
            "Fecha Valor": "",
            "Descripción": m["concepto"],
            "Importe": m["importe"],
            "Saldo": m["saldo"],
            "Banco": "Santander",
        }
        for m in movs
    ])
