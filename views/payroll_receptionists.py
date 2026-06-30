import streamlit as st
import pandas as pd

from components.ui import stat_card, status_banner
from lib.receptionist_payroll_calc import (
    DEFAULT_WARRANTY_BONUS,
    TIRE_PAY_RATE,
    calculate_receptionist_payroll,
)
from lib.receptionist_payroll_export_data import build_receptionist_payroll_snapshot
from lib.receptionist_payroll_parser import parse_cashiers_report
from lib.receptionist_payroll_pdf_export import generate_receptionist_payroll_pdf
from lib.receptionist_payroll_storage import save_receptionist_payroll_run
from lib.receptionist_roster import (
    add_employee,
    clone_roster,
    flatten_roster,
    remove_employee,
    reset_roster,
    save_roster,
    update_employee,
)
from views.receptionist_payroll_helpers import (
    all_receptionists_synced,
    apply_cashiers_report_to_session,
    apply_receptionist_value_store,
    apply_roster_to_session,
    capture_open_receptionist_inputs,
    capture_receptionist_values,
    form_key,
    init_receptionist_payroll_session,
    rec_key,
    refresh_receptionist_value_store,
    save_receptionist_form,
    section_open_key,
    section_toggle_key,
    sync_all_appointment_rates_to_roster,
    sync_receptionist,
    toggle_receptionist_section,
    _appointment_rate_text_key,
    _read_appointment_rate,
    _tires_text_key,
)
from views.payroll_helpers import render_payroll_sync_error, render_roster_sync_error


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _apply_roster_change(mutator):
    rows = flatten_roster(st.session_state.receptionist_roster)
    values = capture_receptionist_values(rows)
    roster = clone_roster(st.session_state.receptionist_roster)
    ok, message = mutator(roster)
    if not ok:
        st.warning(message)
        return
    save_roster(roster)
    apply_roster_to_session(roster, values)
    st.success(message)
    st.rerun()


def _render_roster_manager():
    with st.expander("👥 Manage receptionist roster", expanded=False):
        render_roster_sync_error("_receptionist_roster_sync_error")
        st.caption("Add, edit, or remove receptionists. $/appointment saves when you change it in each person's section.")

        for row in flatten_roster(st.session_state.receptionist_roster):
            c1, c2, c3 = st.columns([2, 2.2, 0.8])
            with c1:
                st.write(row.name)
                if row.has_warranty_bonus:
                    st.caption(f"Warranty bonus eligible · {_money(row.warranty_bonus_amount)}")
            with c2:
                codes = ", ".join(row.taker_codes) if row.taker_codes else "—"
                st.caption(f"Last name: {row.last_name or '—'} · Codes: {codes}")
            with c3:
                with st.popover("Edit", use_container_width=True):
                    new_name = st.text_input("Name", value=row.name, key=f"rec_edit_name_{row.name}")
                    new_last = st.text_input(
                        "Last name (for CASHIERS match)",
                        value=row.last_name,
                        key=f"rec_edit_last_{row.name}",
                    )
                    new_codes = st.text_input(
                        "Taker codes (comma-separated)",
                        value=", ".join(row.taker_codes),
                        key=f"rec_edit_codes_{row.name}",
                    )
                    warranty_eligible = st.checkbox(
                        "Extended warranty schedule bonus",
                        value=row.has_warranty_bonus,
                        key=f"rec_edit_warranty_{row.name}",
                    )
                    warranty_amount = st.number_input(
                        "Warranty bonus amount ($)",
                        min_value=0.0,
                        step=1.0,
                        value=float(row.warranty_bonus_amount or DEFAULT_WARRANTY_BONUS),
                        key=f"rec_edit_warranty_amt_{row.name}",
                    )
                    if st.button("Save changes", key=f"rec_save_{row.name}", use_container_width=True):
                        codes = [c.strip() for c in new_codes.split(",") if c.strip()]
                        _apply_roster_change(
                            lambda r, n=row.name: (
                                update_employee(
                                    r,
                                    n,
                                    new_name=new_name.strip() or n,
                                    last_name=new_last,
                                    taker_codes=codes,
                                    has_warranty_bonus=warranty_eligible,
                                    warranty_bonus_amount=warranty_amount,
                                )
                            )
                        )
                if st.button("Remove", key=f"rec_rm_{row.name}", use_container_width=True):
                    _apply_roster_change(lambda r, n=row.name: remove_employee(r, n))

        st.markdown("**Add receptionist**")
        c1, c2, c3, c4 = st.columns([2, 1.2, 1.5, 0.8])
        with c1:
            new_name = st.text_input("Name", key="rec_add_name", placeholder="First Last")
        with c2:
            new_last = st.text_input("Last name", key="rec_add_last", placeholder="SMITH")
        with c3:
            new_codes = st.text_input("Taker codes", key="rec_add_codes", placeholder="22SMITHJ")
        with c4:
            if st.button("Add", key="rec_add_btn", use_container_width=True):
                codes = [c.strip() for c in new_codes.split(",") if c.strip()]
                _apply_roster_change(
                    lambda r: add_employee(
                        r,
                        new_name,
                        last_name=new_last,
                        taker_codes=codes,
                    )
                )

        if st.button("Reset roster to defaults", key="rec_reset_roster"):
            values = capture_receptionist_values(flatten_roster(st.session_state.receptionist_roster))
            apply_roster_to_session(reset_roster(), values)
            st.success("Roster reset.")
            st.rerun()


