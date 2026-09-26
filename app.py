from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = "skillswap_secret"

# PostgreSQL configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'skillswap_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_PORT = os.getenv('DB_PORT', '5432')

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )
    return conn

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute(
                    'INSERT INTO users (name, email, password) VALUES (%s, %s, %s)',
                    (name, email, password)
                )
                conn.commit()
            except psycopg2.IntegrityError:
                conn.rollback()
                conn.close()
                return "Email already registered. Please login."
            cur.close()
            conn.close()

            return redirect(url_for('login'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='register')

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM users WHERE email = %s AND password = %s',
                (email, password))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user:
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                return redirect(url_for('dashboard'))
            else:
                return "Invalid email or password"
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='login')

    return render_template('login.html')
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get user's own skills
        cur.execute(
            "SELECT skill_name, skill_type FROM skills WHERE user_id = %s",
            (session["user_id"],)
        )
        user_skills = cur.fetchall()
        
        # Get search query and sorting preference
        search_query = request.args.get('search', '').strip()
        sort_by = request.args.get('sort', 'popular')  # popular, recent, trending
        
        # Get all available skills from other users (for learning/discovery)
        if search_query:
            cur.execute('''
                SELECT s.skill_name, COUNT(*) as popularity, s.skill_type, 
                       STRING_AGG(DISTINCT u.name, ', ') as offered_by_users
                FROM skills s
                JOIN users u ON s.user_id = u.id
                WHERE s.user_id != %s 
                AND s.skill_type = 'Offer'
                AND s.skill_name ILIKE %s
                GROUP BY s.skill_name, s.skill_type
                ORDER BY popularity DESC
                LIMIT 20
            ''', (session["user_id"], f"%{search_query}%"))
        else:
            # Show most popular courses if no search
            cur.execute('''
                SELECT s.skill_name, COUNT(*) as popularity, s.skill_type,
                       STRING_AGG(DISTINCT u.name, ', ') as offered_by_users
                FROM skills s
                JOIN users u ON s.user_id = u.id
                WHERE s.user_id != %s AND s.skill_type = 'Offer'
                GROUP BY s.skill_name, s.skill_type
                ORDER BY popularity DESC
                LIMIT 12
            ''', (session["user_id"],))
        
        available_skills = cur.fetchall()
        # Get latest feedback
        cur.execute('''
        SELECT f.message, f.created_at, u.name
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC
        LIMIT 5
        ''')

        feedbacks = cur.fetchall()
        print("Feedback data:", feedbacks) 
        # Get pending requests for this user
        cur.execute('''
            SELECT r.id, u.name, r.skill_name, r.course_id, r.request_type, r.status,
                   c.title as course_title
            FROM requests r
            JOIN users u ON r.from_user = u.id
            LEFT JOIN courses c ON r.course_id = c.id
            WHERE r.to_user = %s AND r.status = 'Pending'
            ORDER BY r.id DESC
            LIMIT 5
        ''', (session["user_id"],))
        pending_requests = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            'dashboard.html',
            name=session['user_name'],
            skills=user_skills,
            available_skills=available_skills,
            search_query=search_query,
            feedbacks=feedbacks,
            pending_requests=pending_requests
        )
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='dashboard')

