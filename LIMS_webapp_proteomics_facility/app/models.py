from app import app, db, bcrypt, login
from flask import render_template, redirect, url_for, flash
from sqlalchemy import event
from datetime import datetime
from time import time
import jwt
 
@login.user_loader
def load_user(useremail):
     if useremail is not None:
         return Users.query.get(useremail)
     return None
    
@login.unauthorized_handler
def unauthorized():
     return redirect(url_for('index'))



class Pwds(db.Model):
     __tablename__ = 'pwds'
     id = db.Column(db.Integer, primary_key=True)
     email = db.Column(db.String(50))
     password = db.Column(db.String(100))
     authenticated = db.Column(db.Boolean, default=False)
     def __init__(self, id, email, password, authenticated):
          self.email = email
          self.password = bcrypt.generate_password_hash(password).decode('UTF-8')
     def verify_password(self, pwd):
          return bcrypt.check_password_hash(self.password, pwd)
     def is_active(self):
          return True
     def get_id(self):
          return self.email
     def is_authenticated(self):
          return self.authenticated
     def is_anonymous(self):
          return False
     def get_reset_token(self, expires_in=1800):
          return jwt.encode({'reset_password': self.id, 'exp': time() + expires_in}, app.config['SECRET_KEY'], algorithm='HS256')
     @staticmethod
     def verify_reset_token(token):
          try:
               id = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
          except:
               return
          return Pwds.query.get(id)





class Users(db.Model):
     __tablename__ = 'users'
     user_id = db.Column(db.Integer, nullable=False)
     first_name = db.Column(db.String(50), nullable=False)
     last_name = db.Column(db.String(50), nullable=False)
     email = db.Column(db.String(50), primary_key=True)	
     access_level = db.Column(db.String(50), nullable=False)
     position = db.Column(db.String(50), nullable=False)
     group_id = db.Column(db.String(50), nullable=False)
     institute_name = db.Column(db.String(50), nullable=False)
     institute_type = db.Column(db.String(50), nullable=False)
     grant_codes = db.Column(db.String(200), nullable=True)
     grant_years = db.Column(db.String(200), nullable=True)
     time_registered = db.Column(db.String(50), nullable=False)
     authenticated = db.Column(db.Boolean, default=False)   
     def __init__(self, user_id, first_name, last_name, email, access_level, position, group_id, institute_name, institute_type, grant_codes, grant_years, time_registered, authenticated):
          self.user_id = user_id
          self.first_name = first_name
          self.last_name = last_name
          self.email = email
          self.access_level = access_level
          self.position = position
          self.group_id = group_id
          self.institute_name= institute_name
          self.institute_type = institute_type
          self.grant_codes = grant_codes
          self.grant_years = grant_years
          self.time_registered = time_registered  
     def is_authenticated(self):
          return self.authenticated

@event.listens_for(Users.__table__, 'after_create')
def create_admin(tbl, conn, **kw):
     conn.execute(tbl.insert().values(user_id=[1], first_name='Harriet', last_name='Parsons', email='tempeparsons@gmail.com',  access_level='ADMIN',
                                      position='PI/Project_Lead', group_id='tempeparsons@gmail.com', institute_name='Lawrence Berkeley National Laboratory',
                                      institute_type='Other Academia', grant_codes=['LBNL/00'], grant_years=['2020'], time_registered=datetime.now(), authenticated=0))
	




