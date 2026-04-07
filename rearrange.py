import streamlit as st
import io
import re
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import PyPDF2
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Label Tool", layout="wide", page_icon="📄")

# --- Supabase Setup ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Supabase secrets missing!")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Flipkart Label Tool - Login / Signup")
    with st.form("auth"):
        mode = st.radio("Action", ["Login", "Signup"])
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Submit"):
            try:
                if mode == "Login":
                    res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                else:
                    res = supabase.auth.sign_up({"email": e, "password": p})
                if res.user:
                    st.session_state.user = res.user
                    st.experimental_rerun()
            except Exception as ex:
                st.error(f"Auth Failed: {ex}")
else:
    u_id = st.session_state.user.id
    st.sidebar.success(f"Logged in as: {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.experimental_rerun()

    st.title("📄 Flipkart Label Crop & Reorder Tool")

    # ----------------- 3. USER-SPECIFIC MAPPING -----------------
    @st.cache_data(ttl=300)
    def load_user_mapping(u_id):
        res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", u_id).execute()
        return {item['portal_sku'].upper(): item['master_sku'].upper() for item in res.data} if res.data else {}

    mapping_dict = load_user_mapping(u_id)

    # ----------------- 4. CROP SETTINGS -----------------
    X, Y, W, H = 187, 461, 218, 358

    def crop_pdf(input_pdf):
        output_pdf = io.BytesIO()
        pdf_reader = PyPDF2.PdfReader(input_pdf)
        pdf_writer = PyPDF2.PdfWriter()
        for page in pdf_reader.pages:
            page.mediabox.lower_left = (X, Y)
            page.mediabox.upper_right = (X + W, Y + H)
            pdf_writer.add_page(page)
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)
        return output_pdf

    # ----------------- 5. REORDER FUNCTIONS -----------------
    def extract_blocks(pdf_file):
        blocks = []
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                temp_blocks = text.split("ORDERED THROUGH")
                temp_blocks = [("ORDERED THROUGH" + b).strip() for b in temp_blocks if b.strip()]
                blocks.extend(temp_blocks)
        return blocks

    def find_sku(block):
        match = re.search(r'(FM[P|C]\d{10,12})', block)
        return match.group(0).upper() if match else "UNKNOWN"

    def reorder_blocks(blocks, mapping_dict):
        mapped_blocks = [(block, mapping_dict.get(find_sku(block), find_sku(block))) for block in blocks]
        mapped_blocks.sort(key=lambda x: x[1])
        return [x[0] for x in mapped_blocks]

    def create_pdf(blocks):
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 50
        c.setFont("Helvetica", 10)
        for block in blocks:
            for line in block.split("\n"):
                if y < 50:
                    c.showPage()
                    y = height - 50
                c.drawString(30, y, line)
                y -= 12
            y -= 10
        c.save()
        buffer.seek(0)
        return buffer

    # ----------------- 6. STREAMLIT WORKFLOW -----------------
    uploaded_file = st.file_uploader("Upload Flipkart Labels PDF", type=["pdf"])

    if uploaded_file:
        st.subheader("Step 1: Crop PDF")
        if st.button("Crop PDF"):
            cropped_pdf = crop_pdf(uploaded_file)
            st.success("✅ PDF Cropped!")
            st.download_button("📥 Download Cropped PDF", cropped_pdf, "cropped.pdf", "application/pdf")

        st.subheader("Step 2: Reorder PDF (using Master SKU)")
        if st.button("Reorder PDF"):
            blocks = extract_blocks(uploaded_file)
            reordered = reorder_blocks(blocks, mapping_dict)
            pdf_buffer = create_pdf(reordered)
            st.success("✅ PDF Reordered!")
            st.download_button("📥 Download Reordered PDF", pdf_buffer, "reordered_labels.pdf", "application/pdf")
