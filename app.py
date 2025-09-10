import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from ics import Calendar, Event
from sqlalchemy import create_engine

st.set_page_config(page_title="Across Mexico | Calendario", layout="wide")

# --- Persistencia (SQLite simple) ---
engine = create_engine("sqlite:///data.db")

def ensure_table():
    with engine.begin() as conn:
        conn.execute("""
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

def load_df():
    try:
        df = pd.read_sql("SELECT * FROM activities", engine)
        return df
    except Exception:
        return pd.DataFrame()

def upsert_row(row: dict):
    df = pd.DataFrame([row])
    with engine.begin() as conn:
        conn.execute("DELETE FROM activities WHERE activity_id = ?", (row["activity_id"],))
        df.to_sql("activities", conn, if_exists="append", index=False)

def delete_activity(activity_id: str):
    with engine.begin() as conn:
        conn.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))

def import_csv(path="sample_activities.csv"):
    df = pd.read_csv(path)
    with engine.begin() as conn:
        df.to_sql("activities", conn, if_exists="append", index=False)

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
    trips = ["(Todos)"] + sorted(df["trip_name"].dropna().unique().tolist()) if not df.empty else ["(Todos)"]
    trip_sel = st.selectbox("Filtrar por viaje", trips)
with colf2:
    sups = ["(Todos)"] + sorted(df["supplier_name"].dropna().unique().tolist()) if not df.empty else ["(Todos)"]
    sup_sel = st.selectbox("Filtrar por supplier", sups)
with colf3:
    status_opt = ["(Todos)"] + ["confirmado", "tentativo", "cancelado"]
    status_sel = st.selectbox("Filtrar por status", status_opt)

fdf = df.copy()
if trip_sel != "(Todos)":
    fdf = fdf[fdf["trip_name"] == trip_sel]
if sup_sel != "(Todos)":
    fdf = fdf[fdf["supplier_name"] == sup_sel]
if status_sel != "(Todos)":
    fdf = fdf[fdf["status"] == status_sel]

# --- Vista calendario (timeline) ---
st.subheader("Vista de cronograma (día/semana)")
if not fdf.empty:
    fdf["start_dt"] = pd.to_datetime(fdf["start_datetime"])
    fdf["end_dt"]   = pd.to_datetime(fdf["end_datetime"])
    row_label = st.radio("Agrupar filas por:", ["supplier_name", "trip_name"], horizontal=True, index=0)
    title_hover = ["title","trip_name","supplier_name","category","status","pax","guide_language","location","notes"]
    fig = px.timeline(
        fdf,
        x_start="start_dt", x_end="end_dt",
        y=row_label, color="category",
        hover_data=title_hover,
        title=None
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=500, margin=dict(t=20,b=20,l=20,r=20))
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
            supplier_id = st.text_input("Supplier ID", placeholder="S001")
        with c3:
            supplier_name = st.text_input("Supplier name", placeholder="Sibaria Tours / Mondrian")
            pax = st.number_input("PAX", min_value=0, value=2)
            guide_language = st.text_input("Idioma guía", value="EN")

        c4, c5 = st.columns(2)
        with c4:
            start_datetime = st.text_input("Inicio (YYYY-MM-DD HH:MM)", value=datetime.now().strftime("%Y-%m-%d 09:00"))
        with c5:
            end_datetime = st.text_input("Fin (YYYY-MM-DD HH:MM)", value=datetime.now().strftime("%Y-%m-%d 10:00"))

        location = st.text_input("Lugar", placeholder="CDMX / Oaxaca / GDL")
        notes = st.text_area("Notas", placeholder="Pedidos especiales, referencia de reserva, etc.")

        submitted = st.form_submit_button("Guardar/Actualizar")
        if submitted:
            if not activity_id.strip():
                st.error("Necesitás un ID de actividad único.")
            else:
                row = dict(
                    activity_id=activity_id.strip(),
                    trip_id=trip_id.strip(),
                    trip_name=trip_name.strip(),
                    supplier_id=supplier_id.strip(),
                    supplier_name=supplier_name.strip(),
                    title=title.strip(),
                    category=category,
                    start_datetime=start_datetime.strip(),
                    end_datetime=end_datetime.strip(),
                    location=location.strip(),
                    status=status,
                    pax=int(pax),
                    guide_language=guide_language.strip(),
                    notes=notes.strip()
                )
                try:
                    pd.to_datetime(row["start_datetime"])
                    pd.to_datetime(row["end_datetime"])
                    upsert_row(row)
                    st.success("Actividad guardada/actualizada.")
                except Exception as e:
                    st.error(f"Error guardando la actividad: {e}")

# Lista y borrar
if not df.empty:
    st.dataframe(fdf[[
        "activity_id","trip_name","supplier_name","title","category","start_datetime","end_datetime","status","pax","guide_language","location","notes"
    ]].sort_values("start_datetime"), use_container_width=True)

    del_id = st.text_input("ID a borrar")
    if st.button("Borrar actividad"):
        if del_id.strip():
            delete_activity(del_id.strip())
            st.warning(f"Actividad {del_id.strip()} borrada.")

# --- Export .ics por viaje ---
st.subheader("Exportar calendario (.ics)")
exp_trip = st.selectbox("Elegí el viaje para exportar", ["(Elegí)"] + sorted(df["trip_name"].dropna().unique().tolist()) if not df.empty else ["(Elegí)"])
if st.button("Exportar .ics") and exp_trip != "(Elegí)":
    tdf = df[df["trip_name"] == exp_trip].copy()
    if tdf.empty:
        st.error("Ese viaje no tiene actividades.")
    else:
        cal = Calendar()
        for _, r in tdf.iterrows():
            ev = Event()
            ev.name = f"{r['title']} — {r['supplier_name']}"
            ev.begin = pd.to_datetime(r["start_datetime"]).to_pydatetime()
            ev.end = pd.to_datetime(r["end_datetime"]).to_pydatetime()
            ev.location = r.get("location") or ""
            ev.description = f"Trip: {r['trip_name']} | Category: {r['category']} | Status: {r['status']} | PAX: {r['pax']} | Notes: {r.get('notes','')}"
            cal.events.add(ev)
        ics_str = str(cal)
        st.download_button(
            label=f"Descargar {exp_trip}.ics",
            data=ics_str,
            file_name=f"{exp_trip.replace(' ','_')}.ics",
            mime="text/calendar"
        )

