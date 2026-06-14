from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string, redirect, session
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os, csv, json, glob, threading, hmac, secrets as _pysecrets, requests as _requests
try:
    import cloudscraper as _cloudscraper
    _scraper = _cloudscraper.create_scraper(browser={"browser":"chrome","platform":"windows","mobile":False})
    print("[Sellauth] cloudscraper ready")
except ImportError:
    _scraper = None
    print("[Sellauth] cloudscraper not installed, using requests")

app = Flask(__name__)

# ────────────────────────────────────────────────
# Secret loading — NEVER hardcode credentials in source.
# Values resolve from environment variables first, then from a
# gitignored Api/secrets_local.py (for local/server convenience).
# See secrets_local.example.py for the names you must provide.
# ────────────────────────────────────────────────
try:
    import secrets_local as _secrets_local
except Exception:
    _secrets_local = None

def _secret(name, default=""):
    val = os.getenv(name)
    if val:
        return val
    if _secrets_local is not None and getattr(_secrets_local, name, None):
        return getattr(_secrets_local, name)
    return default

# ────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users_licenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = _secret('JWT_SECRET_KEY', 'dev-insecure-change-me')
app.config['SECRET_KEY']     = _secret('FLASK_SECRET_KEY', 'dev-insecure-change-me')

# Session cookie hardening. SameSite=Lax stops the cookie from riding along on
# cross-site POSTs (the CSRF vector for /verify-invoice). Secure needs HTTPS, so
# it's opt-in via env to avoid breaking the plain-HTTP deployment.
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE']   = os.getenv('SESSION_COOKIE_SECURE', '0') == '1'

# ── Discord ───────────────────────────────────────
DISCORD_CLIENT_ID           = "1477748438190788630"   # public, not a secret
DISCORD_CLIENT_SECRET       = _secret('DISCORD_CLIENT_SECRET')
DISCORD_BOT_TOKEN           = _secret('DISCORD_BOT_TOKEN')   # set via env or secrets_local.py
DISCORD_GUILD_ID            = "1468909781896134790"
DISCORD_VERIFIED_ROLE_ID    = "1477641916165394646"  # must have to access download
DISCORD_BUYER_ROLE_ID       = "1468940254252761098"  # Arena Breakout buyer role
DISCORD_ARC_BUYER_ROLE_ID   = "1495026039842144316"  # Arc Raiders buyer role
DISCORD_ANNOUNCE_CH         = "1479087988766937169"  # Arena Breakout announce channel
DISCORD_ARC_ANNOUNCE_CH     = "1495024400062480454"  # Arc Raiders announce channel
BASE_URL                    = "http://132.145.60.51:5000"

# ── Sellauth ──────────────────────────────────────
SELLAUTH_SHOP_ID = "214568"   # public shop id, not a secret
SELLAUTH_API_KEY = _secret('SELLAUTH_API_KEY')

# ── Admin ─────────────────────────────────────────
# Token required by every /admin/* route. Set via env ADMIN_KEY or
# secrets_local.py. If unset, admin routes fail closed (deny all).
ADMIN_KEY = _secret('ADMIN_KEY')

DISCORD_OAUTH_REDIRECT = f"{BASE_URL}/discord/callback"
DISCORD_OAUTH_URL = (
    "https://discord.com/api/oauth2/authorize"
    f"?client_id={DISCORD_CLIENT_ID}"
    "&response_type=code&scope=identify"
    f"&redirect_uri={DISCORD_OAUTH_REDIRECT}"
)

DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

# Configs folder — put your .json files here
CONFIGS_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'configs')
os.makedirs(CONFIGS_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
jwt = JWTManager(app)

# ── Always return JSON on unhandled errors (never HTML) ──────────────────────
@app.errorhandler(Exception)
def _handle_exception(e):
    import traceback
    print(f"[ERROR] Unhandled exception: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    try:
        db.session.rollback()
    except Exception:
        pass
    from flask import jsonify as _j
    # Details stay in server logs only — never leak type/message to the client.
    return _j({"error": "Internal server error"}), 500

@app.errorhandler(400)
def _bad_request(e):
    from flask import jsonify as _j
    return _j({"error": str(e)}), 400

@app.errorhandler(404)
def _not_found(e):
    from flask import jsonify as _j
    return _j({"error": "Not found"}), 404

# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=True)

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    hwid = db.Column(db.String(64), nullable=False)
    license_key = db.Column(db.String(64), nullable=False)
    license_type = db.Column(db.String(20), nullable=False)
    game = db.Column(db.String(32), nullable=False, default='arena_breakout')  # 'arena_breakout' | 'arc_raiders' | 'both'
    expires_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)

class RedeemedInvoice(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.String(128), unique=True, nullable=False)
    discord_id = db.Column(db.String(32), nullable=True)
    redeemed_at= db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    # ── Auto-migrate old DBs: add any missing columns without losing data ──
    import sqlalchemy as _sa
    with db.engine.connect() as _conn:
        _inspector = _sa.inspect(db.engine)
        _existing_cols = {c['name'] for c in _inspector.get_columns('license')}
        _migrations = []
        if 'game' not in _existing_cols:
            _migrations.append("ALTER TABLE license ADD COLUMN game VARCHAR(32) NOT NULL DEFAULT 'arena_breakout'")
        if 'activated_at' not in _existing_cols:
            _migrations.append("ALTER TABLE license ADD COLUMN activated_at DATETIME")
        for _sql in _migrations:
            try:
                _conn.execute(_sa.text(_sql))
                _conn.commit()
                print(f"[DB MIGRATION] Applied: {_sql}")
            except Exception as _me:
                print(f"[DB MIGRATION] Skipped ({_me}): {_sql}")

# ────────────────────────────────────────────────
# CSV Serial Management
# ────────────────────────────────────────────────
SERIALS_FILE = "serials.csv"

def load_serials():
    serials = {}
    if not os.path.exists(SERIALS_FILE):
        print(f"[WARNING] {SERIALS_FILE} not found → creating empty file")
        with open(SERIALS_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["serial_key", "status"])
        return serials
    with open(SERIALS_FILE, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row["serial_key"].strip()
            status = row.get("status", "available").strip().lower()
            serials[key] = status
    return serials

def save_serials(serials):
    with open(SERIALS_FILE, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["serial_key", "status"])
        for key, status in serials.items():
            writer.writerow([key, status])
    print(f"[INFO] serials.csv updated")

AVAILABLE_SERIALS = load_serials()

# ────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────

@app.route('/update/info', methods=['GET'])
def update_info():
    base_url = "http://132.145.60.51:5000"
    # Single unified zip — both Arena Breakout and Arc Raiders users get the same app
    return jsonify({
        "latest_version": "2.21",
        "download_url": f"{base_url}/downloads/PatoToolBot.zip"
    }), 200


@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email    = data.get('email', '').strip()
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username min 3 characters"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password min 4 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409
    hashed = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed, email=email or None)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "User created"}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_access_token(identity=user.id, expires_delta=timedelta(days=30))
    return jsonify({
        "access_token": token,
        "username": username,
        "has_email": bool(user.email)
    }), 200


