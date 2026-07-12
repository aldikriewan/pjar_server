"""
PJAR Server - Backend API (Ubuntu)
Pure backend API tanpa UI
Server hanya expose endpoints JSON untuk client
"""

import os
import random
import socket
import sqlite3
import threading
from pathlib import Path
from email.message import EmailMessage
import smtplib

from flask import Flask, jsonify, request

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-pjar")

# Configuration
DB_PATH = os.environ.get("DATABASE_PATH", Path(__file__).parent / "users.db")
UPLOAD_DIR = os.environ.get("UPLOAD_FOLDER", Path(__file__).parent / "uploads" / "received")
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# SMTP Config (dari environment variables)
SMTP_CONFIG = {
    "MAIL_USERNAME": os.environ.get("MAIL_USERNAME", ""),
    "MAIL_PASSWORD": os.environ.get("MAIL_PASSWORD", ""),
    "MAIL_SERVER": os.environ.get("MAIL_SERVER", "smtp.gmail.com"),
    "MAIL_PORT": os.environ.get("MAIL_PORT", 465),
}

SERVER_STARTED = False


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL
        )
    """)
    conn.commit()
    
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if count == 0:
        conn.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                    ("admin", "admin123", "admin@example.com"))
        conn.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                    ("mahasiswa1", "lulus2026", "mahasiswa1@example.com"))
        conn.commit()
    conn.close()


init_db()


def send_verification_email(recipient: str, code: str) -> bool:
    smtp_user = SMTP_CONFIG.get("MAIL_USERNAME", "")
    smtp_pass = SMTP_CONFIG.get("MAIL_PASSWORD", "")
    if not smtp_user or not smtp_pass:
        print(f"[MAIL] Kode verifikasi untuk {recipient}: {code}")
        return True

    msg = EmailMessage()
    msg["Subject"] = "Kode verifikasi aplikasi PJAR"
    msg["From"] = smtp_user
    msg["To"] = recipient
    msg.set_content(f"Halo,\n\nKode verifikasi Anda adalah: {code}\n\nGunakan kode ini untuk masuk ke aplikasi.")

    try:
        with smtplib.SMTP_SSL(SMTP_CONFIG.get("MAIL_SERVER", "smtp.gmail.com"), 
                             int(SMTP_CONFIG.get("MAIL_PORT", 465))) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"[MAIL] Error: {e}")
        return False


# ============= TCP Upload Server =============
def tcp_upload_handler(conn, addr):
    print(f"[TCP] Client connected: {addr}")
    try:
        data = conn.recv(4096).decode("utf-8", errors="ignore")
        if not data:
            conn.sendall(b"NO_DATA")
            return
        filename, filesize = data.strip().split(":", 1)
        filesize = int(filesize)
        target_path = Path(UPLOAD_DIR) / filename
        received = 0
        with open(target_path, "wb") as handle:
            while received < filesize:
                chunk = conn.recv(min(4096, filesize - received))
                if not chunk:
                    break
                handle.write(chunk)
                received += len(chunk)
        conn.sendall(f"SAVED:{target_path.name}".encode("utf-8"))
        print(f"[TCP] File received: {filename}")
    except Exception as exc:
        conn.sendall(f"ERROR:{exc}".encode("utf-8"))
    finally:
        conn.close()


def tcp_server_thread():
    tcp_host = os.environ.get("TCP_HOST", "0.0.0.0")
    tcp_port = int(os.environ.get("TCP_PORT", 5003))
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((tcp_host, tcp_port))
    server.listen(5)
    print(f"[TCP] Upload server listening on {tcp_host}:{tcp_port}")
    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(target=tcp_upload_handler, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()


# ============= UDP Streaming Server =============
def udp_server_thread():
    udp_host = os.environ.get("UDP_HOST", "0.0.0.0")
    udp_port = int(os.environ.get("UDP_PORT", 5004))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((udp_host, udp_port))
    print(f"[UDP] Streaming server listening on {udp_host}:{udp_port}")
    try:
        while True:
            data, addr = sock.recvfrom(1024)
            if data == b"START":
                sock.sendto(b"STREAM_READY", addr)
                print(f"[UDP] Streaming started for {addr}")
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


def ensure_background_servers():
    global SERVER_STARTED
    if SERVER_STARTED:
        return
    SERVER_STARTED = True
    threading.Thread(target=tcp_server_thread, daemon=True).start()
    threading.Thread(target=udp_server_thread, daemon=True).start()


# ============= API Endpoints =============

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "server": "PJAR Backend"})


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    email = data.get("email", "").strip()

    if not username or not password or not email:
        return jsonify({"error": "Username, password, dan email wajib diisi"}), 400

    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Username sudah terdaftar"}), 409

    conn.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)",
                (username, password, email))
    conn.commit()
    conn.close()
    return jsonify({"message": "Akun berhasil dibuat"}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    conn = get_db_connection()
    user = conn.execute("SELECT username, password, email FROM users WHERE username = ?",
                       (username,)).fetchone()
    conn.close()

    if user and user["password"] == password:
        code = "000000"  # Demo: fixed code
        return jsonify({
            "message": "Login berhasil",
            "username": username,
            "email": user["email"],
            "code": code
        }), 200

    return jsonify({"error": "Username atau password salah"}), 401


@app.route("/api/verify", methods=["POST"])
def verify():
    data = request.get_json()
    code = data.get("code", "").strip()
    expected_code = data.get("expected_code", "").strip()

    if code == expected_code:
        return jsonify({"message": "Verifikasi berhasil"}), 200
    
    return jsonify({"error": "Kode verifikasi salah"}), 401


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Tidak ada file"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Filename kosong"}), 400

    target_path = Path(UPLOAD_DIR) / file.filename
    file.save(target_path)

    try:
        with socket.create_connection(("127.0.0.1", 5003), timeout=3) as sock:
            header = f"{file.filename}:{target_path.stat().st_size}".encode("utf-8")
            sock.sendall(header + b"\n")
            with open(target_path, "rb") as handle:
                while chunk := handle.read(4096):
                    sock.sendall(chunk)
            response = sock.recv(1024).decode("utf-8", errors="ignore").strip()
        return jsonify({"message": "File berhasil dikirim", "filename": file.filename, "response": response}), 200
    except OSError as exc:
        return jsonify({"message": f"File disimpan lokal: {exc}", "filename": file.filename}), 200


@app.route("/api/stream", methods=["POST"])
def stream_video():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.sendto(b"START", ("127.0.0.1", 5004))
            data, _ = sock.recvfrom(1024)
            status = data.decode("utf-8", errors="ignore")
        return jsonify({"message": "Streaming dimulai", "status": status}), 200
    except OSError as exc:
        return jsonify({"error": f"Streaming gagal: {exc}"}), 500


if __name__ == "__main__":
    ensure_background_servers()
    app.run(debug=False, host="0.0.0.0", port=5000)
