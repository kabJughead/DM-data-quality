import pandas as pd
from sqlalchemy import create_engine, text
import os
import datetime
import time
import shutil
from dotenv import load_dotenv
from typing import List, Dict, Union

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

# โหลดค่าจากไฟล์ .env (ถ้ามี) — ห้าม commit ไฟล์ .env
load_dotenv()

# Database Connection Settings
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("ไม่พบ DB_PASSWORD — กรุณาสร้างไฟล์ .env (ดู .env.example)")
DB_NAME = os.getenv("DB_NAME", "mydb")
DB_PORT = os.getenv("DB_PORT", "5432")

# ตรวจสอบ Environment (Docker vs Local)
if os.getenv("AIRFLOW_HOME"):
    DB_HOST = "postgres"
    # ใน Docker จะใช้ path นี้
    DATA_DIR = "/opt/airflow/data"
else:
    DB_HOST = "127.0.0.1"
    # ใน Local Windows
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))

# สร้างโฟลเดอร์ data หากยังไม่มี
os.makedirs(DATA_DIR, exist_ok=True)

# ==============================================================================
# 2. ENGINE SETUP
# ==============================================================================

engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    echo=False, 
    future=True
)

# ==============================================================================
# 3. HELPER FUNCTIONS (File Handling)
# ==============================================================================

def read_file_to_df(filepath: str) -> pd.DataFrame:
    """อ่านไฟล์ CSV หรือ Excel เป็น DataFrame รองรับภาษาไทย"""
    print(f" Reading file: {filepath}")
    
    if filepath.endswith('.csv'):
        # utf-8-sig รองรับภาษาไทยได้ดีที่สุดสำหรับ CSV
        return pd.read_csv(filepath, encoding='utf-8-sig')
    elif filepath.endswith(('.xlsx', '.xls')):
        # ต้องติดตั้ง openpyxl: pip install openpyxl
        return pd.read_excel(filepath)
    else:
        raise ValueError("รองรับเฉพาะไฟล์นามสกุล .csv, .xlsx, .xls เท่านั้น")

# ==============================================================================
# 4. DATABASE & ETL FUNCTIONS
# ==============================================================================

