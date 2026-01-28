import streamlit as st
import pandas as pd
import re
import unicodedata
from io import BytesIO
import altair as alt

# =====================================
# FUNCIONES
# =====================================

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = str(texto).lower()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto


def formato_usd(valor):
    if pd.isna(valor):
        return ""
    return f"USD {valor:,.2f}"

# =====================================
# CONFIGURACIÓN
# =====================================
st.set_page_config(page_title="Buscador de Proyectos", layout="wide")

st.title("Buscador de proyectos por palabras clave, ubicación y filtros avanzados")

# =====================================
# CARGAR DATOS
# =====================================

@st.cache_data
def cargar_datos():
    return pd.read_excel("BBDD.xlsx")

df = cargar_datos()

df["FECHA INICIAL"] = pd.to_datetime(df["FECHA INICIAL"], errors="coerce")
if "FECHA FINAL" in df.columns:
    df["FECHA FINAL"] = pd.to_datetime(df["FECHA FINAL"], errors="coerce")

# =====================================
# SIDEBAR - FILTROS
# =====================================

st.sidebar.header("Filtros de búsqueda")

entrada = st.sidebar.text_input("Palabras clave")

# AÑOS (FECHA INICIAL)
lista_anios = sorted(df["FECHA INICIAL"].dropna().dt.year.unique().astype(int))
anios = st.sidebar.multiselect("Años (fecha inicial)", ["Todos"] + lista_anios)

# RANGO FECHA FINAL (inicia sin filtrar)
fecha_final_rango = None
if "FECHA FINAL" in df.columns:
    st.sidebar.markdown("### Rango de fecha finalización")
    
    # Obtener fecha mínima y máxima del dataset
    min_fecha = df["FECHA FINAL"].min()
    max_fecha = df["FECHA FINAL"].max()
    
    # Mostrar date_input con rango completo como inicial
    fecha_final_rango = st.sidebar.date_input(
        "Selecciona rango",
        value=(min_fecha, max_fecha),
        min_value=min_fecha,
        max_value=max_fecha
    )

# DEPARTAMENTO

lista_departamentos = sorted(df["DEPARTAMENTO"].dropna().unique())
departamentos = st.sidebar.multiselect("Departamento", ["Todos"] + lista_departamentos)

# MUNICIPIO
if "Todos" in departamentos or len(departamentos) == 0:
    municipios_base = df
else:
    municipios_base = df[df["DEPARTAMENTO"].isin(departamentos)]

lista_municipios = sorted(municipios_base["MUNICIPIO"].dropna().unique())
municipios = st.sidebar.multiselect("Municipio", ["Todos"] + lista_municipios)

# FILTROS AVANZADOS

def multiselect_columna(nombre_columna, label):
    if nombre_columna in df.columns:
        valores = sorted(df[nombre_columna].dropna().unique())
        return st.sidebar.multiselect(label, ["Todos"] + valores)
    return []

actor_1 = multiselect_columna("ACTOR PRIMER NIVEL", "Actor primer nivel")
actor_2 = multiselect_columna("ACTOR SEGUNDO NIVEL", "Actor segundo nivel")
origen_actor = multiselect_columna("ORIGEN DEL ACTOR", "Origen del actor")
nombre_actor = multiselect_columna("NOMBRE ACTOR", "Nombre actor")
ods = multiselect_columna("ODS", "ODS")
estado_intervencion = multiselect_columna("ESTADO DE INTERVENCION", "Estado de intervención")

boton_buscar = st.sidebar.button("Buscar")

# =====================================
# PROCESAMIENTO
# =====================================

