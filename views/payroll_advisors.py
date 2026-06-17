import streamlit as st
import pandas as pd

from components.ui import stat_card, status_banner
from lib.advisor_payroll_calc import (
    ALIGNMENT_BONUS_AMOUNT,
    CP_BUMP_RATES,
    CP_HOURS_BUMP_THRESHOLD,
    CSI_TIER_OPTIONS,
    NEW_HIRE_WEEKLY_GUARANTEE,
    PLAN_LABELS,
    PLAN_NEW_ADVISORS,
    PLAN_NEW_HIRES,
    PLAN_SEASONED,
    TOM_JOEY_CP_BUMP_RATE,
    calculate_advisor_payroll,
)
from lib.advisor_payroll_export_data import build_advisor_payroll_snapshot
from lib.advisor_payroll_parser import parse_advisor_payroll_report
from lib.advisor_payroll_pdf_export import generate_advisor_payroll_pdf
from lib.advisor_payroll_storage import save_advisor_payroll_run
from lib.advisor_roster import (
    PLAN_ORDER,
    add_advisor,
    change_advisor_plan,
    clone_roster,
    flatten_roster,
    remove_advisor,
    reset_roster,
    save_roster,
    update_advisor,
)
from views.advisor_payroll_helpers import (
    CSI_TIER_KEYS,
    adv_key,
    all_advisors_synced,
    apply_advisor_report_to_session,
    apply_advisor_value_store,
    apply_roster_to_session,
    capture_advisor_values,
    init_advisor_payroll_session,
    persist_advisor_changes,
    refresh_advisor_value_store,
    toggle_advisor_section,
)
from views.payroll_helpers import pay_period_weeks


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _plan_label(plan_type: str) -> str:
    return PLAN_LABELS.get(plan_type, plan_type)


def _apply_roster_change(mutator):
    rows = flatten_roster(st.session_state.advisor_roster)
    values = capture_advisor_values(rows)
    roster = clone_roster(st.session_state.advisor_roster)
    ok, message = mutator(roster)
    if not ok:
        st.warning(message)
        return
    save_roster(roster)
    apply_roster_to_session(roster, values)
    st.success(message)
    st.rerun()


