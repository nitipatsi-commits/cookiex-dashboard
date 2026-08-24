import base64
import io
import os
import random
import string
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

# ไลบรารีสำหรับ Google Drive API
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False

# 🟢 ตั้งค่าหน้าเว็บให้รองรับมือถือและจอคอม
st.set_page_config(
    page_title="Cookie X - Admin System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🟢 เชื่อมต่อ Supabase
SUPABASE_URL = "https://dkgeqwmuvgjlaweamhsc.supabase.co"
SUPABASE_KEY = "sb_publishable_GjArIEEPL9ZcIWuOl28J6Q_4QmIeWEk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔒 อ่านค่า Webhook จาก st.secrets
ADMIN_DISCORD_WEBHOOK = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
GDRIVE_FOLDER_ID = st.secrets.get("GDRIVE_FOLDER_ID", "")

# 🟢 ระบบอัปโหลดไฟล์ขึ้น Google Drive
def upload_slip_to_gdrive(file_bytes, filename, mimetype="image/jpeg"):
    """อัปโหลดสลิปไปยังโฟลเดอร์ Google Drive และคืนค่า URL ดูรูปภาพ"""
    if not HAS_GDRIVE:
        raise ImportError("กรุณาติดตั้ง google-api-python-client และ google-auth ก่อนใช้งาน")

    if "gcp_service_account" not in st.secrets:
        raise ValueError("ยังไม่ได้ตั้งค่า [gcp_service_account] ใน st.secrets")

    creds_info = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": filename}
    if GDRIVE_FOLDER_ID:
        file_metadata["parents"] = [GDRIVE_FOLDER_ID]

    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype, resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink, webContentLink"
    ).execute()

    return uploaded

# 🟢 Relay Worker ยิงภาพเข้า Discord
def discord_relay_worker():
    while True:
        try:
            res = supabase.table("user_monitors").select("*").not_.is_("pending_alert_msg", "null").execute()
            rows = res.data
            if rows:
                for row in rows:
                    row_id = row.get("id")
                    msg = row.get("pending_alert_msg")
                    b64_img = row.get("pending_alert_img")
                    row_key = row.get("license_key") or row.get("hwid") or "Unknown"

                    claim_res = supabase.table("user_monitors").update({
                        "pending_alert_msg": None,
                        "pending_alert_img": None
                    }).eq("id", row_id).not_.is_("pending_alert_msg", "null").execute()

                    if not bool(claim_res.data):
                        continue

                    if not msg or str(msg).strip() in ["[NULL]", "None", "null", ""]:
                        continue

                    if ADMIN_DISCORD_WEBHOOK:
                        payload_data = {"content": f"🤖 **[Bot: {row_key}]**\n{msg}"}
                        files = None
                        if b64_img and len(str(b64_img)) > 20:
                            try:
                                img_bytes = base64.b64decode(b64_img)
                                files = {'file': ('screenshot.png', img_bytes, 'image/png')}
                            except Exception:
                                pass
                        requests.post(ADMIN_DISCORD_WEBHOOK, data=payload_data, files=files)
        except Exception:
            pass
        time.sleep(3)

_relay_worker_started = False
_relay_worker_lock = threading.Lock()

def start_relay_worker_once():
    global _relay_worker_started
    with _relay_worker_lock:
        if not _relay_worker_started:
            _relay_worker_started = True
            threading.Thread(target=discord_relay_worker, daemon=True).start()

start_relay_worker_once()

# 🔒 ตรวจสอบ PIN แอดมิน
ADMIN_PIN = st.secrets.get("ADMIN_PIN", "")
if not ADMIN_PIN:
    st.error("❌ ยังไม่ได้ตั้งค่า ADMIN_PIN ใน st.secrets — กรุณาตั้งค่าก่อนใช้งานระบบ")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Admin Authentication")
    st.caption("ระบบจัดการบอท Cookie X (กรุณากรอก PIN เพื่อเข้าใช้งาน)")
    pin_input = st.text_input("กรอกรหัส Admin PIN:", type="password")
    if st.button("เข้าสู่ระบบ"):
        if pin_input == ADMIN_PIN:
            st.session_state.authenticated = True
            st.success("เข้าสู่ระบบสำเร็จ!")
            st.rerun()
        else:
            st.error("รหัส PIN ไม่ถูกต้อง!")
    st.stop()

