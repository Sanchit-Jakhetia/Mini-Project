import pandas as pd
import joblib
from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient

app = Flask(__name__)
app.secret_key = 'secret_key'

client = MongoClient("mongodb://localhost:27017/")
db = client["Academics"]
users = db["users"]

#----------------------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

#----------------------------------------------------------------------------------------
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

#----------------------------------------------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

#----------------------------------------------------------------------------------------
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

#----------------------------------------------------------------------------------------
@app.route("/dashboard_teacher")
def dashboard_teacher():
    sem1 = list(db["Semester_1"].find())
    sem2 = list(db["Semester_2"].find())
    sem3 = list(db["Semester_3"].find())

    all_students = sem1 + sem2 + sem3  # Simple union; refine if needed

    unique_ids = {s["student_id"]: s for s in all_students}.values()
    total_students = len(unique_ids)
    avg_gpa = round(sum([s["semester_gpa"] for s in unique_ids]) / total_students, 2)
    low_performers = sum(1 for s in unique_ids if s["semester_gpa"] < 6.5)

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

#----------------------------------------------------------------------------------------
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

#----------------------------------------------------------------------------------------
@app.route('/student/<int:student_id>/profile')
def student_profile(student_id):
    student_info_collection = db["Class_10th"]  
    student_data = student_info_collection.find_one({"student_id": student_id})

    if not student_data:
        return "Student profile not found.", 404

    return render_template("profile.html", student=student_data)

#----------------------------------------------------------------------------------------
@app.route('/teacher/analytics')
def teacher_analytics():
    # Fetch all relevant student data from semester collections
    sem1_data = list(db["Semester_1"].find())
    sem2_data = list(db["Semester_2"].find())
    sem3_data = list(db["Semester_3"].find())

    # Fetch metadata from Class_10th and Class_12th for each student
    tenth_data = {s["student_id"]: s for s in db["Class_10th"].find()}
    twelfth_data = {s["student_id"]: s for s in db["Class_12th"].find()}

    # Merge all semester data
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
        # Fetch the metadata for the student
        meta_10th = tenth_data.get(student_id)
        meta_12th = twelfth_data.get(student_id)

        # If metadata is missing for any student, skip them
        if not meta_10th or not meta_12th:
            continue

        # Prepare the input dictionary for the model based on the new feature set
        try:
            # Encode binary features (Yes/No as 1/0)
            remedial_classes_taken = 1 if meta_12th.get("remedial_classes_taken", "No") == "Yes" else 0
            participated_in_olympiads = 1 if meta_12th.get("participated_in_olympiads", "No") == "Yes" else 0
            extracurricular_focus = meta_12th.get("extracurricular_focus", "Sports")
            leadership_roles = 1 if meta_12th.get("leadership_roles", "No") == "Yes" else 0
            internet_access_at_home = 1 if meta_12th.get("internet_access_at_home", "No") == "Yes" else 0
            
            # Prepare the input dictionary
            input_dict = {
                "student_id": student_id,
                "study_method": meta_12th.get("study_method", "Independent"),
                "preferred_learning_style": meta_12th.get("preferred_learning_style", "Visual"),
                "participated_in_olympiads": participated_in_olympiads,
                "extracurricular_focus": extracurricular_focus,  # This needs to be one-hot encoded later
                "parental_education_level": meta_12th.get("parental_education_level", "High School"),

                "10th_percentage": meta_10th.get("tenth_percentage", 0),
                "12th_percentage": meta_12th.get("twelfth_percentage", 0),
                "math_score_10th": meta_10th.get("math_score", 0),
                "science_score_10th": meta_10th.get("science_score", 0),
                "remedial_classes_taken": remedial_classes_taken,  # Binary: 0 or 1
                "average_study_hours_per_day": meta_12th.get("study_hours_per_day", 0),
                "attendance_10th": meta_10th.get("attendance_percentage", 0),
                "attendance_12th": meta_12th.get("attendance_percentage", 0),
                "leadership_roles": leadership_roles,  # Binary: 0 or 1
                "confidence_level": meta_12th.get("confidence_level", 0),
                "motivation_level": meta_12th.get("motivation_level", 0),
                "internet_access_at_home": internet_access_at_home,  # Binary: 0 or 1

                # GPA from semester data
                "semester_1_gpa": sem_data["gpas"][0] if len(sem_data["gpas"]) > 0 else 0,
                "semester_2_gpa": sem_data["gpas"][1] if len(sem_data["gpas"]) > 1 else 0,
                "semester_3_gpa": sem_data["gpas"][2] if len(sem_data["gpas"]) > 2 else 0,

                # Additional calculated metrics
                "average_attendance_semesters": round(sum(sem_data["attendances"]) / len(sem_data["attendances"]), 2),
                "subjects_failed_total": sum(1 for subj in entry.get("subjects", []) if subj.get("failed", False)),
                "average_interest_level": meta_12th.get("average_interest_level", 0),
                "subjects_need_support_count": meta_12th.get("subjects_need_support_count", 0)
            }
            sem3 = db["Semester_3"].find_one({"student_id": student_id})
            gpa = sem3.get("semester_gpa") if sem3 else None
            # Convert the data to a DataFrame for prediction
            df = pd.DataFrame([input_dict])
            model = joblib.load("student_model.pkl")
            preprocessor = joblib.load("preprocessor.pkl")
            # Preprocess the input data
            X_processed = preprocessor.transform(df)

            # Make the prediction
            prediction = model.predict(X_processed)[0]  # Get predicted category
            
            analytics.append({
                "student_id": student_id,
                "name": meta_12th.get("name", "Unknown"),
                "sem3_gpa": gpa,
                "predicted_category": prediction
            })

        except Exception as e:
            print(f"Prediction error for student {student_id}: {e}")
            continue

    # Pass the analytics data to the template for rendering
    return render_template("teacher_analytics.html", analytics=analytics)

#----------------------------------------------------------------------------------------
@app.route("/student/recommendation/<int:student_id>")
def student_recommendation(student_id):
    student_data = db["Semester_3"].find_one({"student_id": student_id})  # Example
    return render_template("student_recommendation.html", student=student_data)

#----------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------

#----------------------------------------------------------------------------------------
if __name__ == "__main__":
    import webbrowser
    import threading
    webbrowser.open_new("http://127.0.0.1:5000/")
    app.run(debug=True)
