import streamlit as st
import io
import re
import pypdf
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

# ----------------- 1. CONFIG -----------------
st.set_page_config(page_title="Flipkart Ultra Tool", layout="wide", page_icon="📦")

# Supabase Initialization
@st.cache_resource
def init_supabase():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        st.error("Supabase credentials missing!")
        return None

supabase = init_supabase()

if 'user' not in st.session_state:
    st.session_state.user = None

# ----------------- 2. AUTHENTICATION -----------------
if st.session_state.user is None:
    st.title("🔐 Flipkart Tool - Login")
    with st.form("auth"):
        e = st.text_input("Email")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": e, "password": p})
                st.session_state.user = res.user
                st.rerun()
            except Exception as ex:
                st.error("Invalid Login Details")
else:
    # Sidebar UI
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
            return {str(item['portal_sku']).strip().upper(): str(item['master_sku']).strip().upper() for item in res.data}
        except:
            return {}

    mapping_dict = load_mapping(u_id)

    # ----------------- 4. ULTRA-FAST ENGINE -----------------
    def process_labels(file_bytes, mapping):
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_data = []
        
        # Regex Patterns (Multiple checks to avoid UNKNOWN)
        # 1. Standard: 1 [SKU] |
        # 2. Backup: 1 [SKU] (without pipe)
        pattern1 = re.compile(r'1\s+([^\s|]+)\s*\|')
        pattern2 = re.compile(r'1\s+([A-Z0-9._\-/]+)')

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            p_sku = "UNKNOWN"

            # Match dhundne ki koshish
            match1 = pattern1.search(text)
            match2 = pattern2.search(text)

            if match1:
                p_sku = match1.group(1).strip().upper()
            elif match2:
                p_sku = match2.group(1).strip().upper()

            # Mapping apply karein
            m_sku = mapping.get(p_sku, p_sku)
            
            extracted_data.append({
                "p_sku": p_sku,
                "m_sku": m_sku,
                "page_idx": i
            })
            
        return extracted_data, reader

    # ----------------- 5. MAIN UI -----------------
    st.title("📦 Flipkart Order Processor (Fast Mode)")
    
    uploaded_file = st.file_uploader("Upload Labels PDF", type="pdf")

    if uploaded_file:
        # File read as bytes for performance
        file_bytes = uploaded_file.read()
        
        with st.spinner("⚡ Scanning PDF..."):
            all_data, reader = process_labels(file_bytes, mapping_dict)
            df = pd.DataFrame(all_data)

        # UI: Picklist & Download
        st.subheader("📋 Picklist Summary")
        if not df.empty:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Grouping by Master SKU
                summary = df.groupby('m_sku').size().reset_index(name='Qty')
                st.dataframe(summary, use_container_width=True, hide_index=True)
            
            with col2:
                st.metric("Total Labels", len(df))
                csv = summary.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download CSV", csv, "picklist.csv", "text/csv")
                
                # Check for UNKNOWNs
                unknown_count = len(df[df['p_sku'] == "UNKNOWN"])
                if unknown_count > 0:
                    st.warning(f"⚠️ {unknown_count} labels mein SKU nahi mila. Ek baar PDF format check karein.")

        st.divider()

        # STEP 2: CROPPING & SORTING
        st.subheader("✂️ Generate Organized PDF")
        if st.button("🚀 Process & Download Final Labels", use_container_width=True):
            with st.status("Generating High-Speed PDF...") as status:
                # Master SKU ke hisaab se sort karein
                df_sorted = df.sort_values(by="m_sku")
                writer = pypdf.PdfWriter()
                
                # Flipkart 4x6 Crop Coordinates
                X, Y, W, H = 187, 461, 218, 358

                for _, row in df_sorted.iterrows():
                    page = reader.pages[row['page_idx']]
                    page.mediabox.lower_left = (X, Y)
                    page.mediabox.upper_right = (X + W, Y + H)
                    writer.add_page(page)

                output = io.BytesIO()
                writer.write(output)
                
                status.update(label="✅ PDF Ready!", state="complete")
                
                st.download_button(
                    label="📥 Download Sorted PDF",
                    data=output.getvalue(),
                    file_name=f"Labels_{datetime.now().strftime('%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

    # Sidebar Mapping Preview
    with st.sidebar.expander("🔍 SKU Mapping Preview"):
        if mapping_dict:
            st.json(mapping_dict)
        else:
            st.write("No mappings found.")
