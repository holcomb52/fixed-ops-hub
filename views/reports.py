from datetime import date, datetime
from typing import Callable, Optional

import pandas as pd
import streamlit as st

from components.ui import (
    page_hero,
    report_run_summary_card,
    report_section_header,
    status_banner,
    team_section_divider,
)
from lib.earnings_report import (
    collect_earnings_lines,
    format_month_label,
    month_range_for_date,
    summarize_earnings,
)
from lib.earnings_report_pdf_export import generate_earnings_report_pdf
from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_pdf_export import generate_payroll_pdf
from lib.advisor_payroll_pdf_export import generate_advisor_payroll_pdf
from lib.advisor_payroll_storage import (
    apply_advisor_snapshot_to_session,
    delete_advisor_payroll_run,
    list_advisor_payroll_runs,
    load_advisor_payroll_run,
)
from lib.receptionist_payroll_pdf_export import generate_receptionist_payroll_pdf
from lib.receptionist_payroll_storage import (
    apply_receptionist_snapshot_to_session,
    delete_receptionist_payroll_run,
    list_receptionist_payroll_runs,
    load_receptionist_payroll_run,
)
from lib.payroll_storage import (
    apply_snapshot_to_session,
    delete_payroll_run,
    list_payroll_runs,
    load_payroll_run,
    snapshot_to_teams,
)
from lib.supabase_client import is_configured
from lib.warranty_labor_calc import summarize_reviewed_running_total, summarize_rows
from lib.warranty_labor_storage import (
    apply_warranty_snapshot_to_session,
    delete_warranty_labor_run,
    deserialize_warranty_row,
    list_warranty_labor_runs,
    load_warranty_labor_run,
)
from lib.warranty_labor_pdf_export import (
    generate_warranty_analysis_pdf,
    generate_warranty_original_pdf,
)
from views.payroll_helpers import init_payroll_session

ACCENT_TECH = "orange"
ACCENT_ADVISOR = "cyan"
ACCENT_RECEPTIONIST = "violet"
ACCENT_WARRANTY = "amber"


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


def _run_status_badge(run: dict) -> str:
    if run.get("status") == "draft":
        return '<span class="badge badge-soon">Draft</span>'
    return '<span class="badge badge-live">Saved</span>'


def _run_status_caption(run: dict, completed: str) -> str:
    if run.get("status") == "draft":
        return f"Draft · last updated {completed}"
    return f"Completed {completed}"


def _render_earnings_lookup():
    with st.expander("Employee earnings lookup — search by month", expanded=False):
        st.caption(
            "Totals include saved payroll runs whose pay period **starts** in the month you pick. "
            "Pick any day in that month — June 3 and June 28 both mean all of June."
        )

        default_month = date.today()

        c1, c2, c3 = st.columns([1, 1.2, 1.2])
        with c1:
            month_date = st.date_input(
                "Month",
                value=default_month,
                key="earnings_month_date",
                help="Any day in the month you want to total.",
            )
        with c2:
            role_filter = st.selectbox(
                "Employee type",
                ["All", "Technician", "Service Advisor", "Receptionist"],
                key="earnings_role_filter",
            )
        with c3:
            name_query = st.text_input(
                "Search name",
                placeholder="Optional — filter by employee name",
                key="earnings_name_query",
            )

        month_start, month_end = month_range_for_date(month_date)
        month_label = format_month_label(month_date)
        lines = collect_earnings_lines(month_date, role_filter, name_query)
        summaries = summarize_earnings(lines)

        if not summaries:
            st.markdown(
                status_banner(
                    f"No saved payroll found with a start date in **{month_label}**. "
                    "Complete payroll on the Payroll tab first, then return here.",
                    "warn",
                ),
                unsafe_allow_html=True,
            )
            return

        grand_total = sum(item.total_pay for item in summaries)
        period_count = len({line.pay_period for line in lines})
        m1, m2, m3, m4 = st.columns([1, 1, 1, 1.2])
        with m1:
            st.metric("Employees", len(summaries))
        with m2:
            st.metric("Pay periods", period_count)
        with m3:
            st.metric("Total paid", _money(grand_total))
        with m4:
            pdf_name = f"EMPLOYEE_EARNINGS_{month_start.strftime('%m-%Y')}.pdf"
            st.download_button(
                "📄 Export PDF",
                data=generate_earnings_report_pdf(
                    month_start,
                    month_end,
                    month_label,
                    role_filter,
                    name_query,
                    summaries,
                    lines,
                ),
                file_name=pdf_name,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )

        summary_rows = [
            {
                "Employee": item.name,
                "Type": item.role,
                "Pay periods": len(item.pay_periods),
                "Total earned": item.total_pay,
            }
            for item in summaries
        ]
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Total earned": st.column_config.NumberColumn(format="$%.2f"),
            },
        )

        with st.expander("Pay period breakdown", expanded=False):
            detail_rows = [
                {
                    "Employee": line.name,
                    "Type": line.role,
                    "Pay period": line.pay_period,
                    "Period start": line.period_start.strftime("%m/%d/%Y"),
                    "Period end": line.period_end.strftime("%m/%d/%Y"),
                    "Earned": line.total_pay,
                }
                for line in lines
            ]
            st.dataframe(
                pd.DataFrame(detail_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Earned": st.column_config.NumberColumn(format="$%.2f"),
                },
            )


