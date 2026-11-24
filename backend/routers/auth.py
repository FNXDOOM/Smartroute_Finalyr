from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from models.vehicle import Vehicle
from schemas.user import (
    DriverApplyRequest,
    DriverVerifyRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from services.clerk_service import sync_clerk_user_metadata
from utils.auth_utils import (
    create_local_token,
    get_current_admin_user,
    get_current_user,
    hash_password,
    normalize_email,
    verify_password,
)
from utils.ride_states import VEHICLE_OFFLINE, VEHICLE_IDLE
from utils.ride_scope import LIVE_MODE

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_local_user(register_in: UserRegister, db: Session = Depends(get_db)):
    """Mobile signup; always passenger."""
    email = normalize_email(register_in.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email must not be empty.")
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    name = register_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name must not be empty.")
    user = User(
        name=name,
        email=email,
        phone=(register_in.phone or "").strip(),
        password_hash=hash_password(register_in.password),
        role="passenger",
        driver_status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_local_token(user.id),
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login_local_user(login_in: UserLogin, db: Session = Depends(get_db)):
    """Mobile login."""
    email = normalize_email(login_in.email)
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or not verify_password(login_in.password, user.password_hash or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(
        access_token=create_local_token(user.id),
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Current user profile."""
    return current_user


@router.post("/driver/presence", response_model=UserResponse)
def update_driver_presence(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record that an active driver has the driver app open."""
    if current_user.role != "driver":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver access required")
    if current_user.driver_status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver is not active")
    current_user.driver_last_seen_at = datetime.now(timezone.utc)
    # Opening the approved driver's app makes their unassigned live vehicle
    # available. Never reset an active route or touch presentation vehicles.
    db.query(Vehicle).filter(
        Vehicle.driver_user_id == current_user.id,
        Vehicle.mode == LIVE_MODE,
        Vehicle.status == VEHICLE_OFFLINE,
        Vehicle.assigned_route_id.is_(None),
    ).update({Vehicle.status: VEHICLE_IDLE}, synchronize_session="fetch")
    db.commit()
    db.refresh(current_user)
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update profile fields."""
    if user_update.email is not None:
        email = normalize_email(user_update.email)
        if not email:
            raise HTTPException(status_code=400, detail="Email must not be empty.")
        if email != normalize_email(current_user.email):
            # Email is a recovery + identity credential: changing it needs
            # step-up auth. Clerk-managed accounts own their email at the IdP.
            if not current_user.password_hash:
                raise HTTPException(
                    status_code=400,
                    detail="Email is managed by your sign-in provider and cannot be changed here.",
                )
            if not user_update.current_password or not verify_password(
                user_update.current_password, current_user.password_hash
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Current password is required to change your email.",
                )
            existing_user = (
                db.query(User)
                .filter(func.lower(User.email) == email, User.id != current_user.id)
                .first()
            )
            if existing_user:
                raise HTTPException(status_code=400, detail="Email already registered")
            current_user.email = email

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
    """Apply for driver role."""
    plate = apply_in.license_plate.strip().upper()
    if not plate:
        raise HTTPException(status_code=400, detail="Vehicle license plate must not be empty.")

    preserve_review_status = (
        current_user.role == "driver" and current_user.driver_status in {"active", "suspended"}
    )
    current_user.role = "driver"
    if not preserve_review_status:
        # New applicants need review; reapplying must not change approval or suspension.
        current_user.driver_status = "pending_verification"

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
            status=VEHICLE_OFFLINE,
            driver_user_id=current_user.id,
        )
        db.add(new_vehicle)
    else:
        duplicate_plate = (
            db.query(Vehicle)
            .filter(Vehicle.license_plate == plate, Vehicle.id != existing_vehicle.id)
            .first()
        )
        if duplicate_plate:
            raise HTTPException(
                status_code=400,
                detail=f"Vehicle license plate '{plate}' is already registered.",
            )
        existing_vehicle.license_plate = plate
        if apply_in.capacity:
            existing_vehicle.capacity = apply_in.capacity

    db.commit()
    db.refresh(current_user)

    if current_user.clerk_user_id:
        # Mirror the committed review state, including profile edits by approved drivers.
        sync_clerk_user_metadata(
            current_user.clerk_user_id,
            {
                "role": "pending" if current_user.driver_status == "pending_verification" else current_user.role,
                "driver_status": current_user.driver_status,
                "license_plate": plate,
            },
        )

    return current_user


@router.get("/drivers/pending", response_model=List[UserResponse])
def list_pending_drivers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """List pending drivers."""
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
    """Approve/reject driver. Admin only."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    decision = verify_in.status or "active"
    target.driver_status = decision
    if decision == "active":
        target.role = "driver"
    elif decision == "rejected" and target.role == "driver":
        # A declined application must not leave the applicant holding the role.
        target.role = "passenger"
    # `suspended` keeps the role so an admin can reinstate it; every driver endpoint refuses the account while the status says so.
    db.commit()
    db.refresh(target)

    if target.clerk_user_id:
        # Sync confirmed driver state.
        vehicle = db.query(Vehicle).filter(Vehicle.driver_user_id == target.id).first()
        confirmed_metadata = {"role": target.role, "driver_status": target.driver_status}
        if vehicle:
            confirmed_metadata["license_plate"] = vehicle.license_plate
        sync_clerk_user_metadata(target.clerk_user_id, confirmed_metadata)

    return target


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change user role. Admin only."""
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
