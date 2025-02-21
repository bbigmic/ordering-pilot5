from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort, send_from_directory, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, func
from flask_migrate import Migrate
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import pytz
import qrcode
import io
from dotenv import load_dotenv
from PIL import Image
from functools import wraps  # Dodaj ten import na początku pliku
from flask_login import UserMixin
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash



load_dotenv()
app = Flask(__name__)
# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("SECRET_KEY", "defaultsecretkey")
db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.config['UPLOAD_FOLDER'] = '/var/data/images'


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"  # Przekierowanie na stronę logowania

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Zalogowano pomyślnie", "success")
            return redirect(url_for('admin_panel')) if user.is_admin else redirect(url_for('waiter_view'))
        else:
            flash("Błędne dane logowania", "danger")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Wylogowano", "info")
    return redirect(url_for('admin_panel'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        is_admin = 'is_admin' in request.form
        is_employee = 'is_employee' in request.form

        new_user = User(username=username, password=password, is_admin=is_admin, is_employee=is_employee)
        db.session.add(new_user)
        db.session.commit()

        flash("Dodano nowego użytkownika", "success")
        return redirect(url_for('admin_panel'))

    return render_template('register.html')

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("Brak uprawnień do panelu administratora", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def employee_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin or current_user.is_employee):
            flash("Brak uprawnień", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function



# Funkcja pomocnicza do generowania QR kodów
def generate_qr_code(link):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img


# Modele bazy danych
class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qr_code = db.Column(db.String(100), unique=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Administrator
    is_employee = db.Column(db.Boolean, default=False)  # Pracownik (kelner/kuchnia)


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(500))
    price = db.Column(db.Float)
    customizable = db.Column(db.Boolean, default=False)
    contains_alcohol = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50))
    image_filename = db.Column(db.String(500))
    display_date = db.Column(db.Date, nullable=True)
    available = db.Column(db.Boolean, default=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'))
    status = db.Column(db.String(50), default='Pending')
    total_price = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_items = db.relationship('OrderItem', backref='order', lazy=True)
    call_waiter = db.Column(db.Boolean, default=False)
    last_call_time = db.Column(db.DateTime, nullable=True)
    request_bill = db.Column(db.Boolean, default=False)  # Nowe pole do prośby o rachunek
    bill_payment_method = db.Column(db.String(50), nullable=True)
    order_number = db.Column(db.Integer)
    tip = db.Column(db.Float, nullable=True)  # Nowe pole na napiwek
    nip = db.Column(db.String(15), nullable=True)  # Nowe pole na NIP
    estimated_completion_time = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def generate_order_number():
        # Definiujemy strefę czasową
        timezone = pytz.timezone('Europe/Warsaw')
        today = datetime.now(timezone).date()

        # Znalezienie maksymalnego numeru zamówienia dla bieżącego dnia
        last_order_number = db.session.query(func.max(Order.order_number)).filter(
            func.date(Order.created_at) == today
        ).scalar()

        # Jeśli brak zamówień na dzisiejszy dzień, zaczynamy od 1; w przeciwnym razie zwiększamy numer
        return 1 if last_order_number is None else last_order_number + 1

# Event do ustawienia order_number dla nowego zamówienia
@event.listens_for(Order, 'before_insert')
def set_order_number(mapper, connection, target):
    target.order_number = Order.generate_order_number()


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    quantity = db.Column(db.Integer)
    customization = db.Column(db.String(200))
    takeaway = db.Column(db.Boolean, default=False)
    menu_item = db.relationship('MenuItem')

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    start_date = db.Column(db.Date, nullable=False)  # Początek wydarzenia
    end_date = db.Column(db.Date, nullable=False)    # Koniec wydarzenia
    image = db.Column(db.String(200), nullable=True)  # Ścieżka do obrazu
    display_title = db.Column(db.Boolean, default=True)  # Nowe pole
    display_description = db.Column(db.Boolean, default=True)  # Nowe pole

class Popup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # Nowe pole

# @app.route("/")
# def index():
#     return "Hello, Vercel!"

@app.route('/')
def home():
    today = datetime.now().date()


    # Pobieramy wydarzenia w kolejności rozpoczęcia
    events = Event.query.filter(Event.end_date >= today).order_by(Event.start_date.asc()).all()

    # Jeśli mamy co najmniej jedno wydarzenie, ustawiamy je jako "upcoming_event"
    upcoming_event = events[0] if events else None

    # Jeśli mamy więcej niż jedno wydarzenie, ustawiamy drugie jako "next_event"
    next_event = events[1] if len(events) > 1 else None

    return render_template('home.html', upcoming_event=upcoming_event, next_event=next_event, today=today)


@app.route('/admin/add_popup', methods=['POST'])
@login_required
@admin_required
def add_popup():
    if 'popup_image' not in request.files:
        flash('Nie wybrano pliku', 'danger')
        return redirect(url_for('admin_add_popup'))
    
    file = request.files['popup_image']
    if file.filename == '':
        flash('Nie wybrano pliku', 'danger')
        return redirect(url_for('admin_add_popup'))
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Usuń istniejący pop-up, jeśli jest
        Popup.query.delete()
        new_popup = Popup(image_filename=filename)
        db.session.add(new_popup)
        db.session.commit()

        flash('Pop-up został dodany.', 'success')
        return redirect(url_for('admin_add_popup'))

@app.route('/admin/popups')
@login_required
@admin_required
def admin_add_popup():
    popup = Popup.query.first()
    return render_template('admin_popups.html', 
                           popup_image=popup.image_filename if popup else None, 
                           is_active=popup.is_active if popup else False)

@app.route('/popup_image')
def popup_image():
    popup = Popup.query.first()
    if popup:
        return jsonify({
            "image_url": url_for('uploaded_file', filename=popup.image_filename),
            "is_active": popup.is_active
        })
    return jsonify({"image_url": None, "is_active": False})


@app.route('/admin/toggle_popup', methods=['POST'])
@login_required
@admin_required
def toggle_popup():
    popup = Popup.query.first()
    if popup:
        popup.is_active = not popup.is_active
        db.session.commit()
        flash('Stan pop-upu został zmieniony.', 'success')
    else:
        flash('Brak pop-upu do zmiany stanu.', 'danger')
    return redirect(url_for('admin_add_popup'))


# Widok głównego menu dla klientów
@app.route('/menu/<int:table_id>')
def menu(table_id):
    # Pobierz liczbę stolików w bazie danych
    total_tables = Table.query.count()

    # Sprawdź, czy numer stolika mieści się w aktualnym zakresie
    if table_id < 1 or table_id > total_tables:
        abort(404)  # Zwraca stronę błędu 404, gdy stolik nie istnieje


    # Aktualna godzina w strefie czasowej UTC+1
    timezone = pytz.timezone('Europe/Warsaw')
    current_time = datetime.now(timezone)

    categories = {
        "Lunch Dnia": MenuItem.query.filter_by(category="Lunch dnia").all(),
        "Deser Dnia": MenuItem.query.filter_by(category="Deser dnia").all(),
        "Przystawki": MenuItem.query.filter_by(category="Przystawki").all(),
        "Śniadania": MenuItem.query.filter_by(category="Śniadania").all(),
        "Kanapki": MenuItem.query.filter_by(category="Kanapki").all(),
        "Zupy": MenuItem.query.filter_by(category="Zupy").all(),
        "Bowle": MenuItem.query.filter_by(category="Bowle").all(),
        "Dania główne": MenuItem.query.filter_by(category="Dania główne").all(),
        "Dania dla dzieci": MenuItem.query.filter_by(category="Dania dla dzieci").all(),
        "Sałatki": MenuItem.query.filter_by(category="Sałatki").all(),
        "Desery": MenuItem.query.filter_by(category="Desery").all(),
        "Napoje Ciepłe": MenuItem.query.filter_by(category="Napoje ciepłe").all(),
        "Napoje Zimne": MenuItem.query.filter_by(category="Napoje zimne").all(),
        "Napoje Specjalne": MenuItem.query.filter_by(category="Napoje specjalne").all(),
        "Alkohole": MenuItem.query.filter_by(category="Alkohole").all()
    }
    return render_template('menu.html', categories=categories, table_id=table_id, current_time=current_time)



@app.route('/check_new_orders', methods=['GET'])
def check_new_orders():
    try:
        timezone = pytz.timezone('Europe/Warsaw')
        new_orders = Order.query.filter_by(status="Pending").all()
        
        orders = [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "table_id": order.table_id,
                "status": order.status,
                "total_price": order.total_price,
                "order_time": order.created_at.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M"),
                "items": [
                    {
                        "name": item.menu_item.name,
                        "quantity": item.quantity,
                        "price": item.menu_item.price,
                        "customization": item.customization,
                        "takeaway": item.takeaway
                    }
                    for item in order.order_items
                ]
            }
            for order in new_orders
        ]
        
        print(f"Przetworzone zamówienia: {orders}")  # Dodatkowe logowanie do debugowania
        return jsonify(orders)

    except Exception as e:
        print(f"Błąd podczas pobierania zamówień: {e}")
        return jsonify({"error": "Wystąpił błąd podczas pobierania zamówień"}), 500

@app.route('/kitchen_view')
@login_required
@employee_required
def kitchen_view():
    # Wyświetl widok kuchni
    return render_template('kitchen_view.html')


@app.route('/check_accepted_orders', methods=['GET'])
def check_accepted_orders():
    try:
        timezone = pytz.timezone('Europe/Warsaw')
        accepted_orders = Order.query.filter_by(status="Accepted").all()

        orders = [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "table_id": order.table_id,
                "status": order.status,
                "total_price": order.total_price,
                "order_time": order.created_at.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M"),
                "items": [
                    {
                        "name": item.menu_item.name,
                        "quantity": item.quantity,
                        "price": item.menu_item.price,
                        "customization": item.customization,
                        "takeaway": item.takeaway
                    }
                    for item in order.order_items
                ]
            }
            for order in accepted_orders
        ]

        return jsonify(orders)

    except Exception as e:
        print(f"Błąd podczas pobierania zamówień: {e}")
        return jsonify({"error": "Wystąpił błąd podczas pobierania zamówień"}), 500


