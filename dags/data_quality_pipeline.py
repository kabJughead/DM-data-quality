from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

# 1. เพิ่ม Path เพื่อให้ Airflow หาไฟล์ scripts เจอ
sys.path.append('/opt/airflow/scripts')

# 2. Import ฟังก์ชันใหม่จาก data_functions (ฉบับ Generic)
try:
    from data_functions import (
        create_metadata_tables,
        ingest_generic_data,
        run_custom_dq,
        get_latest_report,
        load_raw_data
    )
except ImportError as e:
    print(f"❌ Import Error: {e}")

# 3. ตั้งค่า Default Arguments
default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

# 4. สร้าง DAG Definition
with DAG(
    'generic_dq_pipeline_v2', # ตั้งชื่อ DAG ใหม่
    default_args=default_args,
    description='Auto Ingest Latest File -> Check 100% Duplicates',
    schedule_interval=None, # รันเมื่อกดปุ่ม (Manual) หรือตั้งเวลาตามต้องการ
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['dq', 'generic']
) as dag:

    # ------------------------------------------------------
    # Task 1: Setup & Ingestion (ค้นหาไฟล์ล่าสุดอัตโนมัติ)
    # ------------------------------------------------------
    def run_auto_ingestion(**kwargs):
        print("--- [Task 1] Starting Auto Ingestion ---")
        
        # 1. สร้างตาราง Metadata
        create_metadata_tables()
        
        # 2. ค้นหาไฟล์ใน Docker Volume
        data_dir = "/opt/airflow/data"
        files = [f for f in os.listdir(data_dir) if f.endswith(('.csv', '.xlsx', '.xls'))]
        
        if not files:
            print("⚠️ No files found in /opt/airflow/data")
            return None
            
        # หาไฟล์ล่าสุด
        latest_file = max([os.path.join(data_dir, f) for f in files], key=os.path.getmtime)
        print(f"📂 Found latest file: {latest_file}")
        
        # 3. นำเข้าข้อมูล
        df = ingest_generic_data(latest_file)
        
        # 4. ส่งรายชื่อคอลัมน์ไปให้ Task ถัดไป (ผ่าน XCom)
        # (ส่งเฉพาะชื่อคอลัมน์ ไม่ส่งข้อมูลทั้งหมด)
        columns = [c for c in df.columns if c != 'row_id']
        return columns

    t1_ingest = PythonOperator(
        task_id='auto_ingest_file',
        python_callable=run_auto_ingestion,
        provide_context=True # จำเป็นสำหรับการส่งค่า XCom
    )

    # ------------------------------------------------------
    # Task 2: DQ Check (ตรวจสอบแบบ 100% Match ทุกคอลัมน์)
    # ------------------------------------------------------
    def run_full_dq_check(**kwargs):
        print("--- [Task 2] Running Exact Match DQ Check ---")
        
        # รับรายชื่อคอลัมน์จาก Task 1
        ti = kwargs['ti']
        columns = ti.xcom_pull(task_ids='auto_ingest_file')
        
        if not columns:
            print("⚠️ No columns received. Skipping DQ check.")
            return

        print(f"🔍 Checking duplicates on ALL columns: {columns}")
        
        # เรียกใช้ Logic ตรวจสอบ (เสมือนเลือก 'Select All')
        result = run_custom_dq(columns)
        print(f"✅ Result: {result}")

    t2_dq_check = PythonOperator(
        task_id='dq_check_exact_match',
        python_callable=run_full_dq_check,
        provide_context=True
    )

    # ------------------------------------------------------
    # Task 3: Reporting
    # ------------------------------------------------------
    def run_reporting():
        print("--- [Task 3] Fetching Latest Report ---")
        report = get_latest_report()
        print("\n=== LATEST DQ REPORT ===")
        print(report)

    t3_report = PythonOperator(
        task_id='show_report',
        python_callable=run_reporting
    )

    # 5. กำหนดลำดับการทำงาน
    t1_ingest >> t2_dq_check >> t3_report