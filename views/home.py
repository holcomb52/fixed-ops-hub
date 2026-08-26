import streamlit as st

from lib.page_ui import module_card, page_hero, stat_card, status_banner
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
            status_banner(
                "Supabase connected — live data ready. "
                "Parts return plans save to Reports when you Complete & Save.",
                "success",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            status_banner("Connect Supabase to unlock live data. See Payroll tab for steps.", "warn"),
            unsafe_allow_html=True,
        )

    c1, c2, c3, c4 = st.columns(4)
    stats = [
        ("Modules Live", "4", "cyan", "⚡"),
        ("In Pipeline", "0", "orange", "◈"),
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

    cards = [
        ("💰 Payroll", "Technician flag sheets + service advisor pay plans", "Live", "cyan"),
        ("🛡️ Warranty", "Customer-pay ELR analysis for rate submissions.", "Live", "green"),
        ("📈 Labor Rate", "Build a customer-pay grid from target ELR + hour mix.", "Live", "violet"),
        ("🔩 Parts", "MNS return allowance plans — save to cloud Reports.", "Live", "orange"),
    ]
    cols = st.columns(2)
    for idx, (title, desc, status, accent) in enumerate(cards):
        with cols[idx % 2]:
            st.markdown(module_card(title, desc, status, accent), unsafe_allow_html=True)