@app.route('/request_bill/<int:order_id>', methods=['POST'])
def request_bill(order_id):
    data = request.json
    payment_method = data.get('payment_method')
    invoice_required = data.get('invoice_required', False)
    nip = data.get('nip') if invoice_required else None
    tip = data.get('tip', 0.0)

    order = Order.query.get_or_404(order_id)
    order.request_bill = True
    order.bill_payment_method = payment_method
    order.tip = float(tip) if tip else 0.0
    order.nip = nip
    order.last_call_time = datetime.utcnow()  # Ustawienie czasu wezwania rachunku
    db.session.commit()

    return jsonify({"status": "success", "message": "Poproszono o rachunek"})

@app.route('/call_waiter/<int:order_id>', methods=['POST'])
def call_waiter(order_id):
    order = Order.query.get_or_404(order_id)

    # Sprawdzenie, czy minęły 3 minuty od ostatniego wezwania
    if order.last_call_time and datetime.utcnow() - order.last_call_time < timedelta(minutes=3):
        return jsonify({"status": "error", "message": "Musisz poczekać zanim ponownie wezwiesz kelnera"}), 403

    # Aktualizacja wezwania kelnera
    order.call_waiter = True
    order.last_call_time = datetime.utcnow()  # Ustawienie czasu ostatniego wezwania
    db.session.commit()
    return jsonify({"status": "success", "message": "Kelner został powiadomiony."})

