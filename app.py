import re
import sqlite3
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
import base64
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import xmltodict
from werkzeug.security import check_password_hash, generate_password_hash


ENV_PATH = Path(__file__).with_name(".env")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(ENV_PATH)


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
DEFAULT_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("FLASK_PORT", "5001"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DB_PATH = Path(__file__).with_name("app.db")


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scan_type TEXT NOT NULL,
                query TEXT NOT NULL,
                verdict TEXT,
                score INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )


init_db()


@app.context_processor
def inject_current_user():
    return {"current_user": current_user()}


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to view search history.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None

    with get_db_connection() as connection:
        user = connection.execute(
            "SELECT id, username, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return dict(user) if user else None


def save_scan_history(scan_type: str, query: str, verdict: str | None, score: int | None) -> None:
    user_id = session.get("user_id")
    if not user_id:
        return

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO search_history (user_id, scan_type, query, verdict, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, scan_type, query, verdict, score),
        )
        connection.commit()


def render_home(**context):
    return render_template(
        "index.html",
        current_user=current_user(),
        **context,
    )


def render_about():
    return render_template("about.html", current_user=current_user())


def user_history():
    user = current_user()
    if not user:
        return []

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT scan_type, query, verdict, score, created_at
            FROM search_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (user["id"],),
        ).fetchall()

    return [dict(row) for row in rows]


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All sign-up fields are required.", "error")
            return render_template("signup.html")

        with get_db_connection() as connection:
            existing_user = connection.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()

            if existing_user:
                flash("That username or email is already registered.", "error")
                return render_template("signup.html")

            connection.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password)),
            )
            connection.commit()

        flash("Account created. Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Enter your email or username and password.", "error")
            return render_template("login.html")

        with get_db_connection() as connection:
            user = connection.execute(
                """
                SELECT id, username, email, password_hash
                FROM users
                WHERE lower(username) = ? OR lower(email) = ?
                """,
                (identifier, identifier),
            ).fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash("Signed in successfully.", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


@app.route("/about")
def about():
    return render_about()


@app.route("/history")
@login_required
def history():
    return render_template("history.html", history_items=user_history())


def extract_first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>'\"]+|www\.[^\s<>'\"]+", text)
    if not match:
        return None

    return match.group(0)


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>'\"]+|www\.[^\s<>'\"]+", text)


def normalize_url(raw_url: str) -> str:
    return raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"


def analyze_message(message: str) -> dict:
    lower_message = message.lower()
    urls = [normalize_url(url) for url in extract_urls(message)]
    reasons = []
    score = 0

    suspicious_phrases = [
        "urgent",
        "immediately",
        "verify",
        "password",
        "account suspended",
        "click here",
        "action required",
        "limited time",
        "won",
        "gift card",
        "suspicious login",
        "confirm your account",
        "reset your password",
    ]

    for phrase in suspicious_phrases:
        if phrase in lower_message:
            score += 1
            reasons.append(f"Contains suspicious phrase: {phrase}")

    if urls:
        score += len(urls)
        reasons.append(f"Contains {len(urls)} link(s)")

    if any(word in lower_message for word in ["bank", "invoice", "wire", "crypto", "reward"]):
        score += 1
        reasons.append("Contains potentially high-risk financial language")

    if message.isupper() and len(message) > 20:
        score += 1
        reasons.append("Message uses excessive capitalization")

    if score >= 4:
        verdict = "Likely phishing"
    elif score >= 2:
        verdict = "Suspicious"
    else:
        verdict = "Looks normal"

    return {
        "verdict": verdict,
        "score": score,
        "reasons": reasons,
        "urls": urls,
    }


