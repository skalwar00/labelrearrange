import streamlit as st
import io
import re
import pypdf # PyPDF2 ka faster version
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Pro Tool", layout="wide", page_icon="📦")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Login")
    with st.form("auth"):
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user
                st.rerun()
            except: st.error("Login Failed")
else:
    u_id = st.session_state.user.id
    
    # ----------------- 3. OPTIMIZED DATA ENGINE -----------------
    @st.cache_data(ttl=600)
    def load_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            return {str(i['portal_sku']).strip().upper(): str(i['master_sku']).strip().upper() for i in res.data}
        except: return {}

    # Fast Extraction Function
    def fast_process_pdf(file_bytes, mapping):
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_data = []
        
        # Regex compiled once for speed
        sku_pattern = re.compile(r'1\s+([A-Z0-9._-]+)\s*\|')
        
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            match = sku_pattern.search(text)
            p_sku = match.group(1).strip().upper() if match else "UNKNOWN"
            m_sku = mapping.get(p_sku, p_sku)
            
            extracted_data.append({
                "p_sku": p_sku,
                "m_sku": m_sku,
                "page_index": i
            })
        return extracted_data, reader

    # ----------------- 4. UI -----------------
    st.title("📦 Flipkart Ultra-Fast Tool")
    mapping_dict = load_mapping(u_id)
    
    uploaded_file = st.file_uploader("Upload Labels PDF", type="pdf")

    if uploaded_file:
        # File ko bytes mein read karein taaki bar-bar read na karna pade
        file_bytes = uploaded_file.read()
        
        with st.spinner("⚡ Scanning PDF at high speed..."):
            all_data, reader = fast_process_pdf(file_bytes, mapping_dict)
            df = pd.DataFrame(all_data)

        # Picklist Summary
        st.subheader("📋 Picklist")
        picklist = df.groupby('m_sku').size().reset_index(name='Qty')
        st.dataframe(picklist, use_container_width=True, hide_index=True)

        st.divider()

        # Processing Logic
        if st.button("🚀 Generate & Crop Labels (Instant)", use_container_width=True):
            with st.status("Processing...") as status:
                writer = pypdf.PdfWriter()
                
                # Sort indices by Master SKU
                sorted_indices = df.sort_values(by="m_sku")["page_index"].tolist()
                
                # Crop Coordinates
                X, Y, W, H = 187, 461, 218, 358

                for idx in sorted_indices:
                    page = reader.pages[idx]
                    page.mediabox.lower_left = (X, Y)
                    page.mediabox.upper_right = (X + W, Y + H)
                    writer.add_page(page)

                output = io.BytesIO()
                writer.write(output)
                
                status.update(label="✅ Done!", state="complete")
                st.download_button("📥 Download PDF", output.getvalue(), "Labels_Sorted.pdf", "application/pdf")
