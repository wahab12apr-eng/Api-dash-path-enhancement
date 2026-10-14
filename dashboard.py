"""Streamlit page that displays the Dash app full-screen."""
import streamlit as st

st.set_page_config(page_title="AI News Analyzer", page_icon="📰", layout="wide",
                   initial_sidebar_state="collapsed")

# Hide Streamlit's chrome so the Dash UI looks exactly like it does standalone
st.markdown("""
<style>
  header[data-testid="stHeader"], footer, [data-testid="stToolbar"],
  [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] { overflow: hidden !important; }
  iframe { position: fixed; inset: 0; width: 100vw !important; height: 100vh !important;
           border: 0 !important; z-index: 1000; }
</style>
""", unsafe_allow_html=True)

st.iframe("/dash/", height=900)
