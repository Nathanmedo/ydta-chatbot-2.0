from flask_wtf import FlaskForm
from wtforms import StringField , PasswordField , SubmitField
from wtforms.validators import DataRequired, Length, Email

class Loginform(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password" , validators=[DataRequired()])
    submit = SubmitField("Login")
    
    
class CreateAdminForm(FlaskForm):
    master_key = PasswordField("Master Key", validators=[DataRequired(), Length(min=6)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    submit = SubmitField("Create Admin")