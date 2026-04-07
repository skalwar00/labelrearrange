import streamlit as st
import pdfplumber
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io
import re
import pandas as pd
from supabase import create_client, Client

# --- 1. CONFIG ---
st.set_page_config(page_title="Flipkart Label Reorder Tool", layout="wide", page_icon="📦")

# --- 2. SUPABASE CONNECTION ---
try:
    url, key = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except:
    st.error("Supabase Secrets Missing! Check Settings > Secrets.")
    st.stop()

# --- 3. USER LOGIN ---
if 'user' not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("📦 Flipkart Label Reorder Tool")
    with st.sidebar:
        mode = st.radio("Action", ["Login", "Signup"])
        with st.form("auth"):
            e, p = st.text_input("Email"), st.text_input("Password", type="password")
            if st.form_submit_button("Submit"):
                try:
                    func = supabase.auth.sign_in_with_password if mode=="Login" else supabase.auth.sign_up
                    res = func({"email": e, "password": p})
                    if res.user:
                        st.session_state.user = res.user
                        st.experimental_rerun()
                except:
                    st.error("Login Failed")
    st.stop()

u_id = st.session_state.user.id

# --- 4. FETCH MAPPING FROM SUPABASE ---
@st.cache_data(ttl=300)
def load_mapping(u_id):
    res = supabase.table("sku_mapping").select("portal_sku, master_sku").eq("user_id", u_id).execute()
    return {item['portal_sku'].upper(): item['master_sku'].upper() for item in res.data} if res.data else {}

mapping_dict = load_mapping(u_id)

st.sidebar.success(f"Logged in as: {st.session_state.user.email}")

# --- 5. UPLOAD FLIPKART PDF ---
st.header("📥 Upload Flipkart PDF Labels")
pdf_file = st.file_uploader("Choose Flipkart PDF", type=["pdf"])

def extract_blocks(pdf_file):
    blocks = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            # Split on "ORDERED THROUGH" keyword (unique start of each label)
            temp_blocks = text.split("ORDERED THROUGH")
            temp_blocks = [("ORDERED THROUGH" + b).strip() for b in temp_blocks if b.strip()]
            blocks.extend(temp_blocks)
    return blocks

def find_sku(block):
    match = re.search(r'(FM[P|C]\d{10,12})', block)
    return match.group(0).upper() if match else "UNKNOWN"

def reorder_blocks(blocks, mapping_dict):
    mapped_blocks = [(block, mapping_dict.get(find_sku(block), find_sku(block))) for block in blocks]
    # Sort by Master SKU
    mapped_blocks.sort(key=lambda x: x[1])
    return [x[0] for x in mapped_blocks]

def create_pdf(blocks):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica", 10)
    for block in blocks:
        for line in block.split("\n"):
            if y < 50:
                c.showPage()
                y = height - 50
            c.drawString(30, y, line)
            y -= 12
        y -= 10  # spacing between labels
    c.save()
    buffer.seek(0)
    return buffer

if pdf_file:
    try:
        blocks = extract_blocks(pdf_file)
        st.success(f"✅ Extracted {len(blocks)} labels")

        if st.button("🔀 Reorder by Master SKU"):
            reordered = reorder_blocks(blocks, mapping_dict)
            pdf_buffer = create_pdf(reordered)
            st.download_button("📥 Download Reordered PDF", pdf_buffer, "reordered_labels.pdf", "application/pdf")
            st.success("Done! Labels reordered successfully.")
    except Exception as e:
        st.error(f"Error processing PDF: {e}")
