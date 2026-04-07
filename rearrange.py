import streamlit as st
import io
import re
import pdfplumber
import PyPDF2
from supabase import create_client, Client

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Label Tool", layout="wide", page_icon="📄")

# --- Supabase Setup ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Error: Supabase Secrets missing in .streamlit/secrets.toml")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Flipkart Label Tool - Login")
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

    st.title("📄 Flipkart Label Tool (Optimized)")

    # ----------------- 3. DATA MAPPING -----------------
    @st.cache_data(ttl=60)
    def load_user_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            return {item['portal_sku'].upper().strip(): item['master_sku'].upper().strip() for item in res.data} if res.data else {}
        except:
            return {}

    mapping_dict = load_user_mapping(u_id)

    # ----------------- 4. CORE ENGINE -----------------
    def process_pdf_fast(uploaded_file, mapping, do_reorder=True):
        # Reset file pointer
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        page_data = []
        
        # Step 1: Scan for SKUs
        with pdfplumber.open(io.BytesIO(file_bytes)) as plum:
            for i, page in enumerate(plum.pages):
                status_text.text(f"Scanning Page {i+1} of {total_pages}...")
                text = page.extract_text() or ""
                # Flipkart SKU Pattern
                match = re.search(r'(FM[P|C]\d{10,12})', text)
                p_sku = match.group(0).upper() if match else "UNKNOWN"
                m_sku = mapping.get(p_sku, p_sku)
                
                page_data.append({"index": i, "master_sku": m_sku})
                progress_bar.progress((i + 1) / total_pages)

        # Step 2: Reorder
        if do_reorder:
            status_text.text("Sorting pages by Master SKU...")
            page_data.sort(key=lambda x: x["master_sku"])

        # Step 3: Crop and Write
        writer = PyPDF2.PdfWriter()
        # Flipkart Label Coordinates
        X, Y, W, H = 187, 461, 218, 358 

        for item in page_data:
            page = reader.pages[item["index"]]
            page.mediabox.lower_left = (X, Y)
            page.mediabox.upper_right = (X + W, Y + H)
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        
        status_text.text("✅ Process Complete!")
        return output

    # ----------------- 5. UI -----------------
    file = st.file_uploader("Upload Labels", type="pdf")
    
    if file:
        if st.button("🚀 Process & Reorder", use_container_width=True):
            with st.spinner("Wait..."):
                final_pdf = process_pdf_fast(file, mapping_dict)
                st.download_button(
                    label="📥 Download Sorted Labels",
                    data=final_pdf,
                    file_name=f"Labels_{datetime.now().strftime('%H%M%S')}.pdf",
                    mime="application/pdf"
                )

    if st.checkbox("Show My SKU Mappings"):
        st.write(mapping_dict)
