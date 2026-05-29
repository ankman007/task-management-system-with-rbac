from fastapi import APIRouter, Depends, HTTPException, status
import jwt
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user import UserCreate
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.user_service import UserService
from app.core import security
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    new_user = UserService.register_new_user(db=db, user_in=user_in)
    tokens = security.generate_auth_tokens(user_id=new_user.id)

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user": new_user,
    }


@router.post("/login", response_model=TokenResponse)
def login(login_in: LoginRequest, db: Session = Depends(get_db)):
    user = UserService.authenticate_user(
        db=db, email=login_in.email, password=login_in.password
    )
    tokens = security.generate_auth_tokens(user_id=user.id)

    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user": user,
    }


@router.post("/refresh")
def refresh_token_endpoint(refresh_token: str, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a brand new access token.
    """
    try:
        # Decode and validate refresh token
        payload = jwt.decode(
            refresh_token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired or invalid refresh token",
        )

    # Fetch user details to verify account status still exists
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Generate fresh token pair
    new_tokens = security.generate_auth_tokens(user_id=user.id)

    return {
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens[
            "refresh_token"
        ],  # Rotation pattern: send back a fresh refresh token too
        "token_type": "bearer",
    }