class ExperimentRequest(db.Model):
     __tablename__ = 'experiment_request'
     email = db.Column(db.String(50), db.ForeignKey('users.email',  ondelete='CASCADE'))
     expt_code = db.Column(db.String(50), nullable=False)
     key1 = db.Column(db.String(50), primary_key=True)
     grant_code = db.Column(db.String(50), nullable=False)
     expt_type = db.Column(db.String(50), nullable=False)
     expt_cat = db.Column(db.String(50), nullable=False)
     db_cat = db.Column(db.String(50), nullable=False)
     extra_notes = db.Column(db.Text(1000), nullable=True)
     time_requested = db.Column(db.String(50))
     arrived = db.Column(db.String(50), nullable=True)
     def __init__(self, email, expt_code, key1, grant_code, expt_type, expt_cat, db_cat, extra_notes, time_requested, arrived):
             self.email=email
             self.expt_code=expt_code
             self.key1=key1
             self.grant_code=grant_code
             self.expt_type=expt_type
             self.expt_cat=expt_cat
             self.db_cat=db_cat
             self.extra_notes=extra_notes
             self.time_requested=time_requested
             self.arrived=arrived





class SampleRequest(db.Model):
     __tablename__ = 'sample_request'
     email = db.Column(db.String(50))
     expt_code = db.Column(db.String(50), nullable=False)
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'))
     sample_code = db.Column(db.String(50), nullable=False)
     key2 =  db.Column(db.String(50), primary_key=True)
     protein_conc = db.Column(db.Float, nullable=False)
     est_injections = db.Column(db.Integer, nullable=False)
     ms_type = db.Column(db.String(50), nullable=False)
     instr_name = db.Column(db.String(50), nullable=False)
     run_gel = db.Column(db.String(50), nullable=True)
     ingel_digest = db.Column(db.String(50), nullable=True)
     s_trap_digest = db.Column(db.String(50), nullable=True)
     insol_digest = db.Column(db.String(50), nullable=True)
     lysc_digest = db.Column(db.String(50), nullable=True)
     po4_enrichment = db.Column(db.String(50), nullable=True)
     label = db.Column(db.String(50), nullable=True)
     fractionate = db.Column(db.String(50), nullable=True)
     intact_protein = db.Column(db.String(50), nullable=True)
     time_requested= db.Column(db.String(50), nullable=True)
     def __init__(self, email, expt_code, key1, sample_code, key2, protein_conc, est_injections, ms_type, instr_name, run_gel, ingel_digest, s_trap_digest, insol_digest, lysc_digest, po4_enrichment, label, fractionate, intact_protein, time_requested):
          self.email=email
          self.expt_code=expt_code
          self.key1=key1
          self.sample_code=sample_code
          self.key2=key2
          self.protein_conc=protein_conc
          self.est_injections=est_injections
          self.ms_type=ms_type
          self.instr_name=instr_name
          self.run_gel=run_gel
          self.ingel_digest=ingel_digest
          self.s_trap_digest=s_trap_digest
          self.insol_digest=insol_digest
          self.lysc_digest=lysc_digest
          self.po4_enrichment=po4_enrichment
          self.label=label
          self.fractionate=fractionate
          self.intact_protein=intact_protein
          self.time_requested=time_requested





class SampleDetails(db.Model):
     __tablename__ = 'sample_details'
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'), nullable=True)
     key2 =  db.Column(db.String(50), primary_key=True)
     bench_methods = db.Column(db.String(50), nullable=True)
     actual_injections = db.Column(db.String(50), nullable=True)
     sparecol1 = db.Column(db.String(50), nullable=True)
     sparecol2 = db.Column(db.String(50), nullable=True)
     time_updated = db.Column(db.String(50), nullable=True)
     def __init__(self, key1, key2, bench_methods, actual_injections, sparecol1, sparecol2, time_updated):
          self.key1=key1
          self.key2=key2
          self.bench_methods=bench_methods
          self.actual_injections=actual_injections
          self.sparecol1=sparecol1
          self.sparecol2=sparecol2
          self.time_updated=time_updated
      



     
class DataRequest(db.Model):
     __tablename__ = 'data_request'
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'), primary_key=True)
     python_hrs = db.Column(db.Float, nullable=True)
     sparecol1 = db.Column(db.String(50), nullable=True)
     sparecol2 = db.Column(db.String(50), nullable=True)
     time_updated = db.Column(db.String(50), nullable=True)
     def __init__(self, key1, python_hrs, sparecol1, sparecol2,  time_updated):
          self.key1=key1
          self.python_hrs=python_hrs
          self.sparecol1=sparecol1
          self.sparecol2=sparecol2
          self.time_upated=time_updated