@app.route("/matches")
def matches():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT u.id AS user_id, u.name, s.skill_name
            FROM skills s
            JOIN users u ON s.user_id = u.id
            WHERE s.skill_name IN (
                SELECT skill_name FROM skills
                WHERE user_id = %s AND skill_type = 'Want'
            )
            AND s.skill_type = 'Offer'
            AND s.user_id != %s
        ''', (session["user_id"], session["user_id"]))
        matches = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("matches.html", matches=matches)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='matches')


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Submit feedback
        if request.method == "POST":
            message = request.form["message"]

            cur.execute(
                "INSERT INTO feedback (user_id, message) VALUES (%s, %s)",
                (session["user_id"], message)
            )
            conn.commit()
            return redirect(url_for("feedback"))

        # Get all feedback with user names
        cur.execute('''
            SELECT f.message, f.created_at, u.name
            FROM feedback f
            JOIN users u ON f.user_id = u.id
            ORDER BY f.created_at DESC
        ''')

        feedbacks = cur.fetchall()

        cur.close()
        conn.close()

        return render_template("feedback.html", feedbacks=feedbacks)

    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='feedback')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/skills', methods=['GET', 'POST'])
def skills():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == 'POST':
            skill_name = request.form['skill_name']
            skill_type = request.form['skill_type']

            cur.execute(
                'INSERT INTO skills (user_id, skill_name, skill_type) VALUES (%s, %s, %s)',
                (session['user_id'], skill_name, skill_type)
            )
            conn.commit()

        cur.execute(
            'SELECT skill_name, skill_type FROM skills WHERE user_id = %s',
            (session['user_id'],)
        )
        skills_list = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('skills.html', skills=skills_list)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='skills')
    
@app.route("/add-skill", methods=["GET", "POST"])
def add_skill():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        skill_name = request.form["skill_name"]
        skill_type = request.form["skill_type"]

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO skills (user_id, skill_name, skill_type) VALUES (%s, %s, %s)",
                (session["user_id"], skill_name, skill_type)
            )
            conn.commit()
            cur.close()
            conn.close()

            return redirect(url_for("dashboard"))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_skill')

    return render_template("add_skill.html")

@app.route('/skill-requests')
def skill_requests():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Ensure skill_requests table exists
        cur.execute('''
            CREATE TABLE IF NOT EXISTS skill_requests (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                skill_name TEXT NOT NULL,
                description TEXT,
                proficiency_level TEXT,
                availability TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

        # Get all skill requests with student info
        cur.execute('''
            SELECT sr.*, u.name as student_name
            FROM skill_requests sr
            JOIN users u ON sr.student_id = u.id
            ORDER BY sr.created_at DESC
        ''')
        skill_requests_list = cur.fetchall()
        cur.close()
        conn.close()

        return render_template('skill_requests.html', skill_requests=skill_requests_list)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='skill_requests')

@app.route('/create-skill-request', methods=['GET', 'POST'])
def create_skill_request():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        skill_name = request.form['skill_name']
        description = request.form.get('description', '')
        proficiency_level = request.form.get('proficiency_level', 'beginner')
        availability = request.form.get('availability', '')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Ensure skill_requests table exists
            cur.execute('''
                CREATE TABLE IF NOT EXISTS skill_requests (
                    id SERIAL PRIMARY KEY,
                    student_id INTEGER,
                    skill_name TEXT NOT NULL,
                    description TEXT,
                    proficiency_level TEXT,
                    availability TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (student_id) REFERENCES users(id)
                )
            ''')
            conn.commit()
            
            cur.execute(
                'INSERT INTO skill_requests (student_id, skill_name, description, proficiency_level, availability) VALUES (%s, %s, %s, %s, %s)',
                (session['user_id'], skill_name, description, proficiency_level, availability)
            )
            conn.commit()
            cur.close()
            conn.close()

            return redirect(url_for('dashboard'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='create_skill_request')

    return render_template('create_skill_request.html')

@app.route('/respond-skill-request/<int:request_id>')
def respond_skill_request(request_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Ensure skill_requests table exists
        cur.execute('''
            CREATE TABLE IF NOT EXISTS skill_requests (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                skill_name TEXT NOT NULL,
                description TEXT,
                proficiency_level TEXT,
                availability TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id)
            )
        ''')
        conn.commit()

        # Get the skill request details
        cur.execute('''
            SELECT sr.*, u.name as student_name
            FROM skill_requests sr
            JOIN users u ON sr.student_id = u.id
            WHERE sr.id = %s
        ''', (request_id,))
        skill_request = cur.fetchone()

        if not skill_request:
            return "Skill request not found", 404

        # Create a direct request to the student
        cur.execute(
            'INSERT INTO requests (from_user, to_user, skill_name, request_type) VALUES (%s, %s, %s, %s)',
            (session['user_id'], skill_request['student_id'], skill_request['skill_name'], 'skill')
        )
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for('skill_requests'))
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='respond_skill_request')
@app.route("/send-request/<int:to_user>/<skill>")
def send_request(to_user, skill):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO requests (from_user, to_user, skill_name, request_type) VALUES (%s, %s, %s, %s)",
            (session["user_id"], to_user, skill, 'skill')
        )
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("matches"))
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='send_request')

