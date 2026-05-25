from datetime import datetime, date
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

from database import get_db_connection
from helpers import (
    obtener_usuario_sesion,
    get_carrera_options,
    get_carrera_id,
    get_seccion_id,
    get_carreras_for_sede,
    get_sede_options,
    is_valid_sede,
)


def register_admin_routes(app):
    @app.route('/admin')
    def dashboard_admin():
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        usuario = obtener_usuario_sesion()
        cursor.execute('SELECT COUNT(*) AS total FROM personas')
        total_personas = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='catedratico' AND activo = 1")
        total_docentes = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='administrativo' AND activo = 1")
        total_admins = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='estudiante' AND activo = 1")
        total_estudiantes = cursor.fetchone()['total']
        cursor.execute("SELECT p.id_persona, p.nombre, p.apellido, p.carnet FROM personas p WHERE p.estado = 'activo' ORDER BY p.id_persona DESC LIMIT 10")
        recent_personas = cursor.fetchall()
        cursor.close()

        for p in recent_personas:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT r.id_rol_persona, r.tipo_persona, r.id_carrera, r.id_seccion,
                       c.nombre AS carrera_nombre, s.nombre AS seccion_nombre
                FROM roles_persona r
                LEFT JOIN carreras c ON r.id_carrera = c.id_carrera
                LEFT JOIN secciones s ON r.id_seccion = s.id_seccion
                WHERE r.id_persona=%s AND r.activo=1
            """, (p['id_persona'],))
            roles = cursor.fetchall()
            cursor.close()
            p['active_roles'] = roles if roles else []

        carrera_options = get_carrera_options()
        conn.close()

        return render_template(
            'admin.html',
            usuario=usuario,
            total_personas=total_personas,
            total_docentes=total_docentes,
            total_admins=total_admins,
            total_estudiantes=total_estudiantes,
            recent_personas=recent_personas,
            carrera_options=carrera_options
        )

    @app.route('/personas/<int:id_persona>/promover', methods=['POST'])
    def promover_persona(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        nuevo_rol = request.form.get('nuevo_rol')
        carrera = request.form.get('carrera')
        seccion = request.form.get('seccion')
        crear_usuario = request.form.get('crear_usuario') == '1'
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_persona=%s AND activo=1", (date.today(), id_persona))
            id_carrera = get_carrera_id(carrera) if carrera else None
            id_seccion = get_seccion_id(seccion, id_carrera) if id_carrera and seccion else None
            cursor.execute(
                "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
                (id_persona, nuevo_rol, None, id_carrera, id_seccion, None, date.today())
            )
            if crear_usuario and nuevo_rol in ('catedratico', 'administrativo'):
                if not username:
                    cursor.execute("SELECT correo FROM personas WHERE id_persona=%s", (id_persona,))
                    rr = cursor.fetchone()
                    username = rr[0] if rr else f'user{id_persona}'
                if not password:
                    password = '123456'
                password_hash = generate_password_hash(password)
                cursor.execute("INSERT INTO usuarios (id_persona, username, password, rol) VALUES (%s, %s, %s, %s)", (id_persona, username, password_hash, nuevo_rol))
            conn.commit()
            flash('Persona promovida correctamente.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error promoviendo persona: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))

    @app.route('/personas/<int:id_persona>/roles/add', methods=['POST'])
    def add_role_persona(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        tipo_persona = request.form.get('tipo_persona')
        carrera = request.form.get('carrera')
        seccion = request.form.get('seccion')
        id_sede = request.form.get('id_sede') or None

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT carnet FROM personas WHERE id_persona=%s', (id_persona,))
            row = cursor.fetchone()
            carnet = row[0] if row else None
            id_carrera = get_carrera_id(carrera) if carrera else None
            id_seccion = get_seccion_id(seccion, id_carrera) if id_carrera and seccion else None
            cursor.execute(
                'INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, datetime.now())
            )
            conn.commit()
            flash('Rol añadido correctamente.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error añadiendo rol: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))

    @app.route('/personas/<int:id_persona>/roles/<int:id_rol>/end', methods=['POST'])
    def end_role_persona(id_persona, id_rol):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s AND id_persona=%s', (datetime.now(), id_rol, id_persona))
            conn.commit()
            flash('Rol finalizado correctamente.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error finalizando rol: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))

    @app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
    def admin_crear_usuario():
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            id_persona = request.form.get('id_persona')
            rol = request.form.get('rol')
            username = request.form.get('username')
            password = request.form.get('password')
            if id_persona and not rol:
                cursor.execute('SELECT tipo_persona FROM roles_persona WHERE id_persona=%s AND activo=1 LIMIT 1', (id_persona,))
                rr = cursor.fetchone()
                rol = rr['tipo_persona'] if rr else None
            if not (id_persona and rol and username and password):
                flash('Todos los campos son obligatorios.', 'warning')
                cursor.close()
                conn.close()
                return redirect(url_for('admin_crear_usuario'))
            try:
                password_hash = generate_password_hash(password)
                cursor.execute('INSERT INTO usuarios (id_persona, username, password, rol) VALUES (%s, %s, %s, %s)', (id_persona, username, password_hash, rol))
                cursor.execute('UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_persona=%s AND activo=1', (date.today(), id_persona))
                cursor.execute('SELECT carnet FROM personas WHERE id_persona=%s', (id_persona,))
                rr = cursor.fetchone()
                carnet = rr['carnet'] if rr else None
                cursor.execute('INSERT INTO roles_persona (id_persona, tipo_persona, carnet, fecha_inicio, activo) VALUES (%s, %s, %s, %s, 1)', (id_persona, rol, carnet, date.today()))
                conn.commit()
                flash('Usuario y rol creados correctamente.', 'success')
                cursor.close()
                conn.close()
                return redirect(url_for('dashboard_admin'))
            except Exception as e:
                conn.rollback()
                flash(f'Error creando usuario: {e}', 'danger')
                cursor.close()
                conn.close()
                return redirect(url_for('admin_crear_usuario'))

        cursor.execute("""
            SELECT DISTINCT p.id_persona, p.nombre, p.apellido, p.carnet, r.tipo_persona AS rol_activo
            FROM personas p
            LEFT JOIN usuarios u ON p.id_persona = u.id_persona
            JOIN roles_persona r ON p.id_persona = r.id_persona AND r.activo = 1
            WHERE u.id_usuario IS NULL AND p.estado = 'activo' AND r.tipo_persona != 'estudiante'
            ORDER BY p.nombre, p.apellido
        """)
        personas = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template('admin_create_user.html', personas=personas, carrera_options=get_carrera_options())

    @app.route('/admin/roles', methods=['GET'])
    def admin_roles():
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        q = request.args.get('q', '').strip()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        results = []
        if q:
            like = f"%{q}%"
            cursor.execute("SELECT id_persona, nombre, apellido, carnet FROM personas WHERE (nombre LIKE %s OR apellido LIKE %s) AND estado='activo' ORDER BY nombre, apellido", (like, like))
            results = cursor.fetchall()
            for p in results:
                cursor2 = conn.cursor(dictionary=True)
                cursor2.execute("""
                    SELECT r.id_rol_persona, r.tipo_persona, r.id_carrera, r.id_seccion,
                           c.nombre AS carrera_nombre, s.nombre AS seccion_nombre, sd.nombre AS sede_nombre
                    FROM roles_persona r
                    LEFT JOIN carreras c ON r.id_carrera = c.id_carrera
                    LEFT JOIN secciones s ON r.id_seccion = s.id_seccion
                    LEFT JOIN sedes sd ON r.id_sede = sd.id_sede
                    WHERE r.id_persona=%s AND r.activo=1
                """, (p['id_persona'],))
                roles = cursor2.fetchall()
                cursor2.close()
                p['active_roles'] = roles if roles else []
        cursor.close()
        conn.close()
        return render_template('admin_roles.html', results=results)

    @app.route('/admin/roles/<int:id_persona>', methods=['GET'])
    def admin_role_detail(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM personas WHERE id_persona=%s', (id_persona,))
        persona = cursor.fetchone()
        if not persona:
            cursor.close()
            conn.close()
            flash('Persona no encontrada', 'warning')
            return redirect(url_for('admin_roles'))

        cursor.execute("""
            SELECT r.id_rol_persona, r.tipo_persona, r.id_carrera, r.id_seccion,
                   c.nombre AS carrera_nombre, s.nombre AS seccion_nombre, sd.nombre AS sede_nombre
            FROM roles_persona r
            LEFT JOIN carreras c ON r.id_carrera = c.id_carrera
            LEFT JOIN secciones s ON r.id_seccion = s.id_seccion
            LEFT JOIN sedes sd ON r.id_sede = sd.id_sede
            WHERE r.id_persona=%s AND r.activo=1
        """, (id_persona,))
        roles = cursor.fetchall()

        cursor.execute('SELECT id_sede, nombre FROM sedes ORDER BY nombre')
        sedes = cursor.fetchall()
        cursor.close()
        conn.close()

        return render_template('admin_role_detail.html', persona=persona, active_roles=roles, carrera_options=get_carrera_options(), sedes=sedes)

    @app.route('/personas/<int:id_persona>/cambiar-carrera', methods=['POST'])
    def change_carrera_persona(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        carrera = request.form.get('carrera')
        if not carrera:
            flash('Debe seleccionar una carrera.', 'warning')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            id_carrera = get_carrera_id(carrera)
            if not id_carrera:
                flash('Carrera inválida.', 'warning')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            cursor.execute('SELECT id_rol_persona, tipo_persona, carnet, id_seccion, id_sede, id_carrera FROM roles_persona WHERE id_persona=%s AND activo=1', (id_persona,))
            current = cursor.fetchone()
            if not current:
                flash('No existe un rol activo para esta persona.', 'warning')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            if current['id_carrera'] == id_carrera:
                flash('La carrera seleccionada es la misma que la actual.', 'info')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            cursor.execute('UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s', (date.today(), current['id_rol_persona']))
            cursor.execute(
                'INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                (id_persona, current['tipo_persona'], current['carnet'], id_carrera, current['id_seccion'], current['id_sede'], date.today())
            )
            conn.commit()
            flash('Carrera actualizada correctamente y el cambio quedó registrado.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error cambiando carrera: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))

    @app.route('/personas/<int:id_persona>/cambiar-sede', methods=['POST'])
    def change_sede_persona(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        id_sede = request.form.get('id_sede')
        if not id_sede or not is_valid_sede(id_sede):
            flash('Debe seleccionar una sede válida.', 'warning')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        id_sede = int(id_sede)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT id_rol_persona, tipo_persona, carnet, id_seccion, id_sede, id_carrera FROM roles_persona WHERE id_persona=%s AND activo=1', (id_persona,))
            current = cursor.fetchone()
            if not current:
                flash('No existe un rol activo para esta persona.', 'warning')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            if current['id_sede'] == id_sede:
                flash('La sede seleccionada es la misma que la actual.', 'info')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            cursor.execute('UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s', (date.today(), current['id_rol_persona']))
            cursor.execute(
                'INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                (id_persona, current['tipo_persona'], current['carnet'], current['id_carrera'], current['id_seccion'], id_sede, date.today())
            )
            conn.commit()
            flash('Sede actualizada correctamente y el cambio quedó registrado.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error cambiando sede: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))

    @app.route('/personas/<int:id_persona>/cambiar-rol', methods=['POST'])
    def change_role_persona(id_persona):
        if session.get('rol') != 'administrativo':
            return redirect(url_for('login'))

        carrera = request.form.get('carrera')
        seccion = request.form.get('seccion')
        id_sede = request.form.get('id_sede')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute('SELECT id_rol_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede FROM roles_persona WHERE id_persona=%s AND activo=1', (id_persona,))
            current = cursor.fetchone()
            if not current:
                flash('No existe un rol activo para esta persona.', 'warning')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            new_id_carrera = current['id_carrera']
            if carrera:
                new_id_carrera = get_carrera_id(carrera)
                if not new_id_carrera:
                    flash('Carrera inválida.', 'warning')
                    return redirect(url_for('admin_role_detail', id_persona=id_persona))

            new_id_seccion = current['id_seccion']
            if seccion:
                if not new_id_carrera:
                    flash('Debe seleccionar primero una carrera válida.', 'warning')
                    return redirect(url_for('admin_role_detail', id_persona=id_persona))
                new_id_seccion = get_seccion_id(seccion, new_id_carrera)
                if new_id_seccion is None:
                    flash('Sección inválida para la carrera seleccionada.', 'warning')
                    return redirect(url_for('admin_role_detail', id_persona=id_persona))

            new_id_sede = current['id_sede']
            if id_sede:
                if not is_valid_sede(id_sede):
                    flash('Sede inválida.', 'warning')
                    return redirect(url_for('admin_role_detail', id_persona=id_persona))
                new_id_sede = int(id_sede)

            if new_id_carrera == current['id_carrera'] and new_id_seccion == current['id_seccion'] and new_id_sede == current['id_sede']:
                flash('No se realizaron cambios en el rol.', 'info')
                return redirect(url_for('admin_role_detail', id_persona=id_persona))

            cursor.execute('UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s', (date.today(), current['id_rol_persona']))
            cursor.execute(
                'INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                (id_persona, current['tipo_persona'], current['carnet'], new_id_carrera, new_id_seccion, new_id_sede, date.today())
            )
            conn.commit()
            flash('Rol actualizado correctamente y el cambio quedó registrado en el historial.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error actualizando el rol: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('admin_roles'))
