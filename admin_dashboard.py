import base64
import random
import string
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st
from supabase import create_client

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

# 🔒 [FIX] อ่านค่า Webhook จาก st.secrets ป้องกันการรั่วไหลบน GitHub สาธารณะ[cite: 2]
ADMIN_DISCORD_WEBHOOK = st.secrets.get("ADMIN_DISCORD_WEBHOOK", "")
if not ADMIN_DISCORD_WEBHOOK:
    st.warning("⚠️ ยังไม่ได้ตั้งค่า ADMIN_DISCORD_WEBHOOK ใน st.secrets — ฟีเจอร์ส่งภาพ/แจ้งเตือนเข้า Discord จะใช้งานไม่ได้")

# 🟢 ปรับแก้ Relay Worker ป้องกัน Thread ซ้ำ และล้างค่าก่อนยิง Discord[cite: 2]
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

                    # 🚨 1. Atomic Claim ผ่านเงื่อนไข WHERE ใน Postgres ป้องกันการยิงซ้ำจากหลาย worker[cite: 2]
                    claim_res = supabase.table("user_monitors").update({
                        "pending_alert_msg": None,
                        "pending_alert_img": None
                    }).eq("id", row_id).not_.is_("pending_alert_msg", "null").execute()

                    won_claim = bool(claim_res.data)
                    if not won_claim:
                        continue  # แพ้ race ให้ worker อื่นไปแล้ว[cite: 2]

                    # 🚨 2. ถ้าระบบส่งข้อความมาเป็นคำว่า [NULL] หรือ None ให้ข้าม[cite: 2]
                    if not msg or str(msg).strip() in ["[NULL]", "None", "null", ""]:
                        continue

                    # 3. ยิงเข้า Discord หากมีข้อความจริง[cite: 2]
                    if ADMIN_DISCORD_WEBHOOK:
                        payload_data = {"content": f"🤖 **[Bot: {row_key}]**\n{msg}"}
                        files = None

                        if b64_img and len(str(b64_img)) > 20: # เช็คว่ามีรูปจริง ไม่ใช่ไฟล์เสีย[cite: 2]
                            try:
                                img_bytes = base64.b64decode(b64_img)
                                files = {'file': ('screenshot.png', img_bytes, 'image/png')}
                            except Exception:
                                pass

                        requests.post(ADMIN_DISCORD_WEBHOOK, data=payload_data, files=files)

        except Exception:
            pass

        time.sleep(3)

# 🟢 ป้องกันการสร้าง thread ซ้ำระดับโปรเซส[cite: 2]
_relay_worker_started = False
_relay_worker_lock = threading.Lock()

def start_relay_worker_once():
    global _relay_worker_started
    with _relay_worker_lock:
        if not _relay_worker_started:
            _relay_worker_started = True
            threading.Thread(target=discord_relay_worker, daemon=True).start()

start_relay_worker_once()

# 🔒 อ่าน PIN แอดมินจาก st.secrets[cite: 2]
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
menu = st.sidebar.radio("เลือกเมนูใช้งาน", ["📊 Live Monitor (มอนิเตอร์บอท)", "🔑 Key Manager (จัดการคีย์)", "💻 Active Sessions (เซสชันจอสด)"])

if st.sidebar.button("🚪 ออกจากระบบ"):
    st.session_state.authenticated = False
    st.rerun()

