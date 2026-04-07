import streamlit as st
import io
import pypdf
import pandas as pd
from supabase import create_client, Client

# --- SETUP ---
st.set_page_config(page_title="Flipkart Bolt", layout="wide")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_data(ttl=600)
def get_skus(user_id):
    supabase = init_supabase()
    res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
    # SKU list ko uppercase bytes mein convert kar rahe hain fast matching ke liye
    mapping = {i['portal_sku'].strip().upper(): i['master_sku'].strip().upper() for i in res.data}
    sorted_skus = sorted(mapping.keys(), key=len, reverse=True)
    return mapping, sorted_skus

# --- THE FAST ENGINE ---
def ultra_fast_process(file_bytes, mapping, sku_list):
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    results = []
    
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        # Sabse bada time-saver: extract_text() ki jagah raw data use karna
        content = page.get_contents() 
        # Content ko string mein badalna bina heavy processing ke
        text_block = str(content).upper()
        
        found = "UNKNOWN"
        for sku in sku_list:
            if sku in text_block:
                found = sku
                break
        
        results.append({
            "p_sku": found,
            "m_sku": mapping.get(found, found),
            "idx": i
        })
    return results, reader

# --- UI ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    # ... Login Code (Same as before) ...
    st.title("🔐 Login")
    with st.form("auth"):
        e, p = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = init_supabase().auth.sign_in_with_password({"email": e, "password": p})
            if res.user: 
                st.session_state.user = res.user
                st.rerun()
else:
    mapping_dict, sku_search_list = get_skus(st.session_state.user.id)
    
    st.title("⚡ Flipkart Bolt Cropper")
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")

    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        # Step 1: Scan (Instant)
        data, reader = ultra_fast_process(file_bytes, mapping_dict, sku_search_list)
        df = pd.DataFrame(data)

        # Step 2: Sort & Crop
        if st.button("🚀 INSTANT DOWNLOAD", use_container_width=True):
            output = io.BytesIO()
            writer = pypdf.PdfWriter()
            
            # Calibration - Flipkart Standard 4x6
            X, Y, W, H = 187, 461, 218, 358 

            # Sorting by Master SKU
            df_sorted = df.sort_values("m_sku")

            for idx in df_sorted['idx']:
                page = reader.pages[idx]
                page.mediabox.lower_left = (X, Y)
                page.mediabox.upper_right = (X + W, Y + H)
                writer.add_page(page)
            
            writer.write(output)
            st.download_button("📥 Click to Save", output.getvalue(), "Labels_Cropped.pdf", "application/pdf")
            st.success(f"Processed {len(df)} pages!")