class BenchHours(db.Model):
     __tablename__ = 'bench_hours'
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'), primary_key=True)
     bench_hrs = db.Column(db.Float, nullable=True)
     sparecol1 = db.Column(db.String(50), nullable=True)
     sparecol2 = db.Column(db.String(50), nullable=True)
     time_updated = db.Column(db.String(50), nullable=True)
     def __init__(self, key1, bench_hrs, sparecol1, sparecol2, time_updated):
          self.key1=key1
          self.bench_hrs=bench_hrs
          self.sparecol1=sparecol1
          self.sparecol2=sparecol2
          self.time_updated=time_updated





class InstrumentDetails(db.Model):
     __tablename__ = 'instrument_details'
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'), primary_key=True)
     method1 = db.Column(db.String(50), nullable=False)
     injections1 = db.Column(db.Integer, nullable=True)
     search1 = db.Column(db.String(50), nullable=True)
     washes1 = db.Column(db.Integer, nullable=True)
     method2 = db.Column(db.String(50), nullable=True)
     injections2 = db.Column(db.Integer, nullable=True)
     search2 = db.Column(db.String(50), nullable=True)
     washes2 = db.Column(db.Integer, nullable=True)
     method3 = db.Column(db.String(50), nullable=True)
     injections3 = db.Column(db.Integer, nullable=True)
     search3 = db.Column(db.String(50), nullable=True)
     washes3 = db.Column(db.Integer, nullable=True)
     method4 = db.Column(db.String(50), nullable=True)
     injections4 = db.Column(db.Integer, nullable=True)
     search4 = db.Column(db.String(50), nullable=True)
     washes4 = db.Column(db.Integer, nullable=True)
     YrQ_updated = db.Column(db.String(50), nullable=True)
     def __init__(self, key1, method1, injections1, search1, washes1, method2, injections2, search2, washes2, method3, injections3, search3, washes3, method4, injections4, search4, washes4, YrQ_updated):
          self.key1=key1
          self.method1=method1
          self.injections1=injections1
          self.search1=search1
          self.washes1=washes1
          self.method2=method2
          self.injections2=injections2
          self.search2=search2
          self.washes2=washes2
          self.method3=method3
          self.injections3=injections3
          self.search3=search3
          self.washes3=washes3
          self.method4=method4
          self.injections4=injections4
          self.search4=search4
          self.washes4=washes4
          self.YrQ_upated=YrQ_updated



    

class ExpensesSummary(db.Model):
     __tablename__ = 'expenses_summary'
     key1 = db.Column(db.String(50), db.ForeignKey('experiment_request.key1',  ondelete='CASCADE'), primary_key=True)
     grant_or_type = db.Column(db.String(50), nullable=False)
     CU_early_discount = db.Column(db.String(50), nullable=True)
     bench_cost = db.Column(db.Float, nullable=True)
     instrument_cost = db.Column(db.Float, nullable=True)
     wash_cost = db.Column(db.Float, nullable=True)
     dbsearch_cost = db.Column(db.Float, nullable=True)
     extras_description = db.Column(db.String(100), nullable=True)
     extras_cost = db.Column(db.Float, nullable=True)
     Yr_instr_run = db.Column(db.Integer, nullable=True)
     YrQ_instr_run = db.Column(db.String(50), nullable=True)
     bench_instr_db_signoff = db.Column(db.String(50), nullable=True)
     python_cost = db.Column(db.Float, nullable=True)
     YrQ_python_run = db.Column(db.String(50), nullable=True)
     python_signoff = db.Column(db.String(50), nullable=True)
     def __init__(self, key1, grant_or_type, CU_early_discount, bench_cost, instrument_cost, wash_cost, dbsearch_cost, extras_description, extras_cost, Yr_instr_run, YrQ_instr_run, bench_instr_db_signoff, python_cost, YrQ_python_run, python_signoff):
          self.key1=key1
          self.grant_or_type=grant_or_type
          self.CU_early_discount=CU_early_discount
          self.bench_cost=bench_cost
          self.instrument_cost=instrument_cost
          self.wash_cost=wash_cost
          self.dbsearch_cost=dbsearch_cost
          self.extras_description=extras_description
          self.extras_cost=extras_cost
          self.Yr_instr_run=Yr_instr_run
          self.YrQ_instr_run=YrQ_instr_run
          self.bench_instr_db_signoff=bench_instr_db_signoff
          self.python_cost=python_cost
          self.YrQ_python_run=YrQ_python_run
          self.python_signoff=python_signoff



	