def analyze_message_with_gemini(message: str) -> dict:
    if not GEMINI_API_KEY:
        analysis = analyze_message(message)
        analysis["source"] = "heuristic"
        analysis["ai_note"] = "Gemini API key is missing, so a local heuristic was used."
        return analysis

    prompt = f"""
You are a cybersecurity analyst reviewing a suspicious email or message.
Analyze the message and return ONLY valid JSON with these keys:
verdict: one of ["Likely phishing", "Suspicious", "Looks normal"]
score: integer from 0 to 10
summary: one short sentence
reasons: array of short strings
urls: array of extracted URLs, or []
recommendation: one short sentence

Message:
{message}
"""

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        .strip()
    )

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = analyze_message(message)
        parsed["source"] = "heuristic"
        parsed["ai_note"] = "Gemini returned an unstructured response, so a local heuristic was used."
        return parsed

    urls = parsed.get("urls") or extract_urls(message)
    if urls:
        urls = [normalize_url(url) for url in urls]

    return {
        "verdict": parsed.get("verdict", "Suspicious"),
        "score": parsed.get("score", 0),
        "summary": parsed.get("summary", ""),
        "reasons": parsed.get("reasons", []),
        "urls": urls,
        "recommendation": parsed.get("recommendation", ""),
        "source": "gemini",
    }


def analyze_url_with_gemini(url: str, whois_result: dict | None) -> dict:
    whois_summary = whois_result or {}
    normalized_url = normalize_url(url)

    def heuristic_result(note: str | None = None) -> dict:
        score = 0
        reasons = []
        domain = urlparse(normalized_url).netloc or normalized_url

        if domain.count(".") >= 2:
            score += 1
            reasons.append("Domain uses multiple subdomains")
        if whois_summary.get("Registrar"):
            reasons.append(f"Registrar reported as {whois_summary['Registrar']}")
        if not whois_summary.get("Domain"):
            score += 1
            reasons.append("WHOIS data was incomplete")

        verdict = "Suspicious" if score >= 2 else "Looks normal"
        result = {
            "verdict": verdict,
            "score": score,
            "summary": f"Local review of {domain} completed without Gemini.",
            "reasons": reasons,
            "urls": [normalized_url],
            "recommendation": "Review the domain and WHOIS details before interacting.",
            "source": "heuristic",
        }
        if note:
            result["ai_note"] = note
        return result

    if not GEMINI_API_KEY:
        return heuristic_result("Gemini API key is missing, so a local heuristic was used.")

    prompt = f"""
You are a cybersecurity analyst reviewing a website.
Analyze the URL and WHOIS information and return ONLY valid JSON with these keys:
verdict: one of ["Likely phishing", "Suspicious", "Looks normal"]
score: integer from 0 to 10
summary: one short sentence
reasons: array of short strings
urls: array containing the scanned URL
recommendation: one short sentence

URL:
{normalize_url(url)}

WHOIS:
{json.dumps(whois_summary, indent=2)}
"""

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return heuristic_result("Gemini request failed, so a local heuristic was used.")

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        .strip()
    )

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return heuristic_result("Gemini returned an unstructured response, so a local heuristic was used.")

    urls = parsed.get("urls") or [normalized_url]
    urls = [normalize_url(item) for item in urls]

    return {
        "verdict": parsed.get("verdict", "Suspicious"),
        "score": parsed.get("score", 0),
        "summary": parsed.get("summary", ""),
        "reasons": parsed.get("reasons", []),
        "urls": urls,
        "recommendation": parsed.get("recommendation", ""),
        "source": "gemini",
    }


def build_url_context(raw_url: str) -> dict:
    screenshot_url = normalize_url(raw_url)
    parsed_url = urlparse(screenshot_url)
    domain_name = parsed_url.netloc or parsed_url.path

    try:
        screenshot_response = requests.get(f"https://image.thum.io/get/{screenshot_url}", timeout=60)
        screenshot_response.raise_for_status()
        image_data = base64.b64encode(screenshot_response.content).decode('utf-8')
    except requests.RequestException:
        return {
            "result": None,
            "image_data": None,
            "url": screenshot_url,
            "whois_error": "Unable to fetch a screenshot for this URL.",
        }

    api_key = os.getenv("WHOISXML_API_KEY")
    if not api_key:
        return {
            "result": None,
            "image_data": image_data,
            "url": screenshot_url,
            "whois_error": "Missing WHOISXML_API_KEY in .env",
        }

    result = None
    try:
        whois_response = requests.get(
            "https://www.whoisxmlapi.com/whoisserver/WhoisService",
            params={
                "apiKey": api_key,
                "domainName": domain_name,
                "outputFormat": "XML",
            },
            timeout=30,
        )
        if whois_response.status_code == 200:
            data = xmltodict.parse(whois_response.text)
            whois = data.get("WhoisRecord", {})
            result = {
                "Domain": whois.get("domainName"),
                "Registrar": whois.get("registrarName"),
                "Created": whois.get("createdDate"),
                "Updated": whois.get("updatedDate"),
                "Expires": whois.get("expiresDate"),
                # "Status": whois.get("status"),
            }

            with open("image.png", "wb") as image_file:
                image_file.write(screenshot_response.content)
    except requests.RequestException:
        return {
            "result": None,
            "image_data": image_data,
            "url": screenshot_url,
            "whois_error": "Unable to fetch WHOIS metadata for this URL.",
        }

    gemini_result = analyze_url_with_gemini(screenshot_url, result)

    return {
        "result": result,
        "image_data": image_data,
        "url": screenshot_url,
        "gemini_result": gemini_result,
    }

