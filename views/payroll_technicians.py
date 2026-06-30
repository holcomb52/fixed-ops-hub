import streamlit as st
import pandas as pd

from components.ui import stat_card, status_banner, team_section_divider, team_section_header
from lib.flag_pdf_parser import parse_flag_sheet
from lib.payroll_export_data import build_payroll_snapshot
from lib.payroll_pdf_export import generate_payroll_pdf
from lib.tech_payroll_calc import (
    PROD_BONUS_TIERS,
    all_hours_by_name,
    apply_flag_data,
    apply_supplemental_metrics,
    apply_tech_numbers,
    supplemental_bonus_eligible,
    team_totals,
)
from lib.tech_supplemental_bonus import SUPPLEMENTAL_BONUS_MATRIX, supplemental_bonus_label
from lib.tech_upsell_parser import parse_upsell_report
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
    pay_period_weeks,
    persist_technician_changes,
    refresh_tech_supplemental_bonuses,
    set_pay_period_dates,
    store_flag_pdf,
    sync_row,
    render_payroll_sync_error,
    render_roster_sync_error,
)


def _team_hours(team_name: str, count: int) -> float:
    return sum(float(st.session_state[field_key(team_name, i, "hours")]) for i in range(count))


def _money(v: float) -> str:
    return f"${v:,.2f}"


TEAM_SECTION_STYLE = {
    "Derrick's Team": {
        "accent": "orange",
        "icon": "🔥",
        "badge": "Foreman $2/hr",
        "subtitle": "Derrick Opp · team production bonus at $2 per team hour",
    },
    "Olan's Team": {
        "accent": "violet",
        "icon": "⚡",
        "badge": "Foreman $1/hr",
        "subtitle": "Olan Halcomb · team production bonus at $1 per team hour",
    },
}


def _team_style(team_name: str) -> dict:
    return TEAM_SECTION_STYLE.get(
        team_name,
        {
            "accent": "cyan",
            "icon": "🔧",
            "badge": "",
            "subtitle": "Technician team",
        },
    )


def _render_team_header(team_name: str, rows: list, team_hrs: float) -> None:
    style = _team_style(team_name)
    st.markdown(
        team_section_header(
            title=team_name,
            subtitle=f"{style['subtitle']} · <strong>{team_hrs:.2f}</strong> team hrs",
            count=len(rows),
            accent=style["accent"],
            icon=style["icon"],
            badge=style["badge"],
        ),
        unsafe_allow_html=True,
    )


def _roster_names() -> list[str]:
    return [row.name for rows in st.session_state.tech_teams.values() for row in rows]


def _store_cp_metrics_from_flag(parsed) -> int:
    cp_by_name = {}
    for tech in parsed.technicians:
        cp_by_name[tech.display_name] = {
            "cp_hours": tech.cp_hours,
            "cp_ro_count": tech.cp_ro_count,
            "cp_hrs_per_ro": tech.cp_hrs_per_ro,
        }
    st.session_state.tech_cp_metrics_by_name = cp_by_name
    apply_supplemental_metrics(
        st.session_state.tech_teams,
        cp_by_name=cp_by_name,
        closing_by_name=st.session_state.get("tech_closing_by_name", {}),
    )
    return len(cp_by_name)


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
        render_roster_sync_error("_tech_roster_sync_error")
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
            edit_scope = f"{team_name}_{row_idx}"
            e1, e2, e3, e4 = st.columns([1, 1, 1, 1])
            with e1:
                edit_number = st.text_input(
                    "Tech #",
                    value=row.tech_number,
                    key=f"roster_edit_number_{edit_scope}",
                )
            with e2:
                edit_rate = st.number_input(
                    "Hourly rate",
                    min_value=0.0,
                    step=0.25,
                    value=float(row.hourly_rate),
                    key=f"roster_edit_rate_{edit_scope}",
                )
            with e3:
                role_keys = list(ROLE_OPTIONS.keys())
                default_role = role_option_key(row)
                edit_role = st.selectbox(
                    "Role",
                    role_keys,
                    index=role_keys.index(default_role),
                    key=f"roster_edit_role_{edit_scope}",
                )
            with e4:
                st.write("")
                st.write("")
                if st.button("Save changes", key=f"roster_edit_save_{edit_scope}", use_container_width=True):
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


def _team_summary_rows(team_name: str, rows: list, global_hours: dict, weeks: float) -> list:
    count = len(rows)
    summary_rows = []
    for i, row in enumerate(rows):
        sync_row(team_name, i, row)
        th = _team_hours(team_name, count)
        summary_rows.append({
            "Tech #": row.tech_number or "—",
            "Technician": row.name,
            "Hours": row.flat_rate_hours,
            "Dollars": row.flag_base_pay(weeks),
            "Guar Top-up": row.guarantee_top_up(weeks) or None,
            "Prod Bonus": row.production_bonus,
            "CP hrs/RO": row.cp_hrs_per_ro if row.cp_hrs_per_ro else None,
            "Close %": row.closing_pct if row.closing_pct else None,
            "Suppl Bonus": row.supplemental_bonus,
            "Foreman / Quick Lube": _bonus_label(row, th, global_hours),
            "Training Pay": row.training_pay,
            "SPIFF": row.spiff,
            "Total Pay": row.total_pay(th, global_hours, weeks),
        })
    return summary_rows


