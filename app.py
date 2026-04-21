import streamlit as st
import pandas as pd
import re
import unicodedata
from io import BytesIO
import altair as alt

# =====================================
# PREFIJOS TRANSPARENTES DEL ESPAÑOL
# =====================================
PREFIJOS_TRANSPARENTES = sorted([
    "trans", "inter", "intra", "extra", "ultra", "supra", "infra", "sub", "super",
    "anti", "contra", "des", "dis",
    "hiper", "hipo", "mega", "macro", "micro",
    "eco", "bio", "geo", "socio", "etno", "afro", "narco", "agro", "demo",
    "psico", "neuro", "tecno", "hidro", "electro",
    "multi", "pluri", "mono", "uni", "bi", "tri", "pan", "omni",
    "pre", "post", "neo", "proto", "paleo",
    "meta", "auto", "co", "pro", "hetero", "homo", "semi",
    "endo", "exo", "re", "in", "im",
], key=len, reverse=True)

COLUMNAS_OBJETIVO = ["NOMBRE INTERVENCION", "OBJETIVO GENERAL"]


# =====================================
# FUNCIONES BASE
# =====================================

def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = str(texto).lower()
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto


def formato_usd(valor):
    if pd.isna(valor):
        return ""
    return f"USD {valor:,.2f}"


def tokenizar(texto: str) -> list:
    return re.findall(r'[a-z0-9]+', texto)


# =====================================
# NÚCLEO: COINCIDENCIA INTELIGENTE
# =====================================

def token_coincide(token: str, palabra: str) -> bool:
    """Una palabra del texto coincide con la palabra buscada (prefijo directo o transparente)."""
    if token.startswith(palabra):
        return True
    for prefijo in PREFIJOS_TRANSPARENTES:
        if token.startswith(prefijo + palabra):
            return True
    return False


def frase_coincide_en_texto(texto_norm: str, palabras_frase: list) -> bool:
    """
    Verifica que TODAS las palabras de una frase aparezcan en el texto (lógica AND).
    Cada palabra individual usa la coincidencia inteligente de prefijos.

    Ejemplo: frase = ["cambio", "climatico"]
      → el texto debe contener algún token que coincida con "cambio"
        Y algún token que coincida con "climatico"
    """
    tokens = tokenizar(texto_norm)
    return all(
        any(token_coincide(tok, palabra) for tok in tokens)
        for palabra in palabras_frase
    )


def texto_contiene_alguna_frase(texto_norm: str, frases: list) -> bool:
    """
    Verifica si el texto contiene AL MENOS UNA de las frases buscadas (lógica OR entre frases).
    Dentro de cada frase todas las palabras deben aparecer (lógica AND).

    Ejemplo: frases = [["cambio", "climatico"], ["feminismo"]]
      → el texto debe tener ("cambio" Y "climatico") O ("feminismo")
    """
    return any(frase_coincide_en_texto(texto_norm, frase) for frase in frases)


def filtrar_por_palabras(serie: pd.Series, frases_norm: list, modo: str) -> pd.Series:
    """
    Aplica el filtro sobre una Serie de textos ya normalizados.

    frases_norm — lista de listas: cada sublista es una frase (sus palabras separadas).
      Ejemplo: [["cambio", "climatico"], ["feminismo"]]

    modo "exacta"      → regex \b...\b sobre la frase completa (texto sin partir)
    modo "inteligente" → AND dentro de frase, OR entre frases
    """
    if not frases_norm:
        return pd.Series(False, index=serie.index)

    if modo == "exacta":
        # En modo exacta cada frase se busca como texto literal completo
        frases_completas = [" ".join(f) for f in frases_norm]
        patron = "|".join(rf"\b{re.escape(f)}\b" for f in frases_completas)
        return serie.str.contains(patron, na=False, regex=True)
    else:
        return serie.apply(lambda txt: texto_contiene_alguna_frase(txt, frases_norm))


# =====================================
# PARSEO DE LA ENTRADA DEL USUARIO
# =====================================

def parsear_entrada(entrada: str):
    """
    Convierte la entrada del usuario en:
      - originales:      lista de frases tal como las escribió el usuario
      - frases_norm:     lista de listas de palabras normalizadas

    Ejemplo:
      "cambio climatico, feminismo" →
        originales   = ["cambio climatico", "feminismo"]
        frases_norm  = [["cambio", "climatico"], ["feminismo"]]
    """
    originales = [p.strip() for p in entrada.split(",") if p.strip()]
    frases_norm = [
        [w for w in tokenizar(normalizar_texto(frase)) if w]
        for frase in originales
    ]
    # Descartar frases que quedaron vacías tras normalizar
    pares = [(o, f) for o, f in zip(originales, frases_norm) if f]
    if not pares:
        return [], []
    originales, frases_norm = zip(*pares)
    return list(originales), list(frases_norm)


