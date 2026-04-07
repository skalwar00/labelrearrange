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
    @st.cache_data(ttl=300)
    def load_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            return {item['portal_sku'].upper().strip(): item['master_sku'].upper().strip() for item in res.data} if res.data else {}
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
            match = re.search(r'(FM[P|C]\d{10,12})', text)
            p_sku = match.group(0).upper() if match else "UNKNOWN"
            m_sku = mapping.get(p_sku, p_sku)
            data.append({"page": page, "p_sku": p_sku, "m_sku": m_sku})
        return data

    # ----------------- 5. UI -----------------
    st.title("📦 Flipkart Picklist & Label Tool")
    
    uploaded_file = st.file_uploader("Upload Labels PDF", type="pdf")

    if uploaded_file:
        # Process data once
        with st.spinner("Analyzing PDF..."):
            all_data = get_pdf_data(uploaded_file, mapping_dict)
            df = pd.DataFrame(all_data)
        
        # --- STEP 1: PICKLIST ---
        st.subheader("📋 Step 1: Picklist Summary")
        if not df.empty:
            # Count occurrences of Master SKU
            picklist = df['m_sku'].value_counts().reset_index()
            picklist.columns = ['Master SKU', 'Quantity']
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.dataframe(picklist, hide_index=True, use_container_width=True)
            
            with col2:
                # Convert picklist to CSV for download
                csv = picklist.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Picklist (CSV)", csv, "picklist.csv", "text/csv")
                st.info(f"Total Labels Found: {len(df)}")

        st.divider()

        # --- STEP 2: LABEL PROCESSING ---
        st.subheader("✂️ Step 2: Crop & Reorder Labels")
        if st.button("🚀 Generate Final Labels PDF", use_container_width=True):
            with st.status("Creating PDF...") as status:
                # Reorder by Master SKU
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
                    f"Labels_{datetime.now().strftime('%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
