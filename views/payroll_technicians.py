import streamlit as st
import pandas as pd

from components.ui import stat_card, status_banner
from lib.flag_pdf_parser import parse_flag_sheet
from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_pdf_export import generate_payroll_pdf
from lib.tech_payroll_calc import (
    PROD_BONUS_TIERS,
    all_hours_by_name,
    apply_flag_data,
    apply_tech_numbers,
    team_totals,
)
from lib.payroll_storage import save_payroll_run
from lib.tech_roster import (
    ROLE_OPTIONS,
    add_technician,
    clone_teams,
    move_technician,
    remove_technician,
    reset_roster,
    role_label,
    role_option_key,
    save_roster,
    update_technician,
)
from views.payroll_helpers import (
    all_rows_synced,
    apply_teams_to_session,
    capture_tech_values,
    ensure_all_row_fields,
    field_key,
    init_payroll_session,
    parse_period_token,
    set_pay_period_dates,
    store_flag_pdf,
    sync_row,
)


def _team_hours(team_name: str, count: int) -> float:
    return sum(float(st.session_state[field_key(team_name, i, "hours")]) for i in range(count))


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _apply_pdf_to_state(flag_map: dict):
    ensure_all_row_fields()
    for team_name, rows in st.session_state.tech_teams.items():
        for i, row in enumerate(rows):
            if row.name in flag_map:
                hours, dollars = flag_map[row.name]
                st.session_state[field_key(team_name, i, "hours")] = float(hours)
                st.session_state[field_key(team_name, i, "dollars")] = float(dollars)
                row.flat_rate_hours = hours
                row.dollars_earned = dollars


def _apply_roster_change(mutator):
    values = capture_tech_values(st.session_state.tech_teams)
    teams = clone_teams(st.session_state.tech_teams)
    ok, message = mutator(teams)
    if not ok:
        st.warning(message)
        return
    save_roster(teams)
    apply_teams_to_session(teams, values)
    st.success(message)
    st.rerun()


