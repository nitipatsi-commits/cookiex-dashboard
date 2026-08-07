import base64
import random
import string
import threading
import time
from datetime import datetime, timedelta

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

# 🔒 Discord Webhook ฝั่ง Admin (ปลอดภัย 100% ลูกค้ามองไม่เห็น)
ADMIN_DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1534196144307966074/HUMcKoACWdddQqGoCRScYZFgS_jplvkJjOs-qp2-KGrX7vOVZGz_hTOnwzGNAUuM7gZk"

# 🟢 [Server Relay Worker] สแกนหาภาพ/ข้อความจากลูกค้าใน Supabase แล้วยิงเข้า Discord แทน
def discord_relay_worker():
    while True:
        try:
            # ดึงรายการที่มีข้อความค้าง
            res = supabase.table("user_monitors").select("*").not_.is_("pending_alert_msg", "null").execute()
            rows = res.data

            if rows:
                for row in rows:
                    msg = row.get("pending_alert_msg")
                    b64_img = row.get("pending_alert_img")
                    row_key = row.get("license_key") or row.get("hwid") or "Unknown"
                    row_id = row.get("id")

                    # 🚨 1. เคลียร์ค่าใน Supabase ออกก่อนทันที! ป้องกันลูปค้างหากยิง Discord ล้มเหลว
                    supabase.table("user_monitors").update({
                        "pending_alert_msg": None,
                        "pending_alert_img": None
                    }).eq("id", row_id).execute()

                    # 2. ถ้าระบบมี Webhook ค่อยยิงเข้า Discord
                    if msg and ADMIN_DISCORD_WEBHOOK:
                        payload_data = {"content": f"🤖 **[Bot: {row_key}]**\n{msg}"}
                        files = None

                        if b64_img:
                            try:
                                img_bytes = base64.b64decode(b64_img)
                                files = {'file': ('screenshot.png', img_bytes, 'image/png')}
                            except Exception:
                                pass

                        requests.post(ADMIN_DISCORD_WEBHOOK, data=payload_data, files=files)

        except Exception as e:
            print(f"Relay Error: {e}")

        time.sleep(3)

# เริ่มรันระบบ Relay Worker เบื้องหลัง
if "relay_started" not in st.session_state:
    st.session_state.relay_started = True
    threading.Thread(target=discord_relay_worker, daemon=True).start()

# 🔒 ระบบล็อกอินความปลอดภัยสำหรับ Admin
ADMIN_PIN = "7692"

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
menu = st.sidebar.radio("เลือกเมนูใช้งาน", ["📊 Live Monitor (มอนิเตอร์บอท)", "🔑 Key Manager (จัดการคีย์)"])

if st.sidebar.button("🚪 ออกจากระบบ"):
    st.session_state.authenticated = False
    st.rerun()

