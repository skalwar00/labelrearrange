import streamlit as st
import io
import re
import PyPDF2
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Fast Label Tool", layout="wide", page_icon="⚡")

# --- Supabase Setup ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Supabase secrets are missing! Check .streamlit/secrets.toml")
    st.stop()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Flipkart Label Tool - Login")
    with st.form("auth"):
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                if res.user:
                    st.session_state.user = res.user
                    st.rerun()
            except Exception as ex:
                st.error(f"Login Failed: {ex}")
else:
    u_id = st.session_state.user.id
    st.sidebar.success(f"Logged in: {st.session_state.user.email}")
    
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # ----------------- 3. DATA MAPPING -----------------
    @st.cache_data(ttl=300)
    def load_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            # Normalize to uppercase and strip whitespace
            return {item['portal_sku'].upper().strip(): item['master_sku'].upper().strip() for item in res.data} if res.data else {}
        except:
            return {}

    mapping_dict = load_mapping(u_id)

    # ----------------- 4. UI & LOGIC -----------------
    st.title("⚡ Ultra-Fast Label Processor")
    st.write(f"Active Mappings: **{len(mapping_dict)}** SKUs")

    uploaded_file = st.file_uploader("Upload Flipkart Label PDF", type=["pdf"])

    if uploaded_file:
        if st.button("🚀 Process & Reorder Now", use_container_width=True):
            with st.status("Processing PDF...", expanded=True) as status:
                try:
                    # Step 1: Initialize
                    status.write("Reading PDF file...")
                    reader = PyPDF2.PdfReader(uploaded_file)
                    writer = PyPDF2.PdfWriter()
                    total_pages = len(reader.pages)
                    page_entries = []

                    # Crop Coordinates
                    X, Y, W, H = 187, 461, 218, 358

                    # Step 2: Extract & Map (High Speed)
                    status.write(f"Scanning {total_pages} pages for SKUs...")
                    for i in range(total_pages):
                        page = reader.pages[i]
                        text = page.extract_text() or ""
                        
                        # Find Flipkart SKU
                        match = re.search(r'(FM[P|C]\d{10,12})', text)
                        p_sku = match.group(0).upper() if match else "UNKNOWN"
                        
                        # Get Master SKU from mapping
                        m_sku = mapping_dict.get(p_sku, p_sku)
                        
                        page_entries.append({
                            "page_obj": page,
                            "master_sku": m_sku,
                            "portal_sku": p_sku
                        })

                    # Step 3: Sort by Master SKU
                    status.write("Reordering pages based on Master SKU...")
                    page_entries.sort(key=lambda x: x["master_sku"])

                    # Step 4: Apply Crop and Build Output
                    status.write("Applying crop and finalising...")
                    for entry in page_entries:
                        p = entry["page_obj"]
                        # Set the Crop Box
                        p.mediabox.lower_left = (X, Y)
                        p.mediabox.upper_right = (X + W, Y + H)
                        writer.add_page(p)

                    # Step 5: Save to Buffer
                    output_pdf = io.BytesIO()
                    writer.write(output_pdf)
                    output_pdf.seek(0)

                    status.update(label="✅ Processing Complete!", state="complete", expanded=False)
                    
                    st.success(f"Success! {total_pages} labels reordered.")
                    st.download_button(
                        label="📥 Download Sorted & Cropped PDF",
                        data=output_pdf,
                        file_name=f"Reordered_Labels_{datetime.now().strftime('%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )

                except Exception as e:
                    status.update(label="❌ Error Occurred", state="error")
                    st.error(f"Something went wrong: {e}")

    # Optional: Quick Preview
    with st.expander("🔍 View Current Mappings"):
        if mapping_dict:
            st.json(mapping_dict)
        else:
            st.info("No mappings found. Make sure your Supabase table 'sku_mapping' has data.")
