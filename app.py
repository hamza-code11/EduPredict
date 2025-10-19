from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory
)
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from functools import wraps
import os
from datetime import datetime

# ---------------------- APP CONFIG ----------------------
app = Flask(__name__)
app.secret_key = "your_secret_key"   # ⚡ Change in production!

# ✅ MongoDB connection (Atlas)
app.config["MONGO_URI"] = "mongodb+srv://eduprediect:eduprediect@cluster0.ra81j.mongodb.net/eduprediect?retryWrites=true&w=majority&appName=Cluster0"
mongo = PyMongo(app)

# # ✅ Upload folder (for assignments)
# UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# ---------------------- HELPERS ----------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ✅ User ko har template me available banane ke liye
@app.context_processor
def inject_user():
    if 'user_id' in session:
        current_user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
        return dict(user=current_user)
    return dict(user=None)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
        if not user or user.get('role') != 'admin':
            flash("Admin access required.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def serialize_cursor(cursor):
    out = []
    for d in cursor:
        d['id'] = str(d['_id'])
        if 'due_date' in d and isinstance(d['due_date'], datetime):
            d['due_date_str'] = d['due_date'].strftime("%Y-%m-%d")
        out.append(d)
    return out

# ---------------------- ROUTES ----------------------
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard')
                        if session.get('role') == 'admin'
                        else url_for('student_dashboard'))
    return render_template('website/home.html')

# ---------- AUTH ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard')
                        if session.get('role') == 'admin'
                        else url_for('student_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        if not username or not password:
            flash("Username and password required.", "warning")
            return redirect(url_for('register'))
        if password != confirm:
            flash("Passwords do not match.", "warning")
            return redirect(url_for('register'))

        if mongo.db.users.find_one({"username": username}):
            flash("Username already taken.", "warning")
            return redirect(url_for('register'))

        mongo.db.users.insert_one({
            "username": username,
            "password": generate_password_hash(password),
            "role": "student",
            "created_at": datetime.utcnow()
        })
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard')
                        if session.get('role') == 'admin'
                        else url_for('student_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = mongo.db.users.find_one({"username": username})
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user.get('role', 'student')
            flash("Logged in successfully.", "success")
            return redirect(url_for('admin_dashboard')
                            if session['role'] == 'admin'
                            else url_for('student_dashboard'))
        flash("Invalid username or password.", "danger")
        return redirect(url_for('login'))
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for('index'))






from flask import render_template, request, redirect, url_for, flash, session
from bson import ObjectId
from datetime import datetime

@app.route('/student')
@login_required
def student_dashboard():
    student_id = ObjectId(session['user_id'])

    # Get student document
    current_user = mongo.db.users.find_one({"_id": student_id})

    # Enrollments join karo classes ke saath
    pipeline = [
        {"$match": {"student_id": student_id}},
        {"$lookup": {
            "from": "classes",
            "localField": "class_id",
            "foreignField": "_id",
            "as": "class_info"
        }},
        {"$unwind": "$class_info"}
    ]
    joined_classes = list(mongo.db.enrollments.aggregate(pipeline))

    return render_template(
        'website/dashboard.html',
        user=current_user,           # ✅ yahan add kiya
        joined_classes=joined_classes
    )



# ---------- STUDENT: Join Class ----------
@app.route('/student/join_class', methods=['POST'])
@login_required
def student_join_class():
    student_id = ObjectId(session['user_id'])
    class_code = request.form.get('class_code', '').strip()

    # Validate ID format
    try:
        class_obj_id = ObjectId(class_code)
    except:
        flash("Invalid Class ID format.", "danger")
        return redirect(url_for('student_dashboard'))

    # Check class exists
    class_doc = mongo.db.classes.find_one({"_id": class_obj_id})
    if not class_doc:
        flash("No class found with this ID.", "warning")
        return redirect(url_for('student_dashboard'))

    # ✅ Insert a document into a separate "enrollments" collection
    mongo.db.enrollments.update_one(
        {"student_id": student_id, "class_id": class_obj_id},
        {"$set": {"student_id": student_id, "class_id": class_obj_id}},
        upsert=True  # <-- agar record na ho to create kar dega
    )

    # Optional: also store inside user's joined_classes array
    mongo.db.users.update_one(
        {"_id": student_id},
        {"$addToSet": {"joined_classes": class_obj_id}}
    )

    flash(f"You have successfully joined the class: {class_doc['class_name']}", "success")
    return redirect(url_for('student_dashboard'))






# ---------- PROFILE ----------
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '').strip()
        update_data = {}

        if new_username and new_username != user['username']:
            if mongo.db.users.find_one({"username": new_username}):
                flash("Username already taken.", "warning")
                return redirect(url_for('profile'))
            update_data['username'] = new_username
            session['username'] = new_username

        if new_password:
            update_data['password'] = generate_password_hash(new_password)

        if update_data:
            mongo.db.users.update_one(
                {"_id": ObjectId(session['user_id'])},
                {"$set": update_data}
            )
            flash("Profile updated successfully.", "success")
        else:
            flash("No changes made.", "info")
        return redirect(url_for('profile'))

    return render_template('website/profile.html', user=user)


