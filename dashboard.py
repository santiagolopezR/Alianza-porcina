"""
Dashboard de Inventario - Baserow
Streamlit Community Cloud
"""

import requests
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────
API_TOKEN         = st.secrets["BASEROW_TOKEN"]
BASE_URL          = "https://api.baserow.io"
TABLE_PRODUCTOS   = 995855
TABLE_MOVIMIENTOS = 995860

HEADERS = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# ── Carga de datos ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def cargar_tabla(table_id: int) -> pd.DataFrame:
    filas, pagina = [], 1
    while True:
        r = requests.get(
            f"{BASE_URL}/api/database/rows/table/{table_id}/",
            headers=HEADERS,
            params={"page": pagina, "size": 200},
        )
        r.raise_for_status()
        data = r.json()
        filas.extend(data["results"])
        if not data["next"]:
            break
        pagina += 1
    return pd.DataFrame(filas)


def preparar_datos():
    productos   = cargar_tabla(TABLE_PRODUCTOS)
    movimientos = cargar_tabla(TABLE_MOVIMIENTOS)

    # Renombrar productos
    productos = productos.rename(columns={
        "field_8720901": "codigo_producto",
        "field_8720903": "active",
        "field_8781326": "producto",
        "field_8790688": "movimientos_link",
    })

    # Renombrar movimientos
    movimientos = movimientos.rename(columns={
        "field_8720938": "id_movimiento",
        "field_8720939": "observaciones",
        "field_8790651": "bodega",
        "field_8790687": "producto",
        "field_8790782": "cantidad_movimiento",
        "field_8790788": "tipo_movimiento",
    })

    # Detectar columna fecha automáticamente
    fecha_col = [c for c in movimientos.columns if "fecha" in c.lower()]
    if fecha_col:
        movimientos = movimientos.rename(columns={fecha_col[0]: "fecha_movimiento"})

    # Limpiar link rows
    movimientos["producto"] = movimientos["producto"].apply(
        lambda x: x[0]["value"] if isinstance(x, list) and x else None
    )
    movimientos["tipo_movimiento"] = movimientos["tipo_movimiento"].apply(
        lambda x: x["value"] if isinstance(x, dict) and x else None
    )

    # Convertir cantidad a número
    movimientos["cantidad_movimiento"] = pd.to_numeric(
        movimientos["cantidad_movimiento"], errors="coerce"
    ).fillna(0)

    # Fecha y mes
    if "fecha_movimiento" in movimientos.columns:
        movimientos["fecha_movimiento"] = pd.to_datetime(
            movimientos["fecha_movimiento"], errors="coerce"
        )
        movimientos["mes"] = movimientos["fecha_movimiento"].dt.to_period("M").astype(str)

    # Cantidad neta
    movimientos["cantidad_neta"] = movimientos.apply(
        lambda x:  x["cantidad_movimiento"] if x["tipo_movimiento"] == "Entrada"
        else      -x["cantidad_movimiento"] if x["tipo_movimiento"] == "Salida"
        else 0,
        axis=1,
    )

    return productos, movimientos


# ── App ────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Inventario Bodegas",
    page_icon="📦",
    layout="wide",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .metric-card {
        background: #f8f9fb;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        border-left: 4px solid #2563eb;
        margin-bottom: 0.5rem;
    }
    .metric-card h3 { font-size: 0.78rem; color: #6b7280; margin: 0; text-transform: uppercase; letter-spacing: .06em; }
    .metric-card p  { font-size: 2rem; font-weight: 700; color: #111827; margin: 0; }
</style>
""", unsafe_allow_html=True)

st.title("📦 Inventario de Bodegas")
st.caption(f"Actualización automática cada 5 min · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

with st.spinner("Cargando datos desde Baserow..."):
    try:
        productos, movimientos = preparar_datos()
    except Exception as e:
        st.error(f"Error conectando a Baserow: {e}")
        st.stop()

# ── Sidebar filtros ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filtros")
    bodegas = ["Todas"] + sorted(movimientos["bodega"].dropna().unique().tolist())
    bodega_sel = st.selectbox("Bodega", bodegas)

    prods = ["Todos"] + sorted(movimientos["producto"].dropna().unique().tolist())
    prod_sel = st.selectbox("Producto", prods)

df = movimientos.copy()
if bodega_sel != "Todas":
    df = df[df["bodega"] == bodega_sel]
if prod_sel != "Todos":
    df = df[df["producto"] == prod_sel]

# ── KPIs ───────────────────────────────────────────────────────────────────────
stock_actual = df["cantidad_neta"].sum()
n_productos  = productos.shape[0]

c1, c2 = st.columns(2)
c1.markdown(f'<div class="metric-card"><h3>Stock actual</h3><p>{stock_actual:,.0f}</p></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="metric-card"><h3>Productos</h3><p>{n_productos}</p></div>', unsafe_allow_html=True)

st.divider()

# ── Gráficas ───────────────────────────────────────────────────────────────────

# Stock por bodega (torta)
st.subheader("Stock por bodega")
stock_bodega = (
    df.groupby("bodega")["cantidad_neta"].sum()
    .reset_index()
    .rename(columns={"cantidad_neta": "stock"})
)
fig_bodega = px.pie(
    stock_bodega, names="bodega", values="stock",
    color_discrete_sequence=px.colors.sequential.Blues_r,
    template="plotly_white",
)
fig_bodega.update_layout(margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig_bodega, use_container_width=True)

# Evolución mensual de movimientos (barras agrupadas)
if "mes" in df.columns:
    st.subheader("Movimientos por mes")
    mensual = (
        df.groupby(["mes", "tipo_movimiento"])["cantidad_movimiento"]
        .sum().reset_index()
    )
    fig_mens = px.bar(
        mensual, x="mes", y="cantidad_movimiento", color="tipo_movimiento",
        barmode="group",
        color_discrete_map={"Entrada": "#2563eb", "Salida": "#ef4444"},
        template="plotly_white",
        labels={"cantidad_movimiento": "Cantidad", "mes": "Mes"},
    )
    fig_mens.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_mens, use_container_width=True)

    # Stock acumulado por producto en el tiempo
    st.subheader("Stock acumulado por producto")
    stock_tiempo = (
        df.groupby(["mes", "producto"])["cantidad_neta"]
        .sum()
        .reset_index()
        .sort_values("mes")
    )
    # Acumular por producto
    stock_tiempo["stock_acumulado"] = (
        stock_tiempo.groupby("producto")["cantidad_neta"].cumsum()
    )
    fig_acum = px.line(
        stock_tiempo, x="mes", y="stock_acumulado", color="producto",
        markers=True,
        template="plotly_white",
        labels={"stock_acumulado": "Stock", "mes": "Mes", "producto": "Producto"},
    )
    fig_acum.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig_acum, use_container_width=True)

# ── Tabla detalle ──────────────────────────────────────────────────────────────
st.subheader("Detalle de movimientos")
cols_show = [c for c in ["fecha_movimiento", "producto", "bodega", "tipo_movimiento",
                          "cantidad_movimiento", "observaciones"] if c in df.columns]
df_show = df[cols_show]
if "fecha_movimiento" in df_show.columns:
    df_show = df_show.sort_values("fecha_movimiento", ascending=False)
st.dataframe(df_show, use_container_width=True, hide_index=True)
