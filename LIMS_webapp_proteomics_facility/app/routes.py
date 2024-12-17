
from app import app, db, mail, login
from flask_mail import Message
from flask_login import current_user, login_user, logout_user, login_required
from flask import render_template, request, redirect, url_for, flash, session, send_file, escape, Response, current_app
from app.models import Pwds, Users, ExperimentRequest, SampleRequest, DataRequest, BenchHours, InstrumentDetails, ExpensesSummary, SampleDetails, Instruments, BenchMethods, InstrumentDataMethods, Acquisition, PricePerMin, InstituteType, Species
from collections import defaultdict, OrderedDict, Counter
from datetime import datetime, timedelta
from sqlalchemy import update, text, select, create_engine, insert, and_, or_, func, case
from flask_bcrypt import Bcrypt
from functools import wraps
from werkzeug.utils import secure_filename
import numpy as np
import pandas as pd
import os.path, os, sys, stat, platform, re, random, string, urllib.parse
import base64
from io import BytesIO
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from cmap import Colormap


hostname = platform.node()

##checks whether this is being run remotely or locally and sets variables as appropriate

if 'sounder' in hostname:  #replace 'sounder' with whatever local machine name you're using
        print('this is your local desktop')
        
        db_url = 'mysql+pymysql://htp25:1Shap2In3Say4!@localhost/cimr2' 
        
        email1 = 'htp25@cam.ac.uk'  #mygmailaddress@gmail.com
        
        authorised_for_data_signoff =  'tempeparsons@gmail.com' #mygmailaddress@gmail.com
        authorised_for_instrument_signoff =  'tempeparsons@gmail.com' #mygmailaddress@gmail.com
        
        local_path_start_groups = 'home/htp25/Documents/flask_stuff/app/groups/' ##change
        local_path_start_facility = 'home/htp25/Documents/flask_stuff/app/facility/'  ##change
        
        finance_dir = f'/{local_path_start_facility}/proteomics_finance'
        stats_dir = f'/{local_path_start_facility}/proteomics_stats'
        injections_dir = f'/{local_path_start_facility}/injection_lists'
        
        directories = [finance_dir, injections_dir, stats_dir]
        for directory in directories:
                if not os.path.isdir(directory):
                        os.mkdir(directory)

else:
        print('remote deployment assumed')
        db_url = 'mysql+pymysql://flask:v2XepjYLMNvB@localhost/proteomics'
        
        email1 = 'proteomics.portal@cimr.cam.ac.uk' ##############
        
        authorised_for_data_signoff =  'tempeparsons@gmail.com'
        authorised_for_instrument_signoff =  'pra29@cam.ac.uk'
        
        local_path_start_groups = 'var/www/flask/app/groups/' #must pre-exist
        local_path_start_facility = 'var/www/flask/app/facility/'  #must pre-exist

        finance_dir = f'/{local_path_start_facility}/proteomics_finance'
        stats_dir = f'/{local_path_start_facility}/proteomics_stats'
        injections_dir = f'/{local_path_start_facility}/injection_lists'
        
        directories = [finance_dir, injections_dir]
        for directory in directories:
                if not os.path.isdir(directory):
                        os.mkdir(directory)


bcrypt = Bcrypt() #see 'models.py'
engine = create_engine(db_url)


################################## checks and moves or deletes old files ####################################


import time
import shutil

def is_file_older_than_x_days(file, n_days): 
    file_time = os.path.getmtime(file) 
    # Check time in secs against 24hrs multiplied by no. of days. returns True/False
    return ((time.time() - file_time) / 3600 > 24*n_days)


#any file older than 30 days gets moved to old data in group directory
grp_dirs = None

if 'sounder' in hostname:
        grp_dirs = next(os.walk('./groups/'))[1]
else:
        grp_dirs = next(os.walk(f'{local_path_start_groups}'))[1] ##works_if_hardcode:  grp_dirs = next(os.walk('var/www/flask/app/groups'))[1]
        
for gd in grp_dirs:
        flist = os.listdir(f'/{local_path_start_groups}/{gd}/current_data')
        for f in flist: 
                fcurr = f'/{local_path_start_groups}/{gd}/current_data/{f}'
                if is_file_older_than_x_days(fcurr, 30):
                        fdest = f'/{local_path_start_groups}/{gd}/old_data/{f}'
                        shutil.move(fcurr, fdest)


#deletes any file in facility folder that is older than 3 months
folderpath_list = [finance_dir, stats_dir, injections_dir]
for folderpath in folderpath_list:
        flist = os.listdir(folderpath)
        for f in flist:
                f = f'{folderpath}/{f}'
                if is_file_older_than_x_days(f, 90):
                        os.remove(f)

                
################################## useful time variables ############################################

now_ymd = datetime.now() 
now = now_ymd.strftime("%d/%m/%Y, %H:%M:%S")
thisyear = now.split(' ')[0][-5:-1] #sets yyyy text variable for the final .csv filename
lastyear = str(int(thisyear) - 1)
nextyear = str(int(thisyear)+1)
today = [i for i in now.split(',')][0]
dttdy = datetime.strptime(today, "%d/%m/%Y")

#adjusts things to compensate for financial vs calender year ends
janfirst = datetime.strptime('01/01/'+thisyear, "%d/%m/%Y")
janlast = datetime.strptime('31/01/'+thisyear, "%d/%m/%Y")
Q4hangover = janfirst < dttdy <janlast

#defines financial year
last_finan_yr_start = '01/02/' + lastyear
last_finan_yr_end = '31/01/' + thisyear
this_finan_yr_start = '01/02/' + thisyear
last_finan_yr_end = '31/01/' + nextyear

#financial quarter cut-offs
Q1_0, Q1_1 = '01/02/' + thisyear, '30/04/' + thisyear
Q2_0, Q2_1 = '01/05/' + thisyear, '31/07/' + thisyear
Q3_0, Q3_1 = '01/08/' + thisyear, '31/10/' + thisyear
Q4_0, Q4_1 = '01/11/' + thisyear, '31/01/' + nextyear

#associates dates with quarter-identifiers
Q0 = [Q1_0, Q2_0, Q3_0, Q4_0]
Q1 = [Q1_1, Q2_1, Q3_1, Q4_1]
dtq0 = [datetime.strptime(q, "%d/%m/%Y") for q in Q0]
dtq1 = [datetime.strptime(q, "%d/%m/%Y") for q in Q1]

#finds which financial quarter you're currently in
def get_Q_for_today():
        for i, q in enumerate(dtq0):
                if q < dttdy < dtq1[i]:
                        return f'Q{i+1}'

#format user in expenses and signoffs
YearQ = thisyear + '_' + get_Q_for_today()

#not sure if this gets used
signoff_i = authorised_for_instrument_signoff + '_' + YearQ
signoff_d = authorised_for_data_signoff + '_' + YearQ



##############################################################################################


############################### SECTION FOR FUNCTIONS USED IN routes.py  ##################################

#would have tidied all the functions up to a separate file if I'd had time. 

def get_time_start_end(baton):
        '''function for getting start-end of time period where 'baton' is the time drop-down selection from previous page'''

        start = None
        end = None

        if baton.startswith('Q'):
                q0 = baton+'_0'
                q1 = baton+'_1'
                for i, str_q in enumerate(str_quarters):
                        if str_q == q0:
                                start = quarters[i]
                        if str_q == q1:
                                end = quarters[i]

        if baton.startswith('this'):
                start = datetime.strptime(f'01/01/{thisyear}, 00:00:01', "%d/%m/%Y, %H:%M:%S")
                end = datetime.strptime(f'31/12/{thisyear}, 23:59:59', "%d/%m/%Y, %H:%M:%S")

        if baton.startswith('last'):
                start = datetime.strptime(f'01/01/{lastyear}, 00:00:01', "%d/%m/%Y, %H:%M:%S")
                end = datetime.strptime(f'31/12/{lastyear}, 23:59:59', "%d/%m/%Y, %H:%M:%S")

        if baton == 'all_dates':
                start = datetime.strptime('01/01/2000, 00:00:01', "%d/%m/%Y, %H:%M:%S")
                end = datetime.strptime('31/12/2100, 23:59:59', "%d/%m/%Y, %H:%M:%S")
                        
        return start, end


###  function for getting everything out of table for 'query DB 1 pages'  ###

def table_contents_getter(TableName):
        col_names = TableName.__table__.columns.keys()
        query = db.session.query(TableName).all()

        tablerows = []
        for n in list(range(len(query))):
                tablerow = ([getattr(query[n], name) for name in col_names])
                tablerows.append(tablerow)

        return col_names, tablerows



###  function for getting everything out of table for query DB 2 and 3 pages  ###

def user_contents_getter(TableName, email, exptkey):

        col_names = TableName.__table__.columns.keys()
        query = []
        
        if TableName == Users:
                query = db.session.query(TableName).filter(TableName.email.contains(f'{email}')).all()

        if TableName != Users:
                if not exptkey:
                        query = db.session.query(TableName).filter(TableName.key1.contains(f'{email}')).all()
                if exptkey:
                        query = db.session.query(TableName).filter(TableName.key1.contains(f'{exptkey}')).all()
               
        tablerows = []
        for n in list(range(len(query))):
                tablerow = ([getattr(query[n], name) for name in col_names])
                tablerows.append(tablerow)

        return col_names, tablerows



###   function that make dictionaries from tables   ###

def grp_lead_grp_mbr_dct():
        '''makes dict of group leader: [list of group members]'''
        researchers = db.session.query(Users).with_entities(Users.email, Users.group_id).all()
        leaders = [r[1] for r in researchers]
        leaders = list(set(leaders))
        
        grp_dct = {k:[] for k in leaders}

        for r in researchers:
                if r[1] in grp_dct.keys(): 
                        grp_dct[r[1]] += [r[0]]

        return grp_dct



def grp_lead_grp_grnts_dct():
        '''makes dict of group leader: [list of group grants]'''
        usr_grnt = db.session.query(Users).with_entities(Users.email, Users.grant_codes).all()
        grnt_lists = [g[1].split(',') for g in usr_grnt]
        usr_list = [u[0]for u in usr_grnt]
        ug = list(zip(usr_list, grnt_lists))

        grp_membs = grp_lead_grp_mbr_dct()
        grp_grnts_dct = {}

        for k, valslist in grp_membs.items():
                grp_grnts = []
                for ug_pr in ug:
                        if ug_pr[0] in valslist or ug_pr[0] == k:
                                grp_grnts += ug_pr[1]

                grp_grnts_dct[k] = grp_grnts

        return grp_grnts_dct


def get_benchmeth_names_where_box_checked(exptkey):
        '''make zipped list of bench method names and bench method checkbox results for each sample in request form'''
        '''then returns list of names for methods with positive becks'''
        pos_checked_names_per_sample = []
        
        q = db.session.query(SampleRequest).filter_by(key1=exptkey).all()
        
        for smp in q:
                method_chkboxes = [smp.run_gel, smp.ingel_digest, smp.s_trap_digest, smp.insol_digest, smp.lysc_digest, smp.po4_enrichment, smp.label, smp.fractionate, smp.intact_protein]
                method_names =['run_gel', 'ingel_digest', 's_trap_digest', 'insolution_digest', 'digest_with_LysC', 'PO4_enrichment', 'peptide_labelling', 'fractionation', 'intact_protein_analysis']
                names_chckboxes = list(zip(method_names, method_chkboxes))

                for pair in names_chckboxes:
                        if pair[1] == '1':
                                pos_checked_names_per_sample.append(pair[0])

        return pos_checked_names_per_sample



def days_til_end_finanQ(dtq1, dttdy):
        '''sets days until end finanQ'''
        days_togo = None 
        for i in dtq1:
                if (i - dttdy).days >= 0 :
                        days_togo = (i - dttdy).days 
                        break
        return days_togo



def mark_arr_first(exptkey, notarrexpts):
        msg = ''
        if exptkey in notarrexpts:
                msg = 'you need to mark this experiment as arrived first'
                return exptkey, msg
        else:
                return exptkey, msg



#hefty function for making all dicitonaries used for updating the core finance and facility information that is automatically written in when database initiated.
#also sets the dropdown list of species in the database categories, institute_types and bench_methods
tablenames = [BenchMethods, InstrumentDataMethods, InstrumentDataMethods, PricePerMin, InstituteType]
col1s = [BenchMethods.bench_method, InstrumentDataMethods.instrument_method, InstrumentDataMethods.instrument_method, PricePerMin.activity, InstituteType.institute_type]
col2s = [BenchMethods.mins_per_method, InstrumentDataMethods.mins_per_method_instr, InstrumentDataMethods.mins_per_method_search, PricePerMin.price_per_min, InstituteType.price_per_type]

def outer_dict_function(tablenames, col1s, col2s):
        '''outer function makes lists for dropdown from dict keys and species column. returns lists and dicts.'''
        dictionary_list = []
        
        def make_method_minute_dict(TableName, col1, col2):
                '''inner function that makes either {method_name: method_mins} or {other_category: price_per_min} dict from sql query results'''
                result = db.session.query(TableName).with_entities(col1, col2).all()
                methods = [res[0] for res in result]
                minutes = [res[1] for res in result]
                method_min_dict = dict(zip(methods, minutes))
                return method_min_dict
        
        for i, table in enumerate(tablenames):
                outputdict = make_method_minute_dict(table, col1s[i], col2s[i]) #inner function is called
                dictionary_list.append(outputdict)

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict = dictionary_list

        #makes lists for dropdown menus
        instr_methods = list(instrmins_dict.keys()) 
        bench_methods = list(benchmins_dict.keys())
        institute_types = list(institute_price_dict.keys())

        #makes nested list for species, so can be treated like above nested lists
        species = db.session.query(Species).with_entities(Species.species).all()
        DB_categories = [sp[0] for sp in species]

        return benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories



#hefty function for getting all sorts of completeion statuses for experiments
def expt_completion_status_categories():
        '''performs conditional queries for making lists of all different experiment completeion statuses.'''
        '''returns lists for expts needing bench updates, instrument updates, all-unsigned-expts, instrumentation-only-signedoff, analysis-only-signedoff etc.'''
        '''run in facility home and linked/redirected pages'''
        #find arrived expts w no instrument update timestamp
        res1 = db.session.query(ExperimentRequest, InstrumentDetails
                                ).with_entities(ExperimentRequest.expt_code, ExperimentRequest.key1, ExperimentRequest.time_requested
                                                ).filter(ExperimentRequest.arrived != None
                                                         ).where(InstrumentDetails.YrQ_updated==None 
                                                                 ).join(InstrumentDetails, ExperimentRequest.key1 == InstrumentDetails.key1
                                                                        ).all()

        #sets which res1 experiments haven't changed status for 4 weeks
        i_update = []
        for tup in res1:
                time_req = datetime.strptime(tup[-1], "%d/%m/%Y, %H:%M:%S")
                time_req_plus_4weeks = time_req + timedelta(weeks=4)
                if time_req_plus_4weeks < now_ymd:
                        i_update.append(tup[0])

        #fins arrived expts with samples and not signed off
        res2 = db.session.query(ExperimentRequest, ExpensesSummary
                                ).with_entities(ExperimentRequest.expt_code, ExperimentRequest.key1, ExperimentRequest.time_requested
                                        ).filter(ExperimentRequest.expt_type != 'Data only'
                                                 ).filter(ExperimentRequest.arrived != None
                                                         ).filter(ExpensesSummary.bench_instr_db_signoff==None 
                                                                  ).join(ExpensesSummary, ExperimentRequest.key1 == ExpensesSummary.key1
                                                                         ).all()

        #sets which res2 experiments haven't changed status for 8 weeks
        e_signoff = []
        for tup in res2:
                time_req = datetime.strptime(tup[-1], "%d/%m/%Y, %H:%M:%S")
                time_req_plus_8weeks = time_req + timedelta(weeks=8)
                if time_req_plus_8weeks < now_ymd:
                        e_signoff.append(tup[0])

        #expts that received bespoke analysis but no relevant signoff
        res3 = db.session.query(ExperimentRequest, DataRequest, ExpensesSummary
                                ).with_entities(ExperimentRequest.expt_code, ExperimentRequest.key1, ExperimentRequest.time_requested
                                        ).filter(DataRequest.time_updated != None
                                                         ).filter(ExpensesSummary.python_signoff==None 
                                                                  ).filter(DataRequest.key1==ExpensesSummary.key1
                                                                          ).join(ExpensesSummary, ExperimentRequest.key1 == ExpensesSummary.key1
                                                                                 ).all()

        #sets which res3 experiments haven't changed status for 8 weeks
        py_signoff = []
        for tup in res3:
                time_req = datetime.strptime(tup[-1], "%d/%m/%Y, %H:%M:%S")
                time_req_plus_8weeks = time_req + timedelta(weeks=8)
                if time_req_plus_8weeks < now_ymd:
                        py_signoff.append(tup[0])

        #finds expts with no bench update, no instrument signoff
        res4 = db.session.query(ExperimentRequest, SampleDetails, ExpensesSummary
                                ).with_entities(ExperimentRequest.expt_code, ExperimentRequest.key1, ExperimentRequest.time_requested
                                         ).filter(SampleDetails.bench_methods == 'needs bench method(s)' 
                                                 ).filter(ExpensesSummary.bench_instr_db_signoff==None #this seems redundant as can't signoff without bench methods
                                                          ).filter(SampleDetails.key1==ExpensesSummary.key1
                                                                  ).join(ExpensesSummary, ExperimentRequest.key1 == ExpensesSummary.key1
                                                                         ).all()

        #sets which res4 experiments haven't changed status for 8 weeks
        b_update = []
        for tup in res4:
                time_req = datetime.strptime(tup[-1], "%d/%m/%Y, %H:%M:%S")
                time_req_plus_4weeks = time_req + timedelta(weeks=4)
                if time_req_plus_4weeks < now_ymd:
                        b_update.append(tup[0])


        #finds where analysis has been received and updated, just not signed off
        res5 = db.session.query(DataRequest, ExpensesSummary
                                ).with_entities(DataRequest.key1, ExpensesSummary.key1
                                         ).filter(DataRequest.python_hrs != 0.0 
                                                  ).filter(ExpensesSummary.python_signoff == None
                                                          ).join(DataRequest, ExpensesSummary.key1 == DataRequest.key1
                                                                 ).all()

        #no instrument update, no instrument signoff
        res6 = db.session.query(InstrumentDetails, ExpensesSummary
                                ).with_entities(InstrumentDetails.key1, ExpensesSummary.key1
                                         ).filter(InstrumentDetails.method1 != 'needs method1' 
                                                  ).filter(ExpensesSummary.bench_instr_db_signoff == None #this seems redundant as can't signoff without instrument methods
                                                          ).join(InstrumentDetails, ExpensesSummary.key1 == InstrumentDetails.key1
                                                                 ).all()

        #these are likely-completed but not-signed-off experiments. See historical section at end of this route. 
        cmpd_unsgn_expts = [e[0] for e in res5 + res6]

        return i_update, e_signoff, py_signoff, b_update, cmpd_unsgn_expts




### SQL sanitizer functions ####

'''these functions clean user-inputted text and text passed between pages in headers. bespoke way of protecting against sql injections (some special ch. are necessary)'''

def sanitize_text(text):
        specials = ['!', '?', '#', '$', '£', '*', '~', '^', '|']
        for sp in specials:
                if sp in text:
                        text = re.sub(sp,'', text)
        return text


def sanitize_general(text):
        specials = ['!', '?', '#', '$', '£', '~', '^', '%', '@', '=']
        err = ''
        pattern = r'\s+'
        text = re.sub(pattern,'', text)
        for sp in specials:
                if sp in text:
                        err = 'input contains invalid characters, try again'
                        text = ''	
        return text, err


def sanitize_batons(text):
        specials = ['!', '?', '$', '£', '~', '^', '%', '=']
        err = ''
        for sp in specials:
                if sp in text:
                        err = 'input contains invalid characters, try again'
        return text, err

	
def sanitize_code(text):
        pattern = r'\s+|\W+'
        text = re.sub(pattern,'', text)
        return text

  
def sanitize_email(text):
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
        if re.match(pattern, text):  
                err = ''
        else:
                err = 'email invalid'
                text = ''
        return text, err


def sanitize_year(text):
        if re.search('^[0-9]{4}$', str(text)):  
                err = ''
        else:
                err = 'year invalid'
                text = ''
        return text, err
 


#### ACCESS LEVEL WRAPPER FUNCTIONS ####

#these functions protect pages from different user levels.
#user levels default is 'USER'.
#Can be changed by admin from Facility Pages

