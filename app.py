from flask import Flask, render_template, request, redirect, url_for, flash, session
from models.entities import db, User, MenuItem, SupportTicket, Order
import random
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import os
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/helpdesk_pro'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'rand_internet_cafe_secret_key_secure'

# ----------------------------------------------------
# FILE UPLOAD CONFIGURATION FOR MENU IMAGES
# ----------------------------------------------------
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'menu')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------------------------------------------
# GMAIL SMTP CONFIGURATION FOR OTP
# ----------------------------------------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'jankoabadierfernando@gmail.com'
app.config['MAIL_PASSWORD'] = 'rsez olfg mvni cbfi'

# ----------------------------------------------------
# DATABASE INITIALIZATION
# ----------------------------------------------------
db.init_app(app)

with app.app_context():
    db.create_all()

def send_otp_email(to_email, otp):
    """Sends a real 6-digit OTP email through Gmail SMTP or falls back to dev terminal if empty."""
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"\n[DEV MODE - OTP generated for {to_email}]: {otp}\n")
        return True
        
    try:
        msg = EmailMessage()
        msg['Subject'] = 'HelpDeskPro - Password Reset OTP'
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = to_email
        msg.set_content(
            f'Hello!\n\nYour HelpDeskPro password recovery code is: {otp}\n'
            f'This verification code will expire in 10 minutes.\n\n'
            f'If you did not request this code, please ignore this email.'
        )

        with smtplib.SMTP_SSL(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
            smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


# ----------------------------------------------------
# LANDING PAGE ROUTE
# ----------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# ----------------------------------------------------
# REGISTRATION ROUTE
# ----------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not username or not email or not password or not confirm_password:
            flash("All fields are required for registration!", "warning")
            return redirect(url_for('register'))

        if not username.isalnum():
            flash("Username can only contain letters and numbers.", "danger")
            return redirect(url_for('register'))

        if len(username) < 3 or len(username) > 20:
            flash("Username must be between 3 and 20 characters long.", "warning")
            return redirect(url_for('register'))

        if password != confirm_password:
            flash("Passwords do not match! Please check again.", "danger")
            return redirect(url_for('register'))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "danger")
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash("That email address is already registered.", "danger")
            return redirect(url_for('register'))

        new_user = User(username=username, email=email, role='customer')
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully! Please sign in with your PC Station number.", "success")
        return redirect(url_for('login'))
        
    return render_template('register.html')


# ----------------------------------------------------
# CUSTOMER LOGIN ROUTE (MANDATORY STATION BINDING)
# ----------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()
        station = request.form.get('station', '').strip()

        if not username or not password:
            flash("Please enter both username and password.", "warning")
            return redirect(url_for('login'))

        if not station:
            flash("PC Station number is strictly required so staff can serve your station!", "danger")
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = getattr(user, 'role', 'customer')
            session['station'] = station if station.startswith('#') else f"#{station}"
            
            flash(f"Welcome back, {user.username}! Logged in at Station {session['station']}.", "success")
            
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.", "danger")
            return redirect(url_for('login'))

    return render_template('login.html')


# ----------------------------------------------------
# DEDICATED ADMIN LOGIN ROUTE (NO STATION REQUIRED)
# ----------------------------------------------------
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please enter both username and password.", "warning")
            return redirect(url_for('admin_login'))

        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if getattr(user, 'role', 'customer') != 'admin':
                flash("Access denied. Admin credentials required.", "danger")
                return redirect(url_for('admin_login'))

            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = 'admin'
            session['station'] = 'Admin Counter'
            
            flash(f"Welcome to Admin Control Center, {user.username}!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid admin username or password.", "danger")
            return redirect(url_for('admin_login'))

    return render_template('admin_login.html')


# ----------------------------------------------------
# CLIENT DASHBOARD HUB & ORDERING
# ----------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session.get('role') != 'customer':
        flash("Please log in first to access the station hub.", "warning")
        return redirect(url_for('login'))
        
    menu_items = MenuItem.query.all()
    return render_template('dashboard.html', menu_items=menu_items)

@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        flash("Please log in to place an order.", "warning")
        return redirect(url_for('login'))
        
    items_json = request.form.get('cart_data')
    total_amount = request.form.get('total_amount')
    
    if not items_json or not total_amount:
        flash("Your cart is empty!", "danger")
        return redirect(url_for('dashboard'))

    cart_items = json.loads(items_json)
    
    summary_parts = [f"{item['quantity']}x {item['name']} (₱{item['price'] * item['quantity']:.2f})" for item in cart_items]
    items_summary = ", ".join(summary_parts)

    new_order = Order(
        user_id=session['user_id'],
        username=session['username'],
        station=session.get('station', '#36'),
        items_summary=items_summary,
        total_amount=float(total_amount),
        status='Pending'
    )
    
    db.session.add(new_order)
    db.session.commit()
    
    flash("Order placed successfully! Staff have been notified.", "success")
    return redirect(url_for('dashboard'))


# ----------------------------------------------------
# ADMIN CONTROL CENTER & CRUD ROUTES
# ----------------------------------------------------
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Unauthorized access. Admin privileges required.", "danger")
        return redirect(url_for('admin_login'))

    menu_items = MenuItem.query.all()
    orders = Order.query.order_by(Order.id.desc()).all()
    tickets = SupportTicket.query.order_by(SupportTicket.id.desc()).all()
    
    return render_template('admin_dashboard.html', menu_items=menu_items, orders=orders, tickets=tickets)


