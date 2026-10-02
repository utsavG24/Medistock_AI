from sqlalchemy import func
from datetime import date, timedelta
from dotenv import load_dotenv

try:
    from .models import Medicine, InventoryBatch, Admin, Return, SaleHistory
    from .database import SessionLocal, ensure_schema
except ImportError:
    from models import Medicine, InventoryBatch, Admin, Return, SaleHistory
    from database import SessionLocal, ensure_schema

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import bcrypt
from pydantic import BaseModel, field_validator
import re
from fastapi import Request, HTTPException
from google import genai
import os
import json
import secrets
import time
import logging
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

load_dotenv()

APP_ENV = os.getenv("APP_ENV", "development").lower()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500"
    ).split(",")
    if origin.strip()
]
SESSION_SECRET = os.getenv("SESSION_SECRET")
if APP_ENV == "production" and not SESSION_SECRET:
    raise RuntimeError("SESSION_SECRET must be set in production")
if not SESSION_SECRET:
    SESSION_SECRET = secrets.token_urlsafe(32)
SESSION_SAME_SITE = os.getenv(
    "SESSION_SAME_SITE",
    "none" if APP_ENV == "production" else "lax"
)
SESSION_HTTPS_ONLY = os.getenv(
    "SESSION_HTTPS_ONLY",
    "true" if APP_ENV == "production" else "false"
).lower() in {"1", "true", "yes", "on"}


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site=SESSION_SAME_SITE,
    https_only=SESSION_HTTPS_ONLY,
)

@app.on_event("startup")
def migrate_schema():
    ensure_schema()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_admin(request: Request):
    if "admin_id" not in request.session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return request.session["admin_id"]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

class SignupRequest(BaseModel):
    username: str
    password: str
    full_name: str
    pharmacy_name: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value):
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain at least one capital letter")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise ValueError("Password must contain at least one special character")
        return value

class LoginRequest(BaseModel):
    username: str
    password: str

class SellRequest(BaseModel):
    batch_id: int
    quantity: int
    sale_unit: str = "unit"

    @field_validator("sale_unit")
    @classmethod
    def validate_sale_unit(cls, value):
        if value not in {"unit", "strip"}:
            raise ValueError("sale_unit must be 'unit' or 'strip'")
        return value

class CustomerReturnRequest(BaseModel):
    batch_id: int
    quantity: int
    reason: str | None = None

class SupplierReturnRequest(BaseModel):
    batch_id: int
    quantity: int
    quantity_received: int = 0
    reason: str | None = None

class AddMedicineRequest(BaseModel):
    name: str
    category: str
    manufacturer: str
    unit: str
    units_per_strip: int = 1
    unit_price: float
    price_basis: str = "strip"
    reorder_level: int
    batch_number: str
    quantity: int
    manufacture_date: date
    expiry_date: date

class AddBatchRequest(BaseModel):
    batch_number: str
    quantity: int
    manufacture_date: date
    expiry_date: date

class UpdateMedicineDetailsRequest(BaseModel):
    unit: str
    units_per_strip: int = 1
    price_basis: str = "unit"

class AskRequest(BaseModel):
    question: str
    history: list[dict] = []

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def generate_with_ollama(context: str):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": context,
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX}
    }).encode("utf-8")
    request = UrlRequest(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Start Ollama and try again."
        ) from error

    answer = result.get("response", "").strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response.")
    return answer

class AskRequest(BaseModel):
    question: str
    history: list[dict] = []


@app.get("/medicines")
def get_medicines(db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicines = db.query(Medicine).order_by(Medicine.name).all()
    batches = db.query(InventoryBatch).order_by(InventoryBatch.expiry_date).all()
    sales_counts = dict(
        db.query(SaleHistory.medicine_id, func.count(SaleHistory.sale_id))
        .group_by(SaleHistory.medicine_id)
        .all()
    )
    returns_counts = dict(
        db.query(Return.medicine_id, func.count(Return.return_id))
        .group_by(Return.medicine_id)
        .all()
    )
    batches_by_medicine = {}
    for batch in batches:
        batches_by_medicine.setdefault(batch.medicine_id, []).append(batch)

    output = []
    for medicine in medicines:
        medicine_batches = batches_by_medicine.get(medicine.medicine_id, [])
        output.append({
            "medicine_id": medicine.medicine_id,
            "name": medicine.name,
            "category": medicine.category,
            "manufacturer": medicine.manufacturer,
            "unit": medicine.unit,
            "units_per_strip": medicine.units_per_strip,
            "unit_price": float(medicine.unit_price),
            "price_basis": medicine.price_basis,
            "reorder_level": medicine.reorder_level,
            "is_active": medicine.is_active,
            "total_stock": sum(batch.quantity for batch in medicine_batches),
            "batch_count": len(medicine_batches),
            "sales_count": sales_counts.get(medicine.medicine_id, 0),
            "returns_count": returns_counts.get(medicine.medicine_id, 0),
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "batch_number": batch.batch_number,
                    "quantity": batch.quantity,
                    "manufacture_date": batch.manufacture_date.isoformat(),
                    "expiry_date": batch.expiry_date.isoformat()
                }
                for batch in medicine_batches
            ]
        })
    return output

@app.get("/dashboard/summary")
def get_summary(db: Session = Depends(get_db)):
    total_medicines = db.query(Medicine).filter(Medicine.is_active.is_(True)).count()
    total_stock = db.query(func.sum(InventoryBatch.quantity)).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(Medicine.is_active.is_(True)).scalar() or 0

    # stock per medicine (summed across all its batches)
    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("stock")
    ).group_by(InventoryBatch.medicine_id).subquery()

    low_stock_count = db.query(Medicine).filter(Medicine.is_active.is_(True)).join(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).filter(stock_by_medicine.c.stock < Medicine.reorder_level).count()

    today = date.today()
    expiring_count = db.query(InventoryBatch).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(
        Medicine.is_active.is_(True),
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= today + timedelta(days=60)
    ).count()

    return {
        "total_medicines": total_medicines,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "expiring_soon_count": expiring_count
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/dashboard/sales-trend")
def get_sales_trend(period: str = "6m", db: Session = Depends(get_db)):
    today = date.today()

    if period == "30d":
        start_date = today - timedelta(days=29)
        labels = []
        values = []
        current = start_date
        while current <= today:
            next_day = current + timedelta(days=1)
            revenue = db.query(func.coalesce(func.sum(SaleHistory.total_amount), 0)).filter(
                SaleHistory.sale_date >= current,
                SaleHistory.sale_date < next_day
            ).scalar() or 0
            labels.append(current.strftime("%b %d"))
            values.append(float(revenue))
            current = next_day
        return {"labels": labels, "values": values}

    if period == "fy":
        financial_year_start_year = today.year if today.month >= 4 else today.year - 1
        labels = []
        values = []
        elapsed_months = (today.month - 4) % 12 + 1
        for month_offset in range(elapsed_months):
            month_number = 4 + month_offset
            year = financial_year_start_year
            if month_number > 12:
                month_number -= 12
                year += 1
            month_start = date(year, month_number, 1)
            if month_number == 12:
                month_end = date(year + 1, 1, 1)
            else:
                month_end = date(year, month_number + 1, 1)
            revenue = db.query(func.coalesce(func.sum(SaleHistory.total_amount), 0)).filter(
                SaleHistory.sale_date >= month_start,
                SaleHistory.sale_date < month_end
            ).scalar() or 0
            labels.append(month_start.strftime("%b"))
            values.append(float(revenue))
        return {"labels": labels, "values": values}

    total_months = 6 if period == "6m" else 12
    labels = []
    values = []

    for offset in range(total_months - 1, -1, -1):
        month_number = today.month - offset
        year = today.year
        while month_number <= 0:
            month_number += 12
            year -= 1
        while month_number > 12:
            month_number -= 12
            year += 1

        month_start = date(year, month_number, 1)
        if month_number == 12:
            next_year = year + 1
            next_month = 1
        else:
            next_year = year
            next_month = month_number + 1
        month_end = date(next_year, next_month, 1)

        revenue = db.query(func.coalesce(func.sum(SaleHistory.total_amount), 0)).filter(
            SaleHistory.sale_date >= month_start,
            SaleHistory.sale_date < month_end
        ).scalar() or 0

        labels.append(month_start.strftime("%b"))
        values.append(float(revenue))

    return {"labels": labels, "values": values}


@app.get("/stock/low")
def get_low_stock(db: Session = Depends(get_db)):
    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("stock")
    ).group_by(InventoryBatch.medicine_id).subquery()

    results = db.query(
        Medicine.name, Medicine.category, Medicine.reorder_level, Medicine.unit, Medicine.units_per_strip,
        stock_by_medicine.c.stock
    ).filter(Medicine.is_active.is_(True)).join(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).filter(stock_by_medicine.c.stock < Medicine.reorder_level).all()

    return [
        {
            "name": r.name,
            "category": r.category,
            "current_stock": r.stock,
            "reorder_level": r.reorder_level,
            "unit": r.unit,
            "units_per_strip": r.units_per_strip
        }
        for r in results
    ]