def _summary_row(row, synced, result) -> dict:
    return {
        "Receptionist": row.name,
        "$/Appt": synced.appointment_rate,
        "Appts": synced.appointments_set,
        "Appt Pay": result.appointment_pay,
        "Tires": synced.tires_sold,
        "Tire Pay": result.tire_pay,
        "Warranty": result.warranty_pay,
        "SPIFF": result.spiff_pay,
        "Total Pay": result.total_pay,
    }


def _render_receptionist_section(row) -> None:
    st.caption("Enter all values, then click **Save entries** — the section stays open and both fields save together.")

    with st.form(key=form_key(row.name), clear_on_submit=False):
        st.text_input(
            "$ per appointment set",
            key=_appointment_rate_text_key(row.name),
            help="Type the dollars paid per appointment (e.g. 3 or 3.00).",
        )

        c1, c2 = st.columns(2)
        with c1:
            appointments_set = sync_receptionist(row).appointments_set
            st.metric(
                "Appointments set",
                f"{appointments_set:.0f}",
                help="Auto-filled from CASHIERS .xlsx by last name / taker code.",
            )
        with c2:
            st.text_input(
                f"Tires sold (${TIRE_PAY_RATE:.0f} each)",
                key=_tires_text_key(row.name),
                help="Type the number of tires sold this pay period.",
            )

        if row.has_warranty_bonus:
            st.checkbox(
                f"Extended warranty schedule bonus — {_money(row.warranty_bonus_amount)}",
                key=rec_key(row.name, "warranty_bonus"),
                help="Turn on when this receptionist earned the monthly extended warranty bonus.",
            )

        st.number_input(
            "SPIFF ($)",
            min_value=0.0,
            step=1.0,
            key=rec_key(row.name, "spiff"),
        )

        st.text_area(
            "Notes for payroll clerk",
            key=rec_key(row.name, "notes"),
            placeholder="Optional — prints on the payroll PDF for accounting",
            height=68,
        )

        submitted = st.form_submit_button("Save entries", use_container_width=True, type="primary")

    if submitted:
        save_receptionist_form(row.name)

    synced = sync_receptionist(row)
    result = calculate_receptionist_payroll(synced)

    pay_rows = [
        {
            "Pay": "Appointment pay",
            "Amount": result.appointment_pay,
            "Detail": f"{synced.appointments_set:.0f} appts × {_money(synced.appointment_rate)}",
        },
        {
            "Pay": "Tire pay",
            "Amount": result.tire_pay,
            "Detail": f"{synced.tires_sold:.0f} tires × {_money(TIRE_PAY_RATE)}",
        },
    ]
    if row.has_warranty_bonus:
        pay_rows.append({
            "Pay": "Warranty bonus",
            "Amount": result.warranty_pay,
            "Detail": "Qualified" if synced.warranty_bonus_qualified else "Toggle off",
        })
    pay_rows.extend([
        {"Pay": "SPIFF", "Amount": result.spiff_pay, "Detail": ""},
        {"Pay": "TOTAL", "Amount": result.total_pay, "Detail": ""},
    ])
    st.dataframe(
        pd.DataFrame(pay_rows),
        use_container_width=True,
        hide_index=True,
        column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
    )