def _delete_confirm_key(prefix: str, run_id: str) -> str:
    return f"report_delete_confirm_{prefix}_{run_id}"


def _clear_active_report_session(active_key: str, run_id: str, extra_keys: Optional[list[str]] = None):
    if st.session_state.get(active_key) != run_id:
        return
    st.session_state.pop(active_key, None)
    for key in extra_keys or []:
        st.session_state.pop(key, None)


def _render_delete_report_button(prefix: str, run_id: str):
    if st.button("🗑 Delete", key=f"{prefix}_delete_{run_id}", use_container_width=True):
        st.session_state[_delete_confirm_key(prefix, run_id)] = run_id
        st.rerun()


def _render_delete_report_controls(
    *,
    prefix: str,
    run_id: str,
    run_label: str,
    delete_fn: Callable[[str], tuple[bool, str]],
    active_session_key: Optional[str] = None,
    extra_clear_keys: Optional[list[str]] = None,
):
    confirm_key = _delete_confirm_key(prefix, run_id)
    if st.session_state.get(confirm_key) != run_id:
        return

    st.warning(f"Delete **{run_label}**? This cannot be undone.")
    yes_col, no_col = st.columns(2)
    with yes_col:
        if st.button(
            "Yes, delete report",
            key=f"{prefix}_delete_yes_{run_id}",
            use_container_width=True,
            type="primary",
        ):
            ok, err = delete_fn(run_id)
            st.session_state.pop(confirm_key, None)
            if not ok:
                st.error(err or "Could not delete this report.")
            else:
                if active_session_key:
                    _clear_active_report_session(active_session_key, run_id, extra_clear_keys)
                if err:
                    st.warning(err)
                else:
                    st.success(f"Deleted {run_label}.")
                st.rerun()
    with no_col:
        if st.button(
            "Cancel",
            key=f"{prefix}_delete_no_{run_id}",
            use_container_width=True,
        ):
            st.session_state.pop(confirm_key, None)
            st.rerun()


def _export_pdf_from_run(loaded: dict) -> bytes:
    snap = loaded.get("snapshot", {})
    teams = snapshot_to_teams(snap)
    export_snap = build_payroll_snapshot(teams, snap.get("pay_period", ""))
    return generate_payroll_pdf(export_snap)


