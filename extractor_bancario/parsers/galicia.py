"""
Parser de extractos de Banco Galicia (Cuenta Corriente en Pesos).

Soporta dos tipos de PDF:
  - PDF con capa de texto (pdfplumber extrae directo)
  - PDF escaneado/imagen (fallback automático a OCR con pytesseract)

Formato de cada movimiento:
    DD/MM/YY CONCEPTO [ORIGEN_4DIGITOS] IMPORTE SALDO
    linea_continuacion_1  (nombre contraparte, CUIT, banco, etc.)
    ...

El importe lleva signo: negativo = débito, positivo = crédito.
"""
import os
import re
import shutil
from pathlib import Path

import pdfplumber
from .utils import parse_monto_ar, limpiar_espacios

# Acepta DD/MM/AA o DD/MM/YYYY
FECHA_INICIO_RE = re.compile(r"^(\d{2}/\d{2}/\d{2,4})\s+(.*)$")

# Concepto  [origen 4-5 chars]  importe  saldo
COLA_RE = re.compile(
    r"^(.*?)\s+(?:([0-9A-Z]{4,5})\s+)?(-?[\d.,]+)\s+([\d.,]+-?)\s*$"
)

ENCABEZADOS_IGNORAR = (
    "Resumen de Cuenta Corriente",
    "Fecha Descripcion",
    "Fecha Descripcio",
    "Fecha Descripción",
    "Página",
    "Pagina",
    "CUIT del Responsable",
    "IVA: Responsable",
    "Cantidad de cotitulares",
    "Disponés de",
    "Tasa Extraordinaria",
    "Consolidado de retencion",
    "Consolidado de retenci",
    "Los depositos",
    "Los totales",
    "Al completa",
    "Canales de atencion",
    "Ingresa",
    "Chatea",
    "Llamanos",
    "Usted puede",
    "http",
)

FIN_MOVIMIENTOS = ("Total ", "Consolidado de ret")


# ─── Extracción de texto ──────────────────────────────────────────────────────

def _tiene_texto(pdf_path):
    """True si el PDF tiene capa de texto extraíble (no es solo imagen)."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            if len((page.extract_text() or "").strip()) > 50:
                return True
    return False


def _extraer_lineas_texto(pdf_path):
    lineas = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            lineas.extend((page.extract_text() or "").split("\n"))
    return lineas


def _buscar_tesseract():
    """Devuelve la ruta a tesseract.exe si no está en el PATH (Windows)."""
    if shutil.which("tesseract"):
        return None
    candidatos = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]
    for c in candidatos:
        if c.is_file():
            return str(c)
    return None


def _buscar_poppler():
    """Devuelve la carpeta bin de Poppler si pdftoppm no está en el PATH (Windows)."""
    if shutil.which("pdftoppm"):
        return None
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.is_dir():
        for exe in base.glob("oschwartz10612.Poppler*/*/Library/bin/pdftoppm.exe"):
            return str(exe.parent)
    return None


def _extraer_lineas_ocr(pdf_path):
    """
    Fallback OCR: rasteriza el PDF y aplica Tesseract página por página.

    Requiere:
        pip install pdf2image pytesseract
        + Tesseract instalado en el sistema:
            Windows: https://github.com/UB-Mannheim/tesseract/wiki
            Mac:     brew install tesseract
            Linux:   apt install tesseract-ocr
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "Este PDF es una imagen escaneada y requiere OCR.\n"
            "Instalá las dependencias con:\n"
            "  pip install pdf2image pytesseract\n"
            "Y Tesseract en tu sistema:\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  Mac:     brew install tesseract\n"
            "  Linux:   apt install tesseract-ocr"
        )

    tesseract_cmd = _buscar_tesseract()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    pages = convert_from_path(pdf_path, dpi=250, poppler_path=_buscar_poppler())
    lineas = []
    for page in pages:
        text = pytesseract.image_to_string(page, lang="eng", config="--psm 6")
        lineas.extend(text.split("\n"))
    return lineas


