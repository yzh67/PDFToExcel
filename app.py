import io
import re
import csv
import base64
from pathlib import Path

import pdfplumber
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="PDF Converter",
    page_icon="📄",
    layout="wide"
)

st.markdown("""
<style>
    header[data-testid="stHeader"] {display: none !important;}
    div[data-testid="stToolbar"] {display: none !important;}
    div[data-testid="stDecoration"] {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}

    .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #fcfdfe 100%);
        color: #0f172a;
    }

    .block-container {
        max-width: 1120px;
        padding-top: 1rem;
        padding-bottom: 2.5rem;
    }

    .nav-wrap {
        background: rgba(255,255,255,0.88);
        border: 1px solid #e5e7eb;
        border-radius: 22px;
        padding: 14px 18px;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.05);
        margin-bottom: 2rem;
    }

    .nav-icon {
        width: 42px;
        height: 42px;
        border-radius: 14px;
        background: #4f46e5;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.15rem;
        box-shadow: 0 14px 28px rgba(79, 70, 229, 0.25);
        flex-shrink: 0;
    }

    .nav-title {
        font-size: 1.08rem;
        font-weight: 700;
        color: #0f172a;
    }

    .hero-title {
        text-align: center;
        font-size: clamp(2.8rem, 5vw, 4.9rem);
        line-height: 1.05;
        font-weight: 800;
        letter-spacing: -0.03em;
        color: #0f172a;
        margin-top: 1rem;
        margin-bottom: 0.8rem;
    }

    .hero-subtitle {
        text-align: center;
        max-width: 760px;
        margin: 0 auto 2rem auto;
        font-size: 1.08rem;
        line-height: 1.7;
        color: #64748b;
        font-weight: 500;
    }

    .upload-hero {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 30px;
        padding: 2rem 2rem 1.35rem 2rem;
        box-shadow: 0 24px 50px rgba(15, 23, 42, 0.06);
        margin-bottom: 0.9rem;
    }

    .upload-icon {
        width: 84px;
        height: 84px;
        background: #eef2ff;
        color: #4f46e5;
        border-radius: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2rem;
        margin: 0 auto 1rem auto;
    }

    .upload-title {
        text-align: center;
        font-size: 1.9rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.35rem;
    }

    .upload-subtitle {
        text-align: center;
        color: #94a3b8;
        font-size: 1rem;
        margin-bottom: 0;
    }

    div[data-testid="stFileUploader"] {
        margin-top: 0.25rem;
    }

    div[data-testid="stFileUploader"] > section {
        border: 2px dashed #cbd5e1 !important;
        border-radius: 22px !important;
        background: #f8fafc !important;
        padding: 1rem !important;
    }

    div[data-testid="stFileUploader"] > section:hover {
        border-color: #4f46e5 !important;
        background: #f5f7ff !important;
    }

    div[data-testid="stFileUploaderDropzone"] {
        padding: 0.65rem 0.35rem !important;
    }

    div[data-testid="stFileUploader"] small {
        color: #64748b !important;
    }

    .stButton > button {
        background: #4f46e5 !important;
        color: white !important;
        border: none !important;
        border-radius: 16px !important;
        font-weight: 700 !important;
        padding: 0.92rem 1.2rem !important;
        box-shadow: 0 14px 28px rgba(79, 70, 229, 0.24) !important;
        width: 100%;
    }

    .stButton > button:hover {
        background: #4338ca !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 16px !important;
    }
</style>
""", unsafe_allow_html=True)

DATE_PATTERN = r"\d{2}-\d{2}-\d{4}"
AMOUNT_PATTERN = r"\d[\d,]*\.\d{2}"


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def force_csv_text(value):
    value = clean_text(value)
    if value == "":
        return ""
    return f'="{value}"'


def parse_amount(text):
    text = clean_text(text).replace(",", "")
    return float(text)


