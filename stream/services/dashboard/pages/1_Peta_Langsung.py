import streamlit as st
import pandas as pd
import pydeck as pdk
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from utils.data_loader import load_bus_positions, load_predictions, load_route_descriptions, load_stops, load_route_paths
from utils.styling import status_badge, kpi_card, inject_custom_css

inject_custom_css()

refresh_sec = st.session_state.get("map_interval", 15)
st_autorefresh(interval=refresh_sec * 1000, key="autorefresh_main", limit=1000)

st.markdown(
    """<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:-8px;">
    <h1 style="margin:0;">Peta Langsung</h1>
    <div style="font-size:0.75rem; color:#A78425; font-weight:600;">""" +
    datetime.now().strftime('%H:%M:%S') +
    """</div></div>""",
    unsafe_allow_html=True,
)

with st.spinner("Memuat data..."):
    df = load_bus_positions()
    predictions = load_predictions()
    route_desc = load_route_descriptions()
    stops_df = load_stops()
    paths_df = load_route_paths()

# KPI cards dipindahkan ke bawah filter

# ─── Filters ──────────────────────────────────────────────────────────
if df.empty:
    st.warning("Belum ada data posisi bus.")
    st.stop()

routes = sorted(df["route_id"].dropna().unique())

col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1.5, 1.5, 1], gap="medium")
with col_f1:
    # Bug #2: default=[] — empty = "show all"
    sel_routes = st.multiselect("Route", routes, default=[], key="map_routes")
with col_f2:
    status_opts = ["Semua Status", "Live", "Tertunda", "Kadaluarsa"]
    sel_status = st.selectbox("Status", status_opts, index=0, key="map_status")
with col_f3:
    sel_bus = st.text_input("Cari Bus ID", key="map_bus_search")
with col_f4:
    sel_interval = st.slider("Refresh (dtk)", 5, 60, 15, key="map_interval")

# ─── Apply filters ────────────────────────────────────────────────────
# Jika tidak ada route dipilih, tampilkan semua
if sel_routes:
    filtered = df[df["route_id"].isin(sel_routes)].copy()
else:
    filtered = df.copy()

if sel_status != "Semua Status":
    filtered = filtered[filtered["status"] == sel_status]
if sel_bus:
    filtered = filtered[filtered["bus_id"].str.contains(sel_bus, case=False, na=False)]

filtered = filtered.sort_values("created_at").groupby("bus_id", as_index=False).last()

# ─── KPI Cards — dihitung dari df setelah difilter ────────────────────
kpi_buses = filtered["bus_id"].nunique() if not filtered.empty else 0
kpi_routes = filtered["route_id"].nunique() if not filtered.empty else 0
kpi_speed = round(filtered["speed"].mean(), 1) if not filtered.empty else 0

# Gunakan KPI_PALETTE index: 0=Bubblegum, 1=Sandy Brown, 2=Lime Cream, 3=Honeydew, 4=Dark Goldenrod
k1, k2, k3 = st.columns(3)
with k1:
    st.markdown(kpi_card(kpi_buses, "Bus Terpantau", 0), unsafe_allow_html=True)
with k2:
    st.markdown(kpi_card(kpi_routes, "Route Aktif", 1), unsafe_allow_html=True)
with k3:
    st.markdown(kpi_card(f"{kpi_speed} m/s", "Kecepatan Rata-rata", 2), unsafe_allow_html=True)

# ─── Process route paths from WKT ─────────────────────────────────────
path_layers = []
if not paths_df.empty:
    for _, row in paths_df.iterrows():
        wkt = row.get("wkt", "")
        if wkt.startswith("LINESTRING ("):
            coords_str = wkt[len("LINESTRING ("):-1]
            coords = []
            for pair in coords_str.split(","):
                parts = pair.strip().split()
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            if len(coords) > 1:
                path_layers.append(pdk.Layer(
                    "PathLayer",
                    data=[{"path": coords, "name": row["shape_id"]}],
                    get_path="path",
                    get_color=[200, 200, 200, 60],
                    width_scale=1,
                    width_min_pixels=1,
                    pickable=True,
                ))
    if path_layers:
        st.caption(f"Menampilkan {len(path_layers)} jalur rute dari PostGIS")

