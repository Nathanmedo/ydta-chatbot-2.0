from sqlalchemy.orm import sessionmaker
from models import Base, InteractionTiming, BotSpeedLogs, Unanswered, QuestionAnswer
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os


load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
 

def init_utils():
    engine = create_engine(DATABASE_URL, echo=True)
    session = sessionmaker(bind=engine)
    Session = session()
    
    return Session


def add_new_interaction(session, duration, session_id, date):
    new_row = InteractionTiming(
        session_id = session_id,
        time_value = duration,
        date = date
    )
    try:
        session.add(new_row)
        session.commit()
        
        session.close()
        return {'message' : "Done", 'status' : 1}
    except Exception as e:
        return {'message' : f"{str(e)}", 'status' : 0}
        
def add_speed_log(db_session, duration, question, date, category):
    new_row = BotSpeedLogs(
        date=date,
        time_value=duration,
        question=question,
        category=category
    )
    try:
        db_session.add(new_row)
        db_session.commit()
        db_session.refresh(new_row)
        return {'message': "Done", 'status': 1}
    except Exception as e:
        db_session.rollback()
        return {'message': str(e), 'status': 0}


def add_unanswered(db_session,question, category):
    new_row = Unanswered(
        question=question,
        category=category
    )
    try:
        db_session.add(new_row)
        db_session.commit()
        db_session.refresh(new_row)
        return {'message': "Done", 'status': 1}
    except Exception as e:
        db_session.rollback()
        return {'message': str(e), 'status': 0}
    

def add_qa(db_session, question,answer,  category):
    new_row = QuestionAnswer(
        question=question,
        answer=answer,
        category=category
    )
    try:
        db_session.add(new_row)
        db_session.commit()
        db_session.refresh(new_row)
        return {'message': "Done", 'status': 1}
    except Exception as e:
        db_session.rollback()
        return {'message': str(e), 'status': 0}
    
    
def remove_unanswered(db_session, id):
    row = db_session.query(Unanswered).filter(Unanswered.id == id).first()
    
    if not row:
        return {'message': "Invalid row ID", 'status': 0}
    
    db_session.delete(row)
    db_session.commit()
    
    return {'message': "Done", 'status': 1}

    
def edit_qa(db_session, id, question, category, answer):
    row = db_session.query(QuestionAnswer).filter(QuestionAnswer.id == id).first()
    
    if not row:
        return {'message': "Invalid row ID", 'status': 0}

    row.question = question
    row.answer = answer
    row.category = category
    
    db_session.commit()
    
    return {'message': "Updated successfully", 'status': 1}

        
        