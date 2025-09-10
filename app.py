# app.py — Calendario Operativo Across Mexico (Streamlit + SQLite)
# Exporta por viaje y por supplier (PDF/CSV/XLSX/ICS) + Calendario mensual sin solapes
# Compatible con SQLAlchemy 2.x

import io
import calendar as cal
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

# ---------- Helpers export (viaje) ----------
def build_ics(title: str, df: pd.DataFrame) -> str:
    cal_out = Calendar()
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
        cal_out.events.add(ev)
    return str(cal_out)

def build_csv(df: pd.DataFrame) -> bytes:
    return df.sort_values("start_datetime").to_csv(index=False).encode("utf-8")

def build_xlsx_trip(df: pd.DataFrame) -> bytes:
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
        ws.set_column(0, 0, 12); ws.set_column(1, 2, 8)
        ws.set_column(3, 3, 30); ws.set_column(4, 6, 18)
        ws.set_column(7, 8, 10); ws.set_column(9, 9, 40)
    out.seek(0)
    return out.getvalue()

def build_pdf_trip(title: str, df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Agenda — {title}", styles["Heading1"]), Spacer(1, 8)]
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
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    story.append(table); doc.build(story); pdf = buf.getvalue(); buf.close(); return pdf

# ---------- Helpers export (supplier) ----------
def filter_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    sdt = pd.to_datetime(df["start_datetime"])
    return df[(sdt.dt.year == year) & (sdt.dt.month == month)]

def build_xlsx_supplier(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        df2 = df.copy()
        df2["Fecha"] = pd.to_datetime(df2["start_datetime"]).dt.date
        df2["Inicio"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%H:%M")
        df2["Fin"] = pd.to_datetime(df2["end_datetime"]).dt.strftime("%H:%M")
        cols = ["Fecha","Inicio","Fin","trip_name","title","location","status","pax","guide_language","notes"]
        df2 = df2[cols]
        df2.columns = ["Fecha","Inicio","Fin","Trip","Actividad","Lugar","Status","PAX","Idioma","Notas"]
        df2.to_excel(writer, index=False, sheet_name="Supplier")
        ws = writer.sheets["Supplier"]
        ws.set_column(0, 0, 12); ws.set_column(1, 2, 8)
        ws.set_column(3, 3, 24); ws.set_column(4, 4, 28)
        ws.set_column(5, 7, 14); ws.set_column(8, 9, 36)
    out.seek(0)
    return out.getvalue()

def build_pdf_supplier(title: str, df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Agenda Supplier — {title}", styles["Heading1"]), Spacer(1, 8)]
    df2 = df.copy()
    df2["Fecha"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%Y-%m-%d")
    df2["Inicio"] = pd.to_datetime(df2["start_datetime"]).dt.strftime("%H:%M")
    df2["Fin"] = pd.to_datetime(df2["end_datetime"]).dt.strftime("%H:%M")
    cols = ["Fecha","Inicio","Fin","trip_name","title","location","status","pax","guide_language","notes"]
    df2 = df2[cols]
    data = [["Fecha","Inicio","Fin","Trip","Actividad","Lugar","Status","PAX","Idioma","Notas"]] + df2.values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1b4332")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONTNAME", (0,1), (-1,-1), "Helvetica"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
    ]))
    story.append(table); doc.build(story); pdf = buf.getvalue(); buf.close(); return pdf

def build_ics_supplier(title: str, df: pd.DataFrame) -> str:
    cal_out = Calendar()
    for _, r in df.iterrows():
        ev = Event()
        ev.name = f"{r['trip_name']}: {r['title']}"
        ev.begin = pd.to_datetime(r["start_datetime"]).to_pydatetime()
        ev.end   = pd.to_datetime(r["end_datetime"]).to_pydatetime()
        ev.location = r.get("location") or ""
        ev.description = f"Supplier: {r['supplier_name']} | Status: {r['status']} | PAX: {r['pax']} | Notes: {r.get('notes','')}"
        cal_out.events.add(ev)
    return str(cal_out)

# ---------- Calendario mensual sin solapes ----------
def month_calendar_figure(df: pd.DataFrame, suppliers: list[str], year: int, month: int, max_lines:int=6) -> go.Figure:
    df = df.copy()
    df["start_dt"] = pd.to_datetime(df["start_datetime"])
    df = df[(df["start_dt"].dt.year == year) & (df["start_dt"].dt.month == month)]
    if suppliers:
        df = df[df["supplier_name"].isin(suppliers)]

    # Lista por día
    by_day = {}
    for _, r in df.sort_values("start_dt").iterrows():
        d = int(r["start_dt"].day)
        hora = r["start_dt"].strftime("%H:%M")
        line = f"{r['supplier_name']}: {hora} {r['title']}"
        by_day.setdefault(d, []).append(line)

    weeks = cal.monthcalendar(year, month)  # 0 = vacío
    rows = len(weeks)
    fig = go.Figure()

    for r_idx, week in enumerate(weeks):
        for c_idx, day in enumerate(week):
            x0, x1 = c_idx, c_idx + 1
            y0, y1 = rows - r_idx - 1, rows - r_idx
            fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, line=dict(color="#A0A0A0"))
            if day != 0:
                # Número de día
                fig.add_annotation(
                    x=x0 + 0.02, y=y1 - 0.08, xanchor="left", yanchor="top",
                    text=f"<b>{day}</b>", showarrow=False, font=dict(size=12)
                )
                eventos = by_day.get(day, [])
                if eventos:
                    # Altura útil dentro de la celda
                    usable = (y1 - y0) - 0.22
                    step = usable / max_lines
                    max_show = min(len(eventos), max_lines)
                    for j in range(max_show):
                        y_line = y1 - 0.20 - j*step
                        fig.add_annotation(
                            x=x0 + 0.02, y=y_line, xanchor="left", yanchor="top",
                            text=eventos[j], showarrow=False, align="left", font=dict(size=10)
                        )
                    if len(eventos) > max_show:
                        fig.add_annotation(
                            x=x1 - 0.02, y=y0 + 0.02, xanchor="right", yanchor="bottom",
                            text=f"+{len(eventos)-max_show} más", showarrow=False, font=dict(size=9, color="gray")
                        )

    fig.update_xaxes(visible=False, range=[0, 7])
    fig.update_yaxes(visible=False, range=[0, rows])
    month_name = cal.month_name[month]
    sup_label = ", ".join(suppliers) if suppliers else "Todos"
    # Alto adaptativo por filas
    fig.update_layout(
        height=rows * 240, width=1200,
        margin=dict(l=10, r=10, t=50, b=10),
        title=f"Calendario mensual — {month_name} {year} · {sup_label}"
    )
    return fig

def month_calendar_png(fig: go.Figure) -> bytes:
    return fig.to_image(format="png", scale=2)  # requiere 'kaleido'

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
    st.caption("Exportá por viaje o por supplier. Abajo: calendario mensual por supplier.")

st.title("📆 Calendario Operativo — Across Mexico")

df = load_df()

# --- Filtros rápidos para timeline ---
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

# --- Vista timeline (día/semana) ---
st.subheader("Vista de cronograma (día/semana)")
if not fdf.empty:
    try:
        fdf["start_dt"] = pd.to_datetime(fdf["start_datetime"])
        fdf["end_dt"]   = pd.to_datetime(fdf["end_datetime"])
    except Exception as e:
        st.error(f"Error parseando fechas: {e}")
        fdf["start_dt"] = fdf["start_datetime"]; fdf["end_dt"] = fdf["end_datetime"]

    row_label = st.radio("Agrupar filas por:", ["supplier_name", "trip_name"], horizontal=True, index=0)
    title_hover = ["title","trip_name","supplier_name","category","status","pax","guide_language","location","notes"]
    fig_tl = px.timeline(
        fdf, x_start="start_dt", x_end="end_dt",
        y=row_label, color="category", hover_data=title_hover, title=None
    )
    fig_tl.update_yaxes(autorange="reversed")
    fig_tl.update_layout(height=500, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig_tl, use_container_width=True)
else:
    st.info("No hay actividades (todavía). Cargá el CSV de ejemplo o creá una nueva.")

# --- Form de carga/edición ---
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
            trip_name = st.text_input("Trip name", placeholder="Arturo Sánchez / Matt Wallach")
            supplier_id = st.text_input("Supplier ID", placeholder="S_ETIEN / S_GABY / S_CASA / S_MOND")
        with c3:
            supplier_name = st.text_input("Supplier name", placeholder="Etien / Gaby / Casona Roma Norte / Mondrian Condesa")
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
                    pd.to_datetime(row["start_datetime"]); pd.to_datetime(row["end_datetime"])
                    upsert_row(row); st.success("Actividad guardada/actualizada.")
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
            delete_activity(del_id.strip()); st.warning(f"Actividad {del_id.strip()} borrada.")

# --- Calendario mensual por supplier ---
st.subheader("Calendario mensual por supplier (sin solapes)")
if df.empty:
    st.info("Cargá actividades para ver el mensual.")
else:
    today = datetime.now()
    colm, coly, cols = st.columns([1,1,2])
    with colm:
        month = st.selectbox("Mes", list(range(1,13)), index=today.month-1, format_func=lambda m: cal.month_name[m])
    with coly:
        year = st.number_input("Año", min_value=2024, max_value=2030, value=today.year)
    with cols:
        sup_options = sorted(df["supplier_name"].dropna().unique().tolist())
        default_sup = [s for s in ["Mondrian Condesa","Gaby","Etien","Casona Roma Norte"] if s in sup_options]
        sel_sups = st.multiselect("Suppliers", sup_options, default=default_sup)

    fig_month = month_calendar_figure(df, sel_sups, int(year), int(month), max_lines=6)
    st.plotly_chart(fig_month, use_container_width=True)

    # Descarga PNG del mensual
    try:
        st.download_button(
            label="Descargar calendario mensual (PNG)",
            data=month_calendar_png(fig_month),
            file_name=f"calendario_{cal.month_name[month]}_{year}.png",
            mime="image/png",
            use_container_width=True
        )
    except Exception as e:
        st.info(f"No se pudo generar la imagen (instalá 'kaleido' en requirements). Detalle: {e}")

# --- Exportar por viaje ---
st.subheader("Exportar viaje")
exp_trip = st.selectbox(
    "Elegí el viaje", ["(Elegí)"] + (sorted(df["trip_name"].dropna().unique().tolist()) if not df.empty else [])
)
if exp_trip != "(Elegí)" and not df.empty:
    tdf = df[df["trip_name"] == exp_trip].copy()
    if tdf.empty:
        st.error("Ese viaje no tiene actividades.")
    else:
        st.download_button(f"Descargar {exp_trip}.ics", build_ics(exp_trip, tdf),
                           file_name=f"{exp_trip.replace(' ','_')}.ics", mime="text/calendar", use_container_width=True)
        st.download_button(f"Descargar {exp_trip}.csv", build_csv(tdf),
                           file_name=f"{exp_trip.replace(' ','_')}.csv", mime="text/csv", use_container_width=True)
        st.download_button(f"Descargar {exp_trip}.xlsx", build_xlsx_trip(tdf),
                           file_name=f"{exp_trip.replace(' ','_')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        st.download_button(f"Descargar {exp_trip}.pdf (Agenda)", build_pdf_trip(exp_trip, tdf),
                           file_name=f"{exp_trip.replace(' ','_')}.pdf", mime="application/pdf", use_container_width=True)

# --- Exportar agenda por supplier ---
st.subheader("Exportar agenda por supplier (por mes)")
if df.empty:
    st.info("Cargá actividades para exportar por supplier.")
else:
    colsa, colsb, colsc = st.columns([2,1,1])
    with colsa:
        sup_sel2 = st.selectbox("Supplier", sorted(df["supplier_name"].dropna().unique().tolist()))
    with colsb:
        month2 = st.selectbox("Mes (supplier)", list(range(1,13)), index=datetime.now().month-1,
                              format_func=lambda m: cal.month_name[m])
    with colsc:
        year2 = st.number_input("Año (supplier)", min_value=2024, max_value=2030, value=datetime.now().year)

    sdf = df[df["supplier_name"] == sup_sel2].copy()
    sdf = filter_month(sdf, int(year2), int(month2)).sort_values("start_datetime")

    if sdf.empty:
        st.warning("Ese supplier no tiene servicios en el mes seleccionado.")
    else:
        st.download_button(f"Descargar {sup_sel2}.ics", build_ics_supplier(sup_sel2, sdf),
                           file_name=f"{sup_sel2.replace(' ','_')}_{cal.month_name[month2]}_{year2}.ics",
                           mime="text/calendar", use_container_width=True)
        st.download_button(f"Descargar {sup_sel2}.csv", build_csv(sdf),
                           file_name=f"{sup_sel2.replace(' ','_')}_{cal.month_name[month2]}_{year2}.csv",
                           mime="text/csv", use_container_width=True)
        st.download_button(f"Descargar {sup_sel2}.xlsx", build_xlsx_supplier(sdf),
                           file_name=f"{sup_sel2.replace(' ','_')}_{cal.month_name[month2]}_{year2}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
        st.download_button(f"Descargar {sup_sel2}.pdf (Agenda supplier)", build_pdf_supplier(sup_sel2, sdf),
                           file_name=f"{sup_sel2.replace(' ','_')}_{cal.month_name[month2]}_{year2}.pdf",
                           mime="application/pdf", use_container_width=True)