# ---------------------------------------------------------
# 📊 TAB 1: LIVE MONITOR (มอนิเตอร์สถานะบอทลูกค้า + สเปคคอม)
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

            # 🟢 แปลงเวลา UTC -> เวลาไทย (+7 ชม.)
            if "last_seen" in df.columns:
                df["last_seen"] = pd.to_datetime(df["last_seen"])
                df["last_seen"] = df["last_seen"].dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            total_bots = len(df)
            active_bots = len(df[df["status"] == "RUNNING"]) if "status" in df.columns else 0
            captcha_bots = len(df[df["current_step"].str.contains("CAPTCHA", na=False)]) if "current_step" in df.columns else 0
            crashed_bots = len(df[df["status"] == "CRASH"]) if "status" in df.columns else 0
            total_boxes = df["boxes_collected"].sum() if "boxes_collected" in df.columns else 0

            # การ์ดสรุปยอด
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🤖 บอททั้งหมด", f"{total_bots} เครื่อง")
            c2.metric("🟢 กำลังรันอยู่", f"{active_bots} เครื่อง")
            c3.metric("🚨 ติด CAPTCHA / Crash", f"{captcha_bots + crashed_bots} เครื่อง")
            c4.metric("📦 ยอดกล่องสะสม", f"{total_boxes:,} กล่อง")

            st.divider()

            # 🟢 แสดงตาราง (เพิ่มคอลัมน์ pc_specs เข้าไปในรายการที่จะแสดงผล)
            show_cols = ["license_key", "status", "current_step", "farm_mode", "boxes_collected", "lives_collected", "cpu_usage", "ram_usage", "pc_specs", "bot_version", "last_seen"]
            existing_cols = [c for c in show_cols if c in df.columns]
            st.dataframe(df[existing_cols], use_container_width=True, hide_index=True)

            # 🟢 โซนสั่งแคปหน้าจอสดผ่านมือถือ
            st.divider()
            st.subheader("📸 สั่งแคปหน้าจอบอทรอบสด (Remote Screenshot)")
            
            bot_keys = df["license_key"].dropna().tolist() if "license_key" in df.columns else []
            if bot_keys:
                col_ss1, col_ss2 = st.columns([3, 2])
                with col_ss1:
                    selected_bot_key = st.selectbox("เลือกบอทเครื่องที่ต้องการดูหน้าจอ:", bot_keys, key="ss_select_key")
                with col_ss2:
                    st.write("") 
                    st.write("")
                    if st.button("📷 สั่งแคปหน้าจอส่งเข้า Discord", key="btn_send_ss"):
                        try:
                            supabase.table("user_monitors").update({
                                "action_command": "screenshot"
                            }).eq("license_key", selected_bot_key).execute()
                            
                            st.success(f"สั่งแคปหน้าจอคีย์ `{selected_bot_key}` เรียบร้อยแล้ว! บอทจะส่งภาพเข้า Discord ในไม่ช้า")
                        except Exception as ex:
                            st.error(f"เกิดข้อผิดพลาดในการส่งคำสั่ง: {ex}")
            else:
                st.caption("ยังไม่มีเครื่องบอทเชื่อมต่อเข้ามาในระบบ")

        else:
            st.info("ยังไม่มีข้อมูลมอนิเตอร์ในระบบ")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")

