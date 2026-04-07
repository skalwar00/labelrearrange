import streamlit as st
import io
import pypdf
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Pro Bolt", layout="wide")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_data(ttl=600)
def get_skus(user_id):
    try:
        supabase = init_supabase()
        res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
        mapping = {str(i['portal_sku']).strip().upper(): str(i['master_sku']).strip().upper() for i in res.data}
        # Lambe SKUs pehle taaki partial match na ho
        sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
        return mapping, sorted_keys
    except:
        return {}, []

# ----------------- 2. FAST ENGINE -----------------
def process_pdf_fast(file_bytes, mapping, sku_list):
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    data_list = []
    
    for i in range(len(reader.pages)):
        page = reader.pages[i]
        # Text extraction ko limit kiya speed ke liye
        text = (page.extract_text() or "")[:1000].upper()
        
        found_p_sku = "UNKNOWN"
        for sku in sku_list:
            if sku in text:
                found_p_sku = sku
                break
        
        # Mapping se Master SKU uthao, nahi toh Portal SKU hi rehne do
        m_sku = mapping.get(found_p_sku, found_p_sku)
        
        data_list.append({
            "original_index": i,
            "master_sku": m_sku,
            "portal_sku": found_p_sku
        })
        
    return data_list, reader

# ----------------- 3. UI -----------------
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("🔐 Login")
    with st.form("auth"):
        e, p = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            res = init_supabase().auth.sign_in_with_password({"email": e, "password": p})
            if res.user: 
                st.session_state.user = res.user
                st.rerun()
else:
    mapping_dict, search_skus = get_skus(st.session_state.user.id)
    st.title("⚡ Flipkart Ultra-Fast Cropper & Sorter")

    file = st.file_uploader("Upload Labels PDF", type="pdf")

    if file:
        file_bytes = file.read()
        
        with st.spinner("Scanning & Matching..."):
            results, reader = process_pdf_fast(file_bytes, mapping_dict, search_skus)
            df = pd.DataFrame(results)

        # Display Summary
        st.subheader("📋 Order Summary (Sorted by Master SKU)")
        summary = df.groupby('master_sku').size().reset_index(name='Qty')
        st.dataframe(summary, use_container_width=True, hide_index=True)

        if st.button("🚀 CROP & DOWNLOAD SORTED PDF", use_container_width=True):
            with st.status("Rearranging and Cropping...") as status:
                # CRITICAL: Yahan sorting ho rahi hai Master SKU ke basis par
                df_sorted = df.sort_values(by="master_sku", ascending=True)
                
                writer = pypdf.PdfWriter()
                # Flipkart Crop Coordinates
                X, Y, W, H = 187, 461, 218, 358 

                for _, row in df_sorted.iterrows():
                    # Original PDF se sahi page uthao sorted sequence mein
                    page_to_add = reader.pages[row['original_index']]
                    
                    # Crop apply karo
                    page_to_add.mediabox.lower_left = (X, Y)
                    page_to_add.mediabox.upper_right = (X + W, Y + H)
                    
                    # Final PDF mein add karo
                    writer.add_page(page_to_add)

                output = io.BytesIO()
                writer.write(output)
                
                status.update(label="✅ Done!", state="complete")
                st.download_button(
                    "📥 Download Final Sorted PDF", 
                    output.getvalue(), 
                    f"Sorted_Labels_{datetime.now().strftime('%H%M')}.pdf",
                    use_container_width=True
                )
