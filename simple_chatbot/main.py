import streamlit as st
import os
from dotenv import load_dotenv
import requests
import pandas as pd
from io import StringIO
import re

try:
    import google.generativeai as genai
except ImportError:
    st.error("Modul 'google-generativeai' belum terinstall. Jalankan: pip install google-generativeai")
    st.stop()

# --- Tambahan untuk update Google Sheets ---
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    st.error("Modul 'gspread' dan 'google-auth' belum terinstall. Jalankan: pip install gspread google-auth")
    st.stop()

# --- Konfigurasi API Key Gemini ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("GEMINI_API_KEY belum diatur di file .env atau di secrets Streamlit Cloud.")
    st.stop()
genai.configure(api_key=api_key)

ROLES = {
    "Admin": {
        "system_prompt": "You are the admin. You can upload and manage the knowledge base."
    },
    "AM": {
        "system_prompt": "You are an Account Manager (AM). Jawab pertanyaan terkait tugas dan tanggung jawab AM berdasarkan knowledge base."
    },
    "HOTD": {
        "system_prompt": "You are Head of the Department (HOTD). Jawab pertanyaan terkait kebijakan dan keputusan HOTD berdasarkan knowledge base."
    },
    "Unit BS": {
        "system_prompt": "You are a staff of Unit BS. Jawab pertanyaan terkait operasional dan tugas Unit BS berdasarkan knowledge base."
    }
}

def load_gsheet_csv(csv_url):
    try:
        response = requests.get(csv_url)
        if response.status_code == 200:
            return pd.read_csv(StringIO(response.text))
        else:
            return None
    except Exception:
        return None

# --- Fungsi update Google Sheets untuk kolom apapun ---
def update_gsheet_column(sid, column_name, new_value, sheet_id, worksheet_name="Sheet1"):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    import json
    service_account_info = json.loads(st.secrets["SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.worksheet(worksheet_name)
    data = worksheet.get_all_records()
    updated = False

    # Normalisasi nama kolom untuk pencarian fleksibel
    def norm(s): return s.strip().lower().replace(" ", "")
    norm_col = norm(column_name)
    for idx, row in enumerate(data, start=2):  # Mulai dari 2 karena header di baris 1
        if str(row.get("SID", "")).strip() == str(sid):
            col_names = list(row.keys())
            for i, col in enumerate(col_names):
                if norm(col) == norm_col:
                    worksheet.update_cell(idx, i + 1, new_value)
                    updated = True
                    break
            break
    return updated

GSHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1uzrmQBcTCFmDGtVW4oFc0YCVN6zDgHDUoNVBOietUyM/export?format=csv"
kb_title = "https://docs.google.com/spreadsheets/d/1uzrmQBcTCFmDGtVW4oFc0YCVN6zDgHDUoNVBOietUyM/edit?usp=sharing"
GSHEET_ID = "1uzrmQBcTCFmDGtVW4oFc0YCVN6zDgHDUoNVBOietUyM"

# --- Reload DataFrame setiap kali agar user lain dapat melihat update terbaru ---
def get_latest_df():
    return load_gsheet_csv(GSHEET_CSV_URL)

df = get_latest_df()
if df is None:
    st.warning("Knowledge base belum tersedia atau file Google Sheets tidak bisa diakses. Silakan hubungi admin.")
    st.stop()

kb_summary = f"Data berhasil dimuat. Kolom: {', '.join(df.columns)}. Jumlah baris: {len(df)}"

with st.sidebar:
    st.header("Monitoring End Contract Witel JKO")
    st.subheader("🎭 Select Role")
    selected_role = st.selectbox(
        "Choose your role:",
        options=list(ROLES.keys())
    )
    st.subheader("📚 Knowledge Base")
    st.info(f"Knowledge base file: [Lihat di Google Sheets]({kb_title})")
    st.caption(kb_summary)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

model = genai.GenerativeModel("gemini-1.5-flash")

prompt = st.chat_input("Tanyakan sesuatu sesuai knowledge base!")
admin_update_result = ""

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").markdown(prompt)

    system_prompt = ROLES[selected_role]["system_prompt"]

    # --- ADMIN: Deteksi perintah update kolom apapun pada SID ---
    admin_update_result = ""
    if selected_role == "Admin":
        # Deteksi perintah: ganti nama AM pada SID ... menjadi ...
        match = re.search(r"ganti nama ([\w ]+)\s*pada sid\s*(\d+)\s*menjadi\s*([^\n]+)", prompt.lower())
        if match:
            col_name = match.group(1)
            sid = match.group(2)
            new_value = match.group(3).strip()
            try:
                updated = update_gsheet_column(sid, col_name, new_value, GSHEET_ID)
                if updated:
                    admin_update_result = f"Kolom {col_name.upper()} pada SID {sid} berhasil diubah menjadi {new_value} di Google Sheets."
                    df = get_latest_df()
                else:
                    admin_update_result = f"SID {sid} atau kolom {col_name.upper()} tidak ditemukan di Google Sheets."
            except Exception as e:
                admin_update_result = f"Gagal mengupdate Google Sheets: {e}"
        else:
            # Deteksi perintah: SID ... ubah menjadi NAMA AM ...
            match2 = re.search(r"sid\s*(\d+)\s*ubah\s*menjadi\s*nama am\s*([^\n]+)", prompt.lower())
            if match2:
                sid = match2.group(1)
                new_value = match2.group(2).strip()
                try:
                    updated = update_gsheet_column(sid, "AM", new_value, GSHEET_ID)
                    if updated:
                        admin_update_result = f"NAMA AM pada SID {sid} berhasil diubah menjadi {new_value} di Google Sheets."
                        df = get_latest_df()
                    else:
                        admin_update_result = f"SID {sid} atau kolom AM tidak ditemukan di Google Sheets."
                except Exception as e:
                    admin_update_result = f"Gagal mengupdate Google Sheets: {e}"
            else:
                # Tetap support perintah ubah status SID ... menjadi ...
                match_status = re.search(r"ubah status sid (\d+)\s*menjadi\s*([^\n]+)", prompt.lower())
                if match_status:
                    sid = match_status.group(1)
                    new_status = match_status.group(2).strip().upper()
                    try:
                        updated = update_gsheet_column(sid, "Status", new_status, GSHEET_ID)
                        if updated:
                            admin_update_result = f"Status SID {sid} berhasil diubah menjadi {new_status} di Google Sheets."
                            df = get_latest_df()
                        else:
                            admin_update_result = f"SID {sid} tidak ditemukan di Google Sheets."
                    except Exception as e:
                        admin_update_result = f"Gagal mengupdate Google Sheets: {e}"

    # Kirim seluruh data (atau 23 baris pertama jika data besar) ke Gemini
    data_preview = df.head(23).to_string(index=False)
    full_prompt = (
        f"{system_prompt}\n"
        f"Berikut adalah data knowledge base (23 baris pertama):\n{data_preview}\n"
        f"Jawablah pertanyaan user hanya berdasarkan data di atas.\n"
        f"User: {prompt}"
    )

    if admin_update_result:
        assistant_reply = admin_update_result
    else:
        try:
            response = model.generate_content(full_prompt)
            assistant_reply = response.text
        except Exception as e:
            assistant_reply = f"Terjadi error saat memproses permintaan: {e}"

    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
    with st.chat_message("assistant"):
        st.markdown(assistant_reply)