import os
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message # Flask-Mail is still used
from dotenv import load_dotenv
from sqlalchemy import func, extract

load_dotenv() # Load environment variables from .env

app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_key_for_dev_gmail')

# Database Configuration 
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/visitors.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask-Mail Configuration (for Gmail)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # Your Gmail address
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') # Your Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
app.config['MAIL_SUPPRESS_SEND'] = app.testing

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')

# --- Initialize Extensions ---
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)

# --- Database Model (Visitor class remains the same as before) ---
class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    visit_month = db.Column(db.Integer, nullable=False)
    visit_year = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<Visitor {self.ip_address} at {self.timestamp}>'

# --- Helper Functions ---
def send_visitor_notification_email(ip_address, user_agent, page_url):
    if not ADMIN_EMAIL or not app.config.get('MAIL_USERNAME'): # Check if mail is configured
        app.logger.warning("Admin email or mail username not configured. Skipping email.")
        return

    try:
        subject = "🎉 New Website Visitor Alert (via Gmail)!"
        body = f"""
        A new visitor just landed on your site!

        Details:
        - IP Address: {ip_address}
        - User Agent: {user_agent or 'N/A'}
        - Page URL: {page_url or 'N/A'}
        - Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

        Notification sent via Flask app using Gmail.
        """
        # The sender for the Message will default to MAIL_DEFAULT_SENDER
        msg = Message(subject=subject, recipients=[ADMIN_EMAIL], body=body)
        mail.send(msg)
        app.logger.info(f"Visitor notification email sent to {ADMIN_EMAIL} via Gmail.")
    except Exception as e:
        # Catching generic Exception is broad, but useful for debugging mail errors
        app.logger.error(f"Error sending visitor email via Gmail: {e}")
        app.logger.error(f"Current Mail Config: SERVER={app.config['MAIL_SERVER']}, PORT={app.config['MAIL_PORT']}, USER={app.config['MAIL_USERNAME'] is not None}")


# --- API Routes (track_visit and get_monthly_visitors remain the same) ---
@app.route('/api/track-visit', methods=['POST'])
def track_visit():
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    page_url = request.json.get('pageURL') if request.is_json else None

    current_time = datetime.now(timezone.utc)
    month = current_time.month
    year = current_time.year

    try:
        new_visitor = Visitor(
            ip_address=ip_address,
            user_agent=user_agent,
            visit_month=month,
            visit_year=year
        )
        db.session.add(new_visitor)
        db.session.commit()

        # Send email notification
        #send_visitor_notification_email(ip_address, user_agent, page_url)

        return jsonify({"message": "Visit tracked successfully"}), 201
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error tracking visit: {e}")
        return jsonify({"error": "Could not track visit"}), 500

@app.route('/api/monthly-visitors', methods=['GET'])
def get_monthly_visitors():
    current_time = datetime.now(timezone.utc)
    month = request.args.get('month', default=current_time.month, type=int)
    year = request.args.get('year', default=current_time.year, type=int)

    try:
        unique_visitor_count = db.session.query(func.count(Visitor.ip_address.distinct())) \
            .filter(Visitor.visit_month == month, Visitor.visit_year == year) \
            .scalar()

        return jsonify({
            "month": month,
            "year": year,
            "unique_visitors": unique_visitor_count + 2 or 2
        }), 200
    except Exception as e:
        app.logger.error(f"Error getting monthly visitor count: {e}")
        return jsonify({"error": "Could not retrieve visitor count"}), 500
    
@app.post("/api/notify-click")
def notify_click():
    data = request.get_json(silent=True) or {}
    kind = data.get("link_kind", "unknown link")
    page = data.get("page", "unknown page")
    ua   = request.headers.get("User-Agent", "unknown UA")

    try:
        
        subject  = f"🎉  [Portfolio] {kind} clicked"
        body    = f"""
                {kind} was clicked!\n 
                page: {page}
                ua: {ua}
                """
        msg = Message(subject=subject, recipients=[ADMIN_EMAIL], body=body)
        mail.send(msg)

    
    except Exception as e:
        # Catching generic Exception is broad, but useful for debugging mail errors
        app.logger.error(f"Error sending visitor email via Gmail: {e}")
        app.logger.error(f"Current Mail Config: SERVER={app.config['MAIL_SERVER']}, PORT={app.config['MAIL_PORT']}, USER={app.config['MAIL_USERNAME'] is not None}")

# --- CORS Handling (remains important) ---
@app.after_request
def after_request(response):
    frontend_url = os.environ.get('FRONTEND_URL', '*') 
    response.headers.add('Access-Control-Allow-Origin', frontend_url)
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# --- Main (database creation logic remains the same) ---
if __name__ == '__main__':
    if not os.path.exists('instance'):
        os.makedirs('instance')
    with app.app_context():
        db.create_all() # Ensures tables are created before running
    app.run(host='0.0.0.0', port=5000)