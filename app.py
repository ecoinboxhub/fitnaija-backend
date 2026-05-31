#!/usr/bin/env python3
"""
FitNaija Backend - FastAPI Server
Production-ready backend with PostgreSQL, JWT auth, and secure OTP flow.
"""

import hashlib
import os
import random
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Query, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text, create_engine, inspect, text)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

load_dotenv()

raw_database_url = os.getenv("DATABASE_URL", "").strip()
if raw_database_url and ("<" in raw_database_url or ">" in raw_database_url or "password" in raw_database_url or "<port>" in raw_database_url):
    print("[WARNING] Invalid DATABASE_URL detected in environment variables. Falling back to local sqlite for startup.")
    DATABASE_URL = "sqlite:///./fitnaija.db"
else:
    DATABASE_URL = raw_database_url or "sqlite:///./fitnaija.db"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "replace-with-a-strong-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
BACKEND_ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv(
    "BACKEND_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:8000"
).split(",") if origin.strip()]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
security = HTTPBearer()
app = FastAPI(title="FitNaija API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    phone = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    status = Column(String, default="trial_active")
    steps_total = Column(Integer, default=0)
    avatar = Column(String, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    activities = relationship("ActivityLog", back_populates="user")
    leaderboard_entries = relationship("Leaderboard", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")


class OTP(Base):
    __tablename__ = "otps"

    phone = Column(String, primary_key=True, index=True)
    code_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)


class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    activity_type = Column(String, nullable=False)
    entry_fee = Column(Integer, default=0)
    prize_pool = Column(Integer, default=0)
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=False)
    location_scope = Column(String, nullable=True)
    status = Column(String, default="active")
    participants = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    challenge_id = Column(String, ForeignKey("challenges.id"), nullable=True)
    activity_type = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    steps = Column(Integer, default=0)
    distance_km = Column(Float, nullable=True)
    proof_image_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="activities")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount_kobo = Column(Integer, nullable=False)
    txn_type = Column(String, default="tip")
    provider_txn_id = Column(String, nullable=True)
    status = Column(String, default="completed")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    id = Column(String, primary_key=True, index=True)
    challenge_id = Column(String, ForeignKey("challenges.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    steps = Column(Integer, default=0)
    distance_km = Column(Float, default=0.0)
    activities_count = Column(Integer, default=0)
    rank = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="leaderboard_entries")


class SendOtpRequest(BaseModel):
    phone: str


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str


class CreateProfileRequest(BaseModel):
    display_name: str
    location: str


class LogActivityRequest(BaseModel):
    challenge_id: Optional[str] = None
    activity_type: str
    duration_minutes: int
    steps: int
    distance_km: Optional[float] = None


class AIChatRequest(BaseModel):
    message: str


class TipRequest(BaseModel):
    amount: int


class UserResponse(BaseModel):
    id: str
    phone: str
    display_name: str
    location: str
    status: str
    steps_total: int
    avatar: Optional[str] = None


class ChallengeResponse(BaseModel):
    id: str
    title: str
    activity_type: str
    entry_fee: int
    prize_pool: int
    start_date: str
    end_date: str
    location_scope: Optional[str]
    status: str
    participants: int


class ActivityLogResponse(BaseModel):
    id: str
    user_id: str
    challenge_id: Optional[str]
    activity_type: str
    duration_minutes: int
    steps: int
    distance_km: Optional[float]
    created_at: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_phone(phone: str) -> Optional[str]:
    if not phone:
        return None
    digits = ''.join([c for c in phone if c.isdigit()])
    if digits.startswith('234'):
        digits = digits
    elif digits.startswith('0'):
        digits = '234' + digits[1:]
    elif digits.startswith('+234'):
        digits = digits[1:]
    if len(digits) != 13:
        return None
    return digits


def generate_id(prefix: str = "") -> str:
    return f"{prefix}_{int(datetime.utcnow().timestamp() * 1000)}_{random.randint(1000, 9999)}"


def generate_otp() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload.update({"exp": int(expire.timestamp())})
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("exp") and datetime.utcnow().timestamp() > payload["exp"]:
            raise JWTError("Token expired")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
    return db.query(User).filter(User.phone == phone).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "phone": user.phone,
        "display_name": user.display_name,
        "location": user.location,
        "status": user.status,
        "steps_total": user.steps_total,
        "avatar": user.avatar,
    }


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token_data = verify_token(credentials.credentials)
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_verified_phone(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> str:
    token_data = verify_token(credentials.credentials)
    if not token_data.get("is_new"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Profile creation token required")
    phone = token_data.get("phone")
    if not phone:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    otp_record = db.query(OTP).filter(OTP.phone == phone, OTP.verified == True).first()
    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP session is invalid or expired")
    return phone


def challenge_to_dict(challenge: Challenge) -> dict:
    return {
        "id": challenge.id,
        "title": challenge.title,
        "activity_type": challenge.activity_type,
        "entry_fee": challenge.entry_fee,
        "prize_pool": challenge.prize_pool,
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "location_scope": challenge.location_scope,
        "status": challenge.status,
        "participants": challenge.participants,
    }


def activity_to_dict(activity: ActivityLog) -> dict:
    return {
        "id": activity.id,
        "user_id": activity.user_id,
        "challenge_id": activity.challenge_id,
        "activity_type": activity.activity_type,
        "duration_minutes": activity.duration_minutes,
        "steps": activity.steps,
        "distance_km": activity.distance_km,
        "created_at": activity.created_at.isoformat(),
    }


def migrate_sqlite_schema(engine):
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    with engine.begin() as conn:
        if "challenges" in inspector.get_table_names():
            challenge_cols = [col["name"] for col in inspector.get_columns("challenges")]
            if "activity_type" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN activity_type VARCHAR DEFAULT 'steps'"))
            if "entry_fee" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN entry_fee INTEGER DEFAULT 0"))
            if "prize_pool" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN prize_pool INTEGER DEFAULT 0"))
            if "location_scope" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN location_scope VARCHAR"))
            if "status" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN status VARCHAR DEFAULT 'active'"))
            if "participants" not in challenge_cols:
                conn.execute(text("ALTER TABLE challenges ADD COLUMN participants INTEGER DEFAULT 0"))

        if "users" in inspector.get_table_names():
            user_cols = [col["name"] for col in inspector.get_columns("users")]
            if "trial_end" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN trial_end DATETIME"))

        if "activity_logs" in inspector.get_table_names():
            log_cols = [col["name"] for col in inspector.get_columns("activity_logs")]
            if "proof_image_url" not in log_cols:
                conn.execute(text("ALTER TABLE activity_logs ADD COLUMN proof_image_url VARCHAR"))

        if "leaderboard" in inspector.get_table_names():
            board_cols = [col["name"] for col in inspector.get_columns("leaderboard")]
            if "distance_km" not in board_cols:
                conn.execute(text("ALTER TABLE leaderboard ADD COLUMN distance_km REAL DEFAULT 0.0"))
            if "activities_count" not in board_cols:
                conn.execute(text("ALTER TABLE leaderboard ADD COLUMN activities_count INTEGER DEFAULT 0"))
            if "rank" not in board_cols:
                conn.execute(text("ALTER TABLE leaderboard ADD COLUMN rank INTEGER"))


def seed_challenges(db: Session) -> None:
    count = db.query(Challenge).count()
    if count > 0:
        return
    default_challenges = [
        ("c1", "Abuja 10K Steps Streak", "steps", 0, 0, "2026-05-25", "2026-06-25", None, "active", 142),
        ("c2", "Wuse–Maitama Morning Run", "running", 1000, 85000, "2026-06-01", "2026-06-30", "wuse", "upcoming", 37),
        ("c3", "June Cycling Blitz", "cycling", 2500, 200000, "2026-06-01", "2026-06-30", None, "upcoming", 89),
        ("c4", "Port Harcourt Steps Derby", "steps", 5000, 450000, "2026-05-01", "2026-05-31", "port_harcourt", "verification", 211),
        ("c5", "Garki Weekend Warriors", "running", 1500, 120000, "2026-04-01", "2026-04-30", "garki", "settled", 68),
    ]
    for ch in default_challenges:
        db.add(Challenge(
            id=ch[0],
            title=ch[1],
            activity_type=ch[2],
            entry_fee=ch[3],
            prize_pool=ch[4],
            start_date=ch[5],
            end_date=ch[6],
            location_scope=ch[7],
            status=ch[8],
            participants=ch[9],
        ))
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)
    with SessionLocal() as db:
        seed_challenges(db)


@app.post("/auth/send-otp")
def send_otp(request: SendOtpRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")

    code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    hashed_code = hash_text(code)

    otp_record = db.query(OTP).filter(OTP.phone == phone).first()
    if otp_record:
        otp_record.code_hash = hashed_code
        otp_record.created_at = datetime.utcnow()
        otp_record.expires_at = expires_at
        otp_record.verified = False
    else:
        otp_record = OTP(phone=phone, code_hash=hashed_code, created_at=datetime.utcnow(), expires_at=expires_at, verified=False)
        db.add(otp_record)

    db.commit()
    print(f"[OTP] Phone: {phone}, Code: {code}")

    return {"success": True, "message": "OTP sent successfully"}


@app.post("/auth/verify-otp")
def verify_otp(request: VerifyOtpRequest, db: Session = Depends(get_db)):
    phone = normalize_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")

    otp_record = db.query(OTP).filter(OTP.phone == phone).first()
    if not otp_record or otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP not found or expired")

    if otp_record.code_hash != hash_text(request.otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")

    otp_record.verified = True
    db.commit()

    user = get_user_by_phone(db, phone)
    if user:
        access_token = create_access_token({"sub": user.id, "user_id": user.id, "is_new": False})
        return {"success": True, "message": "OTP verified", "user": user_to_dict(user), "is_new": False, "token": access_token}

    access_token = create_access_token({"sub": phone, "phone": phone, "is_new": True})
    return {"success": True, "message": "OTP verified", "is_new": True, "token": access_token}


@app.post("/auth/create-profile")
def create_profile(
    request: CreateProfileRequest,
    phone: str = Depends(get_verified_phone),
    db: Session = Depends(get_db),
):
    display_name = request.display_name.strip()
    location = request.location.strip()

    if not display_name or not location:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All fields are required")

    if get_user_by_phone(db, phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    user_id = generate_id("u")
    avatar = ''.join([w[0].upper() for w in display_name.split() if w])[:2]
    trial_end = datetime.utcnow() + timedelta(days=30)

    user = User(
        id=user_id,
        phone=phone,
        display_name=display_name,
        location=location,
        status="trial_active",
        steps_total=0,
        avatar=avatar,
        trial_end=trial_end,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create profile")

    access_token = create_access_token({"sub": user.id, "user_id": user.id, "is_new": False})
    return {"success": True, "message": "Profile created", "user": user_to_dict(user), "token": access_token}


@app.get("/challenges")
def get_challenges(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Challenge)
    if status:
        query = query.filter(Challenge.status == status)
    challenges = query.order_by(Challenge.created_at.desc()).all()
    return [challenge_to_dict(ch) for ch in challenges]


@app.get("/challenges/{challenge_id}")
def get_challenge(challenge_id: str, db: Session = Depends(get_db)):
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return challenge_to_dict(challenge)


@app.post("/activities/log")
def log_activity(
    user_id: str = Form(...),
    challenge_id: Optional[str] = Form(None),
    activity_type: str = Form(...),
    duration_minutes: int = Form(...),
    steps: int = Form(...),
    distance_km: Optional[float] = Form(None),
    proof_image: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized action")

    if duration_minutes <= 0 or steps < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid activity data")

    activity_id = generate_id("act")
    image_url = None
    if proof_image:
        filename = f"{activity_id}_{proof_image.filename}"
        image_url = f"/uploads/{filename}"

    activity = ActivityLog(
        id=activity_id,
        user_id=current_user.id,
        challenge_id=challenge_id,
        activity_type=activity_type,
        duration_minutes=duration_minutes,
        steps=steps,
        distance_km=distance_km,
        proof_image_url=image_url,
    )
    db.add(activity)
    current_user.steps_total += steps

    if challenge_id:
        leaderboard_entry = db.query(Leaderboard).filter(
            Leaderboard.challenge_id == challenge_id,
            Leaderboard.user_id == current_user.id,
        ).first()
        if leaderboard_entry:
            leaderboard_entry.steps += steps
            leaderboard_entry.activities_count += 1
        else:
            leaderboard_entry = Leaderboard(
                id=generate_id("lb"),
                challenge_id=challenge_id,
                user_id=current_user.id,
                steps=steps,
                activities_count=1,
            )
            db.add(leaderboard_entry)

    db.commit()

    return {
        "success": True,
        "message": "Activity logged successfully",
        "activity_id": activity_id,
        "data": activity_to_dict(activity),
    }


@app.get("/activities/user/{user_id}")
def get_user_activities(user_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access")
    activities = db.query(ActivityLog).filter(ActivityLog.user_id == user_id).order_by(ActivityLog.created_at.desc()).all()
    return [activity_to_dict(act) for act in activities]


@app.get("/leaderboard/{challenge_id}")
def get_leaderboard(challenge_id: str, db: Session = Depends(get_db)):
    entries = db.query(Leaderboard).filter(Leaderboard.challenge_id == challenge_id).order_by(Leaderboard.steps.desc()).all()
    leaderboard = []
    for idx, entry in enumerate(entries, start=1):
        user = get_user_by_id(db, entry.user_id)
        leaderboard.append({
            "rank": idx,
            "user_id": entry.user_id,
            "user_name": user.display_name if user else "Unknown",
            "avatar": user.avatar if user else "U",
            "steps": entry.steps,
            "distance_km": entry.distance_km,
            "activities_count": entry.activities_count,
        })
    return leaderboard


@app.post("/ai/chat")
def ai_chat(request: AIChatRequest, current_user: User = Depends(get_current_user)):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message required")

    responses = [
        "That's a great question! Keep pushing yourself and remember consistency is key to fitness success.",
        "I'm here to help you with your fitness journey. What specific area would you like to focus on?",
        "Keep up the excellent work! Your dedication is inspiring. How can I help you today?",
        "Remember to stay hydrated, warm up properly, and listen to your body during workouts.",
        "Great effort! Recovery is just as important as training. Make sure to get enough rest.",
        "You're doing amazing! Let's keep this momentum going. What's your next fitness goal?",
        "Consistency beats perfection every time. Small steps lead to big results!",
        "Your health journey is unique to you. Focus on progress, not perfection.",
    ]

    response = random.choice(responses)
    return {"success": True, "message": message, "reply": response, "timestamp": datetime.utcnow().isoformat()}


@app.post("/payments/tip")
def process_tip(
    amount: int = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if amount < 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum tip is ₦100")

    txn_id = f"esp_{generate_id('txn')}"
    transaction = Transaction(
        id=generate_id("txn"),
        user_id=current_user.id,
        amount_kobo=amount * 100,
        txn_type="tip",
        provider_txn_id=txn_id,
        status="completed",
    )
    db.add(transaction)
    db.commit()

    return {"success": True, "message": "Tip processed successfully", "txn_id": txn_id, "amount": amount, "timestamp": datetime.utcnow().isoformat()}


@app.get("/payments/recent")
def get_recent_transactions(
    user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user_id and user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access")

    query = db.query(Transaction)
    if user_id:
        query = query.filter(Transaction.user_id == user_id)
    else:
        query = query.filter(Transaction.user_id == current_user.id)

    rows = query.order_by(Transaction.created_at.desc()).limit(50).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "amount_kobo": row.amount_kobo,
            "txn_type": row.txn_type,
            "provider_txn_id": row.provider_txn_id,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/users/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_to_dict(user)


@app.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.steps_total.desc()).all()
    return [user_to_dict(user) for user in users]


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"}


@app.get("/")
def root():
    return {"app": "FitNaija API", "version": "1.0.0", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
