import os
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)

# --- DATABASE CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'abhinavsriram@2006',
    'database': 'pharmacydb'
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def get_next_id(cursor, table, col):
    cursor.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 FROM {table}")
    row = cursor.fetchone()
    return row[0] if row else 1


@app.route('/')
def home():
    return render_template('index.html')

# --- HEALTH & CONNECTION STATUS ---


@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION(), DATABASE();")
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        return jsonify({
            "status": "connected",
            "mysql_version": res[0],
            "database": res[1]
        })
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- AUTHENTICATION & USER PROFILE ---


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
        data = request.json or {}
        persona_role = data.get('persona_role')
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if persona_role:
            cursor.execute(
                "SELECT UserID, FullName, Email, Role, StaffID, Phone, CreatedAt FROM users WHERE Role = %s LIMIT 1;", (persona_role,))
            user = cursor.fetchone()
            if not user:
                # Seed fallback
                defaults = {
                    'Administrator': ('Y. Abhinav Sri Ram', 'abhinav@pharmacare.rx', 'ADM-001', '+91 98450 11223'),
                    'Pharmacist': ('P. Rajesh', 'rajesh@pharmacare.rx', 'PHARM-104', '+91 97412 33445'),
                    'Inventory Manager': ('S. Kulkarni', 'kulkarni@pharmacare.rx', 'INV-209', '+91 94481 55667')
                }
                if persona_role in defaults:
                    name, mail, sid, ph = defaults[persona_role]
                    cursor_raw = conn.cursor()
                    uid = get_next_id(cursor_raw, "users", "UserID")
                    cursor_raw.execute("INSERT IGNORE INTO users (UserID, FullName, Email, PasswordHash, Role, StaffID, Phone) VALUES (%s, %s, %s, 'pass123', %s, %s, %s);",
                                       (uid, name, mail, persona_role, sid, ph))
                    conn.commit()
                    cursor_raw.close()
                    cursor.execute(
                        "SELECT UserID, FullName, Email, Role, StaffID, Phone, CreatedAt FROM users WHERE UserID = %s;", (uid,))
                    user = cursor.fetchone()

        elif email:
            cursor.execute(
                "SELECT UserID, FullName, Email, PasswordHash, Role, StaffID, Phone, CreatedAt FROM users WHERE LOWER(Email) = %s;", (email,))
            user = cursor.fetchone()
            if not user:
                cursor.close()
                conn.close()
                return jsonify({"status": "error", "message": "Invalid email or staff account not found."}), 401

            # Simple password check (matches stored plain or demo default)
            stored_pwd = user.pop('PasswordHash', '')
            if password and password != stored_pwd and password != 'admin123' and password != 'pharm123' and password != 'inv123' and password != 'password':
                cursor.close()
                conn.close()
                return jsonify({"status": "error", "message": "Incorrect password. Please verify credentials."}), 401

        else:
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": "Email and password or persona role required."}), 400

        cursor.close()
        conn.close()

        if user:
            user['CreatedAt'] = str(user.get('CreatedAt', ''))
            return jsonify({
                "status": "success",
                "message": f"Welcome back, {user['FullName']}!",
                "user": user,
                "token": f"pharmacare-auth-{user['UserID']}"
            })
        else:
            return jsonify({"status": "error", "message": "Account could not be authenticated."}), 401

    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    try:
        data = request.json or {}
        full_name = (data.get('full_name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '').strip()
        role = data.get('role') or 'Pharmacist'
        staff_id = (data.get('staff_id') or '').strip()
        phone = (data.get('phone') or '').strip()

        if not full_name or not email or not password:
            return jsonify({"status": "error", "message": "Full Name, Email, and Password are required."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email exists
        cursor.execute(
            "SELECT UserID FROM users WHERE LOWER(Email) = %s;", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": "An account with this email already exists."}), 400

        if not staff_id:
            role_prefix = 'ADM' if role == 'Administrator' else 'PHARM' if role == 'Pharmacist' else 'INV'
            staff_id = f"{role_prefix}-{datetime.now().strftime('%M%S')}"

        new_uid = get_next_id(cursor, "users", "UserID")
        cursor.execute("""
            INSERT INTO users (UserID, FullName, Email, PasswordHash, Role, StaffID, Phone, CreatedAt)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
        """, (new_uid, full_name, email, password, role, staff_id, phone))
        conn.commit()

        cursor.close()
        conn.close()

        new_user = {
            "UserID": new_uid,
            "FullName": full_name,
            "Email": email,
            "Role": role,
            "StaffID": staff_id,
            "Phone": phone,
            "CreatedAt": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        return jsonify({
            "status": "success",
            "message": f"Account created successfully! Welcome, {full_name}.",
            "user": new_user,
            "token": f"pharmacare-auth-{new_uid}"
        })

    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/auth/profile', methods=['GET', 'PUT'])
def auth_profile():
    try:
        conn = get_db_connection()
        if request.method == 'GET':
            user_id = request.args.get('user_id')
            email = request.args.get('email')
            cursor = conn.cursor(dictionary=True)
            if user_id:
                cursor.execute(
                    "SELECT UserID, FullName, Email, Role, StaffID, Phone, CreatedAt FROM users WHERE UserID = %s;", (user_id,))
            elif email:
                cursor.execute(
                    "SELECT UserID, FullName, Email, Role, StaffID, Phone, CreatedAt FROM users WHERE LOWER(Email) = %s;", (email.lower(),))
            else:
                cursor.execute(
                    "SELECT UserID, FullName, Email, Role, StaffID, Phone, CreatedAt FROM users ORDER BY UserID LIMIT 1;")
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            if user:
                user['CreatedAt'] = str(user.get('CreatedAt', ''))
                return jsonify({"status": "success", "user": user})
            return jsonify({"status": "error", "message": "User not found."}), 404

        else:  # PUT
            data = request.json or {}
            user_id = data.get('user_id')
            full_name = (data.get('full_name') or '').strip()
            phone = (data.get('phone') or '').strip()
            if not user_id or not full_name:
                conn.close()
                return jsonify({"status": "error", "message": "User ID and Full Name are required."}), 400

            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET FullName = %s, Phone = %s WHERE UserID = %s;", (full_name, phone, user_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({"status": "success", "message": "Profile updated successfully!"})

    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- METADATA FOR DROPDOWNS ---


@app.route('/api/metadata', methods=['GET'])
def get_metadata():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT CategoryID, CategoryName FROM Categories ORDER BY CategoryName;")
        categories = cursor.fetchall()

        cursor.execute(
            "SELECT ManufacturerID, ManufacturerName FROM Manufacturers ORDER BY ManufacturerName;")
        manufacturers = cursor.fetchall()

        cursor.execute(
            "SELECT SupplierID, SupplierName FROM Suppliers ORDER BY SupplierName;")
        suppliers = cursor.fetchall()

        cursor.execute(
            "SELECT CustomerID, CustomerName, Phone FROM Customers ORDER BY CustomerName;")
        customers = cursor.fetchall()

        cursor.execute("""
            SELECT p.PrescriptionID, p.CustomerID, c.CustomerName, p.DoctorName, p.IssueDate 
            FROM Prescriptions p
            JOIN Customers c ON p.CustomerID = c.CustomerID
            ORDER BY p.PrescriptionID DESC;
        """)
        prescriptions = cursor.fetchall()
        for p in prescriptions:
            p['IssueDate'] = str(p['IssueDate'])

        cursor.execute("""
            SELECT m.MedicineID, m.MedicineName, m.IsRestricted, c.CategoryName, mf.ManufacturerName,
                   (SELECT COUNT(*) FROM Batches b WHERE b.MedicineID = m.MedicineID) AS BatchCount
            FROM Medicines m
            LEFT JOIN Categories c ON m.CategoryID = c.CategoryID
            LEFT JOIN Manufacturers mf ON m.ManufacturerID = mf.ManufacturerID
            ORDER BY m.MedicineName;
        """)
        medicines = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "categories": categories,
            "manufacturers": manufacturers,
            "suppliers": suppliers,
            "customers": customers,
            "prescriptions": prescriptions,
            "medicines": medicines
        })
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- MODULE A: LIVE INVENTORY & BATCH EXPLORER ---


@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                b.BatchID,
                b.BatchNumber,
                m.MedicineID,
                m.MedicineName,
                c.CategoryID,
                c.CategoryName,
                mf.ManufacturerName,
                m.IsRestricted,
                b.StockQuantity,
                b.UnitCost,
                b.ExpiryDate,
                DATEDIFF(b.ExpiryDate, CURRENT_DATE) AS DaysToExpiry
            FROM Batches b
            JOIN Medicines m ON b.MedicineID = m.MedicineID
            JOIN Categories c ON m.CategoryID = c.CategoryID
            JOIN Manufacturers mf ON m.ManufacturerID = mf.ManufacturerID
            ORDER BY b.BatchID DESC;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for r in rows:
            r['ExpiryDate'] = str(r['ExpiryDate'])
            r['UnitCost'] = float(r['UnitCost'])
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "data": rows})
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- MODULE B: POS TERMINAL & DISPENSING (Checkout Transaction) ---


@app.route('/api/sales/checkout', methods=['POST'])
def checkout_sale():
    conn = None
    try:
        data = request.json or {}
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role == 'Inventory Manager':
            return jsonify({
                "status": "error",
                "message": "Access Denied: Inventory Managers are restricted from POS billing and dispensing."
            }), 403

        customer_id = data.get('customer_id')
        prescription_id = data.get('prescription_id')
        payment_method = data.get('payment_method', 'Cash')
        items = data.get('items', [])

        if not customer_id:
            return jsonify({"status": "error", "message": "Please select a Customer."}), 400
        if not items:
            return jsonify({"status": "error", "message": "Dispensing cart cannot be empty."}), 400

        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        has_restricted_item = False
        grand_total = 0.0
        verified_items = []

        for item in items:
            batch_id = int(item['batch_id'])
            qty = int(item['quantity'])
            if qty <= 0:
                conn.rollback()
                return jsonify({"status": "error", "message": "Quantity must be greater than 0."}), 400

            cursor.execute("""
                SELECT b.BatchID, b.BatchNumber, b.StockQuantity, b.UnitCost, m.MedicineID, m.MedicineName, m.IsRestricted
                FROM Batches b
                JOIN Medicines m ON b.MedicineID = m.MedicineID
                WHERE b.BatchID = %s FOR UPDATE;
            """, (batch_id,))
            batch_row = cursor.fetchone()

            if not batch_row:
                conn.rollback()
                return jsonify({"status": "error", "message": f"Batch ID #{batch_id} not found."}), 404

            if batch_row['StockQuantity'] < qty:
                conn.rollback()
                return jsonify({
                    "status": "error",
                    "message": f"Insufficient stock for {batch_row['MedicineName']} (Batch {batch_row['BatchNumber']}). Available: {batch_row['StockQuantity']}, Requested: {qty}"
                }), 400

            if batch_row['IsRestricted']:
                has_restricted_item = True

            unit_price = float(item.get('unit_price') or (
                float(batch_row['UnitCost']) * 1.5))
            subtotal = round(qty * unit_price, 2)
            grand_total += subtotal

            verified_items.append({
                "batch_id": batch_id,
                "batch_number": batch_row['BatchNumber'],
                "medicine_name": batch_row['MedicineName'],
                "quantity": qty,
                "unit_price": unit_price,
                "subtotal": subtotal
            })

        # PRESCRIPTION COMPLIANCE RULE
        if has_restricted_item:
            if not prescription_id:
                conn.rollback()
                return jsonify({
                    "status": "error",
                    "prescription_required": True,
                    "message": "Prescription Mandatory: Cannot dispense restricted drug without doctor prescription."
                }), 422
            cursor.execute(
                "SELECT PrescriptionID FROM Prescriptions WHERE PrescriptionID = %s;", (prescription_id,))
            p_check = cursor.fetchone()
            if not p_check:
                conn.rollback()
                return jsonify({"status": "error", "message": "Prescription ID not found in system."}), 404
        else:
            prescription_id = prescription_id if prescription_id else None

        grand_total = round(grand_total, 2)

        cursor_raw = conn.cursor()
        sale_id = get_next_id(cursor_raw, "sales", "SaleID")
        today_date = date.today().strftime('%Y-%m-%d')

        cursor_raw.execute("""
            INSERT INTO Sales (SaleID, CustomerID, PrescriptionID, SaleDate, GrandTotal)
            VALUES (%s, %s, %s, %s, %s);
        """, (sale_id, customer_id, prescription_id, today_date, grand_total))

        for item in verified_items:
            sale_item_id = get_next_id(cursor_raw, "sale_items", "SaleItemID")
            cursor_raw.execute("""
                INSERT INTO Sale_Items (SaleItemID, SaleID, BatchID, Quantity, UnitPrice, Discount, SubTotal)
                VALUES (%s, %s, %s, %s, %s, 0.00, %s);
            """, (sale_item_id, sale_id, item['batch_id'], item['quantity'], item['unit_price'], item['subtotal']))

            cursor_raw.execute("""
                UPDATE Batches SET StockQuantity = StockQuantity - %s WHERE BatchID = %s;
            """, (item['quantity'], item['batch_id']))

            movement_id = get_next_id(
                cursor_raw, "stock_movements", "MovementID")
            cursor_raw.execute("""
                INSERT INTO Stock_Movements (MovementID, BatchID, MovementType, Quantity, MovementDate)
                VALUES (%s, %s, 'POS Dispensed', %s, %s);
            """, (movement_id, item['batch_id'], -item['quantity'], today_date))

        payment_id = get_next_id(cursor_raw, "payments", "PaymentID")
        cursor_raw.execute("""
            INSERT INTO Payments (PaymentID, SaleID, PaymentMethod, AmountPaid)
            VALUES (%s, %s, %s, %s);
        """, (payment_id, sale_id, payment_method, grand_total))

        conn.commit()
        cursor_raw.close()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Sale #{sale_id} completed successfully!",
            "sale_id": sale_id,
            "grand_total": grand_total,
            "payment_id": payment_id,
            "items_count": len(verified_items)
        })

    except Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": f"Database transaction error: {str(e)}"}), 500