@app.route('/check_waiter_calls', methods=['GET'])
def check_waiter_calls():
    # Pobieramy zamówienia z aktywnym wezwaniem kelnera lub prośbą o rachunek
    orders_with_calls = Order.query.filter((Order.call_waiter == True) | (Order.request_bill == True)).all()
    
    timezone = pytz.timezone('Europe/Warsaw')

    calls = []
    for order in orders_with_calls:
        if order.call_waiter:
            calls.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "table_id": order.table_id,
                "call_type": "Wezwanie kelnera",
                "call_time": order.last_call_time.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M:%S"),
                "payment_method": None,
                "tip": None,
                "nip": None
            })
        if order.request_bill:
            calls.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "table_id": order.table_id,
                "call_type": "Prośba o rachunek",
                "call_time": order.last_call_time.replace(tzinfo=pytz.utc).astimezone(timezone).strftime("%H:%M:%S") if order.last_call_time else None,
                "payment_method": order.bill_payment_method,
                "tip": getattr(order, "tip", 0),  # Pobierz napiwek
                "nip": getattr(order, "nip", None)  # Pobierz NIP
            })

    return jsonify(calls)


@app.route('/dismiss_call/<int:order_id>', methods=['POST'])
def dismiss_call(order_id):
    order = Order.query.get_or_404(order_id)
    order.call_waiter = False
    db.session.commit()
    return jsonify({"status": "success", "message": "Powiadomienie o wezwaniu kelnera zamknięte."})

@app.route('/dismiss_bill/<int:order_id>', methods=['POST'])
def dismiss_bill(order_id):
    order = Order.query.get_or_404(order_id)
    order.request_bill = False
    order.bill_payment_method = None  # Resetujemy metodę płatności
    db.session.commit()
    return jsonify({"status": "success", "message": "Powiadomienie o prośbie o rachunek zamknięte."})

