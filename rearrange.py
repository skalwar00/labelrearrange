import streamlit as st
import io
import re
import PyPDF2
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Pro Tool", layout="wide", page_icon="📦")

# --- Supabase Setup ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("Supabase secrets missing!")
    st.stop()

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
                if res.user:
                    st.session_state.user = res.user
                    st.rerun()
            except Exception as ex:
                st.error(f"Failed: {ex}")
else:
    u_id = st.session_state.user.id
    st.sidebar.success(f"User: {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # ----------------- 3. DATA MAPPING -----------------
    @st.cache_data(ttl=60)
    def load_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            # Normalize keys to avoid space issues
            return {str(item['portal_sku']).strip().upper(): str(item['master_sku']).strip().upper() for item in res.data} if res.data else {}
        except:
            return {}

    mapping_dict = load_mapping(u_id)

    # ----------------- 4. LOGIC FUNCTIONS -----------------
    def get_pdf_data(file, mapping):
        reader = PyPDF2.PdfReader(file)
        data = []
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            text = page.extract_text() or ""
            
            # Pattern 1: Standard Flipkart SKU (FMP/FMC)
            # Pattern 2: Fallback for any alpha-numeric SKU (if FMP logic fails)
            match = re.search(r'1\s+([A-Z0-9-]+\b)\s*\|', text)
            
            p_sku = match.group(0).upper() if match else "NOT_FOUND"
            
            # Agar mapping mein hai toh Master SKU lo, varna Portal SKU hi dikhao
            m_sku = mapping.get(p_sku, p_sku) 
            
            data.append({
                "page": page, 
                "portal_sku": p_sku, 
                "m_sku": m_sku,
                "page_no": i + 1
            })
        return data

    # ----------------- 5. UI -----------------
    st.title("📦 Flipkart Picklist & Label Tool")
    
    uploaded_file = st.file_uploader("Upload Labels PDF", type="pdf")

    if uploaded_file:
        with st.spinner("Analyzing PDF..."):
            all_data = get_pdf_data(uploaded_file, mapping_dict)
            df = pd.DataFrame(all_data)
        
        # --- DEBUG SECTION ---
        if "NOT_FOUND" in df['portal_sku'].values:
            st.warning("Kuch pages par SKU nahi mila. Neeche 'Debug Data' dekhein.")
            with st.expander("Show Debug Data (Kaunse page par error hai?)"):
                st.write(df[['page_no', 'portal_sku', 'm_sku']])

        # --- STEP 1: PICKLIST ---
        st.subheader("📋 Step 1: Picklist Summary")
        if not df.empty:
            # Grouping by Master SKU
            picklist = df.groupby('m_sku').size().reset_index(name='Quantity')
            picklist.columns = ['SKU Name', 'Quantity']
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.dataframe(picklist, hide_index=True, use_container_width=True)
            
            with col2:
                csv = picklist.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Picklist (CSV)", csv, "picklist.csv", "text/csv")
                st.info(f"Total Labels: {len(df)}")

        st.divider()

        # --- STEP 2: LABEL PROCESSING ---
        st.subheader("✂️ Step 2: Crop & Reorder Labels")
        if st.button("🚀 Generate Final Labels PDF", use_container_width=True):
            with st.status("Creating PDF...") as status:
                # Reorder
                df_sorted = df.sort_values(by="m_sku")
                
                writer = PyPDF2.PdfWriter()
                # Coordinates for Crop
                X, Y, W, H = 187, 461, 218, 358

                for _, row in df_sorted.iterrows():
                    p = row['page']
                    p.mediabox.lower_left = (X, Y)
                    p.mediabox.upper_right = (X + W, Y + H)
                    writer.add_page(p)

                output = io.BytesIO()
                writer.write(output)
                output.seek(0)
                
                status.update(label="✅ PDF Ready!", state="complete")
                st.download_button(
                    "📥 Download Sorted Labels", 
                    output, 
                    f"Labels_Sorted_{datetime.now().strftime('%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
