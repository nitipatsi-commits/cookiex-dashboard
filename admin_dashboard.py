import random
import string
import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta

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

# 🔒 ระบบล็อกอินความปลอดภัยสำหรับ Admin
ADMIN_PIN = "1234"  # 👈 เปลี่ยนรหัส PIN ตรงนี้ได้ตามต้องการ

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
            active_bots = len(df[df["status"] == "RUNNING"])
            captcha_bots = len(df[df["current_step"].str.contains("CAPTCHA", na=False)])
            crashed_bots = len(df[df["status"] == "CRASH"])
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
        else:
            st.info("ยังไม่มีข้อมูลมอนิเตอร์ในระบบ")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")

# ---------------------------------------------------------
# 🔑 TAB 2: KEY MANAGER (เพิ่ม / แก้ไข / ต่ออายุ / ปลด HWID)
# ---------------------------------------------------------
elif menu == "🔑 Key Manager (จัดการคีย์)":
    st.title("🔑 License Key Manager")
    st.caption("ระบบเพิ่ม เพิ่มเวลา ปรับสถานะ และจัดการคีย์ลูกค้า")

    # --- Section 1: เพิ่มคีย์ใหม่ ---
    with st.expander("➕ เพิ่มคีย์ใหม่ (Add New License)", expanded=False):
        with st.form("add_key_form"):
            new_key = st.text_input("License Key (หากเว้นว่างไว้จะสุ่มให้อัตโนมัติ 10 หลัก):", value="")
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
                    "hwid": None
                }
                try:
                    supabase.table("licenses").insert(payload).execute()
                    st.success(f"สร้างคีย์สำเร็จ! Key: `{final_key}` (หมดอายุ: {exp_date})")
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
            
            # โชว์ตารางคีย์ทั้งหมด
            st.dataframe(
                df_keys[["id", "license_key", "expire_date", "is_active", "is_used", "hwid"]],
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("🛠️ เครื่องมือจัดการคีย์")

            # เลือกคีย์ที่จะจัดการ
            key_list = [f"{item['license_key']} (ID: {item['id']})" for item in keys_data]
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

                # --- ฝั่งขวา: สถานะ / ปลด HWID / ลบคีย์ ---
                with col_b:
                    st.markdown("##### ⚙️ จัดการสถานะ & HWID")
                    target_id = selected_item["id"]
                    target_key = selected_item["license_key"]
                    current_active = selected_item.get("is_active", True)
                    
                    # สวิตช์ เปิด/ปิด คีย์
                    new_active = st.checkbox("สถานะเปิดใช้งาน (is_active)", value=current_active, key=f"active_{target_id}")
                    if new_active != current_active:
                        if st.button("🔄 อัปเดตสถานะการใช้งาน", key=f"btn_act_{target_id}"):
                            supabase.table("licenses").update({"is_active": new_active}).eq("id", target_id).execute()
                            st.success(f"อัปเดตสถานะคีย์ {target_key} สำเร็จ!")
                            st.rerun()

                    # ปุ่มปลดล็อก HWID
                    st.write(f"**HWID ปัจจุบัน:** `{selected_item.get('hwid')}`")
                    if st.button("🔓 ปลดล็อก HWID (เจาะจงคีย์นี้)", key=f"btn_hwid_{target_id}"):
                        supabase.table("licenses").update({"hwid": None, "is_used": False}).eq("id", target_id).execute()
                        st.success(f"ปลดล็อก HWID เฉพาะคีย์ `{target_key}` เรียบร้อยแล้ว!")
                        st.rerun()

                    st.markdown("---")
                    # ปุ่มลบคีย์
                    if st.button("❌ ลบ License Key นี้ออกจากระบบ", type="primary", key=f"btn_del_{target_id}"):
                        supabase.table("licenses").delete().eq("id", target_id).execute()
                        st.warning(f"ลบ License Key `{target_key}` เรียบร้อยแล้ว!")
                        st.rerun()

        else:
            st.info("ยังไม่มีข้อมูลคีย์ในฐานข้อมูล")

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูลคีย์: {e}")
