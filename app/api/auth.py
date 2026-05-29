from fastapi import APIRouter, Depends, HTTPException, status
import jwt
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user import UserCreate
from app.schemas.auth import LoginRequest, TokenResponse, RefreshTokenRequest
from app.services.auth_service import AuthService
from app.core import security
from app.models.user import User
from app.tasks.email_tasks import send_welcome_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    new_user = AuthService.register_new_user(db=db, user_in=user_in)
    tokens = security.generate_auth_tokens(user_id=new_user.id)
    
    created_email = user_in.email
    send_welcome_email.delay(created_email)
    
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
        "user": new_user,
    }


@router.post("/login", response_model=TokenResponse)
def login(login_in: LoginRequest, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(
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
def refresh_token_endpoint(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    try:
        decoded = jwt.decode(
            payload.refresh_token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
        )

        user_id = decoded.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired or invalid refresh token",
        )

    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    new_tokens = security.generate_auth_tokens(user_id=user.id)

    return {
        "access_token": new_tokens["access_token"],
        "refresh_token": new_tokens["refresh_token"],
        "token_type": "bearer",
    }
