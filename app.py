from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = 'secret_key'

client = MongoClient("mongodb://localhost:27017/")
db = client["Academics"]
users = db["users"]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = users.find_one({"username": username, "password": password})
        if user:
            session["username"] = username
            role = user["role"]
            if role == "admin":
                return redirect("/dashboard_admin")
            elif role == "teacher":
                return redirect("/dashboard_teacher")
            elif role == "student":
                student_id = user["student_id"]
                return redirect(f"/dashboard_student/{user['student_id']}")
            else:
                return "Unknown role."
        else:
            return render_template("login.html", error="Invalid credentials.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard_admin")
def dashboard_admin():
    sem1 = list(db["Semester_1"].find())
    sem2 = list(db["Semester_2"].find())
    sem3 = list(db["Semester_3"].find())
    users_list = list(db["users"].find())

    all_students = sem1 + sem2 + sem3
    student_dict = {s["student_id"]: s for s in all_students}.values()

    total_students = len(student_dict)
    total_teachers = sum(1 for u in users_list if u["role"] == "teacher")
    total_subjects = len(set(sub["subject"] for s in student_dict for sub in s["subjects"]))
    avg_gpa = round(sum([s["semester_gpa"] for s in student_dict]) / total_students, 2)

    recent_students = sorted(student_dict, key=lambda x: x.get("student_id"), reverse=True)[:5]

    return render_template("admin_dashboard.html",
                           admin_name=session.get("username", "Admin"),
                           students=recent_students,
                           stats={
                               "total_students": total_students,
                               "total_teachers": total_teachers,
                               "total_subjects": total_subjects,
                               "average_gpa": avg_gpa
                           })


@app.route("/dashboard_teacher")
def dashboard_teacher():
    sem1 = list(db["Semester_1"].find())
    sem2 = list(db["Semester_2"].find())
    sem3 = list(db["Semester_3"].find())

    all_students = sem1 + sem2 + sem3  # Simple union; refine if needed

    unique_ids = {s["student_id"]: s for s in all_students}.values()
    total_students = len(unique_ids)
    avg_gpa = round(sum([s["semester_gpa"] for s in unique_ids]) / total_students, 2)
    low_performers = sum(1 for s in unique_ids if s["semester_gpa"] < 6)

    student_summary = [
        {
            "student_id": s["student_id"],
            "name": s["name"],
            "class": f"Sem {s['semester']}" if "semester" in s else "Unknown",
            "gpa": s["semester_gpa"],
            "attendance": round(sum(sub["attendance_percentage"] for sub in s["subjects"]) / len(s["subjects"]))
        } for s in unique_ids
    ]

    return render_template("teacher_dashboard.html",
                           teacher_name=session.get("username", "Teacher"),
                           students=student_summary,
                           stats={
                               "total_students": total_students,
                               "average_gpa": avg_gpa,
                               "low_performers": low_performers
                           })


@app.route("/dashboard_student/<int:student_id>")
def student_dashboard(student_id):
    tenth_data = db["Class_10th"].find_one({"student_id": student_id})
    twelfth_data = db["Class_12th"].find_one({"student_id": student_id})
    sem1_data = db["Semester_1"].find_one({"student_id": student_id})
    sem2_data = db["Semester_2"].find_one({"student_id": student_id})
    sem3_data = db["Semester_3"].find_one({"student_id": student_id})
    
    student_name = sem1_data.get("name", "Student") if sem1_data else "Student"

    return render_template("student_dashboard.html",
                           student_id=student_id,
                           student_name=student_name,
                           tenth=tenth_data,
                           twelfth=twelfth_data,
                           sem1=sem1_data,
                           sem2=sem2_data,
                           sem3=sem3_data)


@app.route('/student/<int:student_id>/profile')
def student_profile(student_id):
    student_info_collection = db["Class_10th"]  
    student_data = student_info_collection.find_one({"student_id": student_id})

    if not student_data:
        return "Student profile not found.", 404

    return render_template("profile.html", student=student_data)

@app.route('/teacher/analytics')
def teacher_analytics():
    sem1_data = list(db["Semester_1"].find())
    sem2_data = list(db["Semester_2"].find())
    sem3_data = list(db["Semester_3"].find())
    student_meta = {s["student_id"]: s for s in db["student_info"].find()}

    # Merge semesters
    all_semesters = sem1_data + sem2_data + sem3_data
    student_sem_data = {}

    for entry in all_semesters:
        sid = entry["student_id"]
        if sid not in student_sem_data:
            student_sem_data[sid] = {"gpas": [], "attendances": []}
        student_sem_data[sid]["gpas"].append(entry.get("semester_gpa", 0))
        for subj in entry["subjects"]:
            student_sem_data[sid]["attendances"].append(subj.get("attendance_percentage", 0))

    analytics = []

    for student_id, sem_data in student_sem_data.items():
        meta = student_meta.get(student_id)
        if not meta:
            continue  # skip if no metadata available

        try:
            input_dict = {
                "10th Percentage": meta.get("tenth_percentage"),
                "12th Percentage": meta.get("twelfth_percentage"),
                "Previous Sem CGPA": round(sum(sem_data["gpas"]) / len(sem_data["gpas"]), 2),
                "Attendance Percentage": round(sum(sem_data["attendances"]) / len(sem_data["attendances"]), 2),
                "Midterm Avg": meta.get("midterm_avg"),
                "Quiz Avg": meta.get("quiz_avg"),
                "Assignment Avg": meta.get("assignment_avg"),
                "Practical Avg": meta.get("practical_avg"),
                "Study Hours/Week": meta.get("study_hours_per_week"),
                "Extracurricular Participation": meta.get("extracurricular"),
                "Internet Usage Hours": meta.get("internet_usage_hours"),
                "Teacher Feedback Score": meta.get("teacher_feedback"),
                "Parental Education": meta.get("parental_education"),
                "Financial Support": meta.get("financial_support")
            }

            df = pd.DataFrame([input_dict])
            transformed = transformer.transform(df)
            prediction = model.predict(transformed)[0]

            analytics.append({
                "student_id": student_id,
                "name": meta.get("name"),
                "predicted_category": prediction
            })

        except Exception as e:
            print(f"Prediction error for student {student_id}: {e}")
            continue

    return render_template("teacher_analytics.html", analytics=analytics)


if __name__ == "__main__":
    import webbrowser
    import threading
    webbrowser.open_new("http://127.0.0.1:5000/")
    app.run(debug=True)
