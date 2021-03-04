import datetime
import os
from nipo.attendance import ModuleAttendance
from nipo import attendance, production_session, test_session, db
from flask import Flask, flash, request, render_template, jsonify, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from werkzeug.urls import url_parse
from nipo.db import schema
session = test_session		#Change to production_session in the production environment. This would then utilise production data(bases) 

#The nipo.forms import requires the session var so it is done after session's creation.
from nipo.forms import LoginForm, RegistrationForm
import random


#TODO: Add login required to relevant routes
#TODOs:
# 0. Modify populate.py so that it creates a default user
# 1. Create landing page that doesn't depend on student data(for guest users)
# 2. Create view to check individual attendance
# 3. Use pandas dataframe to store attendance data
#


app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']
login_manager = LoginManager(app)
login_manager.init_app(app)

login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return session.query(schema.User).filter(schema.User.id==int(user_id)).one_or_none()


def get_attendance_module(modulecode):
	try:
		mod_attendance = ModuleAttendance(modulecode)

	except ValueError:
		#Handle this error better
		return "Invalid module code >>{}<<".format(modulecode)

	return mod_attendance.getAttendance()




def get_attendance_student(studentID):
	stud_attendance = attendance.StudentAttendance(studentID, session=session)
	modules = stud_attendance.get_student_modules()
	modulecodes = [mod.code for mod in modules]

	student_attendance = {}

	for modulecode in modulecodes:
		student_attendance[str(modulecode)]=stud_attendance.\
											get_module_attendance(modulecode)

	return student_attendance



def get_attendance_student_module(studentID,modulecode):

	stud = attendance.StudentAttendance(studentID, session)
	stud_att = stud.get_module_attendance(modulecode)
	att = stud_att['attendance']
	tot_present = 0
	tot_sesh = len(att)

	if tot_sesh <= 0:
		stud_att['Present_pc'] = 100
		

	else:
		for sesh in att:
			tot_present += int(att[sesh])

		stud_att['Present_pc'] =  int(tot_present/tot_sesh *100)


	stud_att['Absent_pc'] = 100-stud_att['Present_pc']
	return stud_att


def update_attendance_student_module(studentID, modulecode, sessiondate, present=False):
	#Check for exceptions thrown in case of non-existent student and invalid session date. then catch them as appropriate
	mod_attendance = ModuleAttendance(modulecode, session)
	mod_attendance.updateAttendance(studentID,sessiondate,present=present)

def mark_attendance_students_module(stud_attendances, modulecode, sessiondate):
	'''Accept a dictionary of key:value pairs where the keys are student ID's and the values are True or False for present and absent for each respective student'''
	assert type(stud_attendances) is dict
	mod_attendance = ModuleAttendance(modulecode, session)

	for ID in stud_attendances:
		mod_attendance.updateAttendance(ID, sessiondate,present=stud_attendances[ID])

def recognise_student(studentID=None, encoding=None, face_pixels=None, session=session):
	if studentID is not None:
		student = attendance.StudentAttendance(studentID, session)
	elif encoding is not None:
		student = get_student_from_encoding(encoding)
	elif face_pixels is not None:
		student = get_student_from_face_pixels(face_pixels)
	else:
		raise ValueError("No student ID, face encoding or face pixels provided")
	return student


def get_student_from_encoding(encoding):
	return attendance.get_student_from_encoding(encoding, session)

def get_student_from_face_pixels(face_pixels):
	return attendance.get_student_from_pixels(face_pixels, session)

#TODO: move next 3 methods elsewhere. They shouldnt exist here. Only for dev
def get_course_list(session):
	courses = session.query(db.schema.Course).\
							limit(10).\
							all()

	return courses

def get_module_list(session):
	modules = session.query(db.schema.Module).\
							limit(10).\
							all()

	return modules


def get_student_list(session):
	students = session.query(db.schema.Student).\
							limit(10).\
							all()

	return students