# =====================================
# TRAZABILIDAD — segunda hoja del Excel
# =====================================

def frase_coincide_en_fila(fila: pd.Series, palabras_frase: list, modo: str) -> bool:
    """Verifica si una frase específica coincide en alguna columna objetivo de la fila."""
    for col in COLUMNAS_OBJETIVO:
        if col in fila.index:
            texto_norm = normalizar_texto(fila[col])
            if modo == "exacta":
                frase_completa = " ".join(palabras_frase)
                if re.search(rf"\b{re.escape(frase_completa)}\b", texto_norm):
                    return True
            else:
                if frase_coincide_en_texto(texto_norm, palabras_frase):
                    return True
    return False


def frases_coincidentes_en_fila(fila: pd.Series, originales: list,
                                  frases_norm: list, modo: str) -> str:
    """Retorna las frases originales que coincidieron en la fila."""
    encontradas = [
        orig for orig, frase in zip(originales, frases_norm)
        if frase_coincide_en_fila(fila, frase, modo)
    ]
    return ", ".join(encontradas)


def construir_hoja_palabras(df_filtrado: pd.DataFrame, originales: list,
                             frases_norm: list, modo: str) -> pd.DataFrame:
    if not originales:
        return pd.DataFrame({
            "Nota": ["No se aplicó filtro por palabras clave en esta búsqueda."]
        })

    cols_id = [c for c in ["NOMBRE INTERVENCION", "DEPARTAMENTO", "MUNICIPIO",
                            "NOMBRE ACTOR", "FECHA INICIAL"]
               if c in df_filtrado.columns]

    hoja = df_filtrado[cols_id].copy().reset_index(drop=True)
    hoja["Frases buscadas"] = ", ".join(originales)
    hoja["Modo de búsqueda"] = "Inteligente" if modo == "inteligente" else "Exacta"
    hoja["Frases que coincidieron"] = df_filtrado.apply(
        lambda fila: frases_coincidentes_en_fila(fila, originales, frases_norm, modo),
        axis=1
    ).values

    return hoja


# =====================================
# EXPORTACIÓN EXCEL (2 hojas)
# =====================================

def convertir_excel(df_resultados: pd.DataFrame, df_palabras: pd.DataFrame) -> BytesIO:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df_resultados.to_excel(writer, index=False, sheet_name="Resultados filtrados")
        df_palabras.to_excel(writer, index=False, sheet_name="Palabras clave por proyecto")

        for sheet_name, df_sheet in [
            ("Resultados filtrados", df_resultados),
            ("Palabras clave por proyecto", df_palabras),
        ]:
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(df_sheet.columns):
                ancho = max(
                    len(str(col)),
                    df_sheet[col].astype(str).str.len().max() if len(df_sheet) > 0 else 0
                )
                ws.set_column(i, i, min(ancho + 2, 60))

    buf.seek(0)
    return buf


# =====================================
# CONFIGURACIÓN DE LA APP
# =====================================

st.set_page_config(page_title="Buscador de Proyectos", layout="wide")

st.markdown("""
<style>
[data-testid="stDataFrameToolbar"] { display: none !important; }
.vega-actions { display: none !important; }
</style>
""", unsafe_allow_html=True)

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
# SIDEBAR — FILTROS
# =====================================

st.sidebar.header("Filtros de búsqueda")

entrada = st.sidebar.text_input("Palabras o frases clave")
st.sidebar.caption(
    "✏️ Separa los temas por comas. Cada tema puede tener varias palabras. "
    "Ejemplo: cambio climático, cuidado del medio ambiente, feminismo"
)

modo_busqueda = st.sidebar.radio(
    "Modo de búsqueda",
    options=["inteligente", "exacta"],
    format_func=lambda x: {
        "inteligente": "🧠 Inteligente (recomendado)",
        "exacta":      "🔍 Exacta — solo la palabra tal cual",
    }[x],
    index=0,
    help=(
        "**Inteligente**: cada tema separado por coma se busca con lógica AND "
        "(todas sus palabras deben aparecer en el proyecto). Entre temas distintos "
        "se usa OR (basta que uno coincida).\n\n"
        "✅ `cambio climatico` → el proyecto debe mencionar AMBAS palabras\n"
        "✅ `feminismo` → feminismos, transfeminismo, ecofeminismo\n"
        "✅ `cultura` → culturas, cultural, interculturalismo\n"
        "❌ `cultura` **NO** → agricultura\n\n"
        "**Exacta**: busca la frase literalmente tal como fue escrita."
    )
)

lista_anios = sorted(df["FECHA INICIAL"].dropna().dt.year.unique().astype(int))
anios = st.sidebar.multiselect("Años (fecha inicial)", ["Todos"] + lista_anios)

