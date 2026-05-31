"""
Dashboard de Inventario - Baserow
Streamlit Community Cloud
"""

import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────
API_TOKEN         = st.secrets["BASEROW_TOKEN"]   # en Streamlit Cloud usar secrets
BASE_URL          = "https://api.baserow.io"
TABLE_PRODUCTOS   = 995855
TABLE_MOVIMIENTOS = 995860

HEADERS = {
    "Authorization": f"Token {API_TOKEN}",
    "Content-Type": "application/json",
}

# ── Carga de datos ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)   # refresca cada 5 minutos
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
        "field_8790800": "fecha_movimiento",   # ajusta este field_id si cambia
    })

    # Limpiar link rows
    movimientos["producto"] = movimientos["producto"].apply(
        lambda x: x[0]["value"] if isinstance(x, list) and x else None
    )
    movimientos["tipo_movimiento"] = movimientos["tipo_movimiento"].apply(
        lambda x: x["value"] if isinstance(x, dict) and x else None
    )

    # Fecha y cantidad neta
    if "fecha_movimiento" in movimientos.columns:
        movimientos["fecha_movimiento"] = pd.to_datetime(
            movimientos["fecha_movimiento"], errors="coerce"
        )
        movimientos["mes"] = movimientos["fecha_movimiento"].dt.to_period("M").astype(str)

    movimientos["cantidad_neta"] = movimientos.apply(
        lambda x: x["cantidad_movimiento"]
        if x["tipo_movimiento"] == "Entrada"
        else -x["cantidad_movimiento"]
        if x["tipo_movimiento"] == "Salida"
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

# Estilo
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=DM+Mono&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .metric-card {
        background: #f8f9fb;
        border-radius: 12px;
        padding: 1.2rem 1.5rem;
        border-left: 4px solid #2563eb;
    }
    .metric-card h3 { font-size: 0.8rem; color: #6b7280; margin: 0; text-transform: uppercase; letter-spacing: .05em; }
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
total_entradas = df[df["tipo_movimiento"] == "Entrada"]["cantidad_movimiento"].sum()
total_salidas  = df[df["tipo_movimiento"] == "Salida"]["cantidad_movimiento"].sum()
stock_actual   = total_entradas - total_salidas
n_productos    = productos.shape[0]

c1, c2, c3, c4 = st.columns(4)
c1.markdown(f'<div class="metric-card"><h3>Stock actual</h3><p>{stock_actual:,.0f}</p></div>', unsafe_allow_html=True)
c2.markdown(f'<div class="metric-card"><h3>Total entradas</h3><p>{total_entradas:,.0f}</p></div>', unsafe_allow_html=True)
c3.markdown(f'<div class="metric-card"><h3>Total salidas</h3><p>{total_salidas:,.0f}</p></div>', unsafe_allow_html=True)
c4.markdown(f'<div class="metric-card"><h3>Productos</h3><p>{n_productos}</p></div>', unsafe_allow_html=True)

st.divider()

# ── Gráficas ───────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("Stock por producto")
    stock_prod = (
        df.groupby("producto")["cantidad_neta"].sum()
        .reset_index()
        .rename(columns={"cantidad_neta": "stock"})
        .sort_values("stock", ascending=True)
    )
    fig1 = px.bar(
        stock_prod, x="stock", y="producto", orientation="h",
        color="stock", color_continuous_scale="Blues",
        template="plotly_white",
    )
    fig1.update_layout(showlegend=False, coloraxis_showscale=False,
                       margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.subheader("Stock por bodega")
    stock_bodega = (
        df.groupby("bodega")["cantidad_neta"].sum()
        .reset_index()
        .rename(columns={"cantidad_neta": "stock"})
    )
    fig2 = px.pie(
        stock_bodega, names="bodega", values="stock",
        color_discrete_sequence=px.colors.sequential.Blues_r,
        template="plotly_white",
    )
    fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig2, use_container_width=True)

# Evolución mensual
if "mes" in df.columns:
    st.subheader("Movimientos por mes")
    mensual = (
        df.groupby(["mes", "tipo_movimiento"])["cantidad_movimiento"]
        .sum().reset_index()
    )
    fig3 = px.bar(
        mensual, x="mes", y="cantidad_movimiento", color="tipo_movimiento",
        barmode="group",
        color_discrete_map={"Entrada": "#2563eb", "Salida": "#ef4444"},
        template="plotly_white",
        labels={"cantidad_movimiento": "Cantidad", "mes": "Mes"},
    )
    fig3.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig3, use_container_width=True)

# ── Tabla detalle ──────────────────────────────────────────────────────────────
st.subheader("Detalle de movimientos")
cols_show = [c for c in ["fecha_movimiento","producto","bodega","tipo_movimiento","cantidad_movimiento","observaciones"] if c in df.columns]
st.dataframe(df[cols_show].sort_values("fecha_movimiento", ascending=False) if "fecha_movimiento" in df.columns else df[cols_show],
             use_container_width=True, hide_index=True)
