from flask import Flask, render_template, request, redirect, url_for, session,flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mydatabase.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(10), nullable=False)

class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prime_location_name = db.Column(db.String(100), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200))
    pin_code = db.Column(db.String(10))
    max_spots = db.Column(db.Integer)

class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    status = db.Column(db.String(1), nullable=False, default='Released') 

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)
    parking_timestamp = db.Column(db.DateTime, default=datetime.now)
    leaving_timestamp = db.Column(db.DateTime)
    cost_per_hour = db.Column(db.Float)

@app.before_request
def create_tables():
    print('before first request')
    os.makedirs('instance', exist_ok=True)
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password='admin123', role='admin')
        db.session.add(admin)
        db.session.commit()

def initialize_app():
    os.makedirs('instance', exist_ok=True)
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password='admin123', role='admin')
            db.session.add(admin)
            db.session.commit()

initialize_app()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return 'User already exists.'
        user = User(username=username, password=password, role='user')
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        return 'Invalid credentials.'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if session.get('role') == 'admin':
        combine = db.session.query(ParkingSpot, ParkingLot).join(ParkingLot, ParkingSpot.lot_id == ParkingLot.id).all()
        reservations = Reservation.query.filter_by(leaving_timestamp=None).all()
        users = User.query.all()
        lots=ParkingLot.query.all()
        spots=ParkingSpot.query.all()
        res_user = db.session.query(Reservation, User)\
        .join(User, Reservation.user_id == User.id)\
        .filter(Reservation.leaving_timestamp == None)\
        .all()

        res_user_map = {res.spot_id: (res, user) for res, user in res_user}
        lot_labels = [lot.prime_location_name for lot in lots]
        lot_spot_counts = [len(ParkingSpot.query.filter_by(lot_id=lot.id).all()) for lot in lots]

        return render_template(
            'dashboard_admin.html',
            lots=lots,
            users=users,
            res_user_map=res_user_map,
            lot_labels=lot_labels,
            lot_spot_counts=lot_spot_counts
        )
    elif session.get('role') == 'user':
        lots = ParkingLot.query.all()
        user = User.query.get(session['user_id'])
        return render_template('dashboard_user.html', lots=lots,user=user)
    return redirect(url_for('login'))


@app.route('/add_lot', methods=['POST'])
def add_lot():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    lot = ParkingLot(
        prime_location_name=request.form['location'],
        price_per_hour=float(request.form['price']),
        address=request.form['address'],
        pin_code=request.form['pincode'],
        max_spots=int(request.form['max_spots'])
    )
    db.session.add(lot)
    db.session.commit()
    for _ in range(lot.max_spots):
        db.session.add(ParkingSpot(lot_id=lot.id, status='Released'))
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_lot/<int:lot_id>', methods=['POST'])
def delete_lot(lot_id):
    if session.get('role')!='admin':
        return redirect(url_for('login'))

    lot = ParkingLot.query.get(lot_id)
    if not lot:
        flash('Lot not found.')
        return redirect(url_for('dashboard'))

    active_reservations = Reservation.query \
        .join(ParkingSpot) \
        .filter(ParkingSpot.lot_id == lot_id, Reservation.leaving_timestamp == None).count()

    if active_reservations > 0:
        flash('Cannot delete lot. Active reservations exist.','warning')
        return redirect(url_for('dashboard'))

    ParkingSpot.query.filter_by(lot_id=lot_id).delete()
    db.session.delete(lot)
    db.session.commit()

    flash('Parking lot deleted successfully.')
    return redirect(url_for('dashboard'))

@app.route('/spot_status')
def spot_status():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    combine = db.session.query(ParkingSpot, ParkingLot).join(ParkingLot, ParkingSpot.lot_id == ParkingLot.id).all()
    reservations = Reservation.query.filter_by(leaving_timestamp=None).all()

    user_ids = [r.user_id for r in reservations]
    users = User.query.filter(User.id.in_(user_ids)).all()

    res_user_map = {}
    for r in reservations:
        user = next((u for u in users if u.id == r.user_id), None)
        if user:
            res_user_map[r.spot_id] = (r, user)

    return render_template('spot_status.html', combine=combine, res_user_map=res_user_map)



@app.route('/users')
def view_users():
    if session.get('role') != 'admin':
        flash('Access denied.')
        return redirect(url_for('dashboard'))

    users = User.query.all()
    return render_template('users_list.html', users=users)



@app.route('/book/<int:lot_id>', methods=['POST'])
def book_spot(lot_id):
    if session.get('role') != 'user': return redirect(url_for('login'))
    lot = ParkingLot.query.get(lot_id)
    spot = ParkingSpot.query.filter_by(lot_id=lot_id, status='Released').first()
    if not spot:
        return 'No available spots.',spot
    reservation = Reservation(user_id=session['user_id'], spot_id=spot.id,
                              cost_per_hour=lot.price_per_hour)
    spot.status = 'Occupied'
    db.session.add(reservation)
    db.session.commit()
    return redirect(url_for('my_reservations'))

@app.route('/release/<int:reservation_id>', methods=['POST'])
def release_spot(reservation_id):
    reservation = Reservation.query.get(reservation_id)
    if reservation.user_id != session.get('user_id') or reservation.leaving_timestamp:
        return 'Not allowed.'
    reservation.leaving_timestamp = datetime.now()
    duration = (reservation.leaving_timestamp - reservation.parking_timestamp).total_seconds() / 3600
    spot = ParkingSpot.query.get(reservation.spot_id)
    spot.status = 'Released'
    db.session.commit()
    return redirect(url_for('my_reservations'))

@app.route('/my_reservations')
def my_reservations():
    if session.get('role') != 'user': return redirect(url_for('login'))
    reservations = Reservation.query.filter_by(user_id=session['user_id']).all()
    return render_template('my_reservations.html', reservations=reservations)

if __name__ == '__main__':
    app.run(debug=True)
