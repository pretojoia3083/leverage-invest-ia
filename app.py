import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "leverage-invest-ia-2026")
DB_FILE = "leverage.db"
LICENSE_DAYS = 30
ADMIN_EMAIL = "luisrenatotrader@gmail.com"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="LEVERAGE INVEST IA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            uid TEXT PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            mt5_account TEXT DEFAULT '',
            mt5_server TEXT DEFAULT '',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS licenses (
            uid TEXT PRIMARY KEY,
            key TEXT,
            active INTEGER DEFAULT 0,
            created_at TEXT,
            expires_at TEXT,
            days INTEGER DEFAULT 30
        );
        CREATE TABLE IF NOT EXISTS robots (
            uid TEXT PRIMARY KEY,
            active INTEGER DEFAULT 0,
            symbol TEXT DEFAULT 'XAUUSD',
            started_at TEXT
        );
        CREATE TABLE IF NOT EXISTS configs (
            uid TEXT PRIMARY KEY,
            symbol TEXT DEFAULT 'XAUUSD',
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            profit REAL DEFAULT 0.0
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT,
            symbol TEXT,
            direction TEXT,
            lot REAL,
            price REAL,
            ticket INTEGER,
            status TEXT,
            profit REAL DEFAULT 0.0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ea_data (
            uid TEXT PRIMARY KEY,
            balance REAL DEFAULT 0,
            equity REAL DEFAULT 0,
            profit REAL DEFAULT 0,
            positions INTEGER DEFAULT 0,
            positions_list TEXT DEFAULT '[]',
            last_update TEXT
        );
    """)
    conn.commit()
    conn.close()

init_db()

def create_token(data):
    return jwt.encode(data, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None

def get_uid(request):
    token = request.cookies.get("token")
    if not token:
        return None
    return verify_token(token)

def get_user(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def is_admin(uid):
    user = get_user(uid)
    return user and user.get("email") == ADMIN_EMAIL

def gen_license_key():
    raw = str(uuid.uuid4()).replace("-", "")[:16].upper()
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

def get_license(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM licenses WHERE uid=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_license(uid, lic):
    conn = get_db()
    conn.execute("DELETE FROM licenses WHERE uid=?", (uid,))
    conn.execute("INSERT INTO licenses (uid,key,active,created_at,expires_at,days) VALUES (?,?,?,?,?,?)",
        (uid, lic["key"], 1 if lic["active"] else 0, lic["created_at"], lic["expires_at"], lic.get("days", 30)))
    conn.commit()
    conn.close()

def get_config(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM configs WHERE uid=?", (uid,)).fetchone()
    if not row:
        conn.execute("INSERT INTO configs (uid) VALUES (?)", (uid,))
        conn.commit()
        row = conn.execute("SELECT * FROM configs WHERE uid=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else {"symbol": "XAUUSD", "wins": 0, "losses": 0, "profit": 0.0}

def save_config(uid, cfg):
    conn = get_db()
    conn.execute("DELETE FROM configs WHERE uid=?", (uid,))
    conn.execute("INSERT INTO configs (uid,symbol,wins,losses,profit) VALUES (?,?,?,?,?)",
        (uid, cfg.get("symbol", "XAUUSD"), cfg.get("wins", 0), cfg.get("losses", 0), cfg.get("profit", 0.0)))
    conn.commit()
    conn.close()

def get_robot(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM robots WHERE uid=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else {"active": False, "symbol": "XAUUSD"}

def save_robot(uid, robot):
    conn = get_db()
    conn.execute("DELETE FROM robots WHERE uid=?", (uid,))
    conn.execute("INSERT INTO robots (uid,active,symbol,started_at) VALUES (?,?,?,?)",
        (uid, 1 if robot.get("active") else 0, robot.get("symbol", "XAUUSD"), robot.get("started_at", "")))
    conn.commit()
    conn.close()


# ---- PAGES ----

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    uid = get_uid(request)
    if uid:
        return RedirectResponse(url="/admin" if is_admin(uid) else "/dashboard")
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_uid(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    row = conn.execute("SELECT uid FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if row:
        user = get_user(row["uid"])
        if user and pwd_context.verify(password, user["password"]):
            token = create_token({"sub": row["uid"]})
            response = RedirectResponse(url="/admin" if is_admin(row["uid"]) else "/dashboard", status_code=302)
            response.set_cookie("token", token, httponly=True, max_age=86400)
            return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Email ou senha incorretos"})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    exists = conn.execute("SELECT uid FROM users WHERE email=?", (email,)).fetchone()
    if exists:
        conn.close()
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email ja cadastrado"})

    uid = str(uuid.uuid4())[:8]
    hashed = pwd_context.hash(password)
    conn.execute("INSERT INTO users (uid,name,email,password,mt5_account,mt5_server,created_at) VALUES (?,?,?,?,?,?,?)",
        (uid, name, email, hashed, "", "", datetime.now().isoformat()))
    conn.execute("INSERT INTO configs (uid) VALUES (?)", (uid,))
    conn.execute("INSERT INTO robots (uid) VALUES (?)", (uid,))
    conn.commit()
    conn.close()

    token = create_token({"sub": uid})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("token", token, httponly=True, max_age=86400)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("token")
    return response

@app.get("/payment", response_class=HTMLResponse)
async def payment_page(request: Request):
    return templates.TemplateResponse("payment.html", {"request": request})


# ---- CLIENT DASHBOARD ----

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    uid = get_uid(request)
    if not uid:
        return RedirectResponse(url="/login")
    user = get_user(uid)
    config = get_config(uid)
    robot = get_robot(uid)
    lic = get_license(uid)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "config": config, "robot": robot, "license": lic,
    })


# ---- ADMIN ----

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    uid = get_uid(request)
    if not uid or not is_admin(uid):
        return RedirectResponse(url="/login")
    conn = get_db()
    users = {r["uid"]: dict(r) for r in conn.execute("SELECT * FROM users").fetchall()}
    licenses = {r["uid"]: dict(r) for r in conn.execute("SELECT * FROM licenses").fetchall()}
    conn.close()
    return templates.TemplateResponse("admin.html", {"request": request, "users": users, "licenses": licenses})

@app.post("/admin/activate")
async def admin_activate(request: Request):
    uid = get_uid(request)
    if not uid or not is_admin(uid):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    target_uid = data.get("uid", "")
    days = int(data.get("days", LICENSE_DAYS))

    existing = get_license(target_uid)
    if existing and existing.get("key"):
        key = existing["key"]
        try:
            expires = datetime.fromisoformat(existing["expires_at"])
            if expires < datetime.now():
                expires = datetime.now()
        except:
            expires = datetime.now()
        new_expires = (expires + timedelta(days=days)).isoformat()
    else:
        key = gen_license_key()
        new_expires = (datetime.now() + timedelta(days=days)).isoformat()

    lic = {"key": key, "active": True, "created_at": datetime.now().isoformat(), "expires_at": new_expires, "days": days}
    save_license(target_uid, lic)
    return {"status": "ok", "key": key, "expires": new_expires}

@app.post("/admin/deactivate")
async def admin_deactivate(request: Request):
    uid = get_uid(request)
    if not uid or not is_admin(uid):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    target_uid = data.get("uid", "")
    lic = get_license(target_uid)
    if lic:
        lic["active"] = False
        save_license(target_uid, lic)
    return {"status": "ok"}

@app.post("/admin/renew")
async def admin_renew(request: Request):
    uid = get_uid(request)
    if not uid or not is_admin(uid):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    target_uid = data.get("uid", "")
    days = int(data.get("days", LICENSE_DAYS))
    lic = get_license(target_uid)
    if lic:
        try:
            expires = datetime.fromisoformat(lic["expires_at"])
            if expires < datetime.now():
                expires = datetime.now()
        except:
            expires = datetime.now()
        lic["expires_at"] = (expires + timedelta(days=days)).isoformat()
        lic["active"] = True
        lic["days"] = days
        save_license(target_uid, lic)
        return {"status": "ok", "expires": lic["expires_at"]}
    return JSONResponse({"error": "Licenca nao encontrada"})


# ---- CLIENT API ----

@app.post("/api/connect-mt5")
async def api_connect_mt5(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    conn = get_db()
    conn.execute("UPDATE users SET mt5_account=?, mt5_server=? WHERE uid=?",
        (data.get("account", ""), data.get("server", ""), uid))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Conta vinculada!"}

@app.post("/api/disconnect-mt5")
async def api_disconnect_mt5(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    conn = get_db()
    conn.execute("UPDATE users SET mt5_account='', mt5_server='' WHERE uid=?", (uid,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/api/status")
async def api_status(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user = get_user(uid)
    robot = get_robot(uid)
    lic = get_license(uid)
    config = get_config(uid)
    conn = get_db()
    trades = [dict(r) for r in conn.execute("SELECT * FROM trades WHERE uid=? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()]
    ea = conn.execute("SELECT * FROM ea_data WHERE uid=?", (uid,)).fetchone()
    conn.close()

    lic_valid = False
    lic_expires = ""
    if lic and lic.get("active"):
        try:
            expires = datetime.fromisoformat(lic["expires_at"])
            if expires > datetime.now():
                lic_valid = True
                lic_expires = lic["expires_at"]
        except:
            pass

    ea_dict = dict(ea) if ea else {}
    return {
        "connected": bool(user and user.get("mt5_account")),
        "mt5_account": user.get("mt5_account", "") if user else "",
        "mt5_server": user.get("mt5_server", "") if user else "",
        "balance": ea_dict.get("balance", 0),
        "equity": ea_dict.get("equity", 0),
        "profit": ea_dict.get("profit", 0),
        "positions": ea_dict.get("positions", 0),
        "positions_list": json.loads(ea_dict.get("positions_list", "[]")),
        "robot_active": robot.get("active", False),
        "robot_symbol": robot.get("symbol", "XAUUSD"),
        "wins": config.get("wins", 0),
        "losses": config.get("losses", 0),
        "license_valid": lic_valid,
        "license_expires": lic_expires,
        "license_key": lic.get("key", "") if lic else "",
        "trades": trades,
    }

@app.post("/api/robot/start")
async def api_robot_start(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    lic = get_license(uid)
    if not lic or not lic.get("active"):
        return JSONResponse({"error": "Licenca inativa. Contrate um plano."})
    try:
        if datetime.fromisoformat(lic["expires_at"]) < datetime.now():
            return JSONResponse({"error": "Licenca expirada."})
    except:
        return JSONResponse({"error": "Licenca invalida."})
    data = await request.json()
    robot = {"active": True, "symbol": data.get("symbol", "XAUUSD"), "started_at": datetime.now().isoformat()}
    save_robot(uid, robot)
    return {"status": "ok", "message": f"Robo LIGADO em {data.get('symbol', 'XAUUSD')}"}

@app.post("/api/robot/stop")
async def api_robot_stop(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    robot = get_robot(uid)
    robot["active"] = False
    save_robot(uid, robot)
    return {"status": "ok", "message": "Robo DESLIGADO"}

@app.get("/api/config")
async def api_config(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return get_config(uid)

@app.post("/api/config")
async def api_update_config(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    data = await request.json()
    config = get_config(uid)
    for key in data:
        if key in config:
            config[key] = data[key]
    save_config(uid, config)
    return {"status": "ok"}


# ---- EA API ----

@app.post("/api/ea/validate")
async def api_ea_validate(request: Request):
    data = await request.json()
    key = data.get("key", "")
    account = data.get("account", "")
    server = data.get("server", "")

    conn = get_db()
    row = conn.execute("SELECT * FROM licenses WHERE key=?", (key,)).fetchone()
    if not row:
        conn.close()
        return {"status": "error", "valid": False, "error": "Licenca invalida. Verifique sua chave."}

    lic = dict(row)
    uid = lic["uid"]

    if not lic.get("active"):
        conn.close()
        return {"status": "error", "valid": False, "error": "Licenca bloqueada. Entre em contato com o suporte."}

    try:
        if datetime.fromisoformat(lic["expires_at"]) < datetime.now():
            conn.close()
            return {"status": "error", "valid": False, "error": "Licenca expirada. Renove seu plano."}
    except:
        conn.close()
        return {"status": "error", "valid": False, "error": "Licenca invalida."}

    user = conn.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
    conn.close()

    if not user:
        return {"status": "error", "valid": False, "error": "Conta nao encontrada."}

    user = dict(user)
    if user.get("mt5_account") != account or user.get("mt5_server") != server:
        return {"status": "error", "valid": False, "error": "Conta nao autorizada. Entre em contato com o suporte."}

    robot = get_robot(uid)
    return {
        "status": "ok", "valid": True, "expires": lic["expires_at"],
        "robot_active": robot.get("active", False),
        "symbol": robot.get("symbol", "XAUUSD"),
    }

@app.post("/api/ea/update")
async def api_ea_update(request: Request):
    data = await request.json()
    key = data.get("key", "")
    conn = get_db()
    row = conn.execute("SELECT uid FROM licenses WHERE key=?", (key,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "unknown"})
    uid = row["uid"]
    conn.execute("DELETE FROM ea_data WHERE uid=?", (uid,))
    conn.execute("INSERT INTO ea_data (uid,balance,equity,profit,positions,positions_list,last_update) VALUES (?,?,?,?,?,?,?)",
        (uid, data.get("balance", 0), data.get("equity", 0), data.get("profit", 0),
         data.get("positions", 0), json.dumps(data.get("positions_list", [])), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/ea/trade")
async def api_ea_trade(request: Request):
    data = await request.json()
    key = data.get("key", "")
    conn = get_db()
    row = conn.execute("SELECT uid FROM licenses WHERE key=?", (key,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"error": "unknown"})
    uid = row["uid"]
    conn.execute("INSERT INTO trades (uid,symbol,direction,lot,price,ticket,status,profit,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, data.get("symbol", ""), data.get("direction", ""), data.get("lot", 0),
         data.get("price", 0), data.get("ticket", 0), data.get("status", "open"),
         data.get("profit", 0), datetime.now().isoformat()))
    if data.get("status") == "closed":
        profit = data.get("profit", 0)
        cfg = get_config(uid)
        cfg["profit"] = cfg.get("profit", 0) + profit
        if profit >= 0:
            cfg["wins"] = cfg.get("wins", 0) + 1
        else:
            cfg["losses"] = cfg.get("losses", 0) + 1
        save_config(uid, cfg)
    conn.commit()
    conn.close()
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
