import os
import time
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from trino.dbapi import connect
from datetime import datetime, timedelta

st.set_page_config(page_title="Bus Monitor", layout="wide", initial_sidebar_state="expanded")

TRINO_HOST = os.getenv("TRINO_HOST", "localhost")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
CATALOG = "postgres"
SCHEMA = "public"
REFRESH_SEC = int(os.getenv("REFRESH_SEC", "30"))

@st.cache_data(ttl=REFRESH_SEC, show_spinner=False)
def query(sql):
    conn = connect(host=TRINO_HOST, port=TRINO_PORT, user="dashboard")
    cur = conn.cursor()
    cur.execute(sql)
    cols = [desc[0] for desc in cur.description] if cur.description else []
    rows = cur.fetchall()
    conn.close()
    return pd.DataFrame(rows, columns=cols)

def delay_label(sec):
    if sec < 60:
        return "Lancar"
    elif sec < 180:
        return "Lambat"
    else:
        return "Macet"

def delay_color(val):
    if val < 60:
        return "#28a745"
    elif val < 180:
        return "#ffc107"
    else:
        return "#dc3545"

st.sidebar.title("Bus Monitor")
page = st.sidebar.radio("Menu", [
    "Ringkasan",
    "Peta Langsung",
    "Jadwal",
    "Prediksi Keterlambatan",
])

