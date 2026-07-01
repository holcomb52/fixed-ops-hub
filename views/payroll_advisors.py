import streamlit as st
import pandas as pd
from datetime import date

from components.ui import (
    ACCENT_COLORS,
    advisor_accent_for_index,
    advisor_pay_card_header,
    advisor_pay_detail_panel,
    pay_plan_section_header,
    stat_card,
    status_banner,
    team_section_divider,
)
from lib.advisor_payroll_calc import (
    ADVISOR_WEEKLY_GUARANTEE,
    ALIGNMENT_BONUS_AMOUNT,
    CP_BUMP_RATES,
    CP_HOURS_BUMP_THRESHOLD,
    CSI_TIER_OPTIONS,
    PLAN_LABELS,
    PLAN_NEW_ADVISORS,
    PLAN_NEW_ADVISORS_GUARANTEE,
    PLAN_SEASONED,
    TOM_JOEY_CP_BUMP_RATE,
    calculate_advisor_payroll,
    parse_guarantee_expires,
    plan_has_weekly_guarantee,
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
    advisor_section_open_key,
    advisor_section_toggle_key,
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
from views.payroll_helpers import pay_period_weeks, render_payroll_sync_error, render_roster_sync_error


def _pay_period_start():
    return st.session_state.get("payroll_period_start")


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _plan_label(plan_type: str) -> str:
    return PLAN_LABELS.get(plan_type, plan_type)


PLAN_SECTION_STYLE = {
    PLAN_SEASONED: {
        "accent": "orange",
        "icon": "⭐",
        "badge": "Seasoned",
        "subtitle": "200-hr objective · up to $13/hr with CP bump.",
    },
    PLAN_NEW_ADVISORS: {
        "accent": "cyan",
        "icon": "📈",
        "badge": "Commission",
        "subtitle": "130-hr objective · tiered labor rates with optional CP bump.",
    },
    PLAN_NEW_ADVISORS_GUARANTEE: {
        "accent": "green",
        "icon": "🛡️",
        "badge": "Guarantee",
        "subtitle": (
            f"New Advisors commission or ${ADVISOR_WEEKLY_GUARANTEE:,.0f}/week guarantee — "
            "whichever is higher."
        ),
    },
}


def _render_plan_section_header(plan_type: str, count: int) -> None:
    style = PLAN_SECTION_STYLE[plan_type]
    st.markdown(
        pay_plan_section_header(
            title=PLAN_LABELS[plan_type],
            subtitle=style["subtitle"],
            count=count,
            accent=style["accent"],
            icon=style["icon"],
            badge=style["badge"],
        ),
        unsafe_allow_html=True,
    )


def _render_plan_section_footer(plan_type: str, total_pay: float, count: int) -> None:
    style = PLAN_SECTION_STYLE[plan_type]
    advisor_label = "advisor" if count == 1 else "advisors"
    st.markdown(
        f"""
        <div class="team-total-bar accent-{style['accent']}">
            <span>{PLAN_LABELS[plan_type]} total</span>
            <span class="team-total-val">{count} {advisor_label} · {_money(total_pay)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def _guarantee_expiration_value(key_prefix: str) -> str:
    if st.session_state.get(f"{key_prefix}_open_ended", False):
        return ""
    picked = st.session_state.get(f"{key_prefix}_expires")
    return picked.isoformat() if picked else ""


def _render_guarantee_expiration_fields(key_prefix: str, current_value: str = "") -> None:
    current = parse_guarantee_expires(current_value)
    st.checkbox(
        "No expiration date",
        value=current is None,
        key=f"{key_prefix}_open_ended",
        help="Check if the weekly guarantee has no end date yet.",
    )
    if not st.session_state.get(f"{key_prefix}_open_ended", current is None):
        st.date_input(
            "Guarantee expires",
            value=current or date.today(),
            key=f"{key_prefix}_expires",
            help=(
                "If the expiration falls mid pay period, the advisor still receives "
                "the guarantee for that entire pay period."
            ),
        )


def _guarantee_expiration_label(value: str) -> str:
    expires = parse_guarantee_expires(value)
    if expires:
        return expires.strftime("%m/%d/%y")
    return "Set date"


def _render_advisor_roster_manager():
    with st.expander("👥 Manage advisor roster", expanded=False):
        render_roster_sync_error("_advisor_roster_sync_error")
        st.caption(
            "Add advisors, remove terminations, or move them between pay plans. "
            "Changes save automatically."
        )

        for plan_type in PLAN_ORDER:
            rows = st.session_state.advisor_roster.get(plan_type, [])
            _render_plan_section_header(plan_type, len(rows))

            if not rows:
                st.caption("No advisors on this plan.")
            else:
                detail_header = "Guarantee expires" if plan_has_weekly_guarantee(plan_type) else "Plan detail"
                h1, h2, h3, h4, h5 = st.columns([0.8, 2, 1.2, 1.2, 0.9])
                with h1:
                    st.caption("ID")
                with h2:
                    st.caption("Advisor")
                with h3:
                    st.caption(detail_header)
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
                    if plan_type in (PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE) and row.top_labor_rate > 9.5:
                        st.caption(f"Top tier ${row.top_labor_rate:.0f}/hr")
                    elif plan_has_weekly_guarantee(plan_type):
                        with st.popover(
                            _guarantee_expiration_label(getattr(row, "guarantee_expires", "")),
                            use_container_width=True,
                        ):
                            st.caption(f"**{row.name}** — guarantee expiration")
                            _render_guarantee_expiration_fields(
                                f"adv_exp_{plan_type}_{i}",
                                getattr(row, "guarantee_expires", ""),
                            )
                            if st.button(
                                "Save expiration",
                                key=f"adv_exp_save_{plan_type}_{i}",
                                use_container_width=True,
                            ):
                                new_exp = _guarantee_expiration_value(f"adv_exp_{plan_type}_{i}")
                                _apply_roster_change(
                                    lambda r, pt=plan_type, idx=i, ge=new_exp, aid=row.advisor_id: update_advisor(
                                        r, pt, idx, aid, guarantee_expires=ge
                                    )
                                )
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
                if plan_has_weekly_guarantee(plan_type):
                    _render_guarantee_expiration_fields(f"new_adv_{plan_type}")
                if st.form_submit_button("Add advisor", use_container_width=True):
                    new_guarantee_expires = (
                        _guarantee_expiration_value(f"new_adv_{plan_type}")
                        if plan_has_weekly_guarantee(plan_type)
                        else ""
                    )
                    _apply_roster_change(
                        lambda r, pt=plan_type, nm=new_name, aid=new_id, ge=new_guarantee_expires: add_advisor(
                            r, pt, nm, aid, guarantee_expires=ge
                        )
                    )

            st.markdown('<div class="pay-plan-section-divider"></div>', unsafe_allow_html=True)

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
                if plan_type in (PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE):
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
                            r, pt, idx, aid,
                            top_labor_rate=tr if pt in (PLAN_NEW_ADVISORS, PLAN_NEW_ADVISORS_GUARANTEE) else None,
                        )
                    )
            if plan_has_weekly_guarantee(plan_type):
                st.caption(
                    "Guarantee expiration is set from the **Guarantee expires** button on each advisor row above."
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


def _render_csi_buttons(advisor_idx: int, advisor_name: str):
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
                key=f"csi_pick_{advisor_name}_{tier_key}",
                use_container_width=True,
                type="primary" if selected else "secondary",
            ):
                st.session_state[adv_key(advisor_idx, "csi_tier")] = tier_key
                persist_advisor_changes(advisor_idx, advisor_name)


def _live_advisor_payroll():
    """Read current widget state and calculate pay for every advisor."""
    weeks = pay_period_weeks()
    period_start = _pay_period_start()
    advisor_rows = flatten_roster(st.session_state.advisor_roster)
    synced_advisors = all_advisors_synced()
    advisor_results = [
        calculate_advisor_payroll(a, pay_period_weeks=weeks, pay_period_start=period_start)
        for a in synced_advisors
    ]
    return advisor_rows, synced_advisors, advisor_results, weeks


def _advisor_detail_panel(advisor_idx: int, row, accent: str) -> None:
    st.markdown(advisor_pay_detail_panel(accent), unsafe_allow_html=True)
    _render_advisor_section(advisor_idx, row)


def _render_advisor_pay_entry(advisor_idx: int, row, accent: str) -> None:
    open_key = advisor_section_open_key(row.name)
    weeks = pay_period_weeks()
    synced = all_advisors_synced()[advisor_idx]
    result = calculate_advisor_payroll(
        synced,
        pay_period_weeks=weeks,
        pay_period_start=_pay_period_start(),
    )

    col_toggle, col_card = st.columns([0.06, 0.94], vertical_alignment="center")
    with col_toggle:
        if st.button(
            "▼" if st.session_state.get(open_key, False) else "▶",
            key=advisor_section_toggle_key(row.name),
            help="Expand or collapse pay details",
        ):
            toggle_advisor_section(row.name)

    is_open = bool(st.session_state.get(open_key, False))

    with col_card:
        st.markdown(
            advisor_pay_card_header(
                row.name,
                _money(result.total_pay),
                accent,
                expanded=is_open,
            ),
            unsafe_allow_html=True,
        )

    if is_open:
        _advisor_detail_panel(advisor_idx, row, accent)


def _style_advisor_summary(df: pd.DataFrame, accents: list[str]):
    advisor_col = df.columns.get_loc("Advisor")

    def _row_style(row):
        theme = ACCENT_COLORS[accents[row.name]]
        styles = [""] * len(row)
        styles[advisor_col] = f"color: {theme['title']}; font-weight: 700"
        return styles

    return df.style.apply(_row_style, axis=1)


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
        args=(advisor_idx, row.name),
        help="Auto-filled from PAYROLL.xlsx, or enter manually.",
    )

    if row.plan_type == PLAN_SEASONED:
        st.toggle(
            f"Over {CP_HOURS_BUMP_THRESHOLD} CP hrs/RO — bump to ${TOM_JOEY_CP_BUMP_RATE:.0f}/hr",
            key=adv_key(advisor_idx, "cp_bump"),
            on_change=persist_advisor_changes,
            args=(advisor_idx, row.name),
            help="Turn on when they averaged more than 2.25 customer-pay hours per RO.",
        )
    elif not plan_has_weekly_guarantee(row.plan_type):
        st.toggle(
            f"Over {CP_HOURS_BUMP_THRESHOLD} CP hrs/RO — labor rate bump",
            key=adv_key(advisor_idx, "cp_bump"),
            on_change=persist_advisor_changes,
            args=(advisor_idx, row.name),
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
            args=(advisor_idx, row.name),
            help="Commission pay mirrors New Advisors plan with optional CP bump.",
        )

    st.markdown("##### Bonuses you enter")
    c1, c2 = st.columns(2)
    with c1:
        st.toggle(
            f"Alignment bonus — {_money(ALIGNMENT_BONUS_AMOUNT)}",
            key=adv_key(advisor_idx, "alignment_bonus"),
            on_change=persist_advisor_changes,
            args=(advisor_idx, row.name),
            help="Turn on when the advisor earned the alignment bonus this pay period.",
        )
    with c2:
        st.number_input(
            "SPIFF ($)",
            min_value=0.0,
            step=1.0,
            key=adv_key(advisor_idx, "spiff"),
            on_change=persist_advisor_changes,
            args=(advisor_idx, row.name),
        )

    st.text_area(
        "Notes for payroll clerk",
        key=adv_key(advisor_idx, "notes"),
        on_change=persist_advisor_changes,
        args=(advisor_idx, row.name),
        placeholder="Optional extra notes — guarantee language prints automatically on the PDF",
        height=72,
    )

    _render_csi_buttons(advisor_idx, row.name)

    synced = all_advisors_synced()[advisor_idx]
    weeks = pay_period_weeks()
    period_start = _pay_period_start()
    result = calculate_advisor_payroll(
        synced,
        pay_period_weeks=weeks,
        pay_period_start=period_start,
    )

    st.metric(
        "Labor pay",
        _money(result.hourly_pay),
        delta=f"${result.hourly_rate:.2f}/hr · {result.hourly_tier_label}" if result.hourly_pay else "No tier",
    )

    if plan_has_weekly_guarantee(row.plan_type):
        if not result.guarantee_eligible:
            st.caption(
                "**Guarantee expired** before this pay period — paid on New Advisors commission only."
            )
        else:
            expires = parse_guarantee_expires(synced.guarantee_expires)
            exp_text = f" Expires **{expires.strftime('%m/%d/%y')}**." if expires else ""
            paid_on = "commission sales" if result.commission_total >= result.guarantee_amount else "weekly guarantee"
            st.caption(
                f"**New Advisors commission:** {_money(result.commission_total)} · "
                f"**Weekly guarantee:** ${synced.weekly_guarantee:,.0f}/wk × {weeks:.1f} wks = "
                f"**{_money(result.guarantee_amount)}** · "
                f"**Paid on {paid_on}** ({_money(result.total_pay)}).{exp_text}"
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
    if plan_has_weekly_guarantee(row.plan_type) and result.guarantee_eligible:
        pay_rows.append(
            {
                "Pay": "Commission sales (New Advisors plan)",
                "Amount": result.commission_total,
                "Detail": "Labor + parts + CSI + alignment + SPIFF",
            }
        )
        if result.guarantee_active:
            pay_rows.append(
                {
                    "Pay": "Weekly guarantee top-up",
                    "Amount": result.guarantee_top_up,
                    "Detail": (
                        f"Guarantee {_money(result.guarantee_amount)} exceeds commission — "
                        f"${synced.weekly_guarantee:,.0f}/wk × {weeks:.1f} wks"
                    ),
                }
            )
        else:
            pay_rows.append(
                {
                    "Pay": "Weekly guarantee",
                    "Amount": result.guarantee_amount,
                    "Detail": "Commission sales exceeded guarantee — not added",
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

    render_payroll_sync_error("_advisor_payroll_sync_error", table="advisor_payroll_runs")

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
    st.caption("Click ▶ to expand pay details — the section stays open while you edit toggles and bonuses.")

    advisor_rows = flatten_roster(st.session_state.advisor_roster)
    weeks = pay_period_weeks()
    apply_advisor_value_store()

    global_idx = 0
    for plan_type in PLAN_ORDER:
        plan_rows = st.session_state.advisor_roster.get(plan_type, [])
        if not plan_rows:
            continue

        _render_plan_section_header(plan_type, len(plan_rows))
        plan_total = 0.0

        for local_i, row in enumerate(plan_rows):
            i = global_idx + local_i
            synced = all_advisors_synced()[i]
            result = calculate_advisor_payroll(
                synced,
                pay_period_weeks=weeks,
                pay_period_start=_pay_period_start(),
            )
            plan_total += result.total_pay
            _render_advisor_pay_entry(i, row, advisor_accent_for_index(i))

        _render_plan_section_footer(plan_type, plan_total, len(plan_rows))
        st.markdown(
            team_section_divider(PLAN_SECTION_STYLE[plan_type]["accent"]),
            unsafe_allow_html=True,
        )
        global_idx += len(plan_rows)

    advisor_rows, synced_advisors, advisor_results, weeks = _live_advisor_payroll()
    summary_rows = [
        _summary_row(row, synced_advisors[i], advisor_results[i])
        for i, row in enumerate(advisor_rows)
    ]
    summary_accents = [advisor_accent_for_index(i) for i in range(len(advisor_rows))]
    grand_total = sum(r["Total Pay"] for r in summary_rows)

    st.markdown("---")
    st.markdown("##### Advisor payroll summary")
    summary_df = pd.DataFrame(summary_rows)
    st.dataframe(
        _style_advisor_summary(summary_df, summary_accents),
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
            if st.session_state.get("_advisor_payroll_sync_error"):
                st.error(
                    f"Advisor payroll for {saved_period} was saved on this session only — "
                    "cloud backup failed. Open Reports after fixing the connection, or save again."
                )
            else:
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
            run_id, sync_error = save_advisor_payroll_run(
                all_advisors_synced(),
                st.session_state.pay_period,
                weeks,
                run_id=st.session_state.get("active_advisor_run_id"),
                status="completed",
            )
            st.session_state.active_advisor_run_id = run_id
            st.session_state.advisor_payroll_completed = True
            if sync_error:
                st.session_state["_advisor_payroll_sync_error"] = sync_error
            else:
                st.session_state.pop("_advisor_payroll_sync_error", None)
            st.session_state["_advisor_payroll_saved_period"] = st.session_state.pay_period
            del st.session_state["advisor_payroll_complete_confirm"]
            st.rerun()

    refresh_advisor_value_store()
