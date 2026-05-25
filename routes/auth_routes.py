from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash

from database import get_db_connection
from helpers import obtener_usuario_sesion


def register_auth_routes(app):
    @app.route('/')
    def home():
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM usuarios WHERE username = %s', (username,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id_usuario']
                session['rol'] = user['rol']
                if user['rol'] == 'administrativo':
                    return redirect(url_for('dashboard_admin'))
                elif user['rol'] == 'catedratico':
                    return redirect(url_for('mis_cursos'))
                flash('Rol no autorizado.', 'error')
                return redirect(url_for('login'))
            flash('Usuario o contraseña incorrectos', 'error')
            return redirect(url_for('login'))
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))
