from flask import Flask
from .config import Config 
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_bcrypt import Bcrypt
from flask_login import LoginManager


app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login = LoginManager(app)

import platform

hostname = platform.node() 

# Local development
if hostname == "sounder.cimr.cam.ac.uk":  #mylocalhostname
	app.config['MAIL_SERVER']="smtp.gmail.com"
	app.config['MAIL_PORT'] = 465
	app.config['MAIL_USERNAME'] = "tempeparsons@gmail.com" #mygmailaddress@gmail.com
	app.config['MAIL_PASSWORD'] = "klrrtcnxwpkocfli" #mail_app_pwd_randomly_generated_by_gmail
	app.config['MAIL_USE_TLS'] = False
	app.config['MAIL_USE_SSL'] = True

# Production
else: 
	app.config['MAIL_SERVER']='ppsw.cam.ac.uk'
	app.config['MAIL_PORT'] = 25
	app.config['MAIL_USERNAME'] = 'proteomics.portal@cimr.cam.ac.uk'
	app.config['MAIL_USE_TLS'] = False
	app.config['MAIL_USE_SSL'] = False

mail = Mail(app)
CSRFProtect(app)


from app import routes
from app import models
from app import login



