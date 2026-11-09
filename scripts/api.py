from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List
import pandas as pd
import io
import os
import sys
import shutil

# เพิ่ม Path ของ scripts เพื่อให้สามารถ import data_functions ได้
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

try:
    import data_functions
    # สร้าง Engine สำหรับ FastAPI Query (ถ้าจำเป็นต้องใช้ตรงๆ)
    engine = data_functions.engine
except ImportError:
    raise ImportError("Failed to import data_functions. Check PYTHONPATH.")

app = FastAPI(
    title="Generic Data Quality API",
    description="API สำหรับตรวจสอบคุณภาพข้อมูลแบบยืดหยุ่น (รองรับ CSV/Excel และเลือกคอลัมน์ได้)"
)

# ==============================================================================
# 1. UPLOAD & PREVIEW ENDPOINT
# ==============================================================================
@app.post("/upload", tags=["Ingestion"])
async def upload_file(file: UploadFile = File(...)):
    """
    อัปโหลดไฟล์ (CSV/Excel) เข้าสู่ระบบ
    - บันทึกไฟล์ลง Disk
    - นำเข้าข้อมูลเข้า Database (Raw Data)
    - ส่งคืน 'รายชื่อคอลัมน์' เพื่อให้ Frontend นำไปแสดงให้ User เลือก
    """
    try:
        # ตรวจสอบนามสกุลไฟล์
        filename = file.filename
        if not filename.endswith(('.csv', '.xlsx', '.xls')):
             raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ .csv, .xlsx, .xls เท่านั้น")

        # สร้าง path สำหรับบันทึกไฟล์ (ใช้ชื่อเดิมของไฟล์ หรือตั้งชื่อกลางก็ได้)
        # ในที่นี้เราจะบันทึกโดยใช้ชื่อไฟล์จริง เพื่อให้รู้ว่าไฟล์ไหนเป็นไฟล์ล่าสุด
        save_path = os.path.join(data_functions.DATA_DIR, filename)
        
        # บันทึกไฟล์ลงเครื่อง
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print(f"📥 Received file: {filename}")
        
        # เรียกใช้ฟังก์ชัน Ingest ใน data_functions
        # ฟังก์ชันนี้จะโหลดข้อมูลเข้าตาราง 'raw_data' และคืนค่า DataFrame กลับมา
        df = data_functions.ingest_generic_data(save_path)
        
        # ดึงรายชื่อคอลัมน์ (ไม่รวม row_id ที่ระบบสร้างเอง)
        columns = [c for c in df.columns if c != 'row_id']
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "อัปโหลดและอ่านข้อมูลสำเร็จ",
            "filename": filename,
            "total_rows": len(df),
            "columns": columns # ส่ง list คอลัมน์กลับไป
        })
        
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการอัปโหลด: {str(e)}")

# ==============================================================================
# 2. PROCESS ENDPOINT (Run Custom DQ)
# ==============================================================================
@app.post("/process", tags=["Processing"])
async def process_data(columns: List[str] = Form(...)):
    """
    รับรายชื่อคอลัมน์ที่ User เลือก (List of Strings)
    แล้วสั่งให้ data_functions ทำการตรวจสอบข้อมูลซ้ำ (DQ Check)
    """
    try:
        if not columns:
            raise HTTPException(status_code=400, detail="ต้องเลือกอย่างน้อย 1 คอลัมน์")

        print(f"🔄 Processing with columns: {columns}")
        
        # เรียก Logic DQ
        result = data_functions.run_custom_dq(columns)
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "ประมวลผลเสร็จสิ้น",
            "result": result
        })
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"❌ Process Error: {e}")
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการประมวลผล: {str(e)}")

# ==============================================================================
# 3. DOWNLOAD ENDPOINT
# ==============================================================================
@app.get("/download", tags=["Download"])
def download_clean_data():
    """
    ดาวน์โหลดข้อมูลสะอาด (Clean Data) จากผลลัพธ์ล่าสุด
    """
    try:
        # อ่านข้อมูลจากตารางผลลัพธ์ (clean_data_result)
        # ใช้ pandas read_sql เพื่อความง่าย
        df = pd.read_sql("SELECT * FROM clean_data_result", engine)
        
        if df.empty:
            raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผลลัพธ์ (กรุณาประมวลผลก่อน)")
            
        # ลบ row_id ออกก่อนส่งให้ User
        if 'row_id' in df.columns:
            df = df.drop(columns=['row_id'])
            
        # แปลงเป็น CSV
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        
        return StreamingResponse(
            iter([stream.getvalue()]), 
            media_type="text/csv", 
            headers={"Content-Disposition": "attachment; filename=clean_data.csv"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการเตรียมไฟล์: {str(e)}")

# ==============================================================================
# 4. REPORT ENDPOINT
# ==============================================================================
@app.get("/report", tags=["Report"])
def get_report():
    """ดึงข้อมูลรายงานสรุปล่าสุด"""
    try:
        report = data_functions.get_latest_report()
        if not report:
             return JSONResponse(status_code=200, content={}) # ส่ง object ว่างถ้าไม่มีข้อมูล
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# 5. HEALTH CHECK
# ==============================================================================
@app.get("/health", tags=["System"])
def health_check():
    try:
        with engine.connect():
            db_status = "OK"
    except Exception:
        db_status = "Failed"
    return {"api": "Running", "db": db_status}