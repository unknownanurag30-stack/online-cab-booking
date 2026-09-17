import os
from flask import Flask, render_template, request, jsonify
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)


def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQLHOST", "localhost"),
            user=os.getenv("MYSQLUSER", "root"),
            password=os.getenv("MYSQLPASSWORD", ""),
            database=os.getenv("MYSQLDATABASE", "cab_rental_db"),
            port=int(os.getenv("MYSQLPORT", "3306"))
        )
        return connection
    except Error as e:
        print("Database connection error:", e)
        return None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/cabs")
def cabs():
    return render_template("cabs.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/login-page")
def login_page():
    return render_template("login.html")


@app.route("/tours")
def tours():
    return render_template("tours.html")


@app.route("/booking")
def booking():
    return render_template("booking.html")


@app.route("/daily-rental")
def daily_rental():
    return render_template("daily_rental.html")


@app.route("/my-bookings")
def my_bookings():
    return render_template("my_bookings.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/api/vehicles", methods=["GET"])
def get_vehicles():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Could not connect to database"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT vehicle_id, vehicle_number, vehicle_model, vehicle_type,
                   seating_capacity, price_per_km, availability,
                   total_cars, available_cars
            FROM vehicles ORDER BY vehicle_id
        """)
        return jsonify(cursor.fetchall())
    except Error as e:
        print("Vehicle fetch error:", e)
        return jsonify({"success": False, "message": "Unable to fetch vehicles"}), 500
    finally:
        cursor.close()
        connection.close()


@app.route("/api/daily-rental-vehicles", methods=["GET"])
def daily_rental_vehicles():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    if not start_date or not end_date:
        return jsonify({"success": False, "error": "Start date and end date are required"}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "error": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT fc.fleet_car_id, fc.vehicle_id, fc.vehicle_number,
                   v.vehicle_model, v.vehicle_type, v.seating_capacity,
                   v.daily_car_rate, v.daily_driver_rate,
                   d.driver_id, d.driver_name, d.phone
            FROM fleet_cars fc
            JOIN vehicles v ON fc.vehicle_id = v.vehicle_id
            JOIN drivers d ON fc.driver_id = d.driver_id
            WHERE fc.fleet_car_id NOT IN (
                SELECT dr.fleet_car_id FROM daily_rentals dr
                WHERE dr.booking_status IN ('Pending','Confirmed')
                  AND dr.start_date <= %s AND dr.end_date >= %s
            )
            ORDER BY fc.fleet_car_id
        """, (end_date, start_date))
        return jsonify(cursor.fetchall())
    except Error as e:
        print("Daily rental vehicle fetch error:", e)
        return jsonify({"success": False, "error": "Unable to fetch available cars"}), 500
    finally:
        cursor.close()
        connection.close()


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not name or not phone or not email or not password:
        return jsonify({"success": False, "message": "All fields are required"}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT customer_id FROM customers WHERE email=%s OR phone=%s", (email, phone))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Email or phone already registered"}), 409
        cursor.execute("INSERT INTO customers (name, phone, email, password) VALUES (%s,%s,%s,%s)", (name, phone, email, password))
        connection.commit()
        return jsonify({"success": True, "message": "Account created successfully"}), 201
    except Error as e:
        connection.rollback()
        print("Registration error:", e)
        return jsonify({"success": False, "message": "Unable to create account"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT customer_id, name, phone, email FROM customers WHERE email=%s AND password=%s", (email, password))
        customer = cursor.fetchone()
        if not customer:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
        return jsonify({"success": True, "customer": customer})
    except Error as e:
        print("Login error:", e)
        return jsonify({"success": False, "message": "Unable to login"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/tour-packages", methods=["GET"])
def get_tour_packages():
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM tour_packages ORDER BY package_id")
        return jsonify(cursor.fetchall())
    except Error as e:
        print("Tour package fetch error:", e)
        return jsonify({"success": False, "message": "Unable to fetch tour packages"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/book-cab", methods=["POST"])
def book_cab():
    data = request.get_json() or {}
    required = ["customer_id", "vehicle_id", "pickup_location", "destination", "booking_date", "distance_km"]
    if any(data.get(k) in (None, "") for k in required):
        return jsonify({"success": False, "message": "All booking fields are required"}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT price_per_km, available_cars FROM vehicles WHERE vehicle_id=%s FOR UPDATE", (data["vehicle_id"],))
        vehicle = cursor.fetchone()
        if not vehicle:
            connection.rollback(); return jsonify({"success": False, "message": "Vehicle not found"}), 404
        if int(vehicle["available_cars"]) <= 0:
            connection.rollback(); return jsonify({"success": False, "message": "Vehicle currently unavailable"}), 409
        total = float(data["distance_km"]) * float(vehicle["price_per_km"])
        cursor.execute("""
            INSERT INTO cab_bookings
            (customer_id, vehicle_id, pickup_location, destination, booking_date, distance_km, total_amount)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (data["customer_id"], data["vehicle_id"], data["pickup_location"], data["destination"], data["booking_date"], data["distance_km"], total))
        cursor.execute("UPDATE vehicles SET available_cars=available_cars-1, availability=(available_cars-1)>0 WHERE vehicle_id=%s", (data["vehicle_id"],))
        connection.commit()
        return jsonify({"success": True, "message": "Cab booked successfully", "booking_id": cursor.lastrowid, "total_amount": total}), 201
    except Error as e:
        connection.rollback(); print("Cab booking error:", e)
        return jsonify({"success": False, "message": "Unable to book cab"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/book-tour", methods=["POST"])
def book_tour():
    data = request.get_json() or {}
    required = ["customer_id", "package_id", "booking_date", "number_of_people"]
    if any(data.get(k) in (None, "") for k in required):
        return jsonify({"success": False, "message": "All tour booking fields are required"}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT package_price, availability FROM tour_packages WHERE package_id=%s", (data["package_id"],))
        package = cursor.fetchone()
        if not package or not package["availability"]:
            return jsonify({"success": False, "message": "Tour package unavailable"}), 409
        total = float(data["number_of_people"]) * float(package["package_price"])
        cursor.execute("""
            INSERT INTO tour_bookings (customer_id, package_id, booking_date, number_of_people, total_amount)
            VALUES (%s,%s,%s,%s,%s)
        """, (data["customer_id"], data["package_id"], data["booking_date"], data["number_of_people"], total))
        connection.commit()
        return jsonify({"success": True, "message": "Tour booked successfully", "tour_booking_id": cursor.lastrowid, "total_amount": total}), 201
    except Error as e:
        connection.rollback(); print("Tour booking error:", e)
        return jsonify({"success": False, "message": "Unable to book tour"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/book-daily-rental", methods=["POST"])
def book_daily_rental():
    data = request.get_json() or {}
    required = ["customer_id", "fleet_car_id", "start_date", "end_date"]
    if any(data.get(k) in (None, "") for k in required):
        return jsonify({"success": False, "message": "Customer, car and rental dates are required"}), 400
    connection = get_db_connection()
    if connection is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("SELECT fleet_car_id, vehicle_id FROM fleet_cars WHERE fleet_car_id=%s FOR UPDATE", (data["fleet_car_id"],))
        car = cursor.fetchone()
        if not car:
            connection.rollback(); return jsonify({"success": False, "message": "Car not found"}), 404
        cursor.execute("""
            SELECT daily_rental_id FROM daily_rentals
            WHERE fleet_car_id=%s AND booking_status IN ('Pending','Confirmed')
              AND start_date <= %s AND end_date >= %s LIMIT 1
        """, (data["fleet_car_id"], data["end_date"], data["start_date"]))
        if cursor.fetchone():
            connection.rollback(); return jsonify({"success": False, "message": "Car is already booked for these dates"}), 409
        cursor.execute("SELECT daily_car_rate, daily_driver_rate FROM vehicles WHERE vehicle_id=%s", (car["vehicle_id"],))
        rates = cursor.fetchone()
        from datetime import date
        start = date.fromisoformat(data["start_date"]); end = date.fromisoformat(data["end_date"])
        days = (end - start).days + 1
        if days <= 0:
            connection.rollback(); return jsonify({"success": False, "message": "End date must be on or after start date"}), 400
        total = days * (float(rates["daily_car_rate"]) + float(rates["daily_driver_rate"]))
        cursor.execute("""
            INSERT INTO daily_rentals
            (customer_id, fleet_car_id, start_date, end_date, rental_days,
             car_daily_rate, driver_daily_rate, total_amount, fuel_responsibility, booking_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Customer','Confirmed')
        """, (data["customer_id"], data["fleet_car_id"], data["start_date"], data["end_date"], days, rates["daily_car_rate"], rates["daily_driver_rate"], total))
        connection.commit()
        return jsonify({"success": True, "message": "Daily rental booked successfully", "daily_rental_id": cursor.lastrowid, "rental_days": days, "total_amount": total}), 201
    except (Error, ValueError) as e:
        connection.rollback(); print("Daily rental booking error:", e)
        return jsonify({"success": False, "message": "Unable to book daily rental"}), 500
    finally:
        cursor.close(); connection.close()


@app.route("/api/my-cab-bookings/<int:customer_id>", methods=["GET"])
def my_cab_bookings(customer_id):
    connection = get_db_connection()
    if connection is None: return jsonify([]), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT cb.*, v.vehicle_model, v.vehicle_number, d.driver_name, d.phone AS driver_phone
            FROM cab_bookings cb
            JOIN vehicles v ON cb.vehicle_id=v.vehicle_id
            LEFT JOIN drivers d ON cb.driver_id=d.driver_id
            WHERE cb.customer_id=%s ORDER BY cb.created_at DESC
        """, (customer_id,))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close(); connection.close()


@app.route("/api/my-tour-bookings/<int:customer_id>", methods=["GET"])
def my_tour_bookings(customer_id):
    connection = get_db_connection()
    if connection is None: return jsonify([]), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT tb.*, tp.package_name, tp.destination, tp.duration_days
            FROM tour_bookings tb JOIN tour_packages tp ON tb.package_id=tp.package_id
            WHERE tb.customer_id=%s ORDER BY tb.created_at DESC
        """, (customer_id,))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close(); connection.close()


@app.route("/api/my-daily-rentals/<int:customer_id>", methods=["GET"])
def my_daily_rentals(customer_id):
    connection = get_db_connection()
    if connection is None: return jsonify([]), 500
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT dr.*, fc.vehicle_number, v.vehicle_model, d.driver_name, d.phone AS driver_phone
            FROM daily_rentals dr
            JOIN fleet_cars fc ON dr.fleet_car_id=fc.fleet_car_id
            JOIN vehicles v ON fc.vehicle_id=v.vehicle_id
            JOIN drivers d ON fc.driver_id=d.driver_id
            WHERE dr.customer_id=%s ORDER BY dr.created_at DESC
        """, (customer_id,))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close(); connection.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