def _render_advisor_roster_manager():
    with st.expander("👥 Manage advisor roster", expanded=False):
        st.caption(
            "Add advisors, remove terminations, or move them between pay plans. "
            "Changes save automatically."
        )

        for plan_type in PLAN_ORDER:
            rows = st.session_state.advisor_roster.get(plan_type, [])
            st.markdown(f"**{PLAN_LABELS[plan_type]}** · {len(rows)} advisors")
            if plan_type == PLAN_NEW_HIRES:
                st.caption(
                    f"${NEW_HIRE_WEEKLY_GUARANTEE:,.0f}/week guarantee or commission pay — whichever is higher."
                )
            elif plan_type == PLAN_SEASONED:
                st.caption("200-hr objective · up to $13/hr with CP bump.")
            else:
                st.caption("130-hr objective · tiered labor rates with optional CP bump.")

            if not rows:
                st.caption("No advisors on this plan.")
            else:
                h1, h2, h3, h4, h5 = st.columns([0.8, 2, 1.2, 1.2, 0.9])
                with h1:
                    st.caption("ID")
                with h2:
                    st.caption("Advisor")
                with h3:
                    st.caption("Plan detail")
                with h4:
                    st.caption("Change plan")
                with h5:
                    st.caption("")

            for i, row in enumerate(rows):
                c1, c2, c3, c4, c5 = st.columns([0.8, 2, 1.2, 1.2, 0.9])
                with c1:
                    st.caption(row.advisor_id or "—")
                with c2:
                    st.write(row.name)
                with c3:
                    if plan_type == PLAN_NEW_ADVISORS and row.top_labor_rate > 9.5:
                        st.caption(f"Top tier ${row.top_labor_rate:.0f}/hr")
                    else:
                        st.caption("—")
                with c4:
                    other_plans = [p for p in PLAN_ORDER if p != plan_type]
                    with st.popover("Move", use_container_width=True):
                        st.caption(f"Move **{row.name}** to:")
                        dest = st.radio(
                            "Pay plan",
                            other_plans,
                            format_func=lambda p: PLAN_LABELS[p],
                            key=f"adv_move_dest_{plan_type}_{i}",
                            label_visibility="collapsed",
                        )
                        if st.button("Confirm", key=f"adv_move_{plan_type}_{i}", use_container_width=True):
                            _apply_roster_change(
                                lambda r, fp=plan_type, idx=i, dp=dest: change_advisor_plan(r, fp, idx, dp)
                            )
                with c5:
                    if st.button("Remove", key=f"adv_remove_{plan_type}_{i}", use_container_width=True):
                        _apply_roster_change(
                            lambda r, fp=plan_type, idx=i: remove_advisor(r, fp, idx)
                        )

            with st.form(f"add_advisor_{plan_type}", clear_on_submit=True):
                st.markdown(f"**Add to {PLAN_LABELS[plan_type]}**")
                a1, a2 = st.columns([1, 2])
                with a1:
                    new_id = st.text_input("Advisor ID", key=f"new_adv_id_{plan_type}")
                with a2:
                    new_name = st.text_input("Name", key=f"new_adv_name_{plan_type}")
                if st.form_submit_button("Add advisor", use_container_width=True):
                    _apply_roster_change(
                        lambda r, pt=plan_type, nm=new_name, aid=new_id: add_advisor(r, pt, nm, aid)
                    )

            st.markdown("---")

        choices = []
        for plan_type, rows in st.session_state.advisor_roster.items():
            for i, row in enumerate(rows):
                choices.append((plan_type, i, row))
        if choices:
            st.markdown("**Edit advisor**")
            labels = [f"{row.name} ({PLAN_LABELS[plan_type]})" for plan_type, _, row in choices]
            pick = st.selectbox("Select advisor", labels, key="adv_roster_edit_pick")
            pick_idx = labels.index(pick)
            plan_type, row_idx, row = choices[pick_idx]
            e1, e2, e3 = st.columns([1, 1, 1])
            with e1:
                edit_id = st.text_input("Advisor ID", value=row.advisor_id, key="adv_roster_edit_id")
            with e2:
                top_rate = row.top_labor_rate
                if plan_type == PLAN_NEW_ADVISORS:
                    top_rate = st.number_input(
                        "Top labor rate ($/hr)",
                        min_value=9.5,
                        max_value=15.0,
                        step=0.5,
                        value=float(row.top_labor_rate),
                        key="adv_roster_edit_top_rate",
                    )
            with e3:
                st.write("")
                st.write("")
                if st.button("Save changes", key="adv_roster_edit_save", use_container_width=True):
                    _apply_roster_change(
                        lambda r, pt=plan_type, idx=row_idx, aid=edit_id, tr=top_rate: update_advisor(
                            r, pt, idx, aid, top_labor_rate=tr if pt == PLAN_NEW_ADVISORS else None
                        )
                    )

        st.markdown("**Reset roster**")
        if st.checkbox("I want to reset the advisor roster to defaults", key="adv_roster_reset_confirm"):
            if st.button("Reset to default roster", type="secondary"):
                roster = reset_roster()
                save_roster(roster)
                apply_roster_to_session(roster)
                st.success("Advisor roster reset to defaults.")
                st.rerun()


def _csi_label(tier_key: str) -> str:
    label, amount = CSI_TIER_OPTIONS.get(tier_key, CSI_TIER_OPTIONS["none"])
    if amount:
        return f"{label} · {_money(amount)}"
    return label


def _render_csi_buttons(advisor_idx: int):
    current = st.session_state.get(adv_key(advisor_idx, "csi_tier"), "none")
    if current not in CSI_TIER_KEYS:
        current = "none"

    st.caption("CSI bonus")
    button_order = ["top", "middle", "bottom", "none"]
    cols = st.columns(len(button_order))
    for col, tier_key in zip(cols, button_order):
        label, amount = CSI_TIER_OPTIONS[tier_key]
        with col:
            selected = current == tier_key
            if st.button(
                f"{label}\n{_money(amount)}",
                key=f"csi_pick_{advisor_idx}_{tier_key}",
                use_container_width=True,
                type="primary" if selected else "secondary",
            ):
                st.session_state[adv_key(advisor_idx, "csi_tier")] = tier_key
                persist_advisor_changes(advisor_idx)


def _summary_row(row, synced, result) -> dict:
    return {
        "Advisor": row.name,
        "Plan": _plan_label(row.plan_type),
        "Hours": synced.hours_sold,
        "Labor Pay": result.hourly_pay,
        "Parts": result.parts_pay,
        "CSI": result.csi_pay,
        "Alignment": result.variable_pay,
        "SPIFF": result.spiff_pay,
        "Total Pay": result.total_pay,
    }


