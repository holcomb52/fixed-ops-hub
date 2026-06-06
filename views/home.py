import streamlit as st

from components.ui import module_card, page_hero, stat_card, status_banner
from lib.supabase_client import is_configured


def render():
    st.markdown(
        page_hero(
            "Fixed Ops Hub",
            "Dealership operations, reimagined. One command center for payroll, inventory, and performance.",
            tag="Command Center" if is_configured() else "Setup Required",
            tag_style="live" if is_configured() else "warn",
        ),
        unsafe_allow_html=True,
    )

    if is_configured():
        st.markdown(
            status_banner("Supabase connected — live data ready.", "success"),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            status_banner("Connect Supabase to unlock live data. See Payroll tab for steps.", "warn"),
            unsafe_allow_html=True,
        )

    c1, c2, c3, c4 = st.columns(4)
    stats = [
        ("Modules Live", "2", "cyan", "⚡"),
        ("In Pipeline", "2", "orange", "◈"),
        ("Database", "Supabase" if is_configured() else "—", "violet", "◎"),
        ("Cloud", "Streamlit", "green", "☁"),
    ]
    for col, (label, value, accent, icon) in zip([c1, c2, c3, c4], stats):
        with col:
            size_class = " stat-value-sm" if len(str(value)) > 3 else ""
            card = stat_card(label, value, accent, icon).replace(
                'class="stat-value"', f'class="stat-value{size_class}"'
            )
            st.markdown(card, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title"><h2>Operations Modules</h2>'
        '<p class="section-sub">Pick a module from the sidebar to dive in.</p></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3)
    cards = [
        ("💰 Payroll", "Technician flag sheets + service advisor pay plans", "Live", "cyan"),
        ("📦 Inventory", "Parts tracking, stock alerts, and reorder workflows.", "Queued", "orange"),
        ("📊 Reports", "KPI dashboards, trends, and one-click exports.", "Queued", "violet"),
    ]
    for col, (title, desc, status, accent) in zip(cols, cards):
        with col:
            st.markdown(module_card(title, desc, status, accent), unsafe_allow_html=True)
