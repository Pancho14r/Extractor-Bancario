"""
Parser de extractos de Banco Provincia (Cuenta Corriente / Caja de Ahorro).

Formato observado (texto extraído línea a línea con pdfplumber):
    Fecha Concepto Importe Fecha Valor Saldo
    30/03/2026 SALDO ANTERIOR -15741527.54
    01/04/2026 EXTRACCION CAJERO 01/04/26 12:04 COMPR. -800000.00 01-04 -16541527.54
    000002483000000                                          <- línea de continuación del concepto
    01/04/2026 IMPUESTO DEBITO - LEY 25413 -4800.00 01-04 -16546327.54

Cada movimiento empieza con una fecha DD/MM/YYYY. El resto de la línea es:
    [concepto...] [importe] [fecha valor DD-MM] [saldo]
Puede haber líneas de continuación (sin fecha al inicio) que se agregan al concepto
del movimiento anterior.
"""
import re
import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

FECHA_INICIO_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.*)$")
# importe  fecha_valor(DD-MM)  saldo   al final de la línea
COLA_RE = re.compile(
    r"^(.*?)\s+(-?[\d.,]+)\s+(\d{2}-\d{2})\s+(-?[\d.,]+-?)\s*$"
)


MARCADORES_FIN = (
    "Tot. Retención ARBA",
    "Condiciones de Garantía",
    "Fecha Valor",
    "Tasa de interés para descubiertos",
)


