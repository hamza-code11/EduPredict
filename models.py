from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Classes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    # relationships
    students = db.relationship("Student", secondary="enrollments", backref="classes")

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    due_time = db.Column(db.Time, nullable=False)
    created_by = db.Column(db.Integer)  # optional, FK to user table

# Many-to-many enrollment table
enrollments = db.Table(
    "enrollments",
    db.Column("student_id", db.Integer, db.ForeignKey("student.id")),
    db.Column("class_id", db.Integer, db.ForeignKey("classes.id"))
)