# ---------- ADMIN: Dashboard ----------
@app.route('/admin')
@admin_required
def admin_dashboard():
    users = serialize_cursor(mongo.db.users.find().sort("created_at", -1))
    classes = serialize_cursor(mongo.db.classes.find().sort("created_at", -1))
    current_user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
    return render_template(
        'admin/dashboard.html',
        users=users,
        classes=classes,
        user=current_user
    )

# ---------- ADMIN: Create Class ----------
@app.route('/admin/create_class', methods=['POST'])
@admin_required
def create_class():
    class_name = request.form.get('className').strip()
    description = request.form.get('classDescription').strip()
    admin_id = ObjectId(session['user_id'])

    if not class_name:
        flash("Class name is required.", "warning")
        return redirect(url_for('admin_dashboard'))

    new_class = {
    "class_name": class_name,
    "description": description,
    "created_by_id": admin_id,
    "created_by_name": session['username'],
    "created_at": datetime.utcnow()
}

    mongo.db.classes.insert_one(new_class)
    flash(f"Class '{class_name}' created successfully!", "success")
    return redirect(url_for('admin_dashboard'))

# ✅ Dummy route to avoid BuildError if template still calls create_task
@app.route('/admin/create_task')
@admin_required
def create_task():
    flash("Create Task page is under construction.", "info")
    return redirect(url_for('admin_dashboard'))





# ---------- ADMIN: My Classes List ----------
@app.route('/admin/my_classes')
@admin_required
def admin_my_classes():
    admin_id = ObjectId(session['user_id'])

    # ✅ Current Admin User
    current_user = mongo.db.users.find_one({"_id": admin_id})

    # ✅ Admin ke banaye huwe saare classes (NO LIMIT)
    classes = list(mongo.db.classes.find({"created_by_id": admin_id}).sort("created_at", -1))

    return render_template(
        'admin/my_classes.html',
        classes=classes,
        user=current_user
    )


# ---------- ADMIN: Update Class ----------
@app.route('/admin/update_class/<class_id>', methods=['POST'])
@admin_required
def update_class(class_id):
    class_name = request.form.get('class_name', '').strip()
    description = request.form.get('description', '').strip()

    if not class_name:
        flash("Class name cannot be empty.", "warning")
        return redirect(url_for('admin_my_classes'))

    mongo.db.classes.update_one(
        {"_id": ObjectId(class_id)}, 
        {"$set": {
            "class_name": class_name,
            "description": description,
            "updated_at": datetime.utcnow()
        }}
    )
    flash("Class updated successfully!", "success")
    return redirect(url_for('admin_my_classes'))


# ---------- ADMIN: Delete Class ----------
@app.route('/admin/delete_class/<class_id>', methods=['POST'])
@admin_required
def delete_class(class_id):
    mongo.db.classes.delete_one({"_id": ObjectId(class_id)})
    flash("Class deleted successfully!", "success")
    return redirect(url_for('admin_my_classes'))