def _render_roster_manager():
    with st.expander("👥 Manage team roster", expanded=False):
        st.caption(
            "Add new hires, remove terminations, or move technicians between teams. "
            "Changes save automatically and apply to future pay periods."
        )

        team_names = list(st.session_state.tech_teams.keys())

        for team_name in team_names:
            rows = st.session_state.tech_teams[team_name]
            st.markdown(f"**{team_name}** · {len(rows)} technicians")
            st.caption(f"Everyone listed below is on **{team_name}**.")

            if not rows:
                st.caption("No technicians on this team.")
            else:
                h1, h2, h3, h4, h5, h6 = st.columns([0.7, 2, 1, 1.2, 0.9, 0.9])
                with h1:
                    st.caption("Tech #")
                with h2:
                    st.caption("Technician")
                with h3:
                    st.caption("Rate")
                with h4:
                    st.caption("Role")
                with h5:
                    st.caption("Actions")
                with h6:
                    st.caption("")

            for i, row in enumerate(rows):
                c1, c2, c3, c4, c5, c6 = st.columns([0.7, 2, 1, 1.2, 0.9, 0.9])
                with c1:
                    st.caption(row.tech_number or "—")
                with c2:
                    st.write(row.name)
                with c3:
                    st.caption(f"${row.hourly_rate:.2f}/hr")
                with c4:
                    st.caption(role_label(row))
                with c5:
                    other_teams = [t for t in team_names if t != team_name]
                    if other_teams:
                        with st.popover("Move", use_container_width=True):
                            st.caption(f"Move **{row.name}** from {team_name} to:")
                            dest = st.radio(
                                "Destination team",
                                other_teams,
                                key=f"move_dest_{team_name}_{i}",
                                label_visibility="collapsed",
                            )
                            if st.button("Confirm move", key=f"move_{team_name}_{i}", use_container_width=True):
                                _apply_roster_change(
                                    lambda teams, tn=team_name, idx=i, dt=dest: move_technician(teams, tn, idx, dt)
                                )
                with c6:
                    if st.button("Remove", key=f"remove_{team_name}_{i}", use_container_width=True):
                        _apply_roster_change(
                            lambda teams, tn=team_name, idx=i: remove_technician(teams, tn, idx)
                        )

            with st.form(f"add_tech_{team_name}", clear_on_submit=True):
                st.markdown(f"**Add to {team_name}**")
                a1, a2, a3, a4 = st.columns([1, 2, 1, 1.5])
                with a1:
                    new_number = st.text_input("Tech #", key=f"new_number_{team_name}")
                with a2:
                    new_name = st.text_input("Name", key=f"new_name_{team_name}")
                with a3:
                    new_rate = st.number_input("Hourly rate", min_value=0.0, step=0.25, key=f"new_rate_{team_name}")
                with a4:
                    new_role = st.selectbox("Role", list(ROLE_OPTIONS.keys()), key=f"new_role_{team_name}")
                if st.form_submit_button("Add technician", use_container_width=True):
                    _apply_roster_change(
                        lambda teams, tn=team_name, num=new_number, nm=new_name, rt=new_rate, rl=new_role: add_technician(
                            teams, tn, nm, rt, num, rl
                        )
                    )

            st.markdown("---")

        st.markdown("**Edit technician**")
        tech_choices = []
        for team_name, rows in st.session_state.tech_teams.items():
            for i, row in enumerate(rows):
                tech_choices.append((team_name, i, row))
        if tech_choices:
            labels = [f"{row.name} ({team_name})" for team_name, _, row in tech_choices]
            pick = st.selectbox("Select technician", labels, key="roster_edit_pick")
            pick_idx = labels.index(pick)
            team_name, row_idx, row = tech_choices[pick_idx]
            e1, e2, e3, e4 = st.columns([1, 1, 1, 1])
            with e1:
                edit_number = st.text_input(
                    "Tech #",
                    value=row.tech_number,
                    key="roster_edit_number",
                )
            with e2:
                edit_rate = st.number_input(
                    "Hourly rate",
                    min_value=0.0,
                    step=0.25,
                    value=float(row.hourly_rate),
                    key="roster_edit_rate",
                )
            with e3:
                role_keys = list(ROLE_OPTIONS.keys())
                default_role = role_option_key(row)
                edit_role = st.selectbox(
                    "Role",
                    role_keys,
                    index=role_keys.index(default_role),
                    key="roster_edit_role",
                )
            with e4:
                st.write("")
                st.write("")
                if st.button("Save changes", key="roster_edit_save", use_container_width=True):
                    _apply_roster_change(
                        lambda teams, tn=team_name, idx=row_idx, num=edit_number, rt=edit_rate, rl=edit_role: update_technician(
                            teams, tn, idx, rt, num, rl
                        )
                    )

        st.markdown("---")
        st.markdown("**Reset roster**")
        st.caption("Restore the original default team list from your spreadsheet setup.")
        if st.checkbox("I want to reset the roster to defaults", key="roster_reset_confirm"):
            if st.button("Reset to default roster", type="secondary"):
                teams = reset_roster()
                save_roster(teams)
                apply_teams_to_session(teams)
                st.success("Roster reset to defaults.")
                st.rerun()


def _bonus_label(row, team_hrs, global_hours):
    if row.foreman_rule in ("team_per_hr_2", "team_per_hr_1"):
        return _money(row.foreman_bonus(team_hrs, global_hours))
    if row.quick_lube_sources:
        return _money(row.quick_lube_bonus(global_hours))
    return "—"


def _team_summary_rows(team_name: str, rows: list, global_hours: dict) -> list:
    count = len(rows)
    summary_rows = []
    for i, row in enumerate(rows):
        sync_row(team_name, i, row)
        th = _team_hours(team_name, count)
        summary_rows.append({
            "Tech #": row.tech_number or "—",
            "Technician": row.name,
            "Hours": row.flat_rate_hours,
            "Dollars": row.dollars_earned,
            "Prod Bonus": row.production_bonus,
            "Foreman / Quick Lube": _bonus_label(row, th, global_hours),
            "Training Pay": row.training_pay,
            "SPIFF": row.spiff,
            "Total Pay": row.total_pay(th, global_hours),
        })
    return summary_rows


