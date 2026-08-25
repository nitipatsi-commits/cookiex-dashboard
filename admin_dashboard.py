import base64
from datetime import date, datetime, timedelta, timezone
import io
import os
from PIL import Image
import random
import string
import threading
import time

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

# ไลบรารีสำหรับ Google Drive API (สำรอง)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False

# 🟢 ตั้งค่าหน้าเว็บ (ต้องอยู่หลัง import streamlit as st เสมอ)
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

# ==========================================
# 🚨 ฟังก์ชัน WATCHDOG เฝ้าระวังบอทและแจ้งเตือน DISCORD
# ==========================================
def check_and_alert_bot_health(bot_data_list):
    webhook_url = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
    if not webhook_url or not bot_data_list:
        return

    # ป้องกันการส่งแจ้งเตือนซ้ำรัวๆ โดยจำเวลาที่ส่งไว้ใน Session
    if "alerted_bots" not in st.session_state:
        st.session_state.alerted_bots = {}

    now_utc = datetime.now(timezone.utc)

    for bot in bot_data_list:
        k_code = bot.get("license_key", "Unknown")
        status = str(bot.get("status", "")).upper()
        last_seen_str = bot.get("last_seen") or bot.get("last_heartbeat")
        step_info = str(bot.get("current_step", "-"))
        
        is_problem = False
        problem_reason = ""

        # 1. เช็คสถานะขัดข้องชัดเจน (CRASH หรือ แคปช่า)
        if "CRASH" in status:
            is_problem = True
            problem_reason = "💥 บอทแครช / CRASH"
        elif "CAPTCHA" in status or "ติด" in step_info:
            is_problem = True
            problem_reason = "🚨 บอทติด CAPTCHA ต้องแก้ด่วน"

        # 2. เช็คกรณีบอทดับเงียบ (ขาดการส่งเวลาเกิน 5 นาที)
        if last_seen_str and not is_problem:
            try:
                last_seen_dt = pd.to_datetime(last_seen_str, utc=True)
                diff_mins = (now_utc - last_seen_dt).total_seconds() / 60
                if diff_mins > 5 and status == "RUNNING":
                    is_problem = True
                    problem_reason = f"⚠️ ขาดการเชื่อมต่อเกิน {int(diff_mins)} นาที (เครื่องดับ/เน็ตหลุด)"
            except Exception:
                pass

        # 3. ยิง Discord เฉพาะเมื่อตรวจพบปัญหา และเว้นระยะห่างอย่างน้อย 30 นาทีต่อเครื่อง
        if is_problem:
            last_alert_time = st.session_state.alerted_bots.get(k_code)
            should_send = False
            if not last_alert_time:
                should_send = True
            elif (datetime.now() - last_alert_time).total_seconds() > 1800:  # 30 นาทีเตือนซ้ำ
                should_send = True

            if should_send:
                thai_time_str = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
                payload = {
                    "embeds": [{
                        "title": f"🚨 แจ้งเตือนบอท: {problem_reason}",
                        "color": 15548997,
                        "fields": [
                            {"name": "🔑 License Key", "value": f"`{k_code}`", "inline": True},
                            {"name": "⚙️ สถานะบอท", "value": f"`{status}`", "inline": True},
                            {"name": "📍 ขั้นตอนล่าสุด", "value": f"{step_info}", "inline": False},
                            {"name": "💻 สเปกเครื่อง", "value": f"{bot.get('pc_specs', '-')[:80]}", "inline": False}
                        ],
                        "footer": {"text": f"ระบบเฝ้าระวังอัตโนมัติ (Watchdog) • {thai_time_str}"}
                    }]
                }
                try:
                    requests.post(webhook_url, json=payload, timeout=5)
                    st.session_state.alerted_bots[k_code] = datetime.now()
                except Exception:
                    pass

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
# 📊 TAB 1: LIVE MONITOR (พร้อมระบบ WATCHDOG เฝ้าระวัง Discord Alert)
# ---------------------------------------------------------
if menu == "📊 Live Monitor (มอนิเตอร์บอท)":
    st.title("📊 Live Bot Monitor")
    st.caption("มอนิเตอร์สถานะลูกค้าเรียลไทม์และสเปคฮาร์ดแวร์เครื่องลูกค้า")

    # --- ฟังก์ชันตรวจจับและยิงแจ้งเตือน Discord ---
    def check_and_alert_bot_health(raw_bot_data):
        webhook_url = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
        if not webhook_url or not raw_bot_data:
            return

        if "alerted_bots" not in st.session_state:
            st.session_state.alerted_bots = {}

        now_utc = datetime.now(timezone.utc)

        for bot in raw_bot_data:
            k_code = str(bot.get("license_key", "Unknown"))
            status = str(bot.get("status", "")).upper()
            step_info = str(bot.get("current_step", "-"))
            last_seen_raw = bot.get("last_seen")

            is_problem = False
            problem_reason = ""

            # 1. เช็คสถานะขัดข้อง (CRASH หรือ แคปช่า)
            if status == "CRASH" or "CRASH" in status:
                is_problem = True
                problem_reason = "💥 บอทขัดข้อง / CRASH"
            elif "CAPTCHA" in step_info.upper() or "ติด" in step_info:
                is_problem = True
                problem_reason = "🚨 บอทติด CAPTCHA ต้องแก้ด่วน"

            # 2. เช็คกรณีเครื่องค้าง / หลุดการเชื่อมต่อเกิน 5 นาที
            if last_seen_raw and not is_problem:
                try:
                    last_seen_dt = pd.to_datetime(last_seen_raw, utc=True)
                    diff_mins = (now_utc - last_seen_dt).total_seconds() / 60
                    if diff_mins > 5 and status == "RUNNING":
                        is_problem = True
                        problem_reason = f"⚠️ ขาดการเชื่อมต่อเกิน {int(diff_mins)} นาที (เครื่องดับ/เน็ตหลุด)"
                except Exception:
                    pass

            # 3. ส่งเข้า Discord (เว้นระยะห่างเครื่องละ 30 นาที)
            if is_problem:
                last_alert_time = st.session_state.alerted_bots.get(k_code)
                should_send = False
                if not last_alert_time:
                    should_send = True
                elif (datetime.now() - last_alert_time).total_seconds() > 1800:
                    should_send = True

                if should_send:
                    thai_now = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        last_seen_thai = pd.to_datetime(last_seen_raw, utc=True).tz_convert("Asia/Bangkok").strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        last_seen_thai = str(last_seen_raw)

                    payload = {
                        "embeds": [{
                            "title": f"🚨 แจ้งเตือนบอท: {problem_reason}",
                            "color": 15548997,
                            "fields": [
                                {"name": "🔑 License Key", "value": f"`{k_code}`", "inline": True},
                                {"name": "⚙️ สถานะบอท", "value": f"`{status}`", "inline": True},
                                {"name": "📍 ขั้นตอนล่าสุด", "value": f"{step_info}", "inline": False},
                                {"name": "📦 กล่องสะสม", "value": f"{bot.get('boxes_collected', 0):,} กล่อง", "inline": True},
                                {"name": "⏰ เวลาล่าสุดที่พบ", "value": f"{last_seen_thai}", "inline": True},
                                {"name": "💻 สเปกเครื่อง", "value": f"{str(bot.get('pc_specs', '-'))[:80]}", "inline": False}
                            ],
                            "footer": {"text": f"ระบบเฝ้าระวังอัตโนมัติ (Watchdog) • {thai_now}"}
                        }]
                    }
                    try:
                        requests.post(webhook_url, json=payload, timeout=5)
                        st.session_state.alerted_bots[k_code] = datetime.now()
                    except Exception:
                        pass

    if st.button("🔄 รีเฟรชข้อมูลสด"):
        st.rerun()

    try:
        res = supabase.table("user_monitors").select("*").execute()
        data = res.data
        if data:
            # 🟢 เรียก Watchdog ตรวจสอบสถานะทันทีที่มีข้อมูลเข้ามา
            check_and_alert_bot_health(data)

            df = pd.DataFrame(data)
            if "last_seen" in df.columns:
                df["last_seen"] = pd.to_datetime(df["last_seen"], utc=True).dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            total_bots = len(df)
            active_bots = len(df[df["status"] == "RUNNING"]) if "status" in df.columns else 0
            captcha_bots = len(df[df["current_step"].fillna("").str.contains("CAPTCHA|ติด", case=False)]) if "current_step" in df.columns else 0
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
# 🔑 TAB: จัดการ KEY MANAGER (ตรงกับฐานข้อมูลเป๊ะ: key_type, max_sessions, Note, is_active, expire_date)
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    st.title("🔑 License Key Manager")
    st.caption("ระบบจัดการคีย์ลูกค้า เชื่อมต่อฐานข้อมูลจริง กำหนดเวลา วัน/ชม./นาที และผ่อนผัน 12 ชม. ก่อนลบอัตโนมัติ")

    now_utc = datetime.now(timezone.utc)

    def generate_random_key(length=16):
        chars = string.ascii_uppercase + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    def safe_format_thai_time(ts_val):
        if not ts_val or pd.isna(ts_val):
            return "ตลอดชีพ"
        try:
            dt = pd.to_datetime(ts_val, utc=True)
            return dt.tz_convert('Asia/Bangkok').strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(ts_val)

    try:
        # 1. ดึงข้อมูล License Key ทั้งหมด
        res_keys = supabase.table("licenses").select("*").execute()
        raw_licenses = res_keys.data or []

        valid_licenses = []
        deleted_count = 0
        purge_threshold = now_utc - timedelta(hours=12)

        # เคลียร์คีย์หมดอายุเกิน 12 ชม. อัตโนมัติ
        for k in raw_licenses:
            exp_str = k.get("expire_date") or k.get("expires_at")
            is_purged = False
            if exp_str:
                try:
                    exp_dt = pd.to_datetime(exp_str, utc=True)
                    if exp_dt < purge_threshold:
                        supabase.table("licenses").delete().eq("license_key", k.get("license_key")).execute()
                        deleted_count += 1
                        is_purged = True
                except Exception:
                    pass
            if not is_purged:
                valid_licenses.append(k)

        if deleted_count > 0:
            st.toast(f"🧹 ลบคีย์ที่หมดอายุเกิน 12 ชม. อัตโนมัติ {deleted_count} รายการ", icon="🗑️")

        df_keys = pd.DataFrame(valid_licenses) if valid_licenses else pd.DataFrame()

        if not df_keys.empty:
            # ดึงค่าจากคอลัมน์จริงของ Supabase
            df_keys["display_note"] = df_keys.apply(lambda r: r.get("Note") if pd.notna(r.get("Note")) else (r.get("note") or ""), axis=1)
            df_keys["display_tier"] = df_keys.apply(lambda r: str(r.get("key_type") or r.get("tier") or "normal").capitalize(), axis=1)
            df_keys["display_screens"] = df_keys.apply(lambda r: int(r.get("max_sessions") if pd.notna(r.get("max_sessions")) else (r.get("max_concurrent") or 1)), axis=1)
            df_keys["is_active_bool"] = df_keys.apply(lambda r: r.get("is_active") if "is_active" in r and pd.notna(r.get("is_active")) else (str(r.get("status", "active")).lower() == "active"), axis=1)

            # คำนวณสถานะและเวลาคงเหลือ
            def calculate_key_status(row):
                if not row["is_active_bool"]:
                    return "🔴 ระงับการใช้งาน", "ถูกระงับ"
                
                exp_val = row.get("expire_date") or row.get("expires_at")
                if not exp_val or pd.isna(exp_val):
                    return "🟢 ใช้งานได้ (ตลอดชีพ)", "ไม่มีวันหมดอายุ"

                try:
                    exp_dt = pd.to_datetime(exp_val, utc=True)
                    diff = exp_dt - now_utc
                    if diff.total_seconds() > 0:
                        total_sec = int(diff.total_seconds())
                        days = total_sec // 86400
                        hours = (total_sec % 86400) // 3600
                        mins = (total_sec % 3600) // 60
                        if days > 0:
                            return "🟢 กำลังใช้งาน", f"เหลือ {days}วัน {hours}ชม. {mins}น."
                        else:
                            return "🟢 กำลังใช้งาน", f"เหลือ {hours}ชม. {mins}น."
                    else:
                        del_diff = (exp_dt + timedelta(hours=12)) - now_utc
                        mins_left = max(0, int(del_diff.total_seconds() / 60))
                        h_left = mins_left // 60
                        m_left = mins_left % 60
                        return "⏳ หมดอายุ (ผ่อนผัน)", f"รอลบใน {h_left}ชม. {m_left}น."
                except Exception:
                    return "🟢 กำลังใช้งาน", "-"

            res_status = [calculate_key_status(r) for _, r in df_keys.iterrows()]
            df_keys["สถานะระบบ"] = [s[0] for s in res_status]
            df_keys["เวลาคงเหลือ"] = [s[1] for s in res_status]

            active_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("🟢")])
            expired_grace_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("⏳")])
            suspended_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("🔴")])
            total_screens = df_keys[df_keys["สถานะระบบ"].str.contains("🟢")]["display_screens"].sum()
        else:
            active_count = 0
            expired_grace_count = 0
            suspended_count = 0
            total_screens = 0

        # สรุปตัวเลขสถิติ 4 กล่อง
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔑 คีย์ทั้งหมด", f"{len(df_keys):,} คีย์")
        m2.metric("🟢 พร้อมใช้งาน", f"{active_count:,} คีย์")
        m3.metric("💻 โควตาจอรันจริง", f"{total_screens:,} จอ")
        m4.metric("⏳ หมดอายุ (ผ่อนผัน 12 ชม.)", f"{expired_grace_count:,} คีย์")

        st.write("")

        tab_table, tab_grace, tab_add, tab_manage = st.tabs([
            f"📋 รายการคีย์ทั้งหมด ({len(df_keys)})",
            f"⏳ คีย์หมดอายุผ่อนผัน ({expired_grace_count})",
            "➕ สร้างคีย์ใหม่ (Add Key)",
            "⚙️ แก้ไข / จัดการคีย์ (Manage)"
        ])

        # --- TAB 1: ตารางคีย์ทั้งหมด ---
        with tab_table:
            if not df_keys.empty:
                f1, f2, f3 = st.columns([2, 1, 1])
                with f1:
                    search_txt = st.text_input("🔍 ค้นหาคีย์ / ชื่อลูกค้า (Note) / HWID:", placeholder="พิมพ์ค้นหา เช่น พี่นิว, เต้ NB...", key="s_all_keys")
                with f2:
                    filter_st = st.selectbox("📌 กรองสถานะ:", ["ทั้งหมด", "🟢 กำลังใช้งาน", "⏳ หมดอายุ (ผ่อนผัน)", "🔴 ระงับการใช้งาน"], key="f_st_keys")
                with f3:
                    tier_list = ["ทั้งหมด"] + sorted(list(df_keys["display_tier"].dropna().unique()))
                    filter_tr = st.selectbox("⭐ ระดับ (Key Type):", tier_list, key="f_tr_keys")

                df_disp = df_keys.copy()

                if search_txt.strip():
                    m1 = df_disp["license_key"].fillna("").astype(str).str.contains(search_txt.strip(), case=False)
                    m2 = df_disp["display_note"].fillna("").astype(str).str.contains(search_txt.strip(), case=False)
                    m3 = df_disp["hwid"].fillna("").astype(str).str.contains(search_txt.strip(), case=False) if "hwid" in df_disp.columns else False
                    df_disp = df_disp[m1 | m2 | m3]

                if filter_st != "ทั้งหมด":
                    df_disp = df_disp[df_disp["สถานะระบบ"].str.contains(filter_st.split()[0])]

                if filter_tr != "ทั้งหมด":
                    df_disp = df_disp[df_disp["display_tier"] == filter_tr]

                df_disp["วันหมดอายุ"] = df_disp.apply(lambda r: safe_format_thai_time(r.get("expire_date") or r.get("expires_at")), axis=1)

                display_columns = ["license_key", "สถานะระบบ", "เวลาคงเหลือ", "display_tier", "display_screens", "วันหมดอายุ", "hwid", "display_note"]
                
                st.dataframe(
                    df_disp[display_columns],
                    column_config={
                        "license_key": st.column_config.TextColumn("🔑 License Key"),
                        "สถานะระบบ": st.column_config.TextColumn("สถานะ"),
                        "เวลาคงเหลือ": st.column_config.TextColumn("⏰ เวลาคงเหลือ"),
                        "display_tier": st.column_config.TextColumn("ระดับ (Key Type)"),
                        "display_screens": st.column_config.NumberColumn("จำนวนจอ (Max Sessions)", format="%d จอ"),
                        "hwid": st.column_config.TextColumn("HWID เครื่อง"),
                        "display_note": st.column_config.TextColumn("📝 ลูกค้า / บันทึก (Note)")
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("ยังไม่มีข้อมูล License Key ในระบบ")

        # --- TAB 2: คีย์หมดอายุ (ผ่อนผัน 12 ชม.) ---
        with tab_grace:
            df_grace = df_keys[df_keys["สถานะระบบ"].str.contains("⏳")] if not df_keys.empty else pd.DataFrame()
            if not df_grace.empty:
                st.warning("⚠️ รายการคีย์ด้านล่างนี้หมดอายุแล้ว แต่ระบบเก็บไว้ **12 ชม.** เพื่อให้โอกาสลูกค้าต่ออายุ ก่อนถูกลบทิ้งถาวร")
                for _, r_exp in df_grace.iterrows():
                    k_code = r_exp["license_key"]
                    c1, c2 = st.columns([3, 1.5])
                    with c1:
                        st.markdown(f"🔑 **`{k_code}`** | ระดับ: **{r_exp.get('display_tier','Normal')}** | โควตา: **{r_exp.get('display_screens',1)} จอ**")
                        st.caption(f"📝 {r_exp.get('display_note','') or 'ไม่มีบันทึก'} | ⏰ **{r_exp.get('เวลาคงเหลือ','')}**")
                    with c2:
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("⚡ ต่ออายุ 30 วัน", key=f"btn_rn_{k_code}"):
                                new_exp = now_utc + timedelta(days=30)
                                supabase.table("licenses").update({"expire_date": new_exp.isoformat(), "is_active": True}).eq("license_key", k_code).execute()
                                st.success(f"ต่ออายุคีย์ `{k_code}` สำเร็จ!")
                                st.rerun()
                        with b2:
                            if st.button("🗑️ ลบทันที", key=f"btn_dl_{k_code}"):
                                supabase.table("licenses").delete().eq("license_key", k_code).execute()
                                st.rerun()
                    st.write("---")
            else:
                st.success("🎉 ไม่มีคีย์ที่หมดอายุค้างอยู่ในช่วง 12 ชั่วโมง")

        # --- TAB 3: สร้างคีย์ใหม่ ---
        with tab_add:
            with st.form("add_license_form_v2", clear_on_submit=True):
                col_k1, col_k2 = st.columns(2)
                with col_k1:
                    custom_key = st.text_input("🔑 รหัส License Key (เว้นว่างไว้เพื่อสุ่มให้อัตโนมัติ):", placeholder="เช่น PRO-XXXX-YYYY")
                    max_sessions = st.number_input("💻 จำนวนจอที่อนุญาต (Max Sessions):", min_value=1, value=1, step=1)
                    
                    st.write("**⏳ ระยะเวลาการใช้งาน:**")
                    t_d, t_h, t_m = st.columns(3)
                    with t_d:
                        days_input = st.number_input("วัน (Days):", min_value=0, value=30, step=1)
                    with t_h:
                        hours_input = st.number_input("ชม. (Hours):", min_value=0, value=0, step=1)
                    with t_m:
                        mins_input = st.number_input("นาที (Minutes):", min_value=0, value=0, step=1)

                with col_k2:
                    tier_type = st.selectbox("⭐ ระดับสิทธิ์ (Key Type):", ["premier", "normal"])
                    customer_note = st.text_area("📝 ข้อมูลลูกค้า / บันทึก (Note):", placeholder="เช่น พี่นิว / เต้ NB / ทดสอบบอท", height=110)

                submit_add_key = st.form_submit_button("✨ สร้าง License Key ใหม่")

                if submit_add_key:
                    final_key = custom_key.strip() if custom_key.strip() else generate_random_key(16)
                    total_delta = timedelta(days=int(days_input), hours=int(hours_input), minutes=int(mins_input))
                    
                    # 🟢 ล็อกเวลาสร้างตามเวลาประเทศไทย (UTC+7)
                    thai_tz = timezone(timedelta(hours=7))
                    now_thai = datetime.now(thai_tz)

                    if total_delta.total_seconds() > 0:
                        expire_time = now_thai + total_delta
                        exp_str = expire_time.strftime("%Y-%m-%d %H:%M:%S")
                        exp_msg = expire_time.strftime('%Y-%m-%d %H:%M น.')
                    else:
                        exp_str = None
                        exp_msg = "ตลอดชีพ (ไม่มีวันหมดอายุ)"

                    key_payload = {
                        "license_key": final_key,
                        "max_sessions": int(max_sessions),
                        "key_type": tier_type.lower(),
                        "Note": customer_note.strip(),
                        "expire_date": exp_str,
                        "is_active": True
                    }

                    try:
                        supabase.table("licenses").insert(key_payload).execute()
                        st.success(f"🎉 สร้างคีย์ `{final_key}` สำเร็จ! (หมดอายุ: {exp_msg})")
                        st.rerun()
                    except Exception as err:
                        st.error(f"สร้างคีย์ไม่สำเร็จ: {err}")

        # --- TAB 4: จัดการ / แก้ไข / ปลดล็อค HWID ---
        with tab_manage:
            if valid_licenses:
                key_options = [
                    f"{k['license_key']} | [{str(k.get('key_type') or 'normal').upper()}] จอ: {k.get('max_sessions',1)} ({k.get('Note') or k.get('note') or 'ไม่มีบันทึก'})"
                    for k in valid_licenses
                ]
                selected_manage_str = st.selectbox("เลือกคีย์ที่ต้องการจัดการ:", key_options, key="sel_manage_box")

                if selected_manage_str:
                    target_code = selected_manage_str.split(" |")[0]
                    target_obj = next((k for k in valid_licenses if k["license_key"] == target_code), None)

                    if target_obj:
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            cur_sess = target_obj.get("max_sessions") if pd.notna(target_obj.get("max_sessions")) else 1
                            new_max_screens = st.number_input("💻 ปรับจำนวนจอ (Max Sessions):", min_value=1, value=int(cur_sess), step=1)
                            
                            st.write("**⏳ เพิ่มเวลาการใช้งาน (+วัน/+ชม./+นาที):**")
                            ad_d, ad_h, ad_m = st.columns(3)
                            with ad_d:
                                add_days = st.number_input("+วัน (Days):", min_value=0, value=0, step=1)
                            with ad_h:
                                add_hours = st.number_input("+ชม. (Hours):", min_value=0, value=0, step=1)
                            with ad_m:
                                add_mins = st.number_input("+นาที (Minutes):", min_value=0, value=0, step=1)

                            cur_note_val = target_obj.get("Note") or target_obj.get("note") or ""
                            new_note = st.text_area("📝 แก้ไขบันทึก (Note):", value=cur_note_val, height=68)

                        with col_m2:
                            st.write("**สถานะ HWID ปัจจุบัน:**")
                            st.code(target_obj.get("hwid") or "ยังไม่มีการผูก HWID (ว่าง)")
                            reset_hwid_flag = st.checkbox("🔓 รีเซ็ต HWID (ปลดล็อคย้ายเครื่อง)")

                            cur_is_active = target_obj.get("is_active", True)
                            new_active_status = st.selectbox("📌 สถานะคีย์:", ["🟢 ใช้งานได้ปกติ (Active)", "🔴 ระงับการใช้งาน (Suspended)"], index=0 if cur_is_active else 1)

                        col_btn1, col_btn2 = st.columns([2, 2])
                        with col_btn1:
                            if st.button("💾 บันทึกการแก้ไข", type="primary"):
                                thai_tz = timezone(timedelta(hours=7))
                                now_thai = datetime.now(thai_tz)

                                update_data = {
                                    "max_sessions": int(new_max_screens),
                                    "Note": new_note.strip(),
                                    "is_active": True if "Active" in new_active_status else False
                                }
                                if reset_hwid_flag:
                                    update_data["hwid"] = None

                                # คำนวณบวกเวลาเพิ่ม (+วัน / +ชม. / +นาที)
                                added_delta = timedelta(days=int(add_days), hours=int(add_hours), minutes=int(add_mins))
                                if added_delta.total_seconds() > 0:
                                    current_exp = target_obj.get("expire_date") or target_obj.get("expires_at")
                                    try:
                                        if current_exp and not pd.isna(current_exp):
                                            clean_exp = str(current_exp).replace("T", " ")[:19]
                                            if len(clean_exp) == 10:
                                                clean_exp += " 23:59:59"
                                            base_dt = datetime.strptime(clean_exp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=thai_tz)
                                            if base_dt < now_thai:
                                                base_dt = now_thai
                                        else:
                                            base_dt = now_thai
                                    except Exception:
                                        base_dt = now_thai

                                    new_expire_dt = base_dt + added_delta
                                    update_data["expire_date"] = new_expire_dt.strftime("%Y-%m-%d %H:%M:%S")

                                try:
                                    supabase.table("licenses").update(update_data).eq("license_key", target_code).execute()
                                    st.success(f"🎉 อัปเดตคีย์ `{target_code}` เรียบร้อยแล้ว!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"อัปเดตไม่สำเร็จ: {err}")

                        with col_btn2:
                            if st.button("❌ ลบคีย์นี้ทิ้งถาวร"):
                                try:
                                    supabase.table("licenses").delete().eq("license_key", target_code).execute()
                                    st.success(f"ลบคีย์ `{target_code}` แล้ว!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"ลบไม่สำเร็จ: {err}")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล License: {e}")

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
# 💰 TAB 4: บันทึกรายรับ-รายจ่าย & สลิป (ระบบรอยืนยัน + DISCORD + EXPORT)
# ---------------------------------------------------------
elif menu == "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)":
    st.title("💰 ระบบบันทึกรายรับ-รายจ่าย & บัญชีร้าน")
    st.caption("ระบบจัดการการเงินครบวงจร บันทึกบัญชี แนบสลิป อนุมัติรายการรอยืนยัน สรุปกราฟ และส่งออกข้อมูล")

    # --- ฟังก์ชันช่วยทำงาน ---
    def upload_slip_to_supabase(file_bytes, filename, mimetype="image/jpeg"):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75, optimize=True)
            compressed_bytes = buffer.getvalue()
            final_mime = "image/jpeg"
            clean_name = filename.rsplit(".", 1)[0] + ".jpg"
        except Exception:
            compressed_bytes = file_bytes
            final_mime = mimetype
            clean_name = filename

        file_path = f"receipts/{clean_name}"
        supabase.storage.from_("slips").upload(
            path=file_path,
            file=compressed_bytes,
            file_options={"content-type": final_mime}
        )
        public_url = supabase.storage.from_("slips").get_public_url(file_path)
        return {"id": file_path, "webViewLink": public_url}

    def delete_slip_from_supabase(file_path):
        if not file_path:
            return
        try:
            supabase.storage.from_("slips").remove([file_path])
        except Exception:
            pass

    def send_discord_accounting_alert(tx_type, amount, category, note, status_text, slip_url=""):
        webhook_url = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
        if not webhook_url:
            return
        try:
            is_income = "income" in tx_type.lower() or "รายรับ" in tx_type
            if status_text == "pending":
                color = 16763904  # สีส้ม/เหลือง
                status_badge = "⏳ รอยืนยัน / รอตรวจสอบ"
            else:
                color = 5763719 if is_income else 15548997
                status_badge = "✅ สำเร็จแล้ว"

            title = f"🟢 บันทึกรายรับ ({status_badge})" if is_income else f"🔴 บันทึกรายจ่าย ({status_badge})"
            
            fields = [
                {"name": "💵 จำนวนเงิน", "value": f"**฿{amount:,.2f}**", "inline": True},
                {"name": "📂 หมวดหมู่", "value": category, "inline": True},
                {"name": "📌 สถานะ", "value": status_badge, "inline": True},
                {"name": "📝 หมายเหตุ / ลูกค้า", "value": note or "-", "inline": False},
            ]
            if slip_url:
                fields.append({"name": "📎 ลิงก์รูปสลิป", "value": f"[คลิกเพื่อดูสลิป]({slip_url})", "inline": False})

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
                # 🟢 เลือกสถานะรายการ
                tx_status = st.selectbox("📌 สถานะรายการ:", ["🟢 สำเร็จแล้ว (Completed)", "🟡 รอยืนยัน / รอตรวจสอบสลิป (Pending)"])
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
                        with st.spinner("⏳ กำลังอัปโหลดสลิปไปยัง Supabase Storage..."):
                            try:
                                timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
                                clean_filename = f"slip_{timestamp_prefix}_{slip_file.name}"
                                upload_res = upload_slip_to_supabase(
                                    slip_file.getvalue(),
                                    clean_filename,
                                    mimetype=slip_file.type
                                )
                                drive_file_id = upload_res.get("id", "")
                                slip_url = upload_res.get("webViewLink", "")
                                st.success("☁️ อัปโหลดสลิปสำเร็จเรียบร้อย!")
                            except Exception as ex:
                                st.warning(f"⚠️ บันทึกข้อมูลได้ แต่อัปโหลดรูปสลิปไม่สำเร็จ: {ex}")

                    combined_note = ""
                    if customer_ref.strip() and extra_note.strip():
                        combined_note = f"{customer_ref.strip()} | {extra_note.strip()}"
                    else:
                        combined_note = customer_ref.strip() or extra_note.strip()

                    status_val = "pending" if "รอยืนยัน" in tx_status else "completed"

                    tx_payload = {
                        "type": "income" if "รายรับ" in tx_type else "expense",
                        "amount": amount,
                        "category": category,
                        "note": combined_note,
                        "slip_url": slip_url,
                        "drive_file_id": drive_file_id,
                        "status": status_val,
                        "created_at": datetime.combine(tx_date, datetime.now().time()).isoformat()
                    }

                    try:
                        supabase.table("accounting_records").insert(tx_payload).execute()
                        if send_noti:
                            send_discord_accounting_alert(tx_type, amount, category, combined_note, status_val, slip_url)
                        st.success(f"✅ บันทึกรายการ {category} ยอด {amount:,.2f} บาท เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"บันทึกฐานข้อมูลไม่สำเร็จ: {err}")

    # ==========================================
    # 2. รายการรอยืนยัน (Pending Review Box)
    # ==========================================
    try:
        res_acc = supabase.table("accounting_records").select("*").order("created_at", desc=True).execute()
        acc_data = res_acc.data or []
        
        # จัดการค่า status เริ่มต้นถ้ายังเป็น null
        for item in acc_data:
            if not item.get("status"):
                item["status"] = "completed"

        pending_items = [item for item in acc_data if item.get("status") == "pending"]

        if pending_items:
            st.warning(f"⚠️ มี **{len(pending_items)} รายการ** ที่อยู่ระหว่าง **รอยืนยัน / รอตรวจสอบยอด**")
            with st.expander("⏳ รายการที่รอยืนยัน (คลิกเพื่ออนุมัติ / ยกเลิก)", expanded=True):
                for p_item in pending_items:
                    p_id = p_item["id"]
                    p_type = "🟢 รายรับ" if p_item.get("type") == "income" else "🔴 รายจ่าย"
                    p_col1, p_col2, p_col3, p_col4 = st.columns([3, 2, 1.5, 1.5])
                    
                    with p_col1:
                        st.markdown(f"**ID: {p_id}** | {p_type} **฿{float(p_item.get('amount',0)):,.2f}** - {p_item.get('category','')}")
                        st.caption(f"📝 {p_item.get('note','') or 'ไม่มีหมายเหตุ'} | 📅 {p_item.get('created_at','')[:16]}")
                    
                    with p_col2:
                        if p_item.get("slip_url"):
                            st.markdown(f"[📂 คลิกดูรูปสลิป]({p_item['slip_url']})")
                        else:
                            st.caption("ไม่มีรูปสลิป")
                            
                    with p_col3:
                        if st.button("✅ อนุมัติยอด", key=f"apprv_{p_id}", type="primary"):
                            supabase.table("accounting_records").update({"status": "completed"}).eq("id", p_id).execute()
                            st.success(f"อนุมัติรายการ ID {p_id} เรียบร้อย!")
                            st.rerun()

                    with p_col4:
                        if st.button("❌ ปฏิเสธ", key=f"reject_{p_id}"):
                            supabase.table("accounting_records").update({"status": "rejected"}).eq("id", p_id).execute()
                            st.info(f"ปฏิเสธรายการ ID {p_id} แล้ว")
                            st.rerun()
                    st.write("---")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดรายการรอยืนยัน: {e}")

    st.divider()

    # ==========================================
    # 3. ตัวกรองข้อมูล & รายงานสรุปยอด
    # ==========================================
    st.subheader("📊 สรุปยอดบัญชีและประวัติรายการ")
    
    if acc_data:
        df_all = pd.DataFrame(acc_data)
        df_all["created_at"] = pd.to_datetime(df_all["created_at"])
        df_all["date_only"] = df_all["created_at"].dt.date

        # --- ตัวกรอง ---
        f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.5, 1.5, 2])
        with f_col1:
            filter_period = st.selectbox("📅 ช่วงเวลา:", ["ทั้งหมด", "เดือนนี้ (This Month)", "เดือนที่แล้ว", "กำหนดช่วงวันที่เอง"])
        
        with f_col2:
            filter_status = st.selectbox("📌 สถานะ:", ["ทั้งหมด", "เฉพาะที่สำเร็จ (Completed)", "เฉพาะรอยืนยัน (Pending)", "เฉพาะปฏิเสธ (Rejected)"])

        with f_col3:
            all_cats = ["ทั้งหมด"] + sorted(list(df_all["category"].dropna().unique()))
            filter_cat = st.selectbox("📂 หมวดหมู่:", all_cats)

        with f_col4:
            search_kw = st.text_input("🔍 ค้นหา (ชื่อลูกค้า / หมายเหตุ):", placeholder="พิมพ์คำค้นหา...")

        # กรองช่วงวันที่
        today = datetime.now().date()
        if filter_period == "เดือนนี้ (This Month)":
            df_filtered = df_all[(df_all["created_at"].dt.year == today.year) & (df_all["created_at"].dt.month == today.month)]
        elif filter_period == "เดือนที่แล้ว":
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - timedelta(days=1)
            df_filtered = df_all[(df_all["created_at"].dt.year == last_month_end.year) & (df_all["created_at"].dt.month == last_month_end.month)]
        elif filter_period == "กำหนดช่วงวันที่เอง":
            dr1, dr2 = st.date_input("เลือกช่วงวันที่:", [today - timedelta(days=30), today])
            if isinstance(dr1, (datetime, type(today))):
                df_filtered = df_all[(df_all["date_only"] >= dr1) & (df_all["date_only"] <= dr2)]
            else:
                df_filtered = df_all
        else:
            df_filtered = df_all

        # กรองตามสถานะ
        if filter_status == "เฉพาะที่สำเร็จ (Completed)":
            df_filtered = df_filtered[df_filtered["status"] == "completed"]
        elif filter_status == "เฉพาะรอยืนยัน (Pending)":
            df_filtered = df_filtered[df_filtered["status"] == "pending"]
        elif filter_status == "เฉพาะปฏิเสธ (Rejected)":
            df_filtered = df_filtered[df_filtered["status"] == "rejected"]

        # กรองตามหมวดหมู่และคำค้นหา
        if filter_cat != "ทั้งหมด":
            df_filtered = df_filtered[df_filtered["category"] == filter_cat]
        if search_kw.strip():
            df_filtered = df_filtered[df_filtered["note"].fillna("").str.contains(search_kw.strip(), case=False)]

        # คำนวณสรุปยอด (เฉพาะรายการที่ completed)
        df_completed = df_filtered[df_filtered["status"] == "completed"]
        total_income = df_completed[df_completed["type"] == "income"]["amount"].sum()
        total_expense = df_completed[df_completed["type"] == "expense"]["amount"].sum()
        net_profit = total_income - total_expense

        pending_income = df_filtered[(df_filtered["status"] == "pending") & (df_filtered["type"] == "income")]["amount"].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🟢 รายรับจริง (อนุมัติแล้ว)", f"฿ {total_income:,.2f}")
        m2.metric("🔴 รายจ่ายจริง (อนุมัติแล้ว)", f"฿ {total_expense:,.2f}")
        m3.metric("💵 กำไรสุทธิ (Net)", f"฿ {net_profit:,.2f}", delta=f"{net_profit:,.2f}")
        m4.metric("🟡 ยอดรอยืนยัน", f"฿ {pending_income:,.2f}", help="ยอดเงินที่ยังรอการตรวจสอบสลิป")

        # กราฟสรุปยอด (เฉพาะที่อนุมัติแล้ว)
        if not df_completed.empty:
            st.write("#### 📈 กราฟแนวโน้มรายรับ - รายจ่าย (เฉพาะรายการที่อนุมัติแล้ว)")
            chart_df = df_completed.copy()
            chart_df["date_str"] = chart_df["created_at"].dt.strftime("%Y-%m-%d")
            pivot_chart = chart_df.pivot_table(index="date_str", columns="type", values="amount", aggfunc="sum", fill_value=0)
            if "income" not in pivot_chart.columns: pivot_chart["income"] = 0
            if "expense" not in pivot_chart.columns: pivot_chart["expense"] = 0
            pivot_chart = pivot_chart.rename(columns={"income": "รายรับ (Income)", "expense": "รายจ่าย (Expense)"})
            pivot_chart = pivot_chart.sort_index()
            st.bar_chart(pivot_chart, color=["#22c55e", "#ef4444"], use_container_width=True)

        # ตารางแสดงข้อมูล
        df_display = df_filtered.copy()
        df_display["ประเภท"] = df_display["type"].map({"income": "🟢 รายรับ", "expense": "🔴 รายจ่าย"})
        df_display["สถานะ"] = df_display["status"].map({
            "completed": "🟢 สำเร็จ",
            "pending": "🟡 รอยืนยัน",
            "rejected": "⚪ ยกเลิก/ปฏิเสธ"
        }).fillna("🟢 สำเร็จ")
        df_display["ยอดเงิน (บาท)"] = df_display["amount"].map(lambda x: f"{x:,.2f}")
        df_display["วันที่"] = df_display["created_at"].dt.strftime("%Y-%m-%d %H:%M")

        display_cols = ["id", "วันที่", "ประเภท", "สถานะ", "หมวดหมู่", "ยอดเงิน (บาท)", "note", "slip_url"]
        valid_disp_cols = [c for c in display_cols if c in df_display.columns]

        st.dataframe(
            df_display[valid_disp_cols],
            column_config={
                "id": st.column_config.NumberColumn("ID", format="%d"),
                "note": st.column_config.TextColumn("ลูกค้า / หมายเหตุ (Note)"),
                "slip_url": st.column_config.LinkColumn("รูปสลิป", display_text="📂 เปิดดูรูปสลิป")
            },
            use_container_width=True,
            hide_index=True
        )

        # ปุ่มดาวน์โหลด CSV
        csv_data = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 ดาวน์โหลดประวัติบัญชี (Export to CSV)",
            data=csv_data,
            file_name=f"accounting_report_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

        st.divider()

        # ==========================================
        # 4. เครื่องมือจัดการรายการ (แก้ไข & ลบ)
        # ==========================================
        tab_edit, tab_delete = st.tabs(["✏️ แก้ไขรายการ (Edit)", "🗑️ ลบรายการ (Delete)"])

        # --- แท็บแก้ไข ---
        with tab_edit:
            options_list = [
                f"ID: {item['id']} | [{item.get('status','completed').upper()}] [{item.get('type','').upper()}] {item.get('category','')} - ฿{float(item.get('amount',0)):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
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
                            
                            status_options = ["🟢 สำเร็จแล้ว (Completed)", "🟡 รอยืนยัน / รอตรวจสอบ (Pending)", "⚪ ยกเลิก/ปฏิเสธ (Rejected)"]
                            cur_st = edit_row.get("status", "completed")
                            st_idx = 0 if cur_st == "completed" else (1 if cur_st == "pending" else 2)
                            edit_status = st.selectbox("สถานะรายการ:", status_options, index=st_idx)

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
                                with st.spinner("⏳ กำลังอัปโหลดรูปใหม่ไปยัง Supabase..."):
                                    try:
                                        if final_drive_id:
                                            delete_slip_from_supabase(final_drive_id)

                                        timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        clean_filename = f"slip_{timestamp_prefix}_{new_slip_file.name}"
                                        up_res = upload_slip_to_supabase(
                                            new_slip_file.getvalue(),
                                            clean_filename,
                                            mimetype=new_slip_file.type
                                        )
                                        final_drive_id = up_res.get("id", "")
                                        final_slip_url = up_res.get("webViewLink", "")
                                    except Exception as ex:
                                        st.warning(f"⚠️ อัปโหลดรูปใหม่ไม่สำเร็จ: {ex}")

                            st_val = "completed" if "Completed" in edit_status else ("pending" if "Pending" in edit_status else "rejected")

                            update_payload = {
                                "type": "income" if "รายรับ" in edit_type else "expense",
                                "amount": edit_amount,
                                "category": edit_cat,
                                "status": st_val,
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

        # --- แท็บลบ ---
        with tab_delete:
            del_options = [
                f"ID: {item['id']} | [{item.get('status','completed').upper()}] [{item.get('type','').upper()}] {item.get('category','')} - ฿{float(item.get('amount',0)):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
                for item in acc_data
            ]
            selected_del = st.selectbox("เลือกรายการที่ต้องการลบ:", del_options, key="sel_del_tx")

            col_del1, _ = st.columns([2, 3])
            with col_del1:
                if st.button("❌ ยืนยันลบรายการที่เลือก", type="primary", key="btn_confirm_del_tx"):
                    selected_tx_id = int(selected_del.split("ID: ")[1].split(" |")[0])
                    target_row = next((r for r in acc_data if r["id"] == selected_tx_id), None)
                    
                    if target_row and target_row.get("drive_file_id"):
                        delete_slip_from_supabase(target_row["drive_file_id"])

                    supabase.table("accounting_records").delete().eq("id", selected_tx_id).execute()
                    st.success(f"ลบรายการ ID: {selected_tx_id} เรียบร้อยแล้ว!")
                    st.rerun()

    else:
        st.info("ยังไม่มีรายการบัญชีในระบบ")