'''Decorator function which checks if access level == NONE. Used when a user's access needs to be revoked at 'facility_home'.'''
def keep_out_selected(func):
        @wraps(func)
        def wrappy(*args, **kwargs):
                access_level = current_user.access_level
                if access_level == 'NONE':
                        return render_template('sod_off_politely.html')
                elif access_level != 'NONE':
                        return func(*args, **kwargs)
        return wrappy


'''Decorator function allowing only admin.'''
def admin_required(func):
        @wraps(func)
        def wrappy(*args, **kwargs):
                access_level = current_user.access_level
                if access_level == 'USER':
                        return render_template('sod_off_politely.html')
                elif access_level == 'FINAN':
                        return render_template('sod_off_politely.html')
                elif access_level == 'ADMIN':
                        return func(*args, **kwargs)
        return wrappy

'''Decorator function allowing only admin and finance.'''
def admin_finance_required(func):
        @wraps(func)
        def wrappy(*args, **kwargs):
                access_level = current_user.access_level
                if access_level == 'USER':
                        return render_template('sod_off_politely.html')
                elif access_level == 'ADMIN' or access_level == 'FINAN':
                        return func(*args, **kwargs)
        return wrappy



        
##### OTHER ASSORTED FUNCTIONS USED THROUGHOUT routes.py #####

'''function for file downloads '''
def get_random_string(len=8):
        letters = [random.choice(string.ascii_lowercase) for i in range(len)]
        return ''.join(letters)


'''function that converts list items to float (empty strings get set to 0) and adds them, returns sum. user in expenses pages'''
def float_convert_and_add(listy):
        total = 0.0
        for i in listy:
                if i == '':
                        i = 0
                i = float(i)
                total += i
        return total
		

'''password reset email function'''
def send_password_reset_email(matching_email):
        token = matching_email.get_reset_token()
        msg = Message('Password Reset Request', sender=app.config['MAIL_USERNAME'], recipients=[matching_email.email])
        msg.body = f"""To reset your password follow this link: {url_for('reset_password', token=token, _external=True)} 
        #If you ignore this email no changes will be made"""
        mail.send(msg)


'''gets lists of experiments for dropdown menus for everything, req'd in last 16 weeks or not arrived for display on facility_home page'''
def get_expt_lists():
        allexpts = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.key1, ExperimentRequest.time_requested).all()
        all_expts = [tup[0] for tup in allexpts]
        
        recent_expts = []
        for tup in allexpts:
                time_req = datetime.strptime(tup[1], "%d/%m/%Y, %H:%M:%S")
                time_req_plus_16weeks = time_req + timedelta(weeks=16)
                if time_req_plus_16weeks > now_ymd:
                        recent_expts.append(tup[0])

        notarrexpts = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.key1).where(ExperimentRequest.arrived=='N').where(ExperimentRequest.expt_type!='Data only').all()
        notarr_expts = [tup[0] for tup in notarrexpts]
        
        return all_expts, recent_expts, notarr_expts


'''gets user details for displaying on pages. exptkey is key1.'''
def get_user_details(exptkey):
        email = exptkey.split('*')[0]
        ecode = exptkey.split('*')[1]
        details = db.session.query(Users).with_entities(Users.first_name, Users.last_name, Users.group_id, Users.institute_type).where(Users.email == email).first()
        fn = details[0] #firstname
        ln = details[1] #lastname
        gid = details[2] #group leader email
        itype = details[3] #institute type
        return fn, ln, gid, itype, email


'''works out how to price the current user. exptkey is key1. '''
def instit_type_price_discount(institute_price_dict, exptkey):

        email = exptkey.split('*')[0]
        ecode = exptkey.split('*')[1]
        q4 = db.session.query(Users).with_entities(Users.institute_type, Users.grant_codes, Users.grant_years).filter_by(email=email).first()
        itype = q4[0]
        iprice = institute_price_dict[q4[0]]
        verb = 'are not' #verb gets displayed on html page
        if itype == 'Cambridge University':
                verb = 'are'
                gts = q4[1].split(',')
                yrs = q4[2].split(',')
                gtyr_dict = dict(zip(gts, [int(y) for y in yrs]))
                q5 = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.grant_code).filter_by(key1=exptkey).first()
                if gtyr_dict[q5[0]] <= 2022:
                        iprice = early_grant
                        itype = 'Cambridge University, early grant'
        return itype, iprice, verb 


'''gets experiment details. exptkey is key1.'''
def get_experiment_details(exptkey):
        q = db.session.query(ExperimentRequest).filter_by(key1=exptkey).first()
        db_yn = 'NO'
        if 'Database' in q.expt_type:
                db_yn = 'YES'
        return q.expt_code, q.expt_type, q.expt_cat, q.db_cat, q.grant_code, q.extra_notes, q.time_requested, db_yn


'''function for assigning unique ID to each form field for however many rows are set by the user in the request form.
row name abbrevistions refer to bench methods on experiment request page'''
def get_row_names(n):
        row_names=[]
        for i in range(n):
                sc = f'row{i}box1'
                pc = f'row{i}box2'
                inj = f'row{i}box3'
                rg = f'row{i}box4'
                ingel = f'row{i}box5'
                strap= f'row{i}box6'
                insol = f'row{i}box7'
                lysc = f'row{i}box8'
                po4 = f'row{i}box9'
                label = f'row{i}box10'
                frac = f'row{i}box11'
                intm = f'row{i}box12'
                row_names.append([sc, pc, inj, rg, ingel, strap, insol, lysc, po4, label, frac, intm])
        return row_names


'''functions for getting values out of the lower, tabulated part (sample info) of the experiment request form'''
def process_sample_request_form(nrange, em, ecode, key1, etype):
        sample_request_values= []
        scode_repeat_check = []
        injection_names = []
        errmsg = None
        for i in range(nrange):
                em = em
                ecode = ecode
                key1 = key1
                scode = sanitize_code(request.form[f'row{i}box1'])
                key2 = key1 + '*' + scode
                pconc = request.form[f'row{i}box2']
                estinj = request.form[f'row{i}box3']
                mstype = ''
                instr_name = ''
                rgel = f'row{i}box4' in request.form
                geld = f'row{i}box5' in request.form
                strap= f'row{i}box6' in request.form
                insold = f'row{i}box7' in request.form
                lysc = f'row{i}box8' in request.form
                po4= f'row{i}box9' in request.form
                label = f'row{i}box10' in request.form
                frac = f'row{i}box11' in request.form
                intact = f'row{i}box12' in request.form
                time_requested = now
                #database addition: one list per row, nrows=nsamples.
                sample_request_values.append([em, ecode, key1, scode, key2, pconc, estinj, mstype, instr_name, rgel, geld, strap, insold, lysc, po4, label, frac, intact, time_requested])
                try:
                        injection_codes = [i for i in range(1, int(estinj)+1)] #makes list of injection names what later get written to text file in injection names folder. 
                        injection_names.append(injection_codes)
                except ValueError:
                        injection_names = None
                        errmsg = 'injectionsnames'
                        
                scode_repeat_check.append(scode) #makes list of smaple codes

        if len(set(scode_repeat_check)) != len(scode_repeat_check): #len list vs len set repeat check
                scode_repeat_check = None
                errmsg = 'scode repreat one'

        if scode_repeat_check:
                for sc in scode_repeat_check:
                        if len(sc) > 4:
                                scode_repeat_check = None
                                errmsg = 'scode repreat two'

        these_ones = [3,5,6,9,10,11,12,13,14,15,16,17] #these list indicies must not be blank if benchwork has been requested, otherwise generates specific errors
        for sublist in sample_request_values:
                critical = [sublist[n] for n in these_ones]
                if 'Benchwork' in etype:
                        if True not in critical:
                                sample_request_values = None
                                errmsg = 'srv one'
                if 'Benchwork' not in etype:
                        if True in critical:
                                sample_request_values = None
                                errmsg = 'srv three'
                if '' in critical:
                        sample_request_values = None
                        errmsg = 'srv two'
                       
        return sample_request_values, scode_repeat_check, injection_names, errmsg



def make_userdict_for_javascript():
        userdict = defaultdict()
        userdata = db.session.query(Users).with_entities(Users.user_id, Users.first_name, Users.last_name, Users.email).all()
        for ud in userdata:
                ud0 = str(ud[0])
                key = ' '.join((ud0, ud[1], ud[2]))
                val= ud.email
                userdict[key] = val
        userdict = list(userdict.items())
        return userdict


def make_exptdict_for_javascript():
        ecodes = defaultdict(list)
        q1 = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.email, ExperimentRequest.expt_code).all()
        for q in q1:
                ecodes[q.email].append(q.expt_code)
        ecodes = list(ecodes.items())
        return ecodes


def make_smpldict_for_javascript():
        scodes = defaultdict(list)
        q1 = db.session.query(SampleRequest).with_entities(SampleRequest.expt_code, SampleRequest.sample_code).all()
        for q in q1:
                scodes[q.expt_code].append(q.sample_code)
        scodes = list(scodes.items())
        return scodes


def get_newest_id():
        newest_id = 1
        sqlt = text("""SELECT user_id FROM users ORDER BY user_id DESC LIMIT 1;""")
        with engine.connect() as conn:
                result = conn.execute(sqlt)
                for row in result:
                        for n in row:
                                newest_id += n
        return newest_id


#makes lists of currently registered group leaders; checks against this when new students/PDs register#gets emails of all users registered-to-date to check against
def get_PIemails_allemails():
        legit_gid = []
        res1 = Users.query.with_entities(Users.email).filter(Users.position=='PI/Project_Lead').all()
        for em in res1:
                legit_gid.append(em[0])
        all_emails = []
        res2 = Users.query.with_entities(Users.email).all()
        for em in res2:
                all_emails.append(em[0])
        return legit_gid, all_emails


def get_registree_info(suffix):
        legit_gid, all_emails = get_PIemails_allemails()
        
        pass_list = []
        errs = []
        msg = ''
        fn, err_fn = sanitize_general(request.form[f'fname{suffix}'])
        ln, err_ln = sanitize_general(request.form[f'lname{suffix}'])
        email, err_email = sanitize_email(request.form[f'email{suffix}'])
        access = request.form[f'access{suffix}']         #value="USER" on template
        position = request.form[f'position{suffix}']
        gid, err_gid = sanitize_email(request.form[f'PIemail{suffix}'])
        iname = request.form[f'iname{suffix}']
        itype = request.form[f'itype{suffix}']
        grant_entries = [request.form[f'grant1{suffix}'], request.form[f'grant2{suffix}'], request.form[f'grant3{suffix}']]
        year_entries = [request.form[f'year1{suffix}'], request.form[f'year2{suffix}'], request.form[f'year3{suffix}']]
        time_registered = now
        authenticated = ''

        if err_fn or err_ln or err_email or err_gid:
                        pass_list.append('a')
                        err = err_fn or err_ln or err_email or err_gid
                        errs.append(err)
        for grant in grant_entries:
                grant, err = sanitize_general(grant)
                if err:
                        pass_list.append('a')
                        errs.append(err)
        for year in year_entries:
                if year:
                        year, err = sanitize_year(year)
                        if err:
                                pass_list.append('a')
                                errs.append(err)
        errs = ' '.join(errs)

        if email in all_emails:
                pass_list.append('b')
                msg = 'This email is already in the database, please use another one.'
        if position == 'PI/Project_Lead' and email != gid:
                pass_list.append('c')
                msg = 'If you are a PI or project lead, both emails must match'
        if position != 'PI/Project_Lead' and gid not in legit_gid:
                pass_list.append('d')
                msg = 'The group ID needs to match either the current PIs email or a group ID already in the database.'

        grants = [grant for grant in grant_entries if grant != '']
        years = [year for year in year_entries if year != '']
        if len(grants) != len(years):
                pass_list.append('e')
                msg = 'Please ensure each grant code has an award year and vice-versa'
        grant_codes = ','.join(grants)          #appear as lists in db table
        grant_years = ','.join(years)
        if itype == 'Cambridge University':
                if not grants:
                        pass_list.append('f')
                        msg = 'Group leaders from Cambridge University and their researchers must provide at least one grant number and its award year'
        if itype != 'Cambridge University':
                if grants:
                        pass_list.append('g')
                        msg = 'Please only provide a grant number of you are a Cambridge University user'

        return pass_list, errs, msg, fn, ln, email, access, position, gid, iname, itype, grant_codes, grant_years, time_registered, authenticated, legit_gid



def write_injection_queue(group_email, res_fname, res_lname, exptkey):

        scode_list = []
        n_suffix_list = []
        ecode = None
        queue = []
        
        #get out initials for the files names generated by the instrument
        PI = db.session.query(Users).with_entities(Users.first_name,Users.last_name).filter_by(email=group_email).first()
        PInames = [PI[0], PI[1]]
        PIinitials = ''.join([PI[0][0], PI[1][0]])
        Rinitials = ''.join([res_fname[0] + res_lname[0]])

        #get out the list of sample codes from the exptkey to go after the initials
        q1 = db.session.query(SampleDetails).with_entities(SampleDetails.key2, SampleDetails.actual_injections).filter_by(key1=exptkey).all()
        
        #turn sample codes into initial-containing file names, then add inj-numbers-per-samplecode suffix
        for q in q1:
                ecode = q[0].split('*')[1]
                scode = q[0].split('*')[2]
                sname = PIinitials + '_' + Rinitials + '_' + ecode + '_' + scode
                injection_number = q[1]
                list_of_inj_suffixes = list(range(1, int(injection_number)+1)) #makes list 1-injn in steps of 1
                for n in list_of_inj_suffixes:
                        sname_suffix = [sname + '_' + str(n)]
                        queue += sname_suffix
                             
        return queue, PInames, PIinitials, Rinitials #still need names, initials for making filepath


def write_no_benchwork_injection_queue(gid, ecode, scode_repeat_check, injection_names, fn, ln):
        queue = []
        PI = db.session.query(Users).with_entities(Users.first_name, Users.last_name).filter_by(email=gid).first()
        PInames = [PI[0], PI[1]]
        PIinitials = ''.join([PI[0][0], PI[1][0]])
        Rinitials = ''.join(fn[0] + ln[0])

        for idx, scode in enumerate(scode_repeat_check):
                for n in injection_names[idx]:
                        queue_item = PIinitials + '_' + Rinitials + '_' + ecode + '_' + scode + '_' + str(n)
                        queue.append(queue_item)

        return PIinitials, Rinitials, queue



def add_to_existing_grant_list(filter_var):
        result_grants = db.session.query(Users).with_entities(Users.grant_codes).filter_by(email=filter_var).all()
        result_years = db.session.query(Users).with_entities(Users.grant_years).filter_by(email=filter_var).all()
        grantresults = [r for (r,) in result_grants]
        yearresults = [r for (r,) in result_years]

        previousgrants = []
        gs = grantresults[0].split(',')
        for g in gs:
                previousgrants.append(g)

        return grantresults, yearresults, previousgrants



def reset_extra_wash_mins():
        extra_wash_mins = 120
        return extra_wash_mins



def reset_early_grant_discount():
        early_grant = 0.77
        return early_grant



##### page error wrapper functions #####

@app.errorhandler(404)
def page_not_found(e):
        return render_template('error404.html'), 404

@app.errorhandler(403)
def access_forbidden(e):
        return render_template('error403.html'), 403

@app.errorhandler(410)
def page_deleted(e):
        return render_template('error410.html'), 410
	
@app.errorhandler(500)
def internal_server_error(e):
        return render_template('error500.html'), 410


####################################### END OF FUNCTIONS SECTION #########################################




############## SECTION FOR HARDCODED LISTS FOR DROPDOWN MENUS ON HTML PAGES (except database species, see above) ###############


positions = ['Researcher', 'PI/Project_Lead', 'Other']
expt_types = ['Data only', 'Samples only', 'Samples + Database search', 'Benchwork + Samples + Database search']
expt_categories = ['Data only', 'BioID', 'Immunoprecipitation',  'ID proteins in band(s)', 'ID everything in sample', 'TMT fractions', 'TMT single sample', 'PRM assay', 'Mixed methods', 'Other']
access_levels = ['USER', 'FINAN', 'ADMIN', 'NONE']
date_options = ['Q1', 'Q2', 'Q3', 'Q4', 'this_calendar_year_to_date', 'last_calendar_year']
finan_dates = [f'last financial yr (01/02/{lastyear} to 31/01/{thisyear})', f'this financial yr (01/02/{thisyear} to {today})']
stack_many = ['totals only, no grouping', 'by experiment type', 'by experiment category', 'by research group', 'by client category']
stack_select = ['totals only, no grouping', 'by instrument method', 'by bench method']
bench_python = ['bench hours', 'bespoke analysis hours']
expt_cost_type = ['total cost', 'bench cost', 'instrument cost', 'wash cost', 'database search cost', 'bespoke analysis cost']
injection_wash = ['injections', 'washes']
modtypes = ['bench_method', 'bench_hours', 'instrument_details', 'python_hours', 'extra_costs']


####################################### END OF LISTS SECTION #############################################


early_grant = reset_early_grant_discount()
extra_wash_mins = reset_extra_wash_mins()


##################################### SECTION FOR ROUTING FUNCTIONS #######################################


#route name corresponds to template page file name in as often as possible

##main home page. 
@app.route('/')
@app.route('/index')
def index():
        return render_template('index.html')


##uneventful static pages
@app.route('/privacy_policy', methods = ['GET', 'POST']) 
def privacy_policy():
        return render_template('privacy_policy.html')

@app.route('/instrumentation', methods = ['GET', 'POST'])
def instrumentation():
        return render_template('instrumentation.html')

@app.route('/services', methods = ['GET', 'POST'])
def services():
        return render_template('services.html')

@app.route('/protein_identification', methods = ['GET', 'POST'])
def protein_identification():
        return render_template('protein_identification.html')

@app.route('/protein_discovery', methods = ['GET', 'POST'])
def protein_discovery():
        return render_template('protein_discovery.html')

@app.route('/targeted_proteomics', methods = ['GET', 'POST'])
def targeted_proteomics():
        return render_template('targeted_proteomics.html') 
    
@app.route('/offline_fractionation', methods = ['GET', 'POST'])
def offline_fractionation():
        return render_template('offline_fractionation.html')
        
@app.route('/protein_cross_linking', methods = ['GET', 'POST'])
def protein_cross_linking():
        return render_template('protein_cross_linking.html')

@app.route('/intact_mass_analysis', methods = ['GET', 'POST'])
def intact_mass_analysis():
        return render_template('intact_mass_analysis.html')

@app.route('/data_service', methods = ['GET', 'POST'])
def data_service():
        return render_template('data_service.html')

@app.route('/prices')
def prices():
        return render_template('prices.html')




