import json
import os
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import base64

from flask import Flask, render_template, request, jsonify, Response
import qrcode

app = Flask(__name__)  # REQUIRED

# --- Scanner Basic Auth configuration ---
SCANNER_USERNAME = os.environ.get("SCANNER_USERNAME", "admin")
SCANNER_PASSWORD = os.environ.get("SCANNER_PASSWORD", "secret123")


def _check_scanner_auth(auth):
    return auth and auth.username == SCANNER_USERNAME and auth.password == SCANNER_PASSWORD


def _scanner_auth_required():
    return Response(
        "Authentification requise.", 401,
        {"WWW-Authenticate": 'Basic realm="Scanner"'},
    )


DATA_DIR = "data"
PARTICIPANTS_FILE = os.path.join(DATA_DIR, "participants.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.txt")

# Default config (Render compatible)
EVENT_DATE = datetime.today().date().isoformat()
START_HOUR = 9
END_HOUR = 21
CAPACITY_PER_HOUR = 40
MAX_CODES = 499


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PARTICIPANTS_FILE):
        with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_config():
    global EVENT_DATE, START_HOUR, END_HOUR, CAPACITY_PER_HOUR, MAX_CODES

    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(f"EVENT_DATE={EVENT_DATE}\n")
            f.write(f"START_HOUR={START_HOUR}\n")
            f.write(f"END_HOUR={END_HOUR}\n")
            f.write(f"CAPACITY_PER_HOUR={CAPACITY_PER_HOUR}\n")
            f.write(f"MAX_CODES={MAX_CODES}\n")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().upper()
            value = value.strip()

            if key == "EVENT_DATE":
                EVENT_DATE = value
            elif key == "START_HOUR":
                START_HOUR = int(value)
            elif key == "END_HOUR":
                END_HOUR = int(value)
            elif key == "CAPACITY_PER_HOUR":
                CAPACITY_PER_HOUR = int(value)
            elif key == "MAX_CODES":
                MAX_CODES = int(value)


def load_participants():
    # Self-heal file
    if not os.path.exists(PARTICIPANTS_FILE):
        ensure_dirs()

    try:
        with open(PARTICIPANTS_FILE, "r", encoding="utf-8") as f:
            data = f.read().strip()
            if not data:
                raise ValueError("empty")
            return json.loads(data)
    except Exception:
        with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []


def save_participants(data):
    with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- QR GENERATOR ---
def generate_qr_data_url(text: str) -> str:
    try:
        img = qrcode.make(text)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print("QR ERROR:", e)
        return ""


# --- SLOT ASSIGNMENT ---
def next_available_slot(participants):
    per_hour = {}

    for p in participants:
        slot = p.get("slot_time")
        if not slot:
            continue
        hour_key = slot[:13]
        per_hour[hour_key] = per_hour.get(hour_key, 0) + 1

    for hour in range(START_HOUR, END_HOUR):
        dh = f"{EVENT_DATE}T{hour:02d}:00"
        if per_hour.get(dh, 0) < CAPACITY_PER_HOUR:
            return datetime.strptime(dh, "%Y-%m-%dT%H:%M")

    return None


