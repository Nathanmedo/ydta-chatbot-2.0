# app.py
# This is the main Flask application file.
# It handles the web routes and integrates the chatbot logic from ai_bot.py.

from models import AdminTable, QuestionAnswer,BotSpeedLogs, InteractionTiming, Unanswered
import os
from flask import Flask, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from dotenv import load_dotenv
from flask_cors import CORS
from forms import Loginform, CreateAdminForm
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from admin import init_admin
from ai_bot import get_response, guided_learning_response 
import uuid
from db_utils import init_utils, add_new_interaction, add_speed_log, add_unanswered,add_qa, remove_unanswered
from datetime import datetime
import dotenv
from flask_bcrypt import Bcrypt
from vector import run_sync
 

 
dotenv.load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
MASTER_ADMIN_KEY = os.getenv("MASTER_ADMIN_KEY")  

app = Flask(__name__, static_folder='static', template_folder='templates')

app.config.from_mapping(
    SQLALCHEMY_DATABASE_URI=DATABASE_URL,
    MASTER_ADMIN_KEY= MASTER_ADMIN_KEY
)
CORS(app)
bcrypt = Bcrypt(app)

engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)
scoped_session = Session()
scoped_session2 = Session()

app.secret_key = os.urandom(24) 
init_admin(app)
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. "
                     "Please create a .env file with GEMINI_API_KEY=YOUR_API_KEY.")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.generate_password_hash(plain_password).decode('utf-8')