##new user registration page access from main home page
@app.route('/prospective_users', methods = ['GET', 'POST'])
def prospective_users():

        #for dropdowns
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        #user_id column was required for flask_login.
        #this sets user ID to be one more than the previous highest; users are numbered in registration order, not by first login. 
        newest_id = get_newest_id()
        
        #makes lists of currently registered group leaders; checks against this when new students/PDs register
        legit_group_id = []
        res1 = Users.query.with_entities(Users.email).filter(Users.position=='PI/Project_Lead').all()
        for r in res1:
                legit_group_id.append(r[0])

        #gets emails of all users registered-to-date to check against
        all_emails = []
        res2 = Users.query.with_entities(Users.email).all()
        for em in res2:
                all_emails.append(em[0])

        #initiates variables for template page refills
        fn = None
        ln = None
        email = None
        access = None
        positn = None
        inst_name = None
        inst_type = None

        template_page = 'prospective_users.html'

        if request.method == 'POST' :
                pass_list = []
                
                fn, err_fn = sanitize_general(request.form['fname'])
                ln, err_ln = sanitize_general(request.form['lname'])
                email, err_email = sanitize_email(request.form['email'])
                access = request.form['access_level']         #value="USER" (not shown on html view)
                positn = request.form['position']
                group_id, err_gid = sanitize_email(request.form['PIemail'])
                inst_name = request.form['institute_name']
                inst_type = request.form['institute_type']
                grant_entries = [request.form['grant1'], request.form['grant2'], request.form['grant3']]
                year_entries = [request.form['year1'], request.form['year2'], request.form['year3']]
                time_registered = now
                authenticated = ''

                grants = [grant for grant in grant_entries if grant != '']
                years = [year for year in year_entries if year != '']

                #sanity checks
                if err_fn or err_ln or err_email or err_gid:
                                pass_list.append('a')
                                err = err_fn or err_ln or err_email or err_gid
                                return render_template(template_page, msg=err, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                                       instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)

                for grant in grant_entries:
                        grant, err = sanitize_general(grant)
                        if err:
                                pass_list.append('a')
                                return render_template(template_page, msg=err, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                                       instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)

                for year in year_entries:
                        if year:
                                year, err = sanitize_year(year)
                                if err:
                                        pass_list.append('a')
                                        return render_template(template_page, msg=err, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                                               instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)

                #prevents same email being registered twice
                if email in all_emails:
                        pass_list.append('a')
                        msg = 'This email is already in the database, please use another one.'
                        return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                               instn=inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)

                if positn == 'PI/Project_Lead' and email != group_id:
                        pass_list.append('a')
                        msg = 'If you are a PI or project lead, both emails must match'
                        return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                               instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)

                #everyone must be associated with a group, even a one-person group
                if positn != 'PI/Project_Lead' and group_id not in legit_group_id:
                        pass_list.append('a')
                        msg = 'The group ID needs to match either the current PIs email or a group ID already in the database.'
                        return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                               instn=inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)
                
                #grant and award yr check
                if len(grants) != len(years):
                        pass_list.append('a')
                        msg = 'Please ensure each grant code has an award year and vice-versa'
                        return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                               instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)
                grant_codes = ','.join(grants)          #appear as lists in db table
                grant_years = ','.join(years)

                #prevents CamUni members from leaving the grant-year section blank or using another group leaders grant
                if inst_type == 'Cambridge University':
                        if not grants:
                                pass_list.append('a')
                                msg = 'Group leaders from Cambridge University and their researchers must provide at least one grant number and its award year'
                                return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                                       instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)
                        if grants:
                                grp_grnt_dct = grp_lead_grp_grnts_dct()
                                for k, vlist in grp_grnt_dct.items():
                                        for g in grants:
                                                if g in vlist and group_id != k:
                                                        msg = 'At least one of these grant numbers has already been registered with another group leader'
                                                        return render_template(template_page, msg=msg, fn=fn, ln=ln, em=email, ps=positions, instts=institute_types, p=positn,
                                                       instn = inst_name, instt = inst_type, PI_emails=legit_group_id, gid=group_id, ge=grants, ye=years)
                                                

                #if pass_list is still clear, register user
                if 'a' not in pass_list:
                        newuser = Users(newest_id, fn, ln, email, access, positn, group_id, inst_name, inst_type, grant_codes, grant_years, time_registered, authenticated)
                        db.session.add(newuser)	
                        db.session.commit()
                        msg = 'You have been successfully added the facility database. Now you can set your password on the registered user login page.'
                        return render_template(template_page, msg0=msg, ps=positions, instts=institute_types, PI_emails=legit_group_id)        

        return render_template('prospective_users.html', ps=positions, instts=institute_types)





##user login page
@app.route('/user_login', methods = ['GET', 'POST'])
def user_login():

        #current_user.x is flask-login method
        
        #logged in users sent to user's home page
        if current_user.is_authenticated:
                return redirect(url_for('user_home'))

        #below code executes if first 'set my password' clicked on template
        if request.method == 'POST' and 'setpw' in request.form:
                useremail = request.form['username']
                unrecognised = db.session.query(Users.email).filter_by(email=useremail).first() is None #True if name not in db

                #sanity checks
                if unrecognised:
                        msg = 'No record of this username. Try again or contact us to check you are registered with the facility.'
                        return render_template('user_login.html', msg=msg)

                if not unrecognised:
                        password_exists = db.session.query(Pwds).with_entities(Pwds.password).filter_by(email=useremail).first() is not None #checks if username already has assoc pwrd.
                        
                        if password_exists:
                                msg = 'Your password has already been set. Please log in below.'
                                return render_template('user_login.html', msg=msg)
                        
                        if not password_exists: #if name registered and no assoc pwrd, pwrd can be set.
                                pw1 = request.form['pw1']
                                pw2 = request.form['pw2']
                                
                                if pw1 != pw2:
                                        msg = 'Your passwords do not match. Try again.'
                                        return render_template('user_login.html', msg=msg, useremail=useremail)

                                #passes checks
                                else:
                                        password_details = Pwds(id, useremail, pw2, '')
                                        db.session.add(password_details)
                                        db.session.commit()		
                                        msg0 = 'your password has been set; now you can log in below.'
                                        return render_template('user_login.html', msg0=msg0)


        #below code executes if 'log in' button clicked on template				
        if request.method == 'POST' and 'login' in request.form:
                
                useremail = request.form['registered_user']
                password = request.form['registered_pw']
                res = Users.query.get(useremail)

                #sanity checks
                unrecognised_user = db.session.query(Users.email).filter_by(email=useremail).first() is None
                user_with_password = Pwds.query.filter_by(email=useremail).first()

                if unrecognised_user:
                        msg1 = 'No record of this username. Please make sure you are registered or have typed it properly'
                        return render_template('user_login.html', msg1=msg1)

                if not user_with_password:
                        msg1 = 'Make sure you have set your password above first'
                        return render_template('user_login.html', msg1=msg1)

                if user_with_password and not user_with_password.verify_password(password):
                        msg1 = 'Try typing your password again'
                        return render_template('user_login.html', msg1=msg1, reg_useremail=useremail)

                #if passes checks
                if user_with_password and user_with_password.verify_password(password):
                        login_user(user_with_password) #log user in
                        usergroup = db.session.query(Users).with_entities(Users.group_id).filter_by(email=current_user.email).first() #gets the logged in user's group
                        dir_names = db.session.query(Users).with_entities(Users.first_name, Users.last_name).filter_by(email=usergroup[0]).first() #gets fn and ln of group leader

                        #prepares paths for grp directory w group leaders fname and lname
                        fn = dir_names[0]
                        ln = dir_names[1]
                        path1 = f'/{local_path_start_groups}/{fn}_{ln}_group'
                        path2 = f'/{local_path_start_groups}/{fn}_{ln}_group/current_data'
                        path3 = f'/{local_path_start_groups}/{fn}_{ln}_group/old_data'

                        if not os.path.isdir(path1):
                                os.mkdir(path1)
                                for path in [path2, path3]:
                                        os.mkdir(path)

                        return redirect(url_for('user_home'))


        #executes if pwd reset requested 
        if request.method == 'POST' and 'get_reset' in request.form:
                
                requesters_email = request.form['idiot']
                matching_email = Pwds.query.filter_by(email=requesters_email).first()
                msg = 'Please check your email for a password reset link (link expires in 30 mins).'
                
                if matching_email:
                        send_password_reset_email(matching_email)
                        return render_template('user_login.html', msg2=msg)        

        return render_template('user_login.html')	




#@app.route('/reset_password', methods=['GET', 'POST']) 
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):

        #in case a logged-in user gets here  -> main home page       
        if current_user.is_authenticated:
                return redirect(url_for('index')) 

        #see @staticmethod in Pwds, models.py
        idiot_user = Pwds.verify_reset_token(token)

        #invalid token -> login page
        if not idiot_user:
                return redirect(url_for('user_login')) 


        if request.method == 'POST' and idiot_user:

                new_pwd = request.form['newpw1']
                check_new_pwd = request.form['newpw2']
                
                #sanity checks
                if new_pwd == check_new_pwd:
                        new_hashed_pwd = bcrypt.generate_password_hash(new_pwd).decode('UTF-8')
                        idiot_user.password = new_hashed_pwd
                        db.session.commit()
                        msg = 'Your password has been successfully updated. Please log in again using the Registered Users Sign In Here area.'
                else:
                        msg = 'Your passwords do not match. Try again.'

                return render_template('reset_password.html', msg=msg)

        return render_template('reset_password.html')



@app.route('/user_logout')
@login_required
def user_logout():
        logout_user()
        return redirect(url_for('index'))



@app.route('/user_home', methods = ['GET', 'POST'])
@login_required
@keep_out_selected #can't access if user level is 'NONE'
def user_home():
        return render_template('user_home.html')



@app.route('/expt_advice', methods = ['GET', 'POST'])
@login_required
def experiment_advice():	
        return render_template('experiment_advice.html')



