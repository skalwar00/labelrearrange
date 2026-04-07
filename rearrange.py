import streamlit as st
import io
import re
import pypdf
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Smart Search", layout="wide", page_icon="📦")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTH -----------------
if st.session_state.user is None:
    st.title("🔐 Login")
    # ... (Purana login code yahan rahega)
else:
    u_id = st.session_state.user.id

    # ----------------- 3. SMART MAPPING -----------------
    @st.cache_data(ttl=300)
    def load_mapping_and_list(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            # 1. Mapping dictionary (Portal -> Master)
            mapping = {str(i['portal_sku']).strip().upper(): str(i['master_sku']).strip().upper() for i in res.data}
            # 2. List of all Portal SKUs (Search karne ke liye)
            portal_skus_list = list(mapping.keys())
            # Sabse lambe SKU ko pehle rakhein taaki partial match na ho (e.g., 'ABC-1' vs 'ABC-10')
            portal_skus_list.sort(key=len, reverse=True) 
            return mapping, portal_skus_list
        except:
            return {}, []

    mapping_dict, db_portal_skus = load_mapping_and_list(u_id)

    # ----------------- 4. SMART SEARCH ENGINE -----------------
    def smart_process_pdf(file_bytes, mapping, sku_list):
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_data = []
        
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").upper()
            found_sku = "UNKNOWN"

            # Database ke har SKU ko PDF text mein check karo
            for sku in sku_list:
                # Hum check kar rahe hain ki kya SKU text mein maujood hai
                # Word boundary (\b) use kiya hai taaki exact match mile
                if re.search(rf'\b{re.escape(sku)}\b', text):
                    found_sku = sku
                    break # Ek baar match mil gaya toh loop stop kar do
            
            m_sku = mapping.get(found_sku, found_sku)
            
            extracted_data.append({
                "p_sku": found_sku,
                "m_sku": m_sku,
                "page_idx": i
            })
            
        return extracted_data, reader

    # ----------------- 5. UI -----------------
    st.title("📦 Flipkart Order Processor (Database-Sync Mode)")
    
    if not db_portal_skus:
        st.error("⚠️ Aapke Supabase mein koi SKU nahi mile. Pehle mapping upload karein.")
    
    uploaded_file = st.file_uploader("Upload Labels PDF", type="pdf")

    if uploaded_file and db_portal_skus:
        file_bytes = uploaded_file.read()
        
        with st.spinner("🔍 PDF mein Database SKUs search kar raha hoon..."):
            all_data, reader = smart_process_pdf(file_bytes, mapping_dict, db_portal_skus)
            df = pd.DataFrame(all_data)

        # Picklist Summary
        st.subheader("📋 Picklist (Based on DB Match)")
        summary = df.groupby('m_sku').size().reset_index(name='Qty')
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.dataframe(summary, use_container_width=True, hide_index=True)
        with c2:
            unknowns = len(df[df['p_sku'] == "UNKNOWN"])
            st.metric("Total Orders", len(df))
            if unknowns > 0:
                st.error(f"❌ {unknowns} Labels Database se match nahi huye!")

        # Processing Button
        if st.button("🚀 Sort & Crop Labels", use_container_width=True):
            with st.status("PDF taiyaar ho rahi hai...") as status:
                df_sorted = df.sort_values(by="m_sku")
                writer = pypdf.PdfWriter()
                X, Y, W, H = 187, 461, 218, 358 # Standard Flipkart Crop

                for _, row in df_sorted.iterrows():
                    page = reader.pages[row['page_idx']]
                    page.mediabox.lower_left = (X, Y)
                    page.mediabox.upper_right = (X + W, Y + H)
                    writer.add_page(page)

                output = io.BytesIO()
                writer.write(output)
                status.update(label="✅ Success!", state="complete")
                st.download_button("📥 Download Final PDF", output.getvalue(), "Sorted_Labels.pdf")
