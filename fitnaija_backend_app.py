#!/usr/bin/env python3
"""
FitNaija Backend - FastAPI Server
Full-featured fitness app backend with OTP auth, challenges, workouts, AI coach, and payments
"""

from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import json
import random
import string
import time
from datetime import datetime, timedelta
import hashlib
import os

# ─── SETUP ───────────────────────────────────────────────────────────────────
app = FastAPI(title="FitNaija API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DB_PATH = "fitnaija.db"

def init_db():
    """Initialize SQLite database with schema"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        phone TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        location TEXT NOT NULL,
        status TEXT DEFAULT 'trial_active',
        steps_total INTEGER DEFAULT 0,
        avatar TEXT,
        trial_end TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # OTP table
    c.execute('''CREATE TABLE IF NOT EXISTS otps (
        phone TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
    )''')
    
    # Challenges table
    c.execute('''CREATE TABLE IF NOT EXISTS challenges (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        activity_type TEXT NOT NULL,
        entry_fee INTEGER DEFAULT 0,
        prize_pool INTEGER DEFAULT 0,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        location_scope TEXT,
        status TEXT DEFAULT 'active',
        participants INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Activity logs table
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        challenge_id TEXT,
        activity_type TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        steps INTEGER DEFAULT 0,
        distance_km REAL,
        proof_image_url TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(challenge_id) REFERENCES challenges(id)
    )''')
    
    # Chat messages table
    c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        amount_kobo INTEGER NOT NULL,
        txn_type TEXT DEFAULT 'tip',
        provider_txn_id TEXT,
        status TEXT DEFAULT 'completed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    # Leaderboard entries table
    c.execute('''CREATE TABLE IF NOT EXISTS leaderboard (
        id TEXT PRIMARY KEY,
        challenge_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        steps INTEGER DEFAULT 0,
        distance_km REAL DEFAULT 0,
        activities_count INTEGER DEFAULT 0,
        rank INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(challenge_id) REFERENCES challenges(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    
    conn.commit()
    conn.close()

init_db()

# ─── PYDANTIC MODELS ─────────────────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    phone: str

class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str

class CreateProfileRequest(BaseModel):
    phone: str
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
    avatar: str

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

# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def get_db():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)

def generate_id(prefix=""):
    """Generate unique ID"""
    return f"{prefix}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

def generate_otp():
    """Generate 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))

def get_user_by_phone(phone: str):
    """Get user by phone number"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, phone, display_name, location, status, steps_total, avatar FROM users WHERE phone = ?", (phone,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "phone": row[1],
            "display_name": row[2],
            "location": row[3],
            "status": row[4],
            "steps_total": row[5],
            "avatar": row[6]
        }
    return None

def get_user_by_id(user_id: str):
    """Get user by ID"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, phone, display_name, location, status, steps_total, avatar FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "phone": row[1],
            "display_name": row[2],
            "location": row[3],
            "status": row[4],
            "steps_total": row[5],
            "avatar": row[6]
        }
    return None

def seed_challenges():
    """Seed initial challenges if none exist"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM challenges")
    count = c.fetchone()[0]
    
    if count == 0:
        challenges = [
            ("c1", "Abuja 10K Steps Streak", "steps", 0, 0, "2026-05-25", "2026-06-25", None, "active", 142),
            ("c2", "Wuse–Maitama Morning Run", "running", 1000, 85000, "2026-06-01", "2026-06-30", "wuse", "upcoming", 37),
            ("c3", "June Cycling Blitz", "cycling", 2500, 200000, "2026-06-01", "2026-06-30", None, "upcoming", 89),
            ("c4", "Port Harcourt Steps Derby", "steps", 5000, 450000, "2026-05-01", "2026-05-31", "port_harcourt", "verification", 211),
            ("c5", "Garki Weekend Warriors", "running", 1500, 120000, "2026-04-01", "2026-04-30", "garki", "settled", 68),
        ]
        for ch in challenges:
            c.execute("""INSERT INTO challenges 
                (id, title, activity_type, entry_fee, prize_pool, start_date, end_date, location_scope, status, participants)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", ch)
    
    conn.commit()
    conn.close()

