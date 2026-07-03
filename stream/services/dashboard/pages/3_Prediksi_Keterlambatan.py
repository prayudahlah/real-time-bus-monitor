import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

from utils.data_loader import load_predictions
from utils.styling import status_badge, kpi_card, inject_custom_css, KPI_PALETTE

inject_custom_css()

st.markdown("<h1 style='margin-bottom:0;'>Prediksi Keterlambatan</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='color:#A78425; margin-top:-8px;'>"
    "Waktu tempuh prediktif ke halte berikutnya &mdash; Cepat / Normal / Lambat</p>",
    unsafe_allow_html=True,
)

# ─── Load data ────────────────────────────────────────────────────────
df = load_predictions()

if df.empty:
    st.warning("Belum ada data prediksi.")
    st.stop()

# ─── Baca default filter dari query params — aman, tidak self-reference ─
qp = st.query_params
default_route = qp.get("route", "Semua")
default_bus = qp.get("bus_id", "Semua")
default_status = qp.get("status", "Semua")
default_sort_col = qp.get("sort_col", "timestamp")
default_asc = qp.get("asc", "0") == "1"

# ─── Filters ──────────────────────────────────────────────────────────
route_list = ["Semua"] + sorted(df["route"].dropna().unique().tolist())
bus_list = ["Semua"] + sorted(df["bus_id"].dropna().unique().tolist())
status_list = ["Semua", "Cepat", "Normal", "Lambat"]
sort_options = {
    "timestamp": "Waktu",
    "speed": "Kecepatan",
    "predicted_travel_time_sec": "Waktu Tempuh",
}

route_idx = route_list.index(default_route) if default_route in route_list else 0
bus_idx = bus_list.index(default_bus) if default_bus in bus_list else 0
status_idx = status_list.index(default_status) if default_status in status_list else 0
sort_idx = list(sort_options.keys()).index(default_sort_col) if default_sort_col in sort_options else 0

col1, col2, col3 = st.columns(3, gap="medium")
with col1:
    sel_route = st.selectbox("Route", route_list, index=route_idx, key="pred_route")
with col2:
    sel_bus = st.selectbox("Bus ID", bus_list, index=bus_idx, key="pred_bus")
with col3:
    sel_status = st.selectbox("Status", status_list, index=status_idx, key="pred_status")

col1, col2, col3 = st.columns([2, 1.5, 1], gap="medium")
with col1:
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    sel_range = st.date_input("Rentang Tanggal", value=(week_ago, now), key="pred_date")
with col2:
    sel_sort = st.selectbox(
        "Urutkan Berdasarkan",
        list(sort_options.keys()),
        index=sort_idx,
        format_func=lambda x: sort_options[x],
        key="pred_sort",
    )
with col3:
    # Bug #1: checkbox key berbeda dari expression value
    sort_asc = st.checkbox("Urut Naik", value=default_asc, key="pred_asc")

# ─── Sinkronisasi ke query params ────────────────────────────────────
st.query_params.update({
    "route": sel_route,
    "bus_id": sel_bus,
    "status": sel_status,
    "sort_col": sel_sort,
    "asc": "1" if sort_asc else "0",
})

# ─── Apply filters ────────────────────────────────────────────────────
filtered = df.copy()

if sel_route != "Semua":
    filtered = filtered[filtered["route"] == sel_route]
if sel_bus != "Semua":
    filtered = filtered[filtered["bus_id"] == sel_bus]
if sel_status != "Semua":
    filtered = filtered[filtered["status"] == sel_status]

if isinstance(sel_range, tuple) and len(sel_range) == 2:
    start_dt, end_dt = sel_range
    start_dt = pd.Timestamp(start_dt)
    end_dt = pd.Timestamp(end_dt) + timedelta(days=1)
    filtered = filtered[
        (filtered["timestamp"] >= start_dt) & (filtered["timestamp"] < end_dt)
    ]

filtered = filtered.sort_values(sel_sort, ascending=bool(sort_asc))

