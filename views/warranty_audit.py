"""Stellantis warranty audit: store one manual, then check a repair order against it."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from lib.claim_camera import claim_camera
from lib.page_ui import page_hero, section_title, stat_card, status_banner
from lib.warranty_audit_llm import (
    LlmError,
    MAX_CLAIM_PHOTOS,
    append_claim_photos,
    extract_repair_order,
    llm_configured,
    normalize_repair_order,
    prepare_documents,
    run_audit,
)
from lib.warranty_audit_manual import ManualExtractError, csv_download_name, findings_to_csv
from lib.warranty_audit_storage import (
    apply_warranty_audit_snapshot_to_session,
    audit_tables_sql,
    clear_live_photos,
    delete_live_photo,
    fetch_live_photos,
    list_warranty_audit_runs,
    load_active_manual,
    load_warranty_audit_run,
    new_manual_record,
    publish_live_photos,
    save_audit_run,
    save_manual_record,
)

_LABOR_COLUMNS = ["ro_number", "job_number", "op_code", "description", "failure_code", "hours", "tech_number", "add_on"]
_PUNCH_COLUMNS = ["tech_number", "on", "off", "hours"]
_PART_COLUMNS = ["ro_number", "part_number", "description", "quantity", "failed"]
_TOTAL_COLUMNS = [
    "ro_number",
    "technician_id",
    "technician_name",
    "total_parts",
    "total_labor",
    "total_special_service",
    "pre_tax_total",
]
_SIG_OPTIONS = ["Not visible", "Yes", "No"]
_DOC_OPTIONS = ["Repair order", "FCA claim acknowledgement"]


def render():
    ready = llm_configured()
    st.markdown(
        page_hero(
            "Warranty Audit",
            "Store the Stellantis warranty manual once. Photograph a Reynolds Ignite "
            "repair order or FCA claim acknowledgement and get a list of what to correct.",
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
            "Use your phone to photograph the repair order or claim acknowledgement, then upload the pictures here.",
        ),
        unsafe_allow_html=True,
    )
    if not manual:
        st.caption("Store a warranty manual before running an audit. You can still read a photo.")
    tray = list(st.session_state.get("warranty_audit_photo_tray") or [])
    _watch_phone_photos()
    st.markdown(
        """
        <style>
        [class*="st-key-warranty_audit_ro_file"] [data-testid="stFileUploaderDropzone"],
        [class*="st-key-warranty_audit_ro_file"] [data-testid="stFileDropzone"] {
            min-height: 190px;
            border: 2px dashed rgba(0, 212, 255, 0.7) !important;
            border-radius: 16px !important;
            background: rgba(0, 212, 255, 0.08) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Add up to {MAX_CLAIM_PHOTOS} pictures for one claim. "
        "Tap Open camera, snap every page, then tap Add these pictures. "
        "The camera stays open between pages. You can also choose photos you already took, or drag pictures onto the box."
    )
    photo_generation = int(st.session_state.get("warranty_audit_photo_generation") or 0)
    snapped = claim_camera(
        MAX_CLAIM_PHOTOS - len(tray),
        key=f"warranty_audit_multishot_{photo_generation}",
    )
    upload = st.file_uploader(
        "Drag pictures here",
        type=["jpg", "jpeg", "png", "webp", "heic", "heif", "pdf"],
        accept_multiple_files=True,
        key=f"warranty_audit_ro_file_{photo_generation}",
        help="Drag pictures onto this box. On a phone, use Open camera above to snap every page before adding them.",
    )
    incoming = _without_ignored(_incoming_photos(upload) + list(snapped or []))
    if incoming:
        updated, warnings = append_claim_photos(tray, incoming)
        added = len(updated) > len(tray)
        st.session_state.warranty_audit_photo_tray = updated
        st.session_state.warranty_audit_photo_warnings = warnings
        sync_error = publish_live_photos(updated)
        if sync_error:
            st.session_state.warranty_audit_photo_warnings = warnings + [sync_error]
        if added:
            st.rerun()
        tray = updated
    for warning in st.session_state.get("warranty_audit_photo_warnings") or []:
        st.warning(warning)
    if not tray:
        st.caption(f"No pictures yet. You can add {MAX_CLAIM_PHOTOS}.")
        _render_carried_numbers()
        return
    photos = [(item["name"], item["data"]) for item in tray]
    _show_photo_tray(tray)
    if len(tray) >= MAX_CLAIM_PHOTOS:
        st.caption(f"This claim has {MAX_CLAIM_PHOTOS} pictures, which is the maximum.")
    else:
        st.caption(f"{len(tray)} of {MAX_CLAIM_PHOTOS} pictures. Photo reader 10. Tap Read repair order when every page is here.")
    digest = hashlib.sha256("".join(item["sha"] for item in tray).encode("ascii")).hexdigest()[:16]
    names = ", ".join(name for name, _data in photos)
    if st.button("Read repair order", disabled=not llm_ready, key="warranty_audit_read"):
        with st.spinner("Reading every page, including the notes and the time punches."):
            progress = st.progress(0, text="Starting to read the pictures...")

            def _on_progress(done: int, total: int) -> None:
                if total <= 0:
                    return
                if done > total:
                    progress.progress(1.0, text="Organizing notes and time punches")
                else:
                    progress.progress(done / total, text=f"Reading picture {done} of {total}")

            try:
                prepared = prepare_documents(photos)
                extracted = extract_repair_order(
                    images=prepared["images"],
                    document_text=prepared["document_text"],
                    on_progress=_on_progress,
                )
            except LlmError:
                prepared = {"warnings": [
                    "The pictures could not be read automatically. Fill in the fields below, then check the document."
                ]}
                extracted = normalize_repair_order({"unreadable": ["the pictures"]})
            except Exception as exc:
                st.error(f"Could not read the repair order. {exc}")
                return
            prepared["warnings"] = list(prepared.get("warnings") or []) + apply_carried_numbers(
                extracted,
                st.session_state.get("warranty_audit_carry"),
            )
            progress.empty()
        st.session_state.warranty_audit_extract = extracted
        st.session_state.warranty_audit_extract_digest = digest
        st.session_state.warranty_audit_extract_name = names
        st.session_state.warranty_audit_read_warnings = prepared["warnings"]
        st.session_state.warranty_audit_form_token = f"{digest}-{_stamp()}"
        st.session_state.pop("warranty_audit_result", None)
        st.session_state.pop("warranty_audit_active_run_id", None)
        st.rerun()

    if st.session_state.get("warranty_audit_extract_digest") != digest:
        if not llm_ready:
            st.caption("Set OPENAI_API_KEY before reading this repair order.")
        else:
            st.caption("Click Read repair order. Notes, time punches, labor, and parts are filled in for you. Change only a field that does not match the paper.")
        return

    for warning in st.session_state.get("warranty_audit_read_warnings") or []:
        st.warning(warning)
    extracted = st.session_state.get("warranty_audit_extract") or {}
    if extracted.get("unreadable"):
        st.warning("Could not read: " + ", ".join(str(item) for item in extracted["unreadable"]))
    edited = _repair_order_form(extracted)
    if isinstance(st.session_state.get("warranty_audit_carry"), dict):
        st.session_state.warranty_audit_carry = carried_claim_identity(edited)
    has_manual = bool(manual and manual.get("chunks"))
    if st.button(
        "Check this document",
        type="primary",
        key="warranty_audit_run",
    ):
        with st.spinner("Checking the claim acknowledgement and the stored manual..."):
            try:
                result = run_audit(edited, list((manual or {}).get("chunks") or []))
            except LlmError as exc:
                st.warning(str(exc))
                result = {
                    "ro": edited,
                    "findings": [],
                    "summary": "The manual comparison did not finish. Fill in any blank fields and try the check again.",
                    "retrieved": [],
                    "manual_excerpt_count": 0,
                }
            except Exception as exc:
                st.error(f"The audit could not be completed. {exc}")
                return
        result["source_name"] = st.session_state.get("warranty_audit_extract_name") or names
        result["manual_id"] = (manual or {}).get("id")
        result["manual_filename"] = (manual or {}).get("filename") or ""
        result["audited_at"] = datetime.now(timezone.utc).isoformat()
        st.session_state.warranty_audit_result = result
        st.session_state.pop("warranty_audit_active_run_id", None)
        st.session_state.pop("warranty_audit_saved_label", None)
        st.rerun()
    if has_manual:
        st.caption(
            "Reynolds Ignite claim-acknowledgement fields are always checked. "
            "A manual finding is added only when the stored manual contains the quoted sentence."
        )
    else:
        st.caption(
            "This checks the Reynolds Ignite claim-acknowledgement fields. "
            "Store a warranty manual to also compare against manual text."
        )


