# db/models.py

from sqlalchemy import Column, Integer, String, Date, Time , ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # Reverse relationship
    appointments = relationship("Appointment", back_populates="customer")
    
    
class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    stylist_id = Column(Integer, ForeignKey("stylists.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)

    # Relationships
    customer = relationship("Customer", back_populates="appointments")
    stylist = relationship("Stylist", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
    
    
    
class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration = Column(Integer, nullable=True)  # Duration in minutes
    price = Column(Integer, nullable=True)     # Price in cents or dollars
    description = Column(String, nullable=True)

    # Reverse relationship
    appointments = relationship("Appointment", back_populates="service")
    
    
class Stylist(Base):
    __tablename__ = "stylists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    expertise = Column(String, nullable=True)
    rating = Column(Integer, nullable=True)
    availability = Column(String, nullable=True)

    # Reverse relationship
    appointments = relationship("Appointment", back_populates="stylist")
