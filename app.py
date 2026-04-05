"""Streamlit Web UI for Contract Verification."""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import streamlit as st

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from contract_verifier.project_config import load_config, list_projects, PROJECTS_DIR
from contract_verifier.extract_reservation import extract_safe as extract_reservation_safe
from contract_verifier.extract_contract import extract as extract_contract
from contract_verifier.verify import verify
from contract_verifier.models import (
    CustomPaymentTerms,
    PaymentLine,
    PreContractPaymentLine,
    ReservationData,
    ReservationExtractionResult,
    VerificationReport,
)
from contract_verifier.extract_precontract import extract_safe as extract_precontract_safe
from contract_verifier.compute_precontract import (
    compute_precontract_table,
    compute_mortgage_table,
)

# Check if Google Drive packages are available
try:
    import google.oauth2.credentials  # noqa: F401
    import googleapiclient  # noqa: F401
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False

st.set_page_config(
    page_title="Contract Verifier",
    page_icon="📋",
    layout="wide",
)


# ============================================================
# Verification Page
# ============================================================
def render_verification_page():
    st.title("📋 Contract Verifier")
    st.markdown("Verify purchase contracts against reservation agreements")

    with st.sidebar:
        st.header("Verification Settings")

        projects = list_projects()
        if not projects:
            st.warning("No project configs found. Create one in the Project Configuration page.")
            return
        project_name = st.selectbox("Project", projects, index=0, key="v_project")

        st.divider()

        if DRIVE_AVAILABLE:
            use_drive = st.toggle("Fetch reservation from Google Drive", value=False)
        else:
            use_drive = False

        if use_drive:
            client_name = st.text_input("Client name", placeholder="e.g., נילי שטרן ביבר")
        else:
            reservation_file = st.file_uploader(
                "Upload reservation PDF",
                type=["pdf"],
                help="The reservation agreement PDF (source of truth)",
            )

        st.divider()

        contract_file = st.file_uploader(
            "Upload contract DOCX",
            type=["docx"],
            help="The purchase contract to verify",
        )

    # --- Phase 1: Extract documents ---
    extract_button = st.button("📄 Extract & Review", type="primary", use_container_width=True)

    if extract_button:
        if not contract_file:
            st.error("Please upload a contract DOCX file.")
            st.stop()

        if use_drive:
            if not client_name:
                st.error("Please enter the client name for Google Drive lookup.")
                st.stop()
        else:
            if not reservation_file:
                st.error("Please upload a reservation PDF file.")
                st.stop()

        with st.spinner("Extracting data from documents..."):
            try:
                config = load_config(project_name)

                with tempfile.TemporaryDirectory() as tmpdir:
                    contract_path = Path(tmpdir) / "contract.docx"
                    contract_path.write_bytes(contract_file.read())

                    if use_drive:
                        from contract_verifier.drive_fetch import fetch_reservation
                        reservation_path = fetch_reservation(project_name, client_name)
                    else:
                        reservation_path = Path(tmpdir) / "reservation.pdf"
                        reservation_path.write_bytes(reservation_file.read())
                        reservation_path = str(reservation_path)

                    extraction_result = extract_reservation_safe(str(reservation_path))
                    contract_data = extract_contract(str(contract_path))

                st.session_state["extraction_result"] = extraction_result
                st.session_state["contract_data"] = contract_data
                st.session_state["config"] = config
                # Clear any previous report
                st.session_state.pop("report", None)

            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

    # --- Phase 2: Review & edit reservation values ---
    if "extraction_result" in st.session_state and "report" not in st.session_state:
        extraction_result: ReservationExtractionResult = st.session_state["extraction_result"]
        failed_fields = extraction_result.failed_fields

        if extraction_result.has_warnings:
            st.warning(
                f"⚠️ {len(extraction_result.warnings)} field(s) could not be extracted automatically. "
                "Please fill in the missing values below."
            )
            for w in extraction_result.warnings:
                st.caption(f"**{w.field_name}**: {w.reason}")

        st.subheader("Review Reservation Data")
        st.markdown("Verify extracted values and correct any errors before running verification.")

        rd = extraction_result.data

        col1, col2 = st.columns(2)
        with col1:
            _field_label = "🔴 Client name" if "client_name" in failed_fields else "Client name"
            r_client_name = st.text_input(_field_label, value=rd.client_name, key="r_client_name")

            _field_label = "🔴 Apartment number" if "apartment_number" in failed_fields else "Apartment number"
            r_apartment = st.text_input(_field_label, value=rd.apartment_number, key="r_apartment")

            _field_label = "🔴 Floor" if "floor" in failed_fields else "Floor"
            r_floor = st.text_input(_field_label, value=rd.floor, key="r_floor")

            _field_label = "🔴 Project name" if "project_name" in failed_fields else "Project name"
            r_project = st.text_input(_field_label, value=rd.project_name, key="r_project")

        with col2:
            _field_label = "🔴 Area (sqm)" if "area_gross_sqm" in failed_fields else "Area (sqm)"
            r_area = st.number_input(
                _field_label, value=rd.area_gross_sqm, min_value=0.0, step=0.01,
                format="%.2f", key="r_area",
            )

            _field_label = "🔴 Price without costs (€)" if "price_without_costs" in failed_fields else "Price without costs (€)"
            r_price_base = st.number_input(
                _field_label, value=rd.price_without_costs, min_value=0.0, step=1.0,
                format="%.0f", key="r_price_base",
            )

            _field_label = "🔴 Price with costs (€)" if "price_with_costs" in failed_fields else "Price with costs (€)"
            r_price_total = st.number_input(
                _field_label, value=rd.price_with_costs, min_value=0.0, step=1.0,
                format="%.0f", key="r_price_total",
            )

            _field_label = "🔴 Registration fee (€)" if "registration_fee" in failed_fields else "Registration fee (€)"
            r_reg_fee = st.number_input(
                _field_label, value=rd.registration_fee, min_value=0.0, step=100.0,
                format="%.0f", key="r_reg_fee",
            )

        # --- Custom Payment Terms ---
        st.divider()
        config = st.session_state["config"]
        use_custom = st.checkbox("Client has custom payment terms", key="use_custom_payment")

        custom_payment = None
        if use_custom:
            st.subheader("Custom Payment Terms")
            st.caption("Defaults loaded from project config. Change only what differs for this client.")

            col1, col2 = st.columns(2)
            with col1:
                cpt_reg_fee = st.number_input(
                    "Registration fee (€)", value=float(config.registration_fee),
                    min_value=0.0, step=100.0, format="%.0f", key="cpt_reg_fee",
                )
            with col2:
                cpt_surcharge = st.number_input(
                    "Surcharge percentage", value=float(config.surcharge_percentage),
                    min_value=0.0, step=0.1, format="%.1f", key="cpt_surcharge",
                )

            st.markdown("**Payment Lines**")

            # Initialize custom payment lines from config defaults
            if "cpt_line_count" not in st.session_state:
                st.session_state["cpt_line_count"] = len(config.expected_payment_lines)

            num_cpt_lines = st.session_state["cpt_line_count"]
            cpt_lines = []

            for i in range(num_cpt_lines):
                # Defaults from config
                default_name = config.expected_payment_lines[i].name if i < len(config.expected_payment_lines) else ""
                default_pct = float(config.expected_payment_lines[i].percentage) if i < len(config.expected_payment_lines) else 0.0

                col1, col2, col3, col4, col5 = st.columns([2, 1, 1.5, 1.5, 0.5])
                with col1:
                    cpt_name = st.text_input(
                        f"Line {i+1} name", value=default_name, key=f"cpt_name_{i}",
                        label_visibility="collapsed", placeholder="Payment name",
                    )
                with col2:
                    cpt_pct = st.number_input(
                        f"Line {i+1} %", value=default_pct,
                        min_value=0.0, step=1.0, format="%.0f", key=f"cpt_pct_{i}",
                        label_visibility="collapsed",
                    )
                with col3:
                    cpt_base = st.number_input(
                        f"Line {i+1} base €", value=0.0,
                        min_value=0.0, step=1.0, format="%.0f", key=f"cpt_base_{i}",
                        label_visibility="collapsed",
                    )
                with col4:
                    cpt_surcharge_amt = st.number_input(
                        f"Line {i+1} w/surcharge €", value=0.0,
                        min_value=0.0, step=1.0, format="%.0f", key=f"cpt_surcharge_{i}",
                        label_visibility="collapsed",
                    )
                with col5:
                    if st.button("🗑️", key=f"cpt_del_{i}"):
                        st.session_state["cpt_line_count"] = max(0, num_cpt_lines - 1)
                        st.rerun()

                cpt_lines.append(PaymentLine(
                    name=cpt_name,
                    percentage=cpt_pct,
                    base_amount=cpt_base,
                    amount_with_surcharge=cpt_surcharge_amt,
                ))

            col_add, col_spacer = st.columns([1, 3])
            with col_add:
                if st.button("+ Add Payment Line", key="cpt_add_line"):
                    st.session_state["cpt_line_count"] = num_cpt_lines + 1
                    st.rerun()

            # Validation
            cpt_pct_sum = sum(pl.percentage for pl in cpt_lines)
            if math.isclose(cpt_pct_sum, 100.0, abs_tol=0.01):
                st.success(f"Custom payment lines sum: {cpt_pct_sum:.0f}% = 100%")
            else:
                st.warning(f"Custom payment lines sum: {cpt_pct_sum:.0f}% (expected 100%)")

            custom_payment = CustomPaymentTerms(
                registration_fee=cpt_reg_fee,
                surcharge_percentage=cpt_surcharge,
                payment_lines=cpt_lines,
            )

        # --- Phase 3: Confirm and run verification ---
        if st.button("🔍 Confirm & Run Verification", type="primary", use_container_width=True):
            reservation_data = ReservationData(
                client_name=r_client_name,
                apartment_number=r_apartment,
                floor=r_floor,
                area_gross_sqm=r_area,
                price_without_costs=r_price_base,
                price_with_costs=r_price_total,
                registration_fee=r_reg_fee,
                project_name=r_project,
            )
            contract_data = st.session_state["contract_data"]

            report = verify(reservation_data, contract_data, config, custom_payment)
            st.session_state["report"] = report
            st.session_state["reservation_data"] = reservation_data
            st.session_state["used_custom_payment"] = custom_payment is not None
            st.rerun()

    # --- Display Report ---
    if "report" in st.session_state:
        report: VerificationReport = st.session_state["report"]
        reservation_data = st.session_state["reservation_data"]
        contract_data = st.session_state["contract_data"]

        total = len(report.results)
        failures = [r for r in report.results if not r.passed]

        if not failures:
            st.success(f"ALL {total} CHECKS PASSED")
        else:
            st.error(f"{len(failures)} CHECK(S) FAILED out of {total}")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Reservation Data")
            st.markdown(f"""
| Field | Value |
|---|---|
| **Client** | {reservation_data.client_name} |
| **Apartment** | {reservation_data.apartment_number} |
| **Floor** | {reservation_data.floor} |
| **Area** | {reservation_data.area_gross_sqm} sqm |
| **Price (no costs)** | €{reservation_data.price_without_costs:,.0f} |
| **Price (with costs)** | €{reservation_data.price_with_costs:,.0f} |
| **Registration fee** | €{reservation_data.registration_fee:,.0f} |
""")

        with col2:
            st.subheader("Contract Data")
            st.markdown(f"""
| Field | Value |
|---|---|
| **Client** | {contract_data.client_name} |
| **Apartment** | {contract_data.apartment_number} |
| **Floor** | {contract_data.floor} |
| **Area** | {contract_data.area_gross_sqm} sqm |
| **Total price** | €{contract_data.total_purchase_price:,.0f} |
| **Costs** | {contract_data.total_costs_percentage}% |
| **Registration fee** | €{contract_data.registration_fee:,.0f} |
| **Remaining** | €{contract_data.remaining_after_registration:,.0f} |
| **Surcharge** | {contract_data.surcharge_percentage}% |
""")

        st.divider()

        used_custom = st.session_state.get("used_custom_payment", False)

        categories = {
            "cross_document": "Cross-Document Checks (Reservation vs Contract)",
        }
        if used_custom:
            categories["custom_terms"] = "Custom Terms Validation (Contract vs Custom Payment Terms)"
        else:
            categories["config_validation"] = "Config Validation (Contract vs Project Config)"
        categories["internal_math"] = "Internal Math Checks"

        for cat_key, cat_title in categories.items():
            cat_results = [r for r in report.results if r.category == cat_key]
            if not cat_results:
                continue

            st.subheader(cat_title)

            for r in cat_results:
                if r.passed:
                    st.markdown(f"✅ **{r.check_name}** — Expected: `{r.expected}` | Actual: `{r.actual}`")
                else:
                    st.markdown(f"❌ **{r.check_name}** — Expected: `{r.expected}` | Actual: `{r.actual}`")

            st.divider()

        if contract_data.payment_lines:
            st.subheader("Payment Schedule")
            payment_data = []
            for pl in contract_data.payment_lines:
                payment_data.append({
                    "Payment": pl.name,
                    "Percentage": f"{pl.percentage}%",
                    "Base Amount": f"€{pl.base_amount:,.0f}",
                    "With Surcharge": f"€{pl.amount_with_surcharge:,.0f}",
                    "Notes": (pl.notes[:60] + "...") if len(pl.notes) > 60 else pl.notes,
                })
            st.table(payment_data)


