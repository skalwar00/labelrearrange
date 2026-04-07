import streamlit as st
import io
import pypdf
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Flash Tool", layout="wide")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# ----------------- 2. DATA MAPPING (Cached) -----------------
@st.cache_data(ttl=600)
def load_mapping_data(user_id):
    try:
        res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
        mapping = {str(i['portal_sku']).strip().upper(): str(i['master_sku']).strip().upper() for i in res.data}
        # Sorting by length descending prevents partial matches (e.g., 'ABC' matching 'ABC-123')
        skus = sorted(mapping.keys(), key=len, reverse=True)
        return mapping, skus
    except:
        return {}, []

# ----------------- 3. CORE ENGINE (Optimized) -----------------
def fast_process(file_bytes, mapping, sku_list):
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    processed_pages = []
    
    for i, page in enumerate(reader.pages):
        # Speed Tip: Extracting only the first 500 characters covers most labels
        text = (page.extract_text() or "")[:600].upper()
        
        found_sku = "UNKNOWN"
        for sku in sku_list:
            if sku in text: # Fast string membership check (faster than regex)
                found_sku = sku
                break
        
        processed_pages.append({
            "p_sku": found_sku,
            "m_sku": mapping.get(found_sku, found_sku),
            "page_idx": i
        })
    
    return processed_pages, reader

# ----------------- 4. UI -----------------
if 'user' not in st.session_state:
    st.session_state.user = None

# Simple Login Logic
if st.session_state.user is None:
    st.title("🔐 Login")
    with st.form("auth"):
        e, p = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = supabase.auth.sign_in_with_password({"email": e, "password": p})
            if res.user: 
                st.session_state.user = res.user
                st.rerun()
else:
    mapping_dict, portal_skus = load_mapping_data(st.session_state.user.id)
    
    st.title("⚡ Flipkart Flash Processor")
    file = st.file_uploader("Upload PDF", type="pdf")

    if file:
        file_bytes = file.read()
        
        # Phase 1: Analysis (Seconds mein hoga)
        with st.spinner("Scanning..."):
            data, reader = fast_process(file_bytes, mapping_dict, portal_skus)
            df = pd.DataFrame(data)

        # UI Layout
        col1, col2 = st.columns([3, 1])
        with col1:
            st.dataframe(df.groupby('m_sku').size().reset_index(name='Qty'), use_container_width=True)
        with col2:
            st.metric("Orders", len(df))

        # Phase 2: Instant Crop & Sort
        if st.button("🚀 CROP & DOWNLOAD NOW", use_container_width=True):
            output = io.BytesIO()
            writer = pypdf.PdfWriter()
            
            # Sort pages by Master SKU
            df_sorted = df.sort_values("m_sku")
            
            # Calibration - Flipkart Standard
            X, Y, W, H = 187, 461, 218, 358 

            for _, row in df_sorted.iterrows():
                page = reader.pages[row['page_idx']]
                page.mediabox.lower_left = (X, Y)
                page.mediabox.upper_right = (X + W, Y + H)
                writer.add_page(page)
            
            writer.write(output)
            st.download_button("📥 Get PDF", output.getvalue(), "Flipkart_Final.pdf", "application/pdf")
