# app.py — Calendario Operativo Across Mexico (Streamlit + SQLite)
# Exports: ICS, CSV, XLSX, PDF (agenda) y PNG del timeline
# Compatible con SQLAlchemy 2.x

import io
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from ics import Calendar, Event
from sqlalchemy import create_engine, text
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

st.set_page_config(page_title="Across Mexico | Calendario", layout="wide")

# --- Persistencia (SQLite simple) ---
engine = create_engine("sqlite:///data.db", connect_args={"check_same_thread": False})

def ensure_table():
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
    try:
        return pd.read_sql("SELECT * FROM activities", engine)
    except Exception:
        return pd.DataFrame(columns=[
            "activity_id","trip_id","trip_name","supplier_id","supplier_name","title","category",
            "start_datetime","end_datetime","location","status","pax","guide_language","notes"
        ])

def upsert_row(row: dict):
    df = pd.DataFrame([row])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM activities WHERE activity_id = :id"), {"id": row["activity_id"]})
        df.to_sql("activities", conn, if_exists="append", index=False)

def delete_activity(activity_id: str):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM activities WHERE activity_id = :id"), {"id": activity_id})

def import_csv(path="sample_activities.csv"):
    df = pd.read_csv(path)
    with engine.begin() as conn:
        df.to_sql("activities", conn, if_exists="append", index=False)

# ---------- Helpers de export ----------
def build_ics(trip_name: str, df: pd.DataFrame) -> str:
    cal = Calendar()
    for _, r in df.iterrows():
        ev = Event()
        ev.name = f"{r['title']} — {r['supplier_name']}"
        ev.begin = pd.to_datetime(r["start_datetime"]).to_pydatetime()
        ev.end   = pd.to_datetime(r["end_datetime"]).to_pydatetime()
        ev.location = r.get("location") or ""
        ev.description = (
            f"Trip: {r['trip_name']} | Category: {r['category']} | "
            f"Status: {r['status']} | PAX: {r['pax']} | Notes: {r.get('notes','')}"
        )
        cal.events.add(ev)
    return str(cal)

def build_csv(df: pd.DataFrame) -> bytes:
    return df.sort_values("start_datetime").to_csv(index=False).encode("utf-8")

def build_xlsx(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df2 = df.copy()
        df2["Fecha"] = pd.to_datetime(df2["start_datetime"]).dt.date
        df2["Inicio"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%H:%M")
        df2["Fin"] = pd.to_datetime(df2["end_datetime"]).dt.strftime("%H:%M")
        cols = ["Fecha","Inicio","Fin","title","supplier_name","location","status","pax","guide_language","notes"]
        df2 = df2[cols]
        df2.columns = ["Fecha","Inicio","Fin","Actividad","Supplier","Lugar","Status","PAX","Idioma","Notas"]
        df2.to_excel(writer, index=False, sheet_name="Agenda")
        ws = writer.sheets["Agenda"]
        ws.set_column(0, 0, 12)
        ws.set_column(1, 2, 8)
        ws.set_column(3, 3, 28)
        ws.set_column(4, 6, 16)
        ws.set_column(7, 8, 10)
        ws.set_column(9, 9, 40)
    out.seek(0)
    return out.getvalue()

def build_pdf_agenda(trip_name: str, df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Agenda — {trip_name}", styles["Heading1"]))
    story.append(Spacer(1, 8))

    df2 = df.copy()
    df2["Fecha"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%Y-%m-%d")
    df2["Inicio"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%H:%M")
    df2["Fin"] = pd.to_datetime(df2["end_datetime"]).dt.strftime("%H:%M")
    cols = ["Fecha","Inicio","Fin","title","supplier_name","location","status","pax","guide_language","notes"]
    df2 = df2[cols]
    data = [["Fecha","Inicio","Fin","Actividad","Supplier","Lugar","Status","PAX","Idioma","Notas"]] + df2.values.tolist()

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#222")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 10),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,1), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(table)
    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf

def build_png_timeline(df: pd.DataFrame) -> bytes:
    df = df.copy()
    df["start_dt"] = pd.to_datetime(df["start_datetime"])
    df["end_dt"]   = pd.to_datetime(df["end_datetime"])
    fig = px.timeline(
        df, x_start="start_dt", x_end="end_dt",
        y="supplier_name", color="category",
        hover_data=["title","trip_name","supplier_name","category","status","pax","guide_language","location","notes"]
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=600, width=1400, margin=dict(t=20,b=20,l=20,r=20))
    # requiere 'kaleido' en requirements
    return fig.to_image(format="png", scale=2)

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
    st.caption("Tip: Exportá el viaje a ICS/CSV/XLSX/PDF/PNG más abajo.")

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
    try:
        fdf["start_dt"] = pd.to_datetime(fdf["start_datetime"])
        fdf["end_dt"]   = pd.to_datetime(fdf["end_datetime"])
    except Exception as e:
        st.error(f"Error parseando fechas: {e}")
        fdf["start_dt"] = fdf["start_datetime"]
        fdf["end_dt"]   = fdf["end_datetime"]

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
    st.dataframe(
        fdf[[
            "activity_id","trip_name","supplier_name","title","category",
            "start_datetime","end_datetime","status","pax","guide_language","location","notes"
        ]].sort_values("start_datetime"),
        use_container_width=True
    )

    del_id = st.text_input("ID a borrar")
    if st.button("Borrar actividad"):
        if del_id.strip():
            delete_activity(del_id.strip())
            st.warning(f"Actividad {del_id.strip()} borrada.")

# --- Export Center ---
st.subheader("Exportar viaje")
exp_trip = st.selectbox(
    "Elegí el viaje para exportar",
    ["(Elegí)"] + (sorted(df["trip_name"].dropna().unique().tolist()) if not df.empty else [])
)

if exp_trip != "(Elegí)" and not df.empty:
    tdf = df[df["trip_name"] == exp_trip].copy()
    if tdf.empty:
        st.error("Ese viaje no tiene actividades.")
    else:
        # ICS
        ics_str = build_ics(exp_trip, tdf)
        st.download_button(
            label=f"Descargar {exp_trip}.ics",
            data=ics_str,
            file_name=f"{exp_trip.replace(' ','_')}.ics",
            mime="text/calendar",
            use_container_width=True
        )
        # CSV
        st.download_button(
            label=f"Descargar {exp_trip}.csv",
            data=build_csv(tdf),
            file_name=f"{exp_trip.replace(' ','_')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        # XLSX
        st.download_button(
            label=f"Descargar {exp_trip}.xlsx",
            data=build_xlsx(tdf),
            file_name=f"{exp_trip.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        # PDF (agenda)
        st.download_button(
            label=f"Descargar {exp_trip}.pdf (Agenda)",
            data=build_pdf_agenda(exp_trip, tdf),
            file_name=f"{exp_trip.replace(' ','_')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        # PNG (timeline)
        try:
            png_bytes = build_png_timeline(tdf)
            st.download_button(
                label=f"Descargar {exp_trip}.png (Cronograma)",
                data=png_bytes,
                file_name=f"{exp_trip.replace(' ','_')}.png",
                mime="image/png",
                use_container_width=True
            )
        except Exception as e:
            st.info(f"No se pudo generar la imagen del cronograma (instalá 'kaleido' en requirements). Detalle: {e}")