def _render_advisor_section(advisor_idx: int, row) -> None:
    """Render one advisor's payroll inputs and pay breakdown."""
    st.number_input(
        "Hours sold",
        min_value=0.0,
        step=0.1,
        key=adv_key(advisor_idx, "hours_sold"),
        on_change=persist_advisor_changes,
        args=(advisor_idx,),
        help="Auto-filled from PAYROLL.xlsx, or enter manually.",
    )

    if row.plan_type == PLAN_SEASONED:
        st.toggle(
            f"Over {CP_HOURS_BUMP_THRESHOLD} CP hrs/RO — bump to ${TOM_JOEY_CP_BUMP_RATE:.0f}/hr",
            key=adv_key(advisor_idx, "cp_bump"),
            on_change=persist_advisor_changes,
            args=(advisor_idx,),
            help="Turn on when they averaged more than 2.25 customer-pay hours per RO.",
        )
    elif row.plan_type != PLAN_NEW_HIRES:
        st.toggle(
            f"Over {CP_HOURS_BUMP_THRESHOLD} CP hrs/RO — labor rate bump",
            key=adv_key(advisor_idx, "cp_bump"),
            on_change=persist_advisor_changes,
            args=(advisor_idx,),
            help=(
                "Turn on when they averaged more than 2.25 customer-pay hours per RO. "
                "Bumps their current hour tier rate (e.g. $6.50 → $7.50)."
            ),
        )
    else:
        st.toggle(
            f"Over {CP_HOURS_BUMP_THRESHOLD} CP hrs/RO — labor rate bump",
            key=adv_key(advisor_idx, "cp_bump"),
            on_change=persist_advisor_changes,
            args=(advisor_idx,),
            help="Commission pay mirrors New Advisors plan with optional CP bump.",
        )

    st.markdown("##### Bonuses you enter")
    c1, c2 = st.columns(2)
    with c1:
        st.toggle(
            f"Alignment bonus — {_money(ALIGNMENT_BONUS_AMOUNT)}",
            key=adv_key(advisor_idx, "alignment_bonus"),
            on_change=persist_advisor_changes,
            args=(advisor_idx,),
            help="Turn on when the advisor earned the alignment bonus this pay period.",
        )
    with c2:
        st.number_input(
            "SPIFF ($)",
            min_value=0.0,
            step=1.0,
            key=adv_key(advisor_idx, "spiff"),
            on_change=persist_advisor_changes,
            args=(advisor_idx,),
        )

    st.text_area(
        "Notes for payroll clerk",
        key=adv_key(advisor_idx, "notes"),
        on_change=persist_advisor_changes,
        args=(advisor_idx,),
        placeholder="Optional — prints on the payroll PDF for accounting",
        height=72,
    )

    _render_csi_buttons(advisor_idx)

    synced = all_advisors_synced()[advisor_idx]
    weeks = pay_period_weeks()
    result = calculate_advisor_payroll(synced, pay_period_weeks=weeks)

    st.metric(
        "Labor pay",
        _money(result.hourly_pay),
        delta=f"${result.hourly_rate:.2f}/hr · {result.hourly_tier_label}" if result.hourly_pay else "No tier",
    )

    if row.plan_type == PLAN_NEW_HIRES:
        st.caption(
            f"**New Hire guarantee:** ${synced.weekly_guarantee:,.0f}/wk × {weeks:.1f} wks = "
            f"**{_money(result.guarantee_amount)}** · Commission: **{_money(result.commission_total)}**"
        )
    elif row.plan_type == PLAN_SEASONED:
        if result.cp_bump_active:
            st.caption(
                f"**${TOM_JOEY_CP_BUMP_RATE:.0f}/hr CP bump active** — "
                f"{result.payable_hours:.1f} hrs × ${TOM_JOEY_CP_BUMP_RATE:.2f}/hr."
            )
        else:
            st.caption(
                f"Toggle on when CP hrs/RO exceeds **{CP_HOURS_BUMP_THRESHOLD}** to pay "
                f"**${TOM_JOEY_CP_BUMP_RATE:.0f}/hr** on all hours sold."
            )
    elif result.cp_bump_active:
        bumped = ", ".join(f"${base:.2f}→${bumped:.2f}" for base, bumped in CP_BUMP_RATES.items())
        st.caption(f"**CP bump active** on their current hour tier ({bumped}).")
    else:
        st.caption(
            f"Toggle on when CP hrs/RO exceeds **{CP_HOURS_BUMP_THRESHOLD}** to bump their tier rate."
        )

    st.caption(
        f"Parts sales **{_money(synced.parts_sales)}** · "
        f"Payable hours **{result.payable_hours:.1f}**"
    )

    pay_rows = [
        {
            "Pay": "Labor sales pay",
            "Amount": result.hourly_pay,
            "Detail": f"{result.payable_hours:.1f} hrs × ${result.hourly_rate:.2f}/hr ({result.hourly_tier_label})",
        },
        {
            "Pay": "Parts commission (3%)",
            "Amount": result.parts_pay,
            "Detail": f"{_money(synced.parts_sales)} parts sales",
        },
        {"Pay": "CSI bonus", "Amount": result.csi_pay, "Detail": _csi_label(synced.csi_tier)},
        {
            "Pay": "Alignment bonus",
            "Amount": result.variable_pay,
            "Detail": "Qualified" if result.alignment_qualified else "Toggle off",
        },
        {"Pay": "SPIFF", "Amount": result.spiff_pay, "Detail": ""},
    ]
    if row.plan_type == PLAN_NEW_HIRES:
        pay_rows.append(
            {
                "Pay": "Commission subtotal",
                "Amount": result.commission_total,
                "Detail": "New Advisors pay plan",
            }
        )
        if result.guarantee_active:
            pay_rows.append(
                {
                    "Pay": "Weekly guarantee top-up",
                    "Amount": result.guarantee_top_up,
                    "Detail": f"${synced.weekly_guarantee:,.0f}/wk × {weeks:.1f} wks",
                }
            )
        else:
            pay_rows.append(
                {
                    "Pay": "Weekly guarantee",
                    "Amount": result.guarantee_amount,
                    "Detail": "Commission exceeded guarantee",
                }
            )
    pay_rows.append({"Pay": "TOTAL", "Amount": result.total_pay, "Detail": ""})
    st.dataframe(
        pd.DataFrame(pay_rows),
        use_container_width=True,
        hide_index=True,
        column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
    )