@app.route('/order', methods=['POST'])
def place_order():
    data = request.json
    table_id = data.get('table_id')

    # Sprawdź, czy table_id istnieje w tabeli 'table'
    table = Table.query.get(table_id)
    if not table:
        return jsonify({"error": "Invalid table ID"}), 400

    items = data.get('items')
    total_price = 0  # Początkowa całkowita cena zamówienia

    # Tworzymy nowe zamówienie z `table_id`
    new_order = Order(table_id=table_id, total_price=0)  # Ustawienie 0 jako początkowej wartości
    db.session.add(new_order)
    db.session.commit()

    # Dodajemy wszystkie pozycje zamówienia do tabeli OrderItem i obliczamy całkowitą cenę
    for item in items:
        menu_item = MenuItem.query.get(item['id'])
        if not menu_item:
            return jsonify({"error": f"Invalid menu item ID: {item['id']}"}), 400

        quantity = item['quantity']
        customization = item.get('customization', '')
        takeaway = item.get('takeaway', False)

        # Obliczamy cenę pojedynczej pozycji, uwzględniając opcję "Na wynos"
        item_price = menu_item.price + (2.35 if takeaway else 0)
        item_total = item_price * quantity

        # Dodajemy do całkowitej ceny
        total_price += item_total

        # Tworzymy nowy wpis w OrderItem
        order_item = OrderItem(
            order_id=new_order.id,
            menu_item_id=menu_item.id,
            quantity=quantity,
            customization=customization,
            takeaway=takeaway  # Nowe pole
        )
        db.session.add(order_item)

    # Aktualizujemy całkowitą cenę zamówienia
    new_order.total_price = total_price
    db.session.commit()

    return jsonify({'order_id': new_order.id, 'status': 'Order placed', 'total_price': total_price})




# Widok statusu zamówienia
@app.route('/order_status/<int:order_id>')
def order_status(order_id):
    order = Order.query.get_or_404(order_id)

    if order.estimated_completion_time:
        remaining_time = order.estimated_completion_time - datetime.utcnow()
        remaining_seconds = max(0, int(remaining_time.total_seconds()))
    else:
        remaining_seconds = None

    return render_template('order_status.html', order=order, remaining_seconds=remaining_seconds)




# Widok kelnera
@app.route('/waiter_view')
@login_required
@employee_required
def waiter_view():
    # Pobieranie tylko zamówień oczekujących
    active_orders = Order.query.filter(Order.status != 'Completed').all()
    
    # Strefa czasowa UTC+1 (Europe/Warsaw)
    timezone = pytz.timezone('Europe/Warsaw')
    
    # Konwersja pola `created_at` na UTC+1 dla każdego zamówienia
    for order in active_orders:
        if order.created_at:
            order.created_at = order.created_at.replace(tzinfo=pytz.utc).astimezone(timezone)
    
    return render_template('waiter_view.html', orders=active_orders)

@app.route('/order_history')
@login_required
@employee_required
def order_history():
    # Pobieranie tylko zrealizowanych zamówień
    completed_orders = Order.query.filter_by(status='Completed').all()
    return render_template('order_history.html', orders=completed_orders)


@app.route('/accept_order/<int:order_id>', methods=['POST'])
def accept_order(order_id):
    data = request.json
    realization_time = data.get('realization_time')

    if not realization_time or realization_time <= 0:
        return jsonify({"status": "error", "message": "Niepoprawny czas realizacji."}), 400

    order = Order.query.get_or_404(order_id)
    order.status = 'Accepted'
    order.estimated_completion_time = datetime.utcnow() + timedelta(minutes=realization_time)
    db.session.commit()

    return jsonify({"status": "success", "message": "Zamówienie przyjęte do realizacji."})


