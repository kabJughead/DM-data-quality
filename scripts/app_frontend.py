import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
import os
from dotenv import load_dotenv
from datetime import datetime

# ==========================================
# 1. ตั้งค่าหน้าเว็บ
# ==========================================
st.set_page_config(
    page_title="Generic Data Quality Platform",
    page_icon="🧹",
    layout="wide"
)

# URL ของ FastAPI Backend
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# ==========================================
# SIDEBAR: Menu Selection
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2920/2920326.png", width=100)
    st.title("เมนูหลัก")
    page = st.radio("ไปที่หน้า:", ["🏠 User Dashboard", "🛠️ Admin Console"])
    st.info("ระบบตรวจสอบคุณภาพข้อมูล v1.0")

# ==========================================
# PAGE 1: USER DASHBOARD (หน้าเดิม)
# ==========================================
if page == "🏠 User Dashboard":
    # ==========================================
    # 2. ส่วนหัว (Header)
    # ==========================================
    st.title("🧹 Generic Data Quality Platform")
    st.markdown("""
    ### ระบบตรวจสอบคุณภาพข้อมูลแบบอเนกประสงค์
    รองรับไฟล์ **CSV** และ **Excel** โดยสามารถ **เลือกคอลัมน์ (Columns)** ที่ต้องการใช้ตรวจสอบความซ้ำซ้อนได้เอง
    """)
    st.divider()

    # ==========================================
    # STEP 1: Upload File
    # ==========================================
    st.header("1. อัปโหลดไฟล์ข้อมูล (Upload)")
    st.caption("รองรับไฟล์ .csv และ .xlsx")

    uploaded_file = st.file_uploader("ลากไฟล์มาวางที่นี่ หรือคลิกเพื่อเลือกไฟล์", type=['csv', 'xlsx', 'xls'])

    # ใช้ Session State เก็บค่าระหว่าง Reload
    if 'columns' not in st.session_state:
        st.session_state.columns = []
    if 'upload_success' not in st.session_state:
        st.session_state.upload_success = False

    if uploaded_file:
        if st.button("📤 อัปโหลดและวิเคราะห์ไฟล์", type="primary"):
            with st.spinner("กำลังอ่านไฟล์และวิเคราะห์โครงสร้าง..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                    res = requests.post(f"{API_URL}/upload", files=files)
                    
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.columns = data['columns']
                        st.session_state.upload_success = True
                        if 'result' in st.session_state:
                            del st.session_state.result
                            
                        st.success(f"✅ อัปโหลดสำเร็จ! ไฟล์: **{data['filename']}** | พบข้อมูลทั้งหมด: **{data['total_rows']:,}** แถว")
                    else:
                        st.error(f"เกิดข้อผิดพลาดจาก Server: {res.text}")
                        
                except Exception as e:
                    st.error(f"เชื่อมต่อ API ไม่ได้: {e}")
                    st.warning("คำแนะนำ: ตรวจสอบว่ารัน 'uvicorn api:app' อยู่หรือไม่")

    # ==========================================
    # STEP 2: Select Columns & Process
    # ==========================================
    if st.session_state.upload_success and st.session_state.columns:
        st.divider()
        st.header("2. กำหนดเกณฑ์การตรวจสอบ (Select Keys)")
        st.info("💡 กรุณาเลือกคอลัมน์ที่ต้องการใช้เป็นเกณฑ์ (Key) ในการระบุตัวตน")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            selected_cols = st.multiselect(
                "เลือกคอลัมน์ที่ต้องเหมือนกันเป๊ะๆ (Exact Match):", 
                options=st.session_state.columns,
                default=st.session_state.columns
            )
        
        with col2:
            st.write(" ")
            st.write(" ")
            if st.button("🚀 เริ่มตรวจสอบข้อมูลซ้ำ (Run DQ)", disabled=len(selected_cols)==0, type="primary"):
                with st.spinner("กำลังตรวจสอบข้อมูลซ้ำ..."):
                    try:
                        data = {'columns': selected_cols} 
                        res = requests.post(f"{API_URL}/process", data=data)
                        
                        if res.status_code == 200:
                            st.session_state.result = res.json()['result']
                            st.session_state.selected_cols_log = selected_cols
                            st.success("ประมวลผลเสร็จสิ้น!")
                        else:
                            st.error(f"Process Error: {res.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ==========================================
    # STEP 3: Result & Download
    # ==========================================
    if 'result' in st.session_state:
        res = st.session_state.result
        st.divider()
        st.header("3. ผลลัพธ์การตรวจสอบ (Result)")
        
        st.caption(f"ตรวจสอบโดยใช้คอลัมน์: {', '.join(st.session_state.selected_cols_log)}")
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("ข้อมูลทั้งหมด", f"{res['total']:,} แถว")
        with m2:
            st.metric("ข้อมูลซ้ำ (Duplicates)", f"{res['duplicates']:,} แถว", delta_color="inverse")
        with m3:
            st.metric("ข้อมูลสะอาด (Clean)", f"{res['clean']:,} แถว")
        
        c_chart, c_dl = st.columns([2, 1])
        
        with c_chart:
            chart_data = pd.DataFrame({
                'Status': ['Clean Data', 'Duplicates'],
                'Count': [res['clean'], res['duplicates']]
            })
            fig = px.pie(chart_data, values='Count', names='Status', 
                        title=f'สัดส่วนคุณภาพข้อมูล (ตรวจสอบจาก {len(res["selected_columns"])} คอลัมน์)', 
                        color='Status',
                        color_discrete_map={'Clean Data':'#2ecc71', 'Duplicates':'#e74c3c'},
                        hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
        with c_dl:
            st.subheader("📥 ดาวน์โหลดผลลัพธ์")
            st.write("ดาวน์โหลดไฟล์ข้อมูลสะอาด (Clean Data) ในรูปแบบ CSV")
            
            try:
                dl_res = requests.get(f"{API_URL}/download")
                if dl_res.status_code == 200:
                    st.download_button(
                        label="⬇️ ดาวน์โหลด Clean Data (CSV)",
                        data=dl_res.content,
                        file_name="clean_data.csv",
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    st.warning("ไฟล์ยังไม่พร้อม (ลองกด Process ใหม่อีกครั้ง)")
            except:
                st.error("ไม่สามารถเชื่อมต่อ Server เพื่อดาวน์โหลดได้")

    st.divider()

    # ==========================================
    # 4. ส่วน Feedback (User View)
    # ==========================================
    st.header("💬 ข้อเสนอแนะ (Feedback)")
    st.caption("ความคิดเห็นของคุณช่วยให้เราพัฒนาระบบให้ดียิ่งขึ้น")

    with st.form("feedback_form"):
        col_name, col_type = st.columns(2)
        with col_name:
            user_name = st.text_input("ชื่อของคุณ (ระบุหรือไม่ก็ได้)", placeholder="เช่น สมชาย ใจดี")
        with col_type:
            fb_type = st.selectbox("ประเภทข้อเสนอแนะ", ["แจ้งปัญหาการใช้งาน (Bug)", "เสนอแนะฟีเจอร์ใหม่", "คำชมเชย", "อื่นๆ"])
        
        comment = st.text_area("รายละเอียด", placeholder="พิมพ์ข้อเสนอแนะของคุณที่นี่...")
        
        submitted = st.form_submit_button("ส่งข้อเสนอแนะ")
        
        if submitted:
            if comment:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # เพิ่ม delimiter | เพื่อให้อ่านง่าย
                log_entry = f"{timestamp}|{fb_type}|{user_name if user_name else 'Anonymous'}|{comment}\n"
                
                try:
                    with open("user_feedback.log", "a", encoding="utf-8") as f:
                        f.write(log_entry)
                    st.success("✅ ขอบคุณสำหรับข้อเสนอแนะ! เราได้รับข้อมูลเรียบร้อยแล้ว")
                except Exception as e:
                    st.error(f"ไม่สามารถบันทึกข้อมูลได้: {e}")
            else:
                st.warning("กรุณาพิมพ์รายละเอียดก่อนส่ง")

# ==========================================
# PAGE 2: ADMIN CONSOLE (หน้าใหม่)
# ==========================================
elif page == "🛠️ Admin Console":
    st.title("🛠️ Admin Console")
    st.write("พื้นที่สำหรับผู้ดูแลระบบ เพื่อตรวจสอบสถานะและข้อเสนอแนะ")
    
    # Simple Login (Hardcoded for demo)
    password = st.text_input("กรุณาใส่รหัสผ่าน Admin", type="password")
    
    if ADMIN_PASSWORD and password == ADMIN_PASSWORD:
        st.success("เข้าสู่ระบบสำเร็จ!")
        
        # เพิ่ม Tab สำหรับ Airflow
        tab1, tab2, tab3 = st.tabs(["💬 รายการ Feedback", "⚙️ System Health", "🌪️ Airflow Monitor"])
        
        with tab1:
            st.subheader("รายการข้อเสนอแนะจากผู้ใช้")
            if os.path.exists("user_feedback.log"):
                with open("user_feedback.log", "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                if lines:
                    feedback_data = []
                    for line in lines:
                        try:
                            parts = line.strip().split("|")
                            if len(parts) >= 4:
                                feedback_data.append({
                                    "Time": parts[0],
                                    "Type": parts[1],
                                    "User": parts[2],
                                    "Message": parts[3]
                                })
                        except:
                            continue
                    
                    if feedback_data:
                        df_fb = pd.DataFrame(feedback_data)
                        # แสดงตารางแบบใหม่
                        st.dataframe(df_fb, use_container_width=True)
                        
                        # สรุปประเภท
                        st.caption("สถิติประเภทข้อเสนอแนะ")
                        if 'Type' in df_fb.columns:
                             st.bar_chart(df_fb['Type'].value_counts())
                    else:
                        st.info("ยังไม่มีข้อมูล Feedback หรือรูปแบบข้อมูลไม่ถูกต้อง")
                else:
                    st.info("ยังไม่มีข้อมูล Feedback")
            else:
                st.warning("ไม่พบไฟล์ log (ยังไม่มีการส่ง feedback)")
        
        with tab2:
            st.subheader("ตรวจสอบสถานะระบบ")
            col_health1, col_health2 = st.columns(2)
            
            with col_health1:
                st.write("**Backend API Status**")
                try:
                    health_res = requests.get(f"{API_URL}/health", timeout=2)
                    if health_res.status_code == 200:
                        status = health_res.json()
                        st.success(f"✅ API Online ({API_URL})")
                        st.json(status)
                    else:
                        st.error("❌ API Error")
                except:
                    st.error("❌ Cannot connect to API")
            
            with col_health2:
                st.write("**File System**")
                if os.path.exists("user_feedback.log"):
                    st.success("✅ Feedback Log File exists")
                else:
                    st.warning("⚠️ Feedback Log File not found")
        
        with tab3:
            st.subheader("ระบบจัดการ Workflow (Airflow)")
            st.info("เข้าสู่ระบบ Airflow เพื่อตรวจสอบสถานะ DAGs และ Logs การทำงานเบื้องหลัง")
            
            col_link, col_info = st.columns([1, 2])
            
            with col_link:
                # ปุ่มลิงก์ไปยัง Airflow (Default Port 8080)
                st.link_button("🚀 เปิด Airflow UI", "http://127.0.0.1:8080", type="primary", use_container_width=True)
            
            with col_info:
                st.markdown("""
                **ข้อมูลการเข้าใช้งาน (Default):**
                - **URL:** http://127.0.0.1:8080
                - **Username:** `admin`
                - **Password:** ตามค่า `AIRFLOW_ADMIN_PASSWORD` ใน `.env`
                """)
                st.caption("ใช้สำหรับตรวจสอบ DAG 'generic_dq_pipeline_v2' หรือ 'data_quality_pipeline'")

    elif password:
        st.error("รหัสผ่านไม่ถูกต้อง")

st.sidebar.divider()
st.sidebar.caption("🚀 Generic Data Quality Platform | Powered by Docker, FastAPI, Streamlit")