def _note_height(value: object) -> int:
    """Give a copied narrative enough room to read without typing it again."""
    text = str(value or "")
    lines = text.count("\n") + 1
    if len(text) > 180:
        lines = max(lines, min(18, len(text) // 90))
    return max(96, min(420, lines * 24))


def _repair_order_form(extracted: dict) -> dict:
    token = st.session_state.get("warranty_audit_form_token") or "ro"
    st.markdown("##### What was read")
    st.caption(
        "Change only a field that does not match the paper. "
        "Pre-tax and the owner's name stay blank. List number is printed on the acknowledgement. "
        "A plus sign next to a job number is a warranty add-on and needs your signature."
    )
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
    claim = _claim_acknowledgement_fields(extracted, token)
    concern = st.text_area(
        "Concern",
        value=extracted.get("customer_concern") or "",
        height=_note_height(extracted.get("customer_concern")),
        key=f"{token}_concern",
    )
    cause = st.text_area(
        "Cause",
        value=extracted.get("cause") or "",
        height=_note_height(extracted.get("cause")),
        key=f"{token}_cause",
    )
    correction = st.text_area(
        "Correction",
        value=extracted.get("correction") or "",
        height=_note_height(extracted.get("correction")),
        key=f"{token}_correction",
    )
    tech_notes = st.text_area(
        "Tech notes",
        value=extracted.get("tech_notes") or "",
        height=_note_height(extracted.get("tech_notes") or extracted.get("cause")),
        key=f"{token}_tech_notes",
        help="The technician's story: what was found, the tests, and the repair. These notes have to justify the job.",
    )

    st.markdown("##### Labor operations")
    st.caption("Mark Add-on yes when a small plus sign is printed next to that job number.")
    labor = st.data_editor(
        _frame(_labor_for_editor(extracted.get("labor_operations")), _LABOR_COLUMNS),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"{token}_labor",
        column_config={
            "ro_number": "RO #",
            "job_number": "Job #",
            "op_code": "LOP",
            "description": "Description",
            "failure_code": "Failure code",
            "hours": "Hours",
            "tech_number": "Tech #",
            "add_on": "Add-on (+)",
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
            "ro_number": "RO #",
            "part_number": "Part #",
            "description": "Description",
            "quantity": "Qty",
            "failed": "Failed (yes/no)",
        },
    )
    signatures = extracted.get("signatures") or {}
    s1, s2, s3, s4 = st.columns(4)
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
    with s4:
        manager_sig = st.selectbox(
            "Your signature",
            _SIG_OPTIONS,
            index=_sig_index(signatures.get("service_manager")),
            key=f"{token}_sig_manager",
            help="Required on a warranty add-on, the job with a plus sign next to the job number.",
        )
    notes = st.text_area(
        "Other notes visible on the RO",
        value=extracted.get("other_visible_notes") or "",
        height=_note_height(extracted.get("other_visible_notes")),
        key=f"{token}_notes",
    )
    labor_rows = _records(labor, _LABOR_COLUMNS)
    part_rows = _records(parts, _PART_COLUMNS)
    totals = claim.pop("_totals", [])
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
        "tech_notes": tech_notes,
        "labor_operations": labor_rows,
        "time_punches": _records(punches, _PUNCH_COLUMNS),
        "parts": part_rows,
        "repair_orders": _repair_blocks(labor_rows, part_rows, totals, ro_number, claim.get("technician_name") or ""),
        "signatures": {
            "customer": customer_sig,
            "advisor": advisor_sig,
            "technician": tech_sig,
            "service_manager": manager_sig,
        },
        "other_visible_notes": notes,
        "unreadable": extracted.get("unreadable") or [],
        **claim,
    }


def _claim_acknowledgement_fields(extracted: dict, token: str) -> dict:
    """Fields printed on an FCA Global Claim Acknowledgement from Reynolds Ignite."""
    expanded = extracted.get("document_type") == "claim_acknowledgement"
    with st.expander("Claim acknowledgement fields", expanded=expanded):
        st.caption(
            "These are the boxes on a paid FCA claim acknowledgement. "
            "Owner's name and pre-tax total are left blank. List number is printed on the acknowledgement."
        )
        doc_label = st.selectbox(
            "Document",
            _DOC_OPTIONS,
            index=1 if expanded else 0,
            key=f"{token}_doc",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            claim_number = st.text_input("Claim number", value=extracted.get("claim_number") or "", key=f"{token}_claim")
            dealer_code = st.text_input("Dealer", value=extracted.get("dealer_code") or "", key=f"{token}_dealer")
            claim_status = st.text_input("Status", value=extracted.get("claim_status") or "", key=f"{token}_status")
            authorization = st.text_input("Authorization", value=extracted.get("authorization") or "", key=f"{token}_auth")
        with c2:
            coverage = st.text_input("Warranty coverage", value=extracted.get("warranty_coverage") or "", key=f"{token}_cov")
            claim_type = st.text_input("Claim type", value=extracted.get("claim_type") or "", key=f"{token}_ctype")
            submission = st.text_input("Submission type", value=extracted.get("submission_type") or "", key=f"{token}_sub")
            continuation = st.text_input("Continuation", value=extracted.get("continuation") or "", key=f"{token}_cont")
        with c3:
            in_service = st.text_input("In service date", value=extracted.get("in_service_date") or "", key=f"{token}_insvc")
            received = st.text_input("Date received", value=extracted.get("date_received") or "", key=f"{token}_recv")
            completed = st.text_input("Date completed", value=extracted.get("date_completed") or "", key=f"{token}_done")
            advisor = st.text_input("Service advisor", value=extracted.get("service_advisor") or "", key=f"{token}_advisor")
        d1, d2, d3 = st.columns(3)
        with d1:
            owner = st.text_input(
                "Owner's name",
                value=extracted.get("owner_name") or "",
                key=f"{token}_owner",
                help="Left blank on the claim acknowledgement.",
            )
            vehicle = st.text_input("Vehicle description", value=extracted.get("vehicle_description") or "", key=f"{token}_vehicle")
        with d2:
            list_number = st.text_input(
                "List number",
                value=extracted.get("list_number") or "",
                key=f"{token}_list",
                help="Printed on the claim acknowledgement, such as 2025123.",
            )
            reference = st.text_input("Reference number", value=extracted.get("reference_number") or "", key=f"{token}_ref")
        with d3:
            process_date = st.text_input("Process date", value=extracted.get("process_date") or "", key=f"{token}_process")
            tech_name = st.text_input("Technician name", value=extracted.get("technician_name") or "", key=f"{token}_techname")
        totals = st.data_editor(
            _frame(extracted.get("repair_orders") or [], _TOTAL_COLUMNS),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"{token}_totals",
            column_config={
                "ro_number": "RO #",
                "technician_id": "Tech #",
                "technician_name": "Tech name",
                "total_parts": "Total parts",
                "total_labor": "Total labor",
                "total_special_service": "Special service",
                "pre_tax_total": st.column_config.TextColumn(
                    "Pre-tax total",
                    help="Left blank on these acknowledgements.",
                ),
            },
        )
    return {
        "document_type": "claim_acknowledgement" if doc_label == "FCA claim acknowledgement" else "repair_order",
        "dms": extracted.get("dms") or "",
        "claim_number": claim_number,
        "claim_status": claim_status,
        "dealer_code": dealer_code,
        "in_service_date": in_service,
        "warranty_coverage": coverage,
        "claim_type": claim_type,
        "submission_type": submission,
        "continuation": continuation,
        "date_received": received,
        "date_completed": completed,
        "process_date": process_date,
        "authorization": authorization,
        "owner_name": owner,
        "vehicle_description": vehicle,
        "service_advisor": advisor,
        "list_number": list_number,
        "reference_number": reference,
        "prior_claim": extracted.get("prior_claim") or "",
        "technician_name": tech_name,
        "_totals": _records(totals, _TOTAL_COLUMNS),
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
            "Claim-acknowledgement fields come from the Reynolds Ignite printout. Manual items also quote the stored manual.",
        ),
        unsafe_allow_html=True,
    )
    saved_label = st.session_state.get("warranty_audit_saved_label")
    if st.session_state.get("warranty_audit_active_run_id"):
        st.info(f"Viewing saved audit{f' for RO {saved_label}' if saved_label else ''}.")
    flash = st.session_state.pop("warranty_audit_flash", None)
    if flash == "saved":
        st.success("Audit saved. It is listed below and on Reports. Use Next repair order when you are ready for the next one.")
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
    if st.session_state.get("warranty_audit_active_run_id"):
        st.caption("The next repair order keeps this RO number and claim number. Change them if they are different.")
        if st.button("Next repair order", type="primary", use_container_width=True, key="warranty_audit_next"):
            _start_next_repair_order(result)
            st.rerun()


def carried_claim_identity(repair_order: dict | None) -> dict:
    """RO number and claim number to keep for the next repair order."""
    order = repair_order if isinstance(repair_order, dict) else {}
    return {
        "ro_number": str(order.get("ro_number") or "").strip(),
        "claim_number": str(order.get("claim_number") or "").strip(),
    }


def apply_carried_numbers(extracted: dict, carry: dict | None) -> list[str]:
    """Keep the saved RO number and claim number. The new pictures fill everything else."""
    if not isinstance(extracted, dict) or not isinstance(carry, dict):
        return []
    notes = []
    kept_ro = str(carry.get("ro_number") or "").strip()
    kept_claim = str(carry.get("claim_number") or "").strip()
    read_ro = str(extracted.get("ro_number") or "").strip()
    read_claim = str(extracted.get("claim_number") or "").strip()
    if kept_ro:
        if read_ro and read_ro.casefold() != kept_ro.casefold():
            notes.append(
                f"The pictures show RO {read_ro}. This form kept RO {kept_ro}. "
                "Change the RO number if this one is different."
            )
        extracted["ro_number"] = kept_ro
    if kept_claim:
        if read_claim and read_claim.casefold() != kept_claim.casefold():
            notes.append(
                f"The pictures show claim {read_claim}. This form kept claim {kept_claim}. "
                "Change the claim number if this one is different."
            )
        extracted["claim_number"] = kept_claim
    return notes


def _render_carried_numbers() -> None:
    carry = st.session_state.get("warranty_audit_carry")
    if not isinstance(carry, dict):
        return
    st.success("Ready for the next repair order. The RO number and claim number were kept.")
    generation = int(st.session_state.get("warranty_audit_photo_generation") or 0)
    first, second = st.columns(2)
    with first:
        ro_number = st.text_input(
            "RO number",
            value=str(carry.get("ro_number") or ""),
            key=f"warranty_audit_carry_ro_{generation}",
        )
    with second:
        claim_number = st.text_input(
            "Claim number",
            value=str(carry.get("claim_number") or ""),
            key=f"warranty_audit_carry_claim_{generation}",
        )
    st.caption("These usually stay the same. Change them if this repair order is different, then add the pictures.")
    st.session_state.warranty_audit_carry = {
        "ro_number": ro_number.strip(),
        "claim_number": claim_number.strip(),
    }


def _start_next_repair_order(result: dict) -> None:
    """Clear the audit that was just saved and keep its RO number and claim number."""
    ro = (result or {}).get("ro") if isinstance(result, dict) else {}
    tray = list(st.session_state.get("warranty_audit_photo_tray") or [])
    ignored = list(st.session_state.get("warranty_audit_ignored_shas") or [])
    for item in tray:
        for key in ("sha", "raw_sha"):
            value = str((item or {}).get(key) or "")
            if value and value not in ignored:
                ignored.append(value)
    st.session_state.warranty_audit_carry = carried_claim_identity(ro)
    st.session_state.warranty_audit_ignored_shas = ignored
    st.session_state.warranty_audit_photo_generation = int(
        st.session_state.get("warranty_audit_photo_generation") or 0
    ) + 1
    st.session_state.warranty_audit_photo_tray = []
    st.session_state.warranty_audit_photo_warnings = []
    for key in (
        "warranty_audit_extract",
        "warranty_audit_extract_digest",
        "warranty_audit_extract_name",
        "warranty_audit_read_warnings",
        "warranty_audit_result",
        "warranty_audit_active_run_id",
        "warranty_audit_saved_label",
        "warranty_audit_form_token",
    ):
        st.session_state.pop(key, None)
    clear_live_photos()


def _without_ignored(incoming: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    ignored = set(st.session_state.get("warranty_audit_ignored_shas") or [])
    if not ignored:
        return incoming
    kept = []
    for name, raw in incoming:
        if hashlib.sha256(raw).hexdigest() in ignored:
            continue
        kept.append((name, raw))
    return kept


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


def _incoming_photos(upload) -> list[tuple[str, bytes]]:
    photos: list[tuple[str, bytes]] = []
    uploads = upload if isinstance(upload, list) else ([] if upload is None else [upload])
    for index, item in enumerate(uploads, start=1):
        if item is None:
            continue
        photos.append((item.name or f"phone-photo-{index}.jpg", item.getvalue()))
    return photos


def _show_photo_tray(tray: list[dict]) -> None:
    st.caption("Pictures on this claim")
    columns = st.columns(3)
    for index, item in enumerate(tray):
        with columns[index % 3]:
            if not _show_one_photo(item["data"], f"{index + 1}. {item['name']}"):
                st.caption(f"{index + 1}. {item['name']} could not be shown. Remove it and take that page again.")
            if st.button("Remove", key=f"warranty_audit_remove_{item['sha'][:12]}", use_container_width=True):
                kept = [photo for photo in tray if photo["sha"] != item["sha"]]
                st.session_state.warranty_audit_photo_tray = kept
                delete_live_photo(item["sha"])
                st.rerun()
    if st.button("Remove all pictures", key="warranty_audit_clear_photos"):
        st.session_state.warranty_audit_photo_tray = []
        st.session_state.warranty_audit_photo_warnings = []
        clear_live_photos()
        st.rerun()


@st.fragment(run_every=timedelta(seconds=2))
def _watch_phone_photos() -> None:
    """Pull pictures the phone just saved so the desktop shows them without a refresh."""
    tray = list(st.session_state.get("warranty_audit_photo_tray") or [])
    merged, err = fetch_live_photos(tray)
    if err:
        st.caption(err)
        return
    if [item.get("sha") for item in merged] != [item.get("sha") for item in tray]:
        st.session_state.warranty_audit_photo_tray = merged
        st.rerun(scope="app")


def _show_one_photo(data: bytes, caption: str) -> bool:
    """Show a picture without letting one bad file crash the page."""
    try:
        from PIL import Image

        with Image.open(io_bytes(data)) as image:
            image.load()
        st.image(data, caption=caption, width=180)
        return True
    except Exception:
        return False


def io_bytes(data: bytes | None = None):
    import io

    return io.BytesIO() if data is None else io.BytesIO(data)


def _repair_blocks(labor_rows, part_rows, totals, ro_number: str, tech_name: str) -> list[dict]:
    if not totals:
        return []
    single = len(totals) == 1

    def take(lines, number: str) -> list[dict]:
        if single:
            return lines
        return [line for line in lines if (line.get("ro_number") or "") == number]

    blocks = []
    for row in totals:
        number = row.get("ro_number") or (ro_number if single else "")
        blocks.append({
            "ro_number": number,
            "technician_id": row.get("technician_id") or "",
            "technician_name": row.get("technician_name") or tech_name,
            "total_parts": row.get("total_parts") or "",
            "total_labor": row.get("total_labor") or "",
            "total_special_service": row.get("total_special_service") or "",
            "pre_tax_total": row.get("pre_tax_total") or "",
            "labor_lines": take(labor_rows, row.get("ro_number") or ""),
            "part_lines": take(part_rows, row.get("ro_number") or ""),
        })
    return blocks


def _frame(rows, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows or []), columns=columns)
    return frame.fillna("")


def _labor_for_editor(lines) -> list[dict]:
    rows = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        add_on = line.get("add_on")
        job = str(line.get("job_number") or "")
        if add_on is True or str(add_on).strip().casefold() in {"true", "yes", "y", "+"} or "+" in job:
            label = "yes"
        elif add_on is False or str(add_on).strip().casefold() in {"false", "no", "n"}:
            label = "no"
        else:
            label = ""
        rows.append({column: line.get(column) or "" for column in _LABOR_COLUMNS if column != "add_on"} | {"add_on": label})
    return rows


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
                "ro_number": part.get("ro_number") or "",
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