def choose_debit_amount(line):
    amount_texts = re.findall(AMOUNT_PATTERN, line)

    if not amount_texts:
        return None

    amount_values = [parse_amount(x) for x in amount_texts]

    if len(amount_values) >= 2:
        debit_value = amount_values[-2]
    else:
        debit_value = amount_values[0]

    if debit_value == 0:
        for value in amount_values:
            if value != 0:
                return value

    return debit_value


def extract_guest_name(text):
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if "GUEST NAME & ADDRESS" in line.upper():
            for j in range(i + 1, len(lines)):
                candidate = clean_text(lines[j])

                if not candidate:
                    continue

                candidate = re.split(
                    r"GST\s*Reg\s*No\.?\s*:",
                    candidate,
                    flags=re.IGNORECASE
                )[0].strip()

                if candidate:
                    return candidate

    return ""


def extract_header(text):
    invoice_no = ""
    departure_date = ""
    ta = ""
    guest_name = ""

    invoice_match = re.search(
        r"Invoice\s*No\.?\s*[: ]+\s*([A-Za-z0-9\-/]+)",
        text,
        re.IGNORECASE
    )
    if invoice_match:
        raw_invoice_no = clean_text(invoice_match.group(1))
        if raw_invoice_no.isdigit():
            invoice_no = int(raw_invoice_no)
        else:
            invoice_no = raw_invoice_no

    departure_match = re.search(
        r"Departure\s*[: ]+\s*(" + DATE_PATTERN + r")",
        text,
        re.IGNORECASE
    )
    if departure_match:
        departure_date = clean_text(departure_match.group(1))

    ta_match = re.search(
        r"TA\s*:\s*([A-Za-z0-9\-/#]+)",
        text,
        re.IGNORECASE
    )
    if ta_match:
        ta = clean_text(ta_match.group(1))

    guest_name = extract_guest_name(text)

    return {
        "inv": invoice_no,
        "dept": departure_date,
        "ta": ta,
        "guest": guest_name
    }


def extract_line_items(text):
    lines = text.splitlines()
    items = []
    in_table = False

    for raw_line in lines:
        line = clean_text(raw_line)

        if not line:
            continue

        upper_line = line.upper()

        if "DATE" in upper_line and "DESCRIPTION" in upper_line and "DEBIT" in upper_line and "CREDIT" in upper_line:
            in_table = True
            continue

        if not in_table:
            continue

        if (
            "TOTAL" in upper_line
            or "SUBTOTAL" in upper_line
            or "TAX SUMMARY" in upper_line
            or "BALANCE" in upper_line
        ):
            break

        date_match = re.match(r"^(" + DATE_PATTERN + r")", line)
        if not date_match:
            continue

        service_date = clean_text(date_match.group(1))
        amount = choose_debit_amount(line)

        if amount is None:
            continue

        items.append((service_date, amount))

    return items


def extract_tax_invoices_from_pdf_bytes(pdf_bytes):
    invoices_data = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            if "TAX INVOICE" not in text.upper():
                continue

            header = extract_header(text)
            line_items = extract_line_items(text)

            if not line_items:
                continue

            invoices_data.append({
                "inv": header["inv"],
                "dept": header["dept"],
                "ta": header["ta"],
                "guest": header["guest"],
                "lines": line_items
            })

    return invoices_data


def build_csv_bytes(invoices_data):
    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow(["InvoiceNo", "Invoice Date", "BookingID", "GuestName", "Service Date", "Amount"])

    for invoice in invoices_data:
        for service_date, amount in invoice["lines"]:
            writer.writerow([
                invoice["inv"],
                force_csv_text(invoice["dept"]),
                force_csv_text(invoice["ta"]),
                invoice["guest"],
                force_csv_text(service_date),
                f"{amount:.2f}"
            ])

    return output.getvalue().encode("utf-8-sig")


