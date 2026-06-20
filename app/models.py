import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, Numeric, Boolean, DateTime, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class OCRDocument(Base):
    __tablename__ = "ocr_documents"

    ocr_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_type = Column(String(100), nullable=False)
    raw_text = Column(Text, nullable=False)
    extracted_json = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    confidence_score = Column(Float, nullable=True)
    document_hash = Column(String(64), nullable=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    processing_status = Column(String(50), nullable=False)
    rejection_reason = Column(Text, nullable=True)


class Product(Base):
    __tablename__ = "products"

    product_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku = Column(String(100), unique=True, index=True)
    product_name = Column(String(255))
    category_id = Column(UUID(as_uuid=True), nullable=True)
    weight = Column(Numeric(10, 2), nullable=True)
    is_hazardous = Column(Boolean, default=False)
    is_fragile = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Optional relationships to help querying if needed
    dimensions = relationship("ProductDimension", back_populates="product", uselist=False)
    storage_rule = relationship("ProductStorageRule", back_populates="product", uselist=False)


class ProductDimension(Base):
    __tablename__ = "product_dimensions"

    dimension_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.product_id"), unique=True)
    length = Column(Numeric(10, 2), nullable=True)
    width = Column(Numeric(10, 2), nullable=True)
    height = Column(Numeric(10, 2), nullable=True)
    volume = Column(Numeric(10, 2), nullable=True)
    
    box_length = Column(Numeric(10, 2), nullable=True)
    box_width = Column(Numeric(10, 2), nullable=True)
    box_height = Column(Numeric(10, 2), nullable=True)
    box_volume = Column(Numeric(10, 2), nullable=True)

    product = relationship("Product", back_populates="dimensions")


class ProductStorageRule(Base):
    __tablename__ = "product_storage_rules"

    rule_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.product_id"), unique=True)
    allowed_zone_type = Column(String(50), nullable=True)
    max_stack_height = Column(Integer, nullable=True)
    required_temperature = Column(Numeric(10, 2), nullable=True)
    orientation_rule = Column(String(50), nullable=True)

    product = relationship("Product", back_populates="storage_rule")