@app.route('/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'Completed'
    db.session.commit()
    flash("Status zamówienia został zaktualizowany.")
    return redirect(url_for('waiter_view'))


# Panel administratora
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    menu_items = MenuItem.query.all()
    return render_template('admin_panel.html', menu_items=menu_items)


# Dodawanie nowego dania
@app.route('/add_menu_item', methods=['POST'])
@login_required
@admin_required
def add_menu_item():
    name = request.form['name']
    description = request.form.get('description', '')  # Pusty ciąg, jeśli brak opisu
    price = float(request.form['price'])
    category = request.form['category']
    customizable = 'customizable' in request.form
    contains_alcohol = 'contains_alcohol' in request.form
    display_date = request.form.get('display_date')

    # Ustawiamy `display_date` na obiekt daty lub `None`
    display_date = datetime.strptime(display_date, '%Y-%m-%d').date() if display_date else None

    # Obsługa zdjęcia
    image = request.files['image']
    if image and image.filename != '':
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_filename = filename
    else:
        image_filename = None  # Brak zdjęcia

    # Tworzenie nowego dania
    new_item = MenuItem(
        name=name,
        description=description,
        price=price,
        customizable=customizable,
        category=category,
        contains_alcohol=contains_alcohol,
        image_filename=image_filename,
        display_date=display_date
    )
    
    db.session.add(new_item)
    db.session.commit()
    flash('Dodano nowe danie do menu.')
    return redirect(url_for('admin_panel'))


@app.route('/healthz')
def health_check():
    return "OK", 200

# Edycja pozycji menu
@app.route('/edit_menu_item/<int:item_id>', methods=['POST'])
def edit_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)

    item.name = request.form['name']
    item.description = request.form['description']
    item.price = float(request.form['price'])
    item.category = request.form['category']
    item.customizable = 'customizable' in request.form
    item.available = 'available' in request.form

    # Obsługa zmiany zdjęcia
    if 'image' in request.files:
        image = request.files['image']
        if image:
            # Usunięcie starego pliku zdjęcia, jeśli istnieje
            if item.image_filename:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], item.image_filename)
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            # Zapis nowego zdjęcia
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            item.image_filename = filename

    db.session.commit()
    flash('Danie zostało zaktualizowane.')
    return redirect(url_for('admin_panel'))


# Usuwanie pozycji menu
@app.route('/delete_menu_item/<int:item_id>', methods=['POST'])
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    # Usunięcie wszystkich powiązanych `OrderItem`
    OrderItem.query.filter_by(menu_item_id=item_id).delete()
    db.session.delete(item)
    db.session.commit()
    flash('Pozycja menu została usunięta.') 
    return redirect(url_for('admin_panel'))

@app.route('/admin/add_tables', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tables():
    if request.method == 'POST':
        table_count = int(request.form['table_count'])

        # Pobierz najwyższy istniejący `table_id` w bazie danych
        max_table_id = db.session.query(func.max(Table.id)).scalar() or 0

        # Dodaj nowe stoliki zaczynając od kolejnego ID
        for i in range(1, table_count + 1):
            new_table_id = max_table_id + i
            new_table = Table(
                id=new_table_id,
                qr_code=f"table_{new_table_id}",
            )
            db.session.add(new_table)

            # Generowanie linku i QR kodu
            link = url_for('menu', table_id=new_table_id, _external=True)
            img = generate_qr_code(link)

            # Zapis QR kodu do katalogu produkcyjnego
            qr_folder = app.config['UPLOAD_FOLDER']
            os.makedirs(qr_folder, exist_ok=True)  # Utwórz katalog, jeśli nie istnieje
            qr_path = os.path.join(qr_folder, f"table_{new_table_id}.png")
            img.save(qr_path)

        db.session.commit()
        flash(f'Dodano {table_count} nowe stoliki.', 'success')
        return redirect(url_for('add_tables'))

    # Pobierz wszystkie istniejące stoliki z bazy
    tables = Table.query.all()
    return render_template('admin_add_tables.html', tables=tables)

@app.route('/admin/add_events', methods=['GET', 'POST'])
@login_required
@admin_required
def add_events():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        image = request.files.get('image')
        image_filename = None
        display_title = 'display_title' in request.form  # Sprawdzamy czy checkbox został zaznaczony
        display_description = 'display_description' in request.form  # Sprawdzamy czy checkbox został zaznaczony



        if image:
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename

        new_event = Event(
            title=title,
            description=description,
            start_date=start_date,
            end_date=end_date,
            image=image_filename,
            display_title=display_title,
            display_description=display_description
        )
        db.session.add(new_event)
        db.session.commit()
        flash("Dodano nowe wydarzenie.")
        return redirect(url_for('add_events'))

    events = Event.query.order_by(Event.start_date.desc()).all()
    return render_template('admin_add_events.html', events=events)

@app.route('/delete_event/<int:event_id>', methods=['POST'])
@login_required
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.image:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], event.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    db.session.delete(event)
    db.session.commit()
    flash("Wydarzenie zostało usunięte.")
    return redirect(url_for('add_events'))

