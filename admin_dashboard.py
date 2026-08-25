import base64
from datetime import date, datetime, timedelta, timezone
import io
import random
import string
import threading
import time

import pandas as pd
import requests
import streamlit as st
from PIL import Image
from supabase import create_client

# ไลบรารีสำหรับ Google Drive API (สำรอง - ไม่บังคับใช้)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False

# ==========================================
# 🟢 ตั้งค่าหน้าเว็บ (ต้องอยู่หลัง import streamlit as st เสมอ)
# ==========================================
st.set_page_config(
    page_title="Cookie X - Admin System",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

THAI_TZ = timezone(timedelta(hours=7))


def now_thai():
    return datetime.now(THAI_TZ)


# ==========================================
# 🎨 THEME / CUSTOM CSS
# ==========================================
def inject_theme():
    st.markdown(
        """
        <style>
        :root {
            --cx-bg: #0b0f19;
            --cx-panel: #121826;
            --cx-panel-2: #161d2e;
            --cx-border: #232b3d;
            --cx-accent: #6366f1;
            --cx-accent-2: #22d3ee;
            --cx-green: #22c55e;
            --cx-red: #ef4444;
            --cx-yellow: #eab308;
            --cx-text: #e5e7eb;
            --cx-muted: #94a3b8;
        }

        html, body, [class*="css"] {
            font-family: "Inter", "Noto Sans Thai", "Segoe UI", sans-serif;
        }

        [data-testid="stAppViewContainer"] {
            background: radial-gradient(circle at 15% 0%, #151c2e 0%, var(--cx-bg) 45%);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0e1420 0%, #0a0e17 100%);
            border-right: 1px solid var(--cx-border);
        }

        [data-testid="stSidebar"] * {
            color: var(--cx-text);
        }

        .cx-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 6px 2px 18px 2px;
            border-bottom: 1px solid var(--cx-border);
            margin-bottom: 14px;
        }
        .cx-brand-logo {
            width: 38px; height: 38px;
            border-radius: 10px;
            background: linear-gradient(135deg, var(--cx-accent), var(--cx-accent-2));
            display: flex; align-items: center; justify-content: center;
            font-size: 20px;
            box-shadow: 0 0 18px rgba(99,102,241,0.45);
        }
        .cx-brand-title { font-weight: 700; font-size: 17px; line-height: 1.1; color: #fff; }
        .cx-brand-sub { font-size: 11.5px; color: var(--cx-muted); }

        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, var(--cx-panel), var(--cx-panel-2));
            border: 1px solid var(--cx-border);
            border-radius: 14px;
            padding: 14px 16px 10px 16px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.25);
        }
        div[data-testid="stMetric"] label { color: var(--cx-muted) !important; }

        .cx-card {
            background: linear-gradient(145deg, var(--cx-panel), var(--cx-panel-2));
            border: 1px solid var(--cx-border);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 10px;
        }
        .cx-pill {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }
        .cx-pill-green { background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.35); }
        .cx-pill-red { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }
        .cx-pill-yellow { background: rgba(234,179,8,0.15); color: #fbbf24; border: 1px solid rgba(234,179,8,0.35); }
        .cx-pill-gray { background: rgba(148,163,184,0.15); color: #cbd5e1; border: 1px solid rgba(148,163,184,0.3); }

        .cx-section-title {
            font-size: 20px;
            font-weight: 700;
            color: #fff;
            margin-bottom: 2px;
        }
        .cx-section-sub {
            color: var(--cx-muted);
            font-size: 13px;
            margin-bottom: 14px;
        }

        div.stButton > button {
            border-radius: 10px;
            border: 1px solid var(--cx-border);
        }
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--cx-accent), #4f46e5);
            border: none;
        }

        .cx-login-wrap {
            max-width: 420px;
            margin: 6vh auto 0 auto;
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand():
    st.sidebar.markdown(
        """
        <div class="cx-brand">
            <div class="cx-brand-logo">⚡</div>
            <div>
                <div class="cx-brand-title">Cookie X</div>
                <div class="cx-brand-sub">Admin Control Center</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title, subtitle=""):
    st.markdown(f'<div class="cx-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="cx-section-sub">{subtitle}</div>', unsafe_allow_html=True)


inject_theme()

# ==========================================
# 🟢 เชื่อมต่อ Supabase (อ่านจาก st.secrets เท่านั้น — ห้าม hardcode)
# ==========================================
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error(
        "❌ ยังไม่ได้ตั้งค่า SUPABASE_URL / SUPABASE_KEY ใน st.secrets\n\n"
        "กรุณาเพิ่มค่านี้ในไฟล์ `.streamlit/secrets.toml` หรือใน Secrets ของ Streamlit Cloud ก่อนใช้งาน:\n\n"
        "```toml\nSUPABASE_URL = \"https://xxxx.supabase.co\"\nSUPABASE_KEY = \"xxxx\"\n```"
    )
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔒 อ่านค่า Webhook / Config อื่นๆ จาก st.secrets
ADMIN_DISCORD_WEBHOOK = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
GDRIVE_FOLDER_ID = st.secrets.get("GDRIVE_FOLDER_ID", "")

# ==========================================
# 🚨 WATCHDOG: เฝ้าระวังสถานะบอทและแจ้งเตือน Discord
# ==========================================
def check_and_alert_bot_health(bot_data_list):
    """ตรวจสอบสถานะบอททั้งหมด และยิงแจ้งเตือนเข้า Discord เมื่อพบปัญหา (เว้นระยะ 30 นาทีต่อเครื่อง)"""
    webhook_url = ADMIN_DISCORD_WEBHOOK
    if not webhook_url or not bot_data_list:
        return

    if "alerted_bots" not in st.session_state:
        st.session_state.alerted_bots = {}

    now_utc = datetime.now(timezone.utc)

    for bot in bot_data_list:
        k_code = str(bot.get("license_key", "Unknown"))
        status = str(bot.get("status", "")).upper()
        step_info = str(bot.get("current_step", "-"))
        last_seen_raw = bot.get("last_seen") or bot.get("last_heartbeat")

        is_problem = False
        problem_reason = ""

        if "CRASH" in status:
            is_problem = True
            problem_reason = "💥 บอทขัดข้อง / CRASH"
        elif "CAPTCHA" in step_info.upper() or "ติด" in step_info:
            is_problem = True
            problem_reason = "🚨 บอทติด CAPTCHA ต้องแก้ด่วน"

        if last_seen_raw and not is_problem:
            try:
                last_seen_dt = pd.to_datetime(last_seen_raw, utc=True)
                diff_mins = (now_utc - last_seen_dt).total_seconds() / 60
                if diff_mins > 5 and status == "RUNNING":
                    is_problem = True
                    problem_reason = f"⚠️ ขาดการเชื่อมต่อเกิน {int(diff_mins)} นาที (เครื่องดับ/เน็ตหลุด)"
            except Exception as ex:
                print(f"[watchdog] parse last_seen failed for {k_code}: {ex}")

        if not is_problem:
            continue

        last_alert_time = st.session_state.alerted_bots.get(k_code)
        should_send = (not last_alert_time) or (datetime.now() - last_alert_time).total_seconds() > 1800

        if not should_send:
            continue

        thai_time_str = now_thai().strftime("%Y-%m-%d %H:%M:%S")
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
                    {"name": "💻 สเปกเครื่อง", "value": f"{str(bot.get('pc_specs', '-'))[:80]}", "inline": False},
                ],
                "footer": {"text": f"ระบบเฝ้าระวังอัตโนมัติ (Watchdog) • {thai_time_str}"},
            }]
        }
        try:
            requests.post(webhook_url, json=payload, timeout=5)
            st.session_state.alerted_bots[k_code] = datetime.now()
        except Exception as ex:
            print(f"[watchdog] discord post failed: {ex}")