@app.route('/')
def home():
    return render_home()

@app.route('/search_with_url',methods=['post'])
def url_screenshot():
    raw_url = request.form['url'].strip()
    if not raw_url:
        return render_template('res.html', result=None, image_data=None, url=None, whois_error='Please enter a URL to scan.')

    context = build_url_context(raw_url)
    gemini_result = context.get("gemini_result") or {}
    save_scan_history(
        "url",
        context.get("url", raw_url),
        gemini_result.get("verdict"),
        gemini_result.get("score"),
    )
    return render_template('res.html', **context)


@app.route('/search_with_file',methods=['post'])
def virus_total_res():
    api_key = os.getenv("VIRUSTOTAL_API_KEY")
    if not api_key:
        return render_template('res.html', vt_error='Missing VIRUSTOTAL_API_KEY in .env')

    uploaded_file = request.files.get('file') or request.files.get('url')

    if not uploaded_file or uploaded_file.filename == '':
        return render_template('res.html', vt_error='Please choose a file to scan.')

    headers = {'x-apikey': api_key}
    upload_response = requests.post(
        'https://www.virustotal.com/api/v3/files',
        headers=headers,
        files={'file': (uploaded_file.filename, uploaded_file.stream, uploaded_file.mimetype or 'application/octet-stream')},
        timeout=120,
    )
    upload_response.raise_for_status()
    analysis_id = upload_response.json()['data']['id']

    analysis = None
    for _ in range(12):
        analysis_response = requests.get(
            f'https://www.virustotal.com/api/v3/analyses/{analysis_id}',
            headers=headers,
            timeout=30,
        )
        analysis_response.raise_for_status()
        analysis = analysis_response.json()
        if analysis.get('data', {}).get('attributes', {}).get('status') == 'completed':
            break
        time.sleep(5)

    attributes = analysis.get('data', {}).get('attributes', {}) if analysis else {}
    stats = attributes.get('stats', {})

    vt_result = {
        'filename': uploaded_file.filename,
        'analysis_id': analysis_id,
        'status': attributes.get('status'),
        'malicious': stats.get('malicious'),
        'suspicious': stats.get('suspicious'),
        'harmless': stats.get('harmless'),
        'undetected': stats.get('undetected'),
        'timeout': stats.get('timeout'),
        'analysis_date': attributes.get('date'),
    }

    save_scan_history(
        "file",
        uploaded_file.filename,
        vt_result.get("status"),
        vt_result.get("malicious"),
    )

    return render_template('res.html', vt_result=vt_result)



@app.route('/search_with_message',methods=['post'])
def ml_res():
    message = request.form.get('message', '').strip()
    if not message:
        return render_template('res.html', result=None, image_data=None, url=None, message_error='Please paste a message or content to scan.')

    message_result = analyze_message_with_gemini(message)
    extracted_url = message_result["urls"][0] if message_result["urls"] else None

    context = {
        "message": message,
        "message_result": message_result,
        "gemini_result": message_result,
        "image_data": None,
        "result": None,
        "url": extracted_url,
    }

    if extracted_url:
        try:
            context.update(build_url_context(extracted_url))
        except requests.RequestException:
            context["url"] = extracted_url
            context["whois_error"] = "Unable to fetch URL metadata for the link in the message."

    save_scan_history(
        "message",
        message,
        message_result.get("verdict"),
        message_result.get("score"),
    )

    return render_template('res.html', **context)

if __name__ == "__main__":
    app.run(
        # host=DEFAULT_HOST,
        host="0.0.0.0",
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
        port=DEFAULT_PORT,
    )