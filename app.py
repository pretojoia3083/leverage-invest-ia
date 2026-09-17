import os
import json
import uuid
import hashlib
import time
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from jose import JWTError, jwt

SECRET_KEY = os.getenv("SECRET_KEY", "leverage-invest-ia-2026")
DB_FILE = "data.json"
ADMIN_EMAIL = "luisrenatotrader@gmail.com"
LICENSE_DAYS = 30

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


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "trades": {}, "configs": {}, "robots": {}, "licenses": {}}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, default=str)

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
    return load_db().get("users", {}).get(str(uid))

def is_admin(uid):
    user = get_user(uid)
    return user and user.get("email") == ADMIN_EMAIL

def gen_license_key():
    raw = str(uuid.uuid4()).replace("-", "")[:16].upper()
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

def get_license(uid):
    return load_db().get("licenses", {}).get(str(uid))

def save_license(uid, lic):
    db = load_db()
    db.setdefault("licenses", {})[str(uid)] = lic
    save_db(db)

def get_config(uid):
    db = load_db()
    cfg = db.get("configs", {}).get(str(uid))
    if not cfg:
        cfg = {"symbol": "XAUUSD", "wins": 0, "losses": 0, "profit": 0.0}
        db.setdefault("configs", {})[str(uid)] = cfg
        save_db(db)
    return cfg

def save_config(uid, cfg):
    db = load_db()
    db.setdefault("configs", {})[str(uid)] = cfg
    save_db(db)

def get_robot(uid):
    db = load_db()
    return db.get("robots", {}).get(str(uid), {"active": False, "symbol": "XAUUSD"})

def save_robot(uid, robot):
    db = load_db()
    db.setdefault("robots", {})[str(uid)] = robot
    save_db(db)


# ---- PAGES ----

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    uid = get_uid(request)
    if uid:
        if is_admin(uid):
            return RedirectResponse(url="/admin")
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_uid(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    db = load_db()
    for uid, user in db.get("users", {}).items():
        if user.get("email") == email:
            if pwd_context.verify(password, user["password"]):
                token = create_token({"sub": uid})
                response = RedirectResponse(url="/admin" if is_admin(uid) else "/dashboard", status_code=302)
                response.set_cookie("token", token, httponly=True, max_age=86400)
                return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Email ou senha incorretos"})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    db = load_db()
    for user in db.get("users", {}).values():
        if user.get("email") == email:
            return templates.TemplateResponse("register.html", {"request": request, "error": "Email ja cadastrado"})

    uid = str(uuid.uuid4())[:8]
    hashed = pwd_context.hash(password)
    db.setdefault("users", {})[uid] = {
        "name": name, "email": email, "password": hashed,
        "active": True, "created_at": datetime.now().isoformat(),
        "mt5_account": "", "mt5_server": "",
    }
    db.setdefault("configs", {})[uid] = {"symbol": "XAUUSD", "wins": 0, "losses": 0, "profit": 0.0}
    db.setdefault("trades", {})[uid] = []
    db.setdefault("robots", {})[uid] = {"active": False, "symbol": "XAUUSD"}
    save_db(db)

    token = create_token({"sub": uid})
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie("token", token, httponly=True, max_age=86400)
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("token")
    return response


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
    db = load_db()
    trades = db.get("trades", {}).get(uid, [])[-20:]
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "config": config,
        "trades": trades, "robot": robot, "license": lic,
    })


# ---- ADMIN DASHBOARD ----

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    uid = get_uid(request)
    if not uid or not is_admin(uid):
        return RedirectResponse(url="/login")
    db = load_db()
    users = db.get("users", {})
    licenses = db.get("licenses", {})
    return templates.TemplateResponse("admin.html", {
        "request": request, "users": users, "licenses": licenses,
    })

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
        expires = datetime.fromisoformat(existing["expires_at"])
        if expires < datetime.now():
            expires = datetime.now()
        lic = {
            "key": key,
            "active": True,
            "created_at": existing.get("created_at", datetime.now().isoformat()),
            "expires_at": (expires + timedelta(days=days)).isoformat(),
            "days": days,
        }
    else:
        key = gen_license_key()
        lic = {
            "key": key,
            "active": True,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=days)).isoformat(),
            "days": days,
        }
    save_license(target_uid, lic)
    return {"status": "ok", "key": key, "expires": lic["expires_at"]}

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
        expires = datetime.fromisoformat(lic["expires_at"])
        if expires < datetime.now():
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
    db = load_db()
    db["users"][uid]["mt5_account"] = data.get("account", "")
    db["users"][uid]["mt5_server"] = data.get("server", "")
    save_db(db)
    return {"status": "ok", "message": "Conta vinculada!"}

