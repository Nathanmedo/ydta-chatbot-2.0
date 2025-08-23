import os
import logging
import threading
from flask import session, redirect, url_for, request, flash
from flask_admin import Admin,expose,  BaseView
from flask_admin.contrib.sqla import ModelView
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from dotenv import load_dotenv

from models import QuestionAnswer, Unanswered, InteractionTiming, BotSpeedLogs, Base
from vector import fetch_data_from_db, init_vector_store, sync_documents


# Load environment variables
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

engine = create_engine(DB_URL, echo=True)
Session = sessionmaker(bind=engine)
scoped_session = Session()

_sync_lock = threading.Lock()


class SecuredModelView(ModelView):
    """Restrict access to logged-in users only."""
    def is_accessible(self):
        return session.get("logged_in")

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("login", next=request.url))


def sync_docs():
    """Rebuild/sync Chroma store with current database state (thread-safe)."""
    logging.info("🔄 Starting Chroma store sync...")

    with _sync_lock:
        try:
            df = fetch_data_from_db()
            logging.info(f"✅ Fetched {len(df)} rows from DB.")
            store = init_vector_store(df)
            sync_documents(df, store)
            logging.info("✅ Chroma store sync completed successfully.")
        except Exception as e:
            logging.error("❌ Error during Chroma sync", exc_info=True)

class SyncNowView(BaseView):
    @expose('/')
    def index(self):
        # Launch sync in a background thread
        threading.Thread(target=sync_docs, daemon=True).start()
        flash("✅ Sync started! Check logs for progress.", "success")
        return redirect(url_for('admin.index'))

class SyncModelView(SecuredModelView):
    """Custom ModelView that triggers a vector sync on changes."""

    def after_model_change(self, form, model, is_created):
        super().after_model_change(form, model, is_created)
        logging.info(f"📌 after_model_change triggered for {model}")
        threading.Thread(target=sync_docs, daemon=True).start()

    def after_model_delete(self, model):
        super().after_model_delete(model)
        logging.info(f"📌 after_model_delete triggered for {model}")
        threading.Thread(target=sync_docs, daemon=True).start()


def init_admin(app):
    """Initialize Flask-Admin with secured & sync-enabled views."""
    admin = Admin(app, name="Chatbot Admin", template_mode="bootstrap4")
    admin.add_view(SyncModelView(QuestionAnswer,scoped_session))
    admin.add_view(SyncModelView(Unanswered, scoped_session))
    admin.add_view(SyncModelView(InteractionTiming, scoped_session))
    admin.add_view(SyncModelView(BotSpeedLogs, scoped_session))
    # Add SyncNow button
    admin.add_view(SyncNowView(name="🔄 Sync Now", endpoint="syncnow"))
    return admin