# ─── Map ──────────────────────────────────────────────────────────────
if not filtered.empty:
    route_color_map = {}
    palette_colors = ["#E85A72", "#FB9F4F", "#CDED76", "#A78425", "#F6FFE9"]
    for i, r in enumerate(sorted(filtered["route_id"].unique())):
        route_color_map[r] = palette_colors[i % len(palette_colors)]

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return [int(h[i:i+2], 16) for i in (0, 2, 4)]

    filtered["color"] = filtered["route_id"].map(
        lambda r: hex_to_rgb(route_color_map.get(r, "#888888"))
    )

    filtered["tooltip_text"] = filtered.apply(
        lambda r: (
            f"Bus: {r['bus_id']}  |  Route: {r['route_id']}\n"
            f"Speed: {r['speed']:.1f} m/s  |  Status: {r['status']}\n"
            f"Updated: {r['created_at'].strftime('%H:%M:%S')}"
        ), axis=1
    )

    # Determine view state from bus positions or stop data
    if not stops_df.empty:
        view_state = pdk.ViewState(
            latitude=stops_df["lat"].mean(),
            longitude=stops_df["lon"].mean(),
            zoom=12, pitch=0,
        )
    else:
        view_state = pdk.ViewState(
            latitude=filtered["lat"].mean(),
            longitude=filtered["lon"].mean(),
            zoom=12, pitch=0,
        )

    icon_data = {
        "url": "https://img.icons8.com/ios-filled/50/ffffff/marker.png",
        "width": 50,
        "height": 50,
        "anchorY": 50,
        "mask": True,
    }
    filtered["icon_data"] = [icon_data] * len(filtered)

    layers = path_layers.copy()

    # Add stop points layer
    if not stops_df.empty:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=stops_df,
            get_position=["lon", "lat"],
            get_radius=8,
            get_fill_color=[150, 150, 150, 30],
            get_line_color=[200, 200, 200, 80],
            get_line_width=1,
            pickable=False,
        ))

    # Add bus icon layer
    layers.append(pdk.Layer(
        "IconLayer",
        data=filtered,
        get_position=["lon", "lat"],
        get_icon="icon_data",
        get_size=4,
        size_scale=8,
        get_color="color",
        pickable=True,
        auto_highlight=True,
    ))

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip={"text": "{tooltip_text}"},
    )

    # Bug #4: use_container_width → width='stretch'
    st.pydeck_chart(deck, width="stretch")

    # Legend
    st.markdown("### Route")
    legend_cols = st.columns(min(5, len(route_color_map)))
    for idx, (r, c) in enumerate(sorted(route_color_map.items())):
        desc = route_desc.get(r, r)
        with legend_cols[idx % 5]:
            st.markdown(
                f"""<div class='legend-item'><span class='legend-dot' style='background:{c};'>
</span><span style='font-size:0.8rem;'>{desc}</span></div>""",
                unsafe_allow_html=True,
            )
else:
    st.info("Tidak ada bus yang cocok dengan filter ini.")

# ─── Ringkasan per Route & Prediksi Terbaru ──────────────────────────
if not predictions.empty:
    st.markdown("""<hr style="margin:24px 0; border-color:#E8E4DC;">""", unsafe_allow_html=True)
    st.markdown("### Ringkasan per Route")

    ringkasan = predictions.groupby("route").agg(
        Bus=("bus_id", "nunique"),
        Prediksi=("predicted_travel_time_sec", "count"),
        Rata_Waktu=("predicted_travel_time_sec", "mean"),
        Rata_Speed=("speed", "mean"),
        Cepat=("status", lambda x: (x == "Cepat").sum()),
        Normal=("status", lambda x: (x == "Normal").sum()),
        Lambat=("status", lambda x: (x == "Lambat").sum()),
    ).reset_index()
    ringkasan["Route Info"] = ringkasan["route"].map(route_desc)
    ringkasan["Rata_Waktu"] = (ringkasan["Rata_Waktu"] / 60).round(1).astype(str) + " mnt"
    ringkasan["Rata_Speed"] = ringkasan["Rata_Speed"].round(1).astype(str) + " m/s"
    ringkasan = ringkasan[["Route Info", "Bus", "Prediksi", "Rata_Waktu", "Rata_Speed",
                           "Cepat", "Normal", "Lambat"]].sort_values("Bus", ascending=False)
    ringkasan.columns = ["Route", "Bus", "Jumlah Prediksi", "Rata-rata Waktu", "Rata-rata Speed",
                         "Bus Cepat", "Bus Normal", "Bus Lambat"]

    st.markdown(ringkasan.to_html(classes="styled-table", index=False, escape=False), unsafe_allow_html=True)

    st.markdown("### Prediksi Terbaru")
    recent = predictions.sort_values("timestamp", ascending=False).head(10)
    display = recent[["bus_id", "route", "speed", "predicted_travel_time_sec",
                      "status", "timestamp"]].rename(columns={
        "bus_id": "Bus ID", "route": "Route",
        "status": "Status", "timestamp": "Waktu",
    }).copy()
    display["speed"] = display["speed"].apply(lambda x: f"{x:.1f} m/s")
    display["predicted_travel_time_sec"] = display["predicted_travel_time_sec"].apply(lambda x: f"{int(x)} dtk")
    display = display.rename(columns={
        "speed": "Kecepatan",
        "predicted_travel_time_sec": "Waktu Tempuh",
    })
    display["Status"] = display["Status"].apply(lambda x: status_badge(x))

    st.markdown(display.to_html(classes="styled-table", escape=False, index=False), unsafe_allow_html=True)
