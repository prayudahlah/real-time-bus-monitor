import os
import time
import pandas as pd
import streamlit as st
import plotly.express as px
from trino.dbapi import connect

st.set_page_config(page_title="Bus Monitor", layout="wide")

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

st.sidebar.title("Bus Monitor")
page = st.sidebar.radio("Page", ["Overview", "Map", "Predictions", "GTFS Reference"])

if page == "Overview":
    st.header("Overview")
    try:
        ml = query(f"SELECT * FROM {CATALOG}.{SCHEMA}.predictions_ml_log ORDER BY created_at DESC LIMIT 500")
        if ml.empty:
            st.info("No ML prediction data yet")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Predictions", len(ml))
            c2.metric("Unique Buses", ml.bus_id.nunique())
            c3.metric("Avg Travel Time (s)", round(ml.predicted_travel_time_sec.mean(), 1))
            c4.metric("Unique Routes", ml.route_id.nunique())
            st.subheader("Predictions Over Time")
            fig = px.scatter(ml, x="created_at", y="predicted_travel_time_sec",
                             color="route_id", title="Predicted Travel Time per Bus")
            st.plotly_chart(fig, use_container_width=True)
            st.subheader("Route Distribution")
            fig2 = px.bar(ml.route_id.value_counts().reset_index(),
                          x="route_id", y="count", title="Predictions per Route")
            st.plotly_chart(fig2, use_container_width=True)
            st.subheader("Hourly Distribution")
            ml["hour"] = pd.to_datetime(ml.created_at).dt.hour
            fig3 = px.histogram(ml, x="hour", nbins=24, title="Predictions by Hour of Day")
            st.plotly_chart(fig3, use_container_width=True)
    except Exception as e:
        st.error(f"Trino error: {e}")

elif page == "Map":
    st.header("Bus Positions Map")
    try:
        ml = query(f"SELECT * FROM {CATALOG}.{SCHEMA}.predictions_ml_log ORDER BY created_at DESC LIMIT 200")
        if ml.empty:
            st.info("No bus position data yet")
        else:
            import folium
            from streamlit_folium import st_folium
            center_lat = ml.lat.mean()
            center_lon = ml.lon.mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
            colors = ["red", "blue", "green", "purple", "orange", "darkred", "lightred", "beige",
                      "darkblue", "darkgreen", "cadetblue", "darkpurple", "white", "pink", "lightblue",
                      "lightgreen", "gray", "black", "lightgray"]
            route_colors = {}
            for _, row in ml.iterrows():
                rc = row.route_id
                if rc not in route_colors:
                    route_colors[rc] = colors[len(route_colors) % len(colors)]
                folium.CircleMarker(
                    location=[row.lat, row.lon],
                    radius=6,
                    color=route_colors[rc],
                    fill=True,
                    popup=f"{row.bus_id} | {rc} | {row.predicted_travel_time_sec}s"
                ).add_to(m)
            st_folium(m, width="100%", height=600)
    except Exception as e:
        st.error(f"Trino error: {e}")

elif page == "Predictions":
    st.header("Prediction History")
    try:
        ml = query(f"SELECT * FROM {CATALOG}.{SCHEMA}.predictions_ml_log ORDER BY created_at DESC LIMIT 1000")
        if ml.empty:
            st.info("No prediction data yet")
        else:
            routes = ["All"] + sorted(ml.route_id.dropna().unique().tolist())
            sel_route = st.selectbox("Filter Route", routes)
            if sel_route != "All":
                ml = ml[ml.route_id == sel_route]
            st.dataframe(ml, use_container_width=True, hide_index=True)
            csv = ml.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "predictions.csv", "text/csv")
    except Exception as e:
        st.error(f"Trino error: {e}")

elif page == "GTFS Reference":
    st.header("GTFS Reference Data")
    tabs = st.tabs(["Routes", "Stops", "Trips", "Stop Times"])
    for tab, tbl in zip(tabs, ["routes", "stops", "trips", "stop_times"]):
        with tab:
            try:
                df = query(f"SELECT * FROM {CATALOG}.{SCHEMA}.{tbl} LIMIT 500")
                if df.empty:
                    st.info(f"No data in {tbl}")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Error loading {tbl}: {e}")