@app.get("/stock/expiring")
def get_expiring_stock(db: Session = Depends(get_db)):
    today = date.today()
    results = db.query(
        Medicine.name, Medicine.category,
        InventoryBatch.batch_number, InventoryBatch.quantity, InventoryBatch.expiry_date,
        Medicine.unit, Medicine.units_per_strip
    ).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(
        Medicine.is_active.is_(True),
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= today + timedelta(days=60)
    ).order_by(InventoryBatch.expiry_date).all()

    return [
        {
            "name": r.name,
            "category": r.category,
            "batch_number": r.batch_number,
            "quantity": r.quantity,
            "unit": r.unit,
            "units_per_strip": r.units_per_strip,
            "expiry_date": r.expiry_date.isoformat()
        }
        for r in results
    ]
@app.get("/stock/current")
def get_current_stock(db: Session = Depends(get_db)):
    today = date.today()
    results = db.query(
        Medicine.name, Medicine.category,
        InventoryBatch.batch_id, InventoryBatch.batch_number,
        InventoryBatch.quantity, InventoryBatch.manufacture_date,InventoryBatch.expiry_date,
        Medicine.reorder_level, Medicine.unit, Medicine.units_per_strip
    ).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(Medicine.is_active.is_(True)).order_by(InventoryBatch.expiry_date).all()

    output = []
    for r in results:
        days_left = (r.expiry_date - today).days
        if r.quantity == 0:
            status = "Out of Stock"
        elif days_left < 0:
            status = "Expired"
        elif days_left <= 60:
            status = "Expiring Soon"
        elif r.quantity < r.reorder_level:
            status = "Low Stock"
        else:
            status = "Healthy"

        output.append({
            "batch_id": r.batch_id,
            "name": r.name,
            "category": r.category,
            "batch_number": r.batch_number,
            "stock": r.quantity,
            "unit": r.unit,
            "units_per_strip": r.units_per_strip,
            "reorder_level": r.reorder_level,
            "manufacture_date": r.manufacture_date.isoformat(),
            "expiry_date": r.expiry_date.isoformat(),
            "status": status
        })
    return output


@app.post("/auth/signup")
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(Admin).filter(Admin.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    new_admin = Admin(
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        pharmacy_name=data.pharmacy_name
    )
    db.add(new_admin)
    db.commit()
    return {"message": "Account created successfully"}


@app.post("/auth/login")
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session["admin_id"] = admin.admin_id
    request.session["full_name"] = admin.full_name
    request.session["pharmacy_name"] = admin.pharmacy_name or "Pharmacy"
    return {
        "message": "Login successful",
        "full_name": admin.full_name,
        "pharmacy_name": admin.pharmacy_name or "Pharmacy"
    }


@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}


@app.get("/auth/me")
def get_current_admin(request: Request):
    if "admin_id" not in request.session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {
        "full_name": request.session["full_name"],
        "pharmacy_name": request.session.get("pharmacy_name", "Pharmacy")
    }