# ==========================================
# 🟢 แจ้งเตือน Discord: สร้าง/ต่ออายุ/แก้ไข License Key
# ==========================================
def send_discord_license_alert(action_title, key_code, tier, screens, expire_str, note=""):
    webhook_url = ADMIN_DISCORD_WEBHOOK
    if not webhook_url:
        return

    thai_now_str = now_thai().strftime("%Y-%m-%d %H:%M:%S")
    is_create = "สร้าง" in action_title
    color = 5763719 if is_create else 3447003

    payload = {
        "embeds": [{
            "title": f"🔑 {action_title}",
            "color": color,
            "fields": [
                {"name": "🔑 License Key", "value": f"`{key_code}`", "inline": True},
                {"name": "⭐ ระดับสิทธิ์", "value": f"`{str(tier).upper()}`", "inline": True},
                {"name": "💻 จำนวนจอ", "value": f"`{screens} จอ`", "inline": True},
                {"name": "⏰ วันหมดอายุ", "value": f"**{expire_str}**", "inline": False},
                {"name": "📝 ลูกค้า / บันทึก (Note)", "value": f"{note or '-'}", "inline": False},
            ],
            "footer": {"text": f"ระบบจัดการ License อัตโนมัติ • {thai_now_str}"},
        }]
    }
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception as ex:
        print(f"[license_alert] discord post failed: {ex}")


# ==========================================
# 🟢 แจ้งเตือน Discord: คีย์ใกล้หมดอายุ (ล่วงหน้า)
# ==========================================
def send_discord_expiry_warning(key_code, tier, screens, expire_str, hours_left, note=""):
    webhook_url = ADMIN_DISCORD_WEBHOOK
    if not webhook_url:
        return
    thai_now_str = now_thai().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "embeds": [{
            "title": "⏳ คีย์ใกล้หมดอายุ",
            "color": 16763904,
            "fields": [
                {"name": "🔑 License Key", "value": f"`{key_code}`", "inline": True},
                {"name": "⭐ ระดับสิทธิ์", "value": f"`{str(tier).upper()}`", "inline": True},
                {"name": "💻 จำนวนจอ", "value": f"`{screens} จอ`", "inline": True},
                {"name": "⏰ จะหมดอายุ", "value": f"**{expire_str}** (อีก ~{hours_left} ชม.)", "inline": False},
                {"name": "📝 ลูกค้า / บันทึก (Note)", "value": f"{note or '-'}", "inline": False},
            ],
            "footer": {"text": f"ระบบแจ้งเตือนล่วงหน้า • {thai_now_str}"},
        }]
    }
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception as ex:
        print(f"[expiry_warning] discord post failed: {ex}")


def run_expiry_warning_check(df_keys):
    """เช็คคีย์ที่จะหมดอายุใน 72 ชม. ข้างหน้า แล้วแจ้งเตือน Discord ล่วงหน้า (ครั้งเดียวต่อคีย์ ทุก 12 ชม.)"""
    if df_keys.empty or not ADMIN_DISCORD_WEBHOOK:
        return
    if "expiry_warned" not in st.session_state:
        st.session_state.expiry_warned = {}

    nowt = now_thai()
    for _, row in df_keys.iterrows():
        if not row.get("is_active_bool", True):
            continue
        exp_val = row.get("expire_date") or row.get("expires_at")
        if not exp_val or pd.isna(exp_val):
            continue
        exp_dt = parse_to_thai_datetime(exp_val)
        if not exp_dt:
            continue
        diff_hours = (exp_dt - nowt).total_seconds() / 3600
        if 0 < diff_hours <= 72:
            k_code = row.get("license_key")
            last_warn = st.session_state.expiry_warned.get(k_code)
            if last_warn and (datetime.now() - last_warn).total_seconds() < 43200:
                continue
            send_discord_expiry_warning(
                key_code=k_code,
                tier=row.get("display_tier", "normal"),
                screens=row.get("display_screens", 1),
                expire_str=exp_dt.strftime("%Y-%m-%d %H:%M"),
                hours_left=int(diff_hours),
                note=row.get("display_note", ""),
            )
            st.session_state.expiry_warned[k_code] = datetime.now()


# ==========================================
# 🕒 Helper: แปลงวันที่ทุกรูปแบบเป็น Datetime เวลาไทย
# ==========================================
def parse_to_thai_datetime(ts_val):
    if not ts_val or pd.isna(ts_val):
        return None
    s = str(ts_val).strip()
    try:
        if "+07" in s:
            clean_s = s.split("+")[0].replace("T", " ")[:19]
            return datetime.strptime(clean_s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=THAI_TZ)
        if "Z" in s:
            return pd.to_datetime(s, utc=True).tz_convert("Asia/Bangkok").to_pydatetime()
        clean_s = s.replace("T", " ")[:19]
        if len(clean_s) == 10:
            return datetime.strptime(clean_s + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=THAI_TZ)
        return datetime.strptime(clean_s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=THAI_TZ)
    except Exception:
        return None


def safe_format_thai_time(ts_val):
    if not ts_val or pd.isna(ts_val):
        return "ตลอดชีพ"
    dt = parse_to_thai_datetime(ts_val)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(ts_val)[:16]


def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