def render_save_picker(csv_bytes, output_name):
    b64_data = base64.b64encode(csv_bytes).decode("ascii")
    safe_name = output_name.replace("\\", "\\\\").replace("'", "\\'")

    html = f"""
    <div style="margin-top: 12px;">
      <button id="saveBtn" style="
        width: 100%;
        background: #107c10;
        color: white;
        border: none;
        border-radius: 16px;
        font-weight: 700;
        padding: 0.92rem 1.2rem;
        box-shadow: 0 14px 28px rgba(16, 124, 16, 0.20);
        cursor: pointer;
        font-size: 1rem;
      ">Choose Save Location & Save CSV</button>
      <div id="saveStatus" style="
        margin-top: 10px;
        color: #64748b;
        font-family: sans-serif;
        font-size: 0.92rem;
      "></div>
    </div>

    <script>
      const base64Data = '{b64_data}';
      const outputName = '{safe_name}';

      function base64ToUint8Array(base64) {{
        const binaryString = atob(base64);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {{
          bytes[i] = binaryString.charCodeAt(i);
        }}
        return bytes;
      }}

      async function saveCsv() {{
        const status = document.getElementById("saveStatus");
        const bytes = base64ToUint8Array(base64Data);
        const blob = new Blob([bytes], {{ type: "text/csv;charset=utf-8" }});

        try {{
          if ("showSaveFilePicker" in window) {{
            const handle = await window.showSaveFilePicker({{
              suggestedName: outputName,
              types: [{{
                description: "CSV files",
                accept: {{
                  "text/csv": [".csv"]
                }}
              }}]
            }});

            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
            status.textContent = "Saved successfully.";
          }} else {{
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = outputName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            status.textContent = "Browser save picker not supported here, so a normal download was used.";
          }}
        }} catch (err) {{
          if (err && err.name === "AbortError") {{
            status.textContent = "Save cancelled.";
          }} else {{
            status.textContent = "Could not open save picker. A normal download may be needed in this browser.";
          }}
        }}
      }}

      document.getElementById("saveBtn").addEventListener("click", saveCsv);
    </script>
    """
    components.html(html, height=90)


if "csv_bytes" not in st.session_state:
    st.session_state.csv_bytes = None

if "output_name" not in st.session_state:
    st.session_state.output_name = None


st.markdown("""
<div class="nav-wrap">
    <div class="nav-icon">🧾</div>
    <div class="nav-title">PDF Converter</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero-title">Convert PDF to CSV</div>
<div class="hero-subtitle">
    Upload a PDF, extract invoice data, and choose where to save the CSV file.
</div>
""", unsafe_allow_html=True)

left, center, right = st.columns([1, 1.8, 1])

with center:
    st.markdown("""
    <div class="upload-hero">
        <div class="upload-icon">☁️</div>
        <div class="upload-title">Choose a PDF file</div>
        <div class="upload-subtitle">or drag and drop it here</div>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        label_visibility="collapsed"
    )

    if uploaded_file is not None:
        st.caption(f"Selected file: {uploaded_file.name}")

        if st.button("Convert to CSV"):
            try:
                with st.spinner("Converting PDF to CSV..."):
                    pdf_bytes = uploaded_file.getvalue()
                    invoices_data = extract_tax_invoices_from_pdf_bytes(pdf_bytes)

                    if not invoices_data:
                        st.session_state.csv_bytes = None
                        st.session_state.output_name = None
                        st.error("No TAX INVOICE data found in the uploaded PDF.")
                    else:
                        st.session_state.output_name = Path(uploaded_file.name).with_suffix(".csv").name
                        st.session_state.csv_bytes = build_csv_bytes(invoices_data)
                        st.success(f"Conversion complete. Found {len(invoices_data)} TAX INVOICE page(s).")

            except Exception as e:
                st.session_state.csv_bytes = None
                st.session_state.output_name = None
                st.error(f"Conversion failed: {str(e)}")

    if st.session_state.csv_bytes is not None:
        render_save_picker(
            st.session_state.csv_bytes,
            st.session_state.output_name
        )
