import json
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

DB_PATH = "nightcare.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Yahi pe saare tables ban rahe hain.
    Alag schema.sql ki zarurat nahi.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    # Users table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Doctors
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            speciality TEXT NOT NULL,
            rating REAL,
            distance_km REAL
        )
        """
    )

    # Ambulance bookings
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ambulance_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            pickup_location TEXT,
            destination TEXT,
            status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Blood banks
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS blood_banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            units_available INTEGER NOT NULL,
            distance_km REAL
        )
        """
    )

    # Seed doctors (dummy data)
    cur.execute("SELECT COUNT(*) AS c FROM doctors")
    if cur.fetchone()["c"] == 0:
        doctors = [
            ("Dr. Aditi Rao", "emergency", 4.9, 1.2),
            ("Dr. Karan Mehta", "cardio", 4.8, 2.1),
            ("Dr. Sana Ali", "pediatrics", 4.7, 0.9),
        ]
        cur.executemany(
            "INSERT INTO doctors(name, speciality, rating, distance_km) VALUES (?,?,?,?)",
            doctors,
        )

    # Seed blood banks (dummy data)
    cur.execute("SELECT COUNT(*) AS c FROM blood_banks")
    if cur.fetchone()["c"] == 0:
        blood_rows = [
            ("City Blood Center", "A+", 6, 2.1),
            ("City Blood Center", "O+", 4, 2.1),
            ("Metro Blood Bank", "A+", 3, 3.4),
            ("Metro Blood Bank", "O+", 2, 3.4),
            ("Govt. Blood Bank", "A+", 0, 4.1),
        ]
        cur.executemany(
            "INSERT INTO blood_banks(name, blood_group, units_available, distance_km) VALUES (?,?,?,?)",
            blood_rows,
        )

    conn.commit()
    conn.close()


class ApiHandler(BaseHTTPRequestHandler):
    # ---------- Helper methods ----------

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, data, status=200):
        response = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def read_json_body(self):
        length_str = self.headers.get("Content-Length", "0")
        try:
            length = int(length_str)
        except ValueError:
            length = 0

        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    # ---------- CORS preflight ----------

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    # ---------- Routing ----------

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/login":
            self.handle_login()
        elif path == "/api/symptom-checker":
            self.handle_symptom_checker()
        elif path == "/api/ambulance/book":
            self.handle_ambulance_book()
        elif path == "/api/blood/check":
            self.handle_blood_check()
        else:
            self.send_json({"error": "Not found"}, status=404)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/doctors":
            self.handle_doctors()
        else:
            self.send_json({"error": "Not found"}, status=404)

    # ---------- Handlers ----------

    def handle_login(self):
        data = self.read_json_body()
        phone = (data.get("phone") or "").strip()
        otp = (data.get("otp") or "").strip()

        if not phone or not otp:
            self.send_json({"error": "phone and otp required"}, status=400)
            return

        # Demo logic: koi bhi 6-digit OTP ko valid maan lo
        if len(otp) != 6:
            self.send_json({"error": "invalid otp, must be 6 digits"}, status=400)
            return

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO users(phone) VALUES (?)",
            (phone,),
        )
        conn.commit()
        cur.execute("SELECT id, phone, created_at FROM users WHERE phone = ?", (phone,))
        row = cur.fetchone()
        conn.close()

        if row is None:
            self.send_json({"error": "could not create user"}, status=500)
            return

        user = dict(row)
        self.send_json({"status": "ok", "user": user})

    def handle_symptom_checker(self):
        data = self.read_json_body()
        text = (data.get("description") or "").lower()

        if not text.strip():
            self.send_json(
                {
                    "error": "description required",
                    "message": "please describe at least one symptom",
                },
                status=400,
            )
            return

        severity = "mild"
        urgency = "normal"
        problem = "General viral / mild condition"
        recommendation = (
            "Monitor at home, hydrate well & consult online if symptoms persist."
        )

        if any(k in text for k in ["chest", "stroke", "unconscious"]):
            severity = "critical"
            urgency = "emergency"
            problem = "Possible cardiac / neurological emergency"
            recommendation = (
                "Immediate ambulance required. Do NOT drive yourself. "
                "Start CPR if not breathing."
            )
        elif "breath" in text or "difficulty breathing" in text or "asthma" in text:
            severity = "high"
            urgency = "urgent"
            problem = "Breathing difficulty / possible asthma or lung issue"
            recommendation = (
                "Use inhaler if prescribed & seek emergency department or "
                "ambulance if worsening."
            )
        elif "bleeding" in text or "blood" in text:
            severity = "high"
            urgency = "urgent"
            problem = "Significant bleeding"
            recommendation = (
                "Apply firm pressure, keep limb elevated & visit nearest emergency within 30 minutes."
            )
        elif "fever" in text or "temperature" in text:
            severity = "moderate"
            urgency = "normal"
            problem = "Fever / infection-like symptoms"
            recommendation = (
                "Hydrate, use paracetamol as advised & book online doctor if "
                "more than 48h or very high fever."
            )

        self.send_json(
            {
                "possible_problem": problem,
                "severity": severity,
                "urgency": urgency,
                "recommendation": recommendation,
            }
        )

    def handle_doctors(self):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, speciality, rating, distance_km FROM doctors ORDER BY distance_km ASC"
        )
        rows = cur.fetchall()
        conn.close()
        doctors = [dict(r) for r in rows]
        self.send_json({"doctors": doctors})

    def handle_ambulance_book(self):
        data = self.read_json_body()
        phone = (data.get("phone") or "").strip()
        pickup = (data.get("pickup_location") or "").strip()
        dest = (data.get("destination") or "").strip()

        if not pickup:
            self.send_json({"error": "pickup_location required"}, status=400)
            return

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ambulance_bookings(user_phone, pickup_location, destination, status)
            VALUES (?, ?, ?, ?)
            """,
            (phone, pickup, dest, "BOOKED"),
        )
        booking_id = cur.lastrowid
        conn.commit()
        conn.close()

        self.send_json(
            {
                "status": "ok",
                "booking_id": booking_id,
                "eta_minutes": 5,
                "message": "Ambulance booked, driver will contact you shortly.",
            }
        )

    def handle_blood_check(self):
        data = self.read_json_body()
        group = (data.get("blood_group") or "").strip().upper()

        if not group:
            self.send_json({"error": "blood_group required"}, status=400)
            return

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT name, units_available, distance_km
            FROM blood_banks
            WHERE blood_group = ?
            ORDER BY distance_km ASC
            """,
            (group,),
        )
        rows = cur.fetchall()
        conn.close()

        banks = [dict(r) for r in rows]
        self.send_json({"blood_group": group, "banks": banks})


def run_server(port=8000):
    init_db()
    server_address = ("", port)
    httpd = HTTPServer(server_address, ApiHandler)
    print(f"Backend running on http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