# ------------------------
#        SIGNUP
# ------------------------
@app.route("/", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    zip_code = request.form.get("zip_code", "").strip().upper()
    civic_number = request.form.get("civic_number", "").strip()
    apartment = request.form.get("apartment", "").strip().upper()

    if not (full_name and phone and zip_code and civic_number):
        return render_template(
            "signup.html",
            error="Tous les champs obligatoires doivent être remplis.",
        ), 400

    # -----------------------------------------
    # GEO-LOCK: MUST BE AT SPECIFIC LOCATION
    # -----------------------------------------
    TARGET_LAT = 46.801970
    TARGET_LON = -71.294570
    MAX_DISTANCE_KM = 0.25  # 250 m radius

    user_lat = request.form.get("lat")
    user_lon = request.form.get("lon")

    def distance_km(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, sqrt, atan2
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return 2 * R * atan2(sqrt(a), sqrt(1 - a))

    if not user_lat or not user_lon:
        return render_template(
            "signup.html",
            error="Vous devez être à « 2800 Ave Saint-Jean-Baptiste, Québec City, Quebec G2E 6J5 » pour vous inscrire.",
        ), 400

    try:
        dist = distance_km(float(user_lat), float(user_lon), TARGET_LAT, TARGET_LON)
    except Exception:
        return render_template(
            "signup.html",
            error="Erreur de géolocalisation. Activez la localisation et réessayez.",
        ), 400

    if dist > MAX_DISTANCE_KM:
        return render_template(
            "signup.html",
            error="Vous devez être à « 2800 Ave Saint-Jean-Baptiste, Québec City, Quebec G2E 6J5 » pour vous inscrire.",
        ), 400

    # -----------------------------------------
    # CONTINUE NORMAL LOGIC
    # -----------------------------------------
    ensure_dirs()
    participants = load_participants()

    # ONE ENTRY PER HOUSEHOLD
    new_household_key = f"{zip_code}|{civic_number}|{apartment}"

    for p in participants:
        if p.get("household_key") == new_household_key:
            return render_template(
                "signup.html",
                error="Ce foyer est déjà inscrit.",
            ), 400

    slot_dt = next_available_slot(participants)
    if slot_dt is None:
        return render_template(
            "signup.html",
            error="Tous les créneaux sont complets.",
        ), 400

    token = uuid4().hex
    qr_data_url = generate_qr_data_url(token)

    participant = {
        "id": uuid4().hex,
        "token": token,
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "zip_code": zip_code,
        "civic_number": civic_number,
        "apartment": apartment,
        "household_key": new_household_key,
        "slot_time": slot_dt.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "checked_in": False,
    }

    participants.append(participant)
    save_participants(participants)

    return render_template(
        "success.html",
        participant=participant,
        event_date=EVENT_DATE,
        slot_local=slot_dt.strftime("%H:%M"),
        qr_data_url=qr_data_url,
    )

    ensure_dirs()
    participants = load_participants()

    # ------------------------------
    # 🚨 ONE ENTRY PER HOUSEHOLD RULE
    # ------------------------------
    new_household_key = f"{zip_code}|{civic_number}|{apartment}"

    for p in participants:
        if p.get("household_key") == new_household_key:
            return render_template(
                "signup.html",
                error="Ce foyer est déjà inscrit."
            ), 400

    # ------------------------------

    slot_dt = next_available_slot(participants)
    if slot_dt is None:
        return render_template(
            "signup.html",
            error="Tous les créneaux sont complets."
        ), 400

    token = uuid4().hex
    qr_data_url = generate_qr_data_url(token)

    participant = {
        "id": uuid4().hex,
        "token": token,
        "full_name": full_name,
        "phone": phone,
        "email": email,
        "zip_code": zip_code,
        "civic_number": civic_number,
        "apartment": apartment,
        "household_key": new_household_key,
        "slot_time": slot_dt.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "checked_in": False,
    }

    participants.append(participant)
    save_participants(participants)

    return render_template(
        "success.html",
        participant=participant,
        event_date=EVENT_DATE,
        slot_local=slot_dt.strftime("%H:%M"),
        qr_data_url=qr_data_url,
    )


# ------------------------
#         SCANNER
# ------------------------
@app.route("/scanner")
def scanner():
    auth = request.authorization
    if not _check_scanner_auth(auth):
        return _scanner_auth_required()
    return render_template("scanner.html")


@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token")

    if not token:
        return jsonify({"status": "error", "message": "Missing token."}), 400

    ensure_dirs()
    participants = load_participants()

    p = next((x for x in participants if x.get("token") == token), None)
    if not p:
        remaining = MAX_CODES - sum(x.get("checked_in") for x in participants)
        return jsonify({"status": "error", "message": "Invalid code.", "remaining": remaining}), 404

    if p.get("checked_in"):
        remaining = MAX_CODES - sum(x.get("checked_in") for x in participants)
        return jsonify({"status": "error", "message": "Code déjà utilisé.", "remaining": remaining}), 400

    p["checked_in"] = True
    save_participants(participants)

    remaining = MAX_CODES - sum(x.get("checked_in") for x in participants)

    return jsonify({
        "status": "ok",
        "name": p["full_name"],
        "slot_time": p["slot_time"],
        "remaining": remaining
    })


# ------------------------
#     MAIN (Render OK)
# ------------------------
if __name__ == "__main__":
    ensure_dirs()
    load_config()
    app.run(host="0.0.0.0", port=5000, debug=True)
