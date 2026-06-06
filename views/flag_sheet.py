import base64
import streamlit as st

from components.ui import page_hero, status_banner


def _pdf_viewer(pdf_bytes: bytes, height: int = 820):
    """Embed PDF in the page."""
    b64 = base64.b64encode(pdf_bytes).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}" style="border:1px solid #334155;border-radius:12px;"></iframe>',
        unsafe_allow_html=True,
    )


def render():
    st.markdown(
        page_hero(
            "Flag Sheet",
            "Your uploaded timecard PDF — kept here so you can verify hours without hunting for the file.",
            tag="Source Document",
            tag_style="live" if st.session_state.get("flag_pdf_bytes") else "warn",
        ),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("flag_pdf_bytes"):
        st.markdown(
            status_banner(
                "No flag sheet loaded yet. Upload TECH FLAG SHEETS.pdf on the Payroll tab first.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="glass-panel">
                <p style="color:#94a3b8; margin:0; line-height:1.7;">
                Once you upload the PDF on <strong>Payroll</strong>, it stays attached to this pay period
                so you can cross-check any technician's hours against the original report before or after
                you submit to accounting.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    filename = st.session_state.get("flag_pdf_filename", "flag_sheet.pdf")
    pay_period = st.session_state.get("pay_period", "")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("File", filename)
    with c2:
        st.metric("Pay Period", pay_period or "—")
    with c3:
        size_kb = len(st.session_state.flag_pdf_bytes) / 1024
        st.metric("Size", f"{size_kb:.0f} KB")

    st.download_button(
        label="⬇️ Download original flag sheet",
        data=st.session_state.flag_pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown("##### 📄 Flag sheet preview")
    _pdf_viewer(st.session_state.flag_pdf_bytes)