@app.route('/admin/edit_event/<int:event_id>', methods=['POST'])
@login_required
@admin_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)

    event.title = request.form['title']
    event.description = request.form['description']
    
    # Konwersja daty ze stringa na obiekt date
    event.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
    event.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()

        # Obsługa pól display_title i display_description
    event.display_title = 'display_title' in request.form
    event.display_description = 'display_description' in request.form

    # Sprawdzenie czy użytkownik dodał nowe zdjęcie
    if 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            event.image = filename  # Aktualizacja nazwy pliku w bazie

    db.session.commit()
    flash('Wydarzenie zostało zaktualizowane!', 'success')
    return redirect(url_for('add_events'))

@app.route('/o-nas')
def o_nas():
    return render_template('cards/o-nas.html')

@app.route('/imprezy-okolicznosciowe')
def imprezy_okolicznosciowe():
    return render_template('cards/imprezy-okolicznosciowe.html')

@app.route('/catering')
def catering():
    return render_template('cards/catering.html')

@app.route('/wydarzenia', methods=['GET'])
def view_events():
    events = Event.query.all()
    return render_template('cards/wydarzenia.html', events=events)

@app.route('/godziny-otwarcia')
def godziny_otwarcia():
    return render_template('cards/godziny-otwarcia.html')

@app.route('/praca')
def praca():
    return render_template('cards/praca.html')

@app.route('/kontakt')
def kontakt():
    return render_template('cards/kontakt.html')

@app.route('/regulamin')
def regulamin():
    return render_template('cards/regulamin.html')

@app.route('/polityka-prywatnosci')
def polityka_prywatnosci():
    return render_template('cards/polityka-prywatnosci.html')

@app.route('/kategoria/sniadania')
def sniadania():
    sniadania_items = MenuItem.query.filter_by(category="Śniadania", available=True).all()
    kanapki_items = MenuItem.query.filter_by(category="Kanapki", available=True).all()
    return render_template('kategoria/sniadania.html', menu_items=sniadania_items, kanapki_items=kanapki_items)

@app.route('/kategoria/bowle')
def bowle():
    bowle_items = MenuItem.query.filter_by(category="Bowle", available=True).all()
    return render_template('kategoria/bowle.html', menu_items=bowle_items)

@app.route('/kategoria/salatki')
def salatki():
    salatki_items = MenuItem.query.filter_by(category="Sałatki", available=True).all()
    return render_template('kategoria/salatki.html', menu_items=salatki_items)

@app.route('/kategoria/dania-gorace')
def dania_gorace():
    dania_gorace_items = MenuItem.query.filter_by(category="Dania główne", available=True).all()
    dania_dla_dzieci_items = MenuItem.query.filter_by(category="Dania dla dzieci", available=True).all()
    return render_template(
        'kategoria/dania-gorace.html', 
        menu_items=dania_gorace_items, 
        dania_dla_dzieci_items=dania_dla_dzieci_items
    )

@app.route('/kategoria/zupy-desery-przystawki')
def zupy_desery_przystawki():
    zupy_items = MenuItem.query.filter_by(category="Zupy", available=True).all()
    desery_items = MenuItem.query.filter_by(category="Desery", available=True).all()
    przystawki_items = MenuItem.query.filter_by(category="Przystawki", available=True).all()
    return render_template(
        'kategoria/zupy-desery-przystawki.html',
        zupy_items=zupy_items,
        desery_items=desery_items,
        przystawki_items=przystawki_items
    )


@app.route('/kategoria/napoje')
def napoje():
    napoje_cieple_items = MenuItem.query.filter_by(category="Napoje ciepłe", available=True).all()
    napoje_zimne_items = MenuItem.query.filter_by(category="Napoje zimne", available=True).all()
    napoje_specjalne_items = MenuItem.query.filter_by(category="Napoje specjalne", available=True).all()
    alkohole_items = MenuItem.query.filter_by(category="Alkohole", available=True).all()
    return render_template(
        'kategoria/napoje.html',
        napoje_cieple_items=napoje_cieple_items,
        napoje_zimne_items=napoje_zimne_items,
        napoje_specjalne_items=napoje_specjalne_items,
        alkohole_items=alkohole_items
    )

@app.route('/kategoria/zamow')
def zamow_online():
    return render_template('kategoria/zamow.html')


@app.route('/images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Inicjalizacja bazy danych i uruchomienie aplikacji
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # app.run(host='0.0.0.0', port=5000)
    app.run(debug=True, port=5001)