#expt request form page. heavy stuff.
#this page ideally needs jQuery, AJAX and JSONify so erroneous sample-table data can be reloaded without a page reload. 
@app.route('/experiment_request', methods = ['GET', 'POST'])
@login_required
@keep_out_selected 
def experiment_request():

        #just need DB_categories for specieis drop down
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
        
        #sets the auto-fill variables passed to the template
        fn = current_user.first_name
        ln = current_user.last_name
        em = current_user.email
        gid= current_user.group_id
                
        result_e = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.expt_code).filter_by(email=em).distinct()

        #for the dropdown showing previous experiment code
        used_codes = [r for (r,) in result_e]

        #sets initial number of rows at one (hidden field on template)
        nrows = 1

        #nrows gets update in template by user, then passed back to server when 'tenrows', 'addrow' or 'deleterow' clicked in template
        nameset = get_row_names(nrows)

        #for the dropdown showing user-specific grant list and dictionary of grants, years for setting expenses summary table
        grant_or_type = [current_user.institute_type]
        grant_discount = 'N'
        grantyear_dict = None
        
        if current_user.institute_type == 'Cambridge University': #because only these folks use grant numbers
                result_g = db.session.query(Users).with_entities(Users.grant_codes).filter_by(email=current_user.email).all()
                result_y = db.session.query(Users).with_entities(Users.grant_years).filter_by(email=current_user.email).all()
                
                grantyears = []
                for res in [result_g, result_y]:
                        all_group_grants1 = [i for tup in res for i in tup]
                        all_group_grants2 = [entry.split(',') for entry in all_group_grants1]
                        all_group_grants3= [i for sblist in all_group_grants2 for i in sblist]
                        grantyears.append(all_group_grants3)
                        
                grantyear_dict = dict(zip(grantyears[0], grantyears[1]))
                grant_or_type = list(grantyear_dict.keys())

        #form refill variables
        ecode = None
        gcode= None
        etype = None
        ecat = None
        dbcat = None
        enotes = None
        
        #check if experiment or data request
        data_only = False
        benchwork = False
        samples = False

        if request.method == 'POST':
                #santise user input
                ecode = sanitize_code(request.form['exp_code'])
                gcode= request.form['gcode']
                etype = request.form['etype'] #samples only, data only, benchwork etc. 
                ecat = request.form['ecat']
                dbcat = request.form.getlist('dbcat') #as user can select more than 1
                dbcat = ', '.join(dbcat)
                enotes = sanitize_text(request.form['enotes'])


                #check that current ecode is unqiue
                if ecode in used_codes:
                        msg = 'experiment codes cannot be reused'
                        return render_template('experiment_request.html', nameset=get_row_names(nrows), fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes, used_codes=used_codes, msg=msg)

                #sets how downstream tables get filled in below
                #bm is benchmethod
                bm_if_bmreq = 'no_prep_required'
                
                if 'Data only' in etype:
                        data_only = True
                if 'Benchwork' in etype:
                        benchwork = True
                        bm_if_bmreq = 'needs bench method(s)'
                if 'Samples' in etype:
                        samples = True

                #sets conditions for expenses summary table
                if grantyear_dict:
                        if int(grantyear_dict[gcode]) <= 2022:
                                grant_discount = 'Y'

                #get number of rows from template
                nrows = int(request.form["nrows"])
                nrows = min(max(nrows, 1), 50)
                
                #timestamp and set useremail-ecode unique key:
                time_requested = now
                arrived = 'N'
                key1 = '*'.join((em, ecode))

                
                if "submit_all" in request.form:
                        
                        sample_names = []
                        acquisition_queue = []
                        #these downstream tables must be filled with minimal info, irrespective of type of request
                        er = [em, ecode, key1, gcode, etype, ecat, dbcat, enotes, time_requested, arrived]
                        er = ExperimentRequest(er[0], er[1], er[2], er[3], er[4], er[5], er[6], er[7], er[8], er[9])
                        es = [key1, gcode, grant_discount, None, None, None, None, None, None, None, None, None, 0, None, None]
                        es = ExpensesSummary(es[0], es[1], es[2], es[3], es[4], es[5], es[6], es[7], es[8], es[9], es[10], es[11], es[12], es[13], es[14])
                        ind = [key1, 'needs method1', 0, 'Yes', None, None, None, None, None, None, None, None, None, None, None, None, None, time_requested]
                        ind1 = InstrumentDetails(ind[0], ind[1], ind[2], ind[3], ind[4], ind[5], ind[6], ind[7], ind[8], ind[9], ind[10], ind[11], ind[12], ind[13], ind[14], ind[15], ind[16], ind[17])

                        #DataReq table only gets filled for data requests             
                        if data_only:
                                db.session.add(er)
                                db.session.commit()
                                data_request = [key1, 0, '', '', time_requested]
                                dr = data_request
                                dr = DataRequest(dr[0], dr[1], dr[2], dr[3], dr[4])
                                db.session.add(dr)
                                db.session.add(es)
                                db.session.commit()
                                return redirect(f'request_confirmed/{key1}')
                                
                        #these tables must be filled if something's being injected on to the instruments  
                        if samples:
                                
                                #nrows is hidden field in experiment_request.html
                                nrange = int(request.form["nrows"])
                                
                                #runs form processing func for as many rows as user put in form
                                sample_request_values, scode_repeat_check, injection_names, errmsg = process_sample_request_form(nrange, em, ecode, key1, etype)



                                #[em, ecode, key1, scode, key2, pconc, estinj, mstype, instr_name, rgel, geld, strap, insold, lysc, po4, label, frac, intact, time_requested]


                                
                                
                                #filled-in-form-wrong advice messages
                                if errmsg == 'srv one':
                                        msg = 'If benchwork was requested, make sure at least one sample method box has been checked'
                                        return render_template('experiment_request.html', nameset=get_row_names(nrows), msg=msg, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)                                        

                                if errmsg == 'srv three':
                                        msg = 'You have not requested benchwork but you have checked a sample method box. Do you require benchwork?'
                                        return render_template('experiment_request.html', nameset=get_row_names(nrows), msg=msg, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)                                        

                                if not injection_names or not sample_request_values or not scode_repeat_check:
                                        msg = 'Please check for missing protein concentrations, injections, repeated sample codes or samples code > 3 characters.'
                                        return render_template('experiment_request.html', nameset=get_row_names(nrows), msg=msg, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)  

                                #if the user specifically did not want their instrument data files searched against a database, instrument details table is filled accordingly
                                if 'Database' not in etype:
                                        ind = [key1, 'needs method1', 0, 'No', None, None, None, None, None, None, None, None, None, None, None, None, None, time_requested]
                                        ind1 = InstrumentDetails(ind[0], ind[1], ind[2], ind[3], ind[4], ind[5], ind[6], ind[7], ind[8], ind[9], ind[10], ind[11], ind[12], ind[13], ind[14], ind[15], ind[16], ind[17])
                                                      

                                #passes all checks, big series of db commits to initiate experiment request and get expt keys, smpl keys into all relevant downstream tables
                                if sample_request_values and injection_names and scode_repeat_check:

                                        if not benchwork: #if benchwork, then injection queue written after benchwork completed and injections updated if neccessary
                                                PIinitials, Rinitials, queue = write_no_benchwork_injection_queue(gid, ecode, scode_repeat_check, injection_names, fn, ln)
                                                with open(f'/{local_path_start_facility}/injection_lists/{PIinitials}_{Rinitials}_{ecode}.txt', 'w') as fw: 
                                                        for injection in queue:
                                                                fw.write(f'{injection}\n')

                                        db.session.add(er)
                                        db.session.commit()
                                        db.session.add(es)
                                        db.session.commit()

                                        #one commit per sample into the sample req table                                
                                        for sr in sample_request_values:
                                                exptkey = sr[2]
                                                smplkey = sr[4]
                                                timereq = sr[18]
                                                sr = SampleRequest(sr[0], sr[1], sr[2], sr[3], smplkey, sr[5], sr[6], sr[7], sr[8], sr[9], sr[10], sr[11], sr[12], sr[13], sr[14], sr[15], sr[16], sr[17], timereq)
                                                sd = SampleDetails(exptkey, smplkey, bm_if_bmreq, 'not injected', 'sparecol1', 'sparecol2', timereq)
                                                db.session.add(sr)
                                                db.session.add(sd)
                                                db.session.commit()

                                        #expt key filled into bench hours table if bw requested
                                        if benchwork:      
                                                bench_hours = [key1, 0, '', '', time_requested]
                                                bh = bench_hours
                                                bh = BenchHours(bh[0], bh[1], bh[2], bh[3], bh[4])
                                                db.session.add(bh)
                                                db.session.commit()

                                        #special no-db case from earlier
                                        db.session.add(ind1) 
                                        db.session.commit()
                                
                                        return redirect(f'request_confirmed/{key1}')


                #below code is executed when user changes row numbers in templates.
                #lately discovered neater js method for this but no time to implement. See price Edit Methods page for example.
                if request.method == 'POST' and "addrow" in request.form:
                        nrows += 1
                        render_template('experiment_request.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)

                if request.method == 'POST' and "tenrows" in request.form:
                        nrows += 10
                        nameset = get_row_names(nrows)
                        render_template('experiment_request.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)

                if request.method == 'POST' and "deleterow" in request.form:
                        nrows -= 1
                        nameset = get_row_names(nrows)
                        render_template('experiment_request.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)
                        
        return render_template('experiment_request.html', nameset=get_row_names(nrows), fn=fn, ln=ln, em=em, gid=gid, used_codes=used_codes, ecode=ecode, exptypes=expt_types,
                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)



#experiment request confirmation page
@app.route('/request_confirmed', methods = ['GET', 'POST'])
@app.route('/request_confirmed/<exptkey>', methods = ['GET', 'POST'])
@login_required
def request_confirmed(exptkey=None):
        
        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_confirmed.html', msg=msg)

                #compile info for message in series of queries, some from funcs section at top
                ec, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)
                fn, ln, gid, itype, email = get_user_details(exptkey)

                q2 = db.session.query(SampleRequest).filter_by(key1=exptkey).all()
                sclist = [q.sample_code for q in q2] #list of sample codes in request

                #make set to avoid repeats for samples with the same benchwork requirements
                bw_reqs = list(set(get_benchmeth_names_where_box_checked(exptkey)))

                #insert variable from above queries using python fstring method
                msg = Message(f'Request {ec} submitted by {fn} {ln}', sender = app.config['MAIL_USERNAME'], recipients = [current_user.email, email1]) #user and facility get a copy
                msg.body =f'''
                Hi {fn},\n
                
                Here is an email record of your submission to the facility.\n
                Group/Project leader's email: { gid }\n
                Your institute category: { itype }\n
                Grant code (if CU) for this experiment: { gc }\n
                Experiment code: { ec }\n
                Experiment type: { etype }\n
                Experiment category: { ecat }\n
                Database(s) for searching: { dbcat }\n
                Requested benchwork (if any): { bw_reqs }\n
                Database search requested: { db_yn }\n
                Search against: { dbcat }\n
                List of samples codes: { sclist }\n
                Initial request date: { reqdt }\n
                \n
                Best regards,\n
                The CIMR proteomics facility
                '''
                mail.send(msg)
                        
                return render_template('request_confirmed.html', fn=fn, ln=ln, gid=gid, itype=itype, ec=ec, gc=gc, ecat=ecat, etype=etype, db_yn=db_yn, dbcat=dbcat, sclist=sclist, bw_reqs=bw_reqs, reqdt=reqdt)
        
        return render_template('request_confirmed.html')



@app.route('/add_grant', methods = ['GET', 'POST'])
@login_required
@keep_out_selected
def add_grant():

        #existence of grant number used as flag for internal user; important we never fill in grants from external users. 
        if current_user.institute_type != 'Cambridge University':
                msg0 = 'Only Cambridge University users should supply grant numbers. Please return to the user home page.'
                return render_template('add_grant.html', msg0=msg0)

        #gets existing grant info
        grantresults, yearresults, previousgrants = add_to_existing_grant_list(current_user.group_id) 

        if request.method == 'POST':
                newgrant, err = sanitize_general(request.form['newgrant'])
                awardyr, err = sanitize_general(request.form['awardyr'])

                #sanity check
                if err:
                        msg0 = 'Special characters not accepted. Try again or contact facility.'
                        return render_template('add_grant.html', msg0=msg0)

                if newgrant in previousgrants:
                        msg0 = 'This grant is already registered with your name.'
                        return render_template('add_grant.html', msg0=msg0)

                grp_grnt_dct = grp_lead_grp_grnts_dct() #see funcs section
                
                for k, vlist in grp_grnt_dct.items():
                        if newgrant in vlist and current_user.group_id != k:
                                msg0 = 'This grant number has already been registered with another group leader'
                                return render_template('add_grant.html', msg0=msg0)

                #i hate to store a list in a single db table cell, but on this occaision it seemed reasonable 
                updated_grants = grantresults[0] + ',' + newgrant
                updated_years = yearresults[0] + ',' + awardyr

                db.session.query(Users).where(Users.email == current_user.group_id).update({'grant_codes':updated_grants, 'grant_years':updated_years})
                db.session.commit()

                msg1 = 'Grant and award year added successfully.'
                
                return render_template('add_grant.html', msg1=msg1)

        return render_template('add_grant.html')



@app.route('/group_data', methods = ['GET', 'POST'])
@login_required
@keep_out_selected
def group_data():

        #gets current user info to biuld file path below. Code repeated below - case for future function.
        userinfo = db.session.query(Users).filter_by(email=current_user.email).first()
        usergroup = userinfo.group_id
        dir_names = db.session.query(Users).filter_by(email=usergroup).first()
        pwd_user_id = db.session.query(Pwds).with_entities(Pwds.id).filter_by(email=usergroup).first()	

        fname = dir_names.first_name
        lname = dir_names.last_name
        groupmembers = db.session.query(Users).filter_by(group_id=usergroup).all()

        GROUP_DIR = f'/{local_path_start_groups}/{fname}_{lname}_group/current_data'
        files = os.listdir(GROUP_DIR) #diplayed on html page in tree format

        if request.method == 'POST' :
                
                if 'submit_recent' in request.form:
                        #pass folder subtype on to next page
                        return redirect (f'download_page/current_data')

                if 'submit_old' in request.form: 
                        return redirect (f'download_page/old_data')

        return render_template('group_data.html', files=files, fname=fname, lname=lname, groupmembers=groupmembers)



@app.route('/download_page', methods = ['GET', 'POST'])
@app.route('/download_page/<sub_type>', methods = ['GET', 'POST'])
@login_required
def download_page(sub_type='current_data'): #default is current

        sub_type, err = sanitize_batons(sub_type)
        if err:
                msg = 'there was a problem with this request, please try again'
                return render_template('group_data.html', msg=msg)

        #gets current user info to biuld file path below
        userinfo = db.session.query(Users).filter_by(email=current_user.email).first()
        usergroup = userinfo.group_id
        dir_names = db.session.query(Users).filter_by(email=usergroup).first()
        pwd_user_id = db.session.query(Pwds).with_entities(Pwds.id).filter_by(email=usergroup).first()

        fname = dir_names.first_name 
        lname = dir_names.last_name

        LOCAL_GROUP_DIR = f'/{local_path_start_groups}/{fname}_{lname}_group/{sub_type}/' #subtype applied here

        #this and subsequent function means server structure hidden from user
        download_key = get_random_string()
        session['download_key'] = download_key

        filelist = []
        
        #keep walking until it finds the subtype directory
        for root, dirs, files in os.walk(LOCAL_GROUP_DIR):
                outer_dir = os.path.split(root)[1]
                if outer_dir != sub_type: 
                        continue

                #once found, put content in filelist                
                for i, f in enumerate(files):
                        file_root, file_ext = os.path.splitext(f)
                        full_path = os.path.join(root, f)
                        file_ref = f'file{i}'
                        hidden_key = f'{file_ref}_{download_key}'
                        #this way only see download key, not file path in CIMR server
                        session[hidden_key] = full_path 
                        filelist.append((file_ref, f))

        #and displays filelist content as a series of links which each have a hidden, random key			
        return render_template('download_page.html',filelist=filelist)
	



@app.route('/download')
@app.route('/download/<file_ref>') 
def download(file_ref=None):
	
        file_ref, err = sanitize_general(file_ref)
        if err:
                msg = 'there was a problem with this request, please try again'
                return render_template('group_data.html', msg=msg)
	
        if file_ref and 'download_key' in session:
                download_key = session['download_key']
                hidden_file_key = f'{file_ref}_{download_key}'

                #downloads from group data should end up in that users downloads directory      
                if hidden_file_key in session:
                        download_path = session[hidden_file_key]
                        return send_file(download_path, as_attachment=True)




@app.route('/group_expenses', methods = ['GET', 'POST'])
@login_required
@keep_out_selected
def group_expenses():                

        #view for current user
        q0 = db.session.query(Users, ExperimentRequest, ExpensesSummary
                                ).filter(Users.email==current_user.email 
                                         ).join(ExperimentRequest, Users.email == ExperimentRequest.email
                                                ).join(ExpensesSummary, ExperimentRequest.key1 == ExpensesSummary.key1
                                                       ).all()
        #view for group
        q1 = db.session.query(Users, ExperimentRequest, ExpensesSummary
                                ).filter(Users.group_id==current_user.email 
                                         ).join(ExperimentRequest, Users.email == ExperimentRequest.email
                                                ).join(ExpensesSummary, ExperimentRequest.key1 == ExpensesSummary.key1
                                                       ).all()

        use_this = q0
        
        #check ID of current user; whole group info only accessible for group leader
        if current_user.position == 'PI/Project_Lead': 
                use_this = q1 

        table = []
        for u, er, es in use_this: #user, expt_request, expt_expenses
                t_row = [u.group_id, er.email, er.expt_code, er.expt_type,
                         er.grant_code, es.CU_early_discount, es.bench_cost,
                         es.instrument_cost, es.wash_cost, es.dbsearch_cost,
                         es.python_cost, es.extras_description, es.extras_cost]
                table.append(t_row)
                
        return render_template('group_expenses.html', table=table, email=current_user.email)



@app.route('/request_progess_1', methods = ['GET', 'POST'])
@login_required
@keep_out_selected
def request_progress_1():

        #html page shows who you're logged in as and tells you to log out if you're not that person; filtering is done on current credentials
        email = current_user.email
        fname = current_user.first_name
        lname = current_user.last_name
        
        q0 = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.expt_code).where(ExperimentRequest.email==current_user.email).all()
        ecodes = [q[0] for q in q0]

        #(conceivably, an jQuery/AJAX call in the future could negate requirements for _1 _2 page split)
        if request.method == 'POST':
                ecode = request.form['expt']
                exptkey = current_user.email + '*' + ecode
                #key passed to next page in header
                return redirect(f'request_progess_2/{exptkey}')
                        
        return render_template('request_progress_1.html', ecodes=ecodes, email=email, fname=fname, lname=lname)



@app.route('/request_progess_2', methods = ['GET', 'POST'])
@app.route('/request_progess_2/<exptkey>', methods = ['GET', 'POST']) #look ups done on key passed from previous page
@login_required
@keep_out_selected
def request_progress_2(exptkey=None):

        if exptkey is not None:

                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'

                #make 1st list progress info - expt-level info from expt reqs table 
                q0 = db.session.query(ExperimentRequest).filter_by(key1=exptkey).first()
                
                arrv = q0.arrived
                if arrv != 'N':
                        arrv = 'Y'
                        
                t1 = [q0.email, q0.expt_code, q0.expt_type, q0.expt_cat, q0.time_requested, arrv] 


                #make 2nd (nested) list from lots of sample-level info from sample reqs table
                methods_per_sample = get_benchmeth_names_where_box_checked(exptkey) #funcs section
                
                method_string_per_sample = []
                
                for sample in methods_per_sample:
                        methods_str= ', '.join(methods_per_sample)
                        method_string_per_sample.append(methods_str)
                        
                q1 = db.session.query(SampleRequest).filter_by(key1=exptkey).all()
                
                table_rows = []
                
                for idx, res in enumerate(q1):
                        table_row = []
                        if len(method_string_per_sample) > 0:
                                table_row = [res.sample_code, res.protein_conc, res.est_injections, method_string_per_sample[idx]]
                        else:
                                table_row = [res.sample_code, res.protein_conc, res.est_injections]
                        q2 = db.session.query(SampleDetails).with_entities(SampleDetails.bench_methods, SampleDetails.actual_injections).where(SampleDetails.key2==res.key2).first()
                        table_row.append(q2.bench_methods)
                        table_row.append(q2.actual_injections)
                        table_rows.append(table_row)


                #make 3rd list of instrument method progress - imethod-level info - starting from possibility that none made
                t3 = [None]
                q3 = db.session.query(InstrumentDetails).where(InstrumentDetails.key1==exptkey).first()
                if q3:
                        t3 = [q3.method1, q3.method2, q3.method3, q3.method4] 

                #make 4th list of bespoke analysis method progress starting from possibility that none made
                pyhrs = [None]
                q4 = db.session.query(DataRequest).filter_by(key1=exptkey).first()
                if q4:
                        pyhrs = [q4.python_hrs]

                #make 5th list of expenses progress - the will always be some table contents as gets initiated when request first made       
                q5 = db.session.query(ExpensesSummary).filter_by(key1=exptkey).first()

                #make 6th list of signoff progress from q5 info
                isign = q5.bench_instr_db_signoff
                psign = q5.python_signoff
                es_todate = [q5.bench_cost, q5.instrument_cost, q5.wash_cost, q5.dbsearch_cost, q5.python_cost, q5.extras_cost]
                signs = [isign, psign] 
                
        return render_template('request_progress_2.html', t1=t1, t2=table_rows, t3=t3, t4=pyhrs, t5=es_todate, t6=signs)




@app.route('/facility_home', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def facility_home():

        days_togo = days_til_end_finanQ(dtq1, dttdy)
        
        #get these experiment categories lists for dropdowns menus
        allexpts, recentexpts, notarrexpts = get_expt_lists()

        i_update, e_signoff, py_signoff, b_update, cmpd_unsgn_expts = expt_completion_status_categories() #funcs section
                

        if request.method == 'POST':

                if 'view_expenses' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['view_expenses'], notarrexpts)
                        if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'

                        #requests must be updates in correct sequence
                        q2 = db.session.query(InstrumentDetails).filter_by(key1=exptkey).first()
                        if q2 and q2.method1 == 'needs method1':
                                msg = 'you must update some experimental details before viewing these expenses'
                                
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)
                        
                        return redirect(f'view_experiment_expenses/{exptkey}')


                msg = 'email sent'
                text = f'''
                There are experiments that need updating on the facility website with these experiment codes:\n

                Experiments with the following codes were marked as arrived 4 weeks ago and haven't had any instrument updates.\n
                {i_update}\n
                Experiments with these codes were marked as arrived 8 weeks ago and haven't had any expenses signed off.\n
                {e_signoff}\n
                Please update these experiments as appropriate, or delete the experiment if it the request is no longer relevant.
                '''

                email_dct = {'robin': 'pra29@cam.ac.uk', 'john': 'js2126@cam.ac.uk'} #add/remove any more staff members names and address here as appropriate
                target_options = list(email_dct.keys())

                for target in target_options:
                        if target in request.form: #submit buttons names are same as people's names
                                email = Message(f'!!!! Oustanding experiment updates !!!!', sender = app.config['MAIL_USERNAME'], recipients = [email_dct[target]])
                                email.body = text
                                mail.send(email)
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)


                #finance staff kept out of functions to do with experimental updates.
                if current_user.access_level != 'ADMIN':
                        return render_template('sod_off_politely.html')

                        
                if 'mark_arrived' in request.form:

                        exptkey = request.form['unarrived_expt']
                        if exptkey:
                                db.session.query(ExperimentRequest).where(ExperimentRequest.key1==exptkey).update({'arrived':YearQ})
                                db.session.commit()
                                msg = 'this epxeriment has now been marked as arrived'

                                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)
                                if 'Benchwork' not in etype:       
                                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'bench_cost': 0})
                                        db.session.commit()
                        else:
                                msg = 'you must select an experiment'
                        
                        return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                               e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)


                if 'get_details' in request.form:
                        
                        exptkey = request.form['unarrived_expt']
                        if exptkey:
                                return redirect(f'request_view/{exptkey}')
                        else:
                                msg = 'you must select an experiment'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)

                                
                #depending on what was reqested, activities must be completed in bench > instrument > DBsearch > bespoke-analysis > extras order
        
                if 'bench_method' in request.form:
                        
                         exptkey, msg = mark_arr_first(request.form['update_expt'], notarrexpts)
                         if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)
                                
                         return redirect(f'bench_method/{exptkey}')

                if 'bench_hours' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['update_expt'], notarrexpts)
                        if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)
                        return redirect(f'bench_hours/{exptkey}')

                if 'instr_details' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['update_expt'], notarrexpts)
                        if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)
                        return redirect(f'instrument_details/{exptkey}')

                if 'python_hours' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['update_expt'], notarrexpts)
                        if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes,cmpd_unsgn_expts=cmpd_unsgn_expts)
                        return redirect(f'python_hours/{exptkey}')

                if 'extra_costs' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['update_expt'], notarrexpts)
                        if msg or not exptkey:
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update,
                                                       e_signoff=e_signoff, days_togo=days_togo, allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)
                        return redirect(f'extra_costs/{exptkey}')


                #for long-term lingering experiments not signed off
                #more readable page if they are separated off for standard requests
                if 'mod_historical' in request.form: 
                        
                        exptkey, msg = mark_arr_first(request.form['mod_record'], notarrexpts)
                        modtype = request.form['mod_type'] #see lists section at top

                        if not modtype:
                                
                                msg='please select how you want to modify this experiment from the dropdown menu'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                       days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)
                        
                        if msg or not exptkey:
                                
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff, days_togo=days_togo,  allexpts=allexpts)


                        signedoff = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.key1).filter(ExpensesSummary.bench_instr_db_signoff != None).all()
                        finished_expts = [e[0] for e in signedoff]

                        if exptkey in finished_expts:
                                
                                if modtype == 'bench_hours': #no msg here; bench hours can be changed whenever
                                        return redirect(f'{modtype}/{exptkey}')
                                
                                if modtype == 'python_hours':
                                        
                                        msg = 'This experiment has been signed off and originates from a previous quarter. Additional analysis hours must be added as a separate, data-only request.'
                                        return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                       days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)
                                
                                if modtype in ['bench_method', 'instrument_details', 'extra_costs']:
                                        
                                        msg='this experiment has already been signed off'
                                        return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                       days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)
 
                        return redirect(f'{modtype}/{exptkey}') #effectively takes you to same pages used for updating non-historical-records



                if 'sign_historical' in request.form:
                        
                        exptkey, msg = mark_arr_first(request.form['sign_record'], notarrexpts)
                        
                        if msg or not exptkey:
                                
                                msg='please select an experiment that has been marked as arrived'
                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)
                        
                        return redirect(f'view_experiment_expenses/{exptkey}') #effectively takes you to same pages used for signing-off non-historical-records
                                               
                  
        return render_template('facility_home.html', rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff, py_signoff=py_signoff,
                               b_update=b_update, days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)




@app.route('/request_view', methods = ['GET', 'POST'])
@app.route('/request_view/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def request_view(exptkey=None):

        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_view.html', msg=msg)

                #all code until POST is setting variables to be displayed on request-view page
                fn, ln, gid, itype, email = get_user_details(exptkey)
                
                q1 = db.session.query(SampleRequest).filter_by(key1=exptkey).all()


                #make 2nd (nested) list from lots of sample-level info from sample reqs table
                methods_per_sample = get_benchmeth_names_where_box_checked(exptkey) #funcs section
                
                method_string_per_sample = []
                for sample in methods_per_sample:
                        methods_str= ', '.join(methods_per_sample)
                        method_string_per_sample.append(methods_str)

                table_rows = []
                
                for idx, res in enumerate(q1):
                        table_row = []
                        if len(method_string_per_sample) > 0:
                                table_row = [res.sample_code, res.protein_conc, res.est_injections, method_string_per_sample[idx]]
                        else:
                                table_row = [res.sample_code, res.protein_conc, res.est_injections]
                        q2 = db.session.query(SampleDetails).with_entities(SampleDetails.bench_methods, SampleDetails.actual_injections).where(SampleDetails.key2==res.key2).first()
                        table_row.append(q2.bench_methods)
                        table_row.append(q2.actual_injections)
                        table_rows.append(table_row)

                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey) #funcs section

                return render_template('request_view.html', table_rows=table_rows, fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, dbcat=dbcat,reqdt=reqdt, enotes=enotes)
        
        return render_template('request_view.html')