def _extraer_texto(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            for linea in texto.split("\n"):
                if any(linea.strip().startswith(marc) for marc in MARCADORES_FIN):
                    return lineas
                lineas.append(linea)
    return lineas


# ─── Formato "home banking" (página de movimientos impresa a PDF) ────────────
#
#     30/07/2025                                   -$ 60,86
#     IMPUESTO DEBITO -LEY 25413
#     Saldo: $ 1.065.891,65
#
# Cada movimiento es un bloque que empieza con la fecha. El importe puede
# venir en la misma línea que la fecha o suelto en otra línea del bloque
# (depende de cómo se extraiga el texto), y el saldo viene como "Saldo: $ ...".
# Los movimientos vienen del más nuevo al más viejo.

_MONTO_WEB = r"-?\s?\$\s?-?[\d.]+,\d{2}"
FECHA_WEB_RE = re.compile(rf"^(\d{{2}}/\d{{2}}/\d{{4}})(?:\s+({_MONTO_WEB}))?$")
MONTO_WEB_RE = re.compile(rf"^{_MONTO_WEB}$")
SALDO_WEB_RE = re.compile(rf"^Saldo:\s*({_MONTO_WEB})$")


def _es_formato_web(lineas):
    return any(SALDO_WEB_RE.match(l.strip()) for l in lineas)


def _es_ruido_web(ls):
    return bool(
        re.match(r"^\d{1,2}/\d{1,2}/\d{2}, \d{1,2}:\d{2}", ls)   # encabezado del navegador
        or ls.startswith("http")
        or re.match(r"^C[CA] (U\$S|\$) ", ls)                     # "CC $ 5020-53826/2"
        or ls.startswith("Cuentas / Mis Cuentas")
        or ls in ("Cuenta Movimientos", "Banco Provincia")
    )


def _parse_web(lineas):
    movimientos = []
    actual = None

    def cerrar():
        if actual and actual["importe"] is not None:
            movimientos.append({
                "fecha": actual["fecha"],
                "fecha_valor": "",
                "concepto": limpiar_espacios(" ".join(actual["desc"])),
                "importe": actual["importe"],
                "saldo": actual["saldo"],
                "_es_saldo_inicial": False,
            })

    for linea in lineas:
        ls = linea.strip()
        if not ls or _es_ruido_web(ls):
            continue

        m_fecha = FECHA_WEB_RE.match(ls)
        if m_fecha:
            cerrar()
            actual = {"fecha": m_fecha.group(1), "desc": [], "importe": None, "saldo": None}
            if m_fecha.group(2):
                actual["importe"] = parse_monto_ar(m_fecha.group(2))
            continue
        if actual is None:
            continue

        m_saldo = SALDO_WEB_RE.match(ls)
        if m_saldo:
            actual["saldo"] = parse_monto_ar(m_saldo.group(1))
        elif MONTO_WEB_RE.match(ls) and actual["importe"] is None:
            actual["importe"] = parse_monto_ar(ls)
        else:
            actual["desc"].append(ls)
    cerrar()

    movimientos.reverse()  # orden cronológico, igual que el extracto clásico
    return movimientos


def parse(pdf_path):
    """Devuelve lista de dicts: fecha, fecha_valor, concepto, importe, saldo."""
    lineas = _extraer_texto(pdf_path)
    if _es_formato_web(lineas):
        return _parse_web(lineas)
    movimientos = []
    cont_actual = None  # referencia al último movimiento, para líneas de continuación

    for linea in lineas:
        linea = linea.rstrip()
        if not linea.strip():
            continue

        # Saltar encabezados / pies de página repetidos (anclados al inicio de línea
        # para no descartar movimientos legítimos que mencionen estas palabras, p.ej.
        # "TRANSF A FIBRA OPTICA PEHUAJO")
        ls = linea.strip()
        if ls.startswith("Fecha Concepto") or ls.startswith("Extracto de Cuenta") or \
           ls.startswith("6782 - PEHUAJO") or ls.startswith("CBU:") or \
           ls.startswith("CUENTA CORRIENTE") or ls.startswith("PERSONA JURIDICA") or \
           ls == "LA PLATA" or ls.startswith("LA PLATA 2-CTA") or \
           ls.startswith("TE FITI") or ls.startswith("Cantidad de Titulares") or \
           re.match(r"^\d{6}/\d$", ls) or re.match(r"^\d{2} \d{4}$", ls) or \
           re.match(r"^\d{6}//\d{2}.*CUENTA CORRIENTE", ls):
            continue

        m_inicio = FECHA_INICIO_RE.match(linea)
        if m_inicio:
            fecha = m_inicio.group(1)
            resto = m_inicio.group(2)

            m_cola = COLA_RE.match(resto)
            if m_cola:
                concepto = limpiar_espacios(m_cola.group(1))
                importe = parse_monto_ar(m_cola.group(2))
                fecha_valor = m_cola.group(3)
                saldo = parse_monto_ar(m_cola.group(4))

                if concepto.upper() == "SALDO ANTERIOR":
                    # Es el saldo inicial, no un movimiento; lo guardamos aparte
                    movimientos.append({
                        "fecha": fecha,
                        "fecha_valor": "",
                        "concepto": "SALDO ANTERIOR",
                        "importe": None,
                        "saldo": importe,  # en esta línea el "importe" capturado es el saldo
                        "_es_saldo_inicial": True,
                    })
                    cont_actual = None
                    continue

                mov = {
                    "fecha": fecha,
                    "fecha_valor": fecha_valor,
                    "concepto": concepto,
                    "importe": importe,
                    "saldo": saldo,
                    "_es_saldo_inicial": False,
                }
                movimientos.append(mov)
                cont_actual = mov
            else:
                # Caso especial SALDO ANTERIOR sin más columnas (solo fecha + texto + saldo)
                partes = resto.rsplit(None, 1)
                if len(partes) == 2 and re.match(r"^-?[\d.,]+-?$", partes[1]):
                    concepto = limpiar_espacios(partes[0])
                    saldo = parse_monto_ar(partes[1])
                    movimientos.append({
                        "fecha": fecha,
                        "fecha_valor": "",
                        "concepto": concepto,
                        "importe": None,
                        "saldo": saldo,
                        "_es_saldo_inicial": "SALDO ANTERIOR" in concepto.upper(),
                    })
                    cont_actual = None
                else:
                    cont_actual = None
        else:
            # Línea de continuación del concepto del movimiento anterior
            if cont_actual is not None and not re.match(r"^\d{6,}/?\d*$", linea.strip()):
                cont_actual["concepto"] = limpiar_espacios(
                    cont_actual["concepto"] + " " + linea
                )

    return movimientos


def to_dataframe(pdf_path):
    import pandas as pd
    movs = parse(pdf_path)
    filas = []
    for m in movs:
        if m.get("_es_saldo_inicial"):
            continue
        filas.append({
            "Fecha": m["fecha"],
            "Fecha Valor": m.get("fecha_valor", ""),
            "Descripción": m["concepto"],
            "Importe": m["importe"],
            "Saldo": m["saldo"],
            "Banco": "Provincia",
        })
    return pd.DataFrame(filas)