fecha_final_rango = None
if "FECHA FINAL" in df.columns:
    st.sidebar.markdown("### Rango de fecha finalización")
    min_fecha = df["FECHA FINAL"].min()
    max_fecha = df["FECHA FINAL"].max()
    fecha_final_rango = st.sidebar.date_input(
        "Selecciona rango",
        value=(min_fecha, max_fecha),
        min_value=min_fecha,
        max_value=max_fecha,
    )

lista_departamentos = sorted(df["DEPARTAMENTO"].dropna().unique())
departamentos = st.sidebar.multiselect("Departamento", ["Todos"] + lista_departamentos)

if "Todos" in departamentos or len(departamentos) == 0:
    municipios_base = df
else:
    municipios_base = df[df["DEPARTAMENTO"].isin(departamentos)]

lista_municipios = sorted(municipios_base["MUNICIPIO"].dropna().unique())
municipios = st.sidebar.multiselect("Municipio", ["Todos"] + lista_municipios)

def multiselect_columna(nombre_columna, label):
    if nombre_columna in df.columns:
        valores = sorted(df[nombre_columna].dropna().unique())
        return st.sidebar.multiselect(label, ["Todos"] + valores)
    return []

actor_2       = multiselect_columna("ACTOR SEGUNDO NIVEL",    "Actor segundo nivel")
origen_actor  = multiselect_columna("ORIGEN DEL ACTOR",       "Origen del actor")
nombre_actor  = multiselect_columna("NOMBRE ACTOR",           "Nombre actor")
ods           = multiselect_columna("ODS",                     "ODS")
estado_interv = multiselect_columna("ESTADO DE INTERVENCION", "Estado de intervención")

boton_buscar = st.sidebar.button("Buscar")

# =====================================
# PROCESAMIENTO
# =====================================