@app.route('/bench_method', methods = ['GET', 'POST'])
@app.route('/bench_method/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def bench_method(exptkey=None):

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        table_rows = []
        msg = ''
        
        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_view.html', msg=msg)

                #set variables to be displayed on html page
                fn, ln, gid, itype, email = get_user_details(exptkey)
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)
                instit_type, instit_price, verb = instit_type_price_discount(institute_price_dict, exptkey)

                if 'Benchwork' not in etype:
                        
                        msg = 'Benchwork was not requested, no need to fill in this page. Use top menu to return to Facility Home'
                        return render_template('bench_method.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, bench_methods=bench_methods, table_rows=table_rows, msg=msg)

                q1 = db.session.query(SampleRequest).filter_by(key1=exptkey).all()
                
                sample_keys  = []
                for res in q1:
                        sample_keys.append(res.key2)
                        
                method_string_per_sample = []
                table_rows = []
                bmeth = None
                act_injs = []
                bmeths_gelbands = []
                bmeths_others = []
                bench_expenses = []
                bmeths = []
                updt_injs = []

                methods_per_sample = get_benchmeth_names_where_box_checked(exptkey) #funcs section

                #makes non-redun list for table
                for sample in methods_per_sample:
                        methods_str= ', '.join(methods_per_sample)
                        method_string_per_sample.append(methods_str)
                       
                for idx, res in enumerate(q1):
                        table_row = [res.sample_code, res.protein_conc, res.est_injections, method_string_per_sample[idx]]
                        q2 = db.session.query(SampleDetails).with_entities(SampleDetails.bench_methods, SampleDetails.actual_injections).where(SampleDetails.key2==res.key2).first()
                        table_row.append(q2.bench_methods) #so you can see if the values is the default 'needs bench methods' or it's been filled in already by staff
                        table_row.append(q2.actual_injections) #so you can see if staff updated injection number. if updated, should correspend to injection list length
                        table_rows.append(table_row)



                if request.method =='POST' and 'Benchwork' in etype: #makes sure you can't post from page if no bwork requested

                        #order-of-contents in sublists is critical for filing field ids on template page - change at your peril
                        for sublist in table_rows:
                                bmeth = request.form[f'bmeth_{sublist[0]}']
                                est_or_act_inj = request.form[f'estinj_{sublist[0]}']
                                updt_injs.append(est_or_act_inj) #updated injections
                                bmeths.append(bmeth)

                                if bmeth == 'needs bench method(s)':
                                        msg = 'please make sure bench methods are added for each row'
                                        return render_template('bench_method.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, bench_methods=bench_methods, table_rows=table_rows, msg=msg, updt_injs=updt_injs)

                                if bmeth == bench_methods[1]: #bench_methods is list generated at top of this route, [1] is gel_band.
                                        bmeths_gelbands +=  [bmeth]*int(est_or_act_inj) #cos gelband method gets charged per injection (i.e. per band, which is not always the same as per sample)

                                else:
                                        bmeths_others.append(bmeth)

                        #makes dict {sample_key:[methods, injection number]}
                        bmeths_others = list(set(bmeths_others))
                        bmeths_all = bmeths_gelbands + bmeths_others
                        values = list(zip(bmeths, updt_injs)) 
                        key2_bmeths_updtinjs = dict(zip(sample_keys, values)) 


                        for bmeth in bmeths_all:
                                
                                if bmeth == 'needs method(s)': #default fill, therefore not updated
                                        msg = 'Each sample needs a method. If you need to delete a sample, do this first at Delete Samples in the top menu bar.'
                                        return render_template('bench_method.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, bench_methods=bench_methods, table_rows=table_rows, msg=msg, updt_injs=updt_injs)

                                #calculates costs from method mins and price-per-min dict
                                bmeth_mins =  benchmins_dict[bmeth]
                                bmeth_costs = bmeth_mins*permin_price_dict['bench']
                                bmeth_costs_instit = bmeth_costs*instit_price
                                bench_expenses.append(bmeth_costs_instit)

                        bench_expenses_total = np.sum(bench_expenses) #np is numpy

                        #ExpensesSummary gets updated w bench costs
                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'bench_cost': bench_expenses_total})
                        db.session.commit()

                        #SampleDetails gets updated w new injection number
                        for k, v in key2_bmeths_updtinjs.items():
                                db.session.query(SampleDetails).where(SampleDetails.key2==k).update({'bench_methods': v[0], 'actual_injections': v[1]})
                                db.session.commit()

                                                        
                        queue, PInames, PIinitials, Rinitials  = write_injection_queue(gid, fn, ln, exptkey) #funcs section
                        with open(f'/{local_path_start_facility}/injection_lists/{PIinitials}_{Rinitials}_{ecode}.txt', 'w') as fw:
                                for injection in queue:
                                        fw.write(f'{injection}\n')


                        return redirect(url_for('facility_home'))
                
                return render_template('bench_method.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, bench_methods=bench_methods, table_rows=table_rows, msg=msg)
        
        return render_template('bench_method.html', bench_methods=bench_methods, msg=msg)



@app.route('/bench_hours', methods = ['GET', 'POST'])
@app.route('/bench_hours/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def bench_hours(exptkey=None):

        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_view.html', msg=msg)

                #get vars for page text, see funcs section
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)

                msg = ''

                if 'Benchwork' not in etype :
                        msg = 'Benchwork was not requested, no need to fill in this page'

                if etype == 'Benchwork + Samples + Database search':
                        q0 = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.bench_cost).where(ExpensesSummary.key1==exptkey).first()

                        #if it got a bench method earlier, the expen summ table will have a value in this cell, if not then no q0. 
                        if not q0[0]:
                                
                                i_update, e_signoff, py_signoff, b_update, cmpd_unsgn_expts = expt_completion_status_categories() #funcs section, needed for page dropdowns
                                allexpts, recentexpts, notarrexpts = get_expt_lists() #funcs section, needed for page dropdowns
                                days_togo = days_til_end_finanQ(dtq1, dttdy)
                                msg = 'You need to click Facility Home in the top menu, make sure this message has disappeared, then add benchmethod(s) before adding bench hours'

                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                       days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)

                fn, ln, gid, itype, email = get_user_details(exptkey) #funcs section, for page text vars
                
                q2 = db.session.query(BenchHours).with_entities(BenchHours.bench_hrs).filter_by(key1=exptkey).first()
                
                #default is 0 if table cell empty, and if empty then no q2
                prev_hrs = 0
                if q2:
                        prev_hrs = q2[0]

                if request.method == 'POST': 
                        
                        if 'Bench' in etype:
                                hrs = prev_hrs + float(request.form['curr_hrs'])

                                if hrs < 0:
                                        msg = 'total hours cannot be less than zero; please check your entry' #because you can subtract hours, too
                                        return render_template('bench_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, prev_hrs=prev_hrs, msg=msg)
                                        
                                db.session.query(BenchHours).where(BenchHours.key1==exptkey).update({'bench_hrs':hrs, 'time_updated':now})
                                db.session.commit()
                                return redirect(url_for('facility_home'))
                        
                        elif 'Bench' not in etype:
                                msg = 'Benchwork was not requested for this experiment'
                                return render_template('bench_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, msg=msg)
                        
                return render_template('bench_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, prev_hrs=prev_hrs, msg=msg)
        
        return render_template('bench_hours.html')




####################################################################################################################################

@app.route('/instrument_details', methods = ['GET', 'POST'])
@app.route('/instrument_details/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def instrument_details(exptkey=None):

        #for each experiment, you can inject or re-inject the samples up to 4 times with different instrument methods, different washes, different data-search requirements.
        #this happends if someone wants e.g. a DDA vs DIA method, or want you to search against a new database, or they loaded the expt with diffnt sample-types. 
        #hence the table with 4 input rows. mostly just the first row will get filled. 
        
        #get info for dropdowns
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_view.html', msg=msg)

                #get etype for response options, queries and other info for page text variables
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)

                if etype == 'Data only':
                        msg = 'This is a data only request, no need to fill in this page'
                        return render_template('instrument_details.html', msg=msg,  ecode=ecode, etype=etype, m=None, i=None, w=None, s=None)


                #benchwork section must be completed first if requested. q0 will be none if this hasn't been done. 
                if etype == 'Benchwork + Samples + Database search':
                        qx = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.bench_cost).where(ExpensesSummary.key1==exptkey).first()

                        if not qx[0]:

                                i_update, e_signoff, py_signoff, b_update, cmpd_unsgn_expts = expt_completion_status_categories() #funcs section, needed for page dropdowns
                                allexpts, recentexpts, notarrexpts = get_expt_lists() #funcs section, needed for page dropdowns
                                days_togo = days_til_end_finanQ(dtq1, dttdy) #funcs section, needed for days warning
                                msg = 'You click Facility Home in the top menu, make sure this message has diappeared, then add benchmethod(s) before adding instrument details'

                                return render_template('facility_home.html', msg=msg, rcntexpts=recentexpts, notarrexpts=notarrexpts, i_update=i_update, e_signoff=e_signoff,
                                                       days_togo=days_togo,  allexpts=allexpts, modtypes=modtypes, cmpd_unsgn_expts=cmpd_unsgn_expts)

                        
                #assuming nothing caught be conditional statements above, can get on with loading page and retrieving form info
                        
                fn, ln, gid, itype, email = get_user_details(exptkey) #funcs section, vars for queries and page text

                q0 = db.session.query(SampleRequest).with_entities(SampleDetails.bench_methods, SampleDetails.actual_injections).filter_by(key1=exptkey).all()                
                q1 = db.session.query(SampleRequest).with_entities(SampleRequest.sample_code, SampleRequest.key2).filter_by(key1=exptkey).all()
                
                scodes = [q[0] for q in q1]
                sample_keys = [q[1] for q in q1]
                bmeths = [q[0] for q in q0]
                actual_injs = [q[1] for q in q0]

                #passed to page, fills in table
                dbinfo = list(zip(scodes, bmeths, actual_injs))
                
                q2 = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.expt_type, ExperimentRequest.expt_code).filter_by(key1=exptkey).all()

                #more page text variable setting
                etype = ''
                ecode = ''
                for res in q2:
                        etype = res.expt_type
                        ecode = res.expt_code

                instit_type, instit_price, verb = instit_type_price_discount(institute_price_dict, exptkey) #funcs section, page text vars

                q5 = db.session.query(InstrumentDetails).filter_by(key1=exptkey).first()
                
                #methods, instrument, search, washes: fills in form table on html page w current expt status
                m = [q5.method1, q5.method2, q5.method3, q5.method4]
                i = [q5.injections1, q5.injections2, q5.injections3, q5.injections4]
                s = [q5.search1, q5.search2, q5.search3, q5.search4]
                w = [q5.washes1, q5.washes2, q5.washes3, q5.washes4]
                                  

                if request.method == 'POST':
                        
                        #add-on workaround to financial and calendar yrs being different
                        year = thisyear
                        yearQ = thisyear + '_' + get_Q_for_today()
                        if Q4hangover:
                                yearQ = lastyear + '_' + get_Q_for_today()


                        #all form info from table on html page. positions are critical to next code chunk - don't change
                        list1 = [request.form['imeth1'], request.form['ninj1'], request.form['db1'], request.form['wsh1']]
                        list2 = [request.form['imeth2'], request.form['ninj2'], request.form['db2'], request.form['wsh2']]
                        list3 = [request.form['imeth3'], request.form['ninj3'], request.form['db3'], request.form['wsh3']]
                        list4 = [request.form['imeth4'], request.form['ninj4'], request.form['db4'], request.form['wsh4']]

                        counter = 0
                        lists = [list1, list2, list3, list4]
                        rows = []
                        
                        for ls in lists:
                                
                                if ls[0] == 'repeat DB search(0)':
                                        row = [ls[0], 0,0,0,0,0,0]
                                        rows.append(row)
                                else:
                                        if ls != ['', '', '', '']:
                                                counter += 1
                                                row = []
                                                
                                                row.append(ls[0]) #puts instr method into row
                                                row.append(ls[1]) #puts instr injection into row
                
                                                imins = instrmins_dict[ls[0]] * int(ls[1]) #length instr method * number of injections for that method
                                                row.append(imins) #puts total minutes for each intrument method into row
                                                
                                                row.append(imins*permin_price_dict['instrument']) #instr mins * cost per min of MStime into row
                                                
                                                row.append(ls[2]) #DB search request y/n/ into row
                                                if ls[2] == 'Yes':
                                                        dbmins = datamins_dict[ls[0]]
                                                        dbcost = dbmins*permin_price_dict['data_standard']
                                                        row.append(dbcost) #put DB search cost into row
                                                elif ls[2] != 'Yes':
                                                        row.append(0) #or puts zero if DB search not requested
                                                        
                                                if int(ls[3]) > 2:
                                                         row.append(extra_wash_mins*permin_price_dict['instrument']) #puts extra wash charge in washcharge list
                                                elif int(ls[3]) <= 2:
                                                         row.append(0) #or puts in zero if no extra wash charge
                                                                                                         
                                                rows.append(row)

                        instr_charge_total = (np.sum([row[3] for row in rows]))*instit_price
                        db_charge_total = (np.sum([row[5] for row in rows]))*instit_price
                        wash_charge_total = (np.sum([row[-1] for row in rows]))*instit_price

                        #SampleDetails, InstrumentDetails and ExpensesSummary get updated at this point
                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'instrument_cost': instr_charge_total, 'wash_cost':wash_charge_total, 'dbsearch_cost': db_charge_total, 'Yr_instr_run':year, 'YrQ_instr_run':yearQ})          
                        db.session.commit()

                        #counter incr by 1 for each of the 4 table rows on the html page
                        for n in range(1, counter+1):
                                db.session.query(InstrumentDetails).where(InstrumentDetails.key1==exptkey).update({f'method{n}':lists[n-1][0], f'injections{n}':lists[n-1][1], f'search{n}':lists[n-1][2], f'washes{n}':lists[n-1][3], 'YrQ_updated':yearQ})
                        db.session.commit()

                        return redirect(url_for('facility_home'))
                
                return render_template('instrument_details.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, ecat=ecat, scodes=scodes, instr_methods=instr_methods, m=m, i=i, s=s, w=w, dbinfo=dbinfo)
        
        return render_template('instrument_details.html')



@app.route('/python_hours', methods = ['GET', 'POST'])
@app.route('/python_hours/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def python_hours(exptkey=None):

        #when experiment requests are submitted, downstream tables are filled in with initial, default values.
        #a data_request table entry can be initiated later, however, as users often don't realise they needed bespoke analysis when they made the request

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        #this prompts bioinformatician to sign off analysis if the sign-off for instrument work is imminent. 
        days_togo = days_til_end_finanQ(dtq1, dttdy)
        
        msg=''

        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('python_hours.html', msg=msg)

                #get vars for calcs and page text
                fn, ln, gid, itype, email = get_user_details(exptkey)
                instit_type, instit_price, verb = instit_type_price_discount(institute_price_dict, exptkey)
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)

                proceed = True
                q1a, q1b = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.bench_instr_db_signoff, ExpensesSummary.python_signoff).filter_by(key1=exptkey).first()

                if q1b:
                        proceed = False #it's already been signed off; q1b has returned a value
                
                if q1a and not q1b:
                        q1aYrQ = q1a[-7:]
                        if YearQ != q1aYrQ:
                                proceed = False #it's been signed off for instrument work (q1a has a value) but not for python work (q1b has no value)


                prev_hrs = 0
                new_data_req = False #affects whether database update or addition at end of this route, see comment at top of route
                q2 = db.session.query(DataRequest).with_entities(DataRequest.python_hrs).filter_by(key1=exptkey).first()
                if q2:
                        prev_hrs = q2[0]
                if not q2:
                        new_data_req = True

                if request.method == 'POST':
                        
                        if not proceed:
                                
                                if q1a:
                                        #signing off instrument work takes precedence; Robin remebering to sign anything off is miraculous, so there should be no impediments!
                                        msg = 'The mass spec work was signed off last quarter, so you must make a new, data only request for this users remaining python hours'
                                if q1b:
                                        q1bYrQ = q1b[-7:]
                                        msg = f'You have already signed off python hours for this experiment in {q1bYrQ}'
                                        
                                return render_template('python_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, prev_hrs=prev_hrs, msg=msg)
                                                        
                        if 'submit_pyhrs' in request.form:
                                
                                hrs = prev_hrs + float(request.form['curr_hrs'])
                                hrs_cost = ((hrs*60)*permin_price_dict['data_bespoke'])*instit_price

                                if hrs_cost < 0:
                                        msg = 'hours and costs cannot be less than zero; please check your entry'
                                        return render_template('python_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, prev_hrs=prev_hrs, msg=msg, days_togo=days_togo)

                                if new_data_req:
                                        newdr = DataRequest(exptkey, hrs, '', '', now)
                                        db.session.add(newdr)
                                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'python_cost':hrs_cost})
                                        db.session.commit()

                                if not new_data_req:
                                        db.session.query(DataRequest).where(DataRequest.key1==exptkey).update({'python_hrs':hrs, 'time_updated':now})
                                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'python_cost':hrs_cost})
                                        db.session.commit()
                                        
                                return redirect(url_for('facility_home'))
                        
                return render_template('python_hours.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, prev_hrs=prev_hrs, msg=msg, days_togo=days_togo)
        
        return render_template('python_hours.html')



@app.route('/extra_costs', methods = ['GET', 'POST'])
@app.route('/extra_costs/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def extra_costs(exptkey=None):

        #this page doesn't get used much but it takes positive and negative float input
        #therefore could represent as useful way of correcting costs that can't be changed elsewhere for whatever reason
        #as well as it's intended purpose
        
        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('extra_costs.html', msg=msg)

                fn, ln, gid, itype, email = get_user_details(exptkey)
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)

                q2 = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.extras_description, ExpensesSummary.extras_cost).where(ExpensesSummary.key1==exptkey).first()
                d = q2[0]
                c= q2[1]

                if request.method == 'POST':
                        
                        description = request.form['description']
                        cost = int(request.form['cost'])

                        if cost < 0:
                                msg = 'costs cannot be less than zero; please check your entry'
                                return render_template('extra_costs.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, d=d, c=c, msg=msg)
                        
                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'extras_description':description, 'extras_cost':cost})
                        db.session.commit()
                        return redirect(url_for('facility_home'))
                        
                return render_template('extra_costs.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, d=d, c=c)
        
        return render_template('extra_costs.html')



@app.route('/view_experiment_expenses', methods = ['GET', 'POST'])
@app.route('/view_experiment_expenses/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def view_experiment_expenses(exptkey=None):

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
        msg = ''


        if exptkey is not None:

                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('view_experiment_expenses.html', msg=msg)

                #get page-text vars, set 'gc' appropriately
                fn, ln, gid, itype, email = get_user_details(exptkey)
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)
                instit_type, instit_price, verb = instit_type_price_discount(institute_price_dict, exptkey)
                if 'Cambridge' not in instit_type:
                        gc = 'not required'
                        
                dlist = [fn, ln, ecode, gid, instit_type, verb, gc, etype, ecat] #in list for ease of templating
                bmeth_charge_details = []
                imeth_rows = []
                wash_rows = []
                search_rows = []
                python_row = []
                extras_row = []
                sum_list = []
                EStable_sums = []

                q4 = db.session.query(ExpensesSummary).filter_by(key1=exptkey).first()
                q1a, q1b = db.session.query(ExpensesSummary).with_entities(ExpensesSummary.bench_instr_db_signoff, ExpensesSummary.python_signoff).filter_by(key1=exptkey).first()

                proceed = True


                #data only requsts will only ever need one type of signoff; a data sign-off
                if 'Data only' in etype:

                        if current_user.email == authorised_for_data_signoff: #see remote settings section at top
                                commit = True

                        q3a, q3b = db.session.query(DataRequest).with_entities(DataRequest.python_hrs, DataRequest.time_updated).filter_by(key1=exptkey).first()

                        if q1b:
                                proceed = False
                                msg = 'This experiment has already been signed off. Nothing further can be added without a new experiment request.'
                        if not q3b:
                                proceed  = False
                                msg = 'Python hours have not been updated for this experiment; please go back and do this first.'
                        
                        if q3a:
                                row1_p = [q3a*60, permin_price_dict['data_bespoke'], (q3a*60)*permin_price_dict['data_bespoke'], (q3a*60)*permin_price_dict['data_bespoke']*instit_price]
                                python_row.append(row1_p)

                        sum_list = [0, 0, 0, 0, np.sum([row[-1] for row in python_row]), 0]
                        EStable_sums = [0, 0, 0, 0, q4.python_cost, 0]

                        if request.method == 'POST':
                                
                                if current_user == authorised_for_data_signoff:
                                        if not proceed:
                                                return render_template('view_experiment_expenses.html', dlist=dlist, bench=bmeth_charge_details, imeth=imeth_rows, dbsearch=search_rows,
                                                       wash=wash_rows, python=python_row, extras=extras_row, page=sum_list, EStable=EStable_sums, msg=msg)
                                
                                        db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'python_signoff':signoff_d,  'YrQ_python_run':YearQ})
                                        db.session.commit()
                                        return redirect(url_for('facility_home'))
                                
                                if current_user != authorised_for_data_signoff:
                                        return render_template ('sod_off_politely.html')


                #mat or may not include bespoke data analysis requirements
                if 'Data only' not in etype:

                        if q1a and q1b:
                                proceed = False
                                msg = 'This experiment has already been signed off. Nothing further can be added without a new experiment request.'

                        q2 = db.session.query(InstrumentDetails).filter_by(key1=exptkey).first()
                        if q2.method1 == 'needs method1':
                                proceed = False
                                msg = 'you must fill in the required details before viewing expenses'

                                
                        q0 = db.session.query(SampleDetails).with_entities(SampleDetails.bench_methods).filter_by(key1=exptkey).all()
                        bmeths = [q[0] for q in q0]


                        #remember this got updated on the instrument details page; it should always match the instrument table
                        q1c = db.session.query(SampleRequest).with_entities(SampleDetails.actual_injections).filter_by(key1=exptkey).all()
                        estinjs = [q[0] for q in q1c]

                        b_injs = list(zip(bmeths, estinjs))
                        b_injs = [list(i) for i in b_injs]


                        #gel bands are priced per injection when doing bench work. everything else is priced per sample
                        #therefore if not gelband, injections gets set to 1 during benchwork calculations
                        for pr in b_injs: #pr pair
                                if 'gelbandID' not in pr[0]:
                                        pr[1] = 0
                                        bmeth_charge_details.append(pr)
                                else:
                                        bmeth_charge_details.append(pr) 

                        
                        #extends pair list by setting prices at different calculation stages (view expense page shows calc details)
                        for pr in bmeth_charge_details:
                                pr[1] = int(pr[1])
                                pr.append(benchmins_dict[pr[0]])
                                if pr[1] != 0:
                                        pr.append(benchmins_dict[pr[0]] * pr[1]) #implies it's a gel_band
                                        pr.append(permin_price_dict['bench'])
                                        pr.append((benchmins_dict[pr[0]] *pr[1])*permin_price_dict['bench'])
                                        pr.append(((benchmins_dict[pr[0]] *pr[1])*permin_price_dict['bench']) * instit_price)
                                else:
                                        pr.append(benchmins_dict[pr[0]] * 1) #implies it's not a gel_band
                                        pr.append(permin_price_dict['bench'])
                                        pr.append((benchmins_dict[pr[0]] * 1)*permin_price_dict['bench'])
                                        pr.append(((benchmins_dict[pr[0]] * 1)*permin_price_dict['bench']) * instit_price)


                        meth = q2.method1 #first row html table
                        inj = q2.injections1 #second row html table
                        more_meths = [q2.method2, q2.method3, q2.method4] #subsequent rows
                        more_injs = [q2.injections2, q2.injections3, q2.injections4]
                        imin = permin_price_dict['instrument']

                        #deal w first row. there must be at least one row. usuually there'll onyl be one
                        row_m = [meth, instrmins_dict[meth], inj, inj*instrmins_dict[meth], imin, (inj*instrmins_dict[meth])*imin, ((inj*instrmins_dict[meth])*imin)*instit_price]
                        imeth_rows.append(row_m)
                        
                        for i, next_meth in enumerate(more_meths):
                                if next_meth: #prevents error if there weren't any subsequent rows
                                        if next_meth == 'repeat DB search(0)': #don't put anything in instrument methods if just asking for search against different database
                                                row_m = None
                                        inj = more_injs[i]
                                        row_m = [next_meth, instrmins_dict[next_meth], inj, inj*instrmins_dict[next_meth], imin, (inj*instrmins_dict[next_meth])*imin, ((inj*instrmins_dict[next_meth])*imin)*instit_price]
                                        imeth_rows.append(row_m)


                        #same first row, subsequent rows approach as above
                        n_wash = q2.washes1
                        n_washes = [q2.washes2, q2.washes3, q2.washes4]
                        washYN = 'Yes'
                        extra_wash_mins = reset_extra_wash_mins()
                        if n_wash <= 2: #you only incur the extra wash charge if over two washes per experiment (yup, total per experiment is what Mike wanted)
                                washYN = 'No'
                                extra_wash_mins = 0

                        #details for view page
                        row_w = [n_wash, washYN, extra_wash_mins, imin, extra_wash_mins*imin, (extra_wash_mins*imin)*instit_price]
                        wash_rows.append(row_w)
                        
                        for i, w in enumerate(n_washes):
                                if w  and w > 2:
                                        row_w = [w, washYN, extra_wash_mins, imin, extra_wash_mins*imin, (extra_wash_mins*imin)*instit_price]
                                        wash_rows.append(row_w)

                        #same first row, subsequent rows approach as above
                        search = q2.search1
                        searches = [q2.search2, q2.search3, q2.search4]
                        meth = q2.method1
                        dmin = permin_price_dict['data_standard']

                        #details for view page
                        row_s = [search, datamins_dict[meth], dmin, datamins_dict[meth]*dmin, (datamins_dict[meth]*dmin)*instit_price]
                        search_rows.append(row_s)


                        for i, search in enumerate(searches):
                                if search == 'Yes':
                                        row_s = [search, datamins_dict[more_meths[i]], dmin, datamins_dict[more_meths[i]]*dmin, (datamins_dict[more_meths[i]]*dmin)*instit_price]
                                        search_rows.append(row_s)

                        #check to see if additional data analysis was requested besides standard search
                        if db.session.query(DataRequest).filter_by(key1=exptkey).first():
                                q3a = db.session.query(DataRequest).with_entities(DataRequest.python_hrs).filter_by(key1=exptkey).first()
                                q3a = q3a[0]
                                row1_p = [q3a*60, permin_price_dict['data_bespoke'], (q3a*60)*permin_price_dict['data_bespoke'], (q3a*60)*permin_price_dict['data_bespoke']*instit_price]
                                python_row.append(row1_p)

                        #check to see if extras
                        if q4:
                                row1_e = [q4.extras_description, q4.extras_cost]
                                extras_row.append(row1_e)

                        #sum each row
                        page_sums = [np.sum([row[-1] for row in bmeth_charge_details]),
                                     np.sum([row[-1] for row in imeth_rows]),
                                     np.sum([row[-1] for row in search_rows]),
                                     np.sum([row[-1] for row in wash_rows]),
                                     np.sum([row[-1] for row in python_row]),
                                     np.sum([row[-1] for row in extras_row])]

                        #format nicely; 0.0 for nulls and 3dp for floats
                        for ps in page_sums:
                                if not ps:
                                        ps = 0.0
                                sum_list.append(ps)
                        sum_list = ['%.3f' % n for n in sum_list]
                        EStable_sums = [q4.bench_cost, q4.instrument_cost, q4.dbsearch_cost, q4.wash_cost, q4.python_cost, q4.extras_cost]

                        #get message, not just page error if didn't make it through the calculation
                        if not EStable_sums:
                                proceed = False

                        if request.method == 'POST':
                                if not proceed:
                                        return render_template('view_experiment_expenses.html', dlist=dlist, bench=bmeth_charge_details, imeth=imeth_rows, dbsearch=search_rows,
                                               wash=wash_rows, python=python_row, extras=extras_row, page=sum_list, EStable=EStable_sums, msg=msg)


                                if 'ms_signoff' in request.form:
                                        if current_user.email == authorised_for_instrument_signoff: #see remote settings section at top
                                                db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'bench_instr_db_signoff':signoff_i, 'Yr_instr_run':thisyear, 'YrQ_instr_run':YearQ})
                                                db.session.commit()
                                                return redirect(url_for('facility_home'))
                                        if current_user != authorised_for_instrument_signoff:
                                                return render_template ('sod_off_politely.html')

                                                
                                if 'py_signoff' in request.form:
                                        if current_user.email == authorised_for_data_signoff: #see remote settings section at top
                                                db.session.query(ExpensesSummary).where(ExpensesSummary.key1==exptkey).update({'python_signoff':signoff_i,  'YrQ_python_run':YearQ})
                                                db.session.commit()
                                                return redirect(url_for('facility_home'))
                                        if current_user != authorised_for_data_signoff:
                                                return render_template ('sod_off_politely.html')
                                        

                return render_template('view_experiment_expenses.html', dlist=dlist, bench=bmeth_charge_details, imeth=imeth_rows, dbsearch=search_rows,
                                       wash=wash_rows, python=python_row, extras=extras_row, page=sum_list, EStable=EStable_sums, msg=msg)

        return render_template('view_experiment_expenses.html', dlist=dlist, bench=bmeth_charge_details, imeth=imeth_rows, dbsearch=search_rows,
                                       wash=wash_rows, python=python_row, extras=extras_row, page=sum_list, EStable=EStable_sums, msg=msg)