# ---------------------------------------------------------
# 🔑 TAB 2: KEY MANAGER (จัดการคีย์)
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    st.title("🔑 License Key Manager")
    st.caption("ระบบเพิ่ม เพิ่ม/ลดเวลา ปรับยศสิทธิ์ (Normal/Premier) กำหนดจำนวนโควตาจอ และจัดการคีย์ลูกค้า")

    with st.expander("➕ เพิ่มคีย์ใหม่ (Add New License)", expanded=False):
        with st.form("add_key_form"):
            new_key = st.text_input("License Key (หากเว้นว่างไว้จะสุ่มให้อัตโนมัติ 10 หลัก):", value="")
            key_type_choice = st.selectbox("ประเภทสิทธิ์ใช้งาน (Key Type):", ["normal", "premier"], format_func=lambda x: "👑 Premier (พรีเมียม)" if x == "premier" else "👤 Normal (ปกติ)")
            
            st.markdown("##### ⏱️ กำหนดระยะเวลาใช้งานเริ่มต้น")
            col_d, col_h, col_m = st.columns(3)
            with col_d:
                add_days = st.number_input("วัน (Days):", min_value=0, max_value=3650, value=30)
            with col_h:
                add_hours = st.number_input("ชั่วโมง (Hours):", min_value=0, max_value=23, value=0)
            with col_m:
                add_minutes = st.number_input("นาที (Minutes):", min_value=0, max_value=59, value=0)

            max_sessions_input = st.number_input("จำนวนจอสูงสุดที่เปิดได้พร้อมกัน (max_sessions):", min_value=1, max_value=100, value=1)
            
            submitted = st.form_submit_button("➕ สร้างคีย์ใหม่")

            if submitted:
                if new_key.strip():
                    final_key = new_key.strip()
                else:
                    chars = string.ascii_uppercase + string.digits
                    final_key = ''.join(random.choices(chars, k=10))
                
                # 🟢 บังคับใช้เวลาไทย (UTC+7) เป็นฐานเวลาปัจจุบัน
                tz_th = timezone(timedelta(hours=7))
                now_th = datetime.now(tz_th)
                exp_datetime = now_th + timedelta(days=add_days, hours=add_hours, minutes=add_minutes)

                payload = {
                    "license_key": final_key,
                    "expire_date": exp_datetime.isoformat(),  # 🟢 บันทึกแบบ ISO มี timezone กำกับชัดเจน
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

    st.divider()

    st.subheader("📋 รายการ License Keys ในระบบ")
    
    try:
        res_keys = supabase.table("licenses").select("*").execute()
        keys_data = res_keys.data

        if keys_data:
            today = datetime.now().date()
            expiring_keys = []

            for item in keys_data:
                exp_str = item.get("expire_date", "")[:10]
                try:
                    exp_dt = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_dt - today).days
                    if 0 <= days_left <= 3 and item.get("is_active", True):
                        expiring_keys.append({
                            "License Key": item["license_key"],
                            "สิทธิ์": "👑 PREMIER" if item.get("key_type") == "premier" else "👤 NORMAL",
                            "โควตาจอ": f"{item.get('max_sessions', 1)} จอ",
                            "วันหมดอายุ": exp_str,
                            "คงเหลือ": f"🔴 เหลือ {days_left} วัน" if days_left > 0 else "🚨 หมดอายุวันนี้!"
                        })
                except Exception:
                    pass

            if expiring_keys:
                st.warning("⚠️ **ตรวจพบ License Key ที่กำลังจะหมดอายุภายใน 3 วัน!**")
                st.dataframe(pd.DataFrame(expiring_keys), use_container_width=True, hide_index=True)
                st.divider()

            df_keys = pd.DataFrame(keys_data)
            if "key_type" not in df_keys.columns:
                df_keys["key_type"] = "normal"
            if "max_sessions" not in df_keys.columns:
                df_keys["max_sessions"] = 1
            
            show_key_cols = ["id", "license_key", "key_type", "max_sessions", "expire_date", "is_active", "is_used", "hwid"]
            existing_key_cols = [c for c in show_key_cols if c in df_keys.columns]
            
            st.dataframe(df_keys[existing_key_cols], use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🛠️ เครื่องมือจัดการคีย์")

            key_list = [f"{item['license_key']} [{str(item.get('key_type', 'normal')).upper()}] - {item.get('max_sessions', 1)} จอ (ID: {item['id']})" for item in keys_data]
            selected_option = st.selectbox("เลือก License Key ที่ต้องการจัดการ:", key_list)

            if selected_option:
                selected_id = int(selected_option.split("ID: ")[1].replace(")", ""))
                selected_item = next(item for item in keys_data if item["id"] == selected_id)

                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown("##### 📅 จัดการเวลาหมดอายุ (เพิ่ม / ลด วัน, ชม., นาที)")
                    current_exp_str = selected_item.get("expire_date", "")
                    
                    tz_th = timezone(timedelta(hours=7))
                    try:
                        # แปลงเวลาเดิมให้เป็นเวลาไทย
                        clean_dt = pd.to_datetime(current_exp_str).tz_convert("Asia/Bangkok")
                        current_exp_dt = clean_dt.to_pydatetime()
                    except Exception:
                        current_exp_dt = datetime.now(tz_th)

                    st.write(f"**วันหมดอายุเดิม:** `{current_exp_dt.strftime('%Y-%m-%d %H:%M:%S')}`")

                    action_mode = st.radio(
                        "เลือกการจัดการเวลา:", 
                        ["➕ เพิ่มเวลา", "➖ ลดเวลาออก"], 
                        horizontal=True, 
                        key=f"action_mode_{selected_id}"
                    )

                    col_ad, col_ah, col_am = st.columns(3)
                    with col_ad:
                        p_days = st.number_input("จำนวน (วัน):", min_value=0, max_value=365, value=0, key=f"p_days_{selected_id}")
                    with col_ah:
                        p_hours = st.number_input("จำนวน (ชม.):", min_value=0, max_value=23, value=0, key=f"p_hours_{selected_id}")
                    with col_am:
                        p_minutes = st.number_input("จำนวน (นาที):", min_value=0, max_value=59, value=0, key=f"p_mins_{selected_id}")

                    if st.button("💾 บันทึกการปรับเวลา", key=f"btn_save_exp_{selected_id}"):
                        delta = timedelta(days=p_days, hours=p_hours, minutes=p_minutes)
                        
                        if action_mode == "➕ เพิ่มเวลา":
                            final_exp_dt = current_exp_dt + delta
                        else:
                            final_exp_dt = current_exp_dt - delta
                        
                        try:
                            supabase.table("licenses").update({
                                "expire_date": final_exp_dt.isoformat()
                            }).eq("id", selected_id).execute()
                            
                            st.success(f"อัปเดตเวลาหมดอายุสำเร็จเป็น: {final_exp_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"เกิดข้อผิดพลาด: {ex}")

                with col_b:
                    st.markdown("##### ⚙️ จัดการสิทธิ์, โควตาจอ, สถานะ & HWID")
                    target_id = selected_item["id"]
                    target_key = selected_item["license_key"]
                    current_active = selected_item.get("is_active", True)
                    current_type = str(selected_item.get("key_type", "normal")).lower()
                    current_max_sessions = int(selected_item.get("max_sessions", 1))

                    type_options = ["normal", "premier"]
                    type_index = 1 if current_type == "premier" else 0
                    new_key_type = st.selectbox(
                        "ประเภทสิทธิ์การใช้งาน (key_type):", 
                        type_options, 
                        index=type_index, 
                        format_func=lambda x: "👑 Premier (พรีเมียม)" if x == "premier" else "👤 Normal (ปกติ)",
                        key=f"type_select_{target_id}"
                    )

                    if new_key_type != current_type:
                        if st.button("👑 อัปเดตประเภทสิทธิ์", key=f"btn_type_{target_id}"):
                            try:
                                supabase.table("licenses").update({"key_type": new_key_type}).eq("id", target_id).execute()
                                st.success(f"เปลี่ยนสิทธิ์คีย์ {target_key} เป็น [{new_key_type.upper()}] สำเร็จ!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"เกิดข้อผิดพลาดในการเปลี่ยนสิทธิ์: {ex}")

                    st.markdown("---")

                    new_max_sessions = st.number_input(
                        "โควตาจำนวนจอสูงสุด (max_sessions):", 
                        min_value=1, 
                        max_value=100, 
                        value=current_max_sessions,
                        key=f"max_sess_{target_id}"
                    )

                    if new_max_sessions != current_max_sessions:
                        if st.button("📱 อัปเดตโควตาจำนวนจอ", key=f"btn_sess_{target_id}"):
                            try:
                                supabase.table("licenses").update({"max_sessions": new_max_sessions}).eq("id", target_id).execute()
                                st.success(f"อัปเดตโควตาคีย์ `{target_key}` เป็น {new_max_sessions} จอ เรียบร้อยแล้ว!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"เกิดข้อผิดพลาดในการเปลี่ยนโควตาจอ: {ex}")

                    st.markdown("---")

                    new_active = st.checkbox("สถานะเปิดใช้งาน (is_active)", value=current_active, key=f"active_{target_id}")
                    if new_active != current_active:
                        if st.button("🔄 อัปเดตสถานะการใช้งาน", key=f"btn_act_{target_id}"):
                            supabase.table("licenses").update({"is_active": new_active}).eq("id", target_id).execute()
                            st.success(f"อัปเดตสถานะคีย์ {target_key} สำเร็จ!")
                            st.rerun()

                    st.write(f"**HWID ปัจจุบัน:** `{selected_item.get('hwid')}`")
                    
                    c_hwid1, c_hwid2 = st.columns(2)
                    with c_hwid1:
                        if st.button("🔓 ปลดล็อก HWID", key=f"btn_hwid_{target_id}"):
                            supabase.table("licenses").update({"hwid": None, "is_used": False}).eq("id", target_id).execute()
                            st.success(f"ปลดล็อก HWID คีย์ `{target_key}` เรียบร้อย!")
                            st.rerun()
                    with c_hwid2:
                        if st.button("🧹 เคลียร์เซสชันค้าง", key=f"btn_clear_sess_{target_id}"):
                            try:
                                supabase.table("active_sessions").delete().eq("license_key", target_key).execute()
                                st.success(f"เคลียร์เซสชันค้างของคีย์ `{target_key}` เรียบร้อย!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"เคลียร์เซสชันไม่สำเร็จ: {ex}")

                    st.markdown("---")
                    if st.button("❌ ลบ License Key นี้ออกจากระบบ", type="primary", key=f"btn_del_{target_id}"):
                        supabase.table("licenses").delete().eq("id", target_id).execute()
                        supabase.table("active_sessions").delete().eq("license_key", target_key).execute()
                        st.warning(f"ลบ License Key `{target_key}` และเซสชันทั้งหมดเรียบร้อยแล้ว!")
                        st.rerun()

        else:
            st.info("ยังไม่มีข้อมูลคีย์ในฐานข้อมูล")

        with st.expander("🚀 ปล่อยอัปเดตเวอร์ชันบอทใหม่ (Release Update)", expanded=False):
            with st.form("release_update_form"):
                ver_code = st.text_input("เลขเวอร์ชันใหม่ (เช่น 1.7.0):", value="1.7.0")
                dl_url = st.text_input("Direct Link ดาวน์โหลดไฟล์ .exe เวอร์ชันใหม่:", value="")
                change_log = st.text_area("รายละเอียดการอัปเดต (Changelog):", value="• ปรับปรุงประสิทธิภาพและแก้บั๊ก")
                submit_rel = st.form_submit_button("🚀 ส่งอัปเดตไปยังเครื่องลูกค้าทั้งหมด")

                if submit_rel:
                    if not dl_url.strip():
                        st.error("กรุณากรอก Direct Link สำหรับดาวน์โหลดไฟล์ .exe")
                    else:
                        payload = {
                            "version_code": ver_code.strip(),
                            "download_url": dl_url.strip(),
                            "changelog": change_log.strip()
                        }
                        try:
                            supabase.table("app_versions").insert(payload).execute()
                            st.success(f"🎉 ปล่อยอัปเดตเวอร์ชัน {ver_code} เรียบร้อยแล้ว!")
                        except Exception as ex:
                            st.error(f"เกิดข้อผิดพลาดในการปล่อยอัปเดต: {ex}")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลคีย์: {e}")

# ---------------------------------------------------------
# 💻 TAB 3: ACTIVE SESSIONS (เซสชันจอสด)
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
                df_sess["last_heartbeat"] = pd.to_datetime(df_sess["last_heartbeat"])
                df_sess["last_heartbeat"] = df_sess["last_heartbeat"].dt.tz_convert("Asia/Bangkok").dt.strftime("%Y-%m-%d %H:%M:%S")

            st.write(f"📊 **จำนวนจอที่เปิดใช้งานอยู่ขณะนี้:** `{len(df_sess)} จอ`")
            
            show_sess_cols = ["id", "license_key", "session_id", "hwid", "last_heartbeat"]
            existing_sess_cols = [c for c in show_sess_cols if c in df_sess.columns]
            st.dataframe(df_sess[existing_sess_cols], use_container_width=True, hide_index=True)

            st.divider()
            col_act1, col_act2 = st.columns(2)

            with col_act1:
                st.markdown("##### 🎯 สั่งเตะเซสชันเฉพาะจอ")
                sess_options = [f"ID: {r['id']} | Key: {r['license_key']} | HWID: {r['hwid']}" for r in sess_data]
                sel_sess = st.selectbox("เลือกเซสชันที่ต้องการสั่งเตะออก:", sess_options)
                
                if st.button("❌ เตะเซสชันนี้ออก"):
                    target_sess_id = int(sel_sess.split("ID: ")[1].split(" |")[0])
                    supabase.table("active_sessions").delete().eq("id", target_sess_id).execute()
                    st.success("สั่งเตะเซสชันดังกล่าวเรียบร้อยแล้ว!")
                    st.rerun()

            with col_act2:
                st.markdown("##### 🧹 ล้างเซสชันทั้งหมด")
                st.caption("สั่งลบเซสชันจอทั้งหมดในระบบ (ใช้เมื่อต้องการรีเซ็ตใหม่ทั้งหมด)")
                if st.button("🔥 ล้างเซสชันค้างทั้งหมดในระบบ", type="primary"):
                    supabase.table("active_sessions").delete().neq("id", 0).execute()
                    st.warning("ล้างเซสชันทั้งหมดเรียบร้อยแล้ว!")
                    st.rerun()

        else:
            st.info("ขณะนี้ไม่มีเซสชันจอเปิดรันอยู่ในระบบ")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล active_sessions: {e}")
