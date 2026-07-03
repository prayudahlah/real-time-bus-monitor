import streamlit as st
import pandas as pd
from utils.data_loader import load_routes, load_headsigns, load_schedule, load_route_descriptions
from utils.styling import inject_custom_css

inject_custom_css()

st.markdown("<h1 style='margin-bottom:0;'>Jadwal Bus</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#A78425; margin-top:-8px;'>"
    "Jadwal keberangkatan & kedatangan berdasarkan data GTFS</p>",
    unsafe_allow_html=True,
)

routes = load_routes()
route_desc = load_route_descriptions()

if not routes:
    st.warning("Data jadwal belum tersedia. Jalankan batch pipeline untuk memuat data GTFS.")
    st.stop()

# ─── Filters ──────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1.5, 2, 2], gap="medium")
with col1:
    sel_route = st.selectbox("Route", routes, key="jadwal_route")
with col2:
    headsigns = ["Semua Arah"] + load_headsigns(sel_route)
    sel_headsign = st.selectbox("Arah / Trip Headsign", headsigns, key="jadwal_headsign")
with col3:
    sel_stop = st.text_input("Cari Nama Halte", key="jadwal_stop")

# Banner dihapus sesuai permintaan

# ─── Auto-load schedule ───────────────────────────────────────────────
with st.spinner("Memuat jadwal..."):
    schedule = load_schedule(
        sel_route,
        sel_headsign if sel_headsign != "Semua Arah" else "",
        sel_stop,
    )

if schedule.empty:
    st.warning("Tidak ada jadwal yang cocok dengan filter ini.")
else:
    st.success(f"{len(schedule)} jadwal ditemukan")

    display = schedule.rename(columns={
        "route_short_name": "Route",
        "trip_headsign": "Arah",
        "stop_name": "Halte",
        "arrival_time": "Kedatangan",
        "departure_time": "Keberangkatan",
        "stop_sequence": "Urutan",
    })

    html_table = display.to_html(classes="styled-table", index=False, escape=False)
    st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)

    csv = schedule.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"jadwal_{sel_route}.csv",
        mime="text/csv",
    )