# ============================================================
# Project Configuration Page
# ============================================================
def render_config_page():
    st.title("⚙️ Project Configuration")
    st.markdown("Create and edit project financial configurations")

    # Admin password protection
    try:
        admin_pw = st.secrets.get("ADMIN_PASSWORD", None)
    except FileNotFoundError:
        admin_pw = None
    if admin_pw:
        if "admin_authenticated" not in st.session_state:
            st.session_state["admin_authenticated"] = False

        if not st.session_state["admin_authenticated"]:
            entered = st.text_input("Admin password", type="password", key="admin_pw_input")
            if st.button("Login", key="admin_login"):
                if entered == admin_pw:
                    st.session_state["admin_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
            return

    with st.sidebar:
        st.header("Select Project")

        # Build project list with "Create New" option
        existing = _list_config_files()
        options = ["+ Create New Project"] + existing
        selection = st.selectbox("Project config", options, key="cfg_select")

    if selection == "+ Create New Project":
        _render_new_project()
    else:
        _render_edit_project(selection)


def _list_config_files() -> list[str]:
    """List config filenames (without _template)."""
    files = []
    for p in sorted(PROJECTS_DIR.glob("*.json")):
        if not p.name.startswith("_"):
            files.append(p.stem)
    return files


def _load_raw_config(name: str) -> dict:
    """Load a raw JSON config dict."""
    path = PROJECTS_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_template() -> dict:
    """Load the _template.json."""
    path = PROJECTS_DIR / "_template.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(name: str, data: dict):
    """Save config dict to projects/<name>.json."""
    path = PROJECTS_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _render_new_project():
    st.subheader("Create New Project")

    new_name = st.text_input("Project file name (no extension)", placeholder="e.g., peraia")

    if st.button("Create from Template", type="primary"):
        if not new_name:
            st.error("Please enter a project file name.")
            return
        # Check if already exists
        target = PROJECTS_DIR / f"{new_name}.json"
        if target.exists():
            st.error(f"Project '{new_name}' already exists. Select it from the dropdown to edit.")
            return
        template = _load_template()
        _save_config(new_name, template)
        st.success(f"Created projects/{new_name}.json from template. Select it from the dropdown to edit.")
        st.rerun()

    st.info("After creating, select the new project from the sidebar dropdown to configure it.")


def _render_edit_project(name: str):
    data = _load_raw_config(name)

    st.subheader(f"Editing: {name}.json")

    # --- Basic Info ---
    st.markdown("### Project Identity")
    col1, col2 = st.columns(2)
    with col1:
        data["project_name"] = st.text_input(
            "Project name (Hebrew)", value=data.get("project_name", ""), key="cfg_pname"
        )
    with col2:
        variants_str = st.text_input(
            "Name variants (comma-separated)",
            value=", ".join(data.get("project_name_variants", [])),
            key="cfg_variants",
        )
        data["project_name_variants"] = [v.strip() for v in variants_str.split(",") if v.strip()]

    st.divider()

    # --- Cost Structure ---
    st.markdown("### Cost Structure")
    cost = data.setdefault("cost_structure", {})

    col1, col2 = st.columns(2)
    with col1:
        cost["total_costs_percentage"] = st.number_input(
            "Total costs percentage", value=float(cost.get("total_costs_percentage", 0)),
            min_value=0.0, step=0.01, format="%.2f", key="cfg_total_cost_pct",
        )
    with col2:
        calc_options = ["price_without_costs", "total_price"]
        current_calc = cost.get("costs_calculated_on", "price_without_costs")
        idx = calc_options.index(current_calc) if current_calc in calc_options else 0
        cost["costs_calculated_on"] = st.selectbox(
            "Costs calculated on", calc_options, index=idx, key="cfg_cost_base",
        )

    # Cost lines
    st.markdown("**Cost Lines**")
    cost_lines = cost.setdefault("cost_lines", [])

    # Initialize session state for cost lines count
    if "cfg_cost_line_count" not in st.session_state:
        st.session_state["cfg_cost_line_count"] = len(cost_lines)

    num_cost_lines = st.session_state["cfg_cost_line_count"]

    # Ensure we have enough entries in cost_lines
    while len(cost_lines) < num_cost_lines:
        cost_lines.append({"name": "", "percentage": 0.0})

    updated_cost_lines = []
    for i in range(num_cost_lines):
        cl = cost_lines[i] if i < len(cost_lines) else {"name": "", "percentage": 0.0}
        col1, col2, col3 = st.columns([3, 1, 0.5])
        with col1:
            cl_name = st.text_input(
                f"Cost line {i+1} name", value=cl.get("name", ""), key=f"cl_name_{i}",
                label_visibility="collapsed", placeholder="Cost line name",
            )
        with col2:
            cl_pct = st.number_input(
                f"Cost line {i+1} %", value=float(cl.get("percentage", 0)),
                min_value=0.0, step=0.01, format="%.2f", key=f"cl_pct_{i}",
                label_visibility="collapsed",
            )
        with col3:
            if st.button("🗑️", key=f"cl_del_{i}"):
                st.session_state["cfg_cost_line_count"] = max(0, num_cost_lines - 1)
                # Remove this line
                if i < len(cost_lines):
                    cost_lines.pop(i)
                st.rerun()
        updated_cost_lines.append({"name": cl_name, "percentage": cl_pct})

    col_add, col_spacer = st.columns([1, 3])
    with col_add:
        if st.button("+ Add Cost Line", key="add_cost_line"):
            st.session_state["cfg_cost_line_count"] = num_cost_lines + 1
            st.rerun()

    cost["cost_lines"] = updated_cost_lines

    # Cost validation
    cost_sum = sum(cl["percentage"] for cl in updated_cost_lines)
    if math.isclose(cost_sum, cost["total_costs_percentage"], abs_tol=0.01):
        st.success(f"Cost lines sum: {cost_sum:.2f}% = {cost['total_costs_percentage']}%")
    else:
        st.error(f"Cost lines sum: {cost_sum:.2f}% (expected {cost['total_costs_percentage']}%)")

    st.divider()

    # --- Payment Structure ---
    st.markdown("### Payment Structure")
    payment = data.setdefault("payment_structure", {})

    col1, col2, col3 = st.columns(3)
    with col1:
        payment["registration_fee"] = st.number_input(
            "Registration fee (€)", value=float(payment.get("registration_fee", 2000)),
            min_value=0.0, step=100.0, format="%.0f", key="cfg_reg_fee",
        )
    with col2:
        payment["surcharge_percentage"] = st.number_input(
            "Surcharge percentage", value=float(payment.get("surcharge_percentage", 2.0)),
            min_value=0.0, step=0.1, format="%.1f", key="cfg_surcharge_pct",
        )
    with col3:
        calc_options_p = ["total_minus_registration"]
        payment["payments_calculated_on"] = st.selectbox(
            "Payments calculated on", calc_options_p, index=0, key="cfg_pay_base",
        )

    # Surcharge breakdown
    breakdown = payment.setdefault("surcharge_breakdown", {})
    col1, col2 = st.columns(2)
    with col1:
        breakdown["clearshift_fee"] = st.number_input(
            "Clearshift fee %", value=float(breakdown.get("clearshift_fee", 0.5)),
            min_value=0.0, step=0.1, format="%.1f", key="cfg_clearshift",
        )
    with col2:
        breakdown["security_buffer"] = st.number_input(
            "Security buffer %", value=float(breakdown.get("security_buffer", 1.5)),
            min_value=0.0, step=0.1, format="%.1f", key="cfg_security",
        )

    # Payment lines
    st.markdown("**Payment Lines**")
    payment_lines = payment.setdefault("payment_lines", [])

    if "cfg_payment_line_count" not in st.session_state:
        st.session_state["cfg_payment_line_count"] = len(payment_lines)

    num_payment_lines = st.session_state["cfg_payment_line_count"]

    while len(payment_lines) < num_payment_lines:
        payment_lines.append({"name": "", "percentage": 0.0, "destination": "escrow", "timing": ""})

    updated_payment_lines = []
    for i in range(num_payment_lines):
        pl = payment_lines[i] if i < len(payment_lines) else {"name": "", "percentage": 0.0, "destination": "escrow", "timing": ""}
        col1, col2, col3, col4, col5 = st.columns([2, 1, 1.5, 2, 0.5])
        with col1:
            pl_name = st.text_input(
                f"Payment {i+1} name", value=pl.get("name", ""), key=f"pl_name_{i}",
                label_visibility="collapsed", placeholder="Payment name",
            )
        with col2:
            pl_pct = st.number_input(
                f"Payment {i+1} %", value=float(pl.get("percentage", 0)),
                min_value=0.0, step=1.0, format="%.0f", key=f"pl_pct_{i}",
                label_visibility="collapsed",
            )
        with col3:
            dest_options = ["company_bank", "escrow"]
            current_dest = pl.get("destination", "escrow")
            dest_idx = dest_options.index(current_dest) if current_dest in dest_options else 1
            pl_dest = st.selectbox(
                f"Payment {i+1} dest", dest_options, index=dest_idx, key=f"pl_dest_{i}",
                label_visibility="collapsed",
            )
        with col4:
            pl_timing = st.text_input(
                f"Payment {i+1} timing", value=pl.get("timing", ""), key=f"pl_timing_{i}",
                label_visibility="collapsed", placeholder="Timing",
            )
        with col5:
            if st.button("🗑️", key=f"pl_del_{i}"):
                st.session_state["cfg_payment_line_count"] = max(0, num_payment_lines - 1)
                if i < len(payment_lines):
                    payment_lines.pop(i)
                st.rerun()
        updated_payment_lines.append({
            "name": pl_name, "percentage": pl_pct,
            "destination": pl_dest, "timing": pl_timing,
        })

    col_add, col_spacer = st.columns([1, 3])
    with col_add:
        if st.button("+ Add Payment Line", key="add_payment_line"):
            st.session_state["cfg_payment_line_count"] = num_payment_lines + 1
            st.rerun()

    payment["payment_lines"] = updated_payment_lines

    # Payment validation
    payment_sum = sum(pl["percentage"] for pl in updated_payment_lines)
    if math.isclose(payment_sum, 100.0, abs_tol=0.01):
        st.success(f"Payment lines sum: {payment_sum:.0f}% = 100%")
    else:
        st.error(f"Payment lines sum: {payment_sum:.0f}% (expected 100%)")

    st.divider()

    # --- Tolerances ---
    st.markdown("### Tolerances")
    col1, col2 = st.columns(2)
    with col1:
        data["rounding_tolerance_eur"] = st.number_input(
            "Rounding tolerance (€)", value=float(data.get("rounding_tolerance_eur", 1.0)),
            min_value=0.0, step=0.5, format="%.1f", key="cfg_tol_eur",
        )
    with col2:
        data["area_tolerance_sqm"] = st.number_input(
            "Area tolerance (sqm)", value=float(data.get("area_tolerance_sqm", 0.01)),
            min_value=0.0, step=0.01, format="%.2f", key="cfg_tol_area",
        )

    st.divider()

    # --- Save ---
    if st.button("💾 Save Configuration", type="primary", use_container_width=True):
        # Remove internal keys
        data.pop("_comment", None)
        data.pop("_instructions", None)
        _save_config(name, data)
        st.success(f"Saved to projects/{name}.json")


# ============================================================
# Pre-Contract Info Page
# ============================================================
def render_precontract_page():
    st.title("📄 Pre-Contract Info")
    st.markdown("Extract payment details from a signed contract and build pre-contract payment table")

    with st.sidebar:
        st.header("Pre-Contract Settings")
        available_projects = list_projects()
        project_options = ["—"] + available_projects
        selected_project = st.selectbox(
            "Project", project_options, index=0, key="pc_project"
        )

        contract_pdf = st.file_uploader(
            "Upload signed contract PDF",
            type=["pdf"],
            key="pc_contract_upload",
        )

    # --- Phase 1: Extract ---
    if contract_pdf is not None and "pc_extraction" not in st.session_state:
        if st.button("🔍 Extract / חלץ נתונים", key="pc_extract_btn"):
            with st.spinner("Extracting data from contract PDF (OCR may take a moment)..."):
                try:
                    pc_config = None
                    if selected_project != "—":
                        try:
                            pc_config = load_config(selected_project)
                        except ValueError:
                            pass
                    with tempfile.TemporaryDirectory() as tmpdir:
                        pdf_path = Path(tmpdir) / "contract.pdf"
                        pdf_path.write_bytes(contract_pdf.read())
                        result = extract_precontract_safe(str(pdf_path), config=pc_config)
                        st.session_state["pc_extraction"] = result
                        st.rerun()
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    return

    if "pc_extraction" not in st.session_state:
        st.info("Upload a signed contract PDF and click Extract to begin.")
        return

    result = st.session_state["pc_extraction"]
    d = result.data
    failed = result.failed_fields

    if result.has_warnings:
        st.warning(
            f"⚠️ {len(result.warnings)} field(s) could not be extracted and need manual input: "
            + ", ".join(w.field_name for w in result.warnings)
        )

    # Reset button
    if st.button("🔄 Reset / Start Over", key="pc_reset"):
        for key in list(st.session_state.keys()):
            if key.startswith("pc_"):
                del st.session_state[key]
        st.rerun()

    # --- Phase 2: Editable commercial terms ---
    st.subheader("Commercial Terms / פרטים מסחריים")

    col1, col2 = st.columns(2)
    with col1:
        _lbl = "🔴 Client name" if "client_name" in failed else "Client name"
        pc_client = st.text_input(_lbl, value=d.client_name, key="pc_client_name")

        _lbl = "🔴 Apartment" if "apartment_number" in failed else "Apartment"
        pc_apt = st.text_input(_lbl, value=d.apartment_number, key="pc_apartment")

        _lbl = "🔴 Delivery date" if "delivery_date" in failed else "Delivery date"
        pc_delivery = st.text_input(_lbl, value=d.delivery_date, key="pc_delivery_date")

        _lbl = "🔴 Late delivery (€/month)" if "late_delivery_payment" in failed else "Late delivery (€/month)"
        pc_late = st.number_input(_lbl, value=d.late_delivery_payment, min_value=0.0, step=100.0, key="pc_late_delivery")

    with col2:
        _lbl = "🔴 Purchase price (€)" if "purchase_price" in failed else "Purchase price (€)"
        pc_price = st.number_input(_lbl, value=d.purchase_price, min_value=0.0, step=1000.0, key="pc_purchase_price")

        _lbl = "🔴 Total with costs (€)" if "total_with_costs" in failed else "Total with costs (€)"
        pc_total = st.number_input(_lbl, value=d.total_with_costs, min_value=0.0, step=1000.0, key="pc_total_costs")

        _lbl = "🔴 Gross SQM" if "gross_sqm" in failed else "Gross SQM"
        pc_sqm = st.number_input(_lbl, value=d.gross_sqm, min_value=0.0, step=0.5, key="pc_gross_sqm")

        _lbl = "🔴 Balcony SQM" if "balcony_sqm" in failed else "Balcony SQM"
        pc_balcony = st.number_input(_lbl, value=d.balcony_sqm, min_value=0.0, step=0.5, key="pc_balcony_sqm")

    bcol1, bcol2, bcol3 = st.columns(3)
    with bcol1:
        pc_mortgage = st.checkbox("Has mortgage / נספח משכנתא", value=d.has_mortgage, key="pc_has_mortgage")
    with bcol2:
        pc_storage = st.checkbox("Has storage / מחסן", value=d.has_storage, key="pc_has_storage")
    with bcol3:
        pc_parking = st.checkbox("Has parking / חניה", value=d.has_parking, key="pc_has_parking")

    # --- Phase 1: Contract Payment Table (always shown) ---
    if not d.payment_lines:
        st.error("No payment lines were extracted. Cannot build payment table.")
        return

    payment_lines = d.payment_lines
    project_label = selected_project if selected_project != "—" else "Unknown"

    st.subheader("Contract Payment Table / לוח תשלומים")

    header_cols = st.columns([0.5, 2.5, 2, 1])
    with header_cols[0]:
        st.markdown("**#**")
    with header_cols[1]:
        st.markdown("**Payment**")
    with header_cols[2]:
        st.markdown("**Amount (€)**")
    with header_cols[3]:
        st.markdown("**%**")

    for i, pl in enumerate(payment_lines):
        row_cols = st.columns([0.5, 2.5, 2, 1])
        with row_cols[0]:
            st.write(f"{i + 1}")
        with row_cols[1]:
            st.write(pl.name)
        with row_cols[2]:
            st.write(f"€{pl.amount:,.0f}")
        with row_cols[3]:
            st.write(f"{pl.percentage:.0f}%" if pl.percentage else "—")

    contract_total = sum(pl.amount for pl in payment_lines)
    st.markdown(f"**Contract total: €{contract_total:,.0f}**")

    # Reservation fee controls
    st.markdown("---")
    deduct_reservation = st.checkbox(
        "Deduct reservation fee / ניכוי דמי רצינות מהתשלום הראשון",
        value=False, key="pc_deduct_reservation"
    )
    reservation_fee = 0.0
    if deduct_reservation:
        reservation_fee = st.number_input(
            "Reservation fee (€)", value=0.0, min_value=0.0, step=500.0,
            key="pc_reservation_fee"
        )

    # --- Phase 2: Regular Pre-Contract Payment Table (always shown) ---
    st.subheader("Pre-Contract Payment Table / לוח תשלומי פרה-קונטרקט")

    pc_table = compute_precontract_table(
        payment_lines, pc_price,
        deduct_reservation, reservation_fee,
    )
    for i, line in enumerate(pc_table.lines):
        st.write(f"{i + 1}. {line.name}: €{line.amount:,.0f}")
    st.markdown(f"**Total: €{pc_table.total:,.0f}**")

    if abs(pc_table.total - pc_price) < 1:
        st.success(f"✅ Total matches purchase price (€{pc_price:,.0f})")
    else:
        st.error(f"❌ Total (€{pc_table.total:,.0f}) doesn't match purchase price (€{pc_price:,.0f})")

    # Copy text for regular table
    regular_copy_lines = [
        f"Pre-Contract Payment Table - {project_label} - Apartment {pc_apt}",
        f"Client: {pc_client}",
        f"Purchase Price: €{pc_price:,.0f}",
        "",
    ]
    for i, line in enumerate(pc_table.lines):
        regular_copy_lines.append(f"{i + 1}. {line.name}: €{line.amount:,.0f}")
    regular_copy_lines.append(f"Total: €{pc_table.total:,.0f}")

    st.markdown("**Copy-ready output:**")
    st.code("\n".join(regular_copy_lines), language=None)

    # --- Phase 3: Mortgage section (if detected or toggled) ---
    st.markdown("---")
    if pc_mortgage:
        st.subheader("לוח תשלומים משכנתא")
        st.markdown("סמן את התשלומים שישולמו מהמשכנתא ולחץ על 'חשב' לקבלת לוח תשלומים מותאם")

        # Contract payments with mortgage checkboxes
        mortgage_flags: list[bool] = []

        m_header_cols = st.columns([0.5, 2.5, 2, 1, 1])
        with m_header_cols[0]:
            st.markdown("**#**")
        with m_header_cols[1]:
            st.markdown("**Payment**")
        with m_header_cols[2]:
            st.markdown("**Amount (€)**")
        with m_header_cols[3]:
            st.markdown("**%**")
        with m_header_cols[4]:
            st.markdown("**Mortgage**")

        for i, pl in enumerate(payment_lines):
            row_cols = st.columns([0.5, 2.5, 2, 1, 1])
            with row_cols[0]:
                st.write(f"{i + 1}")
            with row_cols[1]:
                st.write(pl.name)
            with row_cols[2]:
                st.write(f"€{pl.amount:,.0f}")
            with row_cols[3]:
                st.write(f"{pl.percentage:.0f}%" if pl.percentage else "—")
            with row_cols[4]:
                is_mortgage = st.checkbox(
                    "M", value=False, key=f"pc_mortgage_{i}", label_visibility="collapsed"
                )
                mortgage_flags.append(is_mortgage)

        if st.button("חשב / Calculate Mortgage Table", key="pc_calc_mortgage"):
            st.session_state["pc_mortgage_calculated"] = True

        if st.session_state.get("pc_mortgage_calculated") and any(mortgage_flags):
            mt = compute_mortgage_table(
                payment_lines, pc_price, mortgage_flags,
                deduct_reservation, reservation_fee,
            )

            st.markdown("#### Mortgage-Adjusted Payment Table")
            for i, line in enumerate(mt.non_mortgage_lines):
                st.write(f"{i + 1}. {line.name}: €{line.amount:,.0f}")
            if mt.mortgage_line:
                st.write(f"משכנתא: €{mt.mortgage_line.amount:,.0f}")
            st.markdown(f"**Total: €{mt.total:,.0f}**")

            if abs(mt.total - pc_price) < 1:
                st.success(f"✅ Total matches purchase price (€{pc_price:,.0f})")
            else:
                st.error(f"❌ Total (€{mt.total:,.0f}) doesn't match purchase price (€{pc_price:,.0f})")

            # Copy text for mortgage table
            mortgage_copy_lines = [
                f"Mortgage Payment Table - {project_label} - Apartment {pc_apt}",
                f"Client: {pc_client}",
                f"Purchase Price: €{pc_price:,.0f}",
                "",
            ]
            for i, line in enumerate(mt.non_mortgage_lines):
                mortgage_copy_lines.append(f"{i + 1}. {line.name}: €{line.amount:,.0f}")
            if mt.mortgage_line:
                mortgage_copy_lines.append(f"משכנתא: €{mt.mortgage_line.amount:,.0f}")
            mortgage_copy_lines.append(f"Total: €{mt.total:,.0f}")

            st.markdown("**Copy-ready output:**")
            st.code("\n".join(mortgage_copy_lines), language=None)


# ============================================================
# Page Router
# ============================================================
page = st.sidebar.radio("Navigation", ["Verification", "Pre-Contract Info", "Project Configuration"], index=0)

if page == "Verification":
    render_verification_page()
elif page == "Pre-Contract Info":
    render_precontract_page()
else:
    render_config_page()