def _render_team(team_name: str, rows: list, global_hours: dict):
    count = len(rows)
    for i, row in enumerate(rows):
        sync_row(team_name, i, row)

    team_hrs = _team_hours(team_name, count)

    st.markdown(
        f'<div class="section-title"><h2>{team_name}</h2>'
        f'<p class="section-sub">Team hours: <strong>{team_hrs:.2f}</strong></p></div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.pdf_loaded:
        st.info("Upload the flag sheet PDF above to auto-fill hours and dollars.")
        return

    st.markdown("##### ✏️ Enter training hours, SPIFF & notes")
    m1, m2, m3, m4 = st.columns([0.7, 2, 1, 1])
    with m1:
        st.caption("Tech #")
    with m2:
        st.caption("Technician")
    with m3:
        st.caption("Training hrs")
    with m4:
        st.caption("SPIFF $")

    for i, row in enumerate(rows):
        with st.container():
            c1, c2, c3, c4 = st.columns([0.7, 2, 1, 1])
            with c1:
                st.caption(row.tech_number or "—")
            with c2:
                st.write(f"**{row.name}**")
            with c3:
                st.number_input(
                    "Training hrs",
                    min_value=0.0,
                    step=0.1,
                    key=field_key(team_name, i, "train"),
                    label_visibility="collapsed",
                )
            with c4:
                st.number_input(
                    "SPIFF",
                    min_value=0.0,
                    step=1.0,
                    key=field_key(team_name, i, "spiff"),
                    label_visibility="collapsed",
                )
            st.text_area(
                "Notes for payroll clerk",
                key=field_key(team_name, i, "notes"),
                placeholder="Optional — prints on the payroll PDF for accounting",
                height=68,
            )

    summary_rows = _team_summary_rows(team_name, rows, global_hours)
    totals = team_totals(rows, global_hours)

    st.markdown("##### Payroll summary")
    st.dataframe(
        pd.DataFrame(summary_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Hours": st.column_config.NumberColumn(format="%.2f"),
            "Dollars": st.column_config.NumberColumn(format="$%.2f"),
            "Prod Bonus": st.column_config.NumberColumn(format="$%.2f"),
            "Training Pay": st.column_config.NumberColumn(format="$%.2f"),
            "SPIFF": st.column_config.NumberColumn(format="$%.2f"),
            "Total Pay": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    st.markdown(
        f"""
        <div class="team-total-bar">
            <span>TEAM TOTAL</span>
            <span class="team-total-val">{_team_hours(team_name, count):.2f} hrs · {_money(totals["total_pay"])}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render():
    st.markdown(
        '<span class="legend-chip chip-manual">You enter: training hrs, SPIFF & notes</span> '
        '<span class="legend-chip chip-calc">Hours & dollars from flag sheet PDF + auto-calc</span>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("active_run_id"):
        label = "Reopened" if st.session_state.get("payroll_completed") else "Editing"
        st.markdown(
            status_banner(
                f"{label} payroll · {st.session_state.pay_period or '—'} · "
                "Make corrections, export PDF, then check Complete & Save again.",
                "warn" if label == "Reopened" else "success",
            ),
            unsafe_allow_html=True,
        )

    _render_roster_manager()

    st.markdown("---")

    pdf_file = st.file_uploader(
        "Upload TECH FLAG SHEETS.pdf",
        type=["pdf"],
        help="One upload fills hours and dollars. The PDF is saved on the Flag Sheet tab for reference.",
    )

    if pdf_file:
        try:
            pdf_file.seek(0)
            pdf_bytes = pdf_file.read()
            pdf_sig = f"{pdf_file.name}:{len(pdf_bytes)}"
            if st.session_state.get("flag_pdf_processed_sig") != pdf_sig:
                store_flag_pdf(pdf_file, pdf_bytes)
                pdf_file.seek(0)
                parsed = parse_flag_sheet(pdf_file)
                flag_map = {t.display_name: (t.flat_rate_hours, t.dollars_earned) for t in parsed.technicians}
                number_map = {t.display_name: t.tech_number for t in parsed.technicians if t.tech_number}

                _apply_pdf_to_state(flag_map)
                numbers_updated = 0
                for team_rows in st.session_state.tech_teams.values():
                    apply_flag_data(team_rows, flag_map)
                    numbers_updated += apply_tech_numbers(team_rows, number_map)
                if numbers_updated:
                    save_roster(st.session_state.tech_teams)
                st.session_state.pdf_loaded = True
                st.session_state.flag_pdf_processed_sig = pdf_sig

                dates_updated = False
                if parsed.pay_period_start and parsed.pay_period_end:
                    pdf_start = parse_period_token(parsed.pay_period_start)
                    pdf_end = parse_period_token(parsed.pay_period_end)
                    if pdf_start and pdf_end:
                        st.session_state.pending_pay_period_start = pdf_start
                        st.session_state.pending_pay_period_end = pdf_end
                        dates_updated = True

                matched = sum(1 for team in st.session_state.tech_teams.values() for r in team if r.name in flag_map)
                number_note = f" · {numbers_updated} tech numbers synced" if numbers_updated else ""

                period_note = ""
                if dates_updated:
                    period_note = " · Pay dates updated from PDF"
                elif st.session_state.pay_period:
                    period_note = f" · {st.session_state.pay_period}"

                st.markdown(
                    status_banner(
                        f"✓ {matched} techs loaded{number_note} · Flag sheet saved — view anytime on **Flag Sheet** tab"
                        + period_note,
                        "success",
                    ),
                    unsafe_allow_html=True,
                )
                if dates_updated:
                    st.rerun()
        except Exception as exc:
            st.markdown(status_banner(f"PDF parse failed: {exc}", "warn"), unsafe_allow_html=True)

    if st.session_state.pdf_loaded:
        period_slug = (st.session_state.pay_period or "payroll").replace("/", "-")
        export_name = f"TECH_PAYROLL_{period_slug}.pdf"

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                label="📄 Export payroll PDF for accounting",
                data=generate_payroll_pdf(
                    build_payroll_snapshot(all_rows_synced(), st.session_state.pay_period)
                ),
                file_name=export_name,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        with col_b:
            st.caption("Need to verify hours? Open **Flag Sheet** in the sidebar.")

    st.markdown("---")

    synced = all_rows_synced()
    global_hours = all_hours_by_name(synced)

    for team_name, team_rows in synced.items():
        _render_team(team_name, team_rows, global_hours)
        st.markdown("---")

    synced = all_rows_synced()
    global_hours = all_hours_by_name(synced)
    grand_total = 0.0
    grand_hours = 0.0
    for team_rows in synced.values():
        t = team_totals(team_rows, global_hours)
        grand_total += t["total_pay"]
        grand_hours += t["hours"]

    if st.session_state.pdf_loaded:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(stat_card("Grand Total Hours", f"{grand_hours:.2f}", "orange", "⏱"), unsafe_allow_html=True)
        with c2:
            st.markdown(stat_card("Grand Total Pay", _money(grand_total), "green", "💰"), unsafe_allow_html=True)
        with c3:
            st.markdown(
                stat_card("Technicians", str(sum(len(t) for t in synced.values())), "violet", "👥"),
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("##### ✅ Complete payroll")
        st.markdown(
            '<div class="glass-panel"><p style="color:#94a3b8;margin:0;">'
            "Saves this pay period to <strong>Reports → Technician Payroll</strong>. "
            "Reopen anytime from Reports to fix and resubmit.</p></div>",
            unsafe_allow_html=True,
        )

        if saved_period := st.session_state.pop("_payroll_saved_period", None):
            st.success(f"Payroll saved — find it in Reports under {saved_period}")
            st.balloons()

        confirm = st.checkbox(
            "This payroll is complete and ready to save",
            key="payroll_complete_confirm",
        )

        if st.button(
            "Complete & Save to Reports",
            type="primary",
            disabled=not confirm,
            use_container_width=True,
        ):
            run_id = save_payroll_run(
                all_rows_synced(),
                st.session_state.pay_period,
                st.session_state.get("flag_pdf_bytes"),
                st.session_state.get("flag_pdf_filename", "flag_sheet.pdf"),
                run_id=st.session_state.get("active_run_id"),
            )
            st.session_state.active_run_id = run_id
            st.session_state.payroll_completed = True
            st.session_state["_payroll_saved_period"] = st.session_state.pay_period
            del st.session_state["payroll_complete_confirm"]
            st.rerun()

    with st.expander("How it works", expanded=False):
        st.markdown(
            """
            **From PDF (automatic):** Flat rate hours, dollars earned per tech.

            **Calculated (automatic):**
            - Production bonus — hours × tier $/hr when 80+ hrs
            - Foreman bonus — Derrick: team hrs × $2, Olan: team hrs × $1
            - Noah quick lube — selected tech hrs × $1
            - Training pay — training hrs × hourly rate

            **You enter:** Pay period dates, training hours, SPIFF, and optional notes for accounting.

            **Export:** Download the payroll PDF and submit to accounting.
            **Flag Sheet tab:** View the original uploaded PDF anytime.
            """
        )
        tier_df = pd.DataFrame(
            [{"Hours": f"{h}+", "Bonus": f"${m}/hr retro"} for h, m, _ in PROD_BONUS_TIERS]
        )
        st.dataframe(tier_df, hide_index=True)
