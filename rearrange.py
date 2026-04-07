import streamlit as st
import io
import re
import pdfplumber
import PyPDF2
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Label Tool", layout="wide", page_icon="📄")

# --- Supabase Setup ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Supabase configuration not found in .streamlit/secrets.toml")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Flipkart Label Tool - Login / Signup")
    col1, col2 = st.columns([1, 1])
    
    with col1:
        with st.form("auth"):
            st.subheader("Authentication")
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
                        st.rerun()
                except Exception as ex:
                    st.error(f"Auth Failed: {ex}")
else:
    u_id = st.session_state.user.id
    st.sidebar.success(f"Logged in: {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    st.title("📄 Flipkart Label Crop & Reorder Tool")

    # ----------------- 3. DATA MAPPING -----------------
    @st.cache_data(ttl=300)
    def load_user_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            return {item['portal_sku'].upper().strip(): item['master_sku'].upper().strip() for item in res.data} if res.data else {}
        except Exception as e:
            st.sidebar.error(f"Mapping Load Error: {e}")
            return {}

    mapping_dict = load_user_mapping(u_id)
    
    if not mapping_dict:
        st.sidebar.warning("No SKU mappings found in database.")

    # ----------------- 4. PDF PROCESSING ENGINE -----------------
    
    def get_sku_from_page(plum_page):
        """Extracts the Flipkart SKU (FMP/FMC) from the page text."""
        text = plum_page.extract_text()
        if text:
            match = re.search(r'(FM[P|C]\d{10,12})', text)
            return match.group(0).upper() if match else "UNKNOWN"
        return "UNKNOWN"

    def process_labels(input_pdf_file, mapping, do_crop=True, do_reorder=True):
        # Read the file for PyPDF2 (writing) and pdfplumber (reading text)
        pdf_bytes = input_pdf_file.read()
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        
        page_data = []
        
        # Step 1: Analyze Pages
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as plum:
            for i, page in enumerate(plum.pages):
                p_sku = get_sku_from_page(page)
                m_sku = mapping.get(p_sku, p_sku) # Fallback to portal SKU if no mapping
                page_data.append({
                    "original_index": i,
                    "master_sku": m_sku
                })

        # Step 2: Reorder if requested
        if do_reorder:
            page_data.sort(key=lambda x: x["master_sku"])

        # Step 3: Create Output
        writer = PyPDF2.PdfWriter()
        
        # Crop Coordinates (Adjust these if your label position changes)
        # X, Y is bottom-left. W, H is width and height.
        X, Y, W, H = 187, 461, 218, 358

        for item in page_data:
            orig_page = reader.pages[item["original_index"]]
            
            if do_crop:
                orig_page.mediabox.lower_left = (X, Y)
                orig_page.mediabox.upper_right = (X + W, Y + H)
            
            writer.add_page(orig_page)

        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        return output_buffer

    # ----------------- 5. UI INTERFACE -----------------
    uploaded_file = st.file_uploader("Upload Flipkart Shipping Labels (PDF)", type=["pdf"])

    if uploaded_file:
        st.info(f"Loaded mapping: {len(mapping_dict)} SKUs found.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🎯 Only Crop Labels", use_container_width=True):
                with st.spinner("Cropping..."):
                    processed_pdf = process_labels(uploaded_file, mapping_dict, do_crop=True, do_reorder=False)
                    st.success("Cropping Complete!")
                    st.download_button("📥 Download Cropped PDF", processed_pdf, "labels_cropped.pdf", "application/pdf")

        with col2:
            if st.button("🚀 Crop & Reorder by Master SKU", use_container_width=True):
                with st.spinner("Processing Reorder..."):
                    processed_pdf = process_labels(uploaded_file, mapping_dict, do_crop=True, do_reorder=True)
                    st.success("Reordered & Cropped Successfully!")
                    st.download_button("📥 Download Organized PDF", processed_pdf, "labels_organized.pdf", "application/pdf")

    # Optional: Display current mappings for user reference
    with st.expander("View Your SKU Mappings"):
        if mapping_dict:
            st.table([{"Portal SKU": k, "Master SKU": v} for k, v in mapping_dict.items()])
        else:
            st.write("No mappings found. Please add them to your Supabase 'sku_mapping' table.")