@app.post("/sales")
def sell_stock(data: SellRequest, db: Session = Depends(get_db)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    medicine = db.query(Medicine).filter(Medicine.medicine_id == batch.medicine_id).first()
    if not medicine or not medicine.is_active:
        raise HTTPException(status_code=409, detail="This medicine is archived and cannot receive stock activity")
    if batch.expiry_date < date.today():
        raise HTTPException(status_code=400, detail="Cannot sell an expired batch")
    units_per_strip = medicine.units_per_strip or 1
    quantity_units = data.quantity * units_per_strip if data.sale_unit == "strip" else data.quantity
    if batch.quantity < quantity_units:
        raise HTTPException(status_code=400, detail=f"Only {batch.quantity} units available in this batch")

    batch.quantity -= quantity_units

    price_per_unit = float(medicine.unit_price)
    if medicine.price_basis == "strip":
        sale_amount = price_per_unit * quantity_units / units_per_strip
        recorded_unit_price = price_per_unit / units_per_strip
    else:
        sale_amount = price_per_unit * quantity_units
        recorded_unit_price = price_per_unit

    sale = SaleHistory(
        medicine_id=batch.medicine_id,
        batch_id=batch.batch_id,
        quantity_sold=quantity_units,
        sale_date=date.today(),
        unit_price=round(recorded_unit_price, 2),
        total_amount=round(sale_amount, 2)
    )
    db.add(sale)
    db.commit()
    return {"message": f"Sold {data.quantity} {data.sale_unit}(s)", "remaining_stock": batch.quantity}


@app.post("/returns/customer")
def customer_return(data: CustomerReturnRequest, db: Session = Depends(get_db)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    medicine = db.query(Medicine).filter(Medicine.medicine_id == batch.medicine_id).first()
    if not medicine or not medicine.is_active:
        raise HTTPException(status_code=409, detail="This medicine is archived and cannot receive stock activity")

    batch.quantity += data.quantity

    ret = Return(
        medicine_id=batch.medicine_id,
        batch_id=batch.batch_id,
        quantity=data.quantity,
        return_type="customer",
        reason=data.reason,
        return_date=date.today()
    )
    db.add(ret)
    db.commit()
    return {"message": f"Added {data.quantity} units back to stock (customer return)", "new_stock": batch.quantity}


@app.post("/returns/supplier")
def supplier_return(data: SupplierReturnRequest, db: Session = Depends(get_db)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    medicine = db.query(Medicine).filter(Medicine.medicine_id == batch.medicine_id).first()
    if not medicine or not medicine.is_active:
        raise HTTPException(status_code=409, detail="This medicine is archived and cannot receive stock activity")
    if batch.quantity < data.quantity:
        raise HTTPException(status_code=400, detail=f"Only {batch.quantity} units available to return")

    net_change = data.quantity_received - data.quantity
    batch.quantity += net_change

    ret = Return(
        medicine_id=batch.medicine_id,
        batch_id=batch.batch_id,
        quantity=data.quantity,
        return_type="supplier",
        reason=data.reason,
        return_date=date.today()
    )
    db.add(ret)
    db.commit()

    msg = f"Returned {data.quantity} units"
    if data.quantity_received:
        msg += f", received {data.quantity_received} replacement units"

    return {"message": msg, "new_stock": batch.quantity}


@app.get("/transactions")
def get_transactions(db: Session = Depends(get_db)):
    sales = db.query(
        SaleHistory.sale_id, SaleHistory.quantity_sold, SaleHistory.sale_date,
        SaleHistory.total_amount, SaleHistory.batch_id, Medicine.name,
        InventoryBatch.batch_number
    ).join(
        Medicine, Medicine.medicine_id == SaleHistory.medicine_id
    ).outerjoin(
        InventoryBatch, InventoryBatch.batch_id == SaleHistory.batch_id
    ).all()

    returns = db.query(
        Return.return_id, Return.quantity, Return.return_date, Return.batch_id,
        Return.return_type, Return.reason, Medicine.name, InventoryBatch.batch_number
    ).join(
        Medicine, Medicine.medicine_id == Return.medicine_id
    ).outerjoin(
        InventoryBatch, InventoryBatch.batch_id == Return.batch_id
    ).all()

    transactions = []

    for s in sales:
        transactions.append({
            "type": "Sale",
            "medicine_name": s.name,
            "batch_id": s.batch_id,
            "batch_number": s.batch_number,
            "quantity": s.quantity_sold,
            "date": s.sale_date.isoformat(),
            "amount": float(s.total_amount),
            "reason": None
        })

    for r in returns:
        transactions.append({
            "type": "Customer Return" if r.return_type == "customer" else "Supplier Return",
            "medicine_name": r.name,
            "batch_id": r.batch_id,
            "batch_number": r.batch_number,
            "quantity": r.quantity,
            "date": r.return_date.isoformat(),
            "amount": None,
            "reason": r.reason
        })

    transactions.sort(key=lambda t: t["date"], reverse=True)
    return transactions

@app.post("/medicines")
def add_medicine(data: AddMedicineRequest, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    if data.expiry_date <= data.manufacture_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacture date")
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Initial quantity must be greater than 0")
    if data.units_per_strip <= 0:
        raise HTTPException(status_code=400, detail="Units per strip must be greater than 0")
    if data.price_basis not in {"unit", "strip"}:
        raise HTTPException(status_code=400, detail="Price basis must be 'unit' or 'strip'")

    new_medicine = Medicine(
        name=data.name,
        category=data.category,
        manufacturer=data.manufacturer,
        unit=data.unit,
        units_per_strip=data.units_per_strip,
        unit_price=data.unit_price,
        price_basis=data.price_basis,
        reorder_level=data.reorder_level
    )
    db.add(new_medicine)
    db.flush()  # assigns new_medicine.medicine_id without committing yet

    new_batch = InventoryBatch(
        medicine_id=new_medicine.medicine_id,
        batch_number=data.batch_number,
        quantity=data.quantity,
        manufacture_date=data.manufacture_date,
        expiry_date=data.expiry_date
    )
    db.add(new_batch)
    db.commit()

    return {
        "message": "Medicine and initial batch added successfully",
        "medicine_id": new_medicine.medicine_id,
        "batch_id": new_batch.batch_id
    }

@app.post("/medicines/{medicine_id}/batches")
def add_batch(medicine_id: int, data: AddBatchRequest, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicine = db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    if not medicine.is_active:
        raise HTTPException(status_code=409, detail="Restore this medicine before adding a batch")
    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")
    if data.expiry_date <= data.manufacture_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacture date")
    duplicate = db.query(InventoryBatch).filter(
        InventoryBatch.medicine_id == medicine_id,
        InventoryBatch.batch_number == data.batch_number
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="This batch number already exists for the medicine")

    batch = InventoryBatch(medicine_id=medicine_id, **data.model_dump())
    db.add(batch)
    db.commit()
    return {"message": "Batch added successfully", "batch_id": batch.batch_id}

@app.patch("/medicines/{medicine_id}")
def update_medicine_details(
    medicine_id: int,
    data: UpdateMedicineDetailsRequest,
    db: Session = Depends(get_db),
    _: int = Depends(require_admin)
):
    medicine = db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    if not data.unit.strip():
        raise HTTPException(status_code=400, detail="Base unit is required")
    if data.units_per_strip <= 0:
        raise HTTPException(status_code=400, detail="Units per strip must be greater than 0")
    if data.price_basis not in {"unit", "strip"}:
        raise HTTPException(status_code=400, detail="Price basis must be 'unit' or 'strip'")

    medicine.unit = data.unit.strip()
    medicine.units_per_strip = data.units_per_strip
    medicine.price_basis = data.price_basis
    db.commit()
    return {"message": "Medicine details updated successfully"}

@app.post("/medicines/{medicine_id}/archive")
def archive_medicine(medicine_id: int, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicine = db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    if not medicine.is_active:
        return {"message": "Medicine is already archived"}
    medicine.is_active = False
    db.commit()
    return {"message": "Medicine archived successfully"}

@app.post("/medicines/{medicine_id}/restore")
def restore_medicine(medicine_id: int, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicine = db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    medicine.is_active = True
    db.commit()
    return {"message": "Medicine restored successfully"}

@app.delete("/medicines/{medicine_id}")
def delete_medicine(medicine_id: int, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicine = db.query(Medicine).filter(Medicine.medicine_id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")

    sales_count = db.query(SaleHistory).filter(SaleHistory.medicine_id == medicine_id).count()
    returns_count = db.query(Return).filter(Return.medicine_id == medicine_id).count()
    if sales_count or returns_count:
        raise HTTPException(
            status_code=409,
            detail="This medicine has analytics history and cannot be deleted. Keep it for reporting accuracy."
        )

    batches = db.query(InventoryBatch).filter(InventoryBatch.medicine_id == medicine_id).all()
    if any(batch.quantity > 0 for batch in batches):
        raise HTTPException(status_code=409, detail="Clear all remaining stock before deleting this medicine")

    for batch in batches:
        db.delete(batch)
    db.delete(medicine)
    db.commit()
    return {"message": "Medicine deleted successfully"}

@app.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.quantity > 0:
        raise HTTPException(status_code=409, detail="Only empty batches can be deleted")
    if db.query(SaleHistory).filter(SaleHistory.medicine_id == batch.medicine_id).count():
        raise HTTPException(
            status_code=409,
            detail="This batch belongs to a medicine with sales history and cannot be deleted"
        )
    if db.query(Return).filter(Return.batch_id == batch_id).count():
        raise HTTPException(status_code=409, detail="This batch has return history and cannot be deleted")

    db.delete(batch)
    db.commit()
    return {"message": "Batch deleted successfully"}

@app.get("/stock/requirement")
def get_stock_requirement(db: Session = Depends(get_db)):
    SAFETY_DAYS = 14
    SALES_LOOKBACK_DAYS = 90

    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("current_stock")
    ).filter(
        InventoryBatch.expiry_date >= date.today()
    ).group_by(InventoryBatch.medicine_id).subquery()

    cutoff = date.today() - timedelta(days=SALES_LOOKBACK_DAYS)
    sales_by_medicine = db.query(
        SaleHistory.medicine_id,
        func.sum(SaleHistory.quantity_sold).label("total_sold")
    ).filter(SaleHistory.sale_date >= cutoff).group_by(SaleHistory.medicine_id).subquery()

    results = db.query(
        Medicine.medicine_id, Medicine.name, Medicine.category, Medicine.reorder_level,
        Medicine.unit_price, Medicine.unit, Medicine.units_per_strip, Medicine.price_basis,
        stock_by_medicine.c.current_stock,
        sales_by_medicine.c.total_sold
    ).outerjoin(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).outerjoin(
        sales_by_medicine, Medicine.medicine_id == sales_by_medicine.c.medicine_id
    ).filter(Medicine.is_active.is_(True)).all()

    output = []
    for r in results:
        is_fully_expired = r.current_stock is None
        current_stock = r.current_stock or 0

        if current_stock >= r.reorder_level:
            continue  # doesn't need reordering, skip it

        avg_daily_sales = (r.total_sold or 0) / SALES_LOOKBACK_DAYS
        safety_stock = avg_daily_sales * SAFETY_DAYS
        target_level = r.reorder_level + safety_stock
        suggested_order_qty = max(round(target_level - current_stock), 0)
        days_of_stock_left = round(current_stock / avg_daily_sales, 1) if avg_daily_sales > 0 else None
        unit_cost = float(r.unit_price)
        if r.price_basis == "strip":
            unit_cost /= r.units_per_strip or 1
        estimated_cost = round(suggested_order_qty * unit_cost, 2)

        output.append({
            "medicine_id": r.medicine_id,
            "name": r.name,
            "category": r.category,
            "current_stock": current_stock,
            "reorder_level": r.reorder_level,
            "unit": r.unit,
            "units_per_strip": r.units_per_strip,
            "avg_daily_sales": round(avg_daily_sales, 2),
            "suggested_order_qty": suggested_order_qty,
            "unit_price": float(r.unit_price),
            "estimated_cost": estimated_cost,
            "days_of_stock_left": days_of_stock_left,
            "fully_expired": is_fully_expired
        })

    output.sort(key=lambda x: (x["days_of_stock_left"] is None, x["days_of_stock_left"]))
    return output

def get_budget_from_question(question: str):
    match = re.search(
        r"(?:budget|under|within|spend|amount)\D{0,20}(?:₹|rs\.?|inr\s*)?\s*([\d,]+)",
        question.lower()
    )
    if not match:
        return None
    return float(match.group(1).replace(",", ""))

def build_budget_reorder_answer(question: str, requirements: list[dict]):
    budget = get_budget_from_question(question)
    if budget is None:
        return None

    selected = []
    spent = 0.0
    for item in requirements:
        item_cost = float(item["estimated_cost"])
        if item_cost <= 0 or spent + item_cost > budget:
            continue
        selected.append(item)
        spent += item_cost

    remaining = round(budget - spent, 2)
    if not selected:
        return (
            f"No complete urgent reorder item fits within a budget of ₹{budget:,.2f}. "
            "Increase the budget or review the suggested quantities."
        )

    lines = [f"Urgent reorder plan within ₹{budget:,.2f}:"]
    for index, item in enumerate(selected, start=1):
        days_left = (
            f"{item['days_of_stock_left']} days left"
            if item["days_of_stock_left"] is not None
            else "stockout risk"
        )
        lines.append(
            f"{index}. {item['name']} — order {item['suggested_order_qty']} {item['unit']} "
            f"({item['estimated_cost']:,.2f}); {days_left}."
        )
    lines.append(f"Total: ₹{spent:,.2f} | Remaining budget: ₹{remaining:,.2f}")
    return "\n".join(lines)

def build_full_reorder_list_answer(question: str, requirements: list[dict]):
    normalized_question = question.lower()
    asks_reorder = "reorder" in normalized_question
    asks_full_list = any(phrase in normalized_question for phrase in (
        "list every", "full list", "every medicine", "all medicines",
        "which medicines need", "needs reordering", "need reordering"
    ))
    if not (asks_reorder and asks_full_list):
        return None

    if not requirements:
        return "No medicines currently need reordering."

    lines = ["Medicines that need reordering:"]
    for index, item in enumerate(requirements, start=1):
        days_left = (
            f"{item['days_of_stock_left']} days left"
            if item["days_of_stock_left"] is not None
            else "stockout risk"
        )
        lines.append(
            f"{index}. {item['name']} — current stock: {item['current_stock']} {item['unit']}; "
            f"reorder level: {item['reorder_level']} {item['unit']}; "
            f"suggested order: {item['suggested_order_qty']} {item['unit']} "
            f"(₹{item['estimated_cost']:,.2f}); {days_left}."
        )
    lines.append(f"Total medicines needing reorder: {len(requirements)}")
    return "\n".join(lines)


def build_total_reorder_cost_answer(question: str, requirements: list[dict]):
    normalized_question = question.lower()
    asks_for_total = "total" in normalized_question and (
        "cost" in normalized_question or "price" in normalized_question or "amount" in normalized_question
    )
    asks_for_reorder = "reorder" in normalized_question or "required medicine" in normalized_question
    if not asks_for_total or not asks_for_reorder:
        return None

    total_cost = round(sum(float(item["estimated_cost"]) for item in requirements), 2)
    total_items = len(requirements)
    total_units = sum(int(item["suggested_order_qty"]) for item in requirements)
    return (
        f"The total estimated cost to reorder all {total_items} required medicines is "
        f"₹{total_cost:,.2f} for {total_units:,} units."
    )

def build_expiring_medicines_answer(question: str, db: Session):
    normalized_question = question.lower()
    asks_about_expiry = "expir" in normalized_question or "expiry" in normalized_question
    asks_about_three_months = (
        "3 month" in normalized_question
        or "three month" in normalized_question
        or "next quarter" in normalized_question
        or "90 day" in normalized_question
    )
    if not asks_about_expiry or not asks_about_three_months:
        return None

    today = date.today()
    expiry_limit = today + timedelta(days=90)
    results = db.query(
        Medicine.name,
        InventoryBatch.batch_number,
        InventoryBatch.quantity,
        InventoryBatch.expiry_date,
        Medicine.unit
    ).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(
        Medicine.is_active.is_(True),
        InventoryBatch.quantity > 0,
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= expiry_limit
    ).order_by(InventoryBatch.expiry_date).all()

    if not results:
        return "No active medicine with remaining stock is scheduled to expire in the next 3 months."

    lines = [f"Medicines expiring in the next 3 months ({today.isoformat()} to {expiry_limit.isoformat()}):"]
    for index, item in enumerate(results, start=1):
        days_left = (item.expiry_date - today).days
        lines.append(
            f"{index}. {item.name} — batch {item.batch_number}, {item.quantity} {item.unit}, "
            f"expires {item.expiry_date.isoformat()} ({days_left} days left)."
        )
    lines.append(f"Total batches: {len(results)}")
    return "\n".join(lines)

def build_sales_returns_answer(question: str, db: Session):
    normalized_question = question.lower()
    asks_about_sales = "sale" in normalized_question or "sales" in normalized_question
    asks_about_returns = "return" in normalized_question or "returns" in normalized_question
    if not (asks_about_sales and asks_about_returns):
        return None

    sales = db.query(SaleHistory, Medicine.name).join(
        Medicine, Medicine.medicine_id == SaleHistory.medicine_id
    ).order_by(SaleHistory.sale_date.desc()).all()
    returns = db.query(Return, Medicine.name).join(
        Medicine, Medicine.medicine_id == Return.medicine_id
    ).order_by(Return.return_date.desc()).all()

    sold_units = sum(int(sale.quantity_sold or 0) for sale, _ in sales)
    sales_revenue = round(sum(float(sale.total_amount or 0) for sale, _ in sales), 2)
    returned_units = sum(int(item.quantity or 0) for item, _ in returns)
    customer_units = sum(int(item.quantity or 0) for item, _ in returns if item.return_type == "customer")
    supplier_units = sum(int(item.quantity or 0) for item, _ in returns if item.return_type == "supplier")

    lines = [
        "Complete sales and returns summary:",
        f"Sales: {len(sales)} transactions, {sold_units:,} units sold, revenue ₹{sales_revenue:,.2f}.",
        f"Returns: {len(returns)} transactions, {returned_units:,} units returned "
        f"(customer: {customer_units:,}, supplier: {supplier_units:,})."
    ]

    if sales:
        lines.append("Sales details:")
        for sale, medicine_name in sales:
            lines.append(
                f"- {sale.sale_date.isoformat()} — {medicine_name}, {sale.quantity_sold} units, "
                f"₹{float(sale.total_amount or 0):,.2f}."
            )
    else:
        lines.append("Sales details: no sales recorded.")

    if returns:
        lines.append("Returns details:")
        for item, medicine_name in returns:
            reason = f", reason: {item.reason}" if item.reason else ""
            lines.append(
                f"- {item.return_date.isoformat()} — {medicine_name}, {item.quantity} units, "
                f"{item.return_type} return{reason}."
            )
    else:
        lines.append("Returns details: no returns recorded.")

    return "\n".join(lines)

def build_low_stock_answer(question: str, db: Session):
    normalized_question = question.lower()
    asks_about_low_stock = "low stock" in normalized_question or "below reorder" in normalized_question
    asks_for_reorder_level = "reorder level" in normalized_question or "reorder" in normalized_question
    if not asks_about_low_stock or not asks_for_reorder_level:
        return None

    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.coalesce(func.sum(InventoryBatch.quantity), 0).label("current_stock")
    ).group_by(InventoryBatch.medicine_id).subquery()
    results = db.query(
        Medicine.name,
        Medicine.category,
        Medicine.reorder_level,
        Medicine.unit,
        func.coalesce(stock_by_medicine.c.current_stock, 0).label("current_stock")
    ).outerjoin(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).filter(
        Medicine.is_active.is_(True),
        func.coalesce(stock_by_medicine.c.current_stock, 0) < Medicine.reorder_level
    ).order_by(Medicine.name).all()

    if not results:
        return "No active medicines are currently below their reorder levels."

    lines = ["Medicines with low stock:"]
    for index, item in enumerate(results, start=1):
        lines.append(
            f"{index}. {item.name} — current stock: {int(item.current_stock)} {item.unit}; "
            f"reorder level: {item.reorder_level} {item.unit}."
        )
    lines.append(f"Total medicines needing reorder: {len(results)}")
    return "\n".join(lines)



def get_generic_name(full_name: str) -> str:
    return full_name.split()[0].lower() if full_name else ""

def find_medicines_by_generic(text: str, medicines: list[Medicine]) -> list[Medicine]:
    normalized = text.lower()
    matched = []
    for medicine in medicines:
        generic = get_generic_name(medicine.name)
        if generic and generic in normalized:
            matched.append(medicine)
    return matched

def build_extended_answers(question: str, db: Session, history: list[dict] | None = None):
    normalized_question = question.lower()
    today = date.today()

    medicines = db.query(Medicine).filter(Medicine.is_active.is_(True)).all()

    # ---- Exact full-name match runs first (handles distinct products
    # named identically to a generic, e.g. "Test Medicine") ----
    for medicine in medicines:
        if medicine.name.lower() in normalized_question:
            asks_price = "price" in normalized_question or "cost" in normalized_question
            asks_stock = (
                "stock" in normalized_question
                or "how much" in normalized_question
                or "how many" in normalized_question
            )
            if asks_price and "reorder" not in normalized_question:
                return f"{medicine.name} is priced at ₹{float(medicine.unit_price):,.2f} per {medicine.unit}."
            if asks_stock:
                current_stock = db.query(
                    func.coalesce(func.sum(InventoryBatch.quantity), 0)
                ).filter(InventoryBatch.medicine_id == medicine.medicine_id).scalar()
                return f"{medicine.name} currently has {int(current_stock)} {medicine.unit} in stock."

    # ---- Generic/ingredient-name match, with follow-up resolution via history ----
    matched = find_medicines_by_generic(normalized_question, medicines)
    print(f"[DEBUG] matched from current question: {[m.name for m in matched]}")
    if not matched and history:
        for turn in reversed(history[-4:]):
            prior_matched = find_medicines_by_generic(turn.get("question", "").lower(), medicines)
            if prior_matched:
                matched = prior_matched
                break

    if matched:
        asks_price = any(w in normalized_question for w in ("price", "cost", "worth", "value")) and "reorder" not in normalized_question
        asks_stock = any(w in normalized_question for w in ("stock", "how much", "how many", "quantity", "left"))
        asks_manufacturer = any(w in normalized_question for w in ("manufacturer", "made by", "who makes", "company", "brand"))
        asks_category = "category" in normalized_question or "type of medicine" in normalized_question
        asks_reorder_level = (
            ("reorder level" in normalized_question or "reorder point" in normalized_question)
            or ("needs reorder" in normalized_question or "need reorder" in normalized_question)
        )
        asks_batches = "batch" in normalized_question
        asks_units_sold = any(w in normalized_question for w in ("sold", "units sold","sales" ,"how many sales"))
        asks_days_left = any(w in normalized_question for w in ("run out", "last how long", "days left", "how long will"))
        asks_active_status = any(w in normalized_question for w in ("active", "discontinued", "archived"))
        asks_expiry = any(w in normalized_question for w in ("expir", "soonest", "expire"))

        if asks_manufacturer:
            if len(matched) == 1:
                m = matched[0]
                return f"{m.name} is manufactured by {m.manufacturer}."
            lines = [f"Manufacturers for {matched[0].name.split()[0]} products:"]
            for m in matched:
                lines.append(f"- {m.name}: {m.manufacturer}")
            return "\n".join(lines)

        if asks_category:
            if len(matched) == 1:
                m = matched[0]
                return f"{m.name} falls under the {m.category} category."
            lines = [f"Categories for {matched[0].name.split()[0]} products:"]
            for m in matched:
                lines.append(f"- {m.name}: {m.category}")
            return "\n".join(lines)

        if asks_reorder_level:
            lines = []
            for m in matched:
                current_stock = db.query(
                    func.coalesce(func.sum(InventoryBatch.quantity), 0)
                ).filter(InventoryBatch.medicine_id == m.medicine_id).scalar()
                status = "needs reordering" if current_stock < m.reorder_level else "is above its reorder level"
                lines.append(f"- {m.name}: reorder level {m.reorder_level} {m.unit}, current stock {int(current_stock)} {m.unit} — {status}.")
            return "\n".join(lines)

        if asks_batches:
            lines = []
            for m in matched:
                batches = db.query(InventoryBatch).filter(
                    InventoryBatch.medicine_id == m.medicine_id
                ).order_by(InventoryBatch.expiry_date).all()
                if not batches:
                    lines.append(f"{m.name} has no recorded batches.")
                    continue
                lines.append(f"{m.name} batches:")
                for b in batches:
                    lines.append(f"  - {b.batch_number}: {b.quantity} {m.unit}, expires {b.expiry_date.isoformat()}")
            return "\n".join(lines)

        if asks_units_sold:
            lines = []
            for m in matched:
                total_sold = db.query(
                    func.coalesce(func.sum(SaleHistory.quantity_sold), 0)
                ).filter(SaleHistory.medicine_id == m.medicine_id).scalar()
                revenue = db.query(
                    func.coalesce(func.sum(SaleHistory.total_amount), 0)
                ).filter(SaleHistory.medicine_id == m.medicine_id).scalar()
                lines.append(f"- {m.name}: {int(total_sold)} units sold, ₹{float(revenue):,.2f} revenue.")
            return "\n".join(lines)

        if asks_days_left:
            lines = []
            cutoff = today - timedelta(days=90)
            for m in matched:
                current_stock = db.query(
                    func.coalesce(func.sum(InventoryBatch.quantity), 0)
                ).filter(
                    InventoryBatch.medicine_id == m.medicine_id,
                    InventoryBatch.expiry_date >= today
                ).scalar()
                total_sold = db.query(
                    func.coalesce(func.sum(SaleHistory.quantity_sold), 0)
                ).filter(
                    SaleHistory.medicine_id == m.medicine_id,
                    SaleHistory.sale_date >= cutoff
                ).scalar()
                avg_daily = total_sold / 90
                if avg_daily > 0:
                    days_left = round(current_stock / avg_daily, 1)
                    lines.append(f"- {m.name}: about {days_left} days of stock left at current sales pace.")
                else:
                    lines.append(f"- {m.name}: no recent sales, so a run-out estimate isn't possible.")
            return "\n".join(lines)

        if asks_active_status:
            lines = [f"- {m.name}: {'active' if m.is_active else 'archived/discontinued'}" for m in matched]
            return "\n".join(lines)

        if asks_expiry:
            lines = []
            for m in matched:
                next_batch = db.query(InventoryBatch).filter(
                    InventoryBatch.medicine_id == m.medicine_id,
                    InventoryBatch.quantity > 0,
                    InventoryBatch.expiry_date >= today
                ).order_by(InventoryBatch.expiry_date).first()

                if next_batch:
                    days_left = (next_batch.expiry_date - today).days
                    lines.append(
                        f"- {m.name}: soonest expiring batch is {next_batch.batch_number}, "
                        f"expiring {next_batch.expiry_date.isoformat()} ({days_left} days left)."
                    )
                else:
                    lines.append(f"- {m.name}: no active (non-expired, in-stock) batches found.")
            return "\n".join(lines)

        if asks_price:
            if len(matched) == 1:
                m = matched[0]
                return f"{m.name} is priced at ₹{float(m.unit_price):,.2f} per {m.unit}."
            lines = [f"Prices for {matched[0].name.split()[0]} products:"]
            for m in matched:
                lines.append(f"- {m.name}: ₹{float(m.unit_price):,.2f} per {m.unit}")
            return "\n".join(lines)

        if asks_stock:
            total = 0
            lines = []
            for m in matched:
                stock = db.query(func.coalesce(func.sum(InventoryBatch.quantity), 0)).filter(
                    InventoryBatch.medicine_id == m.medicine_id
                ).scalar()
                total += int(stock)
                lines.append(f"- {m.name}: {int(stock)} {m.unit}")
            if len(matched) == 1:
                return f"{matched[0].name} currently has {total} {matched[0].unit} in stock."
            header = f"Total quantity across {matched[0].name.split()[0]} products: {total} units."
            return "\n".join([header] + lines)

    # ---- everything below this line is the rest of your existing function
    # (revenue, best seller, slow mover, returns counts, etc.) — unchanged ----

    # ---- Revenue & sales ----
    asks_total_revenue = "total revenue" in normalized_question or "how much revenue" in normalized_question
    if asks_total_revenue:
        total = db.query(func.coalesce(func.sum(SaleHistory.total_amount), 0)).scalar()
        return f"Total revenue from all recorded sales: ₹{float(total):,.2f}."

    asks_best_seller = any(
        phrase in normalized_question for phrase in ("best selling", "best-selling", "top seller", "most sold")
    )
    if asks_best_seller:
        result = db.query(
            Medicine.name, func.sum(SaleHistory.quantity_sold).label("total_sold")
        ).join(
            Medicine, Medicine.medicine_id == SaleHistory.medicine_id
        ).filter(Medicine.is_active.is_(True)
        ).group_by(Medicine.name).order_by(func.sum(SaleHistory.quantity_sold).desc()).first()
        if result:
            return f"The best-selling medicine is {result.name}, with {result.total_sold} units sold in total."
        return "No sales recorded yet."

    asks_slow_mover = any(
        phrase in normalized_question for phrase in ("slow moving", "least sold", "worst selling")
    )
    if asks_slow_mover:
        result = db.query(
            Medicine.name, func.sum(SaleHistory.quantity_sold).label("total_sold")
        ).join(
            Medicine, Medicine.medicine_id == SaleHistory.medicine_id
        ).filter(Medicine.is_active.is_(True)
        ).group_by(Medicine.name).order_by(func.sum(SaleHistory.quantity_sold).asc()).first()
        if result:
            return f"The slowest-moving medicine is {result.name}, with only {result.total_sold} units sold."
        return "No sales recorded yet."

    asks_average_sale = "average sale" in normalized_question or "average revenue" in normalized_question
    if asks_average_sale:
        avg_amount = db.query(func.coalesce(func.avg(SaleHistory.total_amount), 0)).scalar()
        return f"The average sale value is ₹{float(avg_amount):,.2f}."

    asks_sales_count = (
        ("how many sales" in normalized_question or "total sales" in normalized_question or "number of sales" in normalized_question)
        and "return" not in normalized_question
    )
    if asks_sales_count:
        count = db.query(SaleHistory).count()
        return f"There have been {count} sales recorded in total."

    # ---- Returns ----
    asks_customer_return_count = "customer return" in normalized_question and any(
        phrase in normalized_question for phrase in ("how many", "total", "number")
    )
    if asks_customer_return_count:
        total = db.query(
            func.coalesce(func.sum(Return.quantity), 0)
        ).filter(Return.return_type == "customer").scalar()
        return f"A total of {int(total)} units have been returned by customers."

    asks_supplier_return_count = "supplier return" in normalized_question and any(
        phrase in normalized_question for phrase in ("how many", "total", "number")
    )
    if asks_supplier_return_count:
        total = db.query(
            func.coalesce(func.sum(Return.quantity), 0)
        ).filter(Return.return_type == "supplier").scalar()
        return f"A total of {int(total)} units have been returned to suppliers."

    # ---- Inventory totals ----
    asks_medicine_count = any(
        phrase in normalized_question for phrase in ("how many medicines", "total medicines", "number of medicines")
    )
    if asks_medicine_count:
        count = db.query(Medicine).filter(Medicine.is_active.is_(True)).count()
        return f"There are currently {count} active medicines in the system."

    asks_total_stock = (
        ("total stock" in normalized_question or "how much stock" in normalized_question)
        and "medicine" not in normalized_question
    )
    if asks_total_stock:
        total = db.query(
            func.coalesce(func.sum(InventoryBatch.quantity), 0)
        ).join(Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
        ).filter(Medicine.is_active.is_(True)).scalar()
        return f"Total stock across all active medicines: {int(total):,} units."

    asks_out_of_stock_list = "out of stock" in normalized_question and any(
        phrase in normalized_question for phrase in ("how many", "which", "list")
    )
    if asks_out_of_stock_list:
        stock_by_medicine = db.query(
            InventoryBatch.medicine_id,
            func.coalesce(func.sum(InventoryBatch.quantity), 0).label("stock")
        ).group_by(InventoryBatch.medicine_id).subquery()
        results = db.query(Medicine.name).join(
            stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
        ).filter(
            stock_by_medicine.c.stock == 0, Medicine.is_active.is_(True)
        ).order_by(Medicine.name).all()

        if not results:
            return "No active medicines are currently out of stock."

        lines = ["Medicines out of stock:"]
        for index, item in enumerate(results, start=1):
            lines.append(f"{index}. {item.name}")
        lines.append(f"Total out of stock: {len(results)}")
        return "\n".join(lines)

    asks_highest_stock = "highest stock" in normalized_question or "most stock" in normalized_question
    if asks_highest_stock:
        result = db.query(
            Medicine.name, func.sum(InventoryBatch.quantity).label("stock")
        ).join(
            InventoryBatch, InventoryBatch.medicine_id == Medicine.medicine_id
        ).filter(Medicine.is_active.is_(True)
        ).group_by(Medicine.name).order_by(func.sum(InventoryBatch.quantity).desc()).first()
        if result:
            return f"{result.name} has the highest stock, with {result.stock} units."

    # ---- Running out / expiry ----
    asks_running_out_first = any(
        phrase in normalized_question for phrase in ("run out", "running out")
    ) and any(
        phrase in normalized_question for phrase in ("first", "soonest", "which medicine")
    )
    if asks_running_out_first:
        insights = get_ai_insights(db)
        if insights["running_out_names"]:
            return f"{insights['running_out_names'][0]} is the medicine most likely to run out first."
        return "No medicines are currently projected to run out soon."

    asks_expiring_this_week = "expir" in normalized_question and "this week" in normalized_question
    if asks_expiring_this_week:
        limit = today + timedelta(days=7)
        count = db.query(InventoryBatch).join(
            Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
        ).filter(
            Medicine.is_active.is_(True),
            InventoryBatch.expiry_date >= today,
            InventoryBatch.expiry_date <= limit,
            InventoryBatch.quantity > 0
        ).count()
        return f"{count} batch(es) are expiring within the next 7 days."

    asks_healthy_percentage = "healthy" in normalized_question and any(
        phrase in normalized_question for phrase in ("percentage", "%", "stock level")
    )
    if asks_healthy_percentage:
        insights = get_ai_insights(db)
        return f"{insights['healthy_percentage']}% of current stock is in a healthy state."

    # ---- Category breakdown ----
    asks_top_category = "most medicines" in normalized_question and "category" in normalized_question
    if asks_top_category:
        result = db.query(
            Medicine.category, func.count(Medicine.medicine_id).label("count")
        ).filter(Medicine.is_active.is_(True)
        ).group_by(Medicine.category).order_by(func.count(Medicine.medicine_id).desc()).first()
        if result:
            return f"{result.category} has the most medicines, with {result.count} distinct items."

    return None  # nothing matched — falls through to Gemini

@app.get("/ai/insights")
def get_ai_insights(db: Session = Depends(get_db), _: int = Depends(require_admin)):
    today = date.today()
    SALES_LOOKBACK_DAYS = 90
    RUNNING_OUT_THRESHOLD_DAYS = 7

    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("current_stock")
    ).filter(InventoryBatch.expiry_date >= today).group_by(InventoryBatch.medicine_id).subquery()

    cutoff = today - timedelta(days=SALES_LOOKBACK_DAYS)
    sales_by_medicine = db.query(
        SaleHistory.medicine_id,
        func.sum(SaleHistory.quantity_sold).label("total_sold")
    ).filter(SaleHistory.sale_date >= cutoff).group_by(SaleHistory.medicine_id).subquery()

    demand_results = db.query(
        Medicine.medicine_id, Medicine.name,
        stock_by_medicine.c.current_stock,
        sales_by_medicine.c.total_sold
    ).outerjoin(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).outerjoin(
        sales_by_medicine, Medicine.medicine_id == sales_by_medicine.c.medicine_id
    ).all()

    running_out_names = []
    for r in demand_results:
        current_stock = r.current_stock or 0
        avg_daily_sales = (r.total_sold or 0) / SALES_LOOKBACK_DAYS
        if avg_daily_sales > 0 and (current_stock / avg_daily_sales) < RUNNING_OUT_THRESHOLD_DAYS:
            running_out_names.append(r.name)

    expiring_count = db.query(InventoryBatch).filter(
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= today + timedelta(days=60)
    ).count()

    batch_results = db.query(
        InventoryBatch.quantity, InventoryBatch.expiry_date, Medicine.reorder_level
    ).join(Medicine, Medicine.medicine_id == InventoryBatch.medicine_id).all()

    total_batches = len(batch_results)
    healthy_count = 0
    for b in batch_results:
        days_left = (b.expiry_date - today).days
        if b.quantity == 0:
            status = "Out of Stock"
        elif days_left < 0:
            status = "Expired"
        elif days_left <= 60:
            status = "Expiring Soon"
        elif b.quantity < b.reorder_level:
            status = "Low Stock"
        else:
            status = "Healthy"
        if status == "Healthy":
            healthy_count += 1

    healthy_percentage = round((healthy_count / total_batches) * 100, 1) if total_batches > 0 else 0

    return {
        "running_out_count": len(running_out_names),
        "running_out_names": running_out_names,
        "expiring_soon_count": expiring_count,
        "healthy_percentage": healthy_percentage
    }

@app.post("/ai/ask")
def ask_ai(data: AskRequest, db: Session = Depends(get_db), _: int = Depends(require_admin)):
    requirement_data = get_stock_requirement(db)
    sales_returns_answer = build_sales_returns_answer(data.question, db)
    if sales_returns_answer:
        return {"answer": sales_returns_answer}

    low_stock_answer = build_low_stock_answer(data.question, db)
    if low_stock_answer:
        return {"answer": low_stock_answer}

    expiring_answer = build_expiring_medicines_answer(data.question, db)
    if expiring_answer:
        return {"answer": expiring_answer}

    local_answer = build_total_reorder_cost_answer(data.question, requirement_data)
    if local_answer:
        return {"answer": local_answer}

    budget_answer = build_budget_reorder_answer(data.question, requirement_data)
    if budget_answer:
        return {"answer": budget_answer}

    full_reorder_answer = build_full_reorder_list_answer(data.question, requirement_data)
    if full_reorder_answer:
        return {"answer": full_reorder_answer}

    extended_answer = build_extended_answers(data.question, db, data.history)
    if extended_answer:
        return {"answer": extended_answer}

    normalized_question = data.question.lower()

# Combine current question with the last question in history so a bare
# follow-up ("and their price", "which?") inherits domain keywords
# from what was actually being discussed.
    determination_text = normalized_question
    if data.history:
        determination_text = data.history[-1].get("question", "").lower() + " " + normalized_question

    wants_inventory = any(word in determination_text for word in ("stock", "medicine", "batch", "inventory", "price", "cost"))
    wants_sales = "sale" in determination_text or "revenue" in determination_text
    wants_returns = "return" in determination_text
    wants_expiry = "expir" in determination_text or "expiry" in determination_text
    wants_insights = any(word in determination_text for word in ("running out", "healthy", "insight", "trend"))

# Only fall back to "send everything" if there's truly no history AND no keywords at all
    if not any((wants_inventory, wants_sales, wants_returns, wants_expiry, wants_insights)) and not data.history:
        wants_inventory = True
        wants_insights = True

    sections = [
        "You are an assistant inside Medistock, a pharmacy inventory system.",
        "Answer using ONLY the supplied data. Be concise, practical, and use the same language as the question.",
        "If the question contains words like 'it', 'their', 'each', 'the same', or otherwise reads as a follow-up, "
        "resolve what it refers to using RECENT CONVERSATION below — do not answer about the entire dataset "
        "unless the question or the conversation clearly asks for everything.",
        "When resolving a follow-up question (e.g. containing 'their', 'it', 'the same', 'which'), "
        "only use the entity discussed in RECENT CONVERSATION — never substitute a different list "
        "of medicines from other data sections just because it's shorter or more specific."

    ]


    if wants_inventory:
        inventory_data = []
        medicines = db.query(Medicine).filter(Medicine.is_active.is_(True)).order_by(Medicine.name).all()
        for medicine in medicines:
            batches = db.query(InventoryBatch).filter(
                InventoryBatch.medicine_id == medicine.medicine_id
            ).order_by(InventoryBatch.expiry_date).all()
            inventory_data.append({
                "name": medicine.name,
                "category": medicine.category,
                "unit": medicine.unit,
                "unit_price": float(medicine.unit_price),
                "reorder_level": medicine.reorder_level,
                "batches": [
                    {
                        "batch_number": batch.batch_number,
                        "quantity": batch.quantity,
                        "expiry_date": batch.expiry_date.isoformat()
                    }
                    for batch in batches
                ]
            })
        sections.append(f"ACTIVE INVENTORY (medicine and batch data):\n{json.dumps(inventory_data, ensure_ascii=False)}")

    if wants_sales:
        sales_data = [
            {
                "medicine": medicine_name,
                "quantity_sold": sale.quantity_sold,
                "sale_date": sale.sale_date.isoformat(),
                "total_amount": float(sale.total_amount)
            }
            for sale, medicine_name in db.query(SaleHistory, Medicine.name).join(
                Medicine, Medicine.medicine_id == SaleHistory.medicine_id
            ).order_by(SaleHistory.sale_date.desc()).limit(200).all()
        ]
        sections.append(f"RECENT SALES (maximum 200 records):\n{json.dumps(sales_data, ensure_ascii=False)}")

    if wants_returns:
        returns_data = [
            {
                "medicine": medicine_name,
                "quantity": item.quantity,
                "return_type": item.return_type,
                "reason": item.reason,
                "return_date": item.return_date.isoformat()
            }
            for item, medicine_name in db.query(Return, Medicine.name).join(
                Medicine, Medicine.medicine_id == Return.medicine_id
            ).order_by(Return.return_date.desc()).limit(200).all()
        ]
        sections.append(f"RECENT RETURNS (maximum 200 records):\n{json.dumps(returns_data, ensure_ascii=False)}")

    if wants_expiry:
        expiry_limit = date.today() + timedelta(days=90)
        expiring_data = [
            {
                "medicine": medicine_name,
                "batch_number": batch.batch_number,
                "quantity": batch.quantity,
                "expiry_date": batch.expiry_date.isoformat()
            }
            for batch, medicine_name in db.query(InventoryBatch, Medicine.name).join(
                Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
            ).filter(
                Medicine.is_active.is_(True),
                InventoryBatch.quantity > 0,
                InventoryBatch.expiry_date >= date.today(),
                InventoryBatch.expiry_date <= expiry_limit
            ).order_by(InventoryBatch.expiry_date).all()
        ]
        sections.append(f"EXPIRING ACTIVE STOCK (next 90 days):\n{json.dumps(expiring_data, ensure_ascii=False)}")

    if wants_insights:
        sections.append(f"CURRENT INSIGHTS:\n{json.dumps(get_ai_insights(db), ensure_ascii=False)}")

    if wants_inventory or "reorder" in normalized_question:
        sections.append(f"STOCK REQUIREMENTS:\n{json.dumps(requirement_data, ensure_ascii=False)}")

    if data.history:
        history_lines = ["RECENT CONVERSATION (use this to resolve follow-ups like 'which?', 'their', 'each'):"]
        for turn in data.history[-4:]:
            history_lines.append(f"Q: {turn.get('question', '')}")
            history_lines.append(f"A: {turn.get('answer', '')}")
        sections.append("\n".join(history_lines))

    sections.append(f"ADMIN'S CURRENT QUESTION: {data.question}")

    context = "\n\n".join(sections)
    if len(context) > 100000:
        context = context[:100000] + "\n[Additional records omitted because the context limit was reached.]"
    print(f"[DEBUG] AI_PROVIDER is set to: '{AI_PROVIDER}'")
    if AI_PROVIDER == "ollama":
        try:
            return {"answer": generate_with_ollama(context)}
        except Exception as error:
            logger.exception("Ollama request failed")
            raise HTTPException(status_code=503, detail=str(error)) from error

    if not gemini_client:
        raise HTTPException(status_code=503, detail="AI service is not configured. Add GEMINI_API_KEY to the environment.")

    models_to_try = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models_to_try.append(GEMINI_FALLBACK_MODEL)

    for model_index, model in enumerate(models_to_try):
        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=context
            )
            return {"answer": response.text}
        except Exception as error:
            error_text = str(error).lower()
            logger.exception("Gemini request failed for model %s", model)
            is_rate_limited = "429" in error_text or "rate limit" in error_text or "quota" in error_text
            is_temporary = "503" in error_text or "unavailable" in error_text
            if (is_temporary or is_rate_limited) and model_index < len(models_to_try) - 1:
                time.sleep(1.5)
                continue
            if is_rate_limited:
                raise HTTPException(
                    status_code=429,
                    detail="The AI service quota is temporarily exhausted. Please try again later or configure a fallback model."
                )
            if is_temporary:
                raise HTTPException(
                    status_code=503,
                    detail="The AI service is temporarily busy. Please try again in a moment."
                )
            raise HTTPException(status_code=500, detail="AI service error. Please try again later.")


    