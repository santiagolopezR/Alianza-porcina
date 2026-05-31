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

@st.cache_data(ttl=60)
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

    productos = productos.rename(columns={
        "field_8720901": "codigo_producto",
        "field_8720903": "active",
        "field_8781326": "producto",
        "field_8790688": "movimientos_link",
    })

    movimientos = movimientos.rename(columns={
        "field_8720938": "id_movimiento",
        "field_8720939": "observaciones",
        "field_8790651": "bodega",
        "field_8790687": "producto",
        "field_8790782": "cantidad_movimiento",
        "field_8790788": "tipo_movimiento",
        "field_8795095": "fecha_movimiento",
    })

    # Limpiar link rows
    movimientos["producto"] = movimientos["producto"].apply(
        lambda x: x[0]["value"] if isinstance(x, list) and x else None
    )
    movimientos["tipo_movimiento"] = movimientos["tipo_movimiento"].apply(
        lambda x: x["value"] if isinstance(x, dict) and x else None
    )

    # Cantidad a número
    movimientos["cantidad_movimiento"] = pd.to_numeric(
        movimientos["cantidad_movimiento"], errors="coerce"
    ).fillna(0)

    # Fecha, mes y cantidad neta
    movimientos["fecha_movimiento"] = pd.to_datetime(
        movimientos["fecha_movimiento"], errors="coerce"
    )
    movimientos["mes"] = movimientos["fecha_movimiento"].dt.to_period("M").astype(str)

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
st.caption(f"Actualización automática cada 60 seg · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if st.button("🔄 Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

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

# 1. Entradas y salidas por producto y mes (barras agrupadas)
st.subheader("Entradas y salidas por producto")
ent_sal = (
    df.groupby(["mes", "producto", "tipo_movimiento"])["cantidad_movimiento"]
    .sum().reset_index()
)
fig_ent_sal = px.bar(
    ent_sal, x="producto", y="cantidad_movimiento",
    color="tipo_movimiento", barmode="group",
    facet_col="mes",
    color_discrete_map={"Entrada": "#2563eb", "Salida": "#ef4444"},
    template="plotly_white",
    labels={"cantidad_movimiento": "Cantidad", "producto": "Producto"},
)
fig_ent_sal.update_layout(margin=dict(l=0, r=0, t=40, b=0), legend_title="Tipo")
fig_ent_sal.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
st.plotly_chart(fig_ent_sal, use_container_width=True)

# 2. Stock acumulado hoy por producto (barras horizontales)
st.subheader("Stock actual por producto")
stock_hoy = (
    df.groupby("producto")["cantidad_neta"]
    .sum().reset_index()
    .rename(columns={"cantidad_neta": "stock"})
    .sort_values("stock", ascending=True)
)
fig_stock = px.bar(
    stock_hoy, x="stock", y="producto", orientation="h",
    color="stock",
    color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
    template="plotly_white",
    labels={"stock": "Stock", "producto": "Producto"},
    text="stock",
)
fig_stock.update_traces(textposition="outside")
fig_stock.update_layout(
    coloraxis_showscale=False,
    margin=dict(l=0, r=40, t=10, b=0),
)
st.plotly_chart(fig_stock, use_container_width=True)

# ── Tabla stock por bodega (sin filtros) ──────────────────────────────────────
st.subheader("Stock acumulado por bodega")
stock_bodega_total = (
    movimientos.groupby(["bodega", "producto"])["cantidad_neta"]
    .sum().reset_index()
    .rename(columns={"cantidad_neta": "stock"})
    .pivot_table(index="producto", columns="bodega", values="stock", aggfunc="sum", fill_value=0)
    .reset_index()
)
stock_bodega_total["Total"] = stock_bodega_total.iloc[:, 1:].sum(axis=1)
st.dataframe(stock_bodega_total, use_container_width=True, hide_index=True)

# ── Tabla detalle ──────────────────────────────────────────────────────────────
st.subheader("Detalle de movimientos")
cols_show = [c for c in ["fecha_movimiento", "producto", "bodega", "tipo_movimiento",
                          "cantidad_movimiento", "observaciones"] if c in df.columns]
df_show = df[cols_show].sort_values("fecha_movimiento", ascending=False)
st.dataframe(df_show, use_container_width=True, hide_index=True)