def render():
    init_advisor_payroll_session()

    st.markdown(
        '<span class="legend-chip chip-manual">You enter: CP bump, alignment bonus, CSI tier, SPIFF</span> '
        '<span class="legend-chip chip-calc">Hours & parts sales from PAYROLL report · pay auto-calc</span> '
        '<span class="legend-chip chip-live">Changes save automatically</span>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("active_advisor_run_id"):
        label = "Reopened" if st.session_state.get("advisor_payroll_completed") else "Editing"
        st.markdown(
            status_banner(
                f"{label} advisor payroll · {st.session_state.pay_period or '—'} · "
                "Make corrections, export PDF, then check Complete & Save again.",
                "warn" if label == "Reopened" else "success",
            ),
            unsafe_allow_html=True,
        )

    report_file = st.file_uploader(
        "Upload PAYROLL report (.xlsx)",
        type=["xlsx"],
        help="Import from OFFICE SCANNER/PAYROLL.xlsx — fills hours sold and parts sales.",
    )

    if report_file:
        try:
            matched = apply_advisor_report_to_session(parse_advisor_payroll_report(report_file))
            st.markdown(
                status_banner(
                    f"✓ Loaded payroll report — matched {matched} advisors",
                    "success",
                ),
                unsafe_allow_html=True,
            )
        except Exception as exc:
            st.markdown(status_banner(f"Report import failed: {exc}", "warn"), unsafe_allow_html=True)

    if not st.session_state.advisor_report_loaded:
        st.info("Upload PAYROLL.xlsx to auto-fill hours sold and parts sales.")

    _render_advisor_roster_manager()

    st.markdown("---")

    advisor_rows = flatten_roster(st.session_state.advisor_roster)
    weeks = pay_period_weeks()
    apply_advisor_value_store()
    synced_advisors = all_advisors_synced()
    advisor_results = [
        calculate_advisor_payroll(a, pay_period_weeks=weeks) for a in synced_advisors
    ]

    summary_rows = [
        _summary_row(row, synced_advisors[i], advisor_results[i])
        for i, row in enumerate(advisor_rows)
    ]
    grand_total = sum(r["Total Pay"] for r in summary_rows)

    for i, row in enumerate(advisor_rows):
        result = advisor_results[i]
        open_key = adv_key(i, "expanded")
        exp_label = (
            f"**{row.name}** · {_plan_label(row.plan_type)} · **{_money(result.total_pay)}**"
        )
        col_toggle, col_label = st.columns([0.04, 0.96], vertical_alignment="center")
        with col_toggle:
            if st.button(
                "▼" if st.session_state.get(open_key, False) else "▶",
                key=adv_key(i, "toggle"),
                help="Expand or collapse",
            ):
                toggle_advisor_section(i)
        with col_label:
            st.markdown(exp_label, unsafe_allow_html=True)

        if st.session_state.get(open_key, False):
            _render_advisor_section(i, row)

    st.markdown("---")
    st.markdown("##### Advisor payroll summary")
    st.dataframe(
        pd.DataFrame(summary_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Hours": st.column_config.NumberColumn(format="%.1f"),
            "Labor Pay": st.column_config.NumberColumn(format="$%.2f"),
            "Parts": st.column_config.NumberColumn(format="$%.2f"),
            "CSI": st.column_config.NumberColumn(format="$%.2f"),
            "Alignment": st.column_config.NumberColumn(format="$%.2f"),
            "SPIFF": st.column_config.NumberColumn(format="$%.2f"),
            "Total Pay": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(stat_card("Advisors", str(len(advisor_rows)), "violet", "🧑‍💼"), unsafe_allow_html=True)
    with c2:
        st.markdown(stat_card("Total Advisor Pay", _money(grand_total), "green", "💰"), unsafe_allow_html=True)

    total_parts_labor_sales = sum(a.parts_labor_sales for a in synced_advisors)
    st.markdown("##### Advisor comp %")
    if total_parts_labor_sales > 0:
        comp_pct = grand_total / total_parts_labor_sales * 100
        st.markdown(
            stat_card("Comp %", f"{comp_pct:.2f}%", "cyan", "📊"),
            unsafe_allow_html=True,
        )
        st.caption(
            f"{_money(grand_total)} total advisor pay ÷ "
            f"{_money(total_parts_labor_sales)} parts & labor sales"
        )
    else:
        st.info("Upload PAYROLL.xlsx to load parts & labor sales before comp % can be calculated.")

    if advisor_rows and st.session_state.get("pay_period"):
        snapshot = build_advisor_payroll_snapshot(
            synced_advisors,
            advisor_results,
            st.session_state.pay_period,
            weeks,
        )
        export_pdf = generate_advisor_payroll_pdf(snapshot)
        period_slug = (st.session_state.pay_period or "payroll").replace("/", "-")
        st.download_button(
            label="📄 Export advisor payroll PDF for accounting",
            data=export_pdf,
            file_name=f"ADVISOR_PAYROLL_{period_slug}.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )

        st.markdown("---")
        st.markdown("##### ✅ Complete advisor payroll")
        st.markdown(
            '<div class="glass-panel"><p style="color:#94a3b8;margin:0;">'
            "Saves this pay period to <strong>Reports → Service Advisor Payroll</strong>. "
            "Reopen anytime from Reports to fix and resubmit.</p></div>",
            unsafe_allow_html=True,
        )

        if saved_period := st.session_state.pop("_advisor_payroll_saved_period", None):
            st.success(f"Advisor payroll saved — find it in Reports under {saved_period}")
            st.balloons()

        confirm = st.checkbox(
            "This advisor payroll is complete and ready to save",
            key="advisor_payroll_complete_confirm",
        )

        if st.button(
            "Complete & Save to Reports",
            type="primary",
            disabled=not confirm,
            use_container_width=True,
        ):
            save_roster(st.session_state.advisor_roster)
            run_id = save_advisor_payroll_run(
                all_advisors_synced(),
                st.session_state.pay_period,
                weeks,
                run_id=st.session_state.get("active_advisor_run_id"),
                status="completed",
            )
            st.session_state.active_advisor_run_id = run_id
            st.session_state.advisor_payroll_completed = True
            st.session_state["_advisor_payroll_saved_period"] = st.session_state.pay_period
            del st.session_state["advisor_payroll_complete_confirm"]
            st.rerun()

    refresh_advisor_value_store()