# --- QUICK CUSTOMER ADD ---


@app.route('/api/customers', methods=['POST'])
def add_customer():
    try:
        data = request.json or {}
        name = (data.get('customer_name') or '').strip()
        phone = (data.get('phone') or '').strip()

        if not name:
            return jsonify({"status": "error", "message": "Customer name is required."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cust_id = get_next_id(cursor, "customers", "CustomerID")
        cursor.execute(
            "INSERT INTO Customers (CustomerID, CustomerName, Phone) VALUES (%s, %s, %s);", (cust_id, name, phone))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "customer_id": cust_id, "customer_name": name, "phone": phone})
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# --- QUICK PRESCRIPTION ADD ---


@app.route('/api/prescriptions', methods=['POST'])
def add_prescription():
    try:
        data = request.json or {}
        customer_id = data.get('customer_id')
        doctor_name = (data.get('doctor_name') or '').strip()
        issue_date = data.get(
            'issue_date') or date.today().strftime('%Y-%m-%d')

        if not customer_id or not doctor_name:
            return jsonify({"status": "error", "message": "Customer and Doctor Name are required."}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        p_id = get_next_id(cursor, "prescriptions", "PrescriptionID")
        cursor.execute("INSERT INTO Prescriptions (PrescriptionID, CustomerID, DoctorName, IssueDate) VALUES (%s, %s, %s, %s);",
                       (p_id, customer_id, doctor_name, issue_date))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success", "prescription_id": p_id, "doctor_name": doctor_name})
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# --- MODULE C: INWARD STOCK INTAKE (INSERT - Inventory Mgr & Admin) ---


@app.route('/api/medicines', methods=['POST'])
def add_medicine():
    try:
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role == 'Pharmacist':
            return jsonify({
                "status": "error",
                "message": "Access Denied: Pharmacists are restricted from registering new inward stock lots."
            }), 403

        data = request.json or {}
        is_new_medicine = data.get('is_new_medicine', True)
        supplier_id = int(data.get('supplier_id', 1))
        batch_no = (data.get('batch_number') or '').strip()
        expiry_date = data.get('expiry_date')
        stock_qty = int(data.get('stock_quantity', 0))
        unit_cost = float(data.get('unit_cost', 0.0))

        if not batch_no:
            return jsonify({"status": "error", "message": "Batch Number is required."}), 400
        if not expiry_date:
            return jsonify({"status": "error", "message": "Expiry Date is required."}), 400
        if stock_qty <= 0 or unit_cost <= 0:
            return jsonify({"status": "error", "message": "Quantity and Unit Cost must be greater than 0."}), 400

        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor()

        cursor.execute(
            "SELECT BatchID FROM Batches WHERE BatchNumber = %s;", (batch_no,))
        if cursor.fetchone():
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": f"Batch Number '{batch_no}' already exists in MySQL."}), 400

        if is_new_medicine:
            name = (data.get('medicine_name') or '').strip()
            category_id = int(data.get('category_id', 1))
            manufacturer_id = int(data.get('manufacturer_id', 1))
            is_restricted = 1 if data.get('is_restricted') else 0

            if not name:
                conn.rollback()
                return jsonify({"status": "error", "message": "Medicine Name is required."}), 400

            med_id = get_next_id(cursor, "medicines", "MedicineID")
            cursor.execute("""
                INSERT INTO Medicines (MedicineID, CategoryID, ManufacturerID, MedicineName, IsRestricted)
                VALUES (%s, %s, %s, %s, %s);
            """, (med_id, category_id, manufacturer_id, name, is_restricted))
        else:
            med_id = int(data.get('medicine_id'))
            name = f"Medicine #{med_id}"

        purchase_id = get_next_id(cursor, "purchases", "PurchaseID")
        total_lot_cost = round(stock_qty * unit_cost, 2)
        today_date = date.today().strftime('%Y-%m-%d')
        cursor.execute("""
            INSERT INTO Purchases (PurchaseID, SupplierID, PurchaseDate, TotalAmount, OrderStatus)
            VALUES (%s, %s, %s, %s, 'Delivered');
        """, (purchase_id, supplier_id, today_date, total_lot_cost))

        batch_id = get_next_id(cursor, "batches", "BatchID")
        cursor.execute("""
            INSERT INTO Batches (BatchID, MedicineID, PurchaseID, BatchNumber, ExpiryDate, StockQuantity, UnitCost)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, (batch_id, med_id, purchase_id, batch_no, expiry_date, stock_qty, unit_cost))

        movement_id = get_next_id(cursor, "stock_movements", "MovementID")
        cursor.execute("""
            INSERT INTO Stock_Movements (MovementID, BatchID, MovementType, Quantity, MovementDate)
            VALUES (%s, %s, 'Stock In', %s, %s);
        """, (movement_id, batch_id, stock_qty, today_date))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Successfully committed inward stock: Batch '{batch_no}' ({stock_qty} units) to MySQL!",
            "batch_id": batch_id,
            "medicine_id": med_id
        })

    except Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 400

# --- MODULE D: BATCH & STOCK REVISION (UPDATE - Inventory Mgr & Admin) ---


@app.route('/api/batches/<int:batch_id>', methods=['PUT'])
def update_batch(batch_id):
    try:
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role == 'Pharmacist':
            return jsonify({
                "status": "error",
                "message": "Access Denied: Pharmacists are restricted from revising stock and unit costs."
            }), 403

        data = request.json or {}
        new_stock = int(data.get('stock_quantity', 0))
        new_cost = float(data.get('unit_cost', 0.0))

        if new_stock < 0 or new_cost < 0:
            return jsonify({"status": "error", "message": "Stock and Cost cannot be negative."}), 400

        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor()

        cursor.execute(
            "SELECT StockQuantity FROM Batches WHERE BatchID = %s;", (batch_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": f"Batch ID #{batch_id} not found."}), 404

        old_stock = row[0]
        diff = new_stock - old_stock

        query = "UPDATE Batches SET StockQuantity = %s, UnitCost = %s WHERE BatchID = %s;"
        cursor.execute(query, (new_stock, new_cost, batch_id))

        if diff != 0:
            today_date = date.today().strftime('%Y-%m-%d')
            movement_id = get_next_id(cursor, "stock_movements", "MovementID")
            cursor.execute("""
                INSERT INTO Stock_Movements (MovementID, BatchID, MovementType, Quantity, MovementDate)
                VALUES (%s, %s, 'Stock Adjustment', %s, %s);
            """, (movement_id, batch_id, diff, today_date))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "status": "success",
            "message": f"Batch #{batch_id} updated successfully! New Stock: {new_stock} units, Cost: ₹{new_cost:.2f}."
        })
    except Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 400

# --- MODULE E: CATALOG CLEANUP - STANDARD INTEGRITY-CHECK DELETION (Admin Only) ---


@app.route('/api/medicines/<int:medicine_id>', methods=['DELETE'])
def delete_medicine(medicine_id):
    try:
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role != 'Administrator':
            return jsonify({
                "status": "error",
                "message": "Access Denied: Only Administrator (Y. Abhinav Sri Ram) has permissions for Catalog Deletion & Governance."
            }), 403

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT MedicineName FROM Medicines WHERE MedicineID = %s;", (medicine_id,))
        med_row = cursor.fetchone()
        med_name = med_row[0] if med_row else f"ID #{medicine_id}"

        cursor.execute(
            "DELETE FROM Medicines WHERE MedicineID = %s", (medicine_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "status": "success",
            "message": f"Medicine '{med_name}' (ID #{medicine_id}) permanently removed from catalog."
        })
    except Error as e:
        # Catch MySQL Error 1451: Referential Integrity Constraint
        if e.errno == 1451:
            return jsonify({
                "status": "blocked",
                "error_code": 1451,
                "message": "Action Intercepted: Referential Integrity Constraint Active. This drug has existing stock batches or completed sales records. Use 'Force Cascade Clean Deletion' if you intend to purge all dependencies."
            }), 409
        return jsonify({"status": "error", "message": str(e)}), 400

# --- MODULE E (CASCADING DELETION): FORCE CASCADE CLEAN PURGE (Admin Only) ---


@app.route('/api/medicines/<int:medicine_id>/cascade', methods=['DELETE'])
def cascade_delete_medicine(medicine_id):
    conn = None
    try:
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role != 'Administrator':
            return jsonify({
                "status": "error",
                "message": "Access Denied: Only Administrator (Y. Abhinav Sri Ram) can perform Cascade Clean Deletion."
            }), 403

        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor()

        cursor.execute(
            "SELECT MedicineName FROM Medicines WHERE MedicineID = %s;", (medicine_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": f"Medicine ID #{medicine_id} not found."}), 404

        med_name = row[0]

        # 1. Delete associated stock movements
        cursor.execute("""
            DELETE sm FROM Stock_Movements sm
            JOIN Batches b ON sm.BatchID = b.BatchID
            WHERE b.MedicineID = %s;
        """, (medicine_id,))

        # 2. Delete associated sale items
        cursor.execute("""
            DELETE si FROM Sale_Items si
            JOIN Batches b ON si.BatchID = b.BatchID
            WHERE b.MedicineID = %s;
        """, (medicine_id,))

        # 3. Delete active inventory batches
        cursor.execute(
            "DELETE FROM Batches WHERE MedicineID = %s;", (medicine_id,))

        # 4. Delete parent medicine record
        cursor.execute(
            "DELETE FROM Medicines WHERE MedicineID = %s;", (medicine_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Medicine ID #{medicine_id} ({med_name}) and all associated batch records cleanly purged from MySQL."
        })
    except Error as e:
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": f"Cascade deletion failed: {str(e)}"}), 500

# --- SAFE-DELETE DEMONSTRATION HELPER ---


@app.route('/api/medicines/demo-safe', methods=['POST'])
def create_demo_safe_medicine():
    try:
        user_role = request.headers.get('X-User-Role', 'Administrator')
        if user_role != 'Administrator':
            return jsonify({"status": "error", "message": "Administrator role required."}), 403

        conn = get_db_connection()
        cursor = conn.cursor()
        med_id = get_next_id(cursor, "medicines", "MedicineID")
        timestamp = datetime.now().strftime('%H%M%S')
        test_name = f"Trial-Compound-X{timestamp}"
        cursor.execute("""
            INSERT INTO Medicines (MedicineID, CategoryID, ManufacturerID, MedicineName, IsRestricted)
            VALUES (%s, 1, 1, %s, 0);
        """, (med_id, test_name))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "status": "success",
            "medicine_id": med_id,
            "medicine_name": test_name,
            "message": f"Created standalone test drug '{test_name}' (ID #{med_id}) with NO child batches. Ready for safe-delete demo!"
        })
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# Query 2: Near-Expiry Safety Alerts (Batches <= 30 days)


@app.route('/api/reports/near-expiry', methods=['GET'])
def query_near_expiry():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                b.BatchID,
                b.BatchNumber,
                m.MedicineName,
                c.CategoryName,
                mf.ManufacturerName,
                b.StockQuantity,
                b.UnitCost,
                b.ExpiryDate,
                DATEDIFF(b.ExpiryDate, CURRENT_DATE) AS DaysToExpiry,
                m.IsRestricted
            FROM Batches b
            JOIN Medicines m ON b.MedicineID = m.MedicineID
            JOIN Categories c ON m.CategoryID = c.CategoryID
            JOIN Manufacturers mf ON m.ManufacturerID = mf.ManufacturerID
            WHERE DATEDIFF(b.ExpiryDate, CURRENT_DATE) <= 30
            ORDER BY DaysToExpiry ASC;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for r in rows:
            r['ExpiryDate'] = str(r['ExpiryDate'])
            r['UnitCost'] = float(r['UnitCost'])
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "data": rows, "count": len(rows)})
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Query 3: Stock Movement Audit Log


@app.route('/api/reports/movements', methods=['GET'])
def query_stock_movements():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 
                sm.MovementID,
                sm.MovementType,
                sm.Quantity,
                sm.MovementDate,
                b.BatchNumber,
                m.MedicineName
            FROM Stock_Movements sm
            JOIN Batches b ON sm.BatchID = b.BatchID
            JOIN Medicines m ON b.MedicineID = m.MedicineID
            ORDER BY sm.MovementID DESC
            LIMIT 50;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        for r in rows:
            r['MovementDate'] = str(r['MovementDate'])
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "data": rows})
    except Error as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print(">>> PharmaCare is starting on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)