#Landing page, display the courses (e.g TIEY4, Form 1, Grade 3B etc)
@app.route('/')
@app.route('/index/')
@login_required
def landing():
	'''Display landing page for student, staff(instructor) or admin'''
	#Elif student return student dashboard
	#Elif instructor return syaff dashboard
	#elif admin return admin dashboard

	if current_user.privilege == schema.PrivilegeLevel.student.name:
		modules = get_module_list(session)	#TODO: This function currently gets all modules in the system. Need to modify so that it only gets the modules a student is enrolled to. Nipo challenge??
		return render_template('student_dashboard.html',modules = modules)

		courses = get_course_list(session)
		return render_template('list_courses.html', courses = courses)

	elif current_user.privilege == schema.PrivilegeLevel.staff.name:
		#TODO: Only show modules staff member is registered to. For each module, only show valid dates.
		modules = get_module_list(session)
		dates = []
		formatted_dates = []
		for module in modules:
			dates += ModuleAttendance(module.code, session).dates

		for date in dates:
			human_friendly_format = date.strftime('%a %d %b %H:%M')
			iso_format = date.strftime('%Y-%m-%dT%H:%M')
			combined_format = {"human friendly format": human_friendly_format,
								"iso format": iso_format}

			formatted_dates.append(combined_format)

		students = get_student_list(session)
		for student in students:
			student.status=random.choice(["student-absent","student-present"])
		return render_template('staff_dashboard.html',dates=formatted_dates,students=students,modules=modules)

	elif current_user.privilege == schema.PrivilegeLevel.admin.name:
		return "Hello Administrator. There seems to be nothing for you here"

	

@app.route('/logout')
@login_required
def logout():
	logout_user()
	session.commit()
	return redirect(url_for('landing'))

@app.route('/login', methods = ['GET','POST'])
def login():
	if current_user.is_authenticated:
		return redirect(url_for('landing'))
	form = LoginForm()
	if form.validate_on_submit():
		username = form.username.data
		password = form.password.data
		user = session.query(schema.User).\
					  filter(schema.User.username == username.lower()).\
									  one_or_none()

		if user is None or not user.check_password(password):
			flash('Invalid username or password')
			return redirect(url_for('login'))
		
		login_user(user, remember=form.remember_me.data)
		#Not sure if it is necessary to commit/persist after every login
		next_page = request.args.get('next')
		if not next_page or url_parse(next_page).netloc != '':
			next_page = url_for('landing')
		#print ("Next Page is >>>>>>{}".format(user.is_authenticated))
		return redirect(next_page)
	return render_template('login.html', title='Sign In', form=form)

#This route will need to be hidden in future/require login because students wouldnt register themselves. Only an admin should register students. We probably also want to be able to register students in bulk using a csv or excel file
@app.route('/register', methods=['GET', 'POST'])
def register():
	if current_user.is_authenticated:
		return redirect(url_for('landing'))
	form = RegistrationForm()
	if form.validate_on_submit():
		user = schema.User(username=form.username.data.lower(), email=form.email.data,authenticated=False,active=True)
		user.set_password(form.password.data)
		session.add(user)
		session.commit()		
		flash('Congratulations, you are now a registered user!')
		return redirect(url_for('login'))
	return render_template('register.html', title='Register', form=form)

under_cons_msg = "OOPS! This part of the website is still under construction"

@app.route('/userdetails')
@login_required
def get_user_details():
	'''Get Student's Name and ID'''
	user_detail = {}
	if current_user.privilege == 'student':
		user_detail['name'] = current_user.name
		user_detail['student_id'] = current_user.student_id
		user_detail['status'] = 0	#TODO: Determine status codes for Nipo

	else:
		user_detail['status'] = 1	#TODO: Determine status codes for Nipo
	
	return jsonify(user_detail)



