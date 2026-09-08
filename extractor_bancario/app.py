import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from procesador import procesar_pdf, construir_resumen, exportar_excel, COLUMNAS_FINALES
from parsers import PARSERS

st.set_page_config(
    page_title="Clasificador de Extractos Bancarios",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 Clasificador de Extractos Bancarios")
st.caption(
    "Cargá uno o varios extractos en PDF, indicá de qué banco es cada uno, "
    "y obtené un Excel con todos los movimientos clasificados por categoría."
)

BANCOS_DISPONIBLES = list(PARSERS.keys())


def _sugerir_banco(nombre_archivo: str):
    """Intenta adivinar el banco según el nombre del archivo, para
    preseleccionar la opción correcta en el selector."""
    nombre = nombre_archivo.lower()
    mapeo = {
        "provincia": "Banco Provincia",
        "bapro": "Banco Provincia",
        "bbva": "BBVA",
        "francés": "BBVA",
        "frances": "BBVA",
        "galicia": "Banco Galicia",
        "santander": "Santander",
        "rio": "Santander",
    }
    for clave, banco in mapeo.items():
        if clave in nombre:
            return banco
    return None

if "archivos_procesados" not in st.session_state:
    st.session_state.archivos_procesados = {}

with st.sidebar:
    st.header("⚙️ Configuración")
    st.markdown(
        "**Bancos soportados actualmente:**\n"
        "- Banco Provincia ✅ probado\n"
        "- BBVA ✅ probado\n"
        "- Banco Galicia ✅ probado\n"
        "- Santander ⚠️ estimado (sin validar con un PDF real)\n\n"
        "Si el de **Santander** no cuadra bien, compartí un extracto de "
        "ejemplo (los montos pueden estar editados) para ajustar el parser."
    )
    st.divider()
    st.markdown(
        "**¿Cómo funciona?**\n"
        "1. Subí los PDF.\n"
        "2. Elegí el banco de cada uno.\n"
        "3. Presioná **Procesar**.\n"
        "4. Revisá la vista previa y descargá el Excel."
    )

st.subheader("1. Cargar extractos")

archivos_subidos = st.file_uploader(
    "Subí uno o más extractos en PDF",
    type=["pdf"],
    accept_multiple_files=True,
)

asignaciones = {}
if archivos_subidos:
    st.subheader("2. Indicar el banco de cada archivo")
    cols = st.columns(2)
    for i, archivo in enumerate(archivos_subidos):
        col = cols[i % 2]
        with col:
            banco_sugerido = _sugerir_banco(archivo.name)
            banco = st.selectbox(
                f"📄 {archivo.name}",
                BANCOS_DISPONIBLES,
                index=BANCOS_DISPONIBLES.index(banco_sugerido) if banco_sugerido else 0,
                key=f"banco_{i}_{archivo.name}",
            )
            asignaciones[archivo.name] = (archivo, banco)

    st.subheader("3. Procesar")
    procesar = st.button("🚀 Procesar extractos", type="primary")

    if procesar:
        resultados = []
        errores = []
        with st.spinner("Procesando extractos..."):
            for nombre, (archivo, banco) in asignaciones.items():
                ruta_tmp = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(archivo.getvalue())
                        ruta_tmp = tmp.name
                    df = procesar_pdf(ruta_tmp, banco)
                    if df.empty:
                        errores.append(
                            f"⚠️ **{nombre}** ({banco}): no se detectaron movimientos. "
                            "Verificá que el banco seleccionado sea el correcto."
                        )
                    else:
                        resultados.append(df)
                except Exception as e:
                    errores.append(f"❌ **{nombre}** ({banco}): error al procesar — {e}")
                finally:
                    if ruta_tmp:
                        Path(ruta_tmp).unlink(missing_ok=True)

        for err in errores:
            st.warning(err)

        if resultados:
            df_final = pd.concat(resultados, ignore_index=True)
            st.session_state.archivos_procesados["df"] = df_final
            st.success(f"✅ Se procesaron {len(df_final)} movimientos en total.")
        elif not errores:
            st.error("No se pudo procesar ningún archivo.")

if "df" in st.session_state.archivos_procesados:
    df = st.session_state.archivos_procesados["df"]

    st.subheader("4. Resultados")

    tab_mov, tab_resumen = st.tabs(["📋 Movimientos", "📊 Resumen por categoría"])

    with tab_mov:
        bancos_filtro = st.multiselect(
            "Filtrar por banco", sorted(df["Banco"].unique()),
            default=sorted(df["Banco"].unique()),
        )
        categorias_filtro = st.multiselect(
            "Filtrar por categoría", sorted(df["Categoria"].unique()),
            default=sorted(df["Categoria"].unique()),
        )
        df_vista = df[
            df["Banco"].isin(bancos_filtro) & df["Categoria"].isin(categorias_filtro)
        ]
        st.dataframe(df_vista, use_container_width=True, height=400)

        c1, c2, c3 = st.columns(3)
        c1.metric("Movimientos", len(df_vista))
        c2.metric("Total débitos", f"$ {df_vista[df_vista['Importe']<0]['Importe'].sum():,.2f}")
        c3.metric("Total créditos", f"$ {df_vista[df_vista['Importe']>0]['Importe'].sum():,.2f}")

    with tab_resumen:
        resumen = construir_resumen(df)
        st.dataframe(resumen, use_container_width=True, height=400)

    st.subheader("5. Descargar Excel")
    with tempfile.TemporaryDirectory() as tmpdir:
        ruta_excel = str(Path(tmpdir) / "movimientos_clasificados.xlsx")
        exportar_excel(df, ruta_excel)
        with open(ruta_excel, "rb") as f:
            bytes_excel = f.read()

    st.download_button(
        "⬇️ Descargar Excel con movimientos clasificados",
        data=bytes_excel,
        file_name="movimientos_clasificados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
