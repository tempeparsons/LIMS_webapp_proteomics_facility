import os
import platform

hostname = platform.node() 

class Config(object):
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'setec_astronomy'

        if 'sounder' in hostname:  #myLocalComputerName
                SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://htp25:1Shap2In3Say4!@localhost/cimr2'
        else: # Production
                SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://flask:ZnYphaN57h7QcJNBT3rfc3c3@localhost/cimr2'
	
        SQLALCHEMY_TRACK_MODIFICATIONS = False

