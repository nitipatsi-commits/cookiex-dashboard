import streamlit as st
import pandas as pd
from supabase import create_client
import time

# 🟢 ตั้งค่าหน้าเว็บ
st.set_page_config(
    page_title="Cookie X - Admin Dashboard",
    page_icon="⚡",
    layout="wide"
)

# 🟢 เชื่อมต่อ Supabase
SUPABASE_URL = "https://dkgeqwmuvgjlaweamhsc.supabase.co"
SUPABASE_KEY = "sb_publishable_GjArIEEPL9ZcIWuOl28J6Q_4QmIeWEk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("⚡ Cookie X - Admin Control Dashboard")
st.caption("มอนิเตอร์สถานะลูกค้าแบบ Real-time")

# ปุ่มกดรีเฟรชข้อมูล
if st.button("🔄 รีเฟรชข้อมูลสด"):
    st.rerun()

# 🟢 ดึงข้อมูลจากตาราง user_monitors
try:
    res = supabase.table("user_monitors").select("*").execute()
    data = res.data

    if data:
        df = pd.DataFrame(data)

        # 📊 1. การ์ดสรุปยอดรวม (KPI Cards)
        total_bots = len(df)
        active_bots = len(df[df["status"] == "RUNNING"])
        captcha_bots = len(df[df["current_step"].str.contains("CAPTCHA", na=False)])
        crashed_bots = len(df[df["status"] == "CRASH"])
        total_boxes = df["boxes_collected"].sum() if "boxes_collected" in df.columns else 0

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("🤖 บอททั้งหมด", f"{total_bots} เครื่อง")
        col2.metric("🟢 กำลังรันอยู่", f"{active_bots} เครื่อง")
        col3.metric("🚨 ติด CAPTCHA", f"{captcha_bots} เครื่อง", delta_color="inverse")
        col4.metric("💥 บอท Crash", f"{crashed_bots} เครื่อง", delta_color="inverse")
        col5.metric("📦 ยอดกล่องสะสมรวม", f"{total_boxes:,} กล่อง")

        st.divider()

        # 🚨 2. แจ้งเตือนฉุกเฉิน (แสดงเฉพาะเครื่องที่มีปัญหา)
        problem_bots = df[(df["current_step"].str.contains("CAPTCHA", na=False)) | (df["status"] == "CRASH")]
        if not problem_bots.empty:
            st.error("⚠️ ตรวจพบเครื่องลูกค้าที่ต้องการการช่วยเหลือด่วน!")
            st.dataframe(problem_bots[["license_key", "hwid", "status", "current_step", "last_seen"]], use_container_width=True)

        # 📋 3. ตารางแสดงสถานะเครื่องลูกค้าทุกคน
        st.subheader("📋 รายชื่อและสถานะบอทของลูกค้าทั้งหมด")
        
        # เลือกแสดงเฉพาะคอลัมน์สำคัญ
        show_cols = ["license_key", "status", "current_step", "farm_mode", "boxes_collected", "lives_collected", "cpu_usage", "ram_usage", "bot_version", "last_seen"]
        existing_cols = [c for c in show_cols if c in df.columns]
        
        st.dataframe(
            df[existing_cols],
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info("ยังไม่มีข้อมูลบอทออนไลน์ในระบบ")

except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")

# อัปเดตหน้าจออัตโนมัติทุกๆ 10 วินาที
time.sleep(10)
st.rerun()