class Instruments(db.Model):
     __tablename__ = 'instruments'
     instrument_type = db.Column(db.String(100), primary_key=True)
     price_per_min = db.Column(db.Float, nullable=False)
     def __init__(self, instument_type, price_per_min):
          self.instrument_type=instrument_type
          self.price_per_min=price_per_min

@event.listens_for(Instruments.__table__, 'after_create')
def add_instruments(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'instrument_type':'FusionLumos', 'price_per_min':1.2}, {'instrument_type':'QExactive', 'price_per_min':1.2}])





class Acquisition(db.Model):
     __tablename__ = 'acquisition'
     acqn_type = db.Column(db.String(100), primary_key=True)
     spare_column = db.Column(db.String(50), nullable=True)
     def __init__(self, acqn_type, spare_column):
          self.acqn_type=acq_type
          self.spare_column=spare_column

@event.listens_for(Acquisition.__table__, 'after_create')
def add_acquisitions(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'acqn_type':'DDA', 'spare_column':'empty'},
                                 {'acqn_type':'DIA', 'spare_column':'empty'},
                                 {'acqn_type':'targeted', 'spare_column':'empty'},
                                 {'acqn_type':'intact protein', 'spare_column':'empty'}])

	



class BenchMethods(db.Model):
     __tablename__ = 'bench_methods'
     bench_method = db.Column(db.String(100), primary_key=True)
     mins_per_method = db.Column(db.Float, nullable=False)
     def __init__(self, bench_method, mins_per_method):
          self.bench_method=bench_method
          self.mins_per_method=mins_per_method

@event.listens_for(BenchMethods.__table__, 'after_create')
def add_bench_methods(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'bench_method':'no_prep_required', 'mins_per_method':0},
                                 {'bench_method':'gel_cleanup_gelbandID', 'mins_per_method':15},
                                 {'bench_method':'s_trap_digestion', 'mins_per_method':60},
                                 {'bench_method':'insolution_digest', 'mins_per_method':60},
                                 {'bench_method':'gel_cleanup_whole_sample_facilitygel', 'mins_per_method':360},
                                 {'bench_method':'gel_cleanup_whole_sample_usergel', 'mins_per_method':120},
                                 {'bench_method':'tmt_single_injection', 'mins_per_method':240},
                                 {'bench_method':'tmt_fractionation', 'mins_per_method':480},
                                 {'bench_method':'intact_protein_prep', 'mins_per_method':60}])






class InstrumentDataMethods(db.Model):
     __tablename__ = 'instrument_data_methods'
     instrument_method = db.Column(db.String(100), primary_key=True)
     mins_per_method_instr = db.Column(db.Float, nullable=False)
     mins_per_method_search = db.Column(db.Float, nullable=False)
     def __init__(self, instrument_method, mins_per_method_instr, mins_per_method_search):
          self.instrument_method=instrument_method
          self.mins_per_method_instr=mins_per_method_instr
          self.mins_per_method_search=mins_per_method_search
          
