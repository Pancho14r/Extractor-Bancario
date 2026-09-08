"""
Orquestador: dado un PDF de extracto bancario y el nombre del banco,
extrae los movimientos, los clasifica por categoría y devuelve un
DataFrame final + permite exportarlo a Excel con formato.
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from parsers import PARSERS
from classifier import clasificar_dataframe

COLUMNAS_FINALES = [
    "Banco", "Fecha", "Fecha Valor", "Descripción", "Categoria",
    "Tipo", "Importe", "Saldo",
]


def procesar_pdf(pdf_path: str, banco: str) -> pd.DataFrame:
    """Procesa un único PDF y devuelve un DataFrame clasificado."""
    if banco not in PARSERS:
        raise ValueError(
            f"Banco '{banco}' no soportado. Opciones: {list(PARSERS.keys())}"
        )
    modulo = PARSERS[banco]
    df = modulo.to_dataframe(pdf_path)
    if df.empty:
        return df
    df = clasificar_dataframe(df)
    for col in COLUMNAS_FINALES:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNAS_FINALES]


def procesar_multiples(archivos_con_banco) -> pd.DataFrame:
    """archivos_con_banco: lista de tuplas (ruta_pdf, nombre_banco)."""
    dfs = []
    for ruta, banco in archivos_con_banco:
        df = procesar_pdf(ruta, banco)
        if not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=COLUMNAS_FINALES)
    return pd.concat(dfs, ignore_index=True)


def construir_resumen(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla resumen: total débitos/créditos por banco y categoría."""
    if df.empty:
        return pd.DataFrame(columns=["Banco", "Categoria", "Débitos", "Créditos", "Neto"])
    tmp = df.copy()
    tmp["Debitos"] = tmp["Importe"].apply(lambda x: x if x < 0 else 0)
    tmp["Creditos"] = tmp["Importe"].apply(lambda x: x if x > 0 else 0)
    resumen = (
        tmp.groupby(["Banco", "Categoria"], as_index=False)
        .agg(Débitos=("Debitos", "sum"), Créditos=("Creditos", "sum"))
    )
    resumen["Neto"] = resumen["Débitos"] + resumen["Créditos"]
    return resumen.sort_values(["Banco", "Categoria"]).reset_index(drop=True)


def exportar_excel(df: pd.DataFrame, ruta_salida: str):
    """Genera el Excel final con 3 hojas: Movimientos, Resumen por Categoría,
    y una hoja por banco (si hay más de uno)."""
    resumen = construir_resumen(df)

    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    _escribir_tabla(ws, df, formato_moneda_cols=["Importe", "Saldo"])

    ws_resumen = wb.create_sheet("Resumen por Categoría")
    _escribir_tabla(ws_resumen, resumen, formato_moneda_cols=["Débitos", "Créditos", "Neto"])

    if df["Banco"].nunique() > 1:
        for banco in sorted(df["Banco"].unique()):
            hoja_nombre = f"{banco}"[:31]
            ws_banco = wb.create_sheet(hoja_nombre)
            sub = df[df["Banco"] == banco].reset_index(drop=True)
            _escribir_tabla(ws_banco, sub, formato_moneda_cols=["Importe", "Saldo"])

    wb.save(ruta_salida)
    return ruta_salida


FONT_HEADER = Font(name="Arial", bold=True, color="FFFFFF", size=10)
FILL_HEADER = PatternFill("solid", start_color="2F5496")
FONT_BODY = Font(name="Arial", size=10)
BORDE_FINO = Border(*[Side(style="thin", color="D9D9D9")] * 4)
FORMATO_MONEDA = '#,##0.00;[RED]-#,##0.00'


def _escribir_tabla(ws, df: pd.DataFrame, formato_moneda_cols=None):
    formato_moneda_cols = formato_moneda_cols or []
    if df.empty:
        ws.append(["Sin datos"])
        return

    columnas = list(df.columns)
    ws.append(columnas)
    for cell in ws[1]:
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDE_FINO

    idx_moneda = [columnas.index(c) for c in formato_moneda_cols if c in columnas]

    for _, fila in df.iterrows():
        valores = [fila[c] for c in columnas]
        ws.append(valores)
        fila_excel = ws.max_row
        for c_idx in range(1, len(columnas) + 1):
            cell = ws.cell(row=fila_excel, column=c_idx)
            cell.font = FONT_BODY
            cell.border = BORDE_FINO
            if (c_idx - 1) in idx_moneda:
                cell.number_format = FORMATO_MONEDA

    ws.freeze_panes = "A2"
    for c_idx, col in enumerate(columnas, start=1):
        max_len = max(
            [len(str(col))] + [len(str(v)) for v in df[col].astype(str).tolist()]
        )
        ws.column_dimensions[get_column_letter(c_idx)].width = min(max_len + 3, 60)

    ws.auto_filter.ref = ws.dimensions
