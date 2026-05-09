"""
streamlit_app.py
-----------------
Thin entry-point — delegates everything to ui.app.

Run:
    streamlit run streamlit_app.py
"""

import streamlit as st

st.set_page_config(
    page_title="llull — Decision Intelligence Agent",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.app import main  # noqa: E402

if __name__ == "__main__" or True:
    main()