@event.listens_for(InstrumentDataMethods.__table__, 'after_create')
def add_instrument_data_methods(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'instrument_method':'repeat DB search(0)', 'mins_per_method_instr':0, 'mins_per_method_search':60},
                                 {'instrument_method':'SingleGelBand(120)', 'mins_per_method_instr':120, 'mins_per_method_search':15},
                                 {'instrument_method':'IP_fromSTrap(60)', 'mins_per_method_instr':60, 'mins_per_method_search':60},
                                 {'instrument_method':'IP_fromGel(90)', 'mins_per_method_instr':90, 'mins_per_method_search':72},
                                 {'instrument_method':'SILAC_fromGel(90)', 'mins_per_method_instr':90, 'mins_per_method_search':72},
                                 {'instrument_method':'ProximityLigation(180)', 'mins_per_method_instr':180, 'mins_per_method_search':72},
                                 {'instrument_method':'WholeSample_fromSolution(264)', 'mins_per_method_instr':264, 'mins_per_method_search':24},
                                 {'instrument_method':'WholeSample_fromGel(90)', 'mins_per_method_instr':90, 'mins_per_method_search':72},
                                 {'instrument_method':'TMTsingle(270)', 'mins_per_method_instr':270, 'mins_per_method_search':180},
                                 {'instrument_method':'TMTsingle(90)', 'mins_per_method_instr':90, 'mins_per_method_search':180},
                                 {'instrument_method':'TMTfractionated(188)', 'mins_per_method_instr':188, 'mins_per_method_search':240},
                                 {'instrument_method':'IntactMass(60)', 'mins_per_method_instr':60, 'mins_per_method_search':60}])





class PricePerMin(db.Model):
     __tablename__ = 'price_per_min'
     activity = db.Column(db.String(100), primary_key=True)
     price_per_min = db.Column(db.Float, nullable=False)
     def __init__(self, activity, price_per_min):
          self.activity=activity
          self.price_per_min=price_per_min

@event.listens_for(PricePerMin.__table__, 'after_create')
def add_price_per_min(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'activity':'bench', 'price_per_min':1.01},
                                 {'activity':'instrument', 'price_per_min':1.2},
                                 {'activity':'data_standard', 'price_per_min':1.01},
                                 {'activity':'data_bespoke', 'price_per_min':0.61}])





class InstituteType(db.Model):
     __tablename__ = 'institute_type'
     institute_type = db.Column(db.String(100), primary_key=True)
     price_per_type = db.Column(db.Float, nullable=False)
     def __init__(self, institute_type, price_per_type):
          self.institute_type=institute_type
          self.price_per_type=price_per_type

@event.listens_for(InstituteType.__table__, 'after_create')
def add_institute_types(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'institute_type':'Cambridge University', 'price_per_type':1.0}, {'institute_type':'Other Academia', 'price_per_type':1.223},{'institute_type':'Industry', 'price_per_type':2.0}])
    




class Species(db.Model):
     __tablename__ = 'species'
     species = db.Column(db.String(100), primary_key=True)
     def __init__(self, species):
          self.species=species

@event.listens_for(Species.__table__, 'after_create')
def add_species(tbl, conn, **kw):
     conn.execute(tbl.insert(), [{'species':'No DB search'},
                                 {'species':'Human'},
                                 {'species':'Human w isoforms'},
                                 {'species':'Ecoli'},
                                 {'species':'Plasmodium falciperum'},
                                 {'species':'Salmonella'},
                                 {'species':'Pig'},
                                 {'species':'Horse'},
                                 {'species':'Cat'},
                                 {'species':'Dog'},
                                 {'species':'Chinese hamster'},
                                 {'species':'African green monkey'},
                                 {'species':'Orientia ssp. karp'},
                                 {'species':'Niaph virus'},
                                 {'species':'Influenza A'},
                                 {'species':'Other'}])
    




	
