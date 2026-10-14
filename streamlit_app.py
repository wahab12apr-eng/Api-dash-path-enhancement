"""Streamlit entry point.

Serves the existing Dash app (app.py + assets/) unchanged at /dash/ on
Streamlit's own server, and shows it full-screen via dashboard.py.

Run locally:  streamlit run streamlit_app.py
"""
import os

import streamlit as st
from a2wsgi import WSGIMiddleware
from starlette.routing import Mount

# Dash reads its URL prefix from these env vars, so app.py needs no changes.
os.environ.setdefault("DASH_REQUESTS_PATHNAME_PREFIX", "/dash/")

# On Streamlit Cloud the API key lives in st.secrets; locally config.py reads .env.
try:
    os.environ.setdefault("NEWS_API_KEY", st.secrets["NEWS_API_KEY"])
except Exception:
    pass

from app import app as dash_app  # noqa: E402  (must come after the env setup above)

app = st.App(
    "dashboard.py",
    routes=[Mount("/dash", WSGIMiddleware(dash_app.server))],
)
