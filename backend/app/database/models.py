from sqlalchemy import Text
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, nullable=False, default=True, server_default="true")
    verification_token_hash = Column(String(64), nullable=True)
    verification_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # A user can own multiple workspaces
    workspaces = relationship(
        "Workspace",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)

    # Each workspace belongs to one user
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(String(30), default="stopped", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    owner = relationship("User", back_populates="workspaces")

class UserDevice(Base):
    __tablename__ = "user_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    device_name = Column(String(150), nullable=False)
    operating_system = Column(String(50), nullable=False)
    device_token_hash = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", backref="devices")


class DevicePairing(Base):
    __tablename__ = "device_pairings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User")