def create_metadata_tables():
    """สร้างตารางสำหรับเก็บ Report (dq_summary_generic)"""
    print("\n--- 1. Checking Metadata Tables ---")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_summary_generic (
                process_id TEXT PRIMARY KEY,
                run_timestamp TIMESTAMP,
                filename TEXT,
                selected_columns TEXT,
                total_rows INTEGER,
                duplicate_rows INTEGER,
                clean_rows INTEGER,
                execution_time_seconds FLOAT
            );
        """))
    print("✅ Metadata table 'dq_summary_generic' is ready.")

def ingest_generic_data(filepath: str) -> pd.DataFrame:
    """
    นำเข้าไฟล์ใดๆ เข้าตาราง 'raw_data' ใน Database
    - สร้าง row_id อัตโนมัติ
    - ปรับชื่อคอลัมน์ให้เป็นมิตรกับ Database
    """
    print(f"\n--- 2. Ingesting Generic Data ---")
    df = read_file_to_df(filepath)
    
    # Clean Column Names: ลบช่องว่าง, เปลี่ยนเป็นตัวเล็ก, แทนที่ space ด้วย _
    # เพื่อป้องกัน Error เวลา SQL Query
    df.columns = df.columns.astype(str).str.strip()
    
    # เพิ่ม row_id เพื่อใช้เป็น Unique Key ในการอ้างอิง
    if 'row_id' not in df.columns:
        df.insert(0, 'row_id', range(1, 1 + len(df)))
        
    # บันทึกลง DB (Table: raw_data) - ทับข้อมูลเก่าเสมอ
    with engine.begin() as conn:
        df.to_sql("raw_data", conn, if_exists="replace", index=False)
    
    print(f"✅ Loaded {len(df)} rows from '{os.path.basename(filepath)}' to table 'raw_data'")
    return df

def load_raw_data() -> pd.DataFrame:
    """ดึงข้อมูลดิบจากตาราง raw_data"""
    try:
        return pd.read_sql("SELECT * FROM raw_data", engine)
    except Exception as e:
        print(f"⚠️ Error loading raw_data: {e}")
        return pd.DataFrame()

# ==============================================================================
# 5. GENERIC DQ LOGIC (User-Selected Columns)
# ==============================================================================

def run_custom_dq(selected_columns: List[str]) -> Dict:
    """
    ตรวจสอบข้อมูลซ้ำ (Duplicate) โดยใช้คอลัมน์ที่ผู้ใช้เลือกเจาะจง
    """
    start_time = time.time()
    print(f"\n--- 3. Running DQ Check on columns: {selected_columns} ---")
    
    # 1. โหลดข้อมูลดิบ
    df = load_raw_data()
    if df.empty:
        raise ValueError("ตาราง raw_data ว่างเปล่า กรุณาอัปโหลดไฟล์ก่อน")
    
    # 2. ตรวจสอบว่าคอลัมน์ที่เลือกมีอยู่จริงไหม
    # กรองเอาเฉพาะคอลัมน์ที่มีจริงในตาราง (ป้องกัน Error)
    valid_cols = [c for c in selected_columns if c in df.columns]
    
    if not valid_cols:
        raise ValueError("ไม่พบคอลัมน์ที่เลือกในข้อมูล (หรือคุณยังไม่ได้เลือกคอลัมน์)")

    # 3. ตรวจสอบข้อมูลซ้ำ (Logic: ซ้ำกันในทุกคอลัมน์ที่เลือก = Duplicate)
    # keep='first' -> เก็บตัวแรกไว้เป็น Clean, ตัวหลังๆ ถือเป็น Duplicate
    df['is_duplicate'] = df.duplicated(subset=valid_cols, keep='first')
    
    # แยกข้อมูล
    df_clean = df[df['is_duplicate'] == False].drop(columns=['is_duplicate'])
    df_duplicates = df[df['is_duplicate'] == True].drop(columns=['is_duplicate'])
    
    # 4. บันทึกผลลัพธ์ลง Database
    process_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    
    # 4.1 บันทึกตาราง Clean Data (Table: clean_data_result)
    clean_table_name = "clean_data_result"
    with engine.begin() as conn:
        df_clean.to_sql(clean_table_name, conn, if_exists="replace", index=False)
        
    elapsed_time = time.time() - start_time
        
    # 4.2 บันทึก Report ลง dq_summary_generic
    # ต้องดึงชื่อไฟล์ต้นฉบับมาบันทึกด้วย (ถ้าทำได้) แต่ในที่นี้เราบันทึกผลลัพธ์เป็นหลัก
    with engine.begin() as conn:
        summary_data = {
            'process_id': process_id,
            'run_timestamp': datetime.datetime.now(),
            'filename': "uploaded_file", # อาจจะส่งชื่อไฟล์เข้ามาเป็น parameter ได้ในอนาคต
            'selected_columns': ",".join(valid_cols),
            'total_rows': len(df),
            'duplicate_rows': len(df_duplicates),
            'clean_rows': len(df_clean),
            'execution_time_seconds': elapsed_time
        }
        pd.DataFrame([summary_data]).to_sql("dq_summary_generic", conn, if_exists="append", index=False)

    print(f"✅ DQ Finished. Duplicates found: {len(df_duplicates)}")
    print(f"✅ Saved clean data to table: '{clean_table_name}'")
    
    return {
        "total": len(df),
        "duplicates": len(df_duplicates),
        "clean": len(df_clean),
        "clean_table": clean_table_name,
        "selected_columns": valid_cols,
        "process_time": elapsed_time
    }

def get_latest_report() -> Dict:
    """ดึงรายงานล่าสุดจาก dq_summary_generic"""
    try:
        query = text("SELECT * FROM dq_summary_generic ORDER BY run_timestamp DESC LIMIT 1")
        df = pd.read_sql(query, engine)
        if not df.empty:
            return df.to_dict(orient='records')[0]
        return {}
    except Exception:
        return {}

# ==============================================================================
# 6. MAIN EXECUTION (Local Test)
# ==============================================================================

if __name__ == "__main__":
    print("\n--- Starting Generic DQ Pipeline Test ---")
    
    # 1. Setup
    create_metadata_tables()
    
    # 2. Test Ingestion (ต้องมีไฟล์ทดสอบในโฟลเดอร์ data ก่อน)
    # หาไฟล์ csv หรือ xlsx แรกในโฟลเดอร์ data มาทดสอบ
    test_files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.csv', '.xlsx'))]
    
    if test_files:
        test_file_path = os.path.join(DATA_DIR, test_files[0])
        print(f"🔎 Found test file: {test_files[0]}")
        
        # Ingest
        df_raw = ingest_generic_data(test_file_path)
        
        # 3. Test DQ (สมมติเลือก 2 คอลัมน์แรกมาเช็ค)
        if df_raw is not None and not df_raw.empty:
            cols_to_check = [c for c in df_raw.columns if c != 'row_id'][:2] # เลือก 2 คอลัมน์แรกที่ไม่ใช่ row_id
            print(f" Testing DQ with columns: {cols_to_check}")
            
            result = run_custom_dq(cols_to_check)
            print("\n Result:", result)
    else:
        print("⚠️ No CSV/Excel files found in 'data' folder for testing.")