if boton_buscar:

    with st.spinner("🔄 Procesando búsqueda..."):

        df_filtrado = df.copy()

        # PALABRAS CLAVE
        if entrada.strip() != "":
            palabras_clave = [normalizar_texto(p.strip()) for p in entrada.split(",")]
            expresion = "|".join([re.escape(p) for p in palabras_clave])

            columnas_objetivo = ["NOMBRE INTERVENCION", "OBJETIVO GENERAL"]
            filtro_texto = False

            for col in columnas_objetivo:
                if col in df.columns:
                    texto_col = df[col].astype(str).apply(normalizar_texto)
                    if filtro_texto is False:
                        filtro_texto = texto_col.str.contains(expresion, na=False)
                    else:
                        filtro_texto |= texto_col.str.contains(expresion, na=False)

            df_filtrado = df_filtrado[filtro_texto]

        # FILTROS GENERALES
        def aplicar_filtro(columna, seleccion):
            nonlocal_df = df_filtrado
            if len(seleccion) > 0 and "Todos" not in seleccion:
                nonlocal_df = nonlocal_df[nonlocal_df[columna].isin(seleccion)]
            return nonlocal_df

        if len(anios) > 0 and "Todos" not in anios:
            df_filtrado = df_filtrado[df_filtrado["FECHA INICIAL"].dt.year.isin(anios)]

        # RANGO FECHA FINAL
        if fecha_final_rango and len(fecha_final_rango) == 2 and "FECHA FINAL" in df_filtrado.columns:
            fecha_ini, fecha_fin = fecha_final_rango
            df_filtrado = df_filtrado[
                (df_filtrado["FECHA FINAL"] >= pd.to_datetime(fecha_ini)) &
                (df_filtrado["FECHA FINAL"] <= pd.to_datetime(fecha_fin))
            ]

        df_filtrado = aplicar_filtro("DEPARTAMENTO", departamentos)
        df_filtrado = aplicar_filtro("MUNICIPIO", municipios)
        df_filtrado = aplicar_filtro("ACTOR PRIMER NIVEL", actor_1)
        df_filtrado = aplicar_filtro("ACTOR SEGUNDO NIVEL", actor_2)
        df_filtrado = aplicar_filtro("ORIGEN DEL ACTOR", origen_actor)
        df_filtrado = aplicar_filtro("NOMBRE ACTOR", nombre_actor)
        df_filtrado = aplicar_filtro("ODS", ods)
        df_filtrado = aplicar_filtro("ESTADO DE INTERVENCION", estado_intervencion)

        # Mostrar número de registros dentro del spinner
        st.success(f"Registros encontrados: {len(df_filtrado)}")

    # =====================================
    # TABLA
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
        if columna in df_filtrado.columns and "VALOR APORTE (USD)" in df_filtrado.columns:
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
    # GRÁFICAS
    # =====================================

    st.subheader("Evolución de aportes por año (fecha inicial)")

    if "FECHA INICIAL" in df_filtrado.columns and "VALOR APORTE (USD)" in df_filtrado.columns:
        evolucion = (
            df_filtrado
            .dropna(subset=["FECHA INICIAL"])
            .assign(ANIO=df_filtrado["FECHA INICIAL"].dt.year)
            .groupby("ANIO")["VALOR APORTE (USD)"]
            .sum()
            .reset_index()
            .sort_values("ANIO")
        )

        chart = alt.Chart(evolucion).mark_bar().encode(
            x=alt.X("ANIO:O", title="Año"),
            y=alt.Y("VALOR APORTE (USD):Q", title="Valor aporte (USD)"),
            tooltip=[
                alt.Tooltip("ANIO:O", title="Año"),
                alt.Tooltip("VALOR APORTE (USD):Q", title="Monto", format=",.2f")
            ]
        ).properties(height=400)

        st.altair_chart(chart, use_container_width=True)

    st.subheader("Distribución de aportes (Top 10)")

    def grafica_barras(columna, titulo):
        if columna in df_filtrado.columns:
            datos = (
                df_filtrado.groupby(columna)["VALOR APORTE (USD)"]
                .sum().reset_index()
                .sort_values(by="VALOR APORTE (USD)", ascending=False)
                .head(10)
            )

            chart = alt.Chart(datos).mark_bar().encode(
                x=alt.X(columna, sort='-y'),
                y=alt.Y("VALOR APORTE (USD)", title="USD"),
                tooltip=[
                    alt.Tooltip(columna, title=columna),
                    alt.Tooltip("VALOR APORTE (USD)", title="Monto", format=",.2f")
                ]
            ).properties(title=titulo, height=400)

            st.altair_chart(chart, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        grafica_barras("ORIGEN DEL ACTOR", "Aportes por origen del actor")
        grafica_barras("DEPARTAMENTO", "Aportes por departamento")

    with col2:
        grafica_barras("ODS", "Aportes por ODS")

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


