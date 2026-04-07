# app.py
import streamlit as st
import pandas as pd
import pdfplumber
import io
from thefuzz import fuzz
from supabase import create_client, Client
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- 1. Page Config ---
st.set_page_config(page_title="Flipkart Label Reorder", layout="wide", page_icon="📄")
st.title("📄 Flipkart PDF Label Reorder Tool")

# --- 2. Supabase Connection ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("❌ Supabase Connection Failed! Check Secrets.")
    st.stop()

# --- 3. User Authentication (Optional) ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    with st.sidebar:
        st.subheader("Login")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                if res.user:
                    st.session_state.user = res.user
                    st.success(f"Logged in as {res.user.email}")
                    st.experimental_rerun()
                else:
                    st.error("Login Failed!")
            except Exception as e:
                st.error(f"Error: {e}")
    st.stop()

user_id = st.session_state.user.id

# --- 4. Fetch Mapping from Supabase ---
@st.cache_data(ttl=300)
def load_mapping(user_id):
    try:
        res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", user_id).execute()
        if res.data:
            mapping_dict = {item['portal_sku'].upper(): item['master_sku'].upper() for item in res.data}
        else:
            mapping_dict = {}
        return mapping_dict
    except Exception as e:
        st.error(f"Supabase fetch failed: {e}")
        return {}

mapping_dict = load_mapping(user_id)
st.sidebar.info(f"Loaded {len(mapping_dict)} SKU mappings")

# --- 5. PDF Upload ---
st.header("📥 Upload Flipkart PDF Labels")
pdf_file = st.file_uploader("Choose PDF", type=["pdf"])

# --- 6. Functions ---
def get_design_pattern(master_sku):
    sku = str(master_sku).upper().strip()
    sku = re.sub(r'[-_](S|M|L|XL|XXL|\d*XL|FREE|SMALL|LARGE)$', '', sku)
    sku = re.sub(r'\(.*?\)', '', sku)
    return sku.strip('-_ ')

def extract_labels(pdf_file):
    labels = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # skip header
                    if row and row[0]:
                        labels.append(row[0].upper())
    return labels

def reorder_labels(labels, mapping_dict):
    mapped_labels = [(label, mapping_dict.get(label, "UNKNOWN")) for label in labels]
    mapped_labels.sort(key=lambda x: x[1])
    return [x[0] for x in mapped_labels]

def generate_pdf(labels):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y + 20, "Reordered Flipkart Labels")
    c.setFont("Helvetica", 12)
    for label in labels:
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, label)
        y -= 20
    c.save()
    buffer.seek(0)
    return buffer

# --- 7. Run Tool ---
if pdf_file:
    labels = extract_labels(pdf_file)
    st.success(f"✅ Found {len(labels)} labels in PDF")

    if st.button("Reorder PDF"):
        reordered = reorder_labels(labels, mapping_dict)
        pdf_buffer = generate_pdf(reordered)
        st.download_button(
            "📥 Download Reordered PDF",
            data=pdf_buffer,
            file_name="reordered_labels.pdf",
            mime="application/pdf"
        )
        st.success("Reordered PDF Ready ✅")
