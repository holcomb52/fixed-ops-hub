from datetime import datetime

import streamlit as st

from components.ui import page_hero, section_title, status_banner
from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_pdf_export import generate_payroll_pdf
from lib.advisor_payroll_pdf_export import generate_advisor_payroll_pdf
from lib.advisor_payroll_storage import (
    apply_advisor_snapshot_to_session,
    list_advisor_payroll_runs,
    load_advisor_payroll_run,
)
from lib.payroll_storage import (
    apply_snapshot_to_session,
    list_payroll_runs,
    load_payroll_run,
    snapshot_to_teams,
)
from lib.supabase_client import is_configured
from views.payroll_helpers import init_payroll_session


def _fmt_date(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%m/%d/%Y %I:%M %p")
    except ValueError:
        return iso[:16]


def _money(v) -> str:
    return f"${float(v or 0):,.2f}"


def _export_pdf_from_run(loaded: dict) -> bytes:
    snap = loaded.get("snapshot", {})
    teams = snapshot_to_teams(snap)
    export_snap = build_payroll_snapshot(teams, snap.get("pay_period", ""))
    return generate_payroll_pdf(export_snap)


def render():
    init_payroll_session()

    st.markdown(
        page_hero(
            "Reports",
            "Completed payroll history — reopen any run to correct and resubmit.",
            tag="Payroll History",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if not is_configured():
        st.caption("Payroll history is saved locally. Connect Supabase to sync across devices.")

    st.markdown(
        section_title("Technician Payroll", "Completed pay periods"),
        unsafe_allow_html=True,
    )

    runs = list_payroll_runs()

    if not runs:
        st.markdown(
            status_banner(
                "No completed payroll yet. Finish a pay period on the Payroll tab and click **Complete & Save**.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
        return

    for run in runs:
        run_id = run["id"]
        pay_period = run.get("pay_period", "—")
        completed = _fmt_date(run.get("completed_at", ""))
        grand = _money(run.get("grand_total"))
        loaded = load_payroll_run(run_id)

        with st.container():
            c1, c2, c3 = st.columns([2.5, 2, 1])
            with c1:
                st.markdown(f"### {pay_period}")
                st.caption(f"Completed {completed}")
            with c2:
                st.markdown(f"**{grand}**")
                st.caption(f"{float(run.get('grand_hours', 0)):.2f} hours · Completed")
            with c3:
                st.markdown('<span class="badge badge-live">Saved</span>', unsafe_allow_html=True)

            a1, a2, a3, a4 = st.columns(4)
            with a1:
                if st.button("✏️ Reopen & edit", key=f"reopen_{run_id}", use_container_width=True):
                    if loaded:
                        apply_snapshot_to_session(
                            loaded["snapshot"],
                            run_id,
                            loaded.get("flag_pdf_bytes"),
                            loaded.get("flag_pdf_filename", "flag_sheet.pdf"),
                            status=loaded.get("status", "completed"),
                        )
                        st.session_state.pending_nav = "Payroll"
                        st.rerun()
            with a2:
                if loaded:
                    st.download_button(
                        "📄 Export PDF",
                        data=_export_pdf_from_run(loaded),
                        file_name=f"TECH_PAYROLL_{pay_period.replace('/', '-')}.pdf",
                        mime="application/pdf",
                        key=f"dl_{run_id}",
                        use_container_width=True,
                    )
            with a3:
                if st.button("📋 View flag sheet", key=f"flag_{run_id}", use_container_width=True):
                    if loaded:
                        st.session_state.flag_pdf_bytes = loaded.get("flag_pdf_bytes")
                        st.session_state.flag_pdf_filename = loaded.get("flag_pdf_filename", "")
                        st.session_state.pdf_loaded = bool(loaded.get("flag_pdf_bytes"))
                        st.session_state.pending_nav = "Flag Sheet"
                        st.rerun()
            with a4:
                st.caption(f"ID: {run_id[:8]}…")

            st.markdown("---")

    st.markdown(
        section_title("Service Advisor Payroll", "Completed pay periods"),
        unsafe_allow_html=True,
    )

    advisor_runs = list_advisor_payroll_runs()

    if not advisor_runs:
        st.markdown(
            status_banner(
                "No completed advisor payroll yet. Finish on **Payroll → Service Advisors** "
                "and click **Complete & Save**.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
    else:
        for run in advisor_runs:
            run_id = run["id"]
            pay_period = run.get("pay_period", "—")
            completed = _fmt_date(run.get("completed_at", ""))
            grand = _money(run.get("grand_total"))
            loaded = load_advisor_payroll_run(run_id)

            with st.container():
                c1, c2, c3 = st.columns([2.5, 2, 1])
                with c1:
                    st.markdown(f"### {pay_period}")
                    st.caption(f"Completed {completed}")
                with c2:
                    st.markdown(f"**{grand}**")
                    st.caption(
                        f"{int(run.get('advisor_count', 0))} advisors · Completed"
                    )
                with c3:
                    st.markdown('<span class="badge badge-live">Saved</span>', unsafe_allow_html=True)

                a1, a2, a3 = st.columns(3)
                with a1:
                    if st.button("✏️ Reopen & edit", key=f"adv_reopen_{run_id}", use_container_width=True):
                        if loaded:
                            apply_advisor_snapshot_to_session(
                                loaded["snapshot"],
                                run_id,
                                status=loaded.get("status", "completed"),
                            )
                            st.session_state.pending_nav = "Payroll"
                            st.rerun()
                with a2:
                    if loaded:
                        export_snap = loaded["snapshot"].get("export", {})
                        st.download_button(
                            "📄 Export PDF",
                            data=generate_advisor_payroll_pdf(export_snap),
                            file_name=f"ADVISOR_PAYROLL_{pay_period.replace('/', '-')}.pdf",
                            mime="application/pdf",
                            key=f"adv_dl_{run_id}",
                            use_container_width=True,
                        )
                with a3:
                    st.caption(f"ID: {run_id[:8]}…")

                st.markdown("---")
