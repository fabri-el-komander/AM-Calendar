# app.py — Calendario Operativo Across Mexico (Streamlit + SQLite)
# Compatible con SQLAlchemy 2.x

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from ics import Calendar, Event
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Across Mexico | Calendario", layout="wide")

# --- Persistencia (SQLite simple) ---
# check_same_thread=False para evitar bloqueos en entornos multihilo (Streamlit Cloud)
engine = create_engine("sqlite:///data.db", connect_args={"check_same_thread": False})

def ensure_table():
    """Crea la tabla activities si no existe (DDL con exec_driver_sql para SQLAlchemy 2.x)."""
    with engine.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY,
            trip_id TEXT,
            trip_name TEXT,
            supplier_id TEXT,
            supplier_name TEXT,
            title TEXT,
            category TEXT,
            start_datetime TEXT,
            end_datetime TEXT,
            location TEXT,
            status TEXT,
            pax INTEGER,
            guide_language TEXT,
            notes TEXT
        );
        """)

def load_df() -> pd.DataFrame:
    """Carga todas las actividades desde SQLite."""
    try:
        df = pd.read_sql("SELECT * FROM activities", engine)
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "activity_id","trip_id","trip_name","supplier_id","supplier_name","title","category",
            "start_datetime","end_datetime","location","status","pax","guide_language","notes"
        ])

def upsert_row(row: dict):
    """Borra por activity_id si existe y luego inserta la fila."""
    df = pd.DataFrame([row])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM activities WHERE activity_id = :id"), {"id": row["activity_id"]})
        df.to_sql("activities", conn, if_exists="append", index=False)

def delete_activity(activity_id: str):
    """Elimina una actividad por ID."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM activities WHERE activity_id = :id"), {"id": activity_id})

def import_csv(path="sample_activities.csv"):
    """Importa actividades desde un CSV (debe tener columnas compatibles)."""
    df = pd.read_csv(path)
    with engine.begin() as conn:
        df.to_sql("activities", conn, if_exists="append", index=False)

# ---- Init
ensure_table()

# --- Sidebar: carga inicial ---
with st.sidebar:
    st.header("Datos")
    if st.button("Cargar CSV de ejemplo"):
        try:
            import_csv()
            st.success("Se cargaron actividades de ejemplo.")
        except Exception as e:
            st.error(f"No se pudo cargar el CSV: {e}")
    st.markdown("---")
    st.caption("Tip: Podés exportar por viaje a .ics abajo.")

st.title("📆 Calendario Operativo — Across Mexico")

df = load_df()

# --- Filtros ---
colf1, colf2, colf3 = st.columns([1,1,1])
with colf1:
    trips = ["(Todos)"] + (sorted(df["trip_name"].dropna().unique().tolist()) if not df.empty else [])
    trip_sel = st.selectbox("Filtrar por viaje", trips if trips else ["(Todos)"])
with colf2:
    sups = ["(Todos)"] + (sorted(df["supplier_name"].dropna().unique().tolist()) if not df.empty else [])
    sup_sel = st.selectbox("Filtrar por supplier", sups if sups else ["(Todos)"])
with colf3:
    status_opt = ["(Todos)", "confirmado", "tentativo", "cancelado"]
    status_sel = st.selectbox("Filtrar por status", status_opt)

fdf = df.copy()
if not fdf.empty:
    if trip_sel != "(Todos)":
        fdf = fdf[fdf["trip_name"] == trip_sel]
    if sup_sel != "(Todos)":
        fdf = fdf[fdf["supplier_name"] == sup_sel]
    if status_sel != "(Todos)":
        fdf = fdf[fdf["status"] == status_sel]

# --- Vista calendario (timeline) ---
st.subheader("Vista de cronograma (día/semana)")
if not fdf.empty:
    # Asegurar datetimes
    try:
        fdf["start_dt"] = pd.to_datetime(fdf["start_datetime"])
        fdf["end_dt"]   = pd.to_datetime(fdf["end_datetime"])
    except Exception as e:
        st.error(f"Error parseando fechas: {e}")
        fdf["start_dt"] = fdf["start_datetime"]
        fdf["end_dt"]   = fdf["end_datetime"]

    # Elegí cómo agrupar: por supplier o por viaje
    row_label = st.radio("Agrupar filas por:", ["supplier_name", "trip_name"], horizontal=True, index=0)
    title_hover = ["title","trip_name","supplier_name","category","status","pax","guide_language","location","notes"]

    fig = px.timeline(
        fdf,
        x_start="start_dt", x_end="end_dt",
        y=row_label, color="category",
        hover_data=title_hover,
        title=None
    )
    fig.update_yaxes(autorange="reversed")  # estilo Gantt
    fig.update_layout(height=500, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay actividades (todavía). Cargá el CSV de ejemplo o creá una nueva.")

# --- Tabla editable / creación rápida ---
st.subheader("Actividades")
with st.expander("Agregar / editar actividad"):
    with st.form("activity_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            activity_id = st.text_input("ID actividad (único)", placeholder="A1001")
            title = st.text_input("Título", placeholder="City Tour / Check-in / Transfer")
            category = st.selectbox("Categoría", ["transfer","tour","checkin","checkout","meal","experience","other"])
            status = st.selectbox("Status", ["confirmado","tentativo","cancelado"], index=0)
        with c2:
            trip_id = st.text_input("Trip ID", placeholder="T001")
            trip_name = st.text_input("Trip name", placeholder="Family X / Arturo Sánchez")
            supplier_id = s_