def _extraer_lineas(pdf_path):
    if _tiene_texto(pdf_path):
        return _extraer_lineas_texto(pdf_path)
    return _extraer_lineas_ocr(pdf_path)


# ─── Limpieza específica de artefactos OCR ───────────────────────────────────

def _limpiar_monto_ocr(s):
    """Corrige artefactos OCR en montos: '-4,.398,14' → '-4.398,14'"""
    if not s:
        return s
    s = re.sub(r",\.", ",", s)   # -4,.398 → -4,398
    s = re.sub(r"\.\.", ".", s)  # 4..000  → 4.000
    return s


def _limpiar_concepto(s):
    """Elimina basura OCR que queda pegada al concepto."""
    # Encabezado de página que el OCR mezcla con la última línea de la página anterior
    s = re.sub(
        r"\s*(Fecha\s+Descripc[ií]o?n?\s+Origen\s+Cr[eé]dito\s+D[eé]bito\s+Saldo)\s*",
        "", s, flags=re.IGNORECASE
    )
    # Artefactos típicos: §, =, |, caracteres sueltos
    s = re.sub(r"^[§=\|]\s*", "", s)
    return limpiar_espacios(s)


# ─── Parser principal ─────────────────────────────────────────────────────────

def _es_encabezado_o_ruido(ls):
    if any(ls.startswith(enc) for enc in ENCABEZADOS_IGNORAR):
        return True
    if re.match(r"^\d{15,20}H?$", ls):   # código de página (ej: 20251230049364771H)
        return True
    if ls in ("Movimientos", "Descripcion", "Descripción", "Origen"):
        return True
    if re.match(r"^[§=\|\s]+$", ls):     # línea solo ruido OCR
        return True
    return False


def parse(pdf_path):
    """Devuelve lista de dicts: fecha, concepto, importe, saldo."""
    lineas = _extraer_lineas(pdf_path)
    movimientos = []
    cont_actual = None
    terminado = False

    for linea in lineas:
        ls = linea.strip()
        if not ls:
            continue

        if any(ls.startswith(fin) for fin in FIN_MOVIMIENTOS):
            terminado = True
        if terminado:
            continue

        if _es_encabezado_o_ruido(ls):
            continue

        m_inicio = FECHA_INICIO_RE.match(ls)
        if m_inicio:
            fecha = m_inicio.group(1)
            resto = re.sub(r"[=\|]", "", m_inicio.group(2)).strip()

            m_cola = COLA_RE.match(resto)
            if m_cola:
                concepto = _limpiar_concepto(m_cola.group(1))
                origen   = m_cola.group(2) or ""
                importe  = parse_monto_ar(_limpiar_monto_ocr(m_cola.group(3)))
                saldo    = parse_monto_ar(_limpiar_monto_ocr(m_cola.group(4)))

                mov = {
                    "fecha":   fecha,
                    "concepto": concepto,
                    "origen":  origen,
                    "importe": importe,
                    "saldo":   saldo,
                }
                movimientos.append(mov)
                cont_actual = mov
            else:
                cont_actual = None
        else:
            # Línea de continuación: nombre de contraparte, CUIT, banco destino, etc.
            if cont_actual is not None and not _es_encabezado_o_ruido(ls):
                cont_actual["concepto"] = _limpiar_concepto(
                    cont_actual["concepto"] + " " + ls
                )

    return movimientos


def to_dataframe(pdf_path):
    import pandas as pd
    movs = parse(pdf_path)
    return pd.DataFrame([
        {
            "Fecha":       m["fecha"],
            "Fecha Valor": "",
            "Descripción": m["concepto"],
            "Importe":     m["importe"],
            "Saldo":       m["saldo"],
            "Banco":       "Galicia",
        }
        for m in movs
    ])
