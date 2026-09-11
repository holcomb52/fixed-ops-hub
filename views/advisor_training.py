"""Service Advisor daily training log — end-of-shift progress for new advisors."""

from __future__ import annotations

from datetime import date

import streamlit as st

from lib.advisor_training_calc import (
    SKILL_LEVELS,
    SKILLS,
    TOPIC_GROUPS,
    progress_from_logs,
    suggested_day_number,
    trainee_names_from_logs,
)
from lib.advisor_training_storage import (
    clear_advisor_training_session,
    list_advisor_training_logs,
    save_advisor_training_log,
    serialize_advisor_training_session,
    skills_from_session,
    topics_from_session,
)
from lib.page_ui import page_hero, stat_card, status_banner
from views.payroll_helpers import render_payroll_sync_error


def _init_state():
    defaults = {
        "at_trainee_name": "",
        "at_trainer_name": "",
        "at_log_date": date.today(),
        "at_day_number": 1,
        "at_other_topic_note": "",
        "at_trainee_questions": "",
        "at_trainer_notes": "",
        "at_next_focus": "",
        "active_advisor_training_run_id": None,
        "advisor_training_completed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    for _, items in TOPIC_GROUPS:
        for tid, _ in items:
            key = f"at_topic_{tid}"
            if key not in st.session_state:
                st.session_state[key] = False
    for sid, _ in SKILLS:
        key = f"at_skill_{sid}"
        if key not in st.session_state:
            st.session_state[key] = "—"


def render():
    _init_state()

    st.markdown(
        page_hero(
            "Advisor Training",
            "Daily end-of-shift log for new service advisors — topics covered, "
            "skill check-in, notes, and focus for next session.",
            tag="Training",
            tag_style="live",
        ),
        unsafe_allow_html=True,
    )

    if st.session_state.get("advisor_training_completed"):
        st.markdown(
            status_banner(
                f"Editing saved training log · "
                f"{st.session_state.get('at_trainee_name') or 'Trainee'} · "
                f"Day {st.session_state.get('at_day_number') or '—'} · "
                "Update and Complete & Save again after changes.",
                "success",
            ),
            unsafe_allow_html=True,
        )

    render_payroll_sync_error("_advisor_training_sync_error", table="advisor_training_logs")

    prior_logs = list_advisor_training_logs()
    known_trainees = trainee_names_from_logs(prior_logs)

    top_l, top_r = st.columns([3, 1])
    with top_r:
        if st.button("＋ New daily log", use_container_width=True):
            clear_advisor_training_session()
            st.rerun()

    def _on_trainee_quick_pick():
        pick = st.session_state.get("at_trainee_quick_pick")
        if not pick or pick == "— New trainee —":
            return
        st.session_state.at_trainee_name = pick
        if st.session_state.get("active_advisor_training_run_id"):
            return
        prog = progress_from_logs(pick, prior_logs)
        st.session_state.at_day_number = suggested_day_number(prog)
        if prog.latest_next_focus:
            st.session_state.at_next_focus = prog.latest_next_focus

    st.markdown("##### Log header")
    h1, h2 = st.columns(2)
    with h1:
        if known_trainees:
            st.selectbox(
                "Returning trainee (optional)",
                ["— New trainee —"] + known_trainees,
                key="at_trainee_quick_pick",
                on_change=_on_trainee_quick_pick,
                help="Select to fill the trainee name and suggest the next training day.",
            )
        st.text_input(
            "Trainee name",
            key="at_trainee_name",
            placeholder="New advisor name",
        )
        st.text_input(
            "Trainer / mentor name",
            key="at_trainer_name",
            placeholder="Who coached today",
        )
    with h2:
        st.date_input("Date", key="at_log_date", format="MM/DD/YYYY")
        st.number_input(
            "Training day #",
            min_value=1,
            max_value=365,
            step=1,
            key="at_day_number",
        )

    trainee = (st.session_state.at_trainee_name or "").strip()
    progress = progress_from_logs(
        trainee,
        prior_logs,
        exclude_run_id=st.session_state.get("active_advisor_training_run_id"),
    )

    if trainee and progress.log_count:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                stat_card("Prior logs", str(progress.log_count), "cyan", "📋"),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                stat_card(
                    "Topics so far",
                    f"{progress.topics_ever_covered}/{progress.topics_total}",
                    "orange",
                    "◎",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                stat_card(
                    "Proficient",
                    str(progress.skill_counts.get("proficient", 0)),
                    "green",
                    "✅",
                ),
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                stat_card(
                    "Needs practice",
                    str(progress.skill_counts.get("needs_practice", 0)),
                    "rose",
                    "◆",
                ),
                unsafe_allow_html=True,
            )
        if progress.latest_next_focus:
            st.caption(f"Last focus item: {progress.latest_next_focus}")

    st.markdown("---")
    st.markdown("##### 1. Topics covered today")
    st.caption("Check every topic reviewed or practiced with the trainee today.")

    for group_name, items in TOPIC_GROUPS:
        st.markdown(f"**{group_name}**")
        cols = st.columns(2)
        for i, (tid, label) in enumerate(items):
            with cols[i % 2]:
                st.checkbox(label, key=f"at_topic_{tid}")

    if st.session_state.get("at_topic_other"):
        st.text_input(
            "Other topic detail",
            key="at_other_topic_note",
            placeholder="Describe the other topic covered",
        )

    st.markdown("---")
    st.markdown("##### 2. Skill proficiency check-in")
    st.caption("Rate each skill for today — leave blank if not observed.")

    level_options = ["—"] + [level for level, _ in SKILL_LEVELS]
    level_labels = {"—": "Not rated", **{k: v for k, v in SKILL_LEVELS}}
    for sid, label in SKILLS:
        st.selectbox(
            label,
            level_options,
            key=f"at_skill_{sid}",
            format_func=lambda v: level_labels.get(v, v),
        )

    st.markdown("---")
    st.markdown("##### 3–5. Notes")
    st.text_area(
        "3. Trainee questions / areas of confusion",
        key="at_trainee_questions",
        height=90,
        placeholder="What did they ask about or struggle with?",
    )
    st.text_area(
        "4. Trainer notes & feedback",
        key="at_trainer_notes",
        height=90,
        placeholder="Wins, coaching points, observed habits…",
    )
    st.text_area(
        "5. Focus for next session",
        key="at_next_focus",
        height=80,
        placeholder="What should tomorrow emphasize?",
    )

    topics = topics_from_session()
    skills = skills_from_session()
    log_date: date = st.session_state.at_log_date
    date_label = log_date.isoformat() if isinstance(log_date, date) else str(log_date)

    snapshot = serialize_advisor_training_session(
        trainee_name=st.session_state.at_trainee_name,
        trainer_name=st.session_state.at_trainer_name,
        log_date=date_label,
        day_number=int(st.session_state.at_day_number or 1),
        topics=topics,
        skills=skills,
        other_topic_note=st.session_state.at_other_topic_note,
        trainee_questions=st.session_state.at_trainee_questions,
        trainer_notes=st.session_state.at_trainer_notes,
        next_focus=st.session_state.at_next_focus,
    )

    checked = snapshot["topics_checked"]
    rated = snapshot["skills_rated"]
    st.markdown("---")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(
            stat_card("Topics today", str(checked), "cyan", "☑"),
            unsafe_allow_html=True,
        )
    with s2:
        st.markdown(
            stat_card("Skills rated", str(rated), "orange", "◎"),
            unsafe_allow_html=True,
        )
    with s3:
        st.markdown(
            stat_card("Training day", str(snapshot["day_number"]), "green", "#"),
            unsafe_allow_html=True,
        )

    can_save = bool(snapshot["trainee_name"] and snapshot["trainer_name"])
    if not can_save:
        st.markdown(
            status_banner("Enter trainee and trainer names before saving.", "warn"),
            unsafe_allow_html=True,
        )

    st.markdown("##### ✅ Save to Reports")
    confirm = st.checkbox(
        "This daily training log is complete and ready to save",
        key="at_complete_confirm",
    )
    if st.button(
        "Complete & Save to Reports",
        type="primary",
        disabled=not (confirm and can_save),
        use_container_width=True,
    ):
        run_id, sync_error = save_advisor_training_log(
            snapshot,
            run_id=st.session_state.get("active_advisor_training_run_id"),
            status="completed",
            cloud_sync=True,
        )
        st.session_state.active_advisor_training_run_id = run_id
        st.session_state.advisor_training_completed = True
        if sync_error:
            st.session_state["_advisor_training_sync_error"] = sync_error
        else:
            st.session_state.pop("_advisor_training_sync_error", None)
        st.session_state["_at_saved_label"] = (
            f"{snapshot['trainee_name']} · Day {snapshot['day_number']} · {date_label}"
        )
        del st.session_state["at_complete_confirm"]
        st.rerun()

    if saved := st.session_state.pop("_at_saved_label", None):
        if st.session_state.get("_advisor_training_sync_error"):
            st.error(
                f"Training log for {saved} was saved on this session only — cloud backup failed. "
                "Open Reports after fixing the connection, or save again."
            )
        else:
            st.success(f"Saved — find it in Reports under Advisor Training · {saved}")
            st.balloons()