@app.post("/api/disconnect-mt5")
async def api_disconnect_mt5(request: Request):
    uid = get_uid(request)
    if not uid:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db = load_db()
    db["users"][uid]["mt5_account"] = ""
    db["users"][uid]["mt5_server"] = ""
    save_db(db)
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
    db = load_db()
    trades = db.get("trades", {}).get(uid, [])[-20:]
    ea_data = db.get("ea_data", {}).get(str(uid), {})

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

    return {
        "connected": bool(user.get("mt5_account")),
        "mt5_account": user.get("mt5_account", ""),
        "mt5_server": user.get("mt5_server", ""),
        "balance": ea_data.get("balance", 0),
        "equity": ea_data.get("equity", 0),
        "profit": ea_data.get("profit", 0),
        "positions": ea_data.get("positions", 0),
        "positions_list": ea_data.get("positions_list", []),
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
        expires = datetime.fromisoformat(lic["expires_at"])
        if expires < datetime.now():
            return JSONResponse({"error": "Licenca expirada. Renove seu plano."})
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


# ---- EA API (validacao de licenca) ----

@app.post("/api/ea/validate")
async def api_ea_validate(request: Request):
    data = await request.json()
    key = data.get("key", "")
    account = data.get("account", "")
    server = data.get("server", "")

    db = load_db()
    for uid, lic in db.get("licenses", {}).items():
        if lic.get("key") == key:
            if not lic.get("active"):
                return {"status": "error", "valid": False, "error": "Licenca bloqueada. Entre em contato com o suporte."}
            try:
                expires = datetime.fromisoformat(lic["expires_at"])
                if expires < datetime.now():
                    return {"status": "error", "valid": False, "error": "Licenca expirada. Renove seu plano."}
            except:
                return {"status": "error", "valid": False, "error": "Licenca invalida."}

            user = db.get("users", {}).get(uid, {})
            if user.get("mt5_account") != account or user.get("mt5_server") != server:
                return {"status": "error", "valid": False, "error": "Conta nao autorizada. Entre em contato com o suporte."}

            return {
                "status": "ok",
                "valid": True,
                "expires": lic["expires_at"],
                "robot_active": db.get("robots", {}).get(uid, {}).get("active", False),
                "symbol": db.get("robots", {}).get(uid, {}).get("symbol", "XAUUSD"),
            }

    return {"status": "error", "valid": False, "error": "Licenca invalida. Verifique sua chave."}

@app.post("/api/ea/update")
async def api_ea_update(request: Request):
    data = await request.json()
    key = data.get("key", "")

    db = load_db()
    uid = None
    for k, lic in db.get("licenses", {}).items():
        if lic.get("key") == key:
            uid = k
            break

    if not uid:
        return JSONResponse({"error": "unknown"})

    db.setdefault("ea_data", {})[uid] = {
        "balance": data.get("balance", 0),
        "equity": data.get("equity", 0),
        "profit": data.get("profit", 0),
        "positions": data.get("positions", 0),
        "positions_list": data.get("positions_list", []),
        "last_update": datetime.now().isoformat(),
    }
    save_db(db)
    return {"status": "ok"}

@app.post("/api/ea/trade")
async def api_ea_trade(request: Request):
    data = await request.json()
    key = data.get("key", "")

    db = load_db()
    uid = None
    for k, lic in db.get("licenses", {}).items():
        if lic.get("key") == key:
            uid = k
            break

    if not uid:
        return JSONResponse({"error": "unknown"})

    trade = {
        "id": str(uuid.uuid4())[:8],
        "symbol": data.get("symbol", ""),
        "direction": data.get("direction", ""),
        "lot": data.get("lot", 0),
        "price": data.get("price", 0),
        "ticket": data.get("ticket", 0),
        "status": data.get("status", "open"),
        "profit": data.get("profit", 0),
        "created_at": datetime.now().isoformat(),
    }
    db.setdefault("trades", {}).setdefault(uid, []).append(trade)

    if data.get("status") == "closed":
        config = get_config(uid)
        profit = data.get("profit", 0)
        config["profit"] = config.get("profit", 0) + profit
        if profit >= 0:
            config["wins"] = config.get("wins", 0) + 1
        else:
            config["losses"] = config.get("losses", 0) + 1
        save_config(uid, config)

    save_db(db)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