def _render_team(team_name: str, rows: list, global_hours: dict, weeks: float):
    count = len(rows)
    for i, row in enumerate(rows):
        sync_row(team_name, i, row)

    team_hrs = _team_hours(team_name, count)

    _render_team_header(team_name, rows, team_hrs)

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
                if supplemental_bonus_eligible(row) and (row.cp_hrs_per_ro or row.closing_pct):
                    st.caption(
                        supplemental_bonus_label(
                            row.cp_hrs_per_ro,
                            row.closing_pct,
                            row.supplemental_bonus,
                            row.supplemental_tier,
                        )
                    )
                elif not supplemental_bonus_eligible(row):
                    st.caption("Supplemental bonus — Shop Techs only.")
                elif st.session_state.get("upsell_loaded") or st.session_state.get("tech_cp_metrics_by_name"):
                    st.caption("Upload flag sheet + upsell report to calculate supplemental bonus.")
                if row.pay_plan == "weekly_hour_guarantee" and row.weekly_hour_guarantee > 0:
                    st.caption(row.guarantee_label(weeks))
            with c3:
                st.number_input(
                    "Training hrs",
                    min_value=0.0,
                    step=0.1,
                    key=field_key(team_name, i, "train"),
                    on_change=persist_technician_changes,
                    args=(team_name, i),
                    label_visibility="collapsed",
                )
            with c4:
                st.number_input(
                    "SPIFF",
                    min_value=0.0,
                    step=1.0,
                    key=field_key(team_name, i, "spiff"),
                    on_change=persist_technician_changes,
                    args=(team_name, i),
                    label_visibility="collapsed",
                )
            st.text_area(
                "Notes for payroll clerk",
                key=field_key(team_name, i, "notes"),
                on_change=persist_technician_changes,
                args=(team_name, i),
                placeholder="Optional — prints on the payroll PDF for accounting",
                height=68,
            )

    summary_rows = _team_summary_rows(team_name, rows, global_hours, weeks)
    totals = team_totals(rows, global_hours, weeks)

    st.markdown("##### Payroll summary")
    st.dataframe(
        pd.DataFrame(summary_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Hours": st.column_config.NumberColumn(format="%.2f"),
            "Dollars": st.column_config.NumberColumn(format="$%.2f"),
            "Guar Top-up": st.column_config.NumberColumn(format="$%.2f"),
            "Prod Bonus": st.column_config.NumberColumn(format="$%.2f"),
            "CP hrs/RO": st.column_config.NumberColumn(format="%.2f"),
            "Close %": st.column_config.NumberColumn(format="%.1f"),
            "Suppl Bonus": st.column_config.NumberColumn(format="$%.2f"),
            "Training Pay": st.column_config.NumberColumn(format="$%.2f"),
            "SPIFF": st.column_config.NumberColumn(format="$%.2f"),
            "Total Pay": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    style = _team_style(team_name)
    st.markdown(
        f"""
        <div class="team-total-bar accent-{style['accent']}">
            <span>TEAM TOTAL</span>
            <span class="team-total-val">{_team_hours(team_name, count):.2f} hrs · {_money(totals["total_pay"])}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render():
    st.markdown(
        '<span class="legend-chip chip-manual">You enter: training hrs, SPIFF & notes</span> '
        '<span class="legend-chip chip-calc">Flag sheet + upsell report auto-calc supplemental bonus</span> '
        '<span class="legend-chip chip-live">Changes save automatically</span>',
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

    render_payroll_sync_error("_technician_payroll_sync_error", table="tech_payroll_runs")

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
                cp_count = _store_cp_metrics_from_flag(parsed)
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
                        f"✓ {matched} techs loaded{number_note} · {cp_count} CP metrics · "
                        "Flag sheet saved — view anytime on **Flag Sheet** tab"
                        + period_note,
                        "success",
                    ),
                    unsafe_allow_html=True,
                )
                if dates_updated:
                    st.rerun()
                else:
                    from lib.payroll_autosave import autosave_technician_payroll

                    autosave_technician_payroll()
        except Exception as exc:
            st.markdown(status_banner(f"PDF parse failed: {exc}", "warn"), unsafe_allow_html=True)

    upsell_file = st.file_uploader(
        "Upload Ignite upsell analysis (.xlsx)",
        type=["xlsx", "xls"],
        help="Closing % per tech — combined with CP hrs/RO from the flag sheet to calculate supplemental bonus.",
    )

    if upsell_file:
        try:
            upsell_file.seek(0)
            upsell_bytes = upsell_file.read()
            upsell_sig = f"{upsell_file.name}:{len(upsell_bytes)}"
            if st.session_state.get("upsell_processed_sig") != upsell_sig:
                parsed_upsell = parse_upsell_report(upsell_bytes, _roster_names())
                closing_by_name = {
                    metrics.display_name: metrics.closing_pct
                    for metrics in parsed_upsell.values()
                    if not str(metrics.display_name).startswith("#")
                }
                st.session_state.tech_closing_by_name = closing_by_name
                st.session_state.upsell_loaded = True
                st.session_state.upsell_processed_sig = upsell_sig
                apply_supplemental_metrics(
                    st.session_state.tech_teams,
                    cp_by_name=st.session_state.get("tech_cp_metrics_by_name", {}),
                    closing_by_name=closing_by_name,
                )
                matched = sum(
                    1 for rows in st.session_state.tech_teams.values()
                    for row in rows if row.name in closing_by_name
                )
                st.markdown(
                    status_banner(
                        f"✓ {matched} techs matched on closing % · supplemental bonus updated",
                        "success",
                    ),
                    unsafe_allow_html=True,
                )
                from lib.payroll_autosave import autosave_technician_payroll

                autosave_technician_payroll()
        except Exception as exc:
            st.markdown(status_banner(f"Upsell report parse failed: {exc}", "warn"), unsafe_allow_html=True)

    refresh_tech_supplemental_bonuses()

    weeks = pay_period_weeks()
    if st.session_state.pdf_loaded:
        period_slug = (st.session_state.pay_period or "payroll").replace("/", "-")
        export_name = f"TECH_PAYROLL_{period_slug}.pdf"

        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                label="📄 Export payroll PDF for accounting",
                data=generate_payroll_pdf(
                    build_payroll_snapshot(
                        all_rows_synced(),
                        st.session_state.pay_period,
                        weeks,
                    )
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
        _render_team(team_name, team_rows, global_hours, weeks)
        st.markdown(team_section_divider(_team_style(team_name)["accent"]), unsafe_allow_html=True)

    synced = all_rows_synced()
    global_hours = all_hours_by_name(synced)
    grand_total = 0.0
    grand_hours = 0.0
    for team_rows in synced.values():
        t = team_totals(team_rows, global_hours, weeks)
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
            if st.session_state.get("_technician_payroll_sync_error"):
                st.error(
                    f"Technician payroll for {saved_period} was saved on this session only — "
                    "cloud backup failed. Open Reports after fixing the connection, or save again."
                )
            else:
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
            run_id, sync_error = save_payroll_run(
                all_rows_synced(),
                st.session_state.pay_period,
                st.session_state.get("flag_pdf_bytes"),
                st.session_state.get("flag_pdf_filename", "flag_sheet.pdf"),
                run_id=st.session_state.get("active_run_id"),
                status="completed",
            )
            st.session_state.active_run_id = run_id
            st.session_state.payroll_completed = True
            if sync_error:
                st.session_state["_technician_payroll_sync_error"] = sync_error
            else:
                st.session_state.pop("_technician_payroll_sync_error", None)
            st.session_state["_payroll_saved_period"] = st.session_state.pay_period
            del st.session_state["payroll_complete_confirm"]
            st.rerun()

    with st.expander("How it works", expanded=False):
        st.markdown(
            """
            **From PDF (automatic):** Flat rate hours, dollars earned per tech.

            **Calculated (automatic):**
            - Production bonus — hours × tier $/hr when 80+ hrs
            - **Supplemental bonus** — Shop Techs only: CP hrs/RO (flag sheet) × closing % (upsell report). Both must qualify.
            - Foreman bonus — Derrick: team hrs × $2, Olan: team hrs × $1
            - Noah quick lube — selected tech hrs × $1
            - Training pay — training hrs × hourly rate
            - **Hour guarantee** — Shop Techs on a 40 hr/wk plan are paid on the higher of flag hours or guaranteed hours × effective flag rate

            **You upload:** Flag sheet PDF + Ignite upsell analysis Excel.

            **You enter:** Pay period dates, training hours, SPIFF, and optional notes for accounting.

            **Export:** Download the payroll PDF and submit to accounting.
            **Flag Sheet tab:** View the original uploaded PDF anytime.
            """
        )
        tier_df = pd.DataFrame(
            [{"Hours": f"{h}+", "Bonus": f"${m}/hr retro"} for h, m, _ in PROD_BONUS_TIERS]
        )
        st.dataframe(tier_df, hide_index=True)
        st.markdown("**Supplemental bonus matrix (bi-weekly)**")
        suppl_rows = []
        for (hr_min, hr_max), (close_min, close_max), amount, tier in SUPPLEMENTAL_BONUS_MATRIX:
            hr_label = f"{hr_min:.2f}+" if hr_max >= 100 else f"{hr_min:.2f}–{hr_max:.2f}"
            suppl_rows.append({
                "CP hrs/RO": hr_label,
                "Closing %": f"{close_min:.0f}–{close_max:.0f}%",
                "Bonus": f"${amount:.0f}",
                "Tier": tier,
            })
        st.dataframe(pd.DataFrame(suppl_rows), hide_index=True)