# ------------------- ส่วนเมนูเลือกใช้งาน -------------------
st.sidebar.title("⚡ Cookie X Control")
menu = st.sidebar.radio(
    "เลือกเมนูใช้งาน", 
    [
        "📊 Live Monitor (มอนิเตอร์บอท)", 
        "🔑 Key Manager (จัดการคีย์)", 
        "💻 Active Sessions (เซสชันจอสด)",
        "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)"
    ]
)

if st.sidebar.button("🚪 ออกจากระบบ"):
    st.session_state.authenticated = False
    st.rerun()

# ---------------------------------------------------------
# 📊 TAB 1: LIVE MONITOR
# ---------------------------------------------------------
if menu == "📊 Live Monitor (มอนิเตอร์บอท)":
    st.title("📊 Live Bot Monitor")
    st.caption("มอนิเตอร์สถานะลูกค้าเรียลไทม์และสเปคฮาร์ดแวร์เครื่องลูกค้า")

    if st.button("🔄 รีเฟรชข้อมูลสด"):
        st.rerun()

    try:
        res = supabase.table("user_monitors").select("*").execute()
        data = res.data
        if data:
            df = pd.DataFrame(data)
            if "last_seen" in df.columns:
                df["last_seen"] = pd.to_datetime(df["last_seen"]).dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            total_bots = len(df)
            active_bots = len(df[df["status"] == "RUNNING"]) if "status" in df.columns else 0
            captcha_bots = len(df[df["current_step"].str.contains("CAPTCHA", na=False)]) if "current_step" in df.columns else 0
            crashed_bots = len(df[df["status"] == "CRASH"]) if "status" in df.columns else 0
            total_boxes = df["boxes_collected"].sum() if "boxes_collected" in df.columns else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🤖 บอททั้งหมด", f"{total_bots} เครื่อง")
            c2.metric("🟢 กำลังรันอยู่", f"{active_bots} เครื่อง")
            c3.metric("🚨 ติด CAPTCHA / Crash", f"{captcha_bots + crashed_bots} เครื่อง")
            c4.metric("📦 ยอดกล่องสะสม", f"{total_boxes:,} กล่อง")

            st.divider()
            show_cols = ["license_key", "status", "current_step", "farm_mode", "boxes_collected", "lives_collected", "cpu_usage", "ram_usage", "pc_specs", "bot_version", "last_seen"]
            existing_cols = [c for c in show_cols if c in df.columns]
            st.dataframe(df[existing_cols], use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มีข้อมูลมอนิเตอร์ในระบบ")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

# ---------------------------------------------------------
# 🔑 TAB 2: KEY MANAGER
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    st.title("🔑 License Key Manager")
    st.caption("ระบบเพิ่ม เพิ่ม/ลดเวลา ปรับยศสิทธิ์ (Normal/Premier) กำหนดจำนวนโควตาจอ และจัดการคีย์ลูกค้า")

    with st.expander("➕ เพิ่มคีย์ใหม่ (Add New License)", expanded=False):
        with st.form("add_key_form"):
            new_key = st.text_input("License Key (เว้นว่างไว้จะสุ่มให้อัตโนมัติ 10 หลัก):", value="")
            key_type_choice = st.selectbox("ประเภทสิทธิ์ใช้งาน:", ["normal", "premier"], format_func=lambda x: "👑 Premier" if x == "premier" else "👤 Normal")
            
            st.markdown("##### ⏱️ กำหนดระยะเวลาใช้งานเริ่มต้น")
            col_d, col_h, col_m = st.columns(3)
            with col_d: add_days = st.number_input("วัน:", min_value=0, max_value=3650, value=30)
            with col_h: add_hours = st.number_input("ชั่วโมง:", min_value=0, max_value=23, value=0)
            with col_m: add_minutes = st.number_input("นาที:", min_value=0, max_value=59, value=0)

            max_sessions_input = st.number_input("จำนวนจอสูงสุด (max_sessions):", min_value=1, max_value=100, value=1)
            submitted = st.form_submit_button("➕ สร้างคีย์ใหม่")

            if submitted:
                final_key = new_key.strip() if new_key.strip() else ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
                tz_th = timezone(timedelta(hours=7))
                exp_datetime = datetime.now(tz_th) + timedelta(days=add_days, hours=add_hours, minutes=add_minutes)

                payload = {
                    "license_key": final_key,
                    "expire_date": exp_datetime.isoformat(),
                    "is_active": True,
                    "is_used": False,
                    "hwid": None,
                    "key_type": key_type_choice,
                    "max_sessions": max_sessions_input
                }
                try:
                    supabase.table("licenses").insert(payload).execute()
                    st.success(f"🎉 สร้างคีย์สำเร็จ! Key: `{final_key}` (หมดอายุ: {exp_datetime.strftime('%Y-%m-%d %H:%M:%S')})")
                except Exception as ex:
                    st.error(f"สร้างคีย์ไม่สำเร็จ: {ex}")

# ---------------------------------------------------------
# 💻 TAB 3: ACTIVE SESSIONS
# ---------------------------------------------------------
elif menu == "💻 Active Sessions (เซสชันจอสด)":
    st.title("💻 Active Sessions Control")
    st.caption("ตรวจสอบและจัดการเซสชันจอที่กำลังเปิดรันอยู่สดๆ ทั้งหมด")

    if st.button("🔄 รีเฟรชรายการเซสชัน"):
        st.rerun()

    try:
        res_sess = supabase.table("active_sessions").select("*").execute()
        sess_data = res_sess.data
        if sess_data:
            df_sess = pd.DataFrame(sess_data)
            if "last_heartbeat" in df_sess.columns:
                df_sess["last_heartbeat"] = pd.to_datetime(df_sess["last_heartbeat"]).dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            st.write(f"📊 **จำนวนจอที่เปิดใช้งานอยู่ขณะนี้:** `{len(df_sess)} จอ`")
            show_sess_cols = ["id", "license_key", "session_id", "hwid", "last_heartbeat"]
            existing_sess_cols = [c for c in show_sess_cols if c in df_sess.columns]
            st.dataframe(df_sess[existing_sess_cols], use_container_width=True, hide_index=True)
        else:
            st.info("ขณะนี้ไม่มีเซสชันจอเปิดรันอยู่ในระบบ")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

# ---------------------------------------------------------
# 💰 TAB 4: บันทึกรายรับ-รายจ่าย & สลิป (GOOGLE DRIVE)
# ---------------------------------------------------------
elif menu == "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)":
    st.title("💰 ระบบบันทึกรายรับ-รายจ่าย & อัปโหลดสลิป")
    st.caption("บันทึกบัญชีร้าน พร้อมอัปโหลดรูปสลิปหลักฐานเก็บเข้า Google Drive อัตโนมัติ")

    # 1. กล่องกรอกข้อมูลรายการบัญชี
    with st.expander("📝 เพิ่มรายการรายรับ / รายจ่ายใหม่", expanded=True):
        with st.form("accounting_form", clear_on_submit=True):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                tx_type = st.radio("ประเภทรายการ:", ["🟢 รายรับ (Income)", "🔴 รายจ่าย (Expense)"], horizontal=True)
                amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=50.0, format="%.2f")
                category = st.selectbox("หมวดหมู่:", ["ขาย License Key", "ต่ออายุบอท", "ค่าโฮสต์/เซิร์ฟเวอร์", "ค่าไฟ/อินเทอร์เน็ต", "ค่าเครื่องมือพัฒนา", "อื่นๆ"])
            with col_t2:
                customer_ref = st.text_input("ชื่อลูกค้า / รหัสคีย์ / หมายเหตุ:", placeholder="เช่น ลูกค้าคีย์ 1 เดือน หรือ คีย์ ID 5")
                tx_date = st.date_input("วันที่ทำรายการ:", value=datetime.now().date())
                slip_file = st.file_uploader("📎 แนบรูปสลิปโอนเงิน (JPG / PNG):", type=["png", "jpg", "jpeg"])

            submit_tx = st.form_submit_button("💾 บันทึกรายการและอัปโหลดสลิป")

            if submit_tx:
                if amount <= 0:
                    st.error("กรุณาระบุจำนวนเงินที่มากกว่า 0 บาท")
                else:
                    slip_url = ""
                    drive_file_id = ""

                    # อัปโหลดรูปสลิปขึ้น Google Drive
                    if slip_file is not None:
                        with st.spinner("⏳ กำลังอัปโหลดสลิปไปยัง Google Drive..."):
                            try:
                                timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
                                clean_filename = f"slip_{timestamp_prefix}_{slip_file.name}"
                                upload_res = upload_slip_to_gdrive(
                                    slip_file.getvalue(),
                                    clean_filename,
                                    mimetype=slip_file.type
                                )
                                drive_file_id = upload_res.get("id", "")
                                slip_url = upload_res.get("webViewLink", "")
                                st.success("☁️ อัปโหลดสลิปขึ้น Google Drive สำเร็จ!")
                            except Exception as ex:
                                st.warning(f"⚠️ บันทึกข้อมูลได้ แต่อัปโหลดสลิปไปยัง Google Drive ไม่สำเร็จ: {ex}")

                    # บันทึกข้อมูลลงตาราง transactions ใน Supabase
                    tx_payload = {
                        "type": "income" if "รายรับ" in tx_type else "expense",
                        "amount": amount,
                        "category": category,
                        "note": customer_ref.strip(),
                        "slip_url": slip_url,
                        "drive_file_id": drive_file_id,
                        "created_at": datetime.combine(tx_date, datetime.now().time()).isoformat()
                    }

                    try:
                        supabase.table("accounting_records").insert(tx_payload).execute()
                        st.success(f"✅ บันทึกรายการ {category} ยอด {amount:,.2f} บาท เรียบร้อยแล้ว!")
                    except Exception as err:
                        st.error(f"บันทึกฐานข้อมูลไม่สำเร็จ: {err} (กรุณาสร้างตาราง accounting_records ใน Supabase)")

    st.divider()

    # 2. รายงานสรุปยอดและตารางประวัติ
    st.subheader("📊 สรุปยอดบัญชีและประวัติรายการ")
    try:
        res_acc = supabase.table("accounting_records").select("*").order("created_at", desc=True).execute()
        acc_data = res_acc.data

        if acc_data:
            df_acc = pd.DataFrame(acc_data)
            
            # คำนวณยอดรวม
            total_income = df_acc[df_acc["type"] == "income"]["amount"].sum()
            total_expense = df_acc[df_acc["type"] == "expense"]["amount"].sum()
            net_profit = total_income - total_expense

            m1, m2, m3 = st.columns(3)
            m1.metric("🟢 รายรับรวม", f"฿ {total_income:,.2f}")
            m2.metric("🔴 รายจ่ายรวม", f"฿ {total_expense:,.2f}")
            m3.metric("💵 กำไรสุทธิ (Net)", f"฿ {net_profit:,.2f}", delta=f"{net_profit:,.2f}")

            st.write("")
            # จัดการ Format ตารางแสดงผล
            df_acc["ประเภท"] = df_acc["type"].map({"income": "🟢 รายรับ", "expense": "🔴 รายจ่าย"})
            df_acc["ยอดเงิน (บาท)"] = df_acc["amount"].map(lambda x: f"{x:,.2f}")
            df_acc["วันที่"] = pd.to_datetime(df_acc["created_at"]).dt.strftime("%Y-%m-%d %H:%M")

            display_cols = ["id", "วันที่", "ประเภท", "หมวดหมู่", "ยอดเงิน (บาท)", "note", "slip_url"]
            valid_disp_cols = [c for c in display_cols if c in df_acc.columns]
            
            st.dataframe(
                df_acc[valid_disp_cols],
                column_config={
                    "slip_url": st.column_config.LinkColumn("สลิปบน Google Drive", display_text="📂 เปิดดูรูปสลิป")
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("ยังไม่มีรายการบัญชีในระบบ")
    except Exception as e:
        st.info("💡 พร้อมใช้งาน: สร้างตาราง `accounting_records` ใน Supabase แล้วเริ่มบันทึกรายการได้ทันทีครับ")