@app.route('/add_experiment_1', methods = ['GET', 'POST'])
@login_required
@admin_required
def add_experiment_1():

        #select user on page for on who's behalf you're adding an experiment
        #page split as don't know how to efficiently do this otherwise
        userdict = make_userdict_for_javascript()
        em = ''

        if request.method == 'POST' and 'this_user' in request.form:
                em = request.form['uemail']
                return  redirect(f'add_experiment_2/{em}')

        return render_template('add_experiment_1.html', userdict=userdict)



@app.route('/add_experiment_2', methods = ['GET', 'POST'])
@app.route('/add_experiment_2/<em>', methods = ['GET', 'POST'])
@login_required
@admin_required
def add_experiment_2(em=None):

        #and now do the actual experiment adding
        #similat but not identical to experiment request form
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        if em is not None:

                details = db.session.query(Users).with_entities(Users.first_name, Users.last_name, Users.group_id, Users.institute_type).where(Users.email == em).first()
                fn = details.first_name
                ln = details.last_name
                gid = details[2]
                itype = details[3]

                result_e = db.session.query(ExperimentRequest).with_entities(ExperimentRequest.expt_code).filter_by(email=em).distinct()
                used_codes = [r for (r,) in result_e]

                #sets initial number of rows at one (hidden field on template)
                nrows = 1
                nameset = get_row_names(nrows)

                #for the dropdown showing user-specific grant list and dictionary of grants, years for setting expenses summary table
                grant_or_type = [itype]
                grant_discount = 'N'
                grantyear_dict = None
                
                if itype == 'Cambridge University':
                        
                        result_g = db.session.query(Users).with_entities(Users.grant_codes).filter_by(email=em).all()
                        result_y = db.session.query(Users).with_entities(Users.grant_years).filter_by(email=em).all()

                        #split up and remake lists so can make dict and add them back to table in proper list format
                        grantyears = []
                        for res in [result_g, result_y]:
                                #[res_g, res_y] is a list of two eq-length tuples: [(id1, id2, id3), (yr1, yr2, yr3)]
                                all_group_grants1 = [i for tup in res for i in tup] 
                                all_group_grants2 = [entry.split(',') for entry in all_group_grants1]
                                all_group_grants3= [i for sblist in all_group_grants2 for i in sblist]
                                grantyears.append(all_group_grants3)

                        grantyear_dict = dict(zip(grantyears[0], grantyears[1]))
                        grant_or_type = list(grantyear_dict.keys())

                #form refill variables
                ecode = None
                ecat = None
                dbcat = None
                gcode= None
                etype = None
                enotes = None
                
                #check if experiment or data request
                data_only = False
                benchwork = False
                samples = False

                
        if request.method == 'POST':
                
                #santise user input
                ecode = sanitize_code(request.form['exp_code'])
                gcode= request.form['gcode']
                etype = request.form['etype']
                ecat = request.form['ecat']
                dbcat = request.form.getlist('dbcat')
                enotes = sanitize_text(request.form['enotes'])

                dbcat = ', '.join(dbcat)

                #check that current ecode is unqiue
                if ecode in used_codes:
                        msg = 'experiment codes cannot be reused'
                        return render_template('add_experiment_2.html', nameset=get_row_names(nrows), fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes, used_codes=used_codes, msg=msg)

                #sets conditions for which parts of price-per-method will be applied --> how downstream tables get filled
                if 'Data only' in etype:
                        data_only = True
                if 'Benchwork' in etype:
                        benchwork = True
                if 'Samples' in etype:
                        samples = True

                #sets conditions for expenses summary table
                if grantyear_dict:
                        if int(grantyear_dict[gcode]) <= 2022:
                                grant_discount = 'Y'

                #get number of rows from template
                nrows = int(request.form["nrows"])
                nrows = min(max(nrows, 1), 50)
                
                #timestamp and set useremail-ecode unique key:
                time_requested = now
                arrived = 'N'
                key1 = '*'.join((em, ecode))

               #initiate downstream tables and injection list as per the user experiment request route 
                if "submit_all" in request.form:
                        sample_names = []
                        acquisition_queue = []
                        er = [em, ecode, key1, gcode, etype, ecat, dbcat, enotes, time_requested, arrived]
                        er = ExperimentRequest(er[0], er[1], er[2], er[3], er[4], er[5], er[6], er[7], er[8], er[9])
                        es = [key1, gcode, grant_discount, None, None, None, None, None, None, None, None, None, 0, None, None]
                        es = ExpensesSummary(es[0], es[1], es[2], es[3], es[4], es[5], es[6], es[7], es[8], es[9], es[10], es[11], es[12], es[13], es[14])
                        ind = [key1, 'needs method1', 0, 'Yes', None, None, None, None, None, None, None, None, None, None, None, None, None, time_requested]
                        ind1 = InstrumentDetails(ind[0], ind[1], ind[2], ind[3], ind[4], ind[5], ind[6], ind[7], ind[8], ind[9], ind[10], ind[11], ind[12], ind[13], ind[14], ind[15], ind[16], ind[17])

                                      
                        if data_only:
                                db.session.add(er)
                                db.session.commit()
                                data_request = [key1, 0, '', '', time_requested]
                                dr = data_request
                                dr = DataRequest(dr[0], dr[1], dr[2], dr[3], dr[4])
                                db.session.add(dr)
                                db.session.add(es)
                                db.session.commit()
                                return redirect(f'request_confirmed/{key1}')
                                
                          
                        if samples:
                                nrange = int(request.form["nrows"])
                                sample_request_values, scode_repeat_check, injection_names, errmsg = process_sample_request_form(nrange, em, ecode, key1, etype)

                                if not injection_names or not sample_request_values or not scode_repeat_check:
                                        msg = 'There is a problem in the form. Go back to the previous page and check for missing values, repeated sample codes or samples code > 4 characters.'
                                        return render_template('add_experiment_2', nameset=get_row_names(nrows), msg=msg, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)  
                                
                                if 'Database' not in etype:
                                        ind = [key1, 'needs method1', 0, 'No', None, None, None, None, None, None, None, None, None, None, None, None, None, time_requested]
                                        ind1 = InstrumentDetails(ind[0], ind[1], ind[2], ind[3], ind[4], ind[5], ind[6], ind[7], ind[8], ind[9], ind[10], ind[11], ind[12], ind[13], ind[14], ind[15], ind[16], ind[17])
           
                                if sample_request_values and injection_names and scode_repeat_check:

                                        if not benchwork: #if benchwork, then injection queue written after benchwork completed and injections updated if neccessary
                                                PIinitials, Rinitials, queue = write_no_benchwork_injection_queue(gid, ecode, scode_repeat_check, injection_names, fn, ln)             
                                                with open(f'/{local_path_start_facility}/injection_lists/{PIinitials}_{Rinitials}_{ecode}.txt', 'w') as fw: 
                                                        for injection in queue:
                                                                fw.write(f'{injection}\n')         

                                        db.session.add(er)
                                        db.session.commit()
                                        db.session.add(es)
                                        db.session.commit()
                                                                        
                                        for sr in sample_request_values:
                                                exptkey = sr[2]
                                                smplkey = sr[4]
                                                timereq = sr[18]
                                                sr = SampleRequest(sr[0], sr[1], sr[2], sr[3], smplkey, sr[5], sr[6], sr[7], sr[8], sr[9], sr[10], sr[11], sr[12], sr[13], sr[14], sr[15], sr[16], sr[17], timereq)
                                                sd = SampleDetails(exptkey, smplkey, 'needs method(s)', 'not injected', 'sparecol1', 'sparecol2', timereq)
                                                db.session.add(sr)
                                                db.session.add(sd)
                                                db.session.commit()

                                        if benchwork:      
                                                bench_hours = [key1, 0, '', '', time_requested]
                                                bh = bench_hours
                                                bh = BenchHours(bh[0], bh[1], bh[2], bh[3], bh[4])
                                                db.session.add(bh)
                                                db.session.commit()

                                        db.session.add(ind1)
                                        db.session.commit()
                                        return redirect(f'/request_confirmed/{key1}')


                #below code is executed when user changes row numbers in templates	
                if request.method == 'POST' and "addrow" in request.form:
                        nrows += 1
                        render_template('add_experiment_2.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)

                if request.method == 'POST' and "tenrows" in request.form:
                        nrows += 10
                        nameset = get_row_names(nrows)
                        render_template('add_experiment_2.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)

                if request.method == 'POST' and "deleterow" in request.form:
                        nrows -= 1
                        nameset = get_row_names(nrows)
                        render_template('add_experiment_2.html', nameset=nameset, fn=fn, ln=ln, em=em, gid=gid, ecode=ecode, exptypes=expt_types,
                                        expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)
                        
        return render_template('add_experiment_2.html', nameset=get_row_names(nrows), fn=fn, ln=ln, em=em, gid=gid, used_codes=used_codes, ecode=ecode, exptypes=expt_types,
                               expcats=expt_categories, dbcats=DB_categories, ecat=ecat, etype=etype, dbcat=dbcat, grants=grant_or_type, gcode=gcode, enotes=enotes)

  


@app.route('/delete_experiment', methods = ['GET', 'POST'])
@login_required
@admin_required
def delete_experiment():

        userdict = make_userdict_for_javascript() #funcs section
        exptdict = make_exptdict_for_javascript() 
        em = ''

        if request.method == 'POST':
                em = request.form['uemail']
                ec = request.form['expt_code']
                exptkey = '*'.join((em,ec))

                delExpReq = db.session.query(ExperimentRequest).filter_by(key1=exptkey).first()
                db.session.delete(delExpReq)
                db.session.commit()

                msg = f'All instances of experiment { ec } for user { em } have been deleted from the database and website'
                return render_template('delete_experiment.html', userdict=userdict, emex_dict=exptdict, msg=msg)
        
        return render_template('delete_experiment.html', userdict=userdict, emex_dict=exptdict)



@app.route('/modify_experiment_1', methods = ['GET', 'POST'])
@login_required
@admin_required
def modify_experiment_1():

        #again, page split as don't know good way of doing this otherwise

        userdict = make_userdict_for_javascript() #funcs section
        exptdict = make_exptdict_for_javascript()
        smpldict = make_smpldict_for_javascript()

        if request.method == 'POST':
                
                em = request.form['uemail']
                ec = request.form['expt_code']
                exptkey = '*'.join((em,ec))
                
                return redirect(f'modify_experiment_2/{exptkey}')

        return render_template('modify_experiment_1.html', userdict=userdict, exptdict=exptdict)



@app.route('/modify_experiment_2', methods = ['GET', 'POST'])
@app.route('/modify_experiment_2/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_required
def modify_experiment_2(exptkey=None):

        #modify is misleading. this is a delete-sample-but-not-whole-experiment function. tbh it's usually easier to delete and re-add the experiment.
        
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
        
        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'
                        return render_template('request_view.html', msg=msg)

                fn, ln, gid, itype, email = get_user_details(exptkey)
                ecode, etype, ecat, dbcat, gc, enotes, reqdt, db_yn = get_experiment_details(exptkey)
                instit_type, instit_price, verb = instit_type_price_discount(institute_price_dict, exptkey)

                #must check how fare each sample progressed - if any methods assigned (i.e. work done) then can't delete, as already incurred charges. 
                def get_undeleted_samples():
                        
                        q1 = db.session.query(SampleRequest).filter_by(key1=exptkey).all()
                        sample_keys = []
                        table_rows = []
                        
                        for res in q1:
                                #can replace this with func in funcs section
                                sample_keys.append(res.key2)
                                table_row = [res.sample_code, res.protein_conc, res.est_injections]
                                methods = [res.run_gel, res.ingel_digest, res.s_trap_digest, res.insol_digest, res.lysc_digest, res.po4_enrichment, res.label, res.fractionate, res.intact_protein]
                                method_strings = ['res.run_gel', 'res.ingel_digest', 'res.s_trap_digest', 'res.insol_digest', 'res.lysc_digest', 'res.po4_enrichment', 'res.label', 'res.fractionate', 'res.intact_protein']
                                methods_zip = list(zip(methods, method_strings))
                                methods_per_sample = []
                                
                                for i in methods_zip:
                                        if i[0] == '1':
                                                methods_per_sample.append(i[1][4:])
                                                
                                methods_str= ', '.join(methods_per_sample)        
                                table_row.append(methods_str)
                                subq1 = db.session.query(SampleDetails).with_entities(SampleDetails.bench_methods, SampleDetails.actual_injections).filter_by(key2=res.key2).first()
                                
                                if subq1.bench_methods == 'needs method(s)':
                                        table_row.append('OK to delete')
                                else:
                                        table_row.append('''method, injections assigned: can't delete''')
                                        table_row.append('N')
                                        
                                table_rows.append(table_row)
                                
                        return sample_keys, table_rows

                sample_keys, table_rows = get_undeleted_samples()


                if request.method == "POST":

                        request_table = []
                        
                        for i, sublist in enumerate(table_rows):
                                scode = sublist[0]
                                delete = request.form[f'delete_{sublist[0]}']
                                status = request.form[f'status_{sublist[0]}']
                                request_row = [sample_keys[i], delete]
                                request_table.append(request_row)

                                if 'OK' not in status: #table row will say OK to delete for that sample
                                        msg = 'these samples have been processed within the facility and so cannot be deleted'
                                        return render_template('modify_experiment_2.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, bench_methods=bench_methods, table_rows=table_rows)

                        if len(request_table) == 1:
                                msg = 'This is a single-sample experiment. Please delete using the Delete Expt function.'
                                return render_template('modify_experiment_2.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, bench_methods=bench_methods, table_rows=table_rows, msg=msg)
                                
                        msg = ''
                        
                        for row in request_table:
                                
                                if row[1] == 'Y':
                                        #delete from database
                                        del_smpl_SR= db.session.query(SampleRequest).filter_by(key2=row[0]).first()
                                        del_smpl_SD= db.session.query(SampleDetails).filter_by(key2=row[0]).first()
                                        db.session.delete(del_smpl_SR)
                                        db.session.delete(del_smpl_SD)
                                        db.session.commit()
                                        msg = f'samples with identifiers {[i for i in sample_keys]} have been deleted from the database. They will not contribute to future expenses calculated for this experiment'

                                if row[1] == 'N':
                                        msg = 'selected sample(s) deleted. check you have deleted all the samples you wanted to.'
                                        
                        sample_keys, table_rows = get_undeleted_samples() #must run again as will be different now
                        
                        return render_template('modify_experiment_2.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, bench_methods=bench_methods, table_rows=table_rows, msg=msg)

                                      
                return render_template('modify_experiment_2.html', fn=fn, ln=ln, gid=gid, ecode=ecode, etype=etype, bench_methods=bench_methods, table_rows=table_rows)
        
        return render_template('modify_experiment_2.html', bench_methods=bench_methods)



@app.route('/add_modify_users', methods = ['GET', 'POST'])
@login_required
@admin_required
def add_modify_users():

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
        
        newest_id = get_newest_id() #funcs section
        template_page = 'add_modify_users.html' #not sure why I use this variable sometimes and not others. 
        
        fnames = []
        lnames = []
        emails = []
        
        q1 = db.session.query(Users).with_entities(Users.first_name, Users.last_name, Users.email).all()
        
        for q in q1:
                fnames.append(q[0])
                lnames.append(q[1])
                emails.append(q[2])


        if request.method == 'POST'  and 'adduser' in request.form:
                #funcs section
                pass_list, errs, msg, fn1, ln1, email1, access, position, gid, iname1, itype, grant_codes, grant_years, time_registered, authenticated, legit_gid = get_registree_info('_1')

                if pass_list and access == 'FINAN': #this way finan poeple at Cam Uni don't need a grant code
                        pass_list = None
                        
                if not pass_list:
                        #nothing added to pass list when errors encountered in aboce func
                        newuser = Users(newest_id, fn1, ln1, email1, access, position, gid, iname1, itype, grant_codes, grant_years, time_registered, authenticated)
                        db.session.add(newuser)	
                        db.session.commit()
                        msg = 'This user has been successfully added to the database.'
                        return render_template(template_page, msg0=msg, ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails)
                else:
                        #something got added to the pass list
                        msg = 'Something was not right. Remember that CU users need grant numbers and researchers need a PI in the database. User emails cannot be added more than once.'
                        return render_template(template_page, msg=msg, ps=positions, als=access_levels, itypes=institute_types, fn1=fn1, ln1=ln1, em1=email1, iname1=iname1, itype=itype)
                
                
        if request.method == 'POST'  and 'modifyuser' in request.form:
                
                #nb that the '_2' arg gets pass to func if modifiying existing user, rather than adding new one
                pass_list, errs, msg2, fn2, ln2, email2, access, position, gid, iname2, itype, grant_codes, grant_years, time_registered, authenticated, legit_gid = get_registree_info('_2')

                for i in [pass_list, errs, msg2, fn2, ln2, email2, access, position, gid, iname2, itype, grant_codes, grant_years, time_registered, authenticated, legit_gid]:
                        #breakdown pass list contents to generate meaningful messages
                        if 'g' in pass_list:
                                msg = 'please only add grants for Cambridge University users'
                                return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg2=msg)

                        if 'd' in pass_list:
                                msg = 'PI or Project Leads must already have an email registered in the database'
                                return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg2=msg)


                        if 'f' in pass_list: #if itype is marked to CU and a grant not supplied, checks whether user has a grant (i.e. was previously a CU user or if this is a change)
                                if db.session.query(Users).with_entities(Users.grant_codes).filter(Users.email==email2).first()[0]:
                                        
                                        db.session.query(Users).where(Users.email==email2).update({'first_name':fn2, 'last_name':ln2, 'access_level':access, 'position':position, 'group_id':gid, 'institute_name':iname2})
                                        db.session.commit()
                                        
                                        msg = 'user details successfully modified.'
                                        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg02=msg)
                                else:
                                        
                                        msg = 'You cannot change an institute to Cambridge University without supplying a grant code and award year.'
                                        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg2=msg)

                for letter in ['a', 'c', 'd', 'e']:
                        if letter in pass_list:
                                msg = 'There is a problem with this form. Check for typos, incorrect group leader emails etc.'
                                return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg2=msg)


                #this is a CU user wanting to extend their grant list. normally I'd tell them to DIT at User Home but it might be thay can't 
                if itype=='Cambridge University' and grant_codes and grant_years:
                        
                        grantresults, yearresults, previousgrants = add_to_existing_grant_list(email2)
                        updated_grants = None
                        updated_years = None
                        
                        if len(grantresults[0]) > 0:
                                updated_grants = grantresults[0] + ',' + grant_codes
                                updated_years = yearresults[0] + ',' + grant_years
                        else:
                                updated_grants = grant_codes
                                updated_years = grant_years
                                
                        db.session.query(Users).where(Users.email==email2).update({'first_name':fn2, 'last_name':ln2, 'access_level':access, 'position':position, 'group_id':gid,
                                                                                   'institute_name':iname2, 'grant_codes':updated_grants, 'grant_years':updated_years, 'institute_type':itype})
                        db.session.commit()
                        
                        msg = 'The details for this user have been successully updated.'
                        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg02=msg)

                #grants are supposed to be missing in not CU user                        
                if pass_list == ['b'] and itype!='Cambridge University':
                        
                        db.session.query(Users).where(Users.email==email2).update({'first_name':fn2, 'last_name':ln2, 'access_level':access, 'position':position, 'group_id':gid, 'institute_name':iname2,
                                                                                   'institute_type':itype, 'grant_codes':'', 'grant_years':''})
                        db.session.commit()
                        msg = 'The details for this user have been successully updated.'
                        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg02=msg)

                else:
                        #if I've missed something, it must be a pretty niche error...
                        msg = 'There was some other sort of a problem which Harriet has not thought of'
                        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails, msg2=msg)
        
        return render_template('add_modify_users.html', ps=positions, als=access_levels, itypes=institute_types, fnames=fnames, lnames=lnames, emails=emails)



