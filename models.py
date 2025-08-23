# models.py
from sqlalchemy import Column, Integer, DateTime, Text, Float, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class QuestionAnswer(Base):
    __tablename__ = "questions_and_answers"
    id = Column(Integer, primary_key=True)
    question = Column(Text)
    answer = Column(Text)
    category = Column(Text)
    def to_dict(self):
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
        }

class InteractionTiming(Base):
    __tablename__ = "interaction_timer"
    id = Column(Integer, primary_key=True)
    session_id = Column(String)
    time_value = Column(Integer)
    date = Column(DateTime)
    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "duration": self.time_value,
            "date": self.date,
        }
    
    
class BotSpeedLogs(Base):
    __tablename__ = "botspeed"
    id = Column(Integer, primary_key=True)
    time_value = Column(Integer, nullable=False)
    date = Column(DateTime)
    question = Column(Text)
    category = Column(Text)
    def to_dict(self):
        return {
            "id": self.id,
            "time_value": self.time_value,
        }
    

class Reviews(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    rating = Column(Float)
    comment = Column(Text)
    date = Column(DateTime)
    category = Column(Text)
    
class Unanswered(Base):
    __tablename__ = "unanswered"
    id = Column(Integer, primary_key=True)
    question = Column(Text)
    category = Column(Text)
    def to_dict(self):
        return {
            "id": self.id,
            "question": self.question,
            "category": self.category,
        }
    
class AdminTable(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    email = Column(String,unique=True)
    password = Column(String, unique=True)
    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "password": self.password,
        }
    

