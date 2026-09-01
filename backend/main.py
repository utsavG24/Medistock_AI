from sqlalchemy import func
from datetime import date, timedelta
from models import Medicine, InventoryBatch, Admin, Return, SaleHistory
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal
from starlette.middleware.sessions import SessionMiddleware
import bcrypt
from pydantic import BaseModel, field_validator
import re
from fastapi import Request, HTTPException


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key="change-this-to-something-random-later")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

class SignupRequest(BaseModel):
    username: str
    password: str
    full_name: str

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

class CustomerReturnRequest(BaseModel):
    batch_id: int
    quantity: int
    reason: str | None = None

class SupplierReturnRequest(BaseModel):
    batch_id: int
    quantity: int
    quantity_received: int = 0
    reason: str | None = None

@app.get("/medicines")
def get_medicines(db: Session = Depends(get_db)):
    return db.query(Medicine).all()

@app.get("/dashboard/summary")
def get_summary(db: Session = Depends(get_db)):
    total_medicines = db.query(Medicine).count()
    total_stock = db.query(func.sum(InventoryBatch.quantity)).scalar() or 0

    # stock per medicine (summed across all its batches)
    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("stock")
    ).group_by(InventoryBatch.medicine_id).subquery()

    low_stock_count = db.query(Medicine).join(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).filter(stock_by_medicine.c.stock < Medicine.reorder_level).count()

    today = date.today()
    expiring_count = db.query(InventoryBatch).filter(
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= today + timedelta(days=60)
    ).count()

    return {
        "total_medicines": total_medicines,
        "total_stock": total_stock,
        "low_stock_count": low_stock_count,
        "expiring_soon_count": expiring_count
    }
@app.get("/stock/low")
def get_low_stock(db: Session = Depends(get_db)):
    stock_by_medicine = db.query(
        InventoryBatch.medicine_id,
        func.sum(InventoryBatch.quantity).label("stock")
    ).group_by(InventoryBatch.medicine_id).subquery()

    results = db.query(
        Medicine.name, Medicine.category, Medicine.reorder_level,
        stock_by_medicine.c.stock
    ).join(
        stock_by_medicine, Medicine.medicine_id == stock_by_medicine.c.medicine_id
    ).filter(stock_by_medicine.c.stock < Medicine.reorder_level).all()

    return [
        {"name": r.name, "category": r.category, "current_stock": r.stock, "reorder_level": r.reorder_level}
        for r in results
    ]
@app.get("/stock/expiring")
def get_expiring_stock(db: Session = Depends(get_db)):
    today = date.today()
    results = db.query(
        Medicine.name, Medicine.category,
        InventoryBatch.batch_number, InventoryBatch.quantity, InventoryBatch.expiry_date
    ).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).filter(
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= today + timedelta(days=60)
    ).order_by(InventoryBatch.expiry_date).all()

    return [
        {
            "name": r.name,
            "category": r.category,
            "batch_number": r.batch_number,
            "quantity": r.quantity,
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
        InventoryBatch.quantity, InventoryBatch.expiry_date,
        Medicine.reorder_level
    ).join(
        Medicine, Medicine.medicine_id == InventoryBatch.medicine_id
    ).order_by(InventoryBatch.expiry_date).all()

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
            "reorder_level": r.reorder_level,
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
        full_name=data.full_name
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
    return {"message": "Login successful", "full_name": admin.full_name}


@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}


@app.get("/auth/me")
def get_current_admin(request: Request):
    if "admin_id" not in request.session:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"full_name": request.session["full_name"]}

@app.post("/sales")
def sell_stock(data: SellRequest, db: Session = Depends(get_db)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    if batch.quantity < data.quantity:
        raise HTTPException(status_code=400, detail=f"Only {batch.quantity} units available in this batch")

    medicine = db.query(Medicine).filter(Medicine.medicine_id == batch.medicine_id).first()

    batch.quantity -= data.quantity

    sale = SaleHistory(
        medicine_id=batch.medicine_id,
        quantity_sold=data.quantity,
        sale_date=date.today(),
        unit_price=medicine.unit_price,
        total_amount=round(float(medicine.unit_price) * data.quantity, 2)
    )
    db.add(sale)
    db.commit()
    return {"message": f"Sold {data.quantity} units", "remaining_stock": batch.quantity}


@app.post("/returns/customer")
def customer_return(data: CustomerReturnRequest, db: Session = Depends(get_db)):
    batch = db.query(InventoryBatch).filter(InventoryBatch.batch_id == data.batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

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
        SaleHistory.total_amount, Medicine.name
    ).join(
        Medicine, Medicine.medicine_id == SaleHistory.medicine_id
    ).all()

    returns = db.query(
        Return.return_id, Return.quantity, Return.return_date,
        Return.return_type, Return.reason, Medicine.name
    ).join(
        Medicine, Medicine.medicine_id == Return.medicine_id
    ).all()

    transactions = []

    for s in sales:
        transactions.append({
            "type": "Sale",
            "medicine_name": s.name,
            "quantity": s.quantity_sold,
            "date": s.sale_date.isoformat(),
            "amount": float(s.total_amount),
            "reason": None
        })

    for r in returns:
        transactions.append({
            "type": "Customer Return" if r.return_type == "customer" else "Supplier Return",
            "medicine_name": r.name,
            "quantity": r.quantity,
            "date": r.return_date.isoformat(),
            "amount": None,
            "reason": r.reason
        })

    transactions.sort(key=lambda t: t["date"], reverse=True)
    return transactions