# ---------------------------------------------------------
# 📊 TAB 1: LIVE MONITOR (มอนิเตอร์สถานะบอทลูกค้า)
# ---------------------------------------------------------
if menu == "📊 Live Monitor (มอนิเตอร์บอท)":
    st.title("📊 Live Bot Monitor")
    st.caption("มอนิเตอร์สถานะลูกค้าเรียลไทม์")

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

            # แสดงตาราง
            show_cols = ["license_key", "status", "current_step", "farm_mode", "boxes_collected", "lives_collected", "cpu_usage", "ram_usage", "bot_version", "last_seen"]
            existing_cols = [c for c in show_cols if c in df.columns]
            st.dataframe(df[existing_cols], use_container_width=True, hide_index=True)

            # 🟢 โซนสั่งแคปหน้าจอสดผ่านมือถือ
            st.divider()
            st.subheader("📸 สั่งแคปหน้าจอบอทรอบสด (Remote Screenshot)")
            
            # ดึงรายชื่อ License Key ทั้งหมดในระบบ
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
                            # 🟢 ส่งคำสั่ง screenshot ลง Supabase
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
# 🔑 TAB 2: KEY MANAGER (เพิ่ม / แก้ไข / ต่ออายุ / ปรับสิทธิ์ Premier / ปลด HWID)
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    st.title("🔑 License Key Manager")
    st.caption("ระบบเพิ่ม เพิ่มเวลา ปรับยศสิทธิ์ (Normal/Premier) และจัดการคีย์ลูกค้า")

    # --- Section 1: เพิ่มคีย์ใหม่ ---
    with st.expander("➕ เพิ่มคีย์ใหม่ (Add New License)", expanded=False):
        with st.form("add_key_form"):
            new_key = st.text_input("License Key (หากเว้นว่างไว้จะสุ่มให้อัตโนมัติ 10 หลัก):", value="")
            key_type_choice = st.selectbox("ประเภทสิทธิ์ใช้งาน (Key Type):", ["normal", "premier"], format_func=lambda x: "👑 Premier (พรีเมียม)" if x == "premier" else "👤 Normal (ปกติ)")
            days_valid = st.number_input("จำนวนวันที่ใช้งานได้ (วัน):", min_value=1, max_value=3650, value=30)
            submitted = st.form_submit_button("➕ สร้างคีย์ใหม่")

            if submitted:
                if new_key.strip():
                    final_key = new_key.strip()
                else:
                    chars = string.ascii_uppercase + string.digits
                    final_key = ''.join(random.choices(chars, k=10))
                exp_date = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d")
                payload = {
                    "license_key": final_key,
                    "expire_date": exp_date,
                    "is_active": True,
                    "is_used": False,
                    "hwid": None,
                    "key_type": key_type_choice
                }
                try:
                    supabase.table("licenses").insert(payload).execute()
                    st.success(f"สร้างคีย์สำเร็จ! Key: `{final_key}` | สิทธิ์: **{key_type_choice.upper()}** (หมดอายุ: {exp_date})")
                except Exception as ex:
                    st.error(f"สร้างคีย์ไม่สำเร็จ: {ex}")

    st.divider()

    # --- Section 2: รายการคีย์ทั้งหมดและการจัดการ ---
    st.subheader("📋 รายการ License Keys ในระบบ")
    
    try:
        res_keys = supabase.table("licenses").select("*").execute()
        keys_data = res_keys.data

        if keys_data:
            today = datetime.now().date()
            expiring_keys = []

            # 🚨 ค้นหาและเตรียมข้อมูลคีย์ที่กำลังจะหมดอายุใน 3 วัน
            for item in keys_data:
                exp_str = item.get("expire_date", "")[:10]
                try:
                    exp_dt = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    days_left = (exp_dt - today).days
                    if 0 <= days_left <= 3 and item.get("is_active", True):
                        expiring_keys.append({
                            "License Key": item["license_key"],
                            "สิทธิ์": "👑 PREMIER" if item.get("key_type") == "premier" else "👤 NORMAL",
                            "วันหมดอายุ": exp_str,
                            "คงเหลือ": f"🔴 เหลือ {days_left} วัน" if days_left > 0 else "🚨 หมดอายุวันนี้!"
                        })
                except Exception:
                    pass

            # แสดงแถบเตือนสีแดงด้านบนตาราง หากมีคีย์ใกล้หมดอายุ
            if expiring_keys:
                st.warning("⚠️ **ตรวจพบ License Key ที่กำลังจะหมดอายุภายใน 3 วัน!**")
                st.dataframe(pd.DataFrame(expiring_keys), use_container_width=True, hide_index=True)
                st.divider()

            df_keys = pd.DataFrame(keys_data)
            
            if "key_type" not in df_keys.columns:
                df_keys["key_type"] = "normal"
            
            show_key_cols = ["id", "license_key", "key_type", "expire_date", "is_active", "is_used", "hwid"]
            existing_key_cols = [c for c in show_key_cols if c in df_keys.columns]
            
            st.dataframe(
                df_keys[existing_key_cols],
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("🛠️ เครื่องมือจัดการคีย์")

            # เลือกคีย์ที่จะจัดการ
            key_list = [f"{item['license_key']} [{str(item.get('key_type', 'normal')).upper()}] (ID: {item['id']})" for item in keys_data]
            selected_option = st.selectbox("เลือก License Key ที่ต้องการจัดการ:", key_list)

            if selected_option:
                selected_id = int(selected_option.split("ID: ")[1].replace(")", ""))
                selected_item = next(item for item in keys_data if item["id"] == selected_id)

                col_a, col_b = st.columns(2)

                # --- ฝั่งซ้าย: ต่ออายุ / แก้ไขวันหมดอายุ ---
                with col_a:
                    st.markdown("##### 📅 ต่ออายุ / ปรับวันหมดอายุ")
                    current_exp_str = selected_item.get("expire_date", "")[:10]
                    try:
                        current_exp_dt = datetime.strptime(current_exp_str, "%Y-%m-%d").date()
                    except Exception:
                        current_exp_dt = datetime.now().date()

                    new_exp_date = st.date_input("เลือกวันหมดอายุใหม่:", value=current_exp_dt)
                    add_days = st.number_input("หรือกดบวกเพิ่มจำนวนวัน (+วัน):", min_value=0, max_value=365, value=0)

                    if st.button("💾 บันทึกการเปลี่ยนวันหมดอายุ", key=f"btn_save_exp_{selected_id}"):
                        final_exp_dt = new_exp_date + timedelta(days=add_days)
                        try:
                            supabase.table("licenses").update({
                                "expire_date": final_exp_dt.strftime("%Y-%m-%d")
                            }).eq("id", selected_id).execute()
                            st.success(f"อัปเดตวันหมดอายุสำเร็จเป็น: {final_exp_dt}")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"เกิดข้อผิดพลาด: {ex}")

                # --- ฝั่งขวา: ปรับยศ Premier / สถานะ / ปลด HWID / ลบคีย์ ---
                with col_b:
                    st.markdown("##### ⚙️ จัดการสิทธิ์, สถานะ & HWID")
                    target_id = selected_item["id"]
                    target_key = selected_item["license_key"]
                    current_active = selected_item.get("is_active", True)
                    current_type = str(selected_item.get("key_type", "normal")).lower()

                    # 🟢 1. Dropdown เลือกปรับยศ Normal / Premier
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

                    # 2. สวิตช์ เปิด/ปิด คีย์
                    new_active = st.checkbox("สถานะเปิดใช้งาน (is_active)", value=current_active, key=f"active_{target_id}")
                    if new_active != current_active:
                        if st.button("🔄 อัปเดตสถานะการใช้งาน", key=f"btn_act_{target_id}"):
                            supabase.table("licenses").update({"is_active": new_active}).eq("id", target_id).execute()
                            st.success(f"อัปเดตสถานะคีย์ {target_key} สำเร็จ!")
                            st.rerun()

                    # 3. ปุ่มปลดล็อก HWID
                    st.write(f"**HWID ปัจจุบัน:** `{selected_item.get('hwid')}`")
                    if st.button("🔓 ปลดล็อก HWID (เจาะจงคีย์นี้)", key=f"btn_hwid_{target_id}"):
                        supabase.table("licenses").update({"hwid": None, "is_used": False}).eq("id", target_id).execute()
                        st.success(f"ปลดล็อก HWID เฉพาะคีย์ `{target_key}` เรียบร้อยแล้ว!")
                        st.rerun()

                    st.markdown("---")
                    # 4. ปุ่มลบคีย์
                    if st.button("❌ ลบ License Key นี้ออกจากระบบ", type="primary", key=f"btn_del_{target_id}"):
                        supabase.table("licenses").delete().eq("id", target_id).execute()
                        st.warning(f"ลบ License Key `{target_key}` เรียบร้อยแล้ว!")
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
                            st.success(f"🎉 ปล่อยอัปเดตเวอร์ชัน {ver_code} เรียบร้อยแล้ว! ลูกค้าที่เปิดบอทขึ้นมาจะเด้งป๊อปอัปให้อัปเดตทันที")
                        except Exception as ex:
                            st.error(f"เกิดข้อผิดพลาดในการปล่อยอัปเดต: {ex}")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลคีย์: {e}")