# ---------- ADMIN: Class Detail (Assignments + Students + Progress) ----------
@app.route('/admin/class/<class_id>')
@admin_required
def admin_class_detail(class_id):
    class_oid = ObjectId(class_id)

    # ✅ Find class
    class_obj = mongo.db.classes.find_one({"_id": class_oid})
    if not class_obj:
        flash("Class not found.", "warning")
        return redirect(url_for('admin_dashboard'))

    # ✅ Assignments for this class
    assignments = list(mongo.db.assignments.find({"class_id": class_oid}).sort("created_at", -1))
    total_assignments = len(assignments)
    assignment_ids = [a["_id"] for a in assignments]

    # ✅ Students who joined this class
    students = list(mongo.db.users.find({"joined_classes": class_oid}))

    # ✅ Prepare progress data
    students_data = []
    for student in students:
        sid = student["_id"]

        # 🔹 Get all submissions (multiple screenshots may exist)
        submissions = list(mongo.db.submissions.find({
            "assignment_id": {"$in": assignment_ids},
            "student_id": sid
        }))

        # 🔹 FIX: count only unique assignment_ids (ignore multiple screenshots)
        unique_assignment_ids = {s["assignment_id"] for s in submissions}
        completed = len(unique_assignment_ids)
        incomplete = total_assignments - completed

        # 🔹 FIX: Get latest marks per assignment (if multiple uploads exist)
        marks_by_assignment = {}
        for s in submissions:
            aid = s["assignment_id"]
            marks = int(s.get("marks", 0))
            # Always overwrite so last/latest submission wins
            marks_by_assignment[aid] = marks  

        marks_list = list(marks_by_assignment.values())
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0

        # 🔹 Calculate progress %
        progress = round((completed / total_assignments) * 100, 1) if total_assignments > 0 else 0

        # ✅ Improved Status logic
        if progress == 100:
            status, color = "Excellent", "success"
        elif avg_marks >= 85:
            status, color = "Excellent", "success"
        elif avg_marks >= 70:
            status, color = "Good", "primary"
        elif avg_marks >= 50:
            status, color = "Moderate", "warning"
        else:
            status, color = "Needs Improvement", "danger"

        # ✅ Append student progress info
        students_data.append({
            "name": student.get("username", "Unknown"),
            "avatar": student.get("avatar", f"https://i.pravatar.cc/40?u={sid}"),
            "total": total_assignments,
            "completed": completed,
            "incomplete": incomplete,
            "progress": progress,
            "status": status,
            "color": color,
            "student_id": str(sid)
        })

    # ✅ Current admin user
    current_user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})

    # ✅ Debug log (optional)
    print("=== DEBUG students_data ===", students_data)

    # ✅ Render page
    return render_template(
        'admin/class_detail.html',
        class_obj=class_obj,
        assignments=assignments,
        students=students,
        students_data=students_data,  # 👈 progress table data
        user=current_user
    )





# ---------- ADMIN: Create Assignment ----------
@app.route('/admin/class/<class_id>/create_assignment', methods=['POST'])
@admin_required
def create_assignment(class_id):
    title = request.form.get('title').strip()
    description = request.form.get('description').strip()
    due_date = request.form.get('due_date').strip()  # Example: YYYY-MM-DD HH:MM

    if not title:
        flash("Title is required.", "warning")
        return redirect(url_for('admin_class_detail', class_id=class_id))

    new_assignment = {
        "class_id": ObjectId(class_id),
        "title": title,
        "description": description,
        "due_date": due_date,
        "created_at": datetime.utcnow()
    }

    mongo.db.assignments.insert_one(new_assignment)
    flash("Assignment created successfully!", "success")
    return redirect(url_for('admin_class_detail', class_id=class_id))

# ---------- ADMIN: Delete Assignment ----------
@app.route('/admin/class/<class_id>/delete_assignment/<assignment_id>', methods=['POST'])
@admin_required
def delete_assignment(class_id, assignment_id):
    mongo.db.assignments.delete_one({"_id": ObjectId(assignment_id)})
    flash("Assignment deleted successfully!", "success")
    return redirect(url_for('admin_class_detail', class_id=class_id))



# ---------- ADMIN: Update Assignment ----------
@app.route('/admin/class/<class_id>/update_assignment/<assignment_id>', methods=['POST'])
@admin_required
def update_assignment(class_id, assignment_id):
    title = request.form.get('title').strip()
    description = request.form.get('description').strip()
    due_date = request.form.get('due_date').strip()

    if not title:
        flash("Title is required.", "warning")
        return redirect(url_for('admin_class_detail', class_id=class_id))

    mongo.db.assignments.update_one(
        {"_id": ObjectId(assignment_id)},
        {"$set": {
            "title": title,
            "description": description,
            "due_date": due_date
        }}
    )
    flash("Assignment updated successfully!", "success")
    return redirect(url_for('admin_class_detail', class_id=class_id))





