#Will need to rething these routes. 
	# Currently thinking of them as separate pages.
	# They should however exist as part of a single page that calls javascript to get data.
	# The page then evolves as appropriate
	# The routes would thus mostly return json data. Rarely ever an HTML template

# Return a list of the modules that a student is taking
@app.route('/modules', methods = ['GET','POST'])
def get_student_modules():
	return get_student_attendance()

# Return attendance record for the student logged in for the specified module
@app.route('/module/attendance', methods = ['GET','POST'])
def get_student_module_attendance():
	if request.method == 'POST':
		req = request.get_json()
		studentID = req['studentID']
		modulecode = req['modulecode']
		student_attendance = get_attendance_student_module(studentID,modulecode)
		resp = student_attendance

		return jsonify(resp) 	#TODO: Have this returned by a pretty render_template TODO: MAke the datetime in this response ISO8601 format
	return under_cons_msg + 'for a Get request'

# Return the modules a student is enrolled in with summary attendance (Dashboard)
@app.route('/student', methods = ['GET','POST'])
def get_student_attendance():	#For all modules
	if request.method == 'POST':
		studentID = request.form.get('studentID')
		student = attendance.StudentAttendance(studentID,session)
		student_modules = student.modules

		student_attendance = dict()

		#TODO: Include student name and ID in this response

		for module in student_modules:
			student_attendance[module.code] = student.get_module_attendance(module.code)

		return jsonify(student_attendance) 	#TODO: Have this returned by a pretty  dashboard-like template
	return under_cons_msg + 'for a Get request'


# Return attendance for a student for a module 
@app.route('/student/module', methods = ['GET','POST'])
def get_module_attendance_student():	#Not Yet implemented
	return get_student_module_attendance()#TODO: Have this returned by a pretty template

#Return the list of students in a module
@app.route('/students', methods = ['POST'])
def get_module_students():		#Not Yet implemented
	if request.method == 'POST':
		modulecode = request.form.get('modulecode')
		module = attendance.ModuleAttendance(modulecode, session)

		mod_students = module.students

		resp = dict()

		for student in mod_students:
			resp[student.id] = dict()
			resp[student.id]['Name'] = student.name
			#resp[student.id]['Attendance'] = 

		#student_attendance = get_attendance_student_module(studentID,modulecode)

		return jsonify(resp) 	#TODO: Have this returned by a pretty template
	return under_cons_msg + 'for a Get request'

# Return attendance record for the student logged in for the specified module
@app.route('/module/attendance/mark', methods = ['GET','POST'])
def set_student_module_attendance():
	if request.method == 'POST':
		req = request.get_json()
		studentID = req['studentID']
		modulecode = req['modulecode']
		status = req['status']
		sess_date = req['SessionDate']	#Expects YYYY-MM-DDTHH:MM Format (Iso 8601)
		try:
			studentID = int(studentID)
		except ValueError:
			return "The student ID {} must be a number (integer)".format(studentID)
		try:
			sess_date = datetime.datetime.strptime(sess_date, '%Y-%m-%dT%H:%M')
		except ValueError:
			return "The date {} is not in the required YYYY-MM-DDTHH:mm format".format(sess_date) 

		if status.lower() == "present":
			status = True
		else:
			status = False

		mod_attendance = attendance.ModuleAttendance(modulecode, session)

		# mod_attendance.updateAttendance(studentID,sess_date, present=status)
		try:
			mod_attendance.updateAttendance(studentID,sess_date, present=status)			
		except ValueError:
			return "The date >>{}<< does not have a class session for the module with code >>{}<<".format(sess_date.isoformat(), modulecode)

		#redirect to show student's attendance for the module. Preserve the POST parameters
		return redirect(url_for('get_student_module_attendance'), code=307)
	return under_cons_msg + 'for a Get request'

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

app.debug = True
# if __name__ == '__main__':
# 	app.run(debug = True)
#Because of this final comment, the only way to run the flask app is to `flask run` on cmd