def generate_random_key(length=16):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def log_admin_action(action, detail=""):
    """บันทึก audit log การกระทำของแอดมิน (best-effort — ไม่ทำให้แอปพังถ้า insert ไม่สำเร็จ)"""
    try:
        supabase.table("admin_audit_log").insert({
            "action": action,
            "detail": detail,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as ex:
        print(f"[audit_log] insert failed (ตาราง admin_audit_log อาจยังไม่ถูกสร้าง): {ex}")

# ==========================================
# 🟢 อัปโหลดไฟล์ขึ้น Google Drive (สำรอง — ใช้เมื่อเปิดใช้งาน)
# ==========================================
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
        body=file_metadata, media_body=media, fields="id, name, webViewLink, webContentLink"
    ).execute()
    return uploaded


# ==========================================
# 🟢 Relay Worker: ยิงภาพ/ข้อความแจ้งเตือนเข้า Discord แบบพื้นหลัง
# ==========================================
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
                        "pending_alert_img": None,
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
                                files = {"file": ("screenshot.png", img_bytes, "image/png")}
                            except Exception as ex:
                                print(f"[relay_worker] decode image failed: {ex}")
                        try:
                            requests.post(ADMIN_DISCORD_WEBHOOK, data=payload_data, files=files, timeout=8)
                        except Exception as ex:
                            print(f"[relay_worker] discord post failed: {ex}")
        except Exception as ex:
            print(f"[relay_worker] loop error: {ex}")
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

# ==========================================
# 🔒 ระบบยืนยันตัวตนแอดมิน — พร้อม Rate Limit / Lockout กัน Brute-force
# ==========================================
ADMIN_PIN = st.secrets.get("ADMIN_PIN", "")
if not ADMIN_PIN:
    st.error("❌ ยังไม่ได้ตั้งค่า ADMIN_PIN ใน st.secrets — กรุณาตั้งค่าก่อนใช้งานระบบ")
    st.stop()

MAX_PIN_ATTEMPTS = 5          # จำนวนครั้งที่กรอกผิดได้ก่อนถูกล็อก
LOCKOUT_SECONDS = 300          # ระยะเวลาที่ถูกล็อก (5 นาที) หลังกรอกผิดครบจำนวน
ATTEMPT_WINDOW_SECONDS = 600   # นับจำนวนครั้งผิดภายในกรอบเวลานี้ (10 นาที) แล้วรีเซ็ต

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "pin_fail_count" not in st.session_state:
    st.session_state.pin_fail_count = 0
if "pin_first_fail_at" not in st.session_state:
    st.session_state.pin_first_fail_at = None
if "pin_locked_until" not in st.session_state:
    st.session_state.pin_locked_until = None


def _reset_pin_attempts():
    st.session_state.pin_fail_count = 0
    st.session_state.pin_first_fail_at = None
    st.session_state.pin_locked_until = None


def _register_pin_failure():
    now = datetime.now()
    # ถ้าเกินกรอบเวลานับ ให้เริ่มนับใหม่
    if st.session_state.pin_first_fail_at and (now - st.session_state.pin_first_fail_at).total_seconds() > ATTEMPT_WINDOW_SECONDS:
        st.session_state.pin_fail_count = 0
        st.session_state.pin_first_fail_at = None

    if st.session_state.pin_fail_count == 0:
        st.session_state.pin_first_fail_at = now

    st.session_state.pin_fail_count += 1

    if st.session_state.pin_fail_count >= MAX_PIN_ATTEMPTS:
        st.session_state.pin_locked_until = now + timedelta(seconds=LOCKOUT_SECONDS)


def _is_locked_out():
    locked_until = st.session_state.pin_locked_until
    if not locked_until:
        return False, 0
    remaining = (locked_until - datetime.now()).total_seconds()
    if remaining <= 0:
        _reset_pin_attempts()
        return False, 0
    return True, int(remaining)


if not st.session_state.authenticated:
    inject_theme()
    st.markdown('<div class="cx-login-wrap">', unsafe_allow_html=True)
    st.markdown(
        '<div class="cx-brand-logo" style="margin:0 auto 14px auto;">⚡</div>',
        unsafe_allow_html=True,
    )
    st.title("🔒 Cookie X Admin")
    st.caption("ระบบจัดการบอท Cookie X (กรุณากรอก PIN เพื่อเข้าใช้งาน)")

    locked, remaining_sec = _is_locked_out()

    if locked:
        mins, secs = divmod(remaining_sec, 60)
        st.error(
            f"🚫 กรอกรหัสผิดเกินกำหนด ({MAX_PIN_ATTEMPTS} ครั้ง) — ระบบล็อกชั่วคราว\n\n"
            f"กรุณาลองใหม่อีกครั้งใน **{mins} นาที {secs} วินาที**"
        )
        st.button("🔄 ตรวจสอบสถานะอีกครั้ง")
    else:
        remaining_tries = MAX_PIN_ATTEMPTS - st.session_state.pin_fail_count
        pin_input = st.text_input("กรอกรหัส Admin PIN:", type="password", key="pin_input_box")

        if st.session_state.pin_fail_count > 0:
            st.warning(f"⚠️ รหัสไม่ถูกต้อง — เหลือโอกาสอีก {remaining_tries} ครั้ง ก่อนถูกล็อกชั่วคราว")

        if st.button("เข้าสู่ระบบ", type="primary"):
            if pin_input == ADMIN_PIN:
                _reset_pin_attempts()
                st.session_state.authenticated = True
                st.success("เข้าสู่ระบบสำเร็จ!")
                log_admin_action("login_success")
                st.rerun()
            else:
                _register_pin_failure()
                log_admin_action("login_failed")
                still_locked, still_remaining = _is_locked_out()
                if still_locked:
                    mins, secs = divmod(still_remaining, 60)
                    st.error(f"🚫 กรอกผิดครบ {MAX_PIN_ATTEMPTS} ครั้ง — ระบบล็อก {mins} นาที {secs} วินาที")
                else:
                    st.error("รหัส PIN ไม่ถูกต้อง!")
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ------------------- ส่วนเมนูเลือกใช้งาน -------------------
sidebar_brand()

menu = st.sidebar.radio(
    "เลือกเมนูใช้งาน",
    [
        "🏠 ภาพรวม (Overview)",
        "📊 Live Monitor (มอนิเตอร์บอท)",
        "🔑 Key Manager (จัดการคีย์)",
        "💻 Active Sessions (เซสชันจอสด)",
        "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)",
    ],
    label_visibility="collapsed",
)

st.sidebar.divider()
if st.sidebar.button("🚪 ออกจากระบบ", use_container_width=True):
    log_admin_action("logout")
    st.session_state.authenticated = False
    st.rerun()

st.sidebar.caption(f"🕒 เวลาปัจจุบัน (ไทย): {now_thai().strftime('%Y-%m-%d %H:%M:%S')}")

# ---------------------------------------------------------
# 🏠 TAB 0: OVERVIEW — สรุปภาพรวมทุกระบบในหน้าเดียว
# ---------------------------------------------------------
if menu == "🏠 ภาพรวม (Overview)":
    page_header("🏠 ภาพรวมระบบ", "สรุปสถานะบอท คีย์ เซสชัน และการเงิน ในหน้าเดียว")

    ov_col1, ov_col2 = st.columns(2)

    # --- โซนบอท / เซสชัน ---
    with ov_col1:
        st.markdown("#### 🤖 สถานะบอท")
        try:
            res_bots = supabase.table("user_monitors").select("*").execute()
            bots = res_bots.data or []
            total_bots = len(bots)
            running = len([b for b in bots if str(b.get("status", "")).upper() == "RUNNING"])
            crashed = len([b for b in bots if "CRASH" in str(b.get("status", "")).upper()])
            captcha = len([b for b in bots if "CAPTCHA" in str(b.get("current_step", "")).upper() or "ติด" in str(b.get("current_step", ""))])

            bc1, bc2, bc3 = st.columns(3)
            bc1.metric("ทั้งหมด", f"{total_bots}")
            bc2.metric("🟢 รันอยู่", f"{running}")
            bc3.metric("🚨 มีปัญหา", f"{crashed + captcha}")
        except Exception as e:
            st.error(f"โหลดข้อมูลบอทไม่สำเร็จ: {e}")

        st.markdown("#### 💻 เซสชันที่เปิดอยู่")
        try:
            res_sess_ov = supabase.table("active_sessions").select("*").execute()
            sess_ov = res_sess_ov.data or []
            st.metric("จอที่เปิดใช้งานตอนนี้", f"{len(sess_ov)} จอ")
        except Exception as e:
            st.error(f"โหลดข้อมูลเซสชันไม่สำเร็จ: {e}")

    # --- โซนคีย์ / การเงิน ---
    with ov_col2:
        st.markdown("#### 🔑 License Keys")
        try:
            res_keys_ov = supabase.table("licenses").select("*").execute()
            keys_ov = res_keys_ov.data or []
            df_ov = pd.DataFrame(keys_ov) if keys_ov else pd.DataFrame()

            expiring_soon = 0
            expired_now = 0
            if not df_ov.empty:
                for _, r in df_ov.iterrows():
                    exp_val = r.get("expire_date") or r.get("expires_at")
                    if not exp_val or pd.isna(exp_val):
                        continue
                    exp_dt = parse_to_thai_datetime(exp_val)
                    if not exp_dt:
                        continue
                    diff_h = (exp_dt - now_thai()).total_seconds() / 3600
                    if diff_h <= 0:
                        expired_now += 1
                    elif diff_h <= 72:
                        expiring_soon += 1

            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("คีย์ทั้งหมด", f"{len(df_ov)}")
            kc2.metric("⏳ ใกล้หมดอายุ (72ชม.)", f"{expiring_soon}")
            kc3.metric("🔴 หมดอายุแล้ว", f"{expired_now}")
        except Exception as e:
            st.error(f"โหลดข้อมูลคีย์ไม่สำเร็จ: {e}")

        st.markdown("#### 💰 การเงินเดือนนี้")
        try:
            res_acc_ov = supabase.table("accounting_records").select("*").execute()
            acc_ov = res_acc_ov.data or []
            if acc_ov:
                df_acc_ov = pd.DataFrame(acc_ov)
                df_acc_ov["created_at"] = pd.to_datetime(df_acc_ov["created_at"], errors="coerce")
                today_ov = datetime.now().date()
                this_month = df_acc_ov[
                    (df_acc_ov["created_at"].dt.year == today_ov.year)
                    & (df_acc_ov["created_at"].dt.month == today_ov.month)
                    & (df_acc_ov.get("status", "completed").fillna("completed") == "completed")
                ]
                income_ov = this_month[this_month["type"] == "income"]["amount"].sum()
                expense_ov = this_month[this_month["type"] == "expense"]["amount"].sum()
                fc1, fc2 = st.columns(2)
                fc1.metric("🟢 รายรับเดือนนี้", f"฿{income_ov:,.0f}")
                fc2.metric("🔴 รายจ่ายเดือนนี้", f"฿{expense_ov:,.0f}")
            else:
                st.info("ยังไม่มีข้อมูลบัญชี")
        except Exception as e:
            st.error(f"โหลดข้อมูลบัญชีไม่สำเร็จ: {e}")

    st.divider()
    st.caption("💡 เลือกเมนูด้านซ้ายเพื่อดูรายละเอียดและจัดการแต่ละระบบ")

# ---------------------------------------------------------
# 📊 TAB: LIVE MONITOR (พร้อม Watchdog + ค้นหา)
# ---------------------------------------------------------
elif menu == "📊 Live Monitor (มอนิเตอร์บอท)":
    page_header("📊 Live Bot Monitor", "มอนิเตอร์สถานะลูกค้าเรียลไทม์และสเปคฮาร์ดแวร์เครื่องลูกค้า")

    top_c1, top_c2 = st.columns([1, 5])
    with top_c1:
        if st.button("🔄 รีเฟรชข้อมูลสด"):
            st.rerun()

    try:
        res = supabase.table("user_monitors").select("*").execute()
        data = res.data
        if data:
            check_and_alert_bot_health(data)

            df = pd.DataFrame(data)
            if "last_seen" in df.columns:
                df["last_seen"] = pd.to_datetime(df["last_seen"], utc=True, errors="coerce").dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

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

            search_bot = st.text_input("🔍 ค้นหาบอท (License Key / สถานะ / ขั้นตอน):", placeholder="พิมพ์เพื่อค้นหา...")
            df_show = df.copy()
            if search_bot.strip():
                mask = pd.Series(False, index=df_show.index)
                for col in ["license_key", "status", "current_step"]:
                    if col in df_show.columns:
                        mask = mask | df_show[col].fillna("").astype(str).str.contains(search_bot.strip(), case=False)
                df_show = df_show[mask]

            show_cols = ["license_key", "status", "current_step", "farm_mode", "boxes_collected", "lives_collected", "cpu_usage", "ram_usage", "pc_specs", "bot_version", "last_seen"]
            existing_cols = [c for c in show_cols if c in df_show.columns]
            st.dataframe(df_show[existing_cols], use_container_width=True, hide_index=True)
        else:
            st.info("ยังไม่มีข้อมูลมอนิเตอร์ในระบบ")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

# ---------------------------------------------------------
# 🔑 TAB: KEY MANAGER
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    page_header("🔑 License Key Manager", "ระบบจัดการคีย์ลูกค้า เชื่อมต่อฐานข้อมูลจริง กำหนดเวลา วัน/ชม./นาที (เวลาไทย UTC+7)")

    thai_tz = THAI_TZ
    now_thai_val = now_thai()

    try:
        res_keys = supabase.table("licenses").select("*").execute()
        raw_licenses = res_keys.data or []
        df_keys = pd.DataFrame(raw_licenses) if raw_licenses else pd.DataFrame()

        if not df_keys.empty:
            df_keys["display_note"] = df_keys.apply(lambda r: r.get("Note") if pd.notna(r.get("Note")) else (r.get("note") or ""), axis=1)
            df_keys["display_tier"] = df_keys.apply(lambda r: str(r.get("key_type") or r.get("tier") or "normal").capitalize(), axis=1)
            df_keys["display_screens"] = df_keys.apply(lambda r: safe_int(r.get("max_sessions") if pd.notna(r.get("max_sessions")) else r.get("max_concurrent"), 1), axis=1)
            df_keys["is_active_bool"] = df_keys.apply(lambda r: bool(r.get("is_active")) if "is_active" in r and pd.notna(r.get("is_active")) else (str(r.get("status", "active")).lower() == "active"), axis=1)

            def calculate_key_status(row):
                if not row["is_active_bool"]:
                    return "🔴 ระงับการใช้งาน", "ถูกระงับ"
                exp_val = row.get("expire_date") or row.get("expires_at")
                if not exp_val or pd.isna(exp_val):
                    return "🟢 ใช้งานได้ (ตลอดชีพ)", "ไม่มีวันหมดอายุ"
                exp_dt = parse_to_thai_datetime(exp_val)
                if not exp_dt:
                    return "🟢 กำลังใช้งาน", "-"
                diff = exp_dt - now_thai_val
                if diff.total_seconds() > 0:
                    total_sec = int(diff.total_seconds())
                    days = total_sec // 86400
                    hours = (total_sec % 86400) // 3600
                    mins = (total_sec % 3600) // 60
                    if days > 0:
                        return "🟢 กำลังใช้งาน", f"เหลือ {days}วัน {hours}ชม. {mins}น."
                    return "🟢 กำลังใช้งาน", f"เหลือ {hours}ชม. {mins}น."
                return "⏳ หมดอายุแล้ว", "หมดอายุ"

            res_status = [calculate_key_status(r) for _, r in df_keys.iterrows()]
            df_keys["สถานะระบบ"] = [s[0] for s in res_status]
            df_keys["เวลาคงเหลือ"] = [s[1] for s in res_status]

            # 🔔 เช็คแจ้งเตือนคีย์ใกล้หมดอายุล่วงหน้า (feature ใหม่)
            run_expiry_warning_check(df_keys)

            active_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("🟢")])
            expired_grace_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("⏳")])
            suspended_count = len(df_keys[df_keys["สถานะระบบ"].str.contains("🔴")])
            total_screens = df_keys[df_keys["สถานะระบบ"].str.contains("🟢")]["display_screens"].sum()
        else:
            active_count = expired_grace_count = suspended_count = total_screens = 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔑 คีย์ทั้งหมด", f"{len(df_keys):,} คีย์")
        m2.metric("🟢 พร้อมใช้งาน", f"{active_count:,} คีย์")
        m3.metric("💻 โควตาจอรันจริง", f"{total_screens:,} จอ")
        m4.metric("⏳ หมดอายุแล้ว", f"{expired_grace_count:,} คีย์")

        st.write("")

        tab_table, tab_grace, tab_add, tab_manage = st.tabs([
            f"📋 รายการคีย์ทั้งหมด ({len(df_keys)})",
            f"⏳ คีย์หมดอายุ ({expired_grace_count})",
            "➕ สร้างคีย์ใหม่ (Add Key)",
            "⚙️ แก้ไข / จัดการคีย์ (Manage)",
        ])

        # --- TAB 1: ตารางคีย์ทั้งหมด + Bulk actions ---
        with tab_table:
            if not df_keys.empty:
                f1, f2, f3 = st.columns([2, 1, 1])
                with f1:
                    search_txt = st.text_input("🔍 ค้นหาคีย์ / ชื่อลูกค้า (Note) / HWID:", placeholder="พิมพ์ค้นหา เช่น พี่นิว, เต้ NB...", key="s_all_keys")
                with f2:
                    filter_st = st.selectbox("📌 กรองสถานะ:", ["ทั้งหมด", "🟢 กำลังใช้งาน", "⏳ หมดอายุแล้ว", "🔴 ระงับการใช้งาน"], key="f_st_keys")
                with f3:
                    tier_list = ["ทั้งหมด"] + sorted(list(df_keys["display_tier"].dropna().unique()))
                    filter_tr = st.selectbox("⭐ ระดับ (Key Type):", tier_list, key="f_tr_keys")

                df_disp = df_keys.copy()
                if search_txt.strip():
                    mm1 = df_disp["license_key"].fillna("").astype(str).str.contains(search_txt.strip(), case=False)
                    mm2 = df_disp["display_note"].fillna("").astype(str).str.contains(search_txt.strip(), case=False)
                    mm3 = df_disp["hwid"].fillna("").astype(str).str.contains(search_txt.strip(), case=False) if "hwid" in df_disp.columns else pd.Series(False, index=df_disp.index)
                    df_disp = df_disp[mm1 | mm2 | mm3]
                if filter_st != "ทั้งหมด":
                    df_disp = df_disp[df_disp["สถานะระบบ"].str.contains(filter_st.split()[0])]
                if filter_tr != "ทั้งหมด":
                    df_disp = df_disp[df_disp["display_tier"] == filter_tr]

                df_disp["วันหมดอายุ"] = df_disp.apply(lambda r: safe_format_thai_time(r.get("expire_date") or r.get("expires_at")), axis=1)
                df_disp["เลือก"] = False

                display_columns = ["เลือก", "license_key", "สถานะระบบ", "เวลาคงเหลือ", "display_tier", "display_screens", "วันหมดอายุ", "hwid", "display_note"]

                edited_df = st.data_editor(
                    df_disp[display_columns],
                    column_config={
                        "เลือก": st.column_config.CheckboxColumn("✅"),
                        "license_key": st.column_config.TextColumn("🔑 License Key", disabled=True),
                        "สถานะระบบ": st.column_config.TextColumn("สถานะ", disabled=True),
                        "เวลาคงเหลือ": st.column_config.TextColumn("⏰ เวลาคงเหลือ", disabled=True),
                        "display_tier": st.column_config.TextColumn("ระดับ (Key Type)", disabled=True),
                        "display_screens": st.column_config.NumberColumn("จำนวนจอ (Max Sessions)", format="%d จอ", disabled=True),
                        "วันหมดอายุ": st.column_config.TextColumn("วันหมดอายุ", disabled=True),
                        "hwid": st.column_config.TextColumn("HWID เครื่อง", disabled=True),
                        "display_note": st.column_config.TextColumn("📝 ลูกค้า / บันทึก (Note)", disabled=True),
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="key_bulk_editor",
                )

                selected_rows = edited_df[edited_df["เลือก"] == True]
                if not selected_rows.empty:
                    st.info(f"✅ เลือกไว้ {len(selected_rows)} คีย์")
                    bulk_c1, bulk_c2, bulk_c3 = st.columns(3)
                    with bulk_c1:
                        if st.button(f"⚡ ต่ออายุทั้งหมด +30 วัน ({len(selected_rows)} คีย์)", use_container_width=True):
                            new_exp = (now_thai_val + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                            for kcode in selected_rows["license_key"]:
                                supabase.table("licenses").update({"expire_date": new_exp, "is_active": True}).eq("license_key", kcode).execute()
                            log_admin_action("bulk_renew_30d", f"{len(selected_rows)} keys")
                            st.success(f"ต่ออายุ {len(selected_rows)} คีย์เรียบร้อย!")
                            st.rerun()
                    with bulk_c2:
                        if st.button("🔴 ระงับทั้งหมดที่เลือก", use_container_width=True):
                            for kcode in selected_rows["license_key"]:
                                supabase.table("licenses").update({"is_active": False}).eq("license_key", kcode).execute()
                            log_admin_action("bulk_suspend", f"{len(selected_rows)} keys")
                            st.success(f"ระงับ {len(selected_rows)} คีย์เรียบร้อย!")
                            st.rerun()
                    with bulk_c3:
                        if st.button("🗑️ ลบทั้งหมดที่เลือก", use_container_width=True, type="primary"):
                            for kcode in selected_rows["license_key"]:
                                supabase.table("licenses").delete().eq("license_key", kcode).execute()
                            log_admin_action("bulk_delete", f"{len(selected_rows)} keys")
                            st.success(f"ลบ {len(selected_rows)} คีย์เรียบร้อย!")
                            st.rerun()
            else:
                st.info("ยังไม่มีข้อมูล License Key ในระบบ")

        # --- TAB 2: คีย์หมดอายุ ---
        with tab_grace:
            df_grace = df_keys[df_keys["สถานะระบบ"].str.contains("⏳")] if not df_keys.empty else pd.DataFrame()
            if not df_grace.empty:
                st.warning("⚠️ รายการคีย์ด้านล่างนี้หมดอายุแล้ว สามารถกดต่ออายุให้ลูกค้า หรือกดลบทิ้งได้ทันที")
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
                                new_exp_thai = (now_thai_val + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                                supabase.table("licenses").update({"expire_date": new_exp_thai, "is_active": True}).eq("license_key", k_code).execute()
                                send_discord_license_alert(
                                    action_title="ต่ออายุคีย์อัตโนมัติ (+30 วัน)",
                                    key_code=k_code, tier=str(r_exp.get("display_tier", "Normal")),
                                    screens=r_exp.get("display_screens", 1), expire_str=new_exp_thai,
                                    note=r_exp.get("display_note", ""),
                                )
                                log_admin_action("renew_key_30d", k_code)
                                st.success(f"ต่ออายุคีย์ `{k_code}` สำเร็จ!")
                                st.rerun()
                        with b2:
                            if st.button("🗑️ ลบทันที", key=f"btn_dl_{k_code}"):
                                supabase.table("licenses").delete().eq("license_key", k_code).execute()
                                log_admin_action("delete_key", k_code)
                                st.rerun()
                    st.write("---")
            else:
                st.success("🎉 ไม่มีคีย์ที่หมดอายุค้างอยู่ในระบบ")

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
                    now_thai_add = now_thai()

                    if total_delta.total_seconds() > 0:
                        expire_time = now_thai_add + total_delta
                        exp_str = expire_time.strftime("%Y-%m-%d %H:%M:%S")
                        exp_msg = expire_time.strftime("%Y-%m-%d %H:%M น.")
                    else:
                        exp_str = None
                        exp_msg = "ตลอดชีพ (ไม่มีวันหมดอายุ)"

                    key_payload = {
                        "license_key": final_key,
                        "max_sessions": int(max_sessions),
                        "key_type": tier_type.lower(),
                        "Note": customer_note.strip(),
                        "expire_date": exp_str,
                        "is_active": True,
                    }

                    try:
                        supabase.table("licenses").insert(key_payload).execute()
                        send_discord_license_alert(
                            action_title="สร้าง License Key ใหม่", key_code=final_key, tier=tier_type,
                            screens=max_sessions, expire_str=exp_msg, note=customer_note.strip(),
                        )
                        log_admin_action("create_key", final_key)
                        st.success(f"✅ สร้างคีย์ `{final_key}` สำเร็จ! (วันหมดอายุ: {exp_msg})")
                        st.rerun()
                    except Exception as err:
                        st.error(f"สร้างคีย์ไม่สำเร็จ: {err}")

        # --- TAB 4: แก้ไข / จัดการคีย์ ---
        with tab_manage:
            if not df_keys.empty:
                manage_options = [
                    f"{r['license_key']} | {r.get('display_tier','Normal')} | {r.get('display_note','') or 'ไม่มีบันทึก'}"
                    for _, r in df_keys.iterrows()
                ]
                selected_manage = st.selectbox("เลือกคีย์ที่ต้องการจัดการ:", manage_options, key="sel_manage_key")

                if selected_manage:
                    target_code = selected_manage.split(" | ")[0]
                    target_obj = next((r for r in raw_licenses if r["license_key"] == target_code), None)

                    if target_obj:
                        cur_exp_raw = target_obj.get("expire_date") or target_obj.get("expires_at")
                        cur_exp_str = ""
                        cur_exp_dt = None
                        try:
                            if cur_exp_raw and not pd.isna(cur_exp_raw):
                                cur_exp_clean = str(cur_exp_raw).replace("T", " ")[:19]
                                if len(cur_exp_clean) == 10:
                                    cur_exp_clean += " 23:59:59"
                                cur_exp_dt = datetime.strptime(cur_exp_clean, "%Y-%m-%d %H:%M:%S").replace(tzinfo=thai_tz)
                                cur_exp_str = cur_exp_dt.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                cur_exp_str = (now_thai_val + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            cur_exp_str = (now_thai_val + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            cur_sess = target_obj.get("max_sessions") if pd.notna(target_obj.get("max_sessions")) else 1
                            new_max_screens = st.number_input("💻 ปรับจำนวนจอ (Max Sessions):", min_value=1, value=safe_int(cur_sess, 1), step=1)
                            edit_expire_text = st.text_input(
                                "📅 วันหมดอายุ (พิมพ์แก้ไขตรงนี้ได้เลย รูปแบบ YYYY-MM-DD HH:MM:SS):",
                                value=cur_exp_str,
                            )
                            st.write("**⏳ หรือ เพิ่มเวลาต่ออายุ (+วัน/+ชม./+นาที):**")
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
                                update_data = {
                                    "max_sessions": int(new_max_screens),
                                    "Note": new_note.strip(),
                                    "is_active": True if "Active" in new_active_status else False,
                                }
                                if reset_hwid_flag:
                                    update_data["hwid"] = None

                                added_delta = timedelta(days=int(add_days), hours=int(add_hours), minutes=int(add_mins))
                                if added_delta.total_seconds() > 0:
                                    base_dt = cur_exp_dt if (cur_exp_dt and cur_exp_dt > now_thai_val) else now_thai_val
                                    final_expire_dt = base_dt + added_delta
                                    final_expire_str = final_expire_dt.strftime("%Y-%m-%d %H:%M:%S")
                                else:
                                    final_expire_str = edit_expire_text.strip()

                                update_data["expire_date"] = final_expire_str

                                try:
                                    supabase.table("licenses").update(update_data).eq("license_key", target_code).execute()
                                    send_discord_license_alert(
                                        action_title="อัปเดตข้อมูล / แก้ไขเวลาคีย์", key_code=target_code,
                                        tier=str(target_obj.get("key_type", "normal")), screens=new_max_screens,
                                        expire_str=final_expire_str, note=new_note.strip(),
                                    )
                                    log_admin_action("update_key", target_code)
                                    st.success(f"🎉 อัปเดตคีย์ `{target_code}` สำเร็จ! (วันหมดอายุ: {final_expire_str})")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"อัปเดตไม่สำเร็จ: {err}")
                        with col_btn2:
                            if st.button("❌ ลบคีย์นี้ทิ้งถาวร"):
                                try:
                                    supabase.table("licenses").delete().eq("license_key", target_code).execute()
                                    log_admin_action("delete_key", target_code)
                                    st.success(f"ลบคีย์ `{target_code}` แล้ว!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"ลบไม่สำเร็จ: {err}")
            else:
                st.info("ยังไม่มีคีย์ให้จัดการ")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล License: {e}")

# ---------------------------------------------------------
# 💻 TAB: ACTIVE SESSIONS — พร้อมค้นหา และ Kick Session
# ---------------------------------------------------------
elif menu == "💻 Active Sessions (เซสชันจอสด)":
    page_header("💻 Active Sessions Control", "ตรวจสอบและจัดการเซสชันจอที่กำลังเปิดรันอยู่สดๆ ทั้งหมด")

    if st.button("🔄 รีเฟรชรายการเซสชัน"):
        st.rerun()

    try:
        res_sess = supabase.table("active_sessions").select("*").execute()
        sess_data = res_sess.data
        if sess_data:
            df_sess = pd.DataFrame(sess_data)
            if "last_heartbeat" in df_sess.columns:
                df_sess["last_heartbeat"] = pd.to_datetime(df_sess["last_heartbeat"], errors="coerce").dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            st.write(f"📊 **จำนวนจอที่เปิดใช้งานอยู่ขณะนี้:** `{len(df_sess)} จอ`")

            search_sess = st.text_input("🔍 ค้นหาเซสชัน (License Key / HWID):", placeholder="พิมพ์เพื่อค้นหา...")
            df_sess_show = df_sess.copy()
            if search_sess.strip():
                mask = pd.Series(False, index=df_sess_show.index)
                for col in ["license_key", "hwid", "session_id"]:
                    if col in df_sess_show.columns:
                        mask = mask | df_sess_show[col].fillna("").astype(str).str.contains(search_sess.strip(), case=False)
                df_sess_show = df_sess_show[mask]

            show_sess_cols = ["id", "license_key", "session_id", "hwid", "last_heartbeat"]
            existing_sess_cols = [c for c in show_sess_cols if c in df_sess_show.columns]
            st.dataframe(df_sess_show[existing_sess_cols], use_container_width=True, hide_index=True)

            st.divider()
            st.markdown("#### ⛔ บังคับตัดการเชื่อมต่อ (Kick Session)")
            if "id" in df_sess_show.columns and not df_sess_show.empty:
                kick_options = [
                    f"ID: {r['id']} | {r.get('license_key','-')} | HWID: {str(r.get('hwid','-'))[:20]}"
                    for _, r in df_sess_show.iterrows()
                ]
                kick_sel = st.selectbox("เลือกเซสชันที่ต้องการตัดออก:", kick_options, key="sel_kick_sess")
                if st.button("⛔ ตัดการเชื่อมต่อเซสชันนี้", type="primary"):
                    kick_id = kick_sel.split("ID: ")[1].split(" |")[0]
                    try:
                        supabase.table("active_sessions").delete().eq("id", kick_id).execute()
                        log_admin_action("kick_session", kick_sel)
                        st.success(f"ตัดการเชื่อมต่อเซสชัน ID {kick_id} เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"ตัดการเชื่อมต่อไม่สำเร็จ: {err}")
            else:
                st.caption("ไม่มีเซสชันให้ตัดการเชื่อมต่อ")
        else:
            st.info("ขณะนี้ไม่มีเซสชันจอเปิดรันอยู่ในระบบ")
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

# ---------------------------------------------------------
# 💰 TAB: บันทึกรายรับ-รายจ่าย & สลิป (Accounting)
# ---------------------------------------------------------
elif menu == "💰 บันทึกรายรับ-รายจ่าย & สลิป (Accounting)":
    page_header("💰 ระบบบันทึกรายรับ-รายจ่าย & บัญชีร้าน", "ระบบจัดการการเงินครบวงจร บันทึกบัญชี แนบสลิป อนุมัติรายการรอยืนยัน สรุปกราฟ และส่งออกข้อมูล")

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
        except Exception as ex:
            print(f"[accounting] image compress failed, using original bytes: {ex}")
            compressed_bytes = file_bytes
            final_mime = mimetype
            clean_name = filename

        file_path = f"receipts/{clean_name}"
        supabase.storage.from_("slips").upload(
            path=file_path, file=compressed_bytes, file_options={"content-type": final_mime}
        )
        public_url = supabase.storage.from_("slips").get_public_url(file_path)
        return {"id": file_path, "webViewLink": public_url}

    def delete_slip_from_supabase(file_path):
        if not file_path:
            return
        try:
            supabase.storage.from_("slips").remove([file_path])
        except Exception as ex:
            print(f"[accounting] delete old slip failed: {ex}")

    def send_discord_accounting_alert(tx_type, amount, category, note, status_text, slip_url=""):
        webhook_url = ADMIN_DISCORD_WEBHOOK
        if not webhook_url:
            return
        try:
            is_income = "income" in tx_type.lower() or "รายรับ" in tx_type
            if status_text == "pending":
                color = 16763904
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
                    "title": title, "color": color, "fields": fields,
                    "footer": {"text": f"ระบบบัญชีอัตโนมัติ • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
                }]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as ex:
            print(f"[accounting] discord post failed: {ex}")

    def send_discord_monthly_report(period_label, income_sum, expense_sum, tx_count):
        webhook_url = ADMIN_DISCORD_WEBHOOK
        if not webhook_url:
            return
        net = income_sum - expense_sum
        payload = {
            "embeds": [{
                "title": f"📊 สรุปรายงานบัญชี — {period_label}",
                "color": 3447003 if net >= 0 else 15548997,
                "fields": [
                    {"name": "🟢 รายรับรวม", "value": f"฿{income_sum:,.2f}", "inline": True},
                    {"name": "🔴 รายจ่ายรวม", "value": f"฿{expense_sum:,.2f}", "inline": True},
                    {"name": "💵 กำไรสุทธิ", "value": f"฿{net:,.2f}", "inline": True},
                    {"name": "🧾 จำนวนรายการ (อนุมัติแล้ว)", "value": f"{tx_count} รายการ", "inline": False},
                ],
                "footer": {"text": f"รายงานสรุป • {now_thai().strftime('%Y-%m-%d %H:%M:%S')}"},
            }]
        }
        try:
            requests.post(webhook_url, json=payload, timeout=5)
            return True
        except Exception as ex:
            print(f"[accounting] monthly report post failed: {ex}")
            return False

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
                                upload_res = upload_slip_to_supabase(slip_file.getvalue(), clean_filename, mimetype=slip_file.type)
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
                        "amount": amount, "category": category, "note": combined_note,
                        "slip_url": slip_url, "drive_file_id": drive_file_id, "status": status_val,
                        "created_at": datetime.combine(tx_date, datetime.now().time()).isoformat(),
                    }
                    try:
                        supabase.table("accounting_records").insert(tx_payload).execute()
                        if send_noti:
                            send_discord_accounting_alert(tx_type, amount, category, combined_note, status_val, slip_url)
                        log_admin_action("add_accounting_record", f"{category} ฿{amount:,.2f}")
                        st.success(f"✅ บันทึกรายการ {category} ยอด {amount:,.2f} บาท เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"บันทึกฐานข้อมูลไม่สำเร็จ: {err}")

    # ==========================================
    # 2. รายการรอยืนยัน (Pending Review Box)
    # ==========================================
    acc_data = []
    try:
        res_acc = supabase.table("accounting_records").select("*").order("created_at", desc=True).execute()
        acc_data = res_acc.data or []
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
                        st.markdown(f"**ID: {p_id}** | {p_type} **฿{safe_float(p_item.get('amount')):,.2f}** - {p_item.get('category','')}")
                        st.caption(f"📝 {p_item.get('note','') or 'ไม่มีหมายเหตุ'} | 📅 {str(p_item.get('created_at',''))[:16]}")
                    with p_col2:
                        if p_item.get("slip_url"):
                            st.markdown(f"[📂 คลิกดูรูปสลิป]({p_item['slip_url']})")
                        else:
                            st.caption("ไม่มีรูปสลิป")
                    with p_col3:
                        if st.button("✅ อนุมัติยอด", key=f"apprv_{p_id}", type="primary"):
                            supabase.table("accounting_records").update({"status": "completed"}).eq("id", p_id).execute()
                            log_admin_action("approve_tx", str(p_id))
                            st.success(f"อนุมัติรายการ ID {p_id} เรียบร้อย!")
                            st.rerun()
                    with p_col4:
                        if st.button("❌ ปฏิเสธ", key=f"reject_{p_id}"):
                            supabase.table("accounting_records").update({"status": "rejected"}).eq("id", p_id).execute()
                            log_admin_action("reject_tx", str(p_id))
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
        df_all["created_at"] = pd.to_datetime(df_all["created_at"], errors="coerce")
        df_all["date_only"] = df_all["created_at"].dt.date

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

        if filter_status == "เฉพาะที่สำเร็จ (Completed)":
            df_filtered = df_filtered[df_filtered["status"] == "completed"]
        elif filter_status == "เฉพาะรอยืนยัน (Pending)":
            df_filtered = df_filtered[df_filtered["status"] == "pending"]
        elif filter_status == "เฉพาะปฏิเสธ (Rejected)":
            df_filtered = df_filtered[df_filtered["status"] == "rejected"]

        if filter_cat != "ทั้งหมด":
            df_filtered = df_filtered[df_filtered["category"] == filter_cat]
        if search_kw.strip():
            df_filtered = df_filtered[df_filtered["note"].fillna("").str.contains(search_kw.strip(), case=False)]

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

        # 🟢 ปุ่มส่งรายงานสรุปเข้า Discord (feature ใหม่)
        report_c1, report_c2 = st.columns([1, 4])
        with report_c1:
            if st.button("📤 ส่งสรุปรายงานนี้เข้า Discord"):
                sent_ok = send_discord_monthly_report(filter_period, total_income, total_expense, len(df_completed))
                if sent_ok:
                    log_admin_action("send_report", filter_period)
                    st.success("ส่งรายงานเข้า Discord แล้ว!")
                elif not ADMIN_DISCORD_WEBHOOK:
                    st.warning("ยังไม่ได้ตั้งค่า ADMIN_DISCORD_WEBHOOK ใน st.secrets")
                else:
                    st.error("ส่งรายงานไม่สำเร็จ ลองใหม่อีกครั้ง")

        # กราฟสรุปยอด (เฉพาะที่อนุมัติแล้ว)
        if not df_completed.empty:
            st.write("#### 📈 กราฟแนวโน้มรายรับ - รายจ่าย (เฉพาะรายการที่อนุมัติแล้ว)")
            chart_df = df_completed.copy()
            chart_df["date_str"] = chart_df["created_at"].dt.strftime("%Y-%m-%d")
            pivot_chart = chart_df.pivot_table(index="date_str", columns="type", values="amount", aggfunc="sum", fill_value=0)
            if "income" not in pivot_chart.columns:
                pivot_chart["income"] = 0
            if "expense" not in pivot_chart.columns:
                pivot_chart["expense"] = 0
            pivot_chart = pivot_chart.rename(columns={"income": "รายรับ (Income)", "expense": "รายจ่าย (Expense)"})
            pivot_chart = pivot_chart.sort_index()
            st.bar_chart(pivot_chart, color=["#22c55e", "#ef4444"], use_container_width=True)

        # ตารางแสดงข้อมูล
        df_display = df_filtered.copy()
        df_display["ประเภท"] = df_display["type"].map({"income": "🟢 รายรับ", "expense": "🔴 รายจ่าย"})
        df_display["สถานะ"] = df_display["status"].map({
            "completed": "🟢 สำเร็จ", "pending": "🟡 รอยืนยัน", "rejected": "⚪ ยกเลิก/ปฏิเสธ",
        }).fillna("🟢 สำเร็จ")
        df_display["ยอดเงิน (บาท)"] = df_display["amount"].map(lambda x: f"{safe_float(x):,.2f}")
        df_display["วันที่"] = df_display["created_at"].dt.strftime("%Y-%m-%d %H:%M")

        display_cols = ["id", "วันที่", "ประเภท", "สถานะ", "หมวดหมู่", "ยอดเงิน (บาท)", "note", "slip_url"]
        valid_disp_cols = [c for c in display_cols if c in df_display.columns]

        st.dataframe(
            df_display[valid_disp_cols],
            column_config={
                "id": st.column_config.NumberColumn("ID", format="%d"),
                "note": st.column_config.TextColumn("ลูกค้า / หมายเหตุ (Note)"),
                "slip_url": st.column_config.LinkColumn("รูปสลิป", display_text="📂 เปิดดูรูปสลิป"),
            },
            use_container_width=True,
            hide_index=True,
        )

        csv_data = df_filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 ดาวน์โหลดประวัติบัญชี (Export to CSV)",
            data=csv_data,
            file_name=f"accounting_report_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        st.divider()

        # ==========================================
        # 4. เครื่องมือจัดการรายการ (แก้ไข & ลบ)
        # ==========================================
        tab_edit, tab_delete = st.tabs(["✏️ แก้ไขรายการ (Edit)", "🗑️ ลบรายการ (Delete)"])

        with tab_edit:
            options_list = [
                f"ID: {item['id']} | [{item.get('status','completed').upper()}] [{item.get('type','').upper()}] {item.get('category','')} - ฿{safe_float(item.get('amount')):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
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
                            edit_amount = st.number_input("จำนวนเงิน (บาท):", min_value=0.0, value=safe_float(edit_row.get("amount"), 0.0), step=50.0, format="%.2f")
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
                            old_drive_id_to_delete = None

                            if new_slip_file is not None:
                                # 🟢 อัปโหลดรูปใหม่ให้สำเร็จก่อน แล้วค่อยลบรูปเก่า (แก้ race condition เดิม)
                                with st.spinner("⏳ กำลังอัปโหลดรูปใหม่ไปยัง Supabase..."):
                                    try:
                                        timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        clean_filename = f"slip_{timestamp_prefix}_{new_slip_file.name}"
                                        up_res = upload_slip_to_supabase(new_slip_file.getvalue(), clean_filename, mimetype=new_slip_file.type)
                                        old_drive_id_to_delete = final_drive_id or None
                                        final_drive_id = up_res.get("id", "")
                                        final_slip_url = up_res.get("webViewLink", "")
                                    except Exception as ex:
                                        st.warning(f"⚠️ อัปโหลดรูปใหม่ไม่สำเร็จ รูปเดิมจะยังคงถูกใช้งานอยู่: {ex}")

                            st_val = "completed" if "Completed" in edit_status else ("pending" if "Pending" in edit_status else "rejected")
                            update_payload = {
                                "type": "income" if "รายรับ" in edit_type else "expense",
                                "amount": edit_amount, "category": edit_cat, "status": st_val,
                                "note": edit_note.strip(), "slip_url": final_slip_url, "drive_file_id": final_drive_id,
                                "created_at": datetime.combine(edit_date, datetime.now().time()).isoformat(),
                            }

                            try:
                                supabase.table("accounting_records").update(update_payload).eq("id", edit_id).execute()
                                if old_drive_id_to_delete:
                                    delete_slip_from_supabase(old_drive_id_to_delete)
                                log_admin_action("edit_accounting_record", str(edit_id))
                                st.success(f"🎉 อัปเดตรายการ ID: {edit_id} เรียบร้อยแล้ว!")
                                st.rerun()
                            except Exception as err:
                                st.error(f"อัปเดตข้อมูลไม่สำเร็จ: {err}")

        with tab_delete:
            del_options = [
                f"ID: {item['id']} | [{item.get('status','completed').upper()}] [{item.get('type','').upper()}] {item.get('category','')} - ฿{safe_float(item.get('amount')):,.2f} ({item.get('note','') or 'ไม่มีหมายเหตุ'})"
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
                    log_admin_action("delete_accounting_record", str(selected_tx_id))
                    st.success(f"ลบรายการ ID: {selected_tx_id} เรียบร้อยแล้ว!")
                    st.rerun()
    else:
        st.info("ยังไม่มีรายการบัญชีในระบบ")
