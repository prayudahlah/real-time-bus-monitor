import streamlit as st

COLORS = {
    "Honeydew": "#F6FFE9",
    "Lime Cream": "#CDED76",
    "Bubblegum Pink": "#E85A72",
    "Sandy Brown": "#FB9F4F",
    "Dark Goldenrod": "#A78425",
    "Bg Page": "#FFFDF6",
    "Text Dark": "#3A2E12",
    "Button Hover": "#c94860",
}

# Rotasi warna untuk KPI card (index-based)
KPI_PALETTE = [
    "#E85A72",  # Bubblegum Pink
    "#FB9F4F",  # Sandy Brown
    "#CDED76",  # Lime Cream
    "#F6FFE9",  # Honeydew
    "#A78425",  # Dark Goldenrod
]

STATUS_ICON = {
    "Live": "<i class='fas fa-bus-alt' style='color:#CDED76;'></i>",
    "Tertunda": "<i class='fas fa-clock' style='color:#FB9F4F;'></i>",
    "Kadaluarsa": "<i class='fas fa-times-circle' style='color:#A78425;'></i>",
    "Cepat": "<i class='fas fa-rocket' style='color:#CDED76;'></i>",
    "Normal": "<i class='fas fa-check-circle' style='color:#E85A72;'></i>",
    "Lambat": "<i class='fas fa-exclamation-triangle' style='color:#A78425;'></i>",
}


def status_badge(status):
    icon = STATUS_ICON.get(status, "<i class='fas fa-circle'></i>")
    return f"<span style='display:flex; align-items:center; gap:6px;'>{icon} <span>{status}</span></span>"


def kpi_card(value, label, palette_index=0):
    bg = KPI_PALETTE[palette_index % len(KPI_PALETTE)]
    text_color = "#3A2E12" if palette_index in (1, 2, 3) else "#FFFFFF"
    return f"""<div style="
        background:{bg}; border-radius:18px; padding:20px 24px;
        text-align:center; color:{text_color};
        box-shadow:0 4px 12px rgba(0,0,0,0.08);
        border: 1px solid rgba(255,255,255,0.15);
    ">
        <div style="font-size:2.2rem; font-weight:800; line-height:1.1;">{value}</div>
        <div style="font-size:0.75rem; font-weight:700; text-transform:uppercase; letter-spacing:0.8px; opacity:0.85; margin-top:4px;">{label}</div>
    </div>"""


def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');
        @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css');

        * { font-family: 'DM Sans', sans-serif; }
        
        /* Kurangi jarak atas konten */
        .block-container { padding-top: 1.5rem !important; }

        h1, h2, h3, h4, h5, h6 {
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            color: #E85A72 !important;
        }

        .stApp { background-color: #FFFDF6; }

        .nav-brand {
            background: #FFFFFF;
            border-radius: 18px;
            padding: 18px 22px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            border: 1px solid #E8E4DC;
        }
        div[data-testid="stMetric"] label {
            font-weight: 700 !important;
            text-transform: uppercase;
            font-size: 0.7rem !important;
            letter-spacing: 0.5px;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-weight: 800 !important;
            font-size: 1.6rem !important;
        }

        .stButton button {
            border-radius: 12px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            padding: 8px 24px !important;
            transition: all 0.2s ease;
        }
        .stButton button[kind="primary"] {
            background-color: #E85A72 !important;
            color: #FFFFFF !important;
            border: none !important;
        }
        .stButton button[kind="primary"]:hover {
            background-color: #c94860 !important;
            box-shadow: 0 4px 12px rgba(232,90,114,0.3) !important;
        }

        /* Custom HTML Table (untuk header warna) */
        .styled-table {
            width: 100%;
            border-collapse: collapse;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            border: 1px solid #E8E4DC;
            background: #FFFFFF;
            margin-bottom: 16px;
        }
        .styled-table th {
            background-color: #E85A72;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 12px 16px;
            text-align: left;
        }
        .styled-table td {
            padding: 10px 16px;
            border-bottom: 1px solid #E8E4DC;
            font-size: 0.85rem;
            color: #3A2E12;
        }
        .styled-table tr:last-of-type td {
            border-bottom: none;
        }
        .table-container {
            max-height: 500px;
            overflow-y: auto;
            border-radius: 12px;
            border: 1px solid #E8E4DC;
        }

        div.stDownloadButton button {
            background-color: #E85A72 !important;
            color: #FFFFFF !important;
            border-radius: 12px !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
        }

        .stSelectbox label, .stMultiSelect label, .stTextInput label {
            font-weight: 700 !important;
            text-transform: uppercase !important;
            font-size: 0.65rem !important;
            letter-spacing: 0.5px !important;
            color: #A78425 !important;
        }

        div[data-testid="stInfo"] {
            border-radius: 12px;
            border-left: 4px solid #E85A72;
        }
        div[data-testid="stWarning"] {
            border-radius: 12px;
            border-left: 4px solid #FB9F4F;
        }
        div[data-testid="stError"] {
            border-radius: 12px;
            border-left: 4px solid #A78425;
        }

        hr { margin: 1.5rem 0; border-color: #E8E4DC; }

        .legend-item {
            display: flex; align-items: center; gap: 8px;
            font-size: 0.8rem; margin: 4px 0;
        }
        .legend-dot {
            width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
        }

        .route-pill {
            display: inline-block; padding: 2px 14px; border-radius: 14px;
            font-size: 0.75rem; font-weight: 700;
            background: #CDED76; color: #3A2E12; margin: 2px;
        }

        .st-emotion-cache-1aehpvj {
            border-radius: 16px !important;
        }

        div.stSlider label {
            font-weight: 700 !important;
            text-transform: uppercase !important;
            font-size: 0.65rem !important;
            letter-spacing: 0.5px !important;
            color: #A78425 !important;
        }

        div.st-emotion-cache-1jivqwx {
            font-family: 'DM Sans', sans-serif;
        }
    </style>
    """, unsafe_allow_html=True)