# ─── Result count ─────────────────────────────────────────────────────
st.info(f"{len(filtered)} data ditemukan berdasarkan filter yang dipilih.")

if filtered.empty:
    st.markdown(
        """<div style='text-align:center; padding:40px; background:#FFFDF6; border-radius:18px;'>
        <div style='font-size:1.2rem; color:#A78425; font-weight:600;'>
        Tidak ada data yang cocok dengan filter ini</div>
        <div style='color:#A78425; font-size:0.9rem;'>Coba ubah filter atau rentang waktu</div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.stop()

# ─── Display table (emoji status, no HTML badges) ────────────────────
display = filtered[[
    "bus_id", "route", "speed", "next_stop_id",
    "predicted_travel_time_sec", "status", "timestamp",
]].rename(columns={
    "bus_id": "Bus ID",
    "route": "Route",
    "next_stop_id": "Halte Berikut",
    "status": "Status",
    "timestamp": "Waktu",
}).copy()

display["speed"] = display["speed"].apply(lambda x: f"{x:.1f} m/s")
display["predicted_travel_time_sec"] = display["predicted_travel_time_sec"].apply(lambda x: f"{int(x)} dtk")
display = display.rename(columns={
    "speed": "Kecepatan",
    "predicted_travel_time_sec": "Waktu Tempuh",
})

display["Status"] = display["Status"].apply(lambda x: status_badge(x))

html_table = display.to_html(classes="styled-table", index=False, escape=False)
st.markdown(f'<div class="table-container">{html_table}</div>', unsafe_allow_html=True)

# ─── Download CSV ─────────────────────────────────────────────────────
csv = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download CSV Hasil Filter",
    data=csv,
    file_name=f"prediksi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
)
st.markdown("<div style='margin-bottom: 32px;'></div>", unsafe_allow_html=True)

# ─── Ringkasan per Status: KPI cards + Altair bar chart ─────────────
st.markdown("### Ringkasan per Status")

summary = filtered.groupby("status").agg(
    Jumlah=("predicted_travel_time_sec", "count"),
    Rata_Waktu=("predicted_travel_time_sec", "mean"),
).reset_index()
summary["Rata_Waktu"] = summary["Rata_Waktu"].round(0).astype(int)

status_order = ["Cepat", "Normal", "Lambat"]
summary["status"] = pd.Categorical(summary["status"], categories=status_order, ordered=True)
summary = summary.sort_values("status")

STATUS_ICONS = {"Cepat": "<i class='fas fa-rocket'></i>", "Normal": "<i class='fas fa-check-circle'></i>", "Lambat": "<i class='fas fa-exclamation-triangle'></i>"}

kpi_cols = st.columns(len(summary))
for i, (_, row) in enumerate(summary.iterrows()):
    with kpi_cols[i]:
        icon = STATUS_ICONS.get(row["status"], "<i class='fas fa-circle'></i>")
        color_map = {"Cepat": 2, "Normal": 0, "Lambat": 4}
        st.markdown(
            kpi_card(f"{icon} {row['Jumlah']}", f"{row['status']} — {row['Rata_Waktu']} dtk",
                     color_map.get(row["status"], i)),
            unsafe_allow_html=True,
        )

# Altair bar chart
chart_color_map = {"Cepat": "#CDED76", "Normal": "#E85A72", "Lambat": "#A78425"}
bar_chart = alt.Chart(summary).mark_bar(cornerRadius=8).encode(
    x=alt.X("status:N", title="Status", axis=alt.Axis(labelAngle=0)),
    y=alt.Y("Jumlah:Q", title="Jumlah"),
    color=alt.Color("status:N", scale=alt.Scale(
        domain=list(chart_color_map.keys()),
        range=list(chart_color_map.values()),
    ), legend=None),
    tooltip=[
        alt.Tooltip("status:N", title="Status"),
        alt.Tooltip("Jumlah:Q", title="Jumlah Bus"),
        alt.Tooltip("Rata_Waktu:Q", title="Rata-rata Waktu (dtk)"),
    ],
).properties(height=250)

st.altair_chart(bar_chart, width="stretch")