@app.route('/student/class/<class_id>')
@login_required
def student_class_detail(class_id):
    student_id = ObjectId(session['user_id'])

    current_user = mongo.db.users.find_one({"_id": student_id})

    # ✅ Verify enrollment
    enrollment = mongo.db.enrollments.find_one({
        "student_id": student_id,
        "class_id": ObjectId(class_id)
    })
    if not enrollment:
        flash("You are not enrolled in this class.", "warning")
        return redirect(url_for('student_dashboard'))

    # ✅ Class info
    class_doc = mongo.db.classes.find_one({"_id": ObjectId(class_id)})
    assignments = list(mongo.db.assignments.find({"class_id": ObjectId(class_id)}))
    assignment_ids = [a["_id"] for a in assignments]

    # ✅ Fetch submissions by this student for these assignments
    submissions = list(mongo.db.submissions.find({
        "student_id": student_id,
        "assignment_id": {"$in": assignment_ids}
    }))

    # ✅ Progress calculation
    total_assignments = len(assignments)
    completed_assignment_ids = { str(sub['assignment_id']) for sub in submissions if sub.get('assignment_id') }
    completed_assignments = len(completed_assignment_ids)
    incomplete_assignments = total_assignments - completed_assignments
    progress_percent = round((completed_assignments / total_assignments) * 100) if total_assignments > 0 else 0

    # ✅ Average marks
    marks_list = [s.get("marks", 0) for s in submissions if "marks" in s]
    average_marks = round(sum(marks_list) / len(marks_list), 2) if marks_list else 0

    # ✅ Performance
    if progress_percent >= 80:
        status, badge_class = "Excellent", "bg-success"
    elif progress_percent >= 50:
        status, badge_class = "Moderate effort", "bg-warning text-dark"
    else:
        status, badge_class = "Needs improvement", "bg-danger"

    # ✅ Fetch all students enrolled in this class
    enrollments = list(mongo.db.enrollments.find({"class_id": ObjectId(class_id)}))
    student_ids = [e["student_id"] for e in enrollments]
    students = list(mongo.db.users.find({"_id": {"$in": student_ids}}))

    return render_template(
        'website/classdetails.html',
        class_obj=class_doc,
        assignments=assignments,
        total_assignments=total_assignments,
        completed_assignments=completed_assignments,
        incomplete_assignments=incomplete_assignments,
        progress_percent=progress_percent,
        average_marks=average_marks,
        status=status,
        badge_class=badge_class,
        user=current_user,
        students=students  # ✅ Pass students to template
    )


















# ✅ Assignment detail page (student click karta hai assignment card par)
@app.route("/assignment/<assignment_id>")
@login_required
def assignment_detail(assignment_id):
    assignment = mongo.db.assignments.find_one({"_id": ObjectId(assignment_id)})
    if assignment:
        assignment["_id"] = str(assignment["_id"])
        return render_template("website/assignment_detail.html", assignment=assignment)
    else:
        flash("Assignment not found.", "danger")
        return redirect(url_for("student_dashboard"))



















