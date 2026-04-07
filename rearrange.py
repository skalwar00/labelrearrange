import streamlit as st
import io
import re
import PyPDF2
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Pro Tool", layout="wide", page_icon="📦")

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .stDownloadButton { width: 100%; }
    .stButton { width: 100%; }
    </style>
""", unsafe_allow_html=True)

# --- Supabase Setup ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error("Supabase configuration missing or invalid.")
        return None

supabase = init_connection()

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
                st.session_state.user = res.user
                st.rerun()
            except Exception as ex:
                st.error("Invalid credentials. Please try again.")
else:
    # Sidebar Info
    u_id = st.session_state.user.id
    st.sidebar.title("User Profile")
    st.sidebar.info(f"Logged in as: \n{st.session_state.user.email}")
    
    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # ----------------- 3. DATA MAPPING -----------------
    @st.cache_data(ttl=300) # Increased TTL to 5 mins for better performance
    def load_mapping(user_id):
        try:
            res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
            return {str(item['portal_sku']).strip().upper(): str(item['master_sku']).strip().upper() for item in res.data} if res.data else {}
        except Exception:
            return {}

    mapping_dict = load_mapping(u_id)

    # ----------------- 4. LOGIC ENGINE -----------------
    def get_pdf_data(file, mapping):
        reader = PyPDF2.PdfReader(file)
        data = []
        
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            text = page.extract_text() or ""
            
            # Robust matching: Look for the quantity '1' followed by SKU before the pipe
            match = re.search(r'1\s+([A-Z0-9._-]+)\s*\|', text)
            
            if match:
                p_sku = match.group(1).strip().upper()
            else:
                p_sku = "UNKNOWN_SKU"
            
            m_sku = mapping.get(p_sku, p_sku) 
            
            data.append({
                "page_obj": page, # Keep the object for cropping
                "portal_sku": p_sku, 
                "m_sku": m_sku,
                "page_no": i + 1
            })
        return data

    # ----------------- 5. UI INTERFACE -----------------
    st.title("📦 Flipkart Order Processor")
    
    uploaded_file = st.file_uploader("Upload Flipkart Labels PDF", type="pdf")

    if uploaded_file:
        with st.spinner("Analyzing PDF..."):
            all_data = get_pdf_data(uploaded_file, mapping_dict)
            df = pd.DataFrame(all_data)

        # --- PICKLIST SECTION ---
        st.subheader("📋 Step 1: Inventory Picklist")
        if not df.empty:
            # Grouping Logic
            picklist = df.groupby('m_sku').size().reset_index(name='Qty')
            picklist.columns = ['Master SKU', 'Quantity']
            
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                st.dataframe(picklist, hide_index=True, use_container_width=True)
            with c2:
                csv = picklist.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download CSV", csv, "picklist.csv", "text/csv")
            with c3:
                st.metric("Total Items", len(df))

        st.divider()

        # --- LABEL PROCESSING SECTION ---
        st.subheader("✂️ Step 2: Generate Sorted Labels")
        st.info("Labels will be cropped to 4x6 size and sorted by Master SKU for faster packing.")
        
        if st.button("🚀 Process & Download Sorted PDF"):
            with st.status("Generating PDF...") as status:
                df_sorted = df.sort_values(by="m_sku")
                writer = PyPDF2.PdfWriter()
                
                # Calibration (Standard Flipkart Label Crop)
                # These coordinates may vary slightly based on printer thermal settings
                X, Y, W, H = 187, 461, 218, 358

                for _, row in df_sorted.iterrows():
                    p = row['page_obj']
                    p.mediabox.lower_left = (X, Y)
                    p.mediabox.upper_right = (X + W, Y + H)
                    writer.add_page(p)

                output = io.BytesIO()
                writer.write(output)
                output.seek(0)
                
                status.update(label="✅ Ready!", state="complete")
                
                st.download_button(
                    "📥 Click to Download Sorted_Labels.pdf", 
                    output, 
                    f"Labels_{datetime.now().strftime('%d%m_%H%M')}.pdf",
                    mime="application/pdf"
                )

    # Sidebar Mapping Preview
    with st.sidebar.expander("🔍 View Active Mappings"):
        if mapping_dict:
            st.write(pd.DataFrame(list(mapping_dict.items()), columns=["Portal SKU", "Master SKU"]))
        else:
            st.warning("No mappings found.")
