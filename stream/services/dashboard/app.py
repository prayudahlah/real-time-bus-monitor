import streamlit as st

st.set_page_config(
    page_title="Bus Monitor",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.styling import inject_custom_css

inject_custom_css()

pages = [
    st.Page("pages/1_Peta_Langsung.py", title="Peta Langsung", icon="🗺️", default=True),
    st.Page("pages/2_Jadwal.py", title="Jadwal", icon="📅"),
    st.Page("pages/3_Prediksi_Keterlambatan.py", title="Prediksi Keterlambatan", icon="⏱️"),
]
pg = st.navigation(pages, position="hidden")

# Sidebar styling and order
st.sidebar.markdown("<div class='nav-brand' style='margin-bottom: 24px; padding-left: 0; text-align: center; font-size: 1.5rem;'><i class='fas fa-bus-alt'></i> BUS MONITOR</div>", unsafe_allow_html=True)

st.sidebar.page_link("pages/1_Peta_Langsung.py", label="Peta Langsung", icon=":material/map:")
st.sidebar.page_link("pages/2_Jadwal.py", label="Jadwal", icon=":material/calendar_today:")
st.sidebar.page_link("pages/3_Prediksi_Keterlambatan.py", label="Prediksi Keterlambatan", icon=":material/speed:")

# Sidebar footer
st.sidebar.markdown(
    """<div style='margin-top: 50px; font-size: 0.75rem; color: #A78425; font-weight: 600; text-align: center;'>
    Real-time Bus Monitoring &mdash; WMATA DC
    </div>""",
    unsafe_allow_html=True
)

pg.run()