@app.route('/admin/menu/add', methods=['POST'])
def add_menu_item():
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    name = request.form.get('name')
    category = request.form.get('category')
    price = float(request.form.get('price'))
    description = request.form.get('description')
    
    filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    new_item = MenuItem(
        name=name,
        category=category,
        price=price,
        description=description,
        image_url=filename
    )
    db.session.add(new_item)
    db.session.commit()
    flash(f'Item "{name}" added to menu successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/menu/delete/<int:item_id>', methods=['POST'])
def delete_menu_item(item_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))

    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Item removed from menu.', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/menu/edit/<int:item_id>', methods=['POST'])
def edit_menu_item(item_id):
    if session.get('role') != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin_login'))
    
    item = MenuItem.query.get_or_404(item_id)
    item.name = request.form.get('name')
    item.category = request.form.get('category')
    item.price = float(request.form.get('price'))
    item.description = request.form.get('description')
    
    file = request.files.get('image')
    if file and file.filename != '' and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = os.path.join(app.root_path, 'static', 'uploads', 'menu')
        os.makedirs(upload_folder, exist_ok=True)
        file.save(os.path.join(upload_folder, filename))
        item.image_url = filename
        
    db.session.commit()
    flash(f'Item "{item.name}" updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/orders/update/<int:order_id>/<status>', methods=['POST'])
def update_order_status(order_id, status):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
        
    order = Order.query.get_or_404(order_id)
    order.status = status
    db.session.commit()
    flash(f"Order #{order.id} status updated to {status}.", "success")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/tickets/resolve/<int:ticket_id>', methods=['POST'])
def resolve_ticket(ticket_id):
    if session.get('role') != 'admin':
        return redirect(url_for('admin_login'))
        
    ticket = SupportTicket.query.get_or_404(ticket_id)
    ticket.status = 'Resolved'
    db.session.commit()
    flash(f"Support ticket #{ticket.id} marked as resolved.", "success")
    return redirect(url_for('admin_dashboard'))


# ----------------------------------------------------
# SUPPORT TICKET SUBMISSION ROUTE
# ----------------------------------------------------
@app.route('/submit_ticket', methods=['POST'])
def submit_ticket():
    if 'user_id' not in session:
        flash("Please log in to submit a support ticket.", "warning")
        return redirect(url_for('login'))
        
    category = request.form.get('category')
    description = request.form.get('description')
    current_station = session.get('station', 'Unknown Station')
    
    new_ticket = SupportTicket(
        user_id=session['user_id'],
        username=session['username'],
        station=current_station,
        category=category,
        description=description
    )
    db.session.add(new_ticket)
    db.session.commit()
    
    flash("Support ticket submitted successfully! Staff have been notified.", "success")
    return redirect(url_for('dashboard'))


# ----------------------------------------------------
# 2-STEP OTP PASSWORD RECOVERY ROUTES
# ----------------------------------------------------
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if not user:
            flash("No account registered under that Gmail address.", "danger")
            return redirect(url_for('forgot_password'))

        otp = f"{random.randint(100000, 999999)}"
        user.otp_code = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
        db.session.commit()

        email_sent = send_otp_email(email, otp)
        
        if email_sent:
            session['reset_email'] = email
            flash("A 6-digit verification code has been sent!", "success")
            return redirect(url_for('verify_otp'))
        else:
            flash("Failed to send OTP email. Please try again.", "danger")
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'reset_email' not in session:
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        otp_entered = request.form.get('otp', '').strip()
        user = User.query.filter_by(email=session['reset_email']).first()

        if not user or user.otp_code != otp_entered or not user.otp_expiry or user.otp_expiry < datetime.utcnow():
            flash("Invalid or expired OTP code. Please check again.", "danger")
            return redirect(url_for('verify_otp'))

        session['otp_verified'] = True
        flash("OTP verified! You can now set your new password.", "success")
        return redirect(url_for('new_password'))

    return render_template('verify_otp.html')


@app.route('/new-password', methods=['GET', 'POST'])
def new_password():
    if not session.get('otp_verified') or 'reset_email' not in session:
        flash("Unauthorized access. Please enter your OTP first.", "danger")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if password != confirm_password:
            flash("Passwords do not match!", "warning")
            return redirect(url_for('new_password'))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return redirect(url_for('new_password'))

        user = User.query.filter_by(email=session['reset_email']).first()
        user.set_password(password)
        
        user.otp_code = None
        user.otp_expiry = None
        db.session.commit()

        session.pop('reset_email', None)
        session.pop('otp_verified', None)

        flash("Password successfully updated! Please sign in with your new password.", "success")
        return redirect(url_for('login'))

    return render_template('new_password.html')


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("Please log in to view settings.", "warning")
        return redirect(url_for('login'))
    return render_template('profile.html')


@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    old_pw = request.form.get('old_password')
    new_pw = request.form.get('new_password')
    confirm_pw = request.form.get('confirm_password')

    if new_pw != confirm_pw:
        flash("New passwords do not match!", "danger")
        return redirect(url_for('profile'))

    user = User.query.get(session['user_id'])
    if not user.check_password(old_pw):
        flash("Incorrect current password!", "danger")
        return redirect(url_for('profile'))

    user.set_password(new_pw)
    db.session.commit()
    flash("Password updated successfully!", "success")
    return redirect(url_for('profile'))


# ----------------------------------------------------
# LOGOUT ROUTE
# ----------------------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)