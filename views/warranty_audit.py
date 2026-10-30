"""Stellantis warranty audit: store one manual, then check a repair order against it."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from lib.page_ui import page_hero, section_title, stat_card, status_banner
from lib.warranty_audit_llm import (
    LlmError,
    extract_repair_order,
    llm_configured,
    prepare_ro_input,
    run_audit,
)
from lib.warranty_audit_manual import ManualExtractError, csv_download_name, findings_to_csv
from lib.warranty_audit_storage import (
    apply_warranty_audit_snapshot_to_session,
    audit_tables_sql,
    list_warranty_audit_runs,
    load_active_manual,
    load_warranty_audit_run,
    new_manual_record,
    save_audit_run,
    save_manual_record,
)

_LABOR_COLUMNS = ["op_code", "description", "hours", "tech_number"]
_PUNCH_COLUMNS = ["tech_number", "on", "off", "hours"]
_PART_COLUMNS = ["part_number", "description", "quantity", "failed"]
_SIG_OPTIONS = ["Not visible", "Yes", "No"]


def render():
    ready = llm_configured()
    st.markdown(
        page_hero(
            "Warranty Audit",
            "Store the Stellantis warranty manual once. Photograph a repair order "
            "and get a list of what to correct before the audit.",
            tag="Ready" if ready else "API key required",
            tag_style="live" if ready else "warn",
        ),
        unsafe_allow_html=True,
    )
    if not ready:
        st.markdown(
            status_banner(
                "Add OPENAI_API_KEY to .env or Streamlit secrets to read repair orders. "
                "You can still store the warranty manual. See the README.",
                "warn",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.caption("Repair orders are read with the vision model named in OPENAI_MODEL, or gpt-4o if that secret is unset.")

    manual = _render_manual()
    st.markdown("<hr>", unsafe_allow_html=True)
    _render_repair_order(manual, ready)
    result = st.session_state.get("warranty_audit_result")
    if result:
        st.markdown("<hr>", unsafe_allow_html=True)
        _render_result(result)
    _render_recent()


def _render_manual():
    st.markdown(
        section_title(
            "Warranty manual",
            "Upload the text-based warranty manual PDF once. Later audits reuse the stored sections.",
        ),
        unsafe_allow_html=True,
    )
    current = load_active_manual()
    flash = st.session_state.pop("warranty_audit_manual_flash", None)
    if flash == "stored":
        st.success(st.session_state.pop("warranty_audit_manual_detail", "Manual stored."))
    elif flash:
        st.warning(flash)
        _show_sql(str(flash))
    if current:
        _render_manual_status(current)
        replace = st.checkbox(
            "Replace the stored manual",
            value=False,
            key="warranty_audit_replace_manual",
        )
    else:
        st.markdown(
            status_banner("No warranty manual is stored yet. Upload the PDF to start.", "info"),
            unsafe_allow_html=True,
        )
        replace = True

    if not replace:
        return current

    upload = st.file_uploader(
        "Warranty manual PDF",
        type=["pdf"],
        key="warranty_audit_manual_file",
        help="Use the text warranty manual, not a photo scan. Scanned pages have no text to cite.",
    )
    if upload is not None and st.button(
        "Replace stored manual" if current else "Store manual",
        type="primary",
        key="warranty_audit_store_manual",
    ):
        with st.spinner("Reading the manual and storing sections..."):
            try:
                record = new_manual_record(upload.name, upload.getvalue())
                saved, err = save_manual_record(record)
            except ManualExtractError as exc:
                st.error(str(exc))
                return current
            except Exception as exc:
                st.error(f"Could not store the manual. {exc}")
                return current
        where = "Supabase and this computer" if saved.get("storage_source") == "supabase" else "this computer"
        if err:
            st.session_state.warranty_audit_manual_flash = err
        else:
            st.session_state.warranty_audit_manual_flash = "stored"
            st.session_state.warranty_audit_manual_detail = (
                f"Stored {saved.get('filename')} "
                f"({saved.get('page_count')} pages, {saved.get('chunk_count')} sections) on {where}."
            )
        st.rerun()
    return current


def _render_manual_status(current: dict):
    source = "Supabase" if current.get("storage_source") == "supabase" else "This computer"
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("Manual", current.get("filename") or "Stored", "cyan", "📘"),
        ("PDF pages", str(current.get("page_count") or 0), "violet", "📄"),
        ("Sections", str(current.get("chunk_count") or 0), "green", "§"),
        ("Stored on", source, "orange", "◎"),
    ]
    for column, (label, value, accent, icon) in zip((c1, c2, c3, c4), cards):
        with column:
            card = stat_card(label, value, accent, icon)
            if len(str(value)) > 18:
                card = card.replace('class="stat-value"', 'class="stat-value stat-value-sm"')
            st.markdown(card, unsafe_allow_html=True)
    uploaded = str(current.get("uploaded_at") or "")[:16].replace("T", " ")
    if uploaded:
        st.caption(f"Stored {uploaded} UTC. The original PDF is not kept — only the extracted text.")
    labels = []
    for chunk in current.get("chunks") or []:
        label = str(chunk.get("section_label") or "").strip()
        if label and label not in labels:
            labels.append(label)
    if labels:
        st.caption("Sections found: " + " · ".join(labels[:12]))
    for warning in current.get("warnings") or []:
        st.warning(warning)
    if current.get("storage_warning"):
        st.warning(current["storage_warning"])
        _show_sql(str(current["storage_warning"]))


def _render_repair_order(manual: dict | None, llm_ready: bool):
    st.markdown(
        section_title(
            "Repair order",
            "Take a photo or upload a JPG, PNG, or PDF. Correct anything that was read wrong, then run the audit.",
        ),
        unsafe_allow_html=True,
    )
    if not manual:
        st.caption("Store a warranty manual before running an audit. You can still read a repair order.")
    left, right = st.columns(2)
    with left:
        camera = st.camera_input("Take a photo of the repair order", key="warranty_audit_camera")
    with right:
        upload = st.file_uploader(
            "Or upload a scan",
            type=["jpg", "jpeg", "png", "pdf"],
            key="warranty_audit_ro_file",
        )
    name, data = _selected_file(upload, camera)
    if upload is not None and camera is not None:
        st.caption("Both a photo and an upload are present. The uploaded file is the one that will be checked.")
    if not data:
        return
    digest = hashlib.sha256(data).hexdigest()[:16]
    if st.button("Read repair order", disabled=not llm_ready, key="warranty_audit_read"):
        with st.spinner("Reading the repair order..."):
            try:
                prepared = prepare_ro_input(name, data)
                extracted = extract_repair_order(
                    images=prepared["images"],
                    document_text=prepared["document_text"],
                )
            except LlmError as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"Could not read the repair order. {exc}")
                return
        st.session_state.warranty_audit_extract = extracted
        st.session_state.warranty_audit_extract_digest = digest
        st.session_state.warranty_audit_extract_name = name
        st.session_state.warranty_audit_read_warnings = prepared["warnings"]
        st.session_state.warranty_audit_form_token = f"{digest}-{_stamp()}"
        st.session_state.pop("warranty_audit_result", None)
        st.session_state.pop("warranty_audit_active_run_id", None)
        st.rerun()

    if st.session_state.get("warranty_audit_extract_digest") != digest:
        if not llm_ready:
            st.caption("Set OPENAI_API_KEY before reading this repair order.")
        else:
            st.caption("Click Read repair order. The audit uses the fields below, so you can fix a bad read first.")
        return

    for warning in st.session_state.get("warranty_audit_read_warnings") or []:
        st.warning(warning)
    extracted = st.session_state.get("warranty_audit_extract") or {}
    if extracted.get("unreadable"):
        st.warning("Could not read: " + ", ".join(str(item) for item in extracted["unreadable"]))
    edited = _repair_order_form(extracted)
    audit_disabled = not llm_ready or not manual or not (manual.get("chunks") or [])
    if st.button(
        "Audit against the manual",
        type="primary",
        disabled=audit_disabled,
        key="warranty_audit_run",
    ):
        with st.spinner("Comparing the repair order to the stored manual..."):
            try:
                result = run_audit(edited, list(manual.get("chunks") or []))
            except LlmError as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                st.error(f"The audit could not be completed. {exc}")
                return
        result["source_name"] = st.session_state.get("warranty_audit_extract_name") or name
        result["manual_id"] = manual.get("id")
        result["manual_filename"] = manual.get("filename")
        result["audited_at"] = datetime.now(timezone.utc).isoformat()
        st.session_state.warranty_audit_result = result
        st.session_state.pop("warranty_audit_active_run_id", None)
        st.session_state.pop("warranty_audit_saved_label", None)
        st.rerun()
    if manual and not audit_disabled:
        st.caption("The checker can only flag a requirement it can quote from the stored manual.")


def _repair_order_form(extracted: dict) -> dict:
    token = st.session_state.get("warranty_audit_form_token") or "ro"
    st.markdown("##### What was read")
    st.caption("Change any field that does not match the paper. Not visible means unknown, not missing.")
    a, b, c = st.columns(3)
    with a:
        ro_number = st.text_input("RO number", value=extracted.get("ro_number") or "", key=f"{token}_ro")
        open_date = st.text_input("Open date", value=extracted.get("open_date") or "", key=f"{token}_open")
    with b:
        vin = st.text_input("VIN", value=extracted.get("vin") or "", key=f"{token}_vin")
        close_date = st.text_input("Close date", value=extracted.get("close_date") or "", key=f"{token}_close")
    with c:
        mileage = st.text_input("Mileage", value=extracted.get("mileage") or "", key=f"{token}_miles")
        repair_date = st.text_input("Repair date", value=extracted.get("repair_date") or "", key=f"{token}_repair")
    concern = st.text_area("Concern", value=extracted.get("customer_concern") or "", key=f"{token}_concern")
    cause = st.text_area("Cause", value=extracted.get("cause") or "", key=f"{token}_cause")
    correction = st.text_area("Correction", value=extracted.get("correction") or "", key=f"{token}_correction")

    st.markdown("##### Labor operations")
    labor = st.data_editor(
        _frame(extracted.get("labor_operations"), _LABOR_COLUMNS),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{token}_labor",
        column_config={
            "op_code": "Op code",
            "description": "Description",
            "hours": "Hours",
            "tech_number": "Tech #",
        },
    )
    st.markdown("##### Time punches")
    punches = st.data_editor(
        _frame(extracted.get("time_punches"), _PUNCH_COLUMNS),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{token}_punches",
        column_config={
            "tech_number": "Tech #",
            "on": "On",
            "off": "Off",
            "hours": "Hours",
        },
    )
    st.markdown("##### Parts")
    parts = st.data_editor(
        _frame(_parts_for_editor(extracted.get("parts")), _PART_COLUMNS),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{token}_parts",
        column_config={
            "part_number": "Part #",
            "description": "Description",
            "quantity": "Qty",
            "failed": "Failed (yes/no)",
        },
    )
    signatures = extracted.get("signatures") or {}
    s1, s2, s3 = st.columns(3)
    with s1:
        customer_sig = st.selectbox(
            "Customer signature",
            _SIG_OPTIONS,
            index=_sig_index(signatures.get("customer")),
            key=f"{token}_sig_customer",
        )
    with s2:
        advisor_sig = st.selectbox(
            "Advisor signature",
            _SIG_OPTIONS,
            index=_sig_index(signatures.get("advisor")),
            key=f"{token}_sig_advisor",
        )
    with s3:
        tech_sig = st.selectbox(
            "Technician signature",
            _SIG_OPTIONS,
            index=_sig_index(signatures.get("technician")),
            key=f"{token}_sig_tech",
        )
    notes = st.text_area(
        "Other notes visible on the RO",
        value=extracted.get("other_visible_notes") or "",
        key=f"{token}_notes",
    )
    return {
        "ro_number": ro_number,
        "open_date": open_date,
        "close_date": close_date,
        "repair_date": repair_date,
        "vin": vin,
        "mileage": mileage,
        "customer_concern": concern,
        "cause": cause,
        "correction": correction,
        "labor_operations": _records(labor, _LABOR_COLUMNS),
        "time_punches": _records(punches, _PUNCH_COLUMNS),
        "parts": _records(parts, _PART_COLUMNS),
        "signatures": {
            "customer": customer_sig,
            "advisor": advisor_sig,
            "technician": tech_sig,
        },
        "other_visible_notes": notes,
        "unreadable": extracted.get("unreadable") or [],
    }


def _render_result(result: dict):
    findings = list(result.get("findings") or [])
    required = [item for item in findings if item.get("counts_as_required_correction")]
    rejected = [item for item in findings if not item.get("supported")]
    ro = result.get("ro") or {}
    ro_number = str(ro.get("ro_number") or "").strip()
    summary = str(result.get("summary") or "")
    st.markdown(
        section_title(
            "What to correct",
            "A correction is listed only when the stored manual contains the quoted sentence.",
        ),
        unsafe_allow_html=True,
    )
    saved_label = st.session_state.get("warranty_audit_saved_label")
    if st.session_state.get("warranty_audit_active_run_id"):
        st.info(f"Viewing saved audit{f' for RO {saved_label}' if saved_label else ''}.")
    flash = st.session_state.pop("warranty_audit_flash", None)
    if flash == "saved":
        st.success("Audit saved. It is listed below and on Reports.")
    elif flash:
        st.warning(flash)
        _show_sql(str(flash))

    kind = "warn" if required else "success"
    st.markdown(status_banner(summary, kind), unsafe_allow_html=True)
    manual_name = result.get("manual_filename") or "stored manual"
    st.caption(
        f"Compared with {int(result.get('manual_excerpt_count') or 0)} section(s) from {manual_name}."
    )
    counts = {name: 0 for name in ("critical", "major", "minor")}
    for item in required:
        if item.get("severity") in counts:
            counts[item["severity"]] += 1
    c1, c2, c3, c4 = st.columns(4)
    stats = [
        ("Must fix", str(len(required)), "orange", "⚑"),
        ("Critical", str(counts["critical"]), "violet", "▲"),
        ("Major", str(counts["major"]), "cyan", "◆"),
        ("Minor", str(counts["minor"]), "green", "•"),
    ]
    for column, (label, value, accent, icon) in zip((c1, c2, c3, c4), stats):
        with column:
            st.markdown(stat_card(label, value, accent, icon), unsafe_allow_html=True)

    if required:
        for finding in required:
            _finding_card(finding)
    elif not rejected:
        st.caption("No stored excerpt required a change on this repair order.")

    if rejected:
        with st.expander(f"Not counted ({len(rejected)}) — quote was not in the stored manual"):
            st.caption("These suggestions are not corrections. The manual text used for this audit does not contain the quote.")
            for finding in rejected:
                st.text(f"{finding.get('severity', '').title()} · {finding.get('ro_field')}")
                st.text(finding.get("whats_wrong") or "")
                st.caption(finding.get("support_note") or "")

    retrieved = result.get("retrieved") or []
    if retrieved:
        with st.expander("Manual sections used"):
            for chunk in retrieved:
                st.text(
                    f"PDF page {chunk.get('page_number')} · {chunk.get('section_label') or ''}"
                )
                st.text(chunk.get("text") or "")

    csv_text = findings_to_csv(ro_number, summary, findings)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "Download findings CSV",
            data=csv_text.encode("utf-8-sig"),
            file_name=csv_download_name(ro_number),
            mime="text/csv",
            use_container_width=True,
            key="warranty_audit_csv_download",
        )
    with d2:
        if st.button("Save audit to history", use_container_width=True, key="warranty_audit_save"):
            run_id, err = save_audit_run(result)
            st.session_state.warranty_audit_active_run_id = run_id
            st.session_state.warranty_audit_saved_label = ro_number or "Saved audit"
            st.session_state.warranty_audit_flash = err or "saved"
            st.rerun()
    with d3:
        if st.button("Clear findings", use_container_width=True, key="warranty_audit_clear"):
            for key in (
                "warranty_audit_result",
                "warranty_audit_active_run_id",
                "warranty_audit_saved_label",
            ):
                st.session_state.pop(key, None)
            st.rerun()


def _finding_card(finding: dict):
    severity = str(finding.get("severity") or "major").title()
    with st.container(border=True):
        st.markdown(f"##### {severity}")
        st.caption(str(finding.get("ro_field") or "Repair order"))
        st.text(finding.get("whats_wrong") or "")
        if finding.get("how_to_fix"):
            st.caption("How to fix it")
            st.text(finding.get("how_to_fix") or "")
        page = finding.get("manual_page")
        section = finding.get("manual_section") or "Stored manual"
        st.caption(f"{section} · PDF page {page}" if page else section)
        if finding.get("support_note"):
            st.caption(finding["support_note"])
        st.caption("Manual excerpt")
        st.text(finding.get("citation_quote") or "")


def _render_recent():
    runs = list_warranty_audit_runs()
    st.markdown("<hr>", unsafe_allow_html=True)
    with st.expander(f"Saved audits ({len(runs)})"):
        st.caption("Saving is optional. Delete a saved audit from Reports.")
        if not runs:
            st.caption("No audits saved yet.")
            return
        for run in runs[:8]:
            run_id = run.get("id")
            if not run_id:
                continue
            label = run.get("ro_number") or run.get("source_name") or "Repair order"
            when = str(run.get("completed_at") or "")[:16].replace("T", " ")
            st.text(
                f"RO {label} · {int(run.get('finding_count') or 0)} to fix · "
                f"{int(run.get('critical_count') or 0)} critical · {when}"
            )
            loaded = load_warranty_audit_run(run_id)
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Open", key=f"warranty_audit_open_{run_id}", use_container_width=True):
                    if loaded:
                        apply_warranty_audit_snapshot_to_session(loaded, run_id)
                        st.rerun()
            with b2:
                if loaded:
                    snapshot = loaded.get("snapshot") or {}
                    ro = snapshot.get("ro") or {}
                    csv_text = findings_to_csv(
                        str(ro.get("ro_number") or run.get("ro_number") or ""),
                        str(snapshot.get("summary") or ""),
                        list(snapshot.get("findings") or []),
                    )
                    st.download_button(
                        "CSV",
                        data=csv_text.encode("utf-8-sig"),
                        file_name=csv_download_name(str(ro.get("ro_number") or label)),
                        mime="text/csv",
                        key=f"warranty_audit_hist_csv_{run_id}",
                        use_container_width=True,
                    )


def _show_sql(message: str):
    if "warranty_audit_tables.sql" not in message:
        return
    sql = audit_tables_sql()
    if not sql:
        return
    with st.expander("Supabase SQL for warranty audit tables"):
        st.code(sql, language="sql")


def _selected_file(upload, camera):
    if upload is not None:
        return upload.name or "repair-order", upload.getvalue()
    if camera is not None:
        return "camera-repair-order.jpg", camera.getvalue()
    return "", b""


def _frame(rows, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows or []), columns=columns)
    return frame.fillna("")


def _parts_for_editor(parts) -> list[dict]:
    rows = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        failed = part.get("failed")
        if failed is True or str(failed).strip().casefold() in {"true", "yes", "y"}:
            label = "yes"
        elif failed is False or str(failed).strip().casefold() in {"false", "no", "n"}:
            label = "no"
        else:
            label = ""
        rows.append(
            {
                "part_number": part.get("part_number") or "",
                "description": part.get("description") or "",
                "quantity": part.get("quantity") or "",
                "failed": label,
            }
        )
    return rows


def _records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    records = []
    for row in frame.fillna("").to_dict(orient="records"):
        item = {column: str(row.get(column) or "").strip() for column in columns}
        if any(item.values()):
            records.append(item)
    return records


def _sig_index(value) -> int:
    if value is True or str(value).strip().casefold() in {"true", "yes"}:
        return 1
    if value is False or str(value).strip().casefold() in {"false", "no"}:
        return 2
    return 0


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S%f")
