from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.vehicle import Vehicle
from schemas.user import (
    DriverApplyRequest,
    DriverVerifyRequest,
    UserResponse,
    UserUpdate,
)
from services.clerk_service import sync_clerk_user_metadata
from utils.auth_utils import get_current_admin_user, get_current_user

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Return the application profile for the authenticated Clerk user."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update editable application profile fields."""
    if user_update.email is not None and user_update.email != current_user.email:
        existing_user = db.query(User).filter(User.email == user_update.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = user_update.email

    if user_update.name is not None:
        current_user.name = user_update.name
    if user_update.phone is not None:
        current_user.phone = user_update.phone

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/driver/apply", response_model=UserResponse)
def apply_for_driver(
    apply_in: DriverApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit application to become a driver.
    Role changes to 'driver' with 'pending_verification' status until verified by an admin.
    """
    current_user.role = "driver"
    current_user.driver_status = "pending_verification"

    plate = apply_in.license_plate.strip().upper()
    existing_vehicle = db.query(Vehicle).filter(Vehicle.driver_user_id == current_user.id).first()
    if not existing_vehicle:
        duplicate_plate = db.query(Vehicle).filter(Vehicle.license_plate == plate).first()
        if duplicate_plate:
            raise HTTPException(
                status_code=400,
                detail=f"Vehicle license plate '{plate}' is already registered.",
            )
        new_vehicle = Vehicle(
            license_plate=plate,
            capacity=apply_in.capacity or 4,
            status="offline",
            driver_user_id=current_user.id,
        )
        db.add(new_vehicle)
    else:
        existing_vehicle.license_plate = plate
        if apply_in.capacity:
            existing_vehicle.capacity = apply_in.capacity

    db.commit()
    db.refresh(current_user)

    if current_user.clerk_user_id:
        sync_clerk_user_metadata(
            current_user.clerk_user_id,
            {"role": "driver", "driver_status": "pending_verification"},
        )

    return current_user


@router.get("/drivers/pending", response_model=List[UserResponse])
def list_pending_drivers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List all drivers currently pending admin verification."""
    return (
        db.query(User)
        .filter(User.role == "driver", User.driver_status == "pending_verification")
        .order_by(User.id.desc())
        .all()
    )


@router.post("/driver/{user_id}/verify", response_model=UserResponse)
def verify_driver(
    user_id: int,
    verify_in: DriverVerifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Verify and approve or reject a driver's pending application. Admin only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = "driver"
    target.driver_status = verify_in.status or "active"
    db.commit()
    db.refresh(target)

    if target.clerk_user_id:
        sync_clerk_user_metadata(
            target.clerk_user_id,
            {"role": "driver", "driver_status": target.driver_status},
        )

    return target


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote or demote a user's application role. Admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can change user roles.")

    allowed_roles = {"passenger", "driver", "admin"}
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(allowed_roles))}")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = role
    if role == "driver" and not target.driver_status:
        target.driver_status = "active"
    db.commit()
    db.refresh(target)

    if target.clerk_user_id:
        sync_clerk_user_metadata(
            target.clerk_user_id,
            {"role": target.role, "driver_status": target.driver_status},
        )

    return target
