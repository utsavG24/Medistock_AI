from sqlalchemy import Column, Integer, String, Numeric, Date, ForeignKey
from database import Base

class Medicine(Base):
    __tablename__ = "medicines"
    medicine_id = Column(Integer, primary_key=True)
    name = Column(String)
    category = Column(String)
    manufacturer = Column(String)
    unit = Column(String)
    unit_price = Column(Numeric)
    reorder_level = Column(Integer)

class InventoryBatch(Base):
    __tablename__ = "inventory_batches"
    batch_id = Column(Integer, primary_key=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id"))
    batch_number = Column(String)
    quantity = Column(Integer)
    manufacture_date = Column(Date)
    expiry_date = Column(Date)

class SaleHistory(Base):
    __tablename__ = "sales_history"
    sale_id = Column(Integer, primary_key=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id"))
    quantity_sold = Column(Integer)
    sale_date = Column(Date)
    unit_price = Column(Numeric)
    total_amount = Column(Numeric)
from sqlalchemy import DateTime
from datetime import datetime, timezone

class Admin(Base):
    __tablename__ = "admins"
    admin_id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="Pharmacy Manager")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Return(Base):
    __tablename__ = "returns"
    return_id = Column(Integer, primary_key=True)
    medicine_id = Column(Integer, ForeignKey("medicines.medicine_id"))
    batch_id = Column(Integer, ForeignKey("inventory_batches.batch_id"))
    quantity = Column(Integer)
    return_type = Column(String)
    reason = Column(String)
    return_date = Column(Date)