if boton_buscar:

    with st.spinner("🔄 Procesando búsqueda..."):

        df_filtrado = df.copy()

        # FILTRO FIJO: solo actores internacionales
        if "ACTOR PRIMER NIVEL" in df_filtrado.columns:
            df_filtrado = df_filtrado[
                df_filtrado["ACTOR PRIMER NIVEL"]
                .astype(str).str.lower().str.strip() == "internacional"
            ]

        # PALABRAS / FRASES CLAVE
        palabras_originales = []
        frases_normalizadas = []

        if entrada.strip():
            palabras_originales, frases_normalizadas = parsear_entrada(entrada)

            if frases_normalizadas:
                mascara = pd.Series(False, index=df_filtrado.index)
                for col in COLUMNAS_OBJETIVO:
                    if col in df_filtrado.columns:
                        serie_norm = df_filtrado[col].astype(str).apply(normalizar_texto)
                        mascara |= filtrar_por_palabras(serie_norm, frases_normalizadas, modo_busqueda)
                df_filtrado = df_filtrado[mascara]

        # FILTROS GENERALES
        def aplicar_filtro(df_in: pd.DataFrame, columna: str, seleccion: list) -> pd.DataFrame:
            if seleccion and "Todos" not in seleccion:
                return df_in[df_in[columna].isin(seleccion)]
            return df_in

        if anios and "Todos" not in anios:
            df_filtrado = df_filtrado[df_filtrado["FECHA INICIAL"].dt.year.isin(anios)]

        if (
            fecha_final_rango is not None
            and isinstance(fecha_final_rango, (list, tuple))
            and len(fecha_final_rango) == 2
            and "FECHA FINAL" in df_filtrado.columns
        ):
            f_ini, f_fin = fecha_final_rango
            df_filtrado = df_filtrado[
                (df_filtrado["FECHA FINAL"] >= pd.to_datetime(f_ini)) &
                (df_filtrado["FECHA FINAL"] <= pd.to_datetime(f_fin))
            ]

        df_filtrado = aplicar_filtro(df_filtrado, "DEPARTAMENTO",          departamentos)
        df_filtrado = aplicar_filtro(df_filtrado, "MUNICIPIO",              municipios)
        df_filtrado = aplicar_filtro(df_filtrado, "ACTOR SEGUNDO NIVEL",    actor_2)
        df_filtrado = aplicar_filtro(df_filtrado, "ORIGEN DEL ACTOR",       origen_actor)
        df_filtrado = aplicar_filtro(df_filtrado, "NOMBRE ACTOR",           nombre_actor)
        df_filtrado = aplicar_filtro(df_filtrado, "ODS",                    ods)
        df_filtrado = aplicar_filtro(df_filtrado, "ESTADO DE INTERVENCION", estado_interv)

        etiqueta = {"inteligente": "Inteligente", "exacta": "Exacta"}[modo_busqueda]
        st.success(f"Registros encontrados: {len(df_filtrado)}  |  Modo: {etiqueta}")

    # =====================================
    # TABLA PRINCIPAL
    # =====================================

    df_mostrar = df_filtrado.copy()
    if "VALOR APORTE (USD)" in df_mostrar.columns:
        df_mostrar["VALOR APORTE (USD)"] = df_mostrar["VALOR APORTE (USD)"].apply(formato_usd)

    st.subheader("Resultados filtrados")
    st.dataframe(df_mostrar, use_container_width=True)

    # =====================================
    # TABLAS DE AGRUPACIÓN
    # =====================================

    def mostrar_agrupado(columna: str, titulo: str):
        if columna in df_filtrado.columns and "VALOR APORTE (USD)" in df_filtrado.columns:
            agrupado = (
                df_filtrado.groupby(columna)["VALOR APORTE (USD)"]
                .sum().reset_index()
                .sort_values("VALOR APORTE (USD)", ascending=False)
            )
            n = len(agrupado)
            agrupado["VALOR APORTE (USD)"] = agrupado["VALOR APORTE (USD)"].apply(formato_usd)
            st.subheader(f"{titulo} ({n} {'registro' if n == 1 else 'registros'})")
            st.dataframe(agrupado, use_container_width=True)

    mostrar_agrupado("ORIGEN DEL ACTOR", "Monto total aportado por cooperante")
    mostrar_agrupado("DEPARTAMENTO",     "Monto total aportado por departamento")
    mostrar_agrupado("SECTORES GOB",     "Monto total aportado por sector de gobierno")

    # =====================================
    # GRÁFICAS
    # =====================================

    st.subheader("Evolución del monto aportado por año de inicio del proyecto")

    if "FECHA INICIAL" in df_filtrado.columns and "VALOR APORTE (USD)" in df_filtrado.columns:
        evolucion = (
            df_filtrado.dropna(subset=["FECHA INICIAL"])
            .assign(ANIO=lambda d: d["FECHA INICIAL"].dt.year)
            .groupby("ANIO")["VALOR APORTE (USD)"].sum()
            .reset_index().sort_values("ANIO")
        )
        if len(evolucion) > 0:
            chart = alt.Chart(evolucion).mark_bar().encode(
                x=alt.X("ANIO:O", title="Año de inicio"),
                y=alt.Y("VALOR APORTE (USD):Q", title="Monto total (USD)"),
                tooltip=[
                    alt.Tooltip("ANIO:O", title="Año"),
                    alt.Tooltip("VALOR APORTE (USD):Q", title="Monto (USD)", format=",.2f"),
                ]
            ).properties(height=400)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Sin datos de fecha inicial para graficar.")

    st.subheader("Top 10 por monto aportado")

    def grafica_barras(columna: str, titulo: str, etiqueta_eje: str):
        if columna in df_filtrado.columns and "VALOR APORTE (USD)" in df_filtrado.columns:
            datos = (
                df_filtrado.groupby(columna)["VALOR APORTE (USD)"]
                .sum().reset_index()
                .sort_values("VALOR APORTE (USD)", ascending=False)
                .head(10)
            )
            if len(datos) == 0:
                st.info(f"Sin datos para: {titulo}")
                return
            n_total = df_filtrado[columna].nunique()
            titulo_completo = (
                f"Top {len(datos)} de {n_total} {titulo}"
                if n_total > 10
                else f"{titulo} ({len(datos)} en total)"
            )
            chart = alt.Chart(datos).mark_bar().encode(
                x=alt.X(
                    columna, sort="-y", title=etiqueta_eje,
                    axis=alt.Axis(labelLimit=150, labelAngle=-35)
                ),
                y=alt.Y("VALOR APORTE (USD)", title="Monto total (USD)"),
                tooltip=[
                    alt.Tooltip(columna, title=etiqueta_eje),
                    alt.Tooltip("VALOR APORTE (USD)", title="Monto (USD)", format=",.2f"),
                ]
            ).properties(title=titulo_completo, height=400)
            st.altair_chart(chart, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        grafica_barras("ORIGEN DEL ACTOR", "cooperantes por monto aportado",  "Cooperante")
        grafica_barras("DEPARTAMENTO",     "departamentos por monto recibido", "Departamento")
    with col2:
        grafica_barras("ODS",              "ODS por monto aportado",           "ODS")

    # =====================================
    # DESCARGA (2 hojas)
    # =====================================

    df_palabras = construir_hoja_palabras(
        df_filtrado, palabras_originales, frases_normalizadas, modo_busqueda
    )

    st.download_button(
        "⬇️ Descargar Excel filtrado",
        data=convertir_excel(df_filtrado.copy(), df_palabras),
        file_name="BBDD_filtrada.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

else:
    st.info("Configura los filtros y presiona Buscar")
