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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

class AskRequest(BaseModel):
    question: str

@app.get("/medicines")
def get_medicines(db: Session = Depends(get_db), _: int = Depends(require_admin)):
    medicines = db.query(Medicine).order_by(Medicine.name).all()
    output = []
    for medicine in medicines:
        batches = db.query(InventoryBatch).filter(
            InventoryBatch.medicine_id == medicine.medicine_id
        ).order_by(InventoryBatch.expiry_date).all()
        sales_count = db.query(SaleHistory).filter(
            SaleHistory.medicine_id == medicine.medicine_id
        ).count()
        returns_count = db.query(Return).filter(
            Return.medicine_id == medicine.medicine_id
        ).count()
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
            "total_stock": sum(batch.quantity for batch in batches),
            "batch_count": len(batches),
            "sales_count": sales_count,
            "returns_count": returns_count,
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "batch_number": batch.batch_number,
                    "quantity": batch.quantity,
                    "manufacture_date": batch.manufacture_date.isoformat(),
                    "expiry_date": batch.expiry_date.isoformat()
                }
                for batch in batches
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
    insights = get_ai_insights(db)
    requirement_data = get_stock_requirement(db)
    low_stock_data = get_low_stock(db)

    medicines = db.query(Medicine).order_by(Medicine.name).all()
    inventory_data = []
    for medicine in medicines:
        batches = db.query(InventoryBatch).filter(
            InventoryBatch.medicine_id == medicine.medicine_id
        ).order_by(InventoryBatch.expiry_date).all()
        inventory_data.append({
            "medicine_id": medicine.medicine_id,
            "name": medicine.name,
            "category": medicine.category,
            "manufacturer": medicine.manufacturer,
            "unit": medicine.unit,
            "unit_price": float(medicine.unit_price),
            "reorder_level": medicine.reorder_level,
            "is_active": medicine.is_active,
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "batch_number": batch.batch_number,
                    "quantity": batch.quantity,
                    "manufacture_date": batch.manufacture_date.isoformat(),
                    "expiry_date": batch.expiry_date.isoformat()
                }
                for batch in batches
            ]
        })

    sales_data = [
        {
            "sale_id": sale.sale_id,
            "medicine_id": sale.medicine_id,
            "batch_id": sale.batch_id,
            "quantity_sold": sale.quantity_sold,
            "sale_date": sale.sale_date.isoformat(),
            "unit_price": float(sale.unit_price),
            "total_amount": float(sale.total_amount)
        }
        for sale in db.query(SaleHistory).order_by(SaleHistory.sale_date.desc()).all()
    ]
    returns_data = [
        {
            "return_id": item.return_id,
            "medicine_id": item.medicine_id,
            "batch_id": item.batch_id,
            "quantity": item.quantity,
            "return_type": item.return_type,
            "reason": item.reason,
            "return_date": item.return_date.isoformat()
        }
        for item in db.query(Return).order_by(Return.return_date.desc()).all()
    ]

    context = f"""You are an assistant inside Medistock, a pharmacy inventory system.
Answer the pharmacy administrator's question using ONLY the complete data below.
Use every relevant record available. Do not say that details are unavailable when they exist in the data.
Show full information requested by the administrator, including all matching medicine names, batches, quantities, dates, sales, returns, and costs.
Do not arbitrarily limit lists to a few items. Be clear and practical, and respond in the SAME language as the question.

CURRENT SUMMARY:
{json.dumps(insights, ensure_ascii=False)}

COMPLETE MEDICINE AND BATCH DATA:
{json.dumps(inventory_data, ensure_ascii=False)}

COMPLETE STOCK REQUIREMENT DATA:
{json.dumps(requirement_data, ensure_ascii=False)}

COMPLETE LOW STOCK DATA:
{json.dumps(low_stock_data, ensure_ascii=False)}

COMPLETE SALES HISTORY:
{json.dumps(sales_data, ensure_ascii=False)}

COMPLETE RETURNS HISTORY:
{json.dumps(returns_data, ensure_ascii=False)}

ADMIN'S QUESTION: {data.question}
"""

    if not gemini_client:
        raise HTTPException(status_code=503, detail="AI service is not configured. Add GEMINI_API_KEY to the environment.")

    for attempt in range(2):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=context
            )
            return {"answer": response.text}
        except Exception as error:
            error_text = str(error).lower()
            is_temporary = "503" in error_text or "unavailable" in error_text
            if is_temporary and attempt == 0:
                time.sleep(1.5)
                continue
            if is_temporary:
                raise HTTPException(
                    status_code=503,
                    detail="The AI service is temporarily busy. Please try again in a moment."
                )
            raise HTTPException(status_code=500, detail="AI service error. Please try again later.")


    