def render():
    init_receptionist_payroll_session()

    st.markdown(
        '<span class="legend-chip chip-manual">Click a name · enter values · click Save entries</span> '
        '<span class="legend-chip chip-calc">Appointments from CASHIERS .xlsx</span> '
        '<span class="legend-chip chip-live">Changes save automatically</span>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("active_receptionist_run_id"):
        label = "Reopened" if st.session_state.get("receptionist_payroll_completed") else "Editing"
        st.markdown(
            status_banner(
                f"{label} receptionist payroll · {st.session_state.pay_period or '—'} · "
                "Make corrections, export PDF, then check Complete & Save again.",
                "warn" if label == "Reopened" else "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_receptionist_payroll_sync_error", table="receptionist_payroll_runs")

    report_file = st.file_uploader(
        "Upload CASHIERS report (.xlsx)",
        type=["xlsx"],
        help="Import from OFFICE SCANNER/CASHIERS .xlsx — fills appointments by last name / taker code.",
    )

    if report_file:
        try:
            matched = apply_cashiers_report_to_session(parse_cashiers_report(report_file))
            st.markdown(
                status_banner(
                    f"✓ Loaded CASHIERS report — matched {matched} receptionists",
                    "success",
                ),
                unsafe_allow_html=True,
            )
        except Exception as exc:
            st.markdown(status_banner(f"Report import failed: {exc}", "warn"), unsafe_allow_html=True)

    if not st.session_state.receptionist_report_loaded:
        st.info("Upload CASHIERS .xlsx to auto-fill appointments set.")

    _render_roster_manager()
    st.markdown("---")
    st.caption("Click a receptionist's name to open their pay details.")

    employee_rows = flatten_roster(st.session_state.receptionist_roster)
    apply_receptionist_value_store()

    employee_names = [row.name for row in employee_rows]
    for row in employee_rows:
        open_key = section_open_key(row.name)
        is_open = bool(st.session_state.get(open_key, False))
        synced = next(s for s in all_receptionists_synced() if s.name == row.name)
        result = calculate_receptionist_payroll(synced)
        arrow = "▼" if is_open else "▶"
        display_rate = float(synced.appointment_rate or row.appointment_rate or 0)
        button_label = (
            f"{arrow}  {row.name}  ·  {_money(display_rate)}/appt  ·  "
            f"Total {_money(result.total_pay)}"
        )
        if st.button(
            button_label,
            key=section_toggle_key(row.name),
            use_container_width=True,
            type="primary" if is_open else "secondary",
        ):
            toggle_receptionist_section(row.name, employee_names)

        if is_open:
            _render_receptionist_section(row)

    synced_employees = all_receptionists_synced()
    employee_results = [calculate_receptionist_payroll(e) for e in synced_employees]
    summary_rows = [
        _summary_row(row, synced_employees[i], employee_results[i])
        for i, row in enumerate(employee_rows)
    ]
    grand_total = sum(r["Total Pay"] for r in summary_rows)

    st.markdown("---")
    st.markdown("##### Receptionist payroll summary")
    st.dataframe(
        pd.DataFrame(summary_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "$/Appt": st.column_config.NumberColumn(format="$%.2f"),
            "Appts": st.column_config.NumberColumn(format="%.0f"),
            "Appt Pay": st.column_config.NumberColumn(format="$%.2f"),
            "Tires": st.column_config.NumberColumn(format="%.0f"),
            "Tire Pay": st.column_config.NumberColumn(format="$%.2f"),
            "Warranty": st.column_config.NumberColumn(format="$%.2f"),
            "SPIFF": st.column_config.NumberColumn(format="$%.2f"),
            "Total Pay": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            stat_card("Receptionists", str(len(employee_rows)), "violet", "🧑‍💼"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(stat_card("Total Pay", _money(grand_total), "green", "💰"), unsafe_allow_html=True)

    if employee_rows and st.session_state.get("pay_period"):
        period_slug = (st.session_state.pay_period or "payroll").replace("/", "-")
        capture_open_receptionist_inputs()
        export_synced = all_receptionists_synced()
        export_results = [calculate_receptionist_payroll(e) for e in export_synced]
        export_pdf = generate_receptionist_payroll_pdf(
            build_receptionist_payroll_snapshot(
                export_synced,
                export_results,
                st.session_state.pay_period,
            )
        )
        st.download_button(
            label="📄 Export receptionist payroll PDF for accounting",
            data=export_pdf,
            file_name=f"RECEPTIONIST_PAYROLL_{period_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )

        st.markdown("---")
        st.markdown("##### ✅ Complete receptionist payroll")
        st.markdown(
            '<div class="glass-panel"><p style="color:#94a3b8;margin:0;">'
            "Saves this pay period to <strong>Reports → Receptionist Payroll</strong>. "
            "Reopen anytime from Reports to fix and resubmit.</p></div>",
            unsafe_allow_html=True,
        )

        if saved_period := st.session_state.pop("_receptionist_payroll_saved_period", None):
            if st.session_state.get("_receptionist_payroll_sync_error"):
                st.error(
                    f"Receptionist payroll for {saved_period} was saved on this session only — "
                    "cloud backup failed. Open Reports after fixing the connection, or save again."
                )
            else:
                st.success(f"Receptionist payroll saved — find it in Reports under {saved_period}")
                st.balloons()

        confirm = st.checkbox(
            "This receptionist payroll is complete and ready to save",
            key="receptionist_payroll_complete_confirm",
            on_change=capture_open_receptionist_inputs,
        )

        if st.button(
            "Complete & Save to Reports",
            type="primary",
            disabled=not confirm,
            use_container_width=True,
        ):
            capture_open_receptionist_inputs()
            refresh_receptionist_value_store()
            for row in employee_rows:
                update_employee(
                    st.session_state.receptionist_roster,
                    row.name,
                    appointment_rate=_read_appointment_rate(row.name, row),
                )
            save_roster(st.session_state.receptionist_roster)
            run_id, sync_error = save_receptionist_payroll_run(
                all_receptionists_synced(),
                st.session_state.pay_period,
                run_id=st.session_state.get("active_receptionist_run_id"),
                status="completed",
            )
            st.session_state.active_receptionist_run_id = run_id
            st.session_state.receptionist_payroll_completed = True
            if sync_error:
                st.session_state["_receptionist_payroll_sync_error"] = sync_error
            else:
                st.session_state.pop("_receptionist_payroll_sync_error", None)
            st.session_state["_receptionist_payroll_saved_period"] = st.session_state.pay_period
            del st.session_state["receptionist_payroll_complete_confirm"]
            st.rerun()

    sync_all_appointment_rates_to_roster()
    capture_open_receptionist_inputs()