# ======================== RINGKASAN ========================
if page == "Ringkasan":
    st.header("Ringkasan")
    try:
        ml = query(f"""
            SELECT bus_id, route_id, predicted_travel_time_sec, created_at
            FROM {CATALOG}.{SCHEMA}.predictions_ml_log
            ORDER BY created_at DESC LIMIT 500
        """)
        if ml.empty:
            st.info("Belum ada data prediksi")
        else:
            ml["created_at"] = pd.to_datetime(ml["created_at"])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Prediksi", len(ml))
            c2.metric("Bus Aktif", ml.bus_id.nunique())
            c3.metric("Rata-rata Waktu Tempuh", f"{ml.predicted_travel_time_sec.mean():.0f} dtk")
            c4.metric("Route Terpantau", ml.route_id.nunique())

            st.subheader("Rata-rata Waktu Tempuh per Route")
            avg = ml.groupby("route_id")["predicted_travel_time_sec"].mean().reset_index()
            avg["warna"] = avg["predicted_travel_time_sec"].apply(delay_color)
            fig = px.bar(avg, x="route_id", y="predicted_travel_time_sec",
                         color="predicted_travel_time_sec",
                         color_continuous_scale=["#28a745", "#ffc107", "#dc3545"],
                         labels={"route_id": "Route", "predicted_travel_time_sec": "Rata-rata (dtk)"})
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Tren Waktu Tempuh (30 menit terakhir)")
            cutoff = ml["created_at"].max() - timedelta(minutes=30)
            recent = ml[ml["created_at"] >= cutoff].copy()
            if not recent.empty:
                recent["menit"] = recent["created_at"].dt.floor("1min")
                trend = recent.groupby(["menit", "route_id"])["predicted_travel_time_sec"].mean().reset_index()
                fig2 = px.line(trend, x="menit", y="predicted_travel_time_sec",
                               color="route_id",
                               labels={"menit": "Waktu", "predicted_travel_time_sec": "Rata-rata (dtk)",
                                       "route_id": "Route"})
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Data 30 menit terakhir belum mencukupi")

            st.subheader("Distribusi per Route")
            dist = ml["route_id"].value_counts().reset_index()
            dist.columns = ["route_id", "jumlah"]
            fig3 = px.bar(dist, x="route_id", y="jumlah", color="route_id",
                          labels={"route_id": "Route", "jumlah": "Jumlah Prediksi"})
            fig3.update_layout(showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("Distribusi per Jam")
            ml["jam"] = pd.to_datetime(ml["created_at"]).dt.hour
            fig4 = px.histogram(ml, x="jam", nbins=24, color_discrete_sequence=["#1f77b4"],
                                labels={"jam": "Jam", "count": "Jumlah Prediksi"})
            st.plotly_chart(fig4, use_container_width=True)
    except Exception as e:
        st.error(f"Gagal memuat data: {e}")

# ======================== PETA LANGSUNG ========================
elif page == "Peta Langsung":
    st.header("Peta Langsung — Posisi Bus Saat Ini")
    try:
        df = query(f"""
            SELECT bus_id, route_id, trip_id, lat, lon, speed,
                   predicted_travel_time_sec, nearest_stop_id, next_stop_id, created_at
            FROM {CATALOG}.{SCHEMA}.predictions_ml_log
            ORDER BY created_at DESC LIMIT 5000
        """)
        if df.empty:
            st.info("Belum ada data posisi bus")
        else:
            df["created_at"] = pd.to_datetime(df["created_at"])
            latest = df.sort_values("created_at").groupby("bus_id", as_index=False).last()
            now = datetime.now()
            latest["age_sec"] = (now - latest["created_at"]).dt.total_seconds().clip(lower=0)
            latest["status"] = latest["age_sec"].apply(
                lambda x: "Live" if x < 60 else ("Tertunda" if x < 300 else "Kadaluarsa")
            )
            st.subheader(f"Bus Aktif: {len(latest)}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Bus Terpantau", len(latest))
            c2.metric("Route Aktif", latest.route_id.nunique())
            c3.metric("Kecepatan Rata-rata", f"{latest.speed.mean():.1f} m/s")
            live = len(latest[latest["status"] == "Live"])
            c4.metric("Live", f"{live}/{len(latest)}")

            import folium
            from streamlit_folium import st_folium

            center_lat = latest.lat.mean()
            center_lon = latest.lon.mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
            colors = ["red", "blue", "green", "purple", "orange", "darkred",
                      "darkblue", "darkgreen", "cadetblue", "pink"]
            route_colors = {}
            for _, row in latest.iterrows():
                rc = row.route_id
                if rc not in route_colors:
                    route_colors[rc] = colors[len(route_colors) % len(colors)]
                label = delay_label(row.predicted_travel_time_sec)
                popup_text = (
                    f"<b>{row.bus_id}</b><br>"
                    f"Route: {row.route_id}<br>"
                    f"Kecepatan: {row.speed:.1f} m/s<br>"
                    f"Halte Berikut: {row.next_stop_id}<br>"
                    f"Estimasi Tiba: {row.predicted_travel_time_sec:.0f} dtk<br>"
                    f"Status: {label}<br>"
                    f"<small>Update: {row.created_at.strftime('%H:%M:%S')}</small>"
                )
                folium.Marker(
                    location=[row.lat, row.lon],
                    icon=folium.Icon(color=route_colors[rc], icon="bus", prefix="fa"),
                    popup=folium.Popup(popup_text, max_width=300)
                ).add_to(m)

            st_folium(m, width="100%", height=550)

            st.markdown("**Legenda Route**")
            legend = " ".join(
                f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{c};margin:0 4px 0 8px"></span>{r}'
                for r, c in route_colors.items()
            )
            st.markdown(legend, unsafe_allow_html=True)

            with st.expander("Detail Bus"):
                cols = ["bus_id", "route_id", "lat", "lon", "speed",
                        "predicted_travel_time_sec", "status", "created_at"]
                st.dataframe(latest[cols].sort_values("bus_id"),
                             use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Gagal memuat peta: {e}")

# ======================== JADWAL ========================
elif page == "Jadwal":
    st.header("Jadwal Bus")
    try:
        try:
            sched_catalog = "batch_pg"
            schedule = query(f"""
                SELECT r.route_short_name, r.route_long_name,
                       t.trip_id, t.trip_headsign, t.direction_id,
                       st.stop_sequence, st.arrival_time, st.departure_time,
                       s.stop_name, s.stop_id
                FROM batch_pg.public.stop_times st
                JOIN batch_pg.public.trips t ON st.trip_id = t.trip_id
                JOIN batch_pg.public.routes r ON t.route_id = r.route_id
                JOIN batch_pg.public.stops s ON st.stop_id = s.stop_id
                ORDER BY r.route_short_name, t.trip_id, st.stop_sequence
            """)
        except Exception:
            schedule = query(f"""
                SELECT r.route_short_name, r.route_long_name,
                       t.trip_id, t.trip_headsign, t.direction_id,
                       st.stop_sequence, st.arrival_time, st.departure_time,
                       s.stop_name, s.stop_id
                FROM {CATALOG}.{SCHEMA}.stop_times st
                JOIN {CATALOG}.{SCHEMA}.trips t ON st.trip_id = t.trip_id
                JOIN {CATALOG}.{SCHEMA}.routes r ON t.route_id = r.route_id
                JOIN {CATALOG}.{SCHEMA}.stops s ON st.stop_id = s.stop_id
                ORDER BY r.route_short_name, t.trip_id, st.stop_sequence
            """)
            sched_catalog = "postgres"

        if schedule.empty:
            st.info("Data jadwal belum tersedia.")
            st.caption("Jalankan `stream/scripts/load_gtfs_static.py` untuk memuat data GTFS.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                route_list = ["Semua"] + sorted(schedule.route_short_name.dropna().unique().tolist())
                sel_route = st.selectbox("Route", route_list)
            with col2:
                dir_map = {"Semua": "All", "0": "Pergi (Outbound)", "1": "Pulang (Inbound)"}
                sel_dir = st.selectbox("Arah", list(dir_map.keys()),
                                       format_func=lambda x: dir_map[x])
            with col3:
                stop_list = ["Semua"] + sorted(schedule.stop_name.dropna().unique().tolist())
                sel_stop = st.selectbox("Halte", stop_list)

            filtered = schedule.copy()
            if sel_route != "Semua":
                filtered = filtered[filtered.route_short_name == sel_route]
            if sel_dir != "Semua":
                filtered = filtered[filtered.direction_id == int(sel_dir)]
            if sel_stop != "Semua":
                filtered = filtered[filtered.stop_name == sel_stop]

            if sched_catalog == "batch_pg":
                st.success("Menampilkan data GTFS asli dari batch pipeline")
            else:
                st.warning("Menampilkan data contoh — GTFS asli belum dimuat")

            st.info(f"{len(filtered)} jadwal ditemukan")
            display_cols = ["route_short_name", "route_long_name", "trip_headsign",
                            "arrival_time", "departure_time", "stop_name", "stop_sequence"]
            st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "jadwal.csv", "text/csv")
    except Exception as e:
        st.error(f"Gagal memuat jadwal: {e}")

# ======================== PREDIKSI KETERLAMBATAN ========================
elif page == "Prediksi Keterlambatan":
    st.header("Prediksi Keterlambatan Bus")
    st.caption("Waktu tempuh prediksi ke halte berikutnya. "
               "🟢 Lancar (< 60 dtk)  🟡 Lambat (60-180 dtk)  🔴 Macet (> 180 dtk)")
    try:
        df = query(f"""
            SELECT id, bus_id, route_id, trip_id, lat, lon, speed,
                   nearest_stop_id, next_stop_id,
                   distance_to_next_m, stop_sequence, hour_of_day, stop_position_pct,
                   predicted_travel_time_sec, created_at
            FROM {CATALOG}.{SCHEMA}.predictions_ml_log
            ORDER BY created_at DESC LIMIT 5000
        """)
        if df.empty:
            st.info("Belum ada data prediksi")
        else:
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["delay_level"] = df["predicted_travel_time_sec"].apply(delay_label)

            st.subheader("Filter")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                route_list = ["Semua"] + sorted(df.route_id.dropna().unique().tolist())
                sel_route = st.selectbox("Route", route_list)
            with col2:
                bus_list = ["Semua"] + sorted(df.bus_id.dropna().unique().tolist())
                sel_bus = st.selectbox("Bus ID", bus_list)
            with col3:
                delay_opts = ["Semua", "Lancar", "Lambat", "Macet"]
                sel_delay = st.selectbox("Tingkat Keterlambatan", delay_opts)
            with col4:
                time_opts = ["Semua Waktu", "5 menit", "15 menit", "30 menit",
                             "1 jam", "6 jam"]
                sel_time = st.selectbox("Rentang Waktu", time_opts)

            col1, col2 = st.columns(2)
            with col1:
                sort_col = st.selectbox("Urutkan berdasarkan",
                    ["created_at", "predicted_travel_time_sec", "bus_id", "route_id",
                     "speed", "distance_to_next_m", "stop_sequence", "hour_of_day"],
                    format_func=lambda x: {
                        "created_at": "Waktu", "predicted_travel_time_sec": "Waktu Tempuh (dtk)",
                        "bus_id": "Bus ID", "route_id": "Route", "speed": "Kecepatan",
                        "distance_to_next_m": "Jarak (m)", "stop_sequence": "Urutan Halte",
                        "hour_of_day": "Jam"
                    }.get(x, x))
            with col2:
                sort_asc = st.checkbox("Urut naik", value=False)

            filtered = df.copy()
            if sel_route != "Semua":
                filtered = filtered[filtered.route_id == sel_route]
            if sel_bus != "Semua":
                filtered = filtered[filtered.bus_id == sel_bus]
            if sel_delay != "Semua":
                filtered = filtered[filtered.delay_level == sel_delay]
            if sel_time != "Semua Waktu":
                mins = {"5 menit": 5, "15 menit": 15, "30 menit": 30,
                        "1 jam": 60, "6 jam": 360}
                cutoff = pd.Timestamp.now() - pd.Timedelta(minutes=mins[sel_time])
                filtered = filtered[filtered["created_at"] >= cutoff]

            filtered = filtered.sort_values(sort_col, ascending=sort_asc)

            st.info(f"{len(filtered)} data ditemukan")
            display = filtered[[
                "bus_id", "route_id", "speed", "next_stop_id",
                "predicted_travel_time_sec", "delay_level", "created_at"
            ]].rename(columns={
                "bus_id": "Bus ID", "route_id": "Route", "speed": "Kecepatan (m/s)",
                "next_stop_id": "Halte Berikut", "predicted_travel_time_sec": "Waktu Tempuh (dtk)",
                "delay_level": "Status", "created_at": "Waktu"
            })
            st.dataframe(display, use_container_width=True, hide_index=True)

            st.subheader("Ringkasan")
            ringkasan = filtered.groupby("delay_level").agg(
                jumlah=("id", "count"),
                rata_waktu=("predicted_travel_time_sec", "mean")
            ).reset_index()
            ringkasan.columns = ["Status", "Jumlah", "Rata-rata (dtk)"]
            ringkasan["Rata-rata (dtk)"] = ringkasan["Rata-rata (dtk)"].round(0).astype(int)
            st.dataframe(ringkasan, use_container_width=True, hide_index=True)

            csv = filtered.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "prediksi.csv", "text/csv")
    except Exception as e:
        st.error(f"Gagal memuat prediksi: {e}")
