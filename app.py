from flask import Flask, render_template, request, redirect, url_for, flash, session
import qrcode
import random
import sqlite3
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'secretkey'

# Şifre kontrolü
ADMIN_PASSWORD = 'adminpass'  # Admin girişi için şifre

# Veritabanı bağlantısı
def get_db_connection():
    conn = sqlite3.connect('db.sqlite3')
    conn.row_factory = sqlite3.Row
    return conn

# Kullanıcı tablosunu oluşturma
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            surname TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            qr_party TEXT,
            qr_drink TEXT,
            drink_used BOOLEAN DEFAULT 0,
            party_entry_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# Eşsiz kod üretimi
def generate_unique_code():
    while True:
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE code = ?', (code,)).fetchone()
        conn.close()
        if user is None:
            return code

# QR kod oluşturma
def generate_qr_code(data, filename):
    img = qrcode.make(data)
    img.save(os.path.join('static', 'qr_codes', filename))

# Admin girişini kontrol eden decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Ana sayfa
@app.route('/')
def index():
    return render_template('index.html')

# Kullanıcı sorgulama
@app.route('/user')
def user():
    return render_template('user.html')

# QR kod sorgulama
@app.route('/check_code', methods=['POST'])
def check_code():
    code = request.form['code']
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE code = ?', (code,)).fetchone()
    conn.close()
    
    if user:
        return render_template('user.html', user=user)
    else:
        flash('Geçersiz kod!')
        return redirect(url_for('user'))

# Admin giriş sayfası
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            flash('Yanlış şifre!')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

# Admin paneli
@app.route('/admin')
@login_required
def admin_panel():
    return render_template('admin_panel.html')

# Kullanıcı ekleme sayfası
@app.route('/add_user')
@login_required
def add_user_page():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('add_user.html', users=users)

# Kullanıcı ekleme işlemi
@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    name = request.form['name']
    surname = request.form['surname']
    
    # Eşsiz 6 haneli kodu oluştur
    code = generate_unique_code()

    # Parti ve içki için QR kodlarını oluştur
    qr_party_filename = f'qr_party_{code}.png'
    qr_drink_filename = f'qr_drink_{code}.png'
    
    generate_qr_code(f'Party Entry Code: {code}', qr_party_filename)
    generate_qr_code(f'Drink Code: {code}', qr_drink_filename)

    conn = get_db_connection()
    conn.execute('INSERT INTO users (name, surname, code, qr_party, qr_drink) VALUES (?, ?, ?, ?, ?)',
                 (name, surname, code, qr_party_filename, qr_drink_filename))
    conn.commit()
    conn.close()

    flash('Kullanıcı başarıyla eklendi!')
    return redirect(url_for('add_user_page'))

# QR kod okuma sayfası
@app.route('/scan')
@login_required
def scan_page():
    return render_template('scan.html')

# QR kod okuma işlemi
# QR kod okuma işlemi
@app.route('/scan/<code_type>/<code>')
@login_required
def scan_qr_code(code_type, code):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE code = ?', (code,)).fetchone()

    if user:
        if code_type == 'party':
            # Parti giriş sayısını artır
            party_entry_count = user['party_entry_count'] + 1
            conn.execute('UPDATE users SET party_entry_count = ? WHERE code = ?', (party_entry_count, code))
            conn.commit()
            message = f"Partiye giriş onaylandı. {user['name']} {user['surname']} {party_entry_count} kez giriş yaptı."
        elif code_type == 'drink':
            if user['drink_used']:
                message = "İçki kodu zaten kullanıldı!"
            else:
                # İçki kodunu kullanıldı olarak işaretle
                conn.execute('UPDATE users SET drink_used = 1 WHERE code = ?', (code,))
                conn.commit()
                message = f"İçki hakkı verildi, {user['name']} {user['surname']}!"
    else:
        message = "Geçersiz kod!"

    conn.close()
    return message



# Kullanıcı silme işlemi
@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user:
        # QR kod dosyalarını sil
        if user['qr_party']:
            try:
                os.remove(os.path.join('static', 'qr_codes', user['qr_party']))
            except FileNotFoundError:
                pass

        if user['qr_drink']:
            try:
                os.remove(os.path.join('static', 'qr_codes', user['qr_drink']))
            except FileNotFoundError:
                pass

        # Kullanıcıyı veritabanından sil
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        flash(f'{user["name"]} {user["surname"]} başarıyla silindi.')

    conn.close()
    return redirect(url_for('add_user_page'))



# Admin çıkış
@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0')