# ✅ File upload config
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "zip", "txt"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ✅ Student uploads assignment file
@app.route("/submit_assignment/<assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    if "file" not in request.files:
        flash("No file part", "danger")
        return redirect(request.referrer)

    file = request.files["file"]

    if file.filename == "":
        flash("No selected file", "danger")
        return redirect(request.referrer)

    if file and allowed_file(file.filename):
        file.seek(0, os.SEEK_END)  # move pointer to end
        file_size = file.tell()    # get file size in bytes
        file.seek(0)               # reset pointer to beginning

        if file_size > MAX_FILE_SIZE:
            flash("File too large! Limit is 5MB.", "danger")
            return redirect(request.referrer)

        filename = f"{assignment_id}_{file.filename}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        # ✅ Save submission record in MongoDB
        submission = {
            "assignment_id": ObjectId(assignment_id),
            "student_id": ObjectId(session["user_id"]),  # logged-in student
            "filename": filename,
            "filepath": filepath
        }
        mongo.db.submissions.insert_one(submission)

        flash("Assignment submitted successfully!", "success")
        return redirect(url_for("assignment_detail", assignment_id=assignment_id))
    else:
        flash("Invalid file type!", "danger")
        return redirect(request.referrer)



























from bson import ObjectId
from flask import render_template, send_from_directory, abort
import os


@app.route('/class/<class_id>/assignment/<assignment_id>/submissions', methods=['GET', 'POST'])
def view_submissions(class_id, assignment_id):
    class_obj = mongo.db.classes.find_one({'_id': ObjectId(class_id)})
    assignment = mongo.db.assignments.find_one({'_id': ObjectId(assignment_id)})

    if not class_obj or not assignment:
        flash("Class or assignment not found.", "danger")
        return redirect(url_for('admin_dashboard'))

    # ✅ Group submissions by student
    submissions = list(mongo.db.submissions.find({'assignment_id': ObjectId(assignment_id)}))
    grouped = {}

    for sub in submissions:
        student_id = str(sub['student_id'])
        if student_id not in grouped:
            student = mongo.db.users.find_one({'_id': ObjectId(sub['student_id'])})
            grouped[student_id] = {
                'student_id': student_id,
                'student_name': student['username'] if student else 'Unknown',
                'files': [],
                'marks': sub.get('marks')  # first submission marks
            }
        grouped[student_id]['files'].append(sub['filename'])

    students_submissions = list(grouped.values())

    # ✅ Handle marks update
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        marks = request.form.get('marks')

        try:
            marks = int(marks)
            if marks < 0 or marks > 100:
                flash("Marks must be between 0 and 100.", "warning")
            else:
                # Update marks for all submissions by this student in this assignment
                mongo.db.submissions.update_many(
                    {'assignment_id': ObjectId(assignment_id), 'student_id': ObjectId(student_id)},
                    {'$set': {'marks': marks}}
                )
                flash("Marks saved successfully!", "success")
        except ValueError:
            flash("Invalid marks input.", "danger")

        return redirect(url_for('view_submissions', class_id=class_id, assignment_id=assignment_id))

    return render_template(
        'admin/view_submissions.html',
        class_obj=class_obj,
        assignment=assignment,
        students_submissions=students_submissions
    )


# ✅ New route to view all files by a student
@app.route('/class/<class_id>/assignment/<assignment_id>/student/<student_id>/files')
def view_student_files(class_id, assignment_id, student_id):
    student = mongo.db.users.find_one({'_id': ObjectId(student_id)})
    assignment = mongo.db.assignments.find_one({'_id': ObjectId(assignment_id)})

    # ✅ Get all assignments of this class
    assignments = list(
        mongo.db.assignments.find({"class_id": ObjectId(class_id)}).sort("created_at", -1)
    )
    assignment_ids = [a["_id"] for a in assignments]

    # ✅ Fetch submissions for this student for all class assignments
    submissions = list(
        mongo.db.submissions.find({
            "student_id": ObjectId(student_id),
            "assignment_id": {"$in": assignment_ids}
        })
    )
    

    return render_template(
        'admin/student_files.html',
        student=student,
        assignment=assignment,
        submissions=submissions
    )







# -------------
# -------------
# -------------
@app.route("/student/class/<class_id>/progress/<student_id>")
@login_required
def student_progress(class_id, student_id):
    # ✅ Agar admin kisi student ka data dekh raha hai to uska ID use ho
    student_id = ObjectId(student_id)

    # ✅ All assignments in this class
    assignments = list(mongo.db.assignments.find({"class_id": ObjectId(class_id)}))
    total_assignments = len(assignments)
    assignment_ids = [a["_id"] for a in assignments]

    # ✅ All submissions by this student (avoid duplicates)
    submissions = list(mongo.db.submissions.find({
        "assignment_id": {"$in": assignment_ids},
        "student_id": student_id
    }))

    # ✅ Group by assignment → 1 submission count per assignment
    unique_submissions = {}
    for sub in submissions:
        aid = str(sub["assignment_id"])
        if aid not in unique_submissions:
            unique_submissions[aid] = sub  # only first submission counted

    completed = len(unique_submissions)
    incomplete = total_assignments - completed

    # ✅ Average marks (based on unique submissions)
    marks_list = [s.get("marks", 0) for s in unique_submissions.values() if "marks" in s]
    avg_marks = round(sum(marks_list) / len(marks_list), 2) if marks_list else 0

    # ✅ Progress %
    progress_percent = round((completed / total_assignments) * 100, 1) if total_assignments > 0 else 0

    # ✅ Performance Status
    if avg_marks >= 85:
        status = "Excellent"
        color = "success"
    elif avg_marks >= 70:
        status = "Good"
        color = "primary"
    elif avg_marks >= 50:
        status = "Moderate"
        color = "warning"
    else:
        status = "Needs Improvement"
        color = "danger"

    # ✅ Chart data (for frontend)
    chart_data = []
    for a in assignments:
        aid = str(a["_id"])
        sub = unique_submissions.get(aid)
        marks = sub.get("marks", 0) if sub else 0
        chart_data.append({
            "title": a["title"],
            "marks": marks,
            "submitted": 1 if sub else 0
        })

    return render_template(
        "website/progress.html",
        total=total_assignments,
        completed=completed,
        incomplete=incomplete,
        avg_marks=avg_marks,
        progress=progress_percent,
        status=status,
        color=color,
        chart_data=chart_data
    )




# Optional: For downloading ZIP or other files
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    return send_from_directory(uploads_dir, filename, as_attachment=True)





# -------------
# -------------
# -------------
# -------------


@app.route("/admin/class/<class_id>/progress")
@login_required
def admin_class_progress(class_id):
    class_oid = ObjectId(class_id)

    assignments = list(mongo.db.assignments.find({"class_id": class_oid}))
    total_assignments = len(assignments)
    assignment_ids = [a["_id"] for a in assignments]

    # ✅ Get students from users collection instead of enrollments
    students = list(mongo.db.users.find({"joined_classes": class_oid}))
    student_ids = [s["_id"] for s in students]

    students_data = []

    for sid in student_ids:
        student = mongo.db.users.find_one({"_id": sid})
        submissions = list(mongo.db.submissions.find({
            "assignment_id": {"$in": assignment_ids},
            "student_id": sid
        }))

        completed = len(submissions)
        incomplete = total_assignments - completed
        marks_list = [int(s.get("marks", 0)) for s in submissions if "marks" in s]
        avg_marks = round(sum(marks_list) / len(marks_list), 1) if marks_list else 0
        progress = round((completed / total_assignments) * 100, 1) if total_assignments > 0 else 0

        if avg_marks >= 85:
            status, color = "Excellent", "success"
        elif avg_marks >= 70:
            status, color = "Good", "primary"
        elif avg_marks >= 50:
            status, color = "Moderate", "warning"
        else:
            status, color = "Needs Improvement", "danger"

        students_data.append({
            "name": student.get("username", "Unknown"),
            "avatar": student.get("avatar", f"https://i.pravatar.cc/40?u={sid}"),
            "total": total_assignments,
            "completed": completed,
            "incomplete": incomplete,
            "progress": progress,
            "status": status,
            "color": color,
            "student_id": str(sid)
        })

    print("=== DEBUG students_data ===", students_data)

    return render_template(
        "admin/class_detail.html",
        class_id=str(class_id),
        students_data=students_data
    )












from datetime import datetime
from bson import ObjectId
from flask import request, session, redirect, url_for, flash, render_template

@app.route('/feedback', methods=['GET', 'POST'])
@login_required
def feedback():
    if request.method == 'POST':
        user_id = ObjectId(session['user_id']) if 'user_id' in session else None
        username = session.get('username', 'Anonymous')
        rating = request.form.get('rating')
        message = request.form.get('message', '').strip()

        # 🔹 Basic validation
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError()
        except Exception:
            flash("Please provide a rating between 1 and 5.", "warning")
            return redirect(request.referrer or url_for('feedback'))

        if not message:
            flash("Please write a short message.", "warning")
            return redirect(request.referrer or url_for('feedback'))

        # 🔹 Create document (no class_id)
        doc = {
            "user_id": user_id,
            "username": username,
            "rating": rating,
            "message": message,
            "created_at": datetime.utcnow()
        }

        mongo.db.feedback.insert_one(doc)
        flash("Thanks — your feedback has been submitted.", "success")
        return redirect(url_for('student_dashboard'))

    # GET → render form
    return render_template('website/feedback.html')



# ---------- DEV HELPER ----------
@app.route('/init_admin')
def init_admin():
    if mongo.db.users.find_one({"role": "admin"}):
        return "Admin already exists. Remove this route in production."
    mongo.db.users.insert_one({
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "role": "admin",
        "created_at": datetime.utcnow()
    })
    return "Default admin created: username=admin, password=admin123"

# ---------------------- RUN ----------------------
if __name__ == '__main__':
    app.run(debug=True)
