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
# 💰 TAB 4: บันทึกรายรับ-รายจ่าย & สลิป (GOOGLE DRIVE + DISCORD + EXPORT)
# ---------------------------------------------------------
elif menu == "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)":
    st.title("💰 ระบบบันทึกรายรับ-รายจ่าย & บัญชีร้าน")
    st.caption("ระบบจัดการการเงินครบวงจร บันทึกบัญชี แนบสลิป Google Drive สรุปกราฟ และส่งออกข้อมูล")

    # ฟังก์ชันลบไฟล์สลิปออกจาก Google Drive
    def delete_file_from_gdrive(file_id):
        if not file_id:
            return
        try:
            if not HAS_GDRIVE or "gcp_service_account" not in st.secrets:
                return
            creds_info = dict(st.secrets["gcp_service_account"])
            creds = service_account.Credentials.from_service_account_info(
                creds_info, scopes=["https://www.googleapis.com/auth/drive"]
            )
            service = build("drive", "v3", credentials=creds)
            service.files().delete(fileId=file_id).execute()
        except Exception:
            pass

    # ฟังก์ชันส่งแจ้งเตือนเข้า Discord
    def send_discord_accounting_alert(tx_type, amount, category, note, slip_url=""):
        webhook_url = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
        if not webhook_url:
            return
        try:
            is_income = "income" in tx_type.lower() or "รายรับ" in tx_type
            color = 5763719 if is_income else 15548997  # เขียว / แดง
            title = "🟢 บันทึกรายรับใหม่" if is_income else "🔴 บันทึกรายจ่ายใหม่"
            
            fields = [
                {"name": "💵 จำนวนเงิน", "value": f"**฿{amount:,.2f}**", "inline": True},
                {"name": "📂 หมวดหมู่", "value": category, "inline": True},
                {"name": "📝 หมายเหตุ / ลูกค้า", "value": note or "-", "inline": False},
            ]
            if slip_url:
                fields.append({"name": "📎 ลิงก์สลิป Google Drive", "value": f"[คลิกเพื่อดูสลิป]({slip_url})", "inline": False})

            payload = {
                "embeds": [{
                    "title": title,
                    "color": color,
                    "fields": fields,
                    "footer": {"text": f"ระบบบัญชีอัตโนมัติ • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                }]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception:
            pass

    # ==========================================
    # 1. ฟอร์มเพิ่มรายการใหม่
    # ==========================================
    with st.expander("➕ เพิ่มรายการรายรับ / รายจ่ายใหม่", expanded=False):
        with st.form("accounting_form", clear_on_submit=True):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                tx_type = st.radio("ประเภทรายการ:", ["🟢 รายรับ (Income)", "🔴 รายจ่าย (Expense)"], horizontal=True)
                amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, step=50.0, format="%.2f")
                category = st.selectbox("หมวดหมู่:", ["ขาย License Key", "ต่ออายุบอท", "ค่าโฮสต์/เซิร์ฟเวอร์", "ค่าไฟ/อินเทอร์เน็ต", "ค่าเครื่องมือพัฒนา", "อื่นๆ"])
                customer_ref = st.text_input("👤 ชื่อลูกค้า / รหัสคีย์อ้างอิง:", placeholder="เช่น King Sky (DC) หรือ คีย์ AB12CD")

            with col_t2:
                tx_date = st.date_input("วันที่ทำรายการ:", value=datetime.now().date())
                slip_file = st.file_uploader("📎 แนบรูปสลิปโอนเงิน (JPG / PNG):", type=["png", "jpg", "jpeg"])
                extra_note = st.text_area("📝 หมายเหตุเพิ่มเติม (Note):", placeholder="เช่น คีย์ 7 วัน / โอนเข้ากสิกร นายนิธิภัทร", height=68)

            send_noti = st.checkbox("🔔 ส่งการแจ้งเตือนรายการนี้เข้าห้อง Discord", value=True)
            submit_tx = st.form_submit_button("💾 บันทึกรายการและอัปโหลดสลิป")

            if submit_tx:
                if amount <= 0:
                    st.error("กรุณาระบุจำนวนเงินที่มากกว่า 0 บาท")
                else:
                    slip_url = ""
                    drive_file_id = ""

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
                                st.warning(f"⚠️ บันทึกข้อมูลได้ แต่อัปโหลดสลิปไม่สำเร็จ: {ex}")

                    combined_note = ""
                    if customer_ref.strip() and extra_note.strip():
                        combined_note = f"{customer_ref.strip()} | {extra_note.strip()}"
                    else:
                        combined_note = customer_ref.strip() or extra_note.strip()

                    tx_payload = {
                        "type": "income" if "รายรับ" in tx_type else "expense",
                        "amount": amount,
                        "category": category,
                        "note": combined_note,
                        "slip_url": slip_url,
                        "drive_file_id": drive_file_id,
                        "created_at": datetime.combine(tx_date, datetime.now().time()).isoformat()
                    }

                    try:
                        supabase.table("accounting_records").insert(tx_payload).execute()
                        if send_noti:
                            send_discord_accounting_alert(tx_type, amount, category, combined_note, slip_url)
                        st.success(f"✅ บันทึกรายการ {category} ยอด {amount:,.2f} บาท เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"บันทึกฐานข้อมูลไม่สำเร็จ: {err}")

    st.divider()

    # ==========================================
    # 2. ตัวกรองข้อมูล & รายงานสรุปยอด
    # ==========================================
    st.subheader("📊 สรุปยอดบัญชีและประวัติรายการ")
    
    try:
        res_acc = supabase.table("accounting_records").select("*").order("created_at", desc=True).execute()
        acc_data = res_acc.data

        if acc_data:
            df_all = pd.DataFrame(acc_data)
            df_all["created_at"] = pd.to_datetime(df_all["created_at"])
            df_all["date_only"] = df_all["created_at"].dt.date

            # --- ตัวกรอง (Filters) ---
            f_col1, f_col2, f_col3 = st.columns([1.5, 1.5, 2])
            with f_col1:
                filter_period = st.selectbox("📅 ช่วงเวลา:", ["ทั้งหมด", "เดือนนี้ (This Month)", "เดือนที่แล้ว", "กำหนดช่วงวันที่เอง"])
            
            with f_col2:
                all_cats = ["ทั้งหมด"] + sorted(list(df_all["category"].dropna().unique()))
                filter_cat = st.selectbox("📂 หมวดหมู่:", all_cats)

            with f_col3:
                search_kw = st.text_input("🔍 ค้นหา (ชื่อลูกค้า / หมายเหตุ):", placeholder="พิมพ์คำค้นหา...")

            # คำนวณช่วงวันที่ตามตัวเลือก
            today = datetime.now().date()
            if filter_period == "เดือนนี้ (This Month)":
                df_filtered = df_all[(df_all["created_at"].dt.year == today.year) & (df_all["created_at"].dt.month == today.month)]
            elif filter_period == "เดือนที่แล้ว":
                first_this_month = today.replace(day=1)
                last_month_end = first_this_month - timedelta(days=1)
                df_filtered = df_all[(df_all["created_at"].dt.year == last_month_end.year) & (df_all["created_at"].dt.month == last_month_end.month)]
            elif filter_period == "กำหนดช่วงวันที่เอง":
                dr1, dr2 = st.date_input("เลือกช่วงวันที่:", [today - timedelta(days=30), today])
                if isinstance(dr1, datetime) or isinstance(dr1, date):
                    df_filtered = df_all[(df_all["date_only"] >= dr1) & (df_all["date_only"] <= dr2)]
                else:
                    df_filtered = df_all
            else:
                df_filtered = df_all

            # กรองตามหมวดหมู่และคำค้นหา
            if filter_cat != "ทั้งหมด":
                df_filtered = df_filtered[df_filtered["category"] == filter_cat]
            if search_kw.strip():
                df_filtered = df_filtered[df_filtered["note"].fillna("").str.contains(search_kw.strip(), case=False)]

            # แสดงตัวเลข Metrics สรุปยอด
            total_income = df_filtered[df_filtered["type"] == "income"]["amount"].sum()
            total_expense = df_filtered[df_filtered["type"] == "expense"]["amount"].sum()
            net_profit = total_income - total_expense

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🟢 รายรับรวม", f"฿ {total_income:,.2f}")
            m2.metric("🔴 รายจ่ายรวม", f"฿ {total_expense:,.2f}")
            m3.metric("💵 กำไรสุทธิ (Net)", f"฿ {net_profit:,.2f}", delta=f"{net_profit:,.2f}")
            m4.metric("📑 จำนวนรายการ", f"{len(df_filtered):,} รายการ")

            # กราฟสรุปยอดรายรับ-รายจ่ายรายวัน
            if not df_filtered.empty:
                with st.expander("📈 กราฟแนวโน้มรายรับ - รายจ่าย", expanded=False):
                    chart_df = df_filtered.copy()
                    chart_df["date_str"] = chart_df["created_at"].dt.strftime("%Y-%m-%d")
                    pivot_chart = chart_df.pivot_table(index="date_str", columns="type", values="amount", aggfunc="sum", fill_value=0)
                    if "income" not in pivot_chart.columns: pivot_chart["income"] = 0
                    if "expense" not in pivot_chart.columns: pivot_chart["expense"] = 0
                    pivot_chart = pivot_chart.rename(columns={"income": "รายรับ (Income)", "expense": "รายจ่าย (Expense)"})
                    st.bar_chart(pivot_chart, color=["#22c55e", "#ef4444"])

            # ตารางแสดงข้อมูล
            df_display = df_filtered.copy()
            df_display["ประเภท"] = df_display["type"].map({"income": "🟢 รายรับ", "expense": "🔴 รายจ่าย"})
            df_display["ยอดเงิน (บาท)"] = df_display["amount"].map(lambda x: f"{x:,.2f}")
            df_display["วันที่"] = df_display["created_at"].dt.strftime("%Y-%m-%d %H:%M")

            display_cols = ["id", "วันที่", "ประเภท", "หมวดหมู่", "ยอดเงิน (บาท)", "note", "slip_url"]
            valid_disp_cols = [c for c in display_cols if c in df_display.columns]

            st.dataframe(
                df_display[valid_disp_cols],
                column_config={
                    "id": st.column_config.NumberColumn("ID รายการ", format="%d"),
                    "note": st.column_config.TextColumn("ลูกค้า / หมายเหตุ (Note)"),
                    "slip_url": st.column_config.LinkColumn("สลิป Google Drive", display_text="📂 เปิดดูรูปสลิป")
                },
                use_container_width=True,
                hide_index=True
            )

            # ปุ่มส่งออกข้อมูล (Export to CSV)
            csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 ดาวน์โหลดประวัติบัญชี (Export to CSV)",
                data=csv_data,
                file_name=f"accounting_report_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

            st.divider()

            # ==========================================
            # 3. เครื่องมือจัดการรายการ (แก้ไข & ลบ)
            # ==========================================
            tab_edit, tab_delete = st.tabs(["✏️ แก้ไขรายการ (Edit)", "🗑️ ลบรายการ (Delete)"])

            with tab_edit:
                options_list = [
                    f"ID: {item['id']} | [{item.get('type','').upper()}] {item.get('category','')} - ฿{float(item.get('amount',0)):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
                    for item in acc_data
                ]
                selected_edit_str = st.selectbox("เลือกรายการที่ต้องการแก้ไข:", options_list, key="sel_edit_tx")

                if selected_edit_str:
                    edit_id = int(selected_edit_str.split("ID: ")[1].split(" |")[0])
                    edit_row = next((r for r in acc_data if r["id"] == edit_id), None)

                    if edit_row:
                        with st.form(f"edit_form_{edit_id}"):
                            ec1, ec2 = st.columns(2)
                            with ec1:
                                current_type_idx = 0 if edit_row.get("type") == "income" else 1
                                edit_type = st.radio("ประเภทรายการ:", ["🟢 รายรับ (Income)", "🔴 รายจ่าย (Expense)"], index=current_type_idx, horizontal=True)
                                edit_amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, value=float(edit_row.get("amount", 0.0)), step=50.0, format="%.2f")
                                
                                categories = ["ขาย License Key", "ต่ออายุบอท", "ค่าโฮสต์/เซิร์ฟเวอร์", "ค่าไฟ/อินเทอร์เน็ต", "ค่าเครื่องมือพัฒนา", "อื่นๆ"]
                                cur_cat = edit_row.get("category", "ขาย License Key")
                                cat_idx = categories.index(cur_cat) if cur_cat in categories else 0
                                edit_cat = st.selectbox("หมวดหมู่:", categories, index=cat_idx)

                            with ec2:
                                try:
                                    cur_date = pd.to_datetime(edit_row.get("created_at")).date()
                                except Exception:
                                    cur_date = datetime.now().date()
                                edit_date = st.date_input("วันที่ทำรายการ:", value=cur_date)
                                edit_note = st.text_area("📝 รายละเอียด / หมายเหตุ (Note):", value=edit_row.get("note", "") or "", height=68)
                                new_slip_file = st.file_uploader("📎 อัปโหลดสลิปใหม่แทนที่รูปเดิม (เว้นว่างไว้ถ้าไม่เปลี่ยน):", type=["png", "jpg", "jpeg"])

                            save_edit_btn = st.form_submit_button("💾 บันทึกการแก้ไขข้อมูล")

                            if save_edit_btn:
                                final_slip_url = edit_row.get("slip_url", "")
                                final_drive_id = edit_row.get("drive_file_id", "")

                                if new_slip_file is not None:
                                    with st.spinner("⏳ กำลังอัปโหลดสลิปใหม่ไปยัง Google Drive..."):
                                        try:
                                            if final_drive_id:
                                                delete_file_from_gdrive(final_drive_id)

                                            timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
                                            clean_filename = f"slip_{timestamp_prefix}_{new_slip_file.name}"
                                            up_res = upload_slip_to_gdrive(
                                                new_slip_file.getvalue(),
                                                clean_filename,
                                                mimetype=new_slip_file.type
                                            )
                                            final_drive_id = up_res.get("id", "")
                                            final_slip_url = up_res.get("webViewLink", "")
                                        except Exception as ex:
                                            st.warning(f"⚠️ อัปโหลดรูปใหม่ไม่สำเร็จ: {ex}")

                                update_payload = {
                                    "type": "income" if "รายรับ" in edit_type else "expense",
                                    "amount": edit_amount,
                                    "category": edit_cat,
                                    "note": edit_note.strip(),
                                    "slip_url": final_slip_url,
                                    "drive_file_id": final_drive_id,
                                    "created_at": datetime.combine(edit_date, datetime.now().time()).isoformat()
                                }

                                try:
                                    supabase.table("accounting_records").update(update_payload).eq("id", edit_id).execute()
                                    st.success(f"🎉 อัปเดตรายการ ID: {edit_id} เรียบร้อยแล้ว!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"อัปเดตข้อมูลไม่สำเร็จ: {err}")

            with tab_delete:
                del_options = [
                    f"ID: {item['id']} | [{item.get('type','').upper()}] {item.get('category','')} - ฿{float(item.get('amount',0)):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
                    for item in acc_data
                ]
                selected_del = st.selectbox("เลือกรายการที่ต้องการลบ:", del_options, key="sel_del_tx")

                col_del1, _ = st.columns([2, 3])
                with col_del1:
                    if st.button("❌ ยืนยันลบรายการที่เลือก", type="primary", key="btn_confirm_del_tx"):
                        selected_tx_id = int(selected_del.split("ID: ")[1].split(" |")[0])
                        target_row = next((r for r in acc_data if r["id"] == selected_tx_id), None)
                        
                        if target_row and target_row.get("drive_file_id"):
                            delete_file_from_gdrive(target_row["drive_file_id"])

                        supabase.table("accounting_records").delete().eq("id", selected_tx_id).execute()
                        st.success(f"ลบรายการ ID: {selected_tx_id} เรียบร้อยแล้ว!")
                        st.rerun()

        else:
            st.info("ยังไม่มีรายการบัญชีในระบบ")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