@app.route("/send-upgrade-request/<int:to_user>/<skill>")
def send_upgrade_request(to_user, skill):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO requests (from_user, to_user, skill_name, request_type) VALUES (%s, %s, %s, %s)",
            (session["user_id"], to_user, skill, 'skill_upgrade')
        )
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("matches"))
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='send_upgrade_request')

@app.route("/send-course-request/<int:course_id>")
def send_course_request(course_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Get course instructor
        cur.execute("SELECT instructor_id FROM courses WHERE id = %s", (course_id,))
        course = cur.fetchone()
        if not course:
            return "Course not found", 404

        # Insert course request
        cur.execute(
            "INSERT INTO requests (from_user, to_user, course_id, request_type) VALUES (%s, %s, %s, %s)",
            (session["user_id"], course['instructor_id'], course_id, 'course')
        )
        conn.commit()
        cur.close()
        conn.close()

        flash('Classroom joined successfully! Your enrollment request has been sent.')
        return redirect(url_for("course_detail", course_id=course_id))
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='send_course_request')
@app.route("/requests")
def requests():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT r.id, u.name, r.skill_name, r.course_id, r.request_type, r.status,
                   c.title as course_title
            FROM requests r
            JOIN users u ON r.from_user = u.id
            LEFT JOIN courses c ON r.course_id = c.id
            WHERE r.to_user = %s
        ''', (session["user_id"],))
        reqs = cur.fetchall()
        cur.close()
        conn.close()

        return render_template("requests.html", requests=reqs)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='requests')

@app.route("/update-request/<int:req_id>/<action>")
def update_request(req_id, action):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if action not in ["Accepted", "Rejected"]:
        return redirect(url_for("requests"))

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE requests SET status = %s WHERE id = %s",
            (action, req_id)
        )
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("requests"))
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='update_request')
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            "SELECT name, email FROM users WHERE id = %s",
            (session["user_id"],)
        )
        user = cur.fetchone()

        cur.execute(
            "SELECT skill_name, skill_type FROM skills WHERE user_id = %s",
            (session["user_id"],)
        )
        skills = cur.fetchall()

        cur.close()
        conn.close()

        return render_template(
            "profile.html",
            user=user,
            skills=skills
        )
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='profile')

# EDUCATIONAL CONTENT ROUTES

@app.route('/courses')
def courses():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get all courses with instructor info
        cur.execute('''
            SELECT c.*, u.name as instructor_name
            FROM courses c
            JOIN users u ON c.instructor_id = u.id
            ORDER BY c.created_at DESC
        ''')
        courses_list = cur.fetchall()

        # Get categories for filter
        cur.execute('SELECT DISTINCT category FROM courses WHERE category IS NOT NULL')
        categories = [row['category'] for row in cur.fetchall()]

        cur.close()
        conn.close()

        return render_template('courses.html', courses=courses_list, categories=categories)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='courses')

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get course details
        cur.execute('''
            SELECT c.*, u.name as instructor_name
            FROM courses c
            JOIN users u ON c.instructor_id = u.id
            WHERE c.id = %s
        ''', (course_id,))
        course = cur.fetchone()

        if not course:
            return "Course not found", 404

        # Get lessons for this course
        cur.execute('''
            SELECT * FROM lessons
            WHERE course_id = %s
            ORDER BY order_index, created_at
        ''', (course_id,))
        lessons = cur.fetchall()

        # Check if current user is the instructor
        is_instructor = course['instructor_id'] == session['user_id']

        cur.close()
        conn.close()

        return render_template('course_detail.html', course=course, lessons=lessons, is_instructor=is_instructor)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='course_detail')

@app.route('/study-materials')
def study_materials():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get all study materials
        cur.execute('''
            SELECT sm.*, u.name as uploaded_by_name
            FROM study_materials sm
            JOIN users u ON sm.uploaded_by = u.id
            ORDER BY sm.created_at DESC
        ''')
        materials = cur.fetchall()

        # Get material types and categories for filters
        cur.execute('SELECT DISTINCT material_type FROM study_materials WHERE material_type IS NOT NULL')
        material_types = [row['material_type'] for row in cur.fetchall()]

        cur.execute('SELECT DISTINCT category FROM study_materials WHERE category IS NOT NULL')
        categories = [row['category'] for row in cur.fetchall()]

        cur.close()
        conn.close()

        return render_template('study_materials.html', materials=materials,
                             material_types=material_types, categories=categories)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='study_materials')

@app.route('/live-lectures')
def live_lectures():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get upcoming live lectures
        cur.execute('''
            SELECT ll.*, u.name as instructor_name
            FROM live_lectures ll
            JOIN users u ON ll.instructor_id = u.id
            WHERE ll.scheduled_time > CURRENT_TIMESTAMP
            ORDER BY ll.scheduled_time ASC
        ''')
        lectures = cur.fetchall()

        # Get categories
        cur.execute('SELECT DISTINCT category FROM live_lectures WHERE category IS NOT NULL')
        categories = [row['category'] for row in cur.fetchall()]

        cur.close()
        conn.close()

        return render_template('live_lectures.html', lectures=lectures, categories=categories)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='live_lectures')

@app.route('/projects')
def projects():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get all projects
        cur.execute('''
            SELECT p.*, u.name as created_by_name
            FROM projects p
            JOIN users u ON p.created_by = u.id
            ORDER BY p.created_at DESC
        ''')
        projects_list = cur.fetchall()

        # Get categories and difficulty levels
        cur.execute('SELECT DISTINCT category FROM projects WHERE category IS NOT NULL')
        categories = [row['category'] for row in cur.fetchall()]

        cur.execute('SELECT DISTINCT difficulty_level FROM projects WHERE difficulty_level IS NOT NULL')
        difficulty_levels = [row['difficulty_level'] for row in cur.fetchall()]

        cur.close()
        conn.close()

        return render_template('projects.html', projects=projects_list,
                             categories=categories, difficulty_levels=difficulty_levels)
    except psycopg2.OperationalError:
        return render_template('db_error.html', error_type='projects')

@app.route('/add-course', methods=['GET', 'POST'])
def add_course():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO courses (title, description, category, instructor_id) VALUES (%s, %s, %s, %s)',
                (title, description, category, session['user_id'])
            )
            conn.commit()
            cur.close()
            conn.close()

            return redirect(url_for('courses'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_course')

    return render_template('add_course.html')

@app.route('/add-lesson/<int:course_id>', methods=['GET', 'POST'])
def add_lesson(course_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        content_type = request.form['content_type']
        content_url = request.form['content_url']
        duration = request.form.get('duration', 0)
        order_index = request.form.get('order_index', 0)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO lessons (course_id, title, description, content_type, content_url, duration, order_index)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (course_id, title, description, content_type, content_url, duration, order_index)
            )
            conn.commit()
            cur.close()
            conn.close()

            flash('Lesson added successfully!')
            return redirect(url_for('course_detail', course_id=course_id))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_lesson')

    return render_template('add_lesson.html', course_id=course_id)

@app.route('/add-study-material', methods=['GET', 'POST'])
def add_study_material():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        material_type = request.form['material_type']
        category = request.form['category']
        content_url = request.form['content_url']
        author = request.form.get('author', '')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO study_materials (title, description, material_type, category, content_url, author, uploaded_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (title, description, material_type, category, content_url, author, session['user_id'])
            )
            conn.commit()
            cur.close()
            conn.close()

            flash('Study material added successfully!')
            return redirect(url_for('study_materials'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_study_material')

    return render_template('add_study_material.html')

@app.route('/add-live-lecture', methods=['GET', 'POST'])
def add_live_lecture():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        scheduled_time = request.form['scheduled_time']
        duration = request.form.get('duration', 60)
        meeting_link = request.form['meeting_link']
        category = request.form['category']
        max_participants = request.form.get('max_participants', 50)

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO live_lectures (title, description, instructor_id, scheduled_time, duration, meeting_link, category, max_participants)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (title, description, session['user_id'], scheduled_time, duration, meeting_link, category, max_participants)
            )
            conn.commit()
            cur.close()
            conn.close()

            flash('Live lecture arranged successfully!')
            return redirect(url_for('live_lectures'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_live_lecture')

    return render_template('add_live_lecture.html')

@app.route('/add-project', methods=['GET', 'POST'])
def add_project():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        difficulty_level = request.form['difficulty_level']
        estimated_time = request.form.get('estimated_time') or 0
        requirements = request.form['requirements']
        solution_url = request.form.get('solution_url', '')

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO projects (title, description, category, difficulty_level, estimated_time, requirements, solution_url, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (title, description, category, difficulty_level, estimated_time, requirements, solution_url, session['user_id'])
            )
            conn.commit()
            cur.close()
            conn.close()

            flash('Project uploaded successfully!')
            return redirect(url_for('projects'))
        except psycopg2.OperationalError:
            return render_template('db_error.html', error_type='add_project')

    return render_template('add_project.html')

def init_db():
    """Initialize database tables if they don't exist"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # USERS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        # SKILLS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS skills (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                skill_name TEXT NOT NULL,
                skill_type TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # REQUESTS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                from_user INTEGER,
                to_user INTEGER,
                skill_name TEXT,
                course_id INTEGER,
                request_type TEXT DEFAULT 'skill', -- 'skill', 'course', 'skill_upgrade'
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        ''')
        # PUBLIC SKILL REQUESTS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS skill_requests (
                id SERIAL PRIMARY KEY,
                student_id INTEGER,
                skill_name TEXT NOT NULL,
                description TEXT,
                proficiency_level TEXT, -- 'beginner', 'intermediate', 'advanced'
                availability TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id)
            )
        ''')
        # FEEDBACK TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # EDUCATIONAL CONTENT TABLES
        # COURSES TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                instructor_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instructor_id) REFERENCES users(id)
            )
        ''')

        # LESSONS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS lessons (
                id SERIAL PRIMARY KEY,
                course_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                content_type TEXT, -- 'video', 'text', 'pdf', 'link'
                content_url TEXT,
                duration INTEGER, -- in minutes
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        ''')

        # STUDY MATERIALS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS study_materials (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                material_type TEXT, -- 'book', 'article', 'project', 'thesis', 'reference'
                category TEXT,
                content_url TEXT,
                author TEXT,
                uploaded_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        ''')

        # LIVE LECTURES TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS live_lectures (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                instructor_id INTEGER,
                scheduled_time TIMESTAMP,
                duration INTEGER, -- in minutes
                meeting_link TEXT,
                category TEXT,
                max_participants INTEGER DEFAULT 50,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (instructor_id) REFERENCES users(id)
            )
        ''')

        # PROJECTS TABLE
        cur.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                difficulty_level TEXT, -- 'beginner', 'intermediate', 'advanced'
                estimated_time INTEGER, -- in hours
                requirements TEXT,
                solution_url TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')

        # Add new columns to requests table if they don't exist
        try:
            cur.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS course_id INTEGER")
            cur.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'skill'")
            cur.execute("ALTER TABLE requests ADD CONSTRAINT fk_course_id FOREIGN KEY (course_id) REFERENCES courses(id)")
        except psycopg2.Error:
            pass  # Columns might already exist

        conn.commit()
        cur.close()
        conn.close()
        print("Database tables initialized successfully!")
    except psycopg2.OperationalError as e:
        print(f" Cannot connect to PostgreSQL database!")
        print(f"Error: {e}")
        print("\n📋 Setup Instructions:")
        print("1. Install PostgreSQL from https://www.postgresql.org/download/")
        print("2. Start PostgreSQL service")
        print("3. Create a database: createdb skillswap_db")
        print("4. Update credentials in .env file")
        print("5. Run: python app.py\n")

def populate_sample_data():
    """Populate sample data if database is empty"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Check if skills table already has data
        cur.execute("SELECT COUNT(*) as count FROM skills")
        skill_count = cur.fetchone()[0]
        
        if skill_count > 0:
            print("Database already has skills. Skipping sample data population.")
            cur.close()
            conn.close()
            return

        # Check if users table has more than just test users
        cur.execute("SELECT COUNT(*) as count FROM users")
        user_count = cur.fetchone()[0]

        # Add sample users if needed
        sample_users = [
            ('Alice Johnson', 'alice@example.com', 'password123'),
            ('Bob Smith', 'bob@example.com', 'password123'),
            ('Charlie Brown', 'charlie@example.com', 'password123'),
            ('Diana Prince', 'diana@example.com', 'password123'),
            ('Eve Williams', 'eve@example.com', 'password123'),
        ]

        for name, email, password in sample_users:
            try:
                cur.execute(
                    'INSERT INTO users (name, email, password) VALUES (%s, %s, %s)',
                    (name, email, password)
                )
            except psycopg2.IntegrityError:
                conn.rollback()
                continue
        conn.commit()

        # Get all user IDs
        cur.execute("SELECT id FROM users LIMIT 10")
        user_ids = [row[0] for row in cur.fetchall()]

        if len(user_ids) < 2:
            print("Not enough users for sample data.")
            cur.close()
            conn.close()
            return

        # Add sample skills with different types
        sample_skills = [
            # Alice offers these skills
            (user_ids[0], 'Python', 'Offer'),
            (user_ids[0], 'Web Development', 'Offer'),
            
            # Bob offers these skills
            (user_ids[1], 'JavaScript', 'Offer'),
            (user_ids[1], 'Guitar', 'Offer'),
            
            # Charlie offers these skills
            (user_ids[2], 'Spanish', 'Offer'),
            (user_ids[2], 'Photography', 'Offer'),
            
            # Diana offers these skills
            (user_ids[3], 'Machine Learning', 'Offer'),
            (user_ids[3], 'Data Science', 'Offer'),
            
            # Eve offers these skills
            (user_ids[4], 'French', 'Offer'),
            (user_ids[4], 'Graphic Design', 'Offer'),
            
            # Some Want skills for variety
            (user_ids[0], 'Guitar', 'Want'),
            (user_ids[1], 'Spanish', 'Want'),
            (user_ids[2], 'Python', 'Want'),
            (user_ids[3], 'Photography', 'Want'),
            (user_ids[4], 'Web Development', 'Want'),
        ]

        for user_id, skill_name, skill_type in sample_skills:
            try:
                cur.execute(
                    'INSERT INTO skills (user_id, skill_name, skill_type) VALUES (%s, %s, %s)',
                    (user_id, skill_name, skill_type)
                )
            except psycopg2.IntegrityError:
                conn.rollback()
                continue

        conn.commit()
        cur.close()
        conn.close()
        print("\n Sample data populated successfully!")
        print("   - 5 sample users created")
        print("   - 15 sample skills added (10 Offer, 5 Want)")
        print("   - You can now see skills in the 'Discover Skills' section")
        print("   - Try searching for: Python, Guitar, Spanish, Photography, etc.\n")

    except Exception as e:
        print(f"Error populating sample data: {e}\n")

if __name__ == "__main__":
    # Try to initialize database, but allow app to run even if it fails
    try:
        init_db()
        populate_sample_data()
    except psycopg2.OperationalError:
        print("\n  WARNING: Database connection failed on startup.")
        print("The app will run, but database-dependent features won't work.")
        print("Please start PostgreSQL and refresh the page.\n")
    
    app.run(debug=True)
