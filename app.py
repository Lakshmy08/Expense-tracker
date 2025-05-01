from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import func
from models import db, User

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===================== MODELS =====================

# ===================== LOGIN MANAGER =====================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===================== ROUTES =====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    return render_template('landing.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("User already exists", "danger")
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("Signup successful! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user:
            # First, try checking the password with the current hash method (pbkdf2:sha256)
            if check_password_hash(user.password, password):
                login_user(user)
                flash("Login successful!", "success")
                return redirect(url_for('home'))

            # If the password hash method is outdated (sha256), rehash it and update the user
            if user.password.startswith('sha256'):
                # Rehash the password with pbkdf2:sha256 and update in the database
                new_hash = generate_password_hash(password, method='pbkdf2:sha256')
                user.password = new_hash
                db.session.commit()  # Update the user's password in the database
                login_user(user)
                flash("Login successful! Your password was updated.", "success")
                return redirect(url_for('home'))

        flash("Invalid username or password", "danger")
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/home')
@login_required
def home():
    category = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    search = request.args.get('search')

    query = Expense.query.filter_by(user_id=current_user.id)

    if category:
        query = query.filter_by(category=category)
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Expense.date >= start)
        except ValueError:
            flash("Invalid start date format", "danger")
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Expense.date <= end)
        except ValueError:
            flash("Invalid end date format", "danger")
    if search:
        query = query.filter(Expense.description.ilike(f'%{search}%'))

    expenses = query.all()
    total = sum(exp.amount for exp in expenses)

    now = datetime.now()
    monthly_total = sum(
        exp.amount for exp in expenses
        if exp.date.month == now.month and exp.date.year == now.year
    )

    category_totals = {}
    for exp in expenses:
        category_totals[exp.category] = category_totals.get(exp.category, 0) + exp.amount

    return render_template(
        'home.html', expenses=expenses, total=total,
        category_totals=category_totals, category=category,
        start_date=start_date, end_date=end_date,
        search=search, monthly_total=monthly_total
    )

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            description = request.form['description']
            date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            category = request.form['category']
            new_expense = Expense(
                amount=amount, description=description,
                date=date, category=category, user_id=current_user.id
            )
            db.session.add(new_expense)
            db.session.commit()
            flash("Expense added!", "success")
            return redirect(url_for('home'))
        except (KeyError, ValueError):
            flash("Invalid form data", "danger")
    return render_template('add_expense.html')

@app.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.user_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        try:
            expense.amount = float(request.form['amount'])
            expense.description = request.form['description']
            expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            expense.category = request.form['category']
            db.session.commit()
            flash("Expense updated.", "success")
            return redirect(url_for('home'))
        except ValueError:
            flash("Invalid date format", "danger")
    return render_template('edit_expense.html', expense=expense)

@app.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.user_id != current_user.id:
        abort(403)
    db.session.delete(expense)
    db.session.commit()
    flash("Expense deleted.", "success")
    return redirect(url_for('home'))

@app.route('/chart')
@login_required
def chart():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    category_totals = {}
    for exp in expenses:
        category_totals[exp.category] = category_totals.get(exp.category, 0) + exp.amount
    total = sum(category_totals.values())
    return render_template('chart.html', category_totals=category_totals, total=total)

@app.route('/monthly_expenses')
@login_required
def monthly_expenses():
    selected_month = request.args.get('month')
    available_months = db.session.query(
        func.strftime('%Y-%m', Expense.date)
    ).filter_by(user_id=current_user.id).distinct().all()
    available_months = [m[0] for m in available_months]

    monthly_totals = []
    category_totals_by_month = {}

    if selected_month:
        total = db.session.query(
            func.strftime('%Y-%m', Expense.date).label('month'),
            func.sum(Expense.amount).label('total')
        ).filter(
            Expense.user_id == current_user.id,
            func.strftime('%Y-%m', Expense.date) == selected_month
        ).group_by('month').first()

        if total:
            monthly_totals = [total]
            categories = db.session.query(
                Expense.category,
                func.sum(Expense.amount).label('total')
            ).filter(
                func.strftime('%Y-%m', Expense.date) == selected_month,
                Expense.user_id == current_user.id
            ).group_by(Expense.category).all()

            category_totals_by_month[selected_month] = categories

    return render_template(
        'monthly_expenses.html', monthly_totals=monthly_totals,
        category_totals_by_month=category_totals_by_month,
        available_months=available_months,
        selected_month=selected_month
    )

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/reminders')
@login_required
def reminders():
    from sqlalchemy import and_
    today = datetime.today()

    # Filters from query parameters
    status = request.args.get('status')
    search = request.args.get('search', '')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base query
    query = Reminder.query.filter_by(user_id=current_user.id)

    # Apply search filter
    if search:
        query = query.filter(Reminder.title.ilike(f'%{search}%'))

    # Apply status filter
    if status == 'paid':
        query = query.filter(Reminder.is_paid.is_(True))
    elif status == 'unpaid':
        query = query.filter(Reminder.is_paid.is_(False))

    # Apply date range filter
    if start_date:
        query = query.filter(Reminder.due_date >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(Reminder.due_date <= datetime.strptime(end_date, '%Y-%m-%d'))

    reminders = query.order_by(Reminder.due_date).all()

    # For notification: upcoming unpaid bills (next 2 days)
    upcoming_reminders = Reminder.query.filter_by(user_id=current_user.id)\
        .filter(Reminder.due_date <= today + timedelta(days=2), Reminder.is_paid.is_(False))\
        .order_by(Reminder.due_date).all()

    return render_template('reminders.html', reminders=reminders, upcoming_reminders=upcoming_reminders)


@app.route('/reminders/add', methods=['POST'])
@login_required
def add_reminder():
    title = request.form['title']
    due_date = request.form['due_date']
    new_reminder = Reminder(
        title=title,
        due_date=datetime.strptime(due_date, '%Y-%m-%d'),
        user_id=current_user.id
    )
    db.session.add(new_reminder)
    db.session.commit()
    flash('Reminder added successfully.')
    return redirect(url_for('reminders'))

@app.route('/reminders/mark_paid/<int:id>', methods=['POST'])
@login_required
def mark_reminder_paid(id):
    reminder = Reminder.query.get_or_404(id)
    if reminder.user_id != current_user.id:
        abort(403)
    reminder.is_paid = True
    db.session.commit()
    return redirect(url_for('reminders'))

@app.route('/reminders/delete/<int:id>', methods=['POST'])
@login_required
def delete_reminder(id):
    reminder = Reminder.query.get_or_404(id)
    if reminder.user_id != current_user.id:
        abort(403)
    db.session.delete(reminder)
    db.session.commit()
    flash('Reminder deleted successfully.')
    return redirect(url_for('reminders'))

# ===================== RUN APP =====================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
