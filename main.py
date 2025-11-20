import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from database import create_document, get_documents, db
import csv
import io

# Safe bson import so the server can start even if bson is unavailable
try:
    from bson import ObjectId  # provided by pymongo
except Exception:
    ObjectId = None

app = FastAPI(title="AI Business Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_doc(doc: Dict[str, Any]):
    if not doc:
        return doc
    out = {**doc}
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    return out


@app.get("/")
def read_root():
    return {"message": "AI Business Analytics Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------- Models ----------
class CreateChart(BaseModel):
    dataset_id: str
    title: str
    chart_type: str
    x: str
    y: Optional[str] = None
    agg: Optional[str] = None
    options: Dict[str, Any] = {}


# ---------- Helpers ----------

def infer_type(value: str):
    try:
        if value.strip() == "":
            return "null"
        int(value)
        return "int"
    except Exception:
        try:
            float(value)
            return "float"
        except Exception:
            return "string"


# ---------- Dataset Endpoints ----------
@app.post("/api/datasets")
async def upload_dataset(file: UploadFile = File(...), name: Optional[str] = Form(None)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    # Ensure database configured
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured. Set DATABASE_URL and DATABASE_NAME.")

    # Ensure python-multipart installed (nice error if missing)
    try:
        import multipart  # noqa: F401
    except Exception:
        raise HTTPException(status_code=500, detail="Missing dependency: python-multipart. Please add it to requirements.txt")

    content = await file.read()
    text_stream = io.StringIO(content.decode("utf-8", errors="ignore"))
    reader = csv.DictReader(text_stream)

    rows: List[Dict[str, Any]] = []
    max_preview = 100
    total = 0
    columns_meta: List[Dict[str, Any]] = []
    type_counts: Dict[str, Dict[str, int]] = {}

    for row in reader:
        total += 1
        if len(rows) < max_preview:
            rows.append(row)
        # type inference
        for k, v in row.items():
            t = infer_type(str(v) if v is not None else "")
            if k not in type_counts:
                type_counts[k] = {"int": 0, "float": 0, "string": 0, "null": 0}
            type_counts[k][t] += 1

    if total == 0:
        raise HTTPException(status_code=400, detail="Empty CSV or failed to parse")

    for col, counts in type_counts.items():
        # choose the most frequent non-null type
        best = max(((k, v) for k, v in counts.items() if k != "null"), key=lambda x: x[1])[0]
        columns_meta.append({"name": col, "type": best})

    dataset_doc = {
        "name": name or file.filename,
        "columns": columns_meta,
        "sample": rows,
        "row_count": total
    }

    dataset_id = create_document("dataset", dataset_doc)
    return {"id": dataset_id, **dataset_doc}


@app.get("/api/datasets")
async def list_datasets():
    # If DB not configured, return empty list instead of crashing so UI can load
    if db is None:
        return []
    items = get_documents("dataset")
    return [serialize_doc(d) for d in items]


@app.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if ObjectId is None:
        raise HTTPException(status_code=500, detail="Missing bson (from pymongo). Ensure pymongo is installed.")
    doc = db["dataset"].find_one({"_id": ObjectId(dataset_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return serialize_doc(doc)


# ---------- Insights Endpoint ----------
@app.post("/api/insights/{dataset_id}")
async def generate_insights(dataset_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if ObjectId is None:
        raise HTTPException(status_code=500, detail="Missing bson (from pymongo). Ensure pymongo is installed.")

    doc = db["dataset"].find_one({"_id": ObjectId(dataset_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Dataset not found")

    sample: List[Dict[str, Any]] = doc.get("sample", [])
    columns = doc.get("columns", [])

    numeric_cols = [c["name"] for c in columns if c.get("type") in ["int", "float"]]
    categorical_cols = [c["name"] for c in columns if c.get("type") == "string"]

    details: List[str] = []

    # basic stats for numeric columns
    for col in numeric_cols:
        vals: List[float] = []
        for r in sample:
            v = r.get(col)
            if v is None or str(v).strip() == "":
                continue
            try:
                vals.append(float(v))
            except Exception:
                continue
        if vals:
            mn = min(vals)
            mx = max(vals)
            avg = sum(vals) / len(vals)
            details.append(f"{col}: avg {avg:.2f}, min {mn:.2f}, max {mx:.2f} based on sample")

    # mode for categorical
    from collections import Counter
    for col in categorical_cols:
        freq = Counter([str(r.get(col)) for r in sample if r.get(col) not in (None, "")])
        if freq:
            top, cnt = freq.most_common(1)[0]
            details.append(f"{col}: most frequent value is '{top}' ({cnt} occurrences in sample)")

    summary = "Quick AI-style summary based on your data sample."

    insight_doc = {
        "dataset_id": dataset_id,
        "summary": summary,
        "details": details
    }

    insight_id = create_document("insight", insight_doc)
    return {"id": insight_id, **insight_doc}


# ---------- Charts Endpoints ----------
@app.post("/api/charts")
async def save_chart(payload: CreateChart):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if ObjectId is None:
        raise HTTPException(status_code=500, detail="Missing bson (from pymongo). Ensure pymongo is installed.")

    # validate dataset exists
    if not db["dataset"].find_one({"_id": ObjectId(payload.dataset_id)}):
        raise HTTPException(status_code=400, detail="Related dataset not found")
    chart_doc = payload.model_dump()
    chart_id = create_document("chart", chart_doc)
    return {"id": chart_id, **chart_doc}


@app.get("/api/charts")
async def list_charts(dataset_id: Optional[str] = None):
    if db is None:
        return []
    filt: Dict[str, Any] = {}
    if dataset_id:
        filt["dataset_id"] = dataset_id
    items = get_documents("chart", filt)
    return [serialize_doc(d) for d in items]


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