def check_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a plaintext password with its hashed version."""
    print(f"Checking password against hash: {repr(hashed_password)}")
    print(f"Hash type: {type(hashed_password)}")
    print(f"Hash length: {len(hashed_password) if hashed_password else 'None'}")
    
    # Check if hash looks valid
    if not hashed_password or not hashed_password.startswith(('$2b$', '$2a$', '$2y$')):
        print("Invalid hash format!")
        return False
        
    return bcrypt.check_password_hash(hashed_password, plain_password)

def create_anonymous_id() -> str:
    user_id = str(uuid.uuid4())
    return user_id

def calc_speed(start_time):
    delta = datetime.now() - start_time
    return int(delta.total_seconds())

@app.route('/')
def home():
    """
    Renders the home page of the application.
    """
    return render_template('home.html')

@app.route('/about')
def about():
    """
    Renders the about page.
    """
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """
    Renders the contact page and handles form submissions.
    """
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message = request.form.get('message')
        print(f"Contact form submitted by {name} ({email}). Subject: {subject}. Message: {message}")
        return "<h1>Thank you for your message!</h1><p>We will get back to you shortly.</p>"
    return render_template('contact.html')

@app.route('/chatbot')
def chatbot():
    """
    Renders the main chatbot interface page.
    Initializes a new chat history in the session for the user.
    """
    session['chat_history'] = []
    return render_template('chatbot.html')


@app.route('/ask', methods=['POST'])
def ask():
    start_time = datetime.now()
    user_input = request.json.get('message')

    history =  request.json.get('history', [])
    
    paired_history = []
    temp_user = None

    for msg in history:
        if msg.get("sender") == "user":
            temp_user = msg.get("text")
        elif msg.get("sender") == "bot" and temp_user is not None:
            paired_history.append({
                "user": temp_user,
                "bot": msg.get("text")
            })
            temp_user = None

    chat_history = paired_history

    bot_response, new_history, code, category = get_response(user_input, chat_history, GEMINI_API_KEY)
    session['chat_history'] = new_history

    speed = calc_speed(start_time)
    print("=== Current History ===")
    print(paired_history)

    db_session = init_utils()
    res = add_speed_log(db_session, speed, user_input, start_time, category)
    if code==0:
        res2 = add_unanswered(db_session, user_input, category)
        print(res2)
    db_session.close()

    print(res)

    return jsonify({'response': bot_response}),200


@app.route("/get-unanswered")
def get_unanswered():
    questions = (
        scoped_session2.query(Unanswered)
        .order_by(Unanswered.id.desc())
        .all()
    )
    questions = [q.to_dict() for q in questions]
    
    return jsonify({"data": questions}), 200


 

@app.route("/get-logs")
def get_question():
    logs = scoped_session2.query(BotSpeedLogs).all()
    
    if not logs:
        return jsonify({"average": 0}), 200
    
    total = 0
    length = len(logs)

    for log in logs:
        total += log.time_value

    average = total / length

    return jsonify({
        "average": average
    }), 200

    
@app.route("/edit_unanswered", methods=["POST"])
def add_new():
    data = request.get_json()
    question = data.get("question")
    answer = data.get("answer")
    category = data.get("category")
    un_id = data.get("id")

    res = add_qa(scoped_session, question, answer, category)
    res = run_sync()
    print(res)
    if res["status"] == 1:
        remove_unanswered(scoped_session, un_id)
        run_sync()

    return jsonify(res), 

@app.route('/guided_learning', methods=['POST'])
def guided_learning():
    """
    API endpoint for the guided learning functionality.
    It receives a topic and returns a structured learning plan.
    """
    topic = request.json.get('topic')
    if topic:
        learning_plan = guided_learning_response(topic, GEMINI_API_KEY)
        return jsonify({'response': learning_plan})
    return jsonify({'response': 'Please provide a topic for guided learning.'}), 400



@app.route("/edit-qa", methods=["POST"])
def edit_qa():
    try:
        data = request.get_json()

        qa_id = data.get("id")
        new_question = data.get("question")
        new_answer = data.get("answer")
        new_category = data.get("category")

        if not qa_id:
            return jsonify({"status": 0, "message": "Missing id"}), 400

        # Fetch the row
        row = scoped_session2.query(QuestionAnswer).filter_by(id=qa_id).first()
        if not row:
            return jsonify({"status": 0, "message": "Entry not found"}), 404

        # Update fields if provided
        if new_question is not None:
            row.question = new_question
        if new_answer is not None:
            row.answer = new_answer
        if new_category is not None:
            row.category = new_category

        scoped_session2.commit()
        res = run_sync()
        print(res)
        return jsonify({"status": 1, "message": "Q&A updated successfully"}), 200

    except Exception as e:
        scoped_session2.rollback()
        return jsonify({"status": 0, "message": f"Error: {str(e)}"}), 500

@app.route("/add-qa", methods=["POST"])
def add_qas():
    try:
        data = request.get_json()

        question = data.get("question")
        answer = data.get("answer")
        category = data.get("category")

        if not question or not answer:
            return jsonify({"status": 0, "message": "Question and Answer are required"}), 400

        # Create new entry
        res = add_qa(scoped_session, question, answer, category)

        res = run_sync()
        print(res)
        return jsonify({
            "status": 1,
            "message": "Q&A added successfully",
        }), 201

    except Exception as e:
        scoped_session2.rollback()
        return jsonify({"status": 0, "message": f"Error: {str(e)}"}), 500


@app.route("/fetch-database", methods=["GET"])
def fetch_database():
    try:
        data = scoped_session2.query(QuestionAnswer).all()
        return jsonify({
            "data": [q.to_dict() for q in data]
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Error in fetching from database",
            "details": str(e)
        }), 400


@app.route("/get-interaction-data", methods=["GET"])
def fetch_interaction_data():
    try: 
        data = scoped_session.query(InteractionTiming).all()
        return jsonify({
            "data": [q.to_dict() for q in data]
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Error in fetching interactions",
            "details": str(e)
        }), 400


@app.route("/login" , methods=['GET',"POST"])
def login():
    email_in =  request.json.get('email')
    password_in = request.json.get('password')
    print(email_in, password_in)
    user = scoped_session2.query(AdminTable).filter(AdminTable.email == email_in).first()
    if user:
        print(password_in, user.password)
        is_password_valid = check_password(password_in, user.to_dict().get("password"))
        if is_password_valid:
            session['logged_in'] = True
            flash("Login_successful",'success')
            return jsonify({
                'message': "successful login"
            }), 200
        else:
            return jsonify({
                "message" : "Invalid Password"
            }), 404
    else:
        return jsonify({
                "message" : "Invalid username"
            }), 404



@app.route("/make_admin", methods=["GET", "POST"])
def make_admin():
    form = CreateAdminForm()
    if form.validate_on_submit():
        # Check master key
        print("\n" ,form.master_key.data ,current_app.config.get("MASTER_ADMIN_KEY"), "\n" )
        if form.master_key.data != current_app.config.get("MASTER_ADMIN_KEY"):
            flash("Invalid master key.", "danger")
            return render_template("make_admin.html", form=form)

        email = form.email.data.strip().lower()
        hashed_pw = hash_password(form.password.data)

        exists = scoped_session.query(AdminTable).filter_by(email=email).first()
        if exists:
            flash("An admin with that email already exists.", "warning")
            return render_template("make_admin.html", form=form)

        try:
            new_admin = AdminTable(email=email, password=hashed_pw)
            scoped_session.add(new_admin)
            scoped_session.commit()
            flash("Admin created successfully. You can now log in.", "success")
        except IntegrityError:
            scoped_session.rollback()
            flash("Could not create admin (email may already exist).", "danger")
        except Exception as e:
            scoped_session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template("make_admin.html", form=form)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('home'))


@app.route("/session-duration", methods=["POST"])
def session_duration():
    try:
        data = request.get_json(force=True)  # auto parse JSON
        print("timer payload received:", data)

        duration = data.get("duration")
        session_id = data.get("session_id")
        if duration is None:
            return jsonify({"status": "error", "message": "Missing duration"}), 400

        session = init_utils()
        user_id = session_id

        print("appending started")
        result = add_new_interaction(session, duration, user_id, datetime.now())
        print("DB insert result:", result)

        return jsonify({"status": "success", "duration": duration})

    except Exception as e:
        print("Error parsing session duration:", e)
        return jsonify({"status": "error", "message": str(e)}), 400





if __name__ == '__main__':
    # run_sync_vector()
    app.run(host="0.0.0.0", port=7860)