@app.route('/methods', methods = ['GET', 'POST'])
@login_required
@admin_required
def methods():

        #where you add bench and instrument methods, and add species to database categories (if you're admin)
        
        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        def make_table_rows():
                idmrows = []
                datavallist = list(datamins_dict.values())       
                for i, key in enumerate(list(instrmins_dict.keys())):
                        instrdata_row = [key, instrmins_dict[key],  datavallist[i]]
                        idmrows.append(instrdata_row)

                bmrows = []        
                for k, v in benchmins_dict.items():
                        row = [k,v]
                        bmrows.append(row)
                        
                dbcrows = [[dbc] for dbc in DB_categories]
                
                return bmrows, idmrows, dbcrows

        #fill in html tables with existing methods and dbcategories       
        bmrows, idmrows, dbcrows = make_table_rows()

        
        def test_repeats(table_rows, form_row):
                #make sure not adding a name that's already in use
                problem = False
                if form_row[0] in [i[0] for i in table_rows]:
                        problem = True
                return problem


        msg0 = ''
        msg1 = ''
                
        if request.method == 'POST':
                #straightforward retrieval of form info and db updates - but see javascript functions in script section at top of template page
                
                if 'add_bench_method' in request.form:
                        new_bm_vals = [request.form['new_bmeth_name'], request.form['new_bmeth_mins']]
                        problem = test_repeats(bmrows, new_bm_vals)
                
                        if problem:
                                msg0 = 'repeated method name detected - submission not possible'
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)
                        
                        if not problem:
                                msg1 = 'success! '
                                
                                newbm = BenchMethods(new_bm_vals[0], new_bm_vals[1])
                                db.session.add(newbm)	
                                db.session.commit()

                                benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
                                bmrows, idmrows, dbcrows = make_table_rows()
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)


                if 'add_instr_data_method' in request.form:
                        new_idm_vals = [request.form['new_idmeth_name'], request.form['new_imeth_mins'], request.form['new_dmeth_mins']]
                        problem = test_repeats(idmrows, new_idm_vals)
                
                        if problem:
                                msg0 = 'repeated method name detected - submission not possible'
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)
                        
                        if not problem:
                                msg1 = 'success! '
                                
                                newidm = InstrumentDataMethods(new_idm_vals[0], new_idm_vals[1], new_idm_vals[2])
                                db.session.add(newidm)	
                                db.session.commit()

                                benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
                                bmrows, idmrows, dbcrows = make_table_rows()
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)
                                
                        
                if 'add_dbcategory' in request.form:
                        new_dbc_vals = [request.form['new_dbc']]
                        problem = test_repeats(dbcrows, new_dbc_vals)
                
                        if problem:
                                msg0 = 'repeated method name detected - submission not possible'
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)
                        
                        if not problem:
                                msg1 = f'Success! You have added {new_dbc_vals[0]} to the database'
                                
                                newdbc = Species(new_dbc_vals[0])
                                db.session.add(newdbc)	
                                db.session.commit()

                                benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
                                bmrows, idmrows, dbcrows = make_table_rows()
                                return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)

                                                     
        return render_template('methods.html', bmrows=bmrows, idmrows=idmrows, dbcrows=dbcrows, msg0=msg0, msg1=msg1)


