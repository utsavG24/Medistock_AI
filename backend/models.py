from sqlalchemy import Boolean, Column, Integer, String, Numeric, Date, ForeignKey

try:
    from .database import Base
except ImportError:  # pragma: no cover
    from database import Base

class Medicine(Base):
    __tablename__ = "medicines"
    medicine_id = Column(Integer, primary_key=True)
    name = Column(String)
    category = Column(String)
    manufacturer = Column(String)
    unit = Column(String)
    units_per_strip = Column(Integer, nullable=False, default=1, server_default="1")
    unit_price = Column(Numeric)
    price_basis = Column(String, nullable=False, default="unit", server_default="unit")
    reorder_level = Column(Integer)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

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
    batch_id = Column(Integer, ForeignKey("inventory_batches.batch_id"), nullable=True)
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
    pharmacy_name = Column(String, nullable=True)
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