@app.route('/account/set_email', methods=['POST'])
@jwt_required()
def set_email():
    user_id = get_jwt_identity()
    data = request.get_json()
    email = (data.get('email') or '').strip()
    if not email or '@' not in email:
        return jsonify({"error": "Invalid email"}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    user.email = email
    db.session.commit()
    return jsonify({"message": "Email saved"}), 200


@app.route('/password/forgot', methods=['POST'])
def password_forgot():
    # Placeholder — always returns success to avoid user enumeration
    return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200


@app.route('/license/status', methods=['GET'])
@jwt_required()
def license_status():
    user_id = get_jwt_identity()
    hwid = request.args.get('hwid', '').strip()
    if not hwid:
        return jsonify({"error": "HWID required"}), 400

    license = License.query.filter_by(user_id=user_id, hwid=hwid).first()

    # If not found by HWID, check if this user has ANY active license and auto-migrate HWID
    if not license:
        now_check = datetime.utcnow()
        for candidate in License.query.filter_by(user_id=user_id).all():
            is_active = (
                candidate.license_type == "forever"
                or (candidate.expires_at is not None and candidate.expires_at > now_check)
            )
            if is_active:
                conflict = License.query.filter_by(hwid=hwid).first()
                if conflict and conflict.user_id != user_id:
                    break  # HWID taken by someone else
                candidate.hwid = hwid
                if not candidate.game:
                    candidate.game = 'arena_breakout'
                try:
                    db.session.commit()
                    license = candidate
                    print(f"[AUTO-MIGRATE] user={user_id} license migrated to hwid={hwid[:12]}...")
                except Exception:
                    db.session.rollback()
                break

    if not license:
        return jsonify({"status": "inactive", "message": "No license found"}), 200

    # Migrate legacy licenses (no game set) to arena_breakout
    if not license.game:
        license.game = 'arena_breakout'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    now = datetime.utcnow()
    game_val = license.game or 'arena_breakout'
    base = {
        "game": game_val,
        "games": _game_list(game_val),
    }
    if license.license_type == "forever":
        return jsonify({**base, "status": "active", "type": "forever", "expires_at": None}), 200
    if license.expires_at:
        if license.expires_at > now:
            return jsonify({
                **base,
                "status": "active",
                "type": license.license_type,
                "expires_at": license.expires_at.isoformat(),
                "days_remaining": (license.expires_at - now).days
            }), 200
        else:
            return jsonify({
                **base,
                "status": "expired",
                "message": "License expired",
                "expires_at": license.expires_at.isoformat()
            }), 200
    return jsonify({"status": "inactive", "message": "Invalid license state"}), 200


def _game_list(game_field):
    """Return a list of allowed game keys from a license game field."""
    if game_field == 'both':
        return ['arena_breakout', 'arc_raiders']
    return [game_field] if game_field else ['arena_breakout']


@app.route('/license/activate', methods=['POST'])
@jwt_required()
def activate_license():
    user_id = get_jwt_identity()
    data = request.get_json()
    serial = (data.get('serial') or '').strip().upper()
    hwid   = (data.get('hwid') or '').strip()
    if not hwid:
        return jsonify({"error": "hwid required"}), 400

    global AVAILABLE_SERIALS

    # ── Peek at what game the new serial is for (before any shortcuts) ───
    def _detect_game_from_serial(s):
        if s.startswith("PATO-AR-"):   return 'arc_raiders'
        if s.startswith("PATO-BOTH-"): return 'both'
        if s.startswith("PATO-AB-"):   return 'arena_breakout'
        return 'arena_breakout'  # legacy default

    new_serial_game = _detect_game_from_serial(serial) if serial else None
    new_serial_games = _game_list(new_serial_game) if new_serial_game else []

    # ── Shortcut: user already has an active license on this HWID ────────
    # Only skip activation if the new serial covers games already licensed.
    current_license = License.query.filter_by(user_id=user_id, hwid=hwid).first()
    if current_license:
        now = datetime.utcnow()
        is_active = (
            current_license.license_type == "forever"
            or (current_license.expires_at is not None and current_license.expires_at > now)
        )
        if is_active:
            existing_games = _game_list(current_license.game or 'arena_breakout')
            # If new serial adds a game not yet licensed → don't shortcut, continue to activate
            new_games_needed = [g for g in new_serial_games if g not in existing_games]
            if not serial or not new_games_needed:
                # No new serial or serial covers already-licensed games → return current license
                game_val = current_license.game or 'arena_breakout'
                resp = {
                    "message": "Already activated",
                    "type": current_license.license_type,
                    "game": game_val,
                    "games": _game_list(game_val),
                    "status": "active",
                }
                if current_license.expires_at:
                    resp["expires_at"] = current_license.expires_at.isoformat()
                    resp["days_remaining"] = max(0, (current_license.expires_at - now).days)
                return jsonify(resp), 200
            # else: fall through — new serial unlocks a new game, process it normally
        else:
            db.session.delete(current_license)
            db.session.commit()
            print(f"[INFO] Expired license removed for hwid={hwid}, allowing renewal")

    # ── Shortcut: user has an active license on ANY hwid (old app / reinstall) ──
    # Only migrate if serial doesn't unlock a new game (pure HWID change scenario)
    if serial:
        # Check if this serial unlocks something new before auto-migrating
        any_active = None
        all_user_lics = License.query.filter_by(user_id=user_id).all()
        now_check = datetime.utcnow()
        for lic in all_user_lics:
            if lic.hwid != hwid and (lic.license_type == "forever" or (lic.expires_at and lic.expires_at > now_check)):
                any_active = lic
                break
        if any_active:
            existing_games = _game_list(any_active.game or 'arena_breakout')
            new_games_needed = [g for g in new_serial_games if g not in existing_games]
            if not new_games_needed:
                # Serial doesn't add new games — this is just an old-app HWID migration
                conflict = License.query.filter_by(hwid=hwid).first()
                if conflict and conflict.user_id != user_id:
                    return jsonify({"error": "HWID bound to different user"}), 403
                any_active.hwid = hwid
                if not any_active.game:
                    any_active.game = 'arena_breakout'
                try:
                    db.session.commit()
                    print(f"[AUTO-MIGRATE] user={user_id} migrated license to hwid={hwid[:12]}...")
                except Exception:
                    db.session.rollback()
                game_val = any_active.game or 'arena_breakout'
                resp = {
                    "message": "Already activated",
                    "type": any_active.license_type,
                    "game": game_val,
                    "games": _game_list(game_val),
                    "status": "active",
                }
                if any_active.expires_at:
                    resp["expires_at"] = any_active.expires_at.isoformat()
                    resp["days_remaining"] = max(0, (any_active.expires_at - now_check).days)
                return jsonify(resp), 200
            # else: new serial adds a new game — fall through to normal activation
    else:
        # No serial provided — try HWID migration only
        any_active = None
        all_user_lics = License.query.filter_by(user_id=user_id).all()
        now_check = datetime.utcnow()
        for lic in all_user_lics:
            if lic.license_type == "forever" or (lic.expires_at and lic.expires_at > now_check):
                any_active = lic
                break
        if any_active:
            conflict = License.query.filter_by(hwid=hwid).first()
            if conflict and conflict.user_id != user_id:
                return jsonify({"error": "HWID bound to different user"}), 403
            any_active.hwid = hwid
            if not any_active.game:
                any_active.game = 'arena_breakout'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            game_val = any_active.game or 'arena_breakout'
            return jsonify({
                "message": "Already activated",
                "type": any_active.license_type,
                "game": game_val,
                "games": _game_list(game_val),
                "status": "active",
            }), 200

    # ── Need a valid serial from here on ─────────────────────────────────
    if not serial:
        return jsonify({"error": "serial required"}), 400

    if serial not in AVAILABLE_SERIALS:
        return jsonify({"error": "Invalid serial key"}), 400

    serial_status = str(AVAILABLE_SERIALS[serial]).lower()

    # If serial is "used" but by THIS user on THIS hwid → was already activated above.
    # If serial is "used" by a different user → reject.
    if serial_status != "available":
        # Check if this serial was used to activate a license for this user
        existing_lic = License.query.filter_by(user_id=user_id, license_key=serial).first()
        if existing_lic:
            # Serial belongs to this user — migrate it to new HWID automatically
            # Check if there's already a DIFFERENT license row on this HWID for this user
            other_lic = License.query.filter_by(user_id=user_id, hwid=hwid).filter(
                License.id != existing_lic.id
            ).first()
            if other_lic:
                # Merge: combine games into the existing row on this HWID
                combined = list(set(_game_list(other_lic.game or 'arena_breakout') + _game_list(existing_lic.game or 'arena_breakout')))
                if set(combined) == {'arena_breakout', 'arc_raiders'}:
                    other_lic.game = 'both'
                else:
                    other_lic.game = combined[0] if len(combined) == 1 else 'both'
                if existing_lic.license_type == 'forever':
                    other_lic.license_type = 'forever'
                    other_lic.expires_at = None
                try:
                    db.session.delete(existing_lic)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                game_val = other_lic.game
                return jsonify({
                    "message": "Activated",
                    "type": other_lic.license_type,
                    "game": game_val,
                    "games": _game_list(game_val),
                    "status": "active",
                }), 200
            # No conflict — just update HWID
            existing_lic.hwid = hwid
            if not existing_lic.game:
                existing_lic.game = 'arena_breakout'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            game_val = existing_lic.game
            resp = {
                "message": "Already activated",
                "type": existing_lic.license_type,
                "game": game_val,
                "games": _game_list(game_val),
                "status": "active",
            }
            if existing_lic.expires_at:
                now = datetime.utcnow()
                resp["expires_at"] = existing_lic.expires_at.isoformat()
                resp["days_remaining"] = max(0, (existing_lic.expires_at - now).days)
            return jsonify(resp), 200
        return jsonify({"error": "Serial key already used"}), 403

    # Check HWID not bound to a different user
    existing_hwid = License.query.filter_by(hwid=hwid).first()
    if existing_hwid and existing_hwid.user_id != user_id:
        return jsonify({"error": "HWID bound to different user"}), 403

    # ── Determine license type, duration and game from serial prefix ──────
    license_type = "forever"
    expires_at   = None
    days         = 0
    game         = 'arena_breakout'

    s = serial
    if s.startswith("PATO-AB-"):
        game = 'arena_breakout';   s = "PATO-" + s[len("PATO-AB-"):]
    elif s.startswith("PATO-AR-"):
        game = 'arc_raiders';      s = "PATO-" + s[len("PATO-AR-"):]
    elif s.startswith("PATO-BOTH-"):
        game = 'both';             s = "PATO-" + s[len("PATO-BOTH-"):]

    if s.startswith("PATO-LIFE-") or "LIFE" in s:
        license_type = "forever";  expires_at = None
    elif "D-" in s:
        try:
            import re as _re
            m = _re.search(r'(\d+)D-', s)
            if m:
                days = int(m.group(1))
                if days > 0:
                    license_type = "timed"
                    expires_at = datetime.utcnow() + timedelta(days=days)
        except Exception:
            license_type = "forever";  expires_at = None
    else:
        license_type = "forever";  expires_at = None

    new_license = License(
        user_id=user_id, hwid=hwid, license_key=serial,
        license_type=license_type, game=game, expires_at=expires_at
    )

    # ── If user already has an active license on this HWID for a different game,
    #    merge into 'both' instead of creating a second row ──────────────────
    merge_target = License.query.filter_by(user_id=user_id, hwid=hwid).first()
    if merge_target:
        existing_games = _game_list(merge_target.game or 'arena_breakout')
        combined = list(set(existing_games + _game_list(game)))
        if set(combined) == {'arena_breakout', 'arc_raiders'}:
            merge_target.game = 'both'
        else:
            merge_target.game = combined[0] if len(combined) == 1 else 'both'
        # Keep the better (longer/forever) license type
        if license_type == 'forever':
            merge_target.license_type = 'forever'
            merge_target.expires_at = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Database error during merge, please try again"}), 500
        AVAILABLE_SERIALS[serial] = "used"
        save_serials(AVAILABLE_SERIALS)
        final_game = merge_target.game
        response = {"message": "Activated", "type": merge_target.license_type,
                    "game": final_game, "games": _game_list(final_game), "status": "active"}
        if merge_target.expires_at:
            response["expires_at"] = merge_target.expires_at.isoformat()
        return jsonify(response), 200

    db.session.add(new_license)
    db.session.commit()
    AVAILABLE_SERIALS[serial] = "used"
    save_serials(AVAILABLE_SERIALS)

    response = {"message": "Activated", "type": license_type, "game": game,
                "games": _game_list(game), "status": "active"}
    if expires_at:
        response["expires_at"] = expires_at.isoformat()
        response["days"] = days
    return jsonify(response), 200


@app.route('/license/migrate', methods=['POST'])
@jwt_required()
def migrate_license():
    """Migrate license from old HWID to new HWID — called automatically by client."""
    user_id  = get_jwt_identity()
    data     = request.get_json()
    old_hwid = (data.get('old_hwid') or '').strip()
    new_hwid = (data.get('new_hwid') or '').strip()
    if not old_hwid or not new_hwid:
        return jsonify({"error": "old_hwid and new_hwid required"}), 400
    if old_hwid == new_hwid:
        return jsonify({"message": "HWIDs identical, no migration needed"}), 200
    old_lic = License.query.filter_by(user_id=user_id, hwid=old_hwid).first()
    if not old_lic:
        return jsonify({"error": "No license found for old HWID"}), 404
    now = datetime.utcnow()
    if old_lic.license_type != "forever":
        if old_lic.expires_at is None or old_lic.expires_at <= now:
            return jsonify({"error": "License is expired"}), 403
    conflict = License.query.filter_by(hwid=new_hwid).first()
    if conflict and conflict.user_id != user_id:
        return jsonify({"error": "New HWID already bound to different user"}), 403
    existing_new = License.query.filter_by(user_id=user_id, hwid=new_hwid).first()
    if existing_new:
        db.session.delete(existing_new)
    old_lic.hwid = new_hwid
    db.session.commit()
    print(f"[MIGRATE] user={user_id} {old_hwid[:12]}... -> {new_hwid[:12]}...")
    return jsonify({"message": "License migrated", "type": old_lic.license_type, "game": old_lic.game or 'arena_breakout', "games": _game_list(old_lic.game or 'arena_breakout')}), 200


# ────────────────────────────────────────────────
# Pre-made Configs
# ────────────────────────────────────────────────

@app.route('/configs', methods=['GET'])
@jwt_required()
def list_configs():
    """Return .json config files for the requested game.

    New layout (both games use subfolders):
        configs/arena_breakout/*.json
        configs/arc_raiders/*.json

    Old clients that call /configs with no ?game= param are silently redirected
    to the arena_breakout subfolder so they keep working unchanged.

    Legacy root configs/*.json files are still served as a fallback for arena_breakout
    so nothing breaks if files haven't been moved yet.

    Query param:
        ?game=arena_breakout   (default for old/missing param)
        ?game=arc_raiders
    """
    VALID_GAMES = {'arena_breakout', 'arc_raiders'}
    game_filter = request.args.get('game', '').strip().lower()
    if game_filter not in VALID_GAMES:
        # Old client sent no ?game= — treat as arena_breakout (silent redirect behaviour)
        game_filter = 'arena_breakout'

    configs = []

    def _load_folder(folder_path):
        pattern = os.path.join(folder_path, '*.json')
        for filepath in sorted(glob.glob(pattern)):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                configs.append({
                    "name":          data.get("name", os.path.splitext(os.path.basename(filepath))[0]),
                    "emoji":         data.get("emoji", "⚙️"),
                    "desc":          data.get("desc", ""),
                    "sequence":      data.get("sequence", []),
                    "filename":      os.path.basename(filepath),
                    "base_res":      data.get("base_res", "1920x1080"),
                    "category":      data.get("category", ""),
                    "category_desc": data.get("category_desc", ""),
                })
            except Exception as e:
                print(f"[WARNING] Skipping bad config {filepath}: {e}")

    # Load from the game's own subfolder
    game_folder = os.path.join(CONFIGS_FOLDER, game_filter)
    os.makedirs(game_folder, exist_ok=True)
    _load_folder(game_folder)

    # Fallback: if arena_breakout subfolder is empty, also check root configs/ folder
    # so old files keep working until you move them into the subfolder
    if game_filter == 'arena_breakout' and not configs:
        print(f"[CONFIGS] arena_breakout subfolder empty — falling back to root configs/")
        _load_folder(CONFIGS_FOLDER)

    return jsonify(configs), 200


# ────────────────────────────────────────────────
# Downloads
# ────────────────────────────────────────────────

@app.route('/downloads/<path:filename>')
def serve_file(filename):
    if filename:
        try:
            return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True, conditional=True)
        except FileNotFoundError:
            abort(404)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Pato's Tool Bot — Download</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
    <style>
        :root { --primary:#6366f1; --primary-dark:#4f46e5; --dark:#111827; --gray:#4b5563; --light:#f9fafb; --border:#e5e7eb; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Inter',system-ui,sans-serif; background:var(--light); color:var(--dark); line-height:1.6; }
        .container { max-width:900px; margin:0 auto; padding:0 24px; }
        header { background:white; border-bottom:1px solid var(--border); position:sticky; top:0; z-index:10; }
        .header-inner { display:flex; justify-content:space-between; align-items:center; padding:20px 0; }
        .logo { font-size:1.6rem; font-weight:700; color:var(--primary-dark); text-decoration:none; }
        main { padding:100px 0 140px; }
        .hero { text-align:center; margin-bottom:60px; }
        .hero h1 { font-size:3rem; font-weight:700; margin-bottom:1rem; }
        .hero p { font-size:1.2rem; color:var(--gray); max-width:600px; margin:0 auto; }
        .download-card { background:white; border-radius:20px; overflow:hidden; border:1px solid var(--border); box-shadow:0 10px 30px rgba(0,0,0,0.08); max-width:520px; margin:0 auto; transition:transform .25s,box-shadow .25s; }
        .download-card:hover { transform:translateY(-8px); box-shadow:0 20px 40px rgba(0,0,0,0.12); }
        .card-header { background:linear-gradient(135deg,var(--primary),var(--primary-dark)); color:white; padding:40px 32px; text-align:center; }
        .card-header h2 { font-size:2.1rem; margin-bottom:.4rem; }
        .card-body { padding:40px 32px; text-align:center; }
        .features { margin:28px 0; color:var(--gray); font-size:1.05rem; }
        .features li { margin-bottom:14px; }
        .btn-download { display:inline-block; padding:18px 48px; background:var(--primary); color:white; text-decoration:none; font-weight:600; font-size:1.25rem; border-radius:12px; transition:all .2s; margin-top:20px; }
        .btn-download:hover { background:var(--primary-dark); transform:translateY(-3px); }
        .meta { margin-top:32px; color:#6b7280; font-size:.95rem; }
        footer { background:white; border-top:1px solid var(--border); padding:60px 0 40px; text-align:center; color:var(--gray); }
    </style>
</head>
<body>
    <header><div class="container"><div class="header-inner"><a href="/" class="logo">Pato's Tool Bot</a></div></div></header>
    <main>
        <div class="container">
            <section class="hero"><h1>Download Latest Version</h1><p>The most up-to-date and recommended release</p></section>
            <div class="download-card">
                <div class="card-header"><h2>Latest Version</h2></div>
                <div class="card-body">
                    <p>Get the current stable release of Pato's Tool Bot.</p>
                    <ul class="features"><li>Latest optimizations & fixes</li><li>Updated protection systems</li><li>Improved performance</li></ul>
                    <a href="/downloads/PatoToolBot.zip" class="btn-download">Download Now</a>
                    <div class="meta">Windows executable • Digitally signed</div>
                </div>
            </div>
        </div>
    </main>
    <footer><div class="container"><p>© 2025–2026 Pato's Tool Bot</p></div></footer>
</body>
</html>"""
    return render_template_string(html)



@app.route('/app/info', methods=['GET'])
def app_info():
    """Returns latest version + download URL for the launcher to check."""
    import hashlib, os
    zip_path = "/home/ubuntu/AbiMarket/downloads/PatoToolBot.zip"
    file_hash = ""
    if os.path.exists(zip_path):
        h = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        file_hash = h.hexdigest()
    return jsonify({
        "version": "2.13",
        "hash": file_hash,
        "download_url": "http://132.145.60.51:5000/app/download"
    }), 200


@app.route('/app/download', methods=['GET'])
def app_download():
    """Serves the unified PatoToolBot.zip — same file for all games."""
    import os
    from flask import send_file
    zip_path = "/home/ubuntu/AbiMarket/downloads/PatoToolBot.zip"
    # Fallback to old name if unified zip not present yet
    if not os.path.exists(zip_path):
        zip_path = "/home/ubuntu/AbiMarket/downloads/PatoToolBot.zip"
    if not os.path.exists(zip_path):
        return jsonify({"error": "App package not found on server"}), 404
    return send_file(zip_path,
                     mimetype="application/zip",
                     as_attachment=True,
                     download_name="PatoToolBot.zip")

def _require_admin():
    """Return None if the caller presented a valid admin token, else a 401 response.

    Token comes from the X-Admin-Token header (preferred) or the legacy ?key=
    query param, compared in constant time against ADMIN_KEY. Fails closed when
    ADMIN_KEY is unset so admin routes are never open by default.
    """
    provided = request.headers.get('X-Admin-Token') or request.args.get('key') or ''
    if ADMIN_KEY and hmac.compare_digest(str(provided), str(ADMIN_KEY)):
        return None
    return jsonify({"error": "Unauthorized"}), 401


@app.route('/admin/serials', methods=['GET'])
def admin_serials():
    denied = _require_admin()
    if denied:
        return denied
    return jsonify(AVAILABLE_SERIALS), 200


@app.route('/admin/invoices', methods=['GET'])
def admin_invoices():
    """List all redeemed invoices."""
    denied = _require_admin()
    if denied:
        return denied
    rows = RedeemedInvoice.query.order_by(RedeemedInvoice.redeemed_at.desc()).all()
    return jsonify([{
        "id": r.id, "invoice_id": r.invoice_id,
        "discord_id": r.discord_id,
        "redeemed_at": r.redeemed_at.isoformat()
    } for r in rows]), 200


@app.route('/admin/invoices/reset', methods=['POST'])
def admin_invoices_reset():
    """Delete all redeemed invoices. Requires X-Admin-Token header (or ?key=)."""
    denied = _require_admin()
    if denied:
        return denied
    count = RedeemedInvoice.query.count()
    RedeemedInvoice.query.delete()
    db.session.commit()
    print(f"[ADMIN] Cleared {count} redeemed invoices")
    return jsonify({"message": f"Cleared {count} invoices"}), 200


@app.route('/admin/invoices/delete/<invoice_id>', methods=['POST'])
def admin_invoice_delete(invoice_id):
    """Delete a single redeemed invoice. Requires X-Admin-Token header (or ?key=)."""
    denied = _require_admin()
    if denied:
        return denied
    row = RedeemedInvoice.query.filter_by(invoice_id=invoice_id).first()
    if not row:
        return jsonify({"error": "Invoice not found"}), 404
    db.session.delete(row)
    db.session.commit()
    print(f"[ADMIN] Deleted invoice {invoice_id}")
    return jsonify({"message": f"Deleted {invoice_id}"}), 200



# ────────────────────────────────────────────────
# Discord helpers
# ────────────────────────────────────────────────
DISCORD_API = "https://discord.com/api/v10"

def _dbot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

def _discord_get_member(user_id):
    r = _requests.get(f"{DISCORD_API}/guilds/{DISCORD_GUILD_ID}/members/{user_id}",
                      headers=_dbot_headers(), timeout=10)
    print(f"[MEMBER] {user_id} → {r.status_code}")
    return r.json() if r.ok else None

def _discord_has_verified(user_id):
    m = _discord_get_member(user_id)
    if not m:
        return False
    return DISCORD_VERIFIED_ROLE_ID in m.get("roles", [])

def _discord_has_buyer(user_id):
    m = _discord_get_member(user_id)
    if not m:
        return False
    return DISCORD_BUYER_ROLE_ID in m.get("roles", [])

def _discord_has_verified_or_buyer(user_id):
    """Returns (has_verified, has_buyer) in one API call."""
    m = _discord_get_member(user_id)
    if not m:
        return False, False
    roles = m.get("roles", [])
    return DISCORD_VERIFIED_ROLE_ID in roles, DISCORD_BUYER_ROLE_ID in roles

def _discord_add_role(user_id, role_id):
    r = _requests.put(f"{DISCORD_API}/guilds/{DISCORD_GUILD_ID}/members/{user_id}/roles/{role_id}",
                      headers=_dbot_headers(), timeout=10)
    print(f"[ADD_ROLE] {user_id} role={role_id} → {r.status_code}")

def _discord_send(channel_id, content):
    _requests.post(f"{DISCORD_API}/channels/{channel_id}/messages",
                   headers=_dbot_headers(), json={"content": content}, timeout=10)

def _discord_send_embed(channel_id, embed, content=""):
    """Send a rich embed message to a channel."""
    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content
    r = _requests.post(f"{DISCORD_API}/channels/{channel_id}/messages",
                       headers=_dbot_headers(), json=payload, timeout=10)
    print(f"[EMBED] channel={channel_id} → {r.status_code}")
    return r

def _discord_exchange_code(code):
    r = _requests.post("https://discord.com/api/oauth2/token", data={
        "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": DISCORD_OAUTH_REDIRECT,
    }, timeout=10)
    return r.json() if r.ok else None

def _discord_get_me(token):
    r = _requests.get(f"{DISCORD_API}/users/@me",
                      headers={"Authorization": f"Bearer {token}"}, timeout=8)
    return r.json() if r.ok else None

# ────────────────────────────────────────────────
# Sellauth helper
# ────────────────────────────────────────────────
def sellauth_verify(invoice_id):
    url = f"https://api.sellauth.com/v1/shops/{SELLAUTH_SHOP_ID}/invoices/{invoice_id.strip()}"
    headers = {"Authorization": f"Bearer {SELLAUTH_API_KEY}", "Accept": "application/json", "Content-Type": "application/json"}
    client = _requests  # use plain requests - api.sellauth.com doesn't need cloudscraper
    try:
        r = client.get(url, headers=headers, timeout=15)
        print(f"[SELLAUTH] {r.status_code} → {r.text[:300]}")
        if r.status_code == 404:
            return {"valid": False, "error": "Invoice not found"}
        if r.status_code == 401:
            return {"valid": False, "error": "Invalid Sellauth API key"}
        if not r.ok:
            return {"valid": False, "error": f"Sellauth error {r.status_code}"}
        data = r.json()
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        status = str(data.get("status", "")).lower()
        if status not in ("completed", "paid", "delivered", "complete", "success", "confirmed"):
            return {"valid": False, "error": f"Invoice not paid (status: {status})"}
        product = data.get("product_title") or data.get("title") or "Pato's Tool Bot"
        return {"valid": True, "product": product, "status": status}
    except Exception as e:
        print(f"[SELLAUTH ERROR] {e}")
        return {"valid": False, "error": str(e)}

def _game_from_product(product_name: str) -> str:
    """Detect game from Sellauth product title."""
    n = product_name.lower()
    if "arc" in n:
        return "arc_raiders"
    return "arena_breakout"

def _buyer_role_for_game(game: str) -> str:
    """Return the correct Discord buyer role ID for a game."""
    if game == "arc_raiders":
        return DISCORD_ARC_BUYER_ROLE_ID
    return DISCORD_BUYER_ROLE_ID

def _announce_ch_for_game(game: str) -> str:
    """Return the correct Discord announce channel ID for a game."""
    if game == "arc_raiders":
        return DISCORD_ARC_ANNOUNCE_CH
    return DISCORD_ANNOUNCE_CH

def _zip_for_game(game: str) -> str:
    """Unified zip — same file for all games."""
    return "PatoToolBot.zip"

# ────────────────────────────────────────────────
# Download page HTML
# ────────────────────────────────────────────────
LATEST_VERSION = "2.21"
DOWNLOAD_FILE  = "PatoToolBot.zip"

DOWNLOAD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Pato's Tool Bot — Download</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Sora:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet"/>
<style>
  :root{
    --void:#06070c; --void2:#0b0d16;
    --panel:rgba(18,20,30,.72); --panel-line:rgba(246,196,83,.16);
    --gold:#f6c453; --gold-hi:#ffe6a6; --gold-deep:#b9842a;
    --ink:#f3efe4; --dim:#8a8fa6; --faint:#5a5f73;
    --discord:#5865f2; --discord2:#404abf;
    --green:#52e0a0; --red:#ff6b6b;
    --r:16px;
  }
  *{margin:0;padding:0;box-sizing:border-box;}
  html{scroll-behavior:smooth;}
  body{
    font-family:'Sora',sans-serif;background:var(--void);color:var(--ink);
    min-height:100vh;display:flex;flex-direction:column;align-items:center;
    position:relative;overflow-x:hidden;-webkit-font-smoothing:antialiased;
  }
  .bg{position:fixed;inset:0;z-index:-2;pointer-events:none;
    background:
      radial-gradient(60% 50% at 78% -5%, rgba(246,196,83,.16), transparent 60%),
      radial-gradient(55% 45% at 12% 8%, rgba(120,90,255,.10), transparent 60%),
      radial-gradient(80% 60% at 50% 120%, rgba(246,196,83,.06), transparent 60%),
      var(--void);
    animation:drift 18s ease-in-out infinite alternate;}
  .grid{position:fixed;inset:0;z-index:-2;pointer-events:none;opacity:.35;
    background-image:linear-gradient(rgba(246,196,83,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(246,196,83,.04) 1px,transparent 1px);
    background-size:46px 46px;
    -webkit-mask-image:radial-gradient(ellipse 70% 60% at 50% 30%,#000 30%,transparent 75%);
    mask-image:radial-gradient(ellipse 70% 60% at 50% 30%,#000 30%,transparent 75%);}
  .grain{position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.05;mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");}
  @keyframes drift{0%{transform:translate3d(0,0,0) scale(1);}100%{transform:translate3d(0,-2%,0) scale(1.05);}}

  header{width:100%;display:flex;align-items:center;gap:14px;padding:20px clamp(20px,5vw,48px);
    border-bottom:1px solid var(--panel-line);background:linear-gradient(180deg,rgba(8,9,15,.8),transparent);
    backdrop-filter:blur(8px);position:sticky;top:0;z-index:20;}
  .logo-duck{font-size:1.9rem;filter:drop-shadow(0 0 10px rgba(246,196,83,.55));animation:bob 4s ease-in-out infinite;}
  @keyframes bob{0%,100%{transform:translateY(0) rotate(-3deg);}50%{transform:translateY(-3px) rotate(3deg);}}
  .logo-text{font-family:'Syne',sans-serif;font-weight:800;font-size:1.15rem;letter-spacing:.5px;
    background:linear-gradient(90deg,var(--gold-hi),var(--gold));-webkit-background-clip:text;background-clip:text;color:transparent;}
  .logo-ver{font-family:'JetBrains Mono',monospace;font-size:.68rem;color:var(--gold);margin-left:auto;
    padding:4px 10px;border:1px solid var(--panel-line);border-radius:99px;letter-spacing:1px;background:rgba(246,196,83,.05);}

  main{flex:1;width:100%;max-width:540px;padding:clamp(36px,8vw,72px) 20px 48px;
    display:flex;flex-direction:column;align-items:center;gap:22px;}
  .eyebrow{font-family:'JetBrains Mono',monospace;font-size:.7rem;letter-spacing:3px;text-transform:uppercase;
    color:var(--gold);opacity:0;animation:rise .6s .05s forwards;}
  .title{font-family:'Syne',sans-serif;font-weight:800;font-size:clamp(1.8rem,6vw,2.5rem);line-height:1.05;
    text-align:center;letter-spacing:-.5px;opacity:0;animation:rise .6s .12s forwards;}
  .title em{font-style:normal;background:linear-gradient(120deg,var(--gold-hi),var(--gold) 55%,var(--gold-deep));
    -webkit-background-clip:text;background-clip:text;color:transparent;}
  .subtitle{color:var(--dim);font-size:.95rem;text-align:center;max-width:32ch;opacity:0;animation:rise .6s .2s forwards;}

  .card{width:100%;background:var(--panel);border:1px solid var(--panel-line);border-radius:var(--r);
    backdrop-filter:blur(16px);box-shadow:0 30px 80px -30px rgba(0,0,0,.8),inset 0 1px 0 rgba(255,255,255,.04);
    overflow:hidden;position:relative;opacity:0;animation:rise .7s .28s forwards;}
  .card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,var(--gold),transparent);opacity:.7;}
  .card-body{padding:clamp(24px,5vw,34px);}

  .steps{display:flex;margin-bottom:30px;}
  .step{flex:1;display:flex;flex-direction:column;align-items:center;gap:9px;position:relative;}
  .step:not(:last-child)::after{content:'';position:absolute;top:17px;left:50%;width:100%;height:2px;background:rgba(255,255,255,.07);}
  .step.done::after{background:linear-gradient(90deg,var(--gold-deep),var(--gold));}
  .step-num{width:36px;height:36px;border-radius:50%;border:1.5px solid rgba(255,255,255,.12);
    display:flex;align-items:center;justify-content:center;font-family:'JetBrains Mono',monospace;
    font-size:.82rem;font-weight:700;color:var(--faint);background:var(--void2);position:relative;z-index:1;transition:all .3s;}
  .step.done .step-num{border-color:var(--gold);color:var(--gold);background:rgba(246,196,83,.1);}
  .step.active .step-num{border-color:var(--gold);color:var(--void);
    background:linear-gradient(135deg,var(--gold-hi),var(--gold));
    box-shadow:0 0 0 4px rgba(246,196,83,.12),0 0 20px rgba(246,196,83,.4);}
  .step-label{font-family:'JetBrains Mono',monospace;font-size:.62rem;letter-spacing:1.5px;text-transform:uppercase;color:var(--faint);}
  .step.done .step-label,.step.active .step-label{color:var(--gold);}

  .flex-col{display:flex;flex-direction:column;align-items:stretch;gap:16px;}
  .center{text-align:center;}

  .btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;width:100%;
    padding:15px 24px;border-radius:11px;border:none;cursor:pointer;text-decoration:none;
    font-family:'Syne',sans-serif;font-weight:700;font-size:.98rem;letter-spacing:.3px;
    position:relative;overflow:hidden;transition:transform .2s,box-shadow .2s;}
  .btn>*{position:relative;z-index:1;}
  .btn::after{content:'';position:absolute;inset:0;transform:translateX(-120%);
    background:linear-gradient(110deg,transparent,rgba(255,255,255,.28),transparent);transition:transform .6s;}
  .btn:hover::after{transform:translateX(120%);}
  .btn-discord{background:linear-gradient(135deg,var(--discord),var(--discord2));color:#fff;}
  .btn-discord:hover{transform:translateY(-2px);box-shadow:0 12px 30px -8px rgba(88,101,242,.6);}
  .btn-gold{background:linear-gradient(135deg,var(--gold-hi),var(--gold) 60%,var(--gold-deep));color:#231a06;}
  .btn-gold:hover{transform:translateY(-2px);box-shadow:0 12px 34px -8px rgba(246,196,83,.55);}

  input[type=text]{width:100%;background:var(--void2);border:1.5px solid rgba(255,255,255,.1);border-radius:11px;
    padding:15px 16px;color:var(--ink);font-family:'JetBrains Mono',monospace;font-size:.92rem;outline:none;
    transition:border-color .2s,box-shadow .2s;}
  input[type=text]:focus{border-color:var(--gold);box-shadow:0 0 0 4px rgba(246,196,83,.12);}
  input[type=text]::placeholder{color:var(--faint);}

  .badge{display:inline-flex;align-items:center;gap:7px;padding:7px 14px;border-radius:99px;
    font-family:'JetBrains Mono',monospace;font-size:.74rem;font-weight:500;letter-spacing:.4px;}
  .badge-ok{background:rgba(82,224,160,.1);color:var(--green);border:1px solid rgba(82,224,160,.28);}
  .badge-err{background:rgba(255,107,107,.1);color:var(--red);border:1px solid rgba(255,107,107,.3);justify-content:center;}

  .user-row{display:flex;align-items:center;gap:10px;justify-content:center;flex-wrap:wrap;color:var(--dim);font-size:.88rem;}
  .user-row strong{color:var(--ink);}
  .sep{height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.1),transparent);}
  .hint{font-size:.82rem;color:var(--dim);text-align:center;line-height:1.65;}
  .hint strong{color:var(--gold);font-weight:600;}
  .label{font-family:'JetBrains Mono',monospace;font-size:.68rem;letter-spacing:1.5px;text-transform:uppercase;color:var(--faint);margin-bottom:-6px;}

  .done-ring{width:84px;height:84px;border-radius:50%;margin:4px auto 2px;display:flex;align-items:center;justify-content:center;
    font-size:2.2rem;background:radial-gradient(circle,rgba(82,224,160,.18),transparent 70%);
    border:1.5px solid rgba(82,224,160,.4);box-shadow:0 0 30px rgba(82,224,160,.25);animation:pop .5s .1s both;}
  @keyframes pop{0%{transform:scale(.5);opacity:0;}60%{transform:scale(1.08);}100%{transform:scale(1);opacity:1;}}

  .progressbar{height:3px;width:100%;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden;margin-top:4px;}
  .progressbar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--gold-deep),var(--gold-hi));animation:fill 1.5s linear forwards;}
  @keyframes fill{to{width:100%;}}

  footer{padding:26px;color:var(--faint);font-size:.74rem;text-align:center;width:100%;
    border-top:1px solid rgba(255,255,255,.05);font-family:'JetBrains Mono',monospace;letter-spacing:.5px;}
  @keyframes rise{0%{opacity:0;transform:translateY(14px);}100%{opacity:1;transform:translateY(0);}}
  @media (max-width:480px){ .step-label{font-size:.55rem;} }
</style>
</head>
<body>
<div class="bg"></div>
<div class="grid"></div>
<div class="grain"></div>
<header>
  <span class="logo-duck">🦆</span>
  <span class="logo-text">Pato's Tool Bot</span>
  <span class="logo-ver">v{{ version }}</span>
</header>
<main>
  <div class="eyebrow">Secure Access Portal</div>
  <h1 class="title">Get <em>Pato's Tool Bot</em></h1>
  <p class="subtitle">Verify your purchase in three quick steps to unlock your download.</p>

  <div class="card">
    <div class="card-body">
      <div class="steps">
        <div class="step {{ 'done' if step > 1 else 'active' }}">
          <div class="step-num">{{ '✓' if step > 1 else '1' }}</div>
          <div class="step-label">Discord</div>
        </div>
        <div class="step {{ 'done' if step > 2 else ('active' if step == 2 else '') }}">
          <div class="step-num">{{ '✓' if step > 2 else '2' }}</div>
          <div class="step-label">Invoice</div>
        </div>
        <div class="step {{ 'active' if step == 3 else '' }}">
          <div class="step-num">3</div>
          <div class="step-label">Download</div>
        </div>
      </div>

      {% if step == 1 %}
      <div class="flex-col center">
        <p class="hint">Sign in with Discord so we can confirm you hold the <strong>Verified</strong> role on our server.</p>
        <a href="{{ oauth_url }}" class="btn btn-discord">
          <svg width="20" height="20" viewBox="0 0 71 55" fill="white"><path d="M60.1 4.9A58.5 58.5 0 0 0 45.5.4a.2.2 0 0 0-.2.1 40.8 40.8 0 0 0-1.8 3.7 54 54 0 0 0-16.2 0A37.7 37.7 0 0 0 25.4.5a.2.2 0 0 0-.2-.1A58.4 58.4 0 0 0 10.6 4.9a.2.2 0 0 0-.1.1C1.5 18.1-.9 31 .3 43.6a.2.2 0 0 0 .1.2 58.8 58.8 0 0 0 17.7 9 .2.2 0 0 0 .2-.1 42 42 0 0 0 3.6-5.9.2.2 0 0 0-.1-.3 38.7 38.7 0 0 1-5.5-2.6.2.2 0 0 1 0-.4l1.1-.8a.2.2 0 0 1 .2 0c11.5 5.3 24 5.3 35.3 0a.2.2 0 0 1 .2 0l1.1.8a.2.2 0 0 1 0 .4 36 36 0 0 1-5.6 2.6.2.2 0 0 0-.1.3 47.1 47.1 0 0 0 3.6 5.9.2.2 0 0 0 .2.1 58.6 58.6 0 0 0 17.8-9 .2.2 0 0 0 .1-.2C72.9 29.4 69.4 16.6 60.2 5a.2.2 0 0 0-.1-.1ZM23.7 36.2c-3.5 0-6.4-3.2-6.4-7.2s2.8-7.2 6.4-7.2c3.6 0 6.5 3.3 6.4 7.2 0 4-2.8 7.2-6.4 7.2Zm23.7 0c-3.5 0-6.4-3.2-6.4-7.2s2.8-7.2 6.4-7.2c3.6 0 6.5 3.3 6.4 7.2 0 4-2.8 7.2-6.4 7.2Z"/></svg>
          <span>Continue with Discord</span>
        </a>
        {% if error %}<span class="badge badge-err">⚠ {{ error }}</span>{% endif %}
        <div class="sep"></div>
        <p class="hint">Don't have the <strong>Verified</strong> role yet? Reach out to support on Discord.</p>
      </div>

      {% elif step == 2 %}
      <div class="flex-col">
        <div class="user-row">
          <span class="badge badge-ok">✓ Verified</span>
          <span>Signed in as <strong>{{ discord_user }}</strong></span>
        </div>
        <div class="sep"></div>
        <span class="label">Sellauth Invoice ID</span>
        <form method="POST" action="/verify-invoice" class="flex-col" style="gap:14px;">
          <input type="hidden" name="csrf" value="{{ csrf_token }}"/>
          <input type="text" name="invoice_id" placeholder="9300de157a26c-0000010499984" autocomplete="off" required/>
          {% if error %}<span class="badge badge-err">⚠ {{ error }}</span>{% endif %}
          <button type="submit" class="btn btn-gold"><span>Confirm Purchase →</span></button>
        </form>
        <p class="hint">Find this in your purchase email. Each invoice can be redeemed <strong>once</strong>.</p>
      </div>

      {% elif step == 3 %}
      <div class="flex-col center">
        <div class="done-ring">🦆</div>
        <span class="badge badge-ok" style="align-self:center;">✓ Welcome to the flock</span>
        <p class="hint">Your <strong>Buyer</strong> role is assigned and your download is starting automatically.</p>
        <a href="{{ download_url }}" class="btn btn-gold"><span>⬇ Download Pato's Tool Bot</span></a>
        <div class="progressbar"><i></i></div>
        <div class="sep"></div>
        <p class="hint" style="font-size:.72rem;">Windows only • Run as Administrator</p>
      </div>
      <script>setTimeout(function(){window.location.href="{{ download_url }}";},1500);</script>
      {% endif %}
    </div>
  </div>
</main>
<footer>🦆 PATO'S TOOL BOT • © 2026 • ALL RIGHTS RESERVED</footer>
</body>
</html>"""

# ────────────────────────────────────────────────
# Download page routes
# ────────────────────────────────────────────────

@app.route('/dl/')
def downloads():
    error = request.args.get('error')
    return render_template_string(DOWNLOAD_PAGE,
        step=1, error=error, version=LATEST_VERSION,
        oauth_url=DISCORD_OAUTH_URL, product='', download_url='', discord_user='')


@app.route('/discord/callback')
def discord_callback():
    code = request.args.get('code')
    if not code:
        return redirect('/dl/?error=No+auth+code')
    tokens = _discord_exchange_code(code)
    if not tokens or 'access_token' not in tokens:
        return redirect('/dl/?error=Discord+auth+failed')
    me = _discord_get_me(tokens['access_token'])
    if not me:
        return redirect('/dl/?error=Could+not+fetch+Discord+user')
    discord_id   = me['id']
    discord_name = me.get('username', 'Unknown')

    has_verified, has_buyer = _discord_has_verified_or_buyer(discord_id)

    # Check Arc Raiders role too
    has_arc_buyer = DISCORD_ARC_BUYER_ROLE_ID in (_discord_get_member(discord_id) or {}).get("roles", [])

    # Already a buyer — skip invoice, go straight to download
    if has_arc_buyer or has_buyer:
        game         = "arc_raiders" if has_arc_buyer else "arena_breakout"
        zip_name     = _zip_for_game(game)
        download_url = f"{BASE_URL}/downloads/{zip_name}"
        print(f"[CALLBACK] {discord_name} already has Buyer role ({game}) — skipping invoice")
        return render_template_string(DOWNLOAD_PAGE,
            step=3, error=None, version=LATEST_VERSION,
            oauth_url='', product="Pato's Tool Bot", download_url=download_url,
            discord_user=discord_name)

    # Not verified and not a buyer — reject
    if not has_verified:
        return redirect('/dl/?error=You+don%27t+have+the+Verified+role.+Contact+support.')

    # Verified but not yet buyer — show invoice step
    session['discord_user'] = {'id': discord_id, 'username': discord_name}
    return render_template_string(DOWNLOAD_PAGE,
        step=2, error=None, version=LATEST_VERSION,
        oauth_url='', product='', download_url='', discord_user=discord_name,
        csrf_token=_csrf_token())


def _csrf_token():
    """Return this session's CSRF token, creating one on first use."""
    tok = session.get('csrf')
    if not tok:
        tok = _pysecrets.token_urlsafe(32)
        session['csrf'] = tok
    return tok


@app.route('/verify-invoice', methods=['POST'])
def verify_invoice():
    discord_info = session.get('discord_user')
    if not discord_info:
        return redirect('/dl/?error=Session+expired,+login+with+Discord+again')
    # CSRF: the posted token must match the one issued when step 2 was rendered.
    sess_tok = session.get('csrf')
    if not sess_tok or not hmac.compare_digest(request.form.get('csrf', ''), sess_tok):
        return redirect('/dl/?error=Session+expired,+login+with+Discord+again')
    invoice_id = request.form.get('invoice_id', '').strip()
    if not invoice_id:
        return render_template_string(DOWNLOAD_PAGE, step=2, error='Please enter invoice ID',
            version=LATEST_VERSION, oauth_url='', product='', download_url='',
            discord_user=discord_info['username'], csrf_token=_csrf_token())
    already = RedeemedInvoice.query.filter_by(invoice_id=invoice_id).first()
    if already:
        return render_template_string(DOWNLOAD_PAGE, step=2, error='Invoice already redeemed',
            version=LATEST_VERSION, oauth_url='', product='', download_url='',
            discord_user=discord_info['username'], csrf_token=_csrf_token())
    result = sellauth_verify(invoice_id)
    if not result['valid']:
        return render_template_string(DOWNLOAD_PAGE, step=2, error=result['error'],
            version=LATEST_VERSION, oauth_url='', product='', download_url='',
            discord_user=discord_info['username'], csrf_token=_csrf_token())
    discord_id   = discord_info['id']
    discord_name = discord_info['username']
    product      = result.get('product', "Pato's Tool Bot")
    game         = _game_from_product(product)
    buyer_role   = _buyer_role_for_game(game)
    announce_ch  = _announce_ch_for_game(game)
    zip_name     = _zip_for_game(game)

    # Product-specific welcome message sent to the correct channel
    if game == "arc_raiders":
        announce_msg = (
            f"🎯 **New Arc Raider Buyer!** `{discord_name}` just grabbed **{product}**! "
            f"Welcome to the squad, time to raid! 🦆🔥"
        )
    else:
        announce_msg = (
            f"🦆 **New Buyer!** `{discord_name}` confirmed purchase of **{product}**! "
            f"Welcome to the Arena! 🎉"
        )

    db.session.add(RedeemedInvoice(invoice_id=invoice_id, discord_id=discord_id))
    db.session.commit()
    threading.Thread(target=_discord_add_role, args=(discord_id, buyer_role), daemon=True).start()
    threading.Thread(target=_discord_send, args=(announce_ch, announce_msg), daemon=True).start()
    session.pop('discord_user', None)
    download_url = f"{BASE_URL}/downloads/{zip_name}"
    print(f"[SUCCESS] discord={discord_name} invoice={invoice_id} game={game}")
    return render_template_string(DOWNLOAD_PAGE, step=3, error=None,
        version=LATEST_VERSION, oauth_url='', product=product,
        download_url=download_url, discord_user=discord_name)


# ────────────────────────────────────────────────
# Discord Bot
# ────────────────────────────────────────────────
def run_discord_bot():
    try:
        import discord
        from discord.ext import commands
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)

        @bot.event
        async def on_ready():
            print(f"[Discord Bot] ✅ Logged in as {bot.user}")

        @bot.command(name="setbuyer")
        @commands.has_permissions(administrator=True)
        async def set_buyer(ctx, member: discord.Member):
            role = ctx.guild.get_role(int(DISCORD_BUYER_ROLE_ID))
            if not role:
                await ctx.send("❌ Buyer role not found."); return
            await member.add_roles(role)
            await ctx.send(f"🦆 **{member.display_name}** is now a Buyer!")

        @bot.command(name="removebuyer")
        @commands.has_permissions(administrator=True)
        async def remove_buyer(ctx, member: discord.Member):
            role = ctx.guild.get_role(int(DISCORD_BUYER_ROLE_ID))
            if not role:
                await ctx.send("❌ Buyer role not found."); return
            await member.remove_roles(role)
            await ctx.send(f"✅ Removed Buyer from **{member.display_name}**")

        @bot.command(name="setverified")
        @commands.has_permissions(administrator=True)
        async def set_verified(ctx, member: discord.Member):
            role = ctx.guild.get_role(int(DISCORD_VERIFIED_ROLE_ID))
            if not role:
                await ctx.send("❌ Verified role not found."); return
            await member.add_roles(role)
            await ctx.send(f"✅ **{member.display_name}** is now Verified!")

        @bot.command(name="removeverified")
        @commands.has_permissions(administrator=True)
        async def remove_verified(ctx, member: discord.Member):
            role = ctx.guild.get_role(int(DISCORD_VERIFIED_ROLE_ID))
            if not role:
                await ctx.send("❌ Verified role not found."); return
            await member.remove_roles(role)
            await ctx.send(f"✅ Removed Verified from **{member.display_name}**")

        @bot.command(name="buyers")
        @commands.has_permissions(administrator=True)
        async def list_buyers(ctx):
            role = ctx.guild.get_role(int(DISCORD_BUYER_ROLE_ID))
            if not role:
                await ctx.send("❌ Buyer role not found."); return
            members = [m.display_name for m in ctx.guild.members if role in m.roles]
            if not members:
                await ctx.send("No buyers yet."); return
            for chunk in [members[i:i+30] for i in range(0, len(members), 30)]:
                await ctx.send("Buyers: " + ", ".join(chunk))

        @bot.command(name="announce")
        @commands.has_permissions(administrator=True)
        async def announce(ctx, *, msg: str):
            ch = bot.get_channel(int(DISCORD_ANNOUNCE_CH))
            if ch:
                await ch.send(f"📢 {msg}"); await ctx.send("✅ Sent!")
            else:
                await ctx.send("❌ Channel not found.")

        @bot.command(name="changelog")
        @commands.has_permissions(administrator=True)
        async def send_changelog(ctx, version: str = "2.13"):
            ch = bot.get_channel(int(DISCORD_ANNOUNCE_CH))
            if not ch:
                await ctx.send("❌ Announce channel not found."); return

            embed = discord.Embed(
                title=f"🦆 Pato's Tool Bot — v{version} Update",
                description="A new version is now available. Update to get the latest fixes and features.",
                color=0xFFD700,
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/duck.png")

            embed.add_field(name="🔧 Bug Fixes & Stability", value=(
                "• Fixed sequence flickering and lag when editing actions\n"
                "• Fixed scroll ghosting on the action list\n"
                "• Fixed scroll jumping multiple rows — now snaps one row per tick\n"
                "• Fixed server crash caused by duplicate admin routes\n"
                "• Fixed `/dl/` download page route conflict"
            ), inline=False)

            embed.add_field(name="⚡ Performance", value=(
                "• Sequence rebuild debounced — rapid changes collapse into one redraw\n"
                "• Drag drop indicator throttled to 30fps — no UI freeze on large sequences\n"
                "• Auto-scroll during drag cancels cleanly on drop"
            ), inline=False)

            embed.add_field(name="🖱️ New: Right-Click Context Menu", value=(
                "• Right-click any action to **Edit, Cut, Copy, Paste Above, Paste Below, Duplicate, Delete**\n"
                "• Clipboard persists — copy once, paste anywhere"
            ), inline=False)

            embed.add_field(name="🔑 HWID Stability Fix", value=(
                "• HWID now uses **CPU + Motherboard + BIOS** instead of MAC/disk/hostname\n"
                "• Prevents license loss after VPN, driver updates, or PC renames\n"
                "• **Existing users auto-migrate on first launch** — nothing to do"
            ), inline=False)

            embed.add_field(name="🌐 Download Page", value=(
                "• Returning buyers with the **Buyer role** skip invoice step and go straight to download\n"
                f"• 📥 [Download v{version}](http://132.145.60.51:5000/dl/)"
            ), inline=False)

            embed.set_footer(text="Pato's Tool Bot • Run as Administrator • Windows only")
            embed.timestamp = discord.utils.utcnow()

            await ch.send(content="@everyone", embed=embed)
            await ctx.send(f"✅ Changelog for v{version} sent!")
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"[Discord Bot] CRASH: {type(e).__name__}: {e}")

def start_bot():
    if DISCORD_BOT_TOKEN in ("YOUR_NEW_BOT_TOKEN", "", None):
        print("[Discord Bot] ⚠ Token not set — update DISCORD_BOT_TOKEN in api.py")
        return
    print(f"[Discord Bot] Starting...")
    threading.Thread(target=run_discord_bot, name="DiscordBot", daemon=False).start()

start_bot()

if __name__ == '__main__':
    print("Pato's Tool Bot Server")
    app.run(host='0.0.0.0', port=5000)