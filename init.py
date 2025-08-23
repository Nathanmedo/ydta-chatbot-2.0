## this should be run once

from sqlalchemy import create_engine, inspect
from models import Base, QuestionAnswer
import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy.orm import sessionmaker

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
print(f"Using DATABASE_URL: {DB_URL}")
OVERHAUL_FILE = './overhaul.csv'

def init_db():
    db_url = DB_URL
    if not db_url:
        raise ValueError("\n\n DATABASE_URL not found in environment. Please set it in .env")
    if db_url.startswith("postgresq://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables in database: {tables}")
    print("✅ Database initialized: tables created.")
    
def overhaul_db():
    if not DB_URL:
        raise ValueError("\n\n]DATABASE_URL not found in environment. Please set it in .env")

    engine = create_engine(DB_URL, echo=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    QuestionAnswer.__table__.drop(engine, checkfirst=True)
    QuestionAnswer.__table__.create(engine, checkfirst=True)

    df = pd.read_csv(OVERHAUL_FILE)

    new_rows = []
    for _, row in df.iterrows():
        qa = QuestionAnswer(
            question=row.get("Question"),
            answer=row.get("Answer"),
            category=row.get("Category")
        )
        new_rows.append(qa)

    session.bulk_save_objects(new_rows)
    session.commit()
    session.close()

    print(f"\n\nOverhaul complete: {len(new_rows)} rows inserted.")

    try:
        from vector import init_vector_store, fetch_data_from_db

        df = fetch_data_from_db()
        init_vector_store(df)
        print("Vector store successfully rebuilt ✅")
    except Exception as e:
        print(f"⚠️ Failed to rebuild vector store: {e}")

    
    

    print(f"\n\nOverhaul complete: {len(new_rows)} rows inserted.")

    

if __name__ == "__main__":
    init_db()
    overhaul_db()
    # pass
