import streamlit as st
import pandas as pd
import re
from io import BytesIO

# =====================================
# CONFIGURACIÓN GENERAL
# =====================================
st.set_page_config(page_title="Buscador de Proyectos", layout="wide")

st.title("Buscador de proyectos por palabras clave, ubicación y año")
st.markdown("Filtra la base de datos por palabras clave, departamento, municipio y año.")

# =====================================
# CARGAR BASE DE DATOS
# =====================================

@st.cache_data
def cargar_datos():
    return pd.read_excel("BBDD.xlsx")

df = cargar_datos()

df["FECHA INICIAL"] = pd.to_datetime(df["FECHA INICIAL"], errors="coerce")

# =====================================
# PANEL LATERAL
# =====================================

st.sidebar.header("Filtros de búsqueda")

entrada = st.sidebar.text_input(
    "Palabras clave",
    placeholder="bonos verdes, conservación forestal"
)

# ---------- AÑOS ----------
lista_anios = sorted(df["FECHA INICIAL"].dropna().dt.year.unique().astype(int).tolist())
lista_anios_con_todos = ["Todos"] + lista_anios

anios_seleccionados = st.sidebar.multiselect(
    "Años",
    options=lista_anios_con_todos
)

# ---------- DEPARTAMENTOS ----------
lista_departamentos = sorted(df["DEPARTAMENTO"].dropna().unique().tolist())
lista_departamentos_con_todos = ["Todos"] + lista_departamentos

departamentos_seleccionados = st.sidebar.multiselect(
    "Departamento",
    options=lista_departamentos_con_todos
)

# ---------- MUNICIPIOS DEPENDIENTES ----------

if "Todos" in departamentos_seleccionados or len(departamentos_seleccionados) == 0:
    municipios_filtrados = sorted(df["MUNICIPIO"].dropna().unique().tolist())
else:
    municipios_filtrados = sorted(
        df[df["DEPARTAMENTO"].isin(departamentos_seleccionados)]["MUNICIPIO"]
        .dropna()
        .unique()
        .tolist()
    )

lista_municipios_con_todos = ["Todos"] + municipios_filtrados

municipios_seleccionados = st.sidebar.multiselect(
    "Municipio",
    options=lista_municipios_con_todos
)

boton_buscar = st.sidebar.button("Buscar")

# =====================================
# FORMATO MONEDA
# =====================================

def formato_usd(valor):
    if pd.isna(valor):
        return ""
    return f"USD {valor:,.2f}"

# =====================================
# PROCESAMIENTO
# =====================================

if boton_buscar:

    with st.spinner("🔄 Procesando búsqueda..."):

        df_filtrado = df.copy()

        # -------- Palabras clave --------
        if entrada.strip() != "":
            palabras_clave = [p.strip().lower() for p in entrada.split(",")]
            expresion = "|".join([re.escape(p) for p in palabras_clave])

            columnas_objetivo = ["NOMBRE INTERVENCION", "OBJETIVO GENERAL"]
            columnas_existentes = [c for c in columnas_objetivo if c in df.columns]

            filtro_texto = False
            for col in columnas_existentes:
                if filtro_texto is False:
                    filtro_texto = df[col].astype(str).str.lower().str.contains(expresion, na=False)
                else:
                    filtro_texto |= df[col].astype(str).str.lower().str.contains(expresion, na=False)

            df_filtrado = df_filtrado[filtro_texto]

        # -------- AÑOS --------
        if len(anios_seleccionados) > 0 and "Todos" not in anios_seleccionados:
            df_filtrado = df_filtrado[df_filtrado["FECHA INICIAL"].dt.year.isin(anios_seleccionados)]

        # -------- DEPARTAMENTO --------
        if len(departamentos_seleccionados) > 0 and "Todos" not in departamentos_seleccionados:
            df_filtrado = df_filtrado[df_filtrado["DEPARTAMENTO"].isin(departamentos_seleccionados)]

        # -------- MUNICIPIO --------
        if len(municipios_seleccionados) > 0 and "Todos" not in municipios_seleccionados:
            df_filtrado = df_filtrado[df_filtrado["MUNICIPIO"].isin(municipios_seleccionados)]

    st.success(f" Registros encontrados: {len(df_filtrado)}")

    # =====================================
    # TABLA PRINCIPAL
    # =====================================

    df_mostrar = df_filtrado.copy()

    if "VALOR APORTE (USD)" in df_mostrar.columns:
        df_mostrar["VALOR APORTE (USD)"] = df_mostrar["VALOR APORTE (USD)"].apply(formato_usd)

    st.subheader("Resultados filtrados")
    st.dataframe(df_mostrar, use_container_width=True)

    # =====================================
    # AGRUPACIONES
    # =====================================

    def mostrar_agrupado(columna, titulo):
        if columna in df_filtrado.columns:
            agrupado = (
                df_filtrado.groupby(columna)["VALOR APORTE (USD)"]
                .sum()
                .reset_index()
                .sort_values(by="VALOR APORTE (USD)", ascending=False)
            )

            agrupado["VALOR APORTE (USD)"] = agrupado["VALOR APORTE (USD)"].apply(formato_usd)

            st.subheader(titulo)
            st.dataframe(agrupado, use_container_width=True)

    mostrar_agrupado("ORIGEN DEL ACTOR", "Aportes por cooperante")
    mostrar_agrupado("DEPARTAMENTO", "Aportes por departamento")
    mostrar_agrupado("SECTORES GOB", "Aportes por sector")

    # =====================================
    # DESCARGA
    # =====================================

    def convertir_excel(df_exportar):
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df_exportar.to_excel(writer, index=False, sheet_name="Filtrado")
        buffer.seek(0)
        return buffer

    excel_descarga = convertir_excel(df_filtrado)

    st.download_button(
        "Descargar Excel filtrado",
        data=excel_descarga,
        file_name="BBDD_filtrada.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.info("Configura los filtros y presiona Buscar")