seed_challenges()

# ─── AUTH ENDPOINTS ──────────────────────────────────────────────────────────

@app.post("/auth/send-otp")
async def send_otp(request: SendOtpRequest):
    """Send OTP to phone number"""
    phone = request.phone.strip()
    
    if not phone or len(phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")
    
    try:
        otp_code = generate_otp()
        expires_at = time.time() + 300  # 5 minutes
        
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO otps (phone, code, created_at, expires_at) VALUES (?, ?, ?, ?)",
                  (phone, otp_code, time.time(), expires_at))
        conn.commit()
        conn.close()
        
        # In production, send via SMS/WhatsApp
        print(f"[OTP] Phone: {phone}, Code: {otp_code}")
        
        return {
            "success": True,
            "message": "OTP sent successfully",
            "otp": otp_code  # For testing only
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending OTP: {str(e)}")

@app.post("/auth/verify-otp")
async def verify_otp(request: VerifyOtpRequest):
    """Verify OTP and login/create user"""
    phone = request.phone.strip()
    otp_code = request.otp.strip()
    
    if not phone or not otp_code:
        raise HTTPException(status_code=400, detail="Phone and OTP required")
    
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check OTP
        c.execute("SELECT code, expires_at FROM otps WHERE phone = ?", (phone,))
        otp_row = c.fetchone()
        
        if not otp_row:
            raise HTTPException(status_code=400, detail="OTP not found or expired")
        
        stored_code, expires_at = otp_row
        
        if time.time() > expires_at:
            raise HTTPException(status_code=400, detail="OTP expired")
        
        if stored_code != otp_code:
            raise HTTPException(status_code=400, detail="Invalid OTP")
        
        # Check if user exists
        c.execute("SELECT id, phone, display_name, location, status, steps_total, avatar FROM users WHERE phone = ?", (phone,))
        user_row = c.fetchone()
        
        if user_row:
            user = {
                "id": user_row[0],
                "phone": user_row[1],
                "display_name": user_row[2],
                "location": user_row[3],
                "status": user_row[4],
                "steps_total": user_row[5],
                "avatar": user_row[6]
            }
            conn.close()
            return {"success": True, "message": "OTP verified", "user": user, "is_new": False}
        
        # New user - return phone for profile creation
        conn.close()
        return {"success": True, "message": "OTP verified", "is_new": True, "phone": phone}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying OTP: {str(e)}")

@app.post("/auth/create-profile")
async def create_profile(request: CreateProfileRequest):
    """Create new user profile"""
    phone = request.phone.strip()
    display_name = request.display_name.strip()
    location = request.location.strip()
    
    if not phone or not display_name or not location:
        raise HTTPException(status_code=400, detail="All fields required")
    
    try:
        user_id = generate_id("u")
        avatar = ''.join([w[0].upper() for w in display_name.split()])[:2]
        trial_end = (datetime.now() + timedelta(days=30)).isoformat()
        
        conn = get_db()
        c = conn.cursor()
        c.execute("""INSERT INTO users 
            (id, phone, display_name, location, status, steps_total, avatar, trial_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, phone, display_name, location, "trial_active", 0, avatar, trial_end))
        conn.commit()
        conn.close()
        
        user = {
            "id": user_id,
            "phone": phone,
            "display_name": display_name,
            "location": location,
            "status": "trial_active",
            "steps_total": 0,
            "avatar": avatar
        }
        
        return {"success": True, "message": "Profile created", "user": user}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating profile: {str(e)}")

# ─── CHALLENGES ENDPOINTS ────────────────────────────────────────────────────

@app.get("/challenges")
async def get_challenges(status: Optional[str] = Query(None)):
    """Get all challenges, optionally filtered by status"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        if status:
            c.execute("""SELECT id, title, activity_type, entry_fee, prize_pool, start_date, end_date, 
                        location_scope, status, participants FROM challenges WHERE status = ? ORDER BY created_at DESC""", (status,))
        else:
            c.execute("""SELECT id, title, activity_type, entry_fee, prize_pool, start_date, end_date, 
                        location_scope, status, participants FROM challenges ORDER BY created_at DESC""")
        
        rows = c.fetchall()
        conn.close()
        
        challenges = []
        for row in rows:
            challenges.append({
                "id": row[0],
                "title": row[1],
                "activity_type": row[2],
                "entry_fee": row[3],
                "prize_pool": row[4],
                "start_date": row[5],
                "end_date": row[6],
                "location_scope": row[7],
                "status": row[8],
                "participants": row[9]
            })
        
        return challenges
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching challenges: {str(e)}")

@app.get("/challenges/{challenge_id}")
async def get_challenge(challenge_id: str):
    """Get single challenge detail"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT id, title, activity_type, entry_fee, prize_pool, start_date, end_date, 
                    location_scope, status, participants FROM challenges WHERE id = ?""", (challenge_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Challenge not found")
        
        return {
            "id": row[0],
            "title": row[1],
            "activity_type": row[2],
            "entry_fee": row[3],
            "prize_pool": row[4],
            "start_date": row[5],
            "end_date": row[6],
            "location_scope": row[7],
            "status": row[8],
            "participants": row[9]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching challenge: {str(e)}")

# ─── ACTIVITY ENDPOINTS ──────────────────────────────────────────────────────

@app.post("/activities/log")
async def log_activity(
    user_id: str = Form(...),
    challenge_id: Optional[str] = Form(None),
    activity_type: str = Form(...),
    duration_minutes: int = Form(...),
    steps: int = Form(...),
    distance_km: Optional[float] = Form(None),
    proof_image: Optional[UploadFile] = File(None)
):
    """Log a workout activity"""
    try:
        # Validate user
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate activity
        if duration_minutes <= 0 or steps < 0:
            raise HTTPException(status_code=400, detail="Invalid activity data")
        
        activity_id = generate_id("act")
        image_url = None
        
        # Handle image upload (in production, upload to S3)
        if proof_image:
            filename = f"{activity_id}_{proof_image.filename}"
            # In production: upload to S3 and get URL
            image_url = f"/uploads/{filename}"
        
        conn = get_db()
        c = conn.cursor()
        
        # Insert activity log
        c.execute("""INSERT INTO activity_logs 
            (id, user_id, challenge_id, activity_type, duration_minutes, steps, distance_km, proof_image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (activity_id, user_id, challenge_id, activity_type, duration_minutes, steps, distance_km, image_url))
        
        # Update user total steps
        c.execute("UPDATE users SET steps_total = steps_total + ? WHERE id = ?", (steps, user_id))
        
        # Update leaderboard if challenge specified
        if challenge_id:
            c.execute("""SELECT id FROM leaderboard WHERE challenge_id = ? AND user_id = ?""", (challenge_id, user_id))
            lb_row = c.fetchone()
            
            if lb_row:
                c.execute("""UPDATE leaderboard SET steps = steps + ?, activities_count = activities_count + 1 
                           WHERE challenge_id = ? AND user_id = ?""", (steps, challenge_id, user_id))
            else:
                lb_id = generate_id("lb")
                c.execute("""INSERT INTO leaderboard (id, challenge_id, user_id, steps, activities_count)
                           VALUES (?, ?, ?, ?, ?)""", (lb_id, challenge_id, user_id, steps, 1))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Activity logged successfully",
            "activity_id": activity_id,
            "data": {
                "id": activity_id,
                "user_id": user_id,
                "challenge_id": challenge_id,
                "activity_type": activity_type,
                "duration_minutes": duration_minutes,
                "steps": steps,
                "distance_km": distance_km,
                "created_at": datetime.now().isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error logging activity: {str(e)}")

@app.get("/activities/user/{user_id}")
async def get_user_activities(user_id: str):
    """Get all activities for a user"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT id, user_id, challenge_id, activity_type, duration_minutes, steps, distance_km, created_at
                    FROM activity_logs WHERE user_id = ? ORDER BY created_at DESC""", (user_id,))
        rows = c.fetchall()
        conn.close()
        
        activities = []
        for row in rows:
            activities.append({
                "id": row[0],
                "user_id": row[1],
                "challenge_id": row[2],
                "activity_type": row[3],
                "duration_minutes": row[4],
                "steps": row[5],
                "distance_km": row[6],
                "created_at": row[7]
            })
        
        return activities
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching activities: {str(e)}")

# ─── LEADERBOARD ENDPOINTS ──────────────────────────────────────────────────

@app.get("/leaderboard/{challenge_id}")
async def get_leaderboard(challenge_id: str):
    """Get leaderboard for a challenge"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("""SELECT l.id, l.user_id, l.steps, l.distance_km, l.activities_count
                    FROM leaderboard l
                    WHERE l.challenge_id = ?
                    ORDER BY l.steps DESC""", (challenge_id,))
        rows = c.fetchall()
        conn.close()
        
        leaderboard = []
        for idx, row in enumerate(rows, 1):
            user = get_user_by_id(row[1])
            leaderboard.append({
                "rank": idx,
                "user_id": row[1],
                "user_name": user["display_name"] if user else "Unknown",
                "avatar": user["avatar"] if user else "U",
                "steps": row[2],
                "distance_km": row[3],
                "activities_count": row[4]
            })
        
        return leaderboard
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leaderboard: {str(e)}")

# ─── AI COACH ENDPOINTS ──────────────────────────────────────────────────────

@app.post("/ai/chat")
async def ai_chat(request: AIChatRequest):
    """AI Coach chat endpoint"""
    try:
        message = request.message.strip()
        
        if not message:
            raise HTTPException(status_code=400, detail="Message required")
        
        # Simple AI responses (in production, use OpenAI/Claude API)
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
        
        # Log chat (optional)
        # In production, you'd store this for analytics
        
        return {
            "success": True,
            "message": message,
            "reply": response,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in AI chat: {str(e)}")

# ─── PAYMENT ENDPOINTS ───────────────────────────────────────────────────────

@app.post("/payments/tip")
async def process_tip(user_id: str = Form(...), amount: int = Form(...)):
    """Process tip payment"""
    try:
        if amount < 100:
            raise HTTPException(status_code=400, detail="Minimum tip is ₦100")
        
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Mock Espees payment
        txn_id = f"esp_{generate_id('txn')}"
        
        conn = get_db()
        c = conn.cursor()
        c.execute("""INSERT INTO transactions (id, user_id, amount_kobo, txn_type, provider_txn_id, status)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                  (generate_id("txn"), user_id, amount * 100, "tip", txn_id, "completed"))
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": "Tip processed successfully",
            "txn_id": txn_id,
            "amount": amount,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing tip: {str(e)}")

@app.get("/payments/recent")
async def get_recent_transactions(user_id: Optional[str] = Query(None)):
    """Get recent transactions"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        if user_id:
            c.execute("""SELECT id, user_id, amount_kobo, txn_type, provider_txn_id, status, created_at
                        FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20""", (user_id,))
        else:
            c.execute("""SELECT id, user_id, amount_kobo, txn_type, provider_txn_id, status, created_at
                        FROM transactions ORDER BY created_at DESC LIMIT 50""")
        
        rows = c.fetchall()
        conn.close()
        
        transactions = []
        for row in rows:
            transactions.append({
                "id": row[0],
                "user_id": row[1],
                "amount_kobo": row[2],
                "txn_type": row[3],
                "provider_txn_id": row[4],
                "status": row[5],
                "created_at": row[6]
            })
        
        return transactions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching transactions: {str(e)}")

# ─── USER ENDPOINTS ──────────────────────────────────────────────────────────

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user profile"""
    try:
        user = get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching user: {str(e)}")

@app.get("/users")
async def get_all_users():
    """Get all users"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT id, phone, display_name, location, status, steps_total, avatar FROM users ORDER BY steps_total DESC""")
        rows = c.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                "id": row[0],
                "phone": row[1],
                "display_name": row[2],
                "location": row[3],
                "status": row[4],
                "steps_total": row[5],
                "avatar": row[6]
            })
        
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

# ─── HEALTH CHECK ────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# ─── ROOT ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": "FitNaija API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
