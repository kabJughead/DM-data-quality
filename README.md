# DM-data-quality

ระบบตรวจสอบคุณภาพข้อมูล (Data Quality) เช่น การตรวจหาข้อมูลซ้ำ (duplicate detection)
ประกอบด้วย Airflow DAG, FastAPI backend และ Streamlit frontend

## โครงสร้าง
- `dags/` – Airflow DAG (`data_quality_pipeline.py`)
- `scripts/` – `api.py` (FastAPI), `app_frontend.py` (Streamlit), `data_functions.py`
- `data/` – ข้อมูลตัวอย่าง (`employees_10000.csv`, ข้อมูลสังเคราะห์)
- `docker-compose.yaml` – Airflow + Postgres
- `post/docker-compose.yml` – Postgres แยกสำหรับ API

## วิธีรัน
0. คัดลอก `.env.example` เป็น `.env` (และ `post/.env` ถ้าใช้ Postgres ใน `post/`) แล้วใส่รหัสผ่านของตัวเอง
1. `docker-compose up -d`
2. `pip install -r requirements.txt`
3. Backend: `cd scripts && python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000`
4. Frontend: `python -m streamlit run scripts/app_frontend.py`
5. API docs: http://localhost:8000/docs

> รหัสผ่านทั้งหมดอยู่ในไฟล์ `.env` (ไม่ถูกอัพขึ้น repo)
> (`config/airflow.cfg` ไม่ถูกอัพขึ้น repo เพราะมี secret key)