#the next section of routes is just for viewing db tables in html pages
#nb sometimes have difference access wrappers
@app.route('/table_pwds', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_pwds():
        cols, rows = table_contents_getter(Pwds)
        return render_template('table_pwds.html', cols=cols, rows=rows)


@app.route('/table_users', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_users():
        cols, rows = table_contents_getter(Users)
        return render_template('table_users.html', cols=cols, rows=rows)

           
@app.route('/table_ereqs', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_ereqs():
        cols, rows = table_contents_getter(ExperimentRequest)
        return render_template('table_ereqs.html', cols=cols, rows=rows)


@app.route('/table_sreqs', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_sreqs():
        cols, rows = table_contents_getter(SampleRequest)
        return render_template('table_sreqs.html', cols=cols, rows=rows)


@app.route('/table_sdets', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_sdets():
        cols, rows = table_contents_getter(SampleDetails)
        return render_template('table_sdets.html', cols=cols, rows=rows)


@app.route('/table_idets', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_idets():
        cols, rows = table_contents_getter(InstrumentDetails)
        return render_template('table_idets.html', cols=cols, rows=rows)


@app.route('/table_bhrs', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_bhrs():
        cols, rows = table_contents_getter(BenchHours)
        return render_template('table_bhrs.html', cols=cols, rows=rows)


@app.route('/table_dreqs', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_dreqs():
        cols, rows = table_contents_getter(DataRequest)
        return render_template('table_dreqs.html', cols=cols, rows=rows)


@app.route('/table_esum', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_esum():
        cols, rows = table_contents_getter(ExpensesSummary)
        return render_template('table_esum.html', cols=cols, rows=rows)


@app.route('/table_bmeths', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_bmeths():
        cols, rows = table_contents_getter(BenchMethods)
        return render_template('table_bmeths.html', cols=cols, rows=rows)

           
@app.route('/table_idmeths', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_idmeths():
        cols, rows = table_contents_getter(InstrumentDataMethods)
        return render_template('table_idmeths.html', cols=cols, rows=rows)


@app.route('/table_intypes', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_intypes():
        cols, rows = table_contents_getter(InstituteType)
        return render_template('table_intypes.html', cols=cols, rows=rows)


@app.route('/table_dbcats', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_dbcats():
        cols, rows = table_contents_getter(Species)
        return render_template('table_sdets.html', cols=cols, rows=rows)


@app.route('/table_ppm', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_ppm():
        cols, rows = table_contents_getter(PricePerMin)
        return render_template('table_ppm.html', cols=cols, rows=rows)


@app.route('/table_instrmnts', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_instrmnts():
        cols, rows = table_contents_getter(Instruments)
        return render_template('table_instrmnts.html', cols=cols, rows=rows)


@app.route('/table_acqn', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def table_acqn():
        cols, rows = table_contents_getter(Acquisition)
        return render_template('table_acqn.html', cols=cols, rows=rows)




@app.route('/queryDB_1', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def queryDB_1():
        #this route applied to above section of routes

        #makes dicts-as-js-objects for cascading dropdowns on template page
        userdict = make_userdict_for_javascript()
        userdict2 = userdict
        exptdict = make_exptdict_for_javascript()

        #email query var
        em = '' 

        users  = db.session.query(Users).with_entities(Users.user_id, Users.first_name, Users.last_name, Users.email).all()

        if request.method == 'POST':
                
                #pass email on to next page for usr specific lookup (queryDB2)
                if 'this_user' in request.form:
                        em = request.form['unames1']
                        return redirect(f'queryDB_2/{em}') 

                #pass ecode on to next page for expt specific lookup (queryDB3)
                if 'this_expt' in request.form:
                        em = request.form['unames2']
                        ec = request.form['expt_code']
                        exptkey = '*'.join((em,ec))
                        return redirect(f'queryDB_3/{exptkey}')

                #for whole-table lookups
                if 'get_pwds' in request.form:
                        return redirect(url_for('table_pwds'))

                if 'get_users' in request.form:
                        return redirect(url_for('table_users'))

                if 'get_ereqs' in request.form:
                        return redirect(url_for('table_ereqs'))

                if 'get_sreqs' in request.form:
                        return redirect(url_for('table_sreqs'))

                if 'get_sdets' in request.form:
                        return redirect(url_for('table_sdets'))

                if 'get_dreqs' in request.form:
                        return redirect(url_for('table_dreqs'))

                if 'get_bhrs' in request.form:
                        return redirect(url_for('table_bhrs'))

                if 'get_idets' in request.form:
                        return redirect(url_for('table_idets'))

                if 'get_esum' in request.form:
                        return redirect(url_for('table_esum'))

                if 'get_bmeths' in request.form:
                        return redirect(url_for('table_bmeths'))

                if 'get_idmeths' in request.form:
                        return redirect(url_for('table_idmeths'))

                if 'get_intypes' in request.form:
                        return redirect(url_for('table_intypes'))

                if 'get_species' in request.form:
                        return redirect(url_for('table_dbcats'))

                if 'get_ppm' in request.form:
                        return redirect(url_for('table_ppm'))

                if 'get_instrmnts' in request.form:
                        return redirect(url_for('table_instrmnts'))

                if 'get_acqn' in request.form:
                        return redirect(url_for('table_acqn'))
        
        return render_template('queryDB_1.html', userdict=userdict, userdict2=userdict2, emex_dict=exptdict, unms=users, unms2=users)




@app.route('/queryDB_2', methods = ['GET', 'POST'])
@app.route('/queryDB_2/<em>', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def queryDB_2(em=None):
        
        if em is not None:
                em, err = sanitize_batons(em)
                if err:
                        msg = 'there was a problem with this request, please try again'

                #all poss lookups with an email

                db_tables_list = [Users, ExperimentRequest,SampleRequest, SampleDetails,
                                  InstrumentDetails, BenchHours,DataRequest, ExpensesSummary]

                exptkey = None
                results = []
                for table in db_tables_list:
                        tbl_head, tbl_rows = user_contents_getter(table, em, exptkey)
                        tbl_results = [tbl_head, tbl_rows]
                        results.append(tbl_results)

                usrs, ereqs, sreqs, sdets, idets, bhrs, dreqs, esum = results
                
                return render_template('queryDB_2.html', usrs=usrs, ereqs=ereqs, sreqs=sreqs, sdets=sdets, idets=idets, bhrs=bhrs, dreqs=dreqs, esum=esum)

        return render_template('queryDB_2.html')



@app.route('/queryDB_3', methods = ['GET', 'POST'])
@app.route('/queryDB_3/<exptkey>', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def queryDB_3(exptkey=None):
        
        if exptkey is not None:
                exptkey, err = sanitize_batons(exptkey)
                if err:
                        msg = 'there was a problem with this request, please try again'

                em = exptkey.split('*')[0]

                db_tables_list = [Users, ExperimentRequest,SampleRequest, SampleDetails,
                                  InstrumentDetails, BenchHours,DataRequest, ExpensesSummary]

                #all poss lookups with an email

                results = []
                for table in db_tables_list:
                        tbl_head, tbl_rows = user_contents_getter(table, em, exptkey)
                        tbl_results = [tbl_head, tbl_rows]
                        results.append(tbl_results)

                usrs, ereqs, sreqs, sdets, idets, bhrs, dreqs, esum = results

                return render_template('queryDB_3.html', usrs=usrs, ereqs=ereqs, sreqs=sreqs, sdets=sdets, idets=idets, bhrs=bhrs, dreqs=dreqs, esum=esum)

        return render_template('queryDB_3.html')



@app.route('/finances_1', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def finances_1():

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        #could replace these queries with existing function in func section
        q1 = db.session.query(ExpensesSummary
                             ).with_entities(ExpensesSummary.key1
                                             ).where(ExpensesSummary.instrument_cost != None
                                                     ).where(ExpensesSummary.bench_instr_db_signoff == None).all()

        
        no_ms_signoff = ['all experiments with mass spec costs have been signed off'] #replaces list of expt codes that haven't been signed off, hence list format
        if q1:
                no_ms_signoff = [q[0].split('*')[1] for q in q1] #makes list of not-signed-offs. gets ecode by splitting exptkey (ecode*email)

        q2 = db.session.query(ExpensesSummary
                             ).with_entities(ExpensesSummary.key1
                                             ).where(ExpensesSummary.python_cost != None
                                                     ).where(ExpensesSummary.python_signoff == None).all()

        no_py_signoff = ['all experiments with bespoke data analysis costs have been signed off']
        if q2:
                no_py_signoff = [q[0].split('*')[1] for q in q2]     

        if request.method == 'POST':

                #get table
                if 'get_info' in request.form:

                        #on template page can select to get grouped (condensed) table
                        date = request.form['date']
                        if 'last' in date:
                                date = 'last'
                        if 'this' in date:
                                date = 'this'
                        group = request.form['group']
                        date = date + group
                        
                        return redirect(f'finances_2/{date}')

                #changes times and costs
                if 'update_prices' in request.form:

                        return redirect('update_prices')

                                       
        return render_template('finances_1.html', finan_dates=finan_dates, bdict=benchmins_dict,idict=instrmins_dict,
                               ddict=datamins_dict, ppdict=permin_price_dict, ipdict=institute_price_dict, no_ms_signoff=no_ms_signoff, no_py_signoff=no_py_signoff)



@app.route('/finances_2', methods = ['GET', 'POST'])
@app.route('/finances_2/<date>', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def finances_2(date=None):

        if date is not None:
                date, err = sanitize_batons(date)
                if err:
                        msg = 'there was a problem with this request, please try again'

                yr = thisyear
                if date[:-1] == 'last':
                        yr = lastyear

                groupYN = None
                if date[-1] == 'Y':
                        groupYN = 'Y'
        
                bigt_query = """SELECT
r.expt_code, r.grant_code, r.expt_type, r.expt_cat, r.db_cat, r.key1,
s.grant_or_type, s.CU_early_discount, s.bench_cost, s.instrument_cost, s.wash_cost, s.dbsearch_cost, s.extras_cost,  s.YrQ_instr_run, s.bench_instr_db_signoff, s.python_cost, s.YrQ_python_run, s.python_signoff,
u.group_id, u.institute_name, u.institute_type
FROM experiment_request AS r
INNER JOIN expenses_summary as s
ON r.key1=s.key1
INNER JOIN users as u
ON r.email=u.email;"""

                bigt = pd.read_sql_query(text(bigt_query), engine) #pd, pandas. pd can make dataframe directly from sql. bigt means bigtable
                
                bigt = bigt[(bigt['YrQ_instr_run'].str.contains(yr)) | (bigt['YrQ_python_run'].str.contains(yr))] #pandas dataframe filtering command
                
                cols_to_sum = ['bench_cost', 'instrument_cost', 'wash_cost', 'dbsearch_cost', 'extras_cost', 'python_cost']

                bigt['experiment cost'] = bigt[cols_to_sum].sum(axis=1) #pandas filter and sum
                
                bigt['YrQ MassSpec, YrQ CustomAnalysis'] = bigt['YrQ_instr_run'] + ', ' + bigt['YrQ_python_run'] #pandas new column
                
                cols_to_keep = ['YrQ MassSpec, YrQ CustomAnalysis', 'bench_instr_db_signoff', 'python_signoff', 'expt_code', 'group_id', 'grant_or_type', 'institute_name', 'institute_type', 'experiment cost', 'expt_type']

                bigt = bigt[cols_to_keep] #pandas dataframe subset

                #once got core info into suitable pd datafrme, start formatting for teplate page presentation
                for i, colname in enumerate(bigt.columns):
                        newcol = []
                        col = bigt[colname].to_list()
                        for i in col:
                                if i == None:
                                        newcol.append('None')
                                else:
                                        newcol.append(i)
                        bigt[colname] = newcol
                
                table = None
                theaders = []
                trows = []

                if not groupYN:
                        table = bigt
                        headers = table.columns.to_list()
                        theaders= headers[:-1]

                        for i, row in table.iterrows():
                                rowl = row.to_list()
                                trows.append(rowl[:-1])

                        #mark if experiment ongoing, not yet signed off
                        table['experiment cost'] = np.where((table['python_signoff']=='None') & (table['bench_instr_db_signoff']=='None'), 'experiment_ongoing', table['experiment cost'] )
                        table = table.drop(columns=['expt_type'])
               
                if groupYN:
                        #make smaller table is grouping selected
                        groupt = bigt[(bigt['python_signoff'] != 'None') | (bigt['bench_instr_db_signoff'] != 'None') ]
                        groupt = groupt.groupby(by = ['group_id', 'grant_or_type', 'institute_type', 'institute_name']).sum() #pd.grpoupby
                        table = groupt.reset_index() #pd.reset_index
                        table = table.drop(columns=['python_signoff', 'bench_instr_db_signoff', 'expt_code', 'expt_type', 'YrQ MassSpec, YrQ CustomAnalysis']) #pd.drop
                        theaders = table.columns.to_list()
                        for i, row in table.iterrows(): #pd.iterrows
                                rowl = row.to_list()
                                trows.append(rowl)

                msg = 'examine the table and press Download at the bottom of the page if you are satisifed this is correct'

                if download and request.method == 'POST':
                        
                        table.to_csv(f'/{local_path_start_facility}/proteomics_finance/finances_{yr}.csv', index=False) #should stick it in the finance folder
                        msg = 'Successfully downloaded to proteomics_finance folder. Experiments with costs not yet signed off are marked as "experiment ongoing" .'
                        
                        return render_template('finances_2.html', msg=msg)                                                 

                return render_template('finances_2.html', trows=trows, msg=msg, theaders=theaders)

        return render_template('finances_2.html', trows=trows, msg=msg, theaders=theaders)




@app.route('/update_prices', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def update_prices():

        #take a look at the javascript functions in the script section at the top of this html page

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)
        
        activity_dict_list = [benchmins_dict, instrmins_dict, datamins_dict] 
        activity_ppm_keys = list(permin_price_dict.keys())
        price_dict_list = [permin_price_dict, institute_price_dict]

        
        activity_min_rows = []
        for i, activity_min_dict in enumerate(activity_dict_list):
                rows = []
                for k, v in activity_min_dict.items():
                        row = [k,v, v*permin_price_dict[activity_ppm_keys[i]]]
                        rows.append(row)
                activity_min_rows.append(rows)
        bmrows, imrows, dmrows = activity_min_rows


        price_min_rows = []
        for i, price_min_dict in enumerate(price_dict_list):
                rows = []
                for k, v in price_min_dict.items():
                        row = [k,v]
                        rows.append(row)
                price_min_rows.append(rows)
        ppmrows, iprows = price_min_rows


        #function only used here, so not in funcs section
        def get_activity_outvals(actv_min_row_id):
                outvals = []
                actv_row_dict = {'bm':bmrows, 'im':imrows, 'dm':dmrows, 'ppm':ppmrows, 'ip':iprows}
                key = list(actv_row_dict.keys())[list(actv_row_dict .values()).index(actv_min_row_id)]

                #see outerloop and loopset jinja for loop in html template                
                for n in range(len(actv_min_row_id)):
                        outval = request.form[f'{key}_{n}'] 
                        if outval == '': #nothing filled in in table
                                outval = actv_min_row_id[n][1]
                        else:
                                outval = float(outval)
                        outvals.append(outval) #list of vals for each form on html page

                return outvals



        if request.method == 'POST':
                
                if 'update_bm_times' in request.form: #bench mins
                        new_bm_mins = get_activity_outvals(bmrows)

                        #have to use this method to update by column, rather than row in sqlalchemy
                        payload = dict(zip(list(benchmins_dict.keys()), new_bm_mins))

                        db.session.query(BenchMethods).filter(
                                BenchMethods.bench_method.in_(payload)).update(
                                        {BenchMethods.mins_per_method: case(
                                                payload, value=BenchMethods.bench_method
                                                )}, synchronize_session=False)

                        db.session.commit()
                        msg = 'you have successfully updated the time associated with one or more bench methods.'

                        return redirect('update_message_page')


                if 'update_im_times' in request.form: #instrument mins
                        new_im_mins = get_activity_outvals(imrows)

                        payload = dict(zip(list(instrmins_dict.keys()), new_im_mins))

                        db.session.query(InstrumentDataMethods).filter(
                                InstrumentDataMethods.instrument_method.in_(payload)).update(
                                        {InstrumentDataMethods.mins_per_method_instr: case(
                                                payload, value=InstrumentDataMethods.instrument_method
                                                )}, synchronize_session=False)

                        db.session.commit()
                        msg = 'you have successfully updated the time associated with one or more instrument methods.'

                        return redirect('update_message_page')


                if 'update_dm_times' in request.form: #data search mins
                        new_dm_mins = get_activity_outvals(dmrows)

                        payload = dict(zip(list(datamins_dict.keys()), new_dm_mins))

                        db.session.query(InstrumentDataMethods).filter(
                                InstrumentDataMethods.instrument_method.in_(payload)).update(
                                        {InstrumentDataMethods.mins_per_method_search: case(
                                                payload, value=InstrumentDataMethods.instrument_method
                                                )}, synchronize_session=False)

                        db.session.commit()
                        msg = 'you have successfully updated the time associated with one or more datasearch methods.'

                        return redirect('update_message_page')


                if 'ppm' in request.form: #pricepermin
                        new_ppm_mins = get_activity_outvals(ppmrows)

                        payload = dict(zip(list(permin_price_dict.keys()), new_ppm_mins))

                        db.session.query(PricePerMin).filter(
                                PricePerMin.activity.in_(payload)).update(
                                        {PricePerMin.price_per_min: case(
                                                payload, value=PricePerMin.activity
                                                )}, synchronize_session=False)

                        db.session.commit()
                        msg = 'you have successfully updated the prices per minute of facility activies.'

                        return redirect('update_message_page')

                if 'instpr' in request.form: #institute prices
                        new_instpr_mins = get_activity_outvals(iprows)
                        
                        payload = dict(zip(list(institute_price_dict.keys()), new_instpr_mins))

                        db.session.query(InstituteType).filter(
                                InstituteType.institute_type.in_(payload)).update(
                                        {InstituteType.price_per_type: case(
                                                payload, value=InstituteType.institute_type
                                                )}, synchronize_session=False)

                        db.session.commit()
                        msg = 'you have successfully updated the prices per minute of facility activies.'

                        return redirect('update_message_page')
                       
        return render_template('update_prices.html', bmrows=bmrows, imrows=imrows, dmrows=dmrows, ppmrows=ppmrows, iprows=iprows)


@app.route('/update_message_page', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def update_message_page():
        #because, again, page splits are my go to workaround for certain things
        return render_template('update_message_page.html')

        

@app.route('/facility_stats_1', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def facility_stats_1():

        msg = ''

        #see lists section at top of this file
        stack_iw = [stack_select[0], stack_select[1]]
        stack_bm = [stack_select[0], stack_select[-1]]

        #generates string to be pass to next page containing all the grouping options
        if request.method == 'POST':

                if 'ex_count_submit' in request.form:
                        opt1 = '0'
                        opt2 = request.form['expt_count']
                        
                        if opt1 and opt2:
                                plot_info = 'A'+opt1+str(opt2)+'Y'                
                                return redirect(f'facility_stats_2/{plot_info}')
                        else:
                                msg = 'please select from all the relevant dropdown menus'
                                return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)

                if 'ex_cost_submit' in request.form:
                        opt1 = request.form['expt_sum']
                        opt2 = request.form['stack_expt']
                        
                        if opt1 and opt2:
                                plot_info = 'A'+str(opt1)+str(opt2)+'Z'
                                return redirect(f'facility_stats_2/{plot_info}')
                        else:
                                msg = 'please select from the relevant dropdown menus'
                                return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)


                if 'iw_submit' in request.form:
                        opt1 = request.form['iw_sum']
                        opt2 = request.form['stack_iw']
                        
                        if opt1 and opt2:
                                plot_info = 'E'+str(opt1)+str(opt2)+'Z'
                                return redirect(f'facility_stats_2/{plot_info}')
                        else:
                                msg = 'please select from the relevant dropdown menus'
                                return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)


                if 'hrs_submit' in request.form:
                        opt1 = request.form['hrs_sum']
                        opt2 = request.form['stack_hrs']
                        
                        if opt1 and opt2:
                                if opt1 == '1':
                                        plot_info = 'C'+opt1+str(opt2)+'Z'
                                        return redirect(f'facility_stats_2/{plot_info}')
                                if opt1 != '1':
                                        plot_info = 'D'+opt1+str(opt2)+'Z'
                                        return redirect(f'facility_stats_2/{plot_info}')
                        else:
                                msg = 'please select from the relevant dropdown menus'
                                return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)

                                                
                if 'bm_submit' in request.form:
                        opt1 = '1' #always pulls out columns 'key2' to count on, or group by bench methods
                        opt2 = request.form['bm_count']
                        
                        if opt1 and opt2:
                                plot_info = 'B'+str(opt1)+str(opt2)+'Y'
                                return redirect(f'facility_stats_2/{plot_info}')
                        else:
                                msg = 'please select from the relevant dropdown menus'
                                return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)

                       
        return render_template('facility_stats_1.html', expt_cost=expt_cost_type, iw=injection_wash, hrs=bench_python, stack_many=stack_many, stack_iw=stack_iw, stack_bm=stack_bm, msg=msg)




@app.route('/facility_stats_2', methods = ['GET', 'POST'])
@app.route('/facility_stats_2/<plot_info>', methods = ['GET', 'POST'])
@login_required
@admin_finance_required
def facility_stats_2(plot_info=None):

        benchmins_dict, instrmins_dict, datamins_dict, permin_price_dict, institute_price_dict, instr_methods, bench_methods, institute_types, DB_categories = outer_dict_function(tablenames, col1s, col2s)

        #back in pandas land, converting raw sql query results directly to pd dataframe
        
        edf_query = """SELECT
r.grant_code, r.expt_type, r.expt_cat, r.db_cat, r.key1,
s.grant_or_type, s.CU_early_discount, s.bench_cost, s.instrument_cost, s.wash_cost, s.dbsearch_cost, s.extras_cost,  s.YrQ_instr_run, s.bench_instr_db_signoff, s.python_cost, s.python_signoff
FROM experiment_request AS r
INNER JOIN expenses_summary as s
ON r.key1=s.key1;"""
        edf = pd.read_sql_query(text(edf_query), engine) #expenses data frame, used for most of the plots

        bdf_query = """SELECT key1, key2, bench_methods, actual_injections FROM sample_details;""" #bench df
        bdf = pd.read_sql_query(text(bdf_query), engine)

        bhdf_query = """SELECT key1, bench_hrs from bench_hours;""" #bench hours df
        bhdf = pd.read_sql_query(text(bhdf_query), engine)

        phdf_query = """SELECT key1, python_hrs from data_request;""" #python hours df
        phdf = pd.read_sql_query(text(phdf_query), engine)

        idf_query = """SELECT * FROM instrument_details;""" #instrument df
        idf = pd.read_sql_query(text(idf_query), engine)

        subdfs_for_vstack = []

        nlist = [[0, 1, 2, 4], [0, 5, 6, 8], [0, 9, 10, 12], [0, 13, 14, 16]]
        for sublist in nlist:
                subdf = idf[[idf.columns[n] for n in sublist]]
                subdf.columns = ['key1', 'method', 'injections', 'washes'] #same col names or else vstack won't happen
                subdfs_for_vstack.append(subdf)

        stacked_idf = pd.concat(subdfs_for_vstack, ignore_index = True) #vertical stack and reset indexing
        stacked_idf = stacked_idf.groupby(by = ['key1', 'method']).sum() #group by first the 0th column, then the 1st column
        stacked_idf = stacked_idf.reset_index() #grouping column automatically become index cols, so must reset


        #give edf some extra columns for ease of plotting (requires grp_dct)        
        edf['grant_or_type'] = np.where(edf['grant_or_type'].isin(['Other Academia', 'Industry']), edf['grant_or_type'], 'Cambridge University',)
        edf['grant_or_type'] = np.where(edf['CU_early_discount'].str.contains('Y'), 'Cambridge University early', edf['grant_or_type'])
        cols_to_sum = [col for col in list(edf.columns) if '_cost' in col]
        edf['total_expt_revenue'] = edf[cols_to_sum].sum(axis=1)
        edf['res_email'] = edf['key1'].str.split('*').str[0]

        print('did it really get beyond this point?') #'cos this route is a pain in the arse
        
        grp_dct = grp_lead_grp_mbr_dct() #funcs section at top
        grp_leader_col = []        
        for researcher in edf['res_email']:
                for grp_lead, grp_members in grp_dct.items():
                        if researcher in grp_members:
                                grp_leader_col.append(grp_lead)
                
        edf['grp_leader'] = grp_leader_col #need to groupby group leaders


        #after pimping edf with some extra columns for ease-of-plotting, do this for the other dfs
        #makes dct where vals are columns to be added to dataframes in dfs list, whereever there's a key1 match
        keys, *vals_list = [edf['key1'].to_list(), edf['YrQ_instr_run'].to_list(), edf['grp_leader'].to_list(), edf['grant_or_type'].to_list(), edf['expt_type'].to_list(), edf['expt_cat'].to_list(), edf['db_cat'].to_list()]
        key1_dct = dict(zip(keys, zip(*vals_list)))
        
        dfs = [bdf, bhdf, phdf, stacked_idf]
        for df in dfs:
                df_key1 = df['key1'].to_list()
                df['YrQ_instr_run'] = [key1_dct[key1][0] for key1 in df_key1]
                df['grp_leader'] = [key1_dct[key1][1] for key1 in df_key1]
                df['grant_or_type'] = [key1_dct[key1][2] for key1 in df_key1]
                df['expt_type'] = [key1_dct[key1][3] for key1 in df_key1]
                df['expt_cat'] = [key1_dct[key1][4] for key1 in df_key1]
                df['db_cat'] = [key1_dct[key1][5] for key1 in df_key1]


        #modify a couple of the stack categories
        institute_types_modified = institute_types + ['Cambridge University early']        
        group_leaders = list(set(grp_leader_col))

        #lastly, make some x values
        xval_col = 'YrQ_instr_run'

        #The dataframes are all ready for plotting.
        #Now just need to receive and decoding the info about what plot is desired
        if plot_info is not None:
                
                date, err = sanitize_batons(plot_info)
                if err:
                        msg = 'there was a problem with this request, please try again'

                #write dictionaries manually to interpret codes from previous page options:
                #{number_code: [cols to plot]}
                plt_col_dctA = {'0': ['key1', 'number of experiments'], '1': ['total_expt_revenue', 'total revenue'], '2': ['bench_cost', 'cost of bench work'],
                                '3': ['instrument_cost', 'mass spectrometry costs'], '4': ['wash_cost', 'costs of washes'], '5': ['dbsearch_cost', 'cost of database searches'],
                                '6': ['python_cost', 'cost of bespoke analysis'],}
                plt_col_dctB = {'1': ['key2', 'number of samples'], '2': ['key2', 'number of samples']}
                plt_col_dctC = {'1': ['bench_hrs', 'hours of bench work']}
                plt_col_dctD = {'2': ['python_hrs', 'hours of bespoke analysis']}
                plt_col_dctE = { '0': ['method', 'instrument method'], '1': ['injections', 'injections on to instruments'], '2': ['washes', 'instrument washes']}

                #{letter_code: [dataframe, dict_from_those_just_above]
                plt_df_dct = {'A': [edf, plt_col_dctA], 'B':[bdf, plt_col_dctB], 'C':[bhdf, plt_col_dctC], 'D': [phdf, plt_col_dctD], 'E': [stacked_idf, plt_col_dctE]}

                #{number_code: ['group_type', legend list, last-bit-of-plot-title]
                plt_grp_stk_dct = {'1': ['no_grouping', []], '2':['expt_type', expt_types, 'type of request'], '3':['expt_cat', expt_categories, 'experiment category'], '4': ['grp_leader', group_leaders, 'research group'],
                                   '5': ['grant_or_type', institute_types_modified, 'type of client'], '6': ['db_cat', DB_categories, 'database species'], '7': ['method', instr_methods, 'mass spectrometry method'],
                                   '8': ['bench_methods', bench_methods, 'bench processing method']}

                #set pandas aggregation method
                plt_agg_dct = {'Y': 'count', 'Z': 'sum'}


                #use dictionaries to convert option codes into meaningfully-named arguments for below function
                dataframe = plt_df_dct[plot_info[0]][0] #plt_df_dct[B] --> bdf
                
                wanted_col_dct = plt_df_dct[plot_info[0]][1] #plt_df_dct[B] --> plt_col_dctB
                wanted_col = wanted_col_dct[plot_info[1]][0] #plt_col_dctB[1] --> 'key2' (always, become this option is fixed at 1)
                
                grouping_col = plt_grp_stk_dct[plot_info[2]][0] #plt_grp_stk_dct[1] --> no grouping (or 8 would get out grouping by bench methods)
                stacked_category = plt_grp_stk_dct[plot_info[2]][1] #plt_grp_stk_dct[1] --> empty list (or 8 would get out bench methods list)
                
                agg_method = plt_agg_dct[plot_info[3]]


                def fac_stats_plot(dataframe, wanted_col, grouping_col, stacked_category, agg_method):
                        #returns plot data as url, title as string and the figure structure

                        all_xvals = []
                        all_yvals = []
                        
                        stack_keys = None
                        pltdct = None
                        
                        #actual plotting
                        for idx, vals in enumerate(dataframe[xval_col].unique()):
                                
                                all_xvals.append(f'{vals}')
                                tempdf = dataframe.loc[dataframe[xval_col] == vals]
                                
                                if grouping_col != 'no_grouping':
                                        
                                        if agg_method == 'count':
                                                tempdf = tempdf.groupby([grouping_col]).count()
                                        if agg_method == 'sum':
                                                tempdf = tempdf.groupby([grouping_col]).sum()
                                                
                                        idx_wcol = list(zip(tempdf.index.to_list(), tempdf[wanted_col].to_list()))
                                        
                                        for stck in stacked_category:
                                                if stck not in tempdf.index.to_list():
                                                        idx_wcol.append((stck, 0))
                                                        
                                        idx_wcol = sorted(idx_wcol)
                                        idx_wcol = list(sum(idx_wcol, ())) #flattens
                                        vals_only = idx_wcol[1::2]
                                        keys_only = idx_wcol[0::2]
                                        all_yvals.append(vals_only)
                                        yarr = (np.array(all_yvals)).T
                                        if not stack_keys:
                                                stack_keys = keys_only
                                        pltdct = dict(zip(stack_keys, yarr))
                                        
                                elif grouping_col == 'no_grouping':

                                        if agg_method == 'count':
                                                all_yvals.append(tempdf[wanted_col].count())
                                        if agg_method == 'sum':
                                                all_yvals.append(tempdf[wanted_col].sum())
                                        
                                        yarr = (np.array(all_yvals)).T

                        #plot formatting
                        cmap = Colormap('seaborn:tab20')

                        clist = [n[1] for n in cmap.color_stops]
                        clist = clist + clist
  
                        fig = Figure()
                        FigureCanvas(fig)
                        ax = fig.add_subplot(111)
                        bottom = np.zeros(len(all_xvals))
                        width = 0.5
                        
                        
                        if grouping_col != 'no_grouping':
                                ckeys = pltdct.keys()
                                cvals = clist[:len(ckeys)]
                                cdct = dict(zip(ckeys, cvals))
                                
                                for grouping, ydata in pltdct.items():
                                        
                                        if np.sum(ydata) == 0.0:
                                                ax.bar(all_xvals[:], ydata, width, label='_nolegend_', bottom=bottom)
                                        if np.sum(ydata) > 0.0:
                                                ax.bar(all_xvals[:], ydata, width, label=grouping, bottom=bottom, color=cdct[grouping])
                        
                                        bottom += ydata

                                        labelz = None
                                        for c in ax.containers:
                                                labels = [round(v.get_height(), 2) if v.get_height() > 0 else '' for v in c]
                                                if not labelz:
                                                       labelz = labels
                                        ax.bar_label(c, labels=labels, label_type='center', fontsize=7)
                                ax.set_title(f'{wanted_col_dct[plot_info[1]][1]} by {plt_grp_stk_dct[plot_info[2]][2]}')
                        else:
                                ax.bar(all_xvals[:], yarr, width, label='total')
                                ax.set_title(f'{wanted_col_dct[plot_info[1]][1]} ')

                   
                        ax.set_xlabel('Year-Quarter')
                        ax.set_ylabel('count (n) or sum (GBP)')
                        ax.legend(loc='upper right', fontsize=7)

                        title = ax.get_title()

                        buf = BytesIO()
                        fig.savefig(buf, format="png")
                        buf.seek(0)

                        data = urllib.parse.quote(base64.b64encode(buf.read()).decode())
                        
                        return data, title, fig


                data, title, fig = fac_stats_plot(dataframe, wanted_col, grouping_col, stacked_category, agg_method)


                if request.method == 'POST':
                        fig.savefig(f'/{local_path_start_facility}/proteomics_stats/{title}.png')
                        msg = '''This plot has been downloaded to the proteomics finance folder. The file name should be the same as the plot title.
                                        Files are accessed using Filezilla. All users with ADMIN or FINANCE access are assumed to have configured Filezilla appropriately. 
                                        Please contact CIMR IT if you need Filezilla to be configured for you.'''
                        return render_template('facility_stats_2.html', plot_url=data, msg=msg)                             

                return render_template('facility_stats_2.html', plot_url=data)

        return render_template('facility_stats_2.html')
        

  
 
@app.route('/test_page', methods=['GET', 'POST']) 
def test_page():                
        return render_template('test_page.html')





if __name__ == '__main__':
	app.run(debug=True)