def _render_warranty_runs():
    warranty_runs = list_warranty_labor_runs()

    st.markdown(team_section_divider(ACCENT_WARRANTY), unsafe_allow_html=True)
    st.markdown(
        report_section_header(
            "Warranty ELR Analysis",
            "Saved warranty labor rate runs",
            accent=ACCENT_WARRANTY,
            icon="📊",
            run_count=len(warranty_runs) if warranty_runs else None,
        ),
        unsafe_allow_html=True,
    )

    if not warranty_runs:
        st.markdown(
            status_banner(
                "No saved warranty ELR analysis yet. Finish on **Warranty** "
                "and click **Save to Reports**.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
        return

    for run in warranty_runs:
        run_id = run["id"]
        run_label = run.get("run_label") or run.get("source_name", "—")
        completed = _fmt_date(run.get("completed_at", ""))
        shop_elr = _money(run.get("effective_labor_rate"))
        loaded = load_warranty_labor_run(run_id)

        st.markdown(
            report_run_summary_card(
                run_label,
                ACCENT_WARRANTY,
                caption=f"Saved {completed}",
                amount=shop_elr,
                meta=(
                    f"{int(run.get('included_rows', 0))}/{int(run.get('total_rows', 0))} included lines"
                ),
                badge_html='<span class="badge badge-live">Saved</span>',
            ),
            unsafe_allow_html=True,
        )
        a1, a2, a3, a4 = st.columns(4)
        with a1:
            if st.button(
                "✏️ Reopen & edit",
                key=f"warranty_reopen_{run_id}",
                use_container_width=True,
            ):
                if loaded:
                    apply_warranty_snapshot_to_session(loaded, run_id)
                    st.session_state.pending_nav = "Warranty"
                    st.rerun()
        with a2:
            if loaded:
                snapshot = loaded.get("snapshot", {})
                rows = [
                    deserialize_warranty_row(item, index=index)
                    for index, item in enumerate(snapshot.get("rows", []))
                ]
                reviewed = snapshot.get("reviewed_recids", [])
                summary = summarize_reviewed_running_total(rows, reviewed)
                running_rows = [
                    row
                    for row in rows
                    if str(row.recid).strip() in {str(r).strip() for r in reviewed}
                ]
                st.download_button(
                    "📄 Analysis PDF",
                    data=generate_warranty_analysis_pdf(
                        running_rows if running_rows else rows,
                        summary,
                        snapshot.get("source_name", "warranty_labor.xlsx"),
                        snapshot.get("sheet_name", "Sheet1"),
                    ),
                    file_name=f"WARRANTY_ELR_ANALYSIS_{run_label.replace('/', '-').replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key=f"warranty_analysis_dl_{run_id}",
                    use_container_width=True,
                )
        with a3:
            if loaded:
                snapshot = loaded.get("snapshot", {})
                rows = [
                    deserialize_warranty_row(item, index=index)
                    for index, item in enumerate(snapshot.get("rows", []))
                ]
                st.download_button(
                    "📄 Original PDF",
                    data=generate_warranty_original_pdf(
                        rows,
                        snapshot.get("source_name", "warranty_labor.xlsx"),
                        snapshot.get("sheet_name", "Sheet1"),
                    ),
                    file_name=f"WARRANTY_ELR_ORIGINAL_{run_label.replace('/', '-').replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key=f"warranty_original_dl_{run_id}",
                    use_container_width=True,
                )
        with a4:
            _render_delete_report_button("warranty", run_id)
        _render_delete_report_controls(
            prefix="warranty",
            run_id=run_id,
            run_label=run_label,
            delete_fn=delete_warranty_labor_run,
            active_session_key="active_warranty_run_id",
        )
        st.caption(f"ID: {run_id[:8]}…")
        st.markdown('<div class="report-run-spacer"></div>', unsafe_allow_html=True)


def render():
    init_payroll_session()

    st.markdown(
        page_hero(
            "Reports",
            "Saved payroll and warranty ELR runs — reopen any report to pick up where you left off.",
            tag="History",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if not is_configured():
        st.caption("Payroll history is saved locally. Connect Supabase to sync across devices.")

    _render_earnings_lookup()
    st.markdown(team_section_divider(ACCENT_TECH), unsafe_allow_html=True)

    runs = list_payroll_runs()
    st.markdown(
        report_section_header(
            "Technician Payroll",
            "Saved pay periods",
            accent=ACCENT_TECH,
            icon="🔧",
            run_count=len(runs) if runs else None,
        ),
        unsafe_allow_html=True,
    )

    if not runs:
        st.markdown(
            status_banner(
                "No completed technician payroll yet. Finish on **Payroll → Technicians** "
                "and click **Complete & Save**.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
    else:
        for run in runs:
            run_id = run["id"]
            pay_period = run.get("pay_period", "—")
            completed = _fmt_date(run.get("completed_at", ""))
            grand = _money(run.get("grand_total"))
            loaded = load_payroll_run(run_id)
            hours_caption = f"{float(run.get('grand_hours', 0)):.2f} hours"
            hours_meta = (
                f"{hours_caption} · Completed"
                if run.get("status") != "draft"
                else f"{hours_caption} · In progress"
            )

            st.markdown(
                report_run_summary_card(
                    pay_period,
                    ACCENT_TECH,
                    caption=_run_status_caption(run, completed),
                    amount=grand,
                    meta=hours_meta,
                    badge_html=_run_status_badge(run),
                ),
                unsafe_allow_html=True,
            )
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
                _render_delete_report_button("tech", run_id)
            _render_delete_report_controls(
                prefix="tech",
                run_id=run_id,
                run_label=pay_period,
                delete_fn=delete_payroll_run,
                active_session_key="active_run_id",
                extra_clear_keys=["payroll_completed", "pdf_loaded"],
            )
            st.caption(f"ID: {run_id[:8]}…")
            st.markdown('<div class="report-run-spacer"></div>', unsafe_allow_html=True)

    st.markdown(team_section_divider(ACCENT_ADVISOR), unsafe_allow_html=True)

    advisor_runs = list_advisor_payroll_runs()
    st.markdown(
        report_section_header(
            "Service Advisor Payroll",
            "Saved pay periods",
            accent=ACCENT_ADVISOR,
            icon="👔",
            run_count=len(advisor_runs) if advisor_runs else None,
        ),
        unsafe_allow_html=True,
    )

    if not advisor_runs:
        st.markdown(
            status_banner(
                "No saved advisor payroll in Reports yet. On Streamlit Cloud, payroll is stored in "
                "the database when you click **Complete & Save** on **Payroll → Service Advisors**. "
                "If you already finished that pay period, open it again and save once more.",
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
            count = int(run.get("advisor_count", 0))
            count_meta = (
                f"{count} advisors · Completed"
                if run.get("status") != "draft"
                else f"{count} advisors · In progress"
            )

            st.markdown(
                report_run_summary_card(
                    pay_period,
                    ACCENT_ADVISOR,
                    caption=_run_status_caption(run, completed),
                    amount=grand,
                    meta=count_meta,
                    badge_html=_run_status_badge(run),
                ),
                unsafe_allow_html=True,
            )
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
                _render_delete_report_button("adv", run_id)
            _render_delete_report_controls(
                prefix="adv",
                run_id=run_id,
                run_label=pay_period,
                delete_fn=delete_advisor_payroll_run,
                active_session_key="active_advisor_run_id",
                extra_clear_keys=["advisor_payroll_completed"],
            )
            st.caption(f"ID: {run_id[:8]}…")
            st.markdown('<div class="report-run-spacer"></div>', unsafe_allow_html=True)

    st.markdown(team_section_divider(ACCENT_RECEPTIONIST), unsafe_allow_html=True)

    receptionist_runs = list_receptionist_payroll_runs()
    st.markdown(
        report_section_header(
            "Receptionist Payroll",
            "Saved pay periods",
            accent=ACCENT_RECEPTIONIST,
            icon="🧑‍💼",
            run_count=len(receptionist_runs) if receptionist_runs else None,
        ),
        unsafe_allow_html=True,
    )

    if not receptionist_runs:
        st.markdown(
            status_banner(
                "No saved receptionist payroll in Reports yet. On Streamlit Cloud, payroll is stored in "
                "the database when you click **Complete & Save** on **Payroll → Receptionists**. "
                "If you already finished that pay period, open it again and save once more.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
    else:
        for run in receptionist_runs:
            run_id = run["id"]
            pay_period = run.get("pay_period", "—")
            completed = _fmt_date(run.get("completed_at", ""))
            grand = _money(run.get("grand_total"))
            loaded = load_receptionist_payroll_run(run_id)
            count = int(run.get("employee_count", 0))
            count_meta = (
                f"{count} employees · Completed"
                if run.get("status") != "draft"
                else f"{count} employees · In progress"
            )

            st.markdown(
                report_run_summary_card(
                    pay_period,
                    ACCENT_RECEPTIONIST,
                    caption=_run_status_caption(run, completed),
                    amount=grand,
                    meta=count_meta,
                    badge_html=_run_status_badge(run),
                ),
                unsafe_allow_html=True,
            )
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button(
                    "✏️ Reopen & edit",
                    key=f"rec_reopen_{run_id}",
                    use_container_width=True,
                ):
                    if loaded:
                        apply_receptionist_snapshot_to_session(
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
                        data=generate_receptionist_payroll_pdf(export_snap),
                        file_name=f"RECEPTIONIST_PAYROLL_{pay_period.replace('/', '-')}.pdf",
                        mime="application/pdf",
                        key=f"rec_dl_{run_id}",
                        use_container_width=True,
                    )
            with a3:
                _render_delete_report_button("rec", run_id)
            _render_delete_report_controls(
                prefix="rec",
                run_id=run_id,
                run_label=pay_period,
                delete_fn=delete_receptionist_payroll_run,
                active_session_key="active_receptionist_run_id",
                extra_clear_keys=["receptionist_payroll_completed"],
            )
            st.caption(f"ID: {run_id[:8]}…")
            st.markdown('<div class="report-run-spacer"></div>', unsafe_allow_html=True)

    _render_warranty_runs()
