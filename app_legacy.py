from flask import Flask

from config import Config
from routes.admin_routes import register_admin_routes
from routes.auth_routes import register_auth_routes
from routes.cursos_routes import register_cursos_routes
from routes.docente_routes import register_docente_routes
from routes.registro_routes import register_registro_routes
from routes.reconocimiento import register_reconocimiento_routes, start_camera_threads


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["UPLOAD_FOLDER"] = "static/fotos"

    register_auth_routes(app)
    register_admin_routes(app)
    register_registro_routes(app)
    register_cursos_routes(app)
    register_docente_routes(app)
    register_reconocimiento_routes(app)

    with app.app_context():
        start_camera_threads()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

# Valores de respaldo si la base de datos de opciones aún no existe.
DEFAULT_CAREER_OPTIONS = [
    "Ingeniería en Sistemas",
    "Ingeniería Industrial",
    "Administración de Empresas",
    "Derecho",
    "Medicina",
    "No aplica"
]
DEFAULT_SECTION_OPTIONS = [
    "A",
    "B",
    "C",
    "D",
    "E",
    "No aplica"
]

# Niveles de reconocimiento facial:
# - facil: modelo de encoding "small" (5 puntos)
# - medio: modelo de encoding "large" (68 puntos)
# - avanzado: modelo de detección CNN y encoding "large"
RECOGNITION_LEVEL = "medio"
RECOGNITION_PROFILES = {
    "facil": {
        "detect_model": "hog",
        "encoding_model": "small",
        "tolerance": 0.60
    },
    "medio": {
        "detect_model": "hog",
        "encoding_model": "large",
        "tolerance": 0.50
    },
    "avanzado": {
        "detect_model": "cnn",
        "encoding_model": "large",
        "tolerance": 0.45
    }
}
PROFILE = RECOGNITION_PROFILES[RECOGNITION_LEVEL]
DETECT_MODEL = PROFILE["detect_model"]
ENCODING_MODEL = PROFILE["encoding_model"]
TOLERANCE = PROFILE["tolerance"]
MIN_SECONDS_BETWEEN_LOGS = 300
# =========================================================
# DB
# =========================================================
def get_db_connection():
    return mysql.connector.connect(
        host=app.config.get("MYSQL_HOST", "localhost"),
        user=app.config.get("MYSQL_USER", "root"),
        password=app.config.get("MYSQL_PASSWORD", ""),
        database=app.config.get("MYSQL_DATABASE", "")
    )

def _get_selection_options(table_name, default_options, where_clause=None, params=None):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = f"SELECT DISTINCT nombre FROM {table_name}"
        if where_clause:
            query += f" WHERE {where_clause}"
        query += " ORDER BY nombre"
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        return [row[0] for row in rows] if rows else (default_options or [])
    except Exception as e:
        app.logger.error(f"Error cargando opciones de {table_name}: {e}")
        return default_options or []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_carrera_options():
    return _get_selection_options("carreras", [])

def get_seccion_options(id_sede=None, carrera=None):
    if not carrera:
        return []
    id_carrera = get_carrera_id(carrera)
    if not id_carrera:
        return []

    if id_sede is not None:
        try:
            id_sede = int(id_sede)
        except Exception:
            return []

    conn = get_db_connection()
    cursor = conn.cursor()
    if id_sede:
        cursor.execute(
            """
            SELECT s.nombre
            FROM secciones s
            JOIN sede_carrera sc ON s.id_sede_carrera = sc.id_sede_carrera
            WHERE s.id_carrera = %s AND sc.id_sede = %s
            ORDER BY s.nombre
            """,
            (id_carrera, id_sede)
        )
    else:
        cursor.execute("SELECT nombre FROM secciones WHERE id_carrera = %s ORDER BY nombre", (id_carrera,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r[0] for r in rows] if rows else []

def is_valid_carrera(carrera):
    return len(_get_selection_options("carreras", [], "nombre = %s", (carrera,))) == 1

def is_valid_seccion(seccion, carrera=None, id_sede=None):
    if not (seccion and carrera):
        return False
    return seccion in get_seccion_options(id_sede, carrera)


def is_valid_carrera_in_sede(id_sede, carrera):
    try:
        id_sede = int(id_sede)
    except Exception:
        return False
    id_carrera = get_carrera_id(carrera)
    if not id_carrera:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sede_carrera WHERE id_sede = %s AND id_carrera = %s", (id_sede, id_carrera))
    valid = cursor.fetchone()[0] == 1
    cursor.close()
    conn.close()
    return valid


def get_carreras_for_sede(id_sede):
    try:
        id_sede = int(id_sede)
    except Exception:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT c.nombre FROM carreras c JOIN sede_carrera sc ON c.id_carrera = sc.id_carrera WHERE sc.id_sede = %s ORDER BY c.nombre", (id_sede,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r[0] for r in rows] if rows else []


def get_cursos_for_sede_carrera(id_sede, carrera):
    if not id_sede or not carrera:
        return []
    try:
        id_sede = int(id_sede)
    except Exception:
        return []
    if not is_valid_carrera_in_sede(id_sede, carrera):
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT c.id_curso, c.nombre "
        "FROM cursos c "
        "JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera "
        "JOIN carreras ca ON sc.id_carrera = ca.id_carrera "
        "WHERE sc.id_sede = %s AND ca.nombre = %s "
        "ORDER BY c.nombre",
        (id_sede, carrera)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows if rows else []


def get_carrera_id(carrera):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_carrera FROM carreras WHERE nombre = %s", (carrera,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def get_sede_carrera_id(id_sede, carrera):
    try:
        id_sede = int(id_sede)
    except Exception:
        return None
    id_carrera = get_carrera_id(carrera)
    if not id_carrera:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_sede_carrera FROM sede_carrera WHERE id_sede = %s AND id_carrera = %s", (id_sede, id_carrera))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def get_seccion_id(seccion, id_carrera):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_seccion FROM secciones WHERE nombre = %s AND id_carrera = %s", (seccion, id_carrera))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def get_sede_options():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id_sede, nombre FROM sedes ORDER BY nombre")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows or []


def is_valid_sede(id_sede):
    if not id_sede:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM sedes WHERE id_sede = %s", (id_sede,))
    valid = cursor.fetchone()[0] == 1
    cursor.close()
    conn.close()
    return valid


@app.route('/api/secciones')
def api_secciones():
    id_sede = request.args.get('sede')
    carrera = request.args.get('carrera', '')
    options = get_seccion_options(id_sede, carrera) if carrera else []
    return jsonify({'options': options})


@app.route('/api/carreras')
def api_carreras():
    id_sede = request.args.get('sede')
    if not id_sede:
        # return all carreras
        options = get_carrera_options()
        return jsonify({'options': options})
    try:
        id_sede = int(id_sede)
    except Exception:
        return jsonify({'options': []})
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT c.nombre FROM carreras c JOIN sede_carrera sc ON c.id_carrera = sc.id_carrera WHERE sc.id_sede = %s ORDER BY c.nombre", (id_sede,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    options = [r[0] for r in rows] if rows else []
    return jsonify({'options': options})


@app.route('/api/cursos')
def api_cursos():
    id_sede = request.args.get('sede')
    carrera = request.args.get('carrera', '')
    if not id_sede or not carrera:
        return jsonify({'options': []})
    try:
        id_sede = int(id_sede)
    except Exception:
        return jsonify({'options': []})
    if not is_valid_sede(id_sede) or not is_valid_carrera_in_sede(id_sede, carrera):
        return jsonify({'options': []})
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT c.id_curso, c.nombre "
        "FROM cursos c "
        "JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera "
        "JOIN carreras ca ON sc.id_carrera = ca.id_carrera "
        "WHERE sc.id_sede = %s AND ca.nombre = %s "
        "ORDER BY c.nombre",
        (id_sede, carrera)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    options = [{'id': r[0], 'nombre': r[1]} for r in rows] if rows else []
    return jsonify({'options': options})


def obtener_usuario_sesion():
    if not session.get("user_id"):
        return None
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id_persona, p.nombre, p.apellido, p.foto
        FROM usuarios u
        JOIN personas p ON u.id_persona = p.id_persona
        WHERE u.id_usuario = %s
    """, (session.get("user_id"),))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()
    if usuario and usuario.get("foto"):
        if isinstance(usuario["foto"], (bytes, bytearray)):
            import base64
            usuario["foto"] = base64.b64encode(usuario["foto"]).decode("utf-8")
    elif usuario:
        usuario["foto"] = None

    return usuario
# =========================================================
# HELPERS
# =========================================================
def generar_carnet_unico():
    """
    Genera un carnet único con prefijo '7691-YY-' y 5 dígitos aleatorios.
    Verifica que no exista en la tabla personas.
    """
    yy = datetime.now().strftime("%y")
    prefijo = f"7691-{yy}-"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        while True:
            numero_random = random.randint(10000, 99999)
            carnet = f"{prefijo}{numero_random}"
            cursor.execute("SELECT id_persona FROM personas WHERE carnet = %s", (carnet,))
            if cursor.fetchone() is None:
                return carnet
    finally:
        cursor.close()
        conn.close()
def _decode_dataurl_image(dataurl: str):
    if not dataurl:
        return None
    dataurl = dataurl.strip()
    m = re.match(r"data:image/[^;]+;base64,(.*)", dataurl)
    if m:
        dataurl = m.group(1)
    return base64.b64decode(dataurl)
def generate_id_card_pdf(nombre, apellido, correo, foto_bytes, carnet, id_persona, firma_base64=None):
    conn = None
    cursor = None
    foto_path = None
    qr_path = None
    firma_img_path = None
    try:
        year = datetime.now().year
        # =========================
        # TAMAÑO CARNET (CR80)
        # =========================
        CARD_W = 85.6
        CARD_H = 54.0
        pdf = FPDF(orientation="L", unit="mm", format=(CARD_H, CARD_W))
        pdf.add_page()
        pdf.set_auto_page_break(False)
        # Fondo blanco
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(0, 0, CARD_W, CARD_H, "F")
        # =========================
        # LOGO
        # =========================
        logo_path = os.path.join("static", "img", "logo.png")
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=3.6, y=0.75, w=13.2, h=13.2)
        # =========================
        # UNIVERSIDAD
        # =========================
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Times", "B", 16)
        pdf.text(19.5, 5.5, "UNIVERSIDAD")
        pdf.text(19.5, 12.5, "MARIANO GÁLVEZ")
        # =========================
        # AÑO
        # =========================
        pdf.set_font("Times", "B", 13)
        pdf.text(67.0, 19.5, str(year))
        # =========================
        # FOTO
        # =========================
        foto_path = os.path.join("static", f"temp_foto_{id_persona}.png")
        with open(foto_path, "wb") as f:
            f.write(foto_bytes)
        pdf.image(foto_path, x=4.5, y=16.2, w=23.4, h=25.3)
        # =========================
        # NOMBRE Y APELLIDO
        # =========================
        pdf.set_font("Times", "B", 11)
        pdf.text(32.4, 20.5, nombre)
        pdf.text(32.4, 24.5, apellido)
        # =========================
        # ID
        # =========================
        pdf.set_font("Helvetica", "", 8)
        pdf.text(32.4, 29, "Carnet")
        pdf.text(32.4, 32,  carnet)
        # =========================
        # FIRMA
        # =========================
        firma_bytes = _decode_dataurl_image(firma_base64)
        # Si no viene del form, buscar en BD
        if not firma_bytes:
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT firma FROM personas WHERE id_persona=%s", (id_persona,))
                row = cursor.fetchone()
                if row and row.get("firma"):
                    firma_bytes = _decode_dataurl_image(row["firma"])
            except Exception:
                pass
        if firma_bytes:
            firma_img_path = os.path.join("static", f"temp_firma_{id_persona}.png")
            with open(firma_img_path, "wb") as f:
                f.write(firma_bytes)
            pdf.image(firma_img_path, x=33.7, y=36.5, w=27.3, h=6.3)
            pdf.text(38.7, 46.5, "Firma")
        # =========================
        # QR
        # =========================
        # QR should contain carnet and the full name of the person
        qr_data = f"CARNET:{carnet};NOMBRE:{nombre} {apellido}"
        qr_img = qrcode.make(qr_data)
        qr_path = os.path.join("static", f"temp_qr_{id_persona}.png")
        qr_img.save(qr_path)
        pdf.image(qr_path, x=63.6, y=21.5, w=16.5, h=16.5)
        # =========================
        # SALIDA
        # =========================
        return pdf.output(dest="S").encode("latin1")
    except Exception as e:
        print("Error generando PDF:", e)
        return None
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass
        # Eliminar archivos temporales
        for p in (foto_path, qr_path, firma_img_path):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
def send_email_with_pdf(to_email, pdf_bytes, filename, subject="Tu carnet institucional"):
    smtp_server = app.config.get("SMTP_SERVER") or os.getenv("SMTP_SERVER")
    smtp_port = app.config.get("SMTP_PORT") or os.getenv("SMTP_PORT") or "587"
    try:
        smtp_port = int(smtp_port)
    except Exception:
        smtp_port = 587
    smtp_user = app.config.get("SMTP_USER") or os.getenv("SMTP_USER")
    smtp_pass = app.config.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD")
    sender_email = app.config.get("SENDER_EMAIL") or os.getenv("SENDER_EMAIL")
    use_tls_raw = app.config.get("SMTP_USE_TLS") or os.getenv("SMTP_USE_TLS", "true")
    use_tls = str(use_tls_raw).lower() == "true"
    missing = []
    if not smtp_server: missing.append("SMTP_SERVER")
    if not smtp_user: missing.append("SMTP_USER")
    if not smtp_pass: missing.append("SMTP_PASSWORD")
    if not sender_email: missing.append("SENDER_EMAIL")
    if missing:
        err = "Faltan variables SMTP: " + ", ".join(missing)
        print(err)
        return (False, err)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email
    msg.set_content("Adjunto encontrarás tu carnet institucional en formato PDF.")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            if use_tls:
                server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return (True, None)
    except Exception as e:
        err = f"Error enviando correo con PDF: {e}"
        print(err)
        return (False, err)
# =========================================================
# AUTH ROUTES
# =========================================================
@app.route("/")
def home():
    return redirect(url_for("login"))
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM usuarios WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id_usuario"]
            session["rol"] = user["rol"]
            if user["rol"] == "administrativo":
                return redirect(url_for("dashboard_admin"))
            elif user["rol"] == "catedratico":
                return redirect(url_for("mis_cursos"))
            flash("Rol no autorizado.", "error")
            return redirect(url_for("login"))
        flash("Usuario o contraseña incorrectos", "error")
        return redirect(url_for("login"))
    return render_template("login.html")
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
# =========================================================
# DASHBOARDS
# =========================================================
@app.route("/admin")
def dashboard_admin():
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    usuario = obtener_usuario_sesion()
    cursor.execute("SELECT COUNT(*) AS total FROM personas")
    total_personas = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='catedratico' AND activo = 1")
    total_docentes = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='administrativo' AND activo = 1")
    total_admins = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(DISTINCT id_persona) AS total FROM roles_persona WHERE tipo_persona='estudiante' AND activo = 1")
    total_estudiantes = cursor.fetchone()["total"]
    
    # obtener últimas personas y sus roles activos
    cursor.execute("""
        SELECT p.id_persona, p.nombre, p.apellido, p.carnet
        FROM personas p
        WHERE p.estado = 'activo'
        ORDER BY p.id_persona DESC
        LIMIT 10
    """)
    recent_personas = cursor.fetchall()

    # cerrar cursor y abrir uno nuevo para queries anidadas
    cursor.close()
    
    # para cada persona, obtener sus roles activos
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

    # opciones de carrera para los formularios
    carrera_options = get_carrera_options()

    conn.close()

    return render_template(
        "admin.html",
        usuario=usuario,
        total_personas=total_personas,
        total_docentes=total_docentes,
        total_admins=total_admins,
        total_estudiantes=total_estudiantes,
        recent_personas=recent_personas,
        carrera_options=carrera_options
    )

@app.route("/docente")
def dashboard_docente():
    if session.get("rol") != "catedratico":
        return redirect(url_for("login"))
    usuario = obtener_usuario_sesion()
    return render_template("catedratico/mis_cursos.html", usuario=usuario)
# =========================================================
# REGISTRO PERSONAS
# =========================================================
@app.route("/registrar", methods=["GET", "POST"])
def registrar_persona():
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))
    # Obtener datos del usuario para la plantilla (evita que 'usuario' sea undefined)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.nombre, p.apellido, p.foto
        FROM usuarios u
        JOIN personas p ON u.id_persona = p.id_persona
        WHERE u.id_usuario = %s
    """, (session.get("user_id"),))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()
    if usuario and usuario.get("foto"):
        if isinstance(usuario["foto"], (bytes, bytearray)):
            usuario["foto"] = usuario["foto"].decode("utf-8")
    else:
        if usuario:
            usuario["foto"] = None
    if request.method == "POST":
        # ========= 1) Capturar form =========
        nombre = request.form["nombre"].strip()
        apellido = request.form["apellido"].strip()
        telefono = request.form["telefono"].strip()
        correo = request.form["correo"].strip().lower()
        tipo_persona = request.form["tipo_persona"]
        carrera = request.form.get("carrera", "")
        seccion = request.form.get("seccion", "")
        imagen_base64 = request.form.get("fotografia")
        firma = request.form.get("firma", "").strip()
        # Para re-renderizar y NO perder datos
        form_data = request.form.to_dict(flat=True)
        # ========= 2) Validaciones =========
        seccion_options = get_seccion_options(carrera) if carrera else []
        sede_options = get_sede_options()
        if not is_valid_carrera(carrera):
            flash("Carrera inválida. Seleccione una opción válida.", "danger")
            form_data["fotografia"] = imagen_base64 or ""
            return render_template("registrar.html", form_data=form_data, retake_photo=True, usuario=usuario, carrera_options=[], seccion_options=seccion_options, sede_options=sede_options)
        if not is_valid_seccion(seccion, carrera):
            flash("Sección inválida. Seleccione una opción válida.", "danger")
            form_data["fotografia"] = imagen_base64 or ""
            return render_template("registrar.html", form_data=form_data, retake_photo=True, usuario=usuario, carrera_options=[], seccion_options=seccion_options, sede_options=sede_options)
        sede = request.form.get("sede")
        if not is_valid_sede(sede):
            flash("Sede inválida. Seleccione una opción válida.", "danger")
            form_data["fotografia"] = imagen_base64 or ""
            return render_template("registrar.html", form_data=form_data, retake_photo=True, usuario=usuario, carrera_options=[], seccion_options=seccion_options, sede_options=sede_options)
        if not correo.endswith("@miumg.edu.gt"):
            flash("Debe usar correo institucional @miumg.edu.gt", "danger")
            # NO es error de foto, puede redirigir sin problema
            return redirect(url_for("registrar_persona"))
        if not imagen_base64:
            flash("Debe capturar la fotografía", "danger")
            # Aquí sí conviene re-render para no perder datos
            form_data["fotografia"] = ""
            return render_template("registrar.html", form_data=form_data, retake_photo=True, usuario=usuario, carrera_options=[], seccion_options=get_seccion_options(carrera))
        try:
            _, encoded = imagen_base64.split(",", 1)
            imagen_bytes = base64.b64decode(encoded)
        except Exception:
            flash("Error procesando la imagen. Vuelva a tomar la fotografía.", "danger")
            form_data["fotografia"] = ""
            return render_template("registrar.html", form_data=form_data, retake_photo=True, usuario=usuario, carrera_options=[], seccion_options=get_seccion_options(carrera))

        # ========= 3) DB =========
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM personas WHERE correo = %s", (correo,))
        if cursor.fetchone()["total"] > 0:
            cursor.close()
            conn.close()
            flash("El correo ya está registrado", "warning")
            return redirect(url_for("registrar_persona"))

        carnet = generar_carnet_unico()

        cursor.close()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO personas
            (nombre, apellido, telefono, correo, carnet, foto, firma)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (nombre, apellido, telefono, correo, carnet, imagen_bytes, firma))

        id_persona = cursor.lastrowid
        conn.commit()

        id_carrera = get_carrera_id(carrera)
        id_seccion = get_seccion_id(seccion, id_carrera) if id_carrera else None
        id_sede = int(request.form.get('sede')) if request.form.get('sede') else None
        cursor.execute("""
            INSERT INTO roles_persona
            (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, date.today()))
        conn.commit()

        # ========= 4) Guardar foto en carpeta =========
        def limpiar_nombre(texto):
            return re.sub(r"[^\w\-]", "_", texto)

        nombre_limpio = limpiar_nombre(f"{nombre}_{apellido}")
        carpeta_persona = os.path.join("static", "rostros", f"{id_persona}_{nombre_limpio}")
        os.makedirs(carpeta_persona, exist_ok=True)

        nombre_archivo = f"{nombre_limpio}_1.png"
        ruta_foto = os.path.join(carpeta_persona, nombre_archivo)

        with open(ruta_foto, "wb") as f:
            f.write(imagen_bytes)

        # ========= 5) Encoding facial =========
        try:
            img = cv2.imread(ruta_foto)
            if img is None:
                raise ValueError("No se pudo leer la imagen")

            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(rgb_img, model=ENCODING_MODEL)

            if not encodings:
                raise ValueError("No se detectó un rostro válido")

            encoding_json = json.dumps(encodings[0].tolist())
            cursor.execute("""
                UPDATE personas
                SET encoding_facial = %s
                WHERE id_persona = %s
            """, (encoding_json, id_persona))
            conn.commit()

        except Exception as e:
            print("Error encoding:", e)

            # 1) borrar roles asociados antes de borrar la persona
            try:
                cursor.execute("DELETE FROM roles_persona WHERE id_persona = %s", (id_persona,))
                conn.commit()
            except Exception:
                pass

            # 2) borrar registro creado
            try:
                cursor.execute("DELETE FROM personas WHERE id_persona = %s", (id_persona,))
                conn.commit()
            except Exception:
                pass

            # 3) borrar archivo
            try:
                if os.path.exists(ruta_foto):
                    os.remove(ruta_foto)
            except:
                pass

            # 4) (opcional) borrar carpeta si queda vacía
            try:
                if os.path.isdir(carpeta_persona) and len(os.listdir(carpeta_persona)) == 0:
                    os.rmdir(carpeta_persona)
            except:
                pass

            cursor.close()
            conn.close()

            flash("No se detectó un rostro válido. Vuelva a tomar la fotografía.", "danger")

            # ✅ AQUÍ LA CLAVE: NO redirect, re-render con datos
            form_data["fotografia"] = ""   # obligar a retomar foto
            # Si quieres conservar la firma: NO la borres
            # form_data["firma"] = form_data.get("firma", "")

            return render_template(
                "registrar.html",
                form_data=form_data,
                retake_photo=True,
                usuario=usuario,
                carrera_options=[],
                seccion_options=get_seccion_options(carrera),
                sede_options=get_sede_options()
            )

        # ========= 6) PDF + correo =========
        try:
            pdf_bytes = generate_id_card_pdf(nombre, apellido, correo, imagen_bytes, carnet, id_persona, firma)
            if pdf_bytes:
                send_ok, send_err = send_email_with_pdf(correo, pdf_bytes, f"carnet_{id_persona}.pdf")
                if send_ok:
                    flash("Persona registrada y carnet enviado por correo.", "success")
                else:
                    flash(f"Persona registrada, pero error enviando carnet: {send_err}", "warning")
            else:
                flash("Persona registrada, pero no se pudo generar el carnet PDF.", "warning")
        except Exception as e:
            flash(f"Persona registrada, pero error al enviar carnet: {e}", "warning")

        cursor.close()
        conn.close()
        return redirect(url_for("registrar_persona"))

    # GET normal
    sede_options = get_sede_options()
    return render_template(
        "registrar.html",
        usuario=usuario,
        carrera_options=[],
        seccion_options=[],
        sede_options=sede_options
    )


@app.route('/personas/<int:id_persona>/promover', methods=['POST'])
def promover_persona(id_persona):
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    nuevo_rol = request.form.get('nuevo_rol')
    carrera = request.form.get('carrera')
    seccion = request.form.get('seccion')
    crear_usuario = request.form.get('crear_usuario') == '1'
    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Desactivar roles activos previos
        cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_persona=%s AND activo=1", (date.today(), id_persona))

        # Resolver ids de carrera/seccion si vienen
        id_carrera = get_carrera_id(carrera) if carrera else None
        id_seccion = get_seccion_id(seccion, id_carrera) if id_carrera and seccion else None

        # Obtener carnet actual (si existe)
        cursor.execute("SELECT carnet FROM personas WHERE id_persona=%s", (id_persona,))
        row = cursor.fetchone()
        carnet = row[0] if row else None

        # Insertar nuevo rol
        cursor.execute(
            "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, 1)",
            (id_persona, nuevo_rol, carnet, id_carrera, id_seccion, date.today())
        )

        # Crear cuenta de usuario si corresponde
        if crear_usuario and nuevo_rol in ('catedratico', 'administrativo'):
            if not username:
                # intentar usar correo como username
                cursor.execute("SELECT correo FROM personas WHERE id_persona=%s", (id_persona,))
                rr = cursor.fetchone()
                username = rr[0] if rr else f'user{ id_persona }'
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    tipo_persona = request.form.get('tipo_persona')
    carrera = request.form.get('carrera')
    seccion = request.form.get('seccion')
    id_sede = request.form.get('id_sede') or None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # obtener carnet actual
        cursor.execute("SELECT carnet FROM personas WHERE id_persona=%s", (id_persona,))
        row = cursor.fetchone()
        carnet = row[0] if row else None

        id_carrera = get_carrera_id(carrera) if carrera else None
        id_seccion = get_seccion_id(seccion, id_carrera) if id_carrera and seccion else None

        # insertar nuevo rol (no inactivar los anteriores)
        cursor.execute(
            "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s AND id_persona=%s", (datetime.now(), id_rol, id_persona))
        conn.commit()
        flash('Rol finalizado correctamente.', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error finalizando rol: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_roles'))


# =========================================================
# RECONOCIMIENTO MULTICÁMARA
# =========================================================
CAMERAS = {
    "cam1": {"nombre": "Puerta Principal", "ubicacion": "Puerta Principal", "source": "http://10.159.145.12:4747/video"},
    "cam2": {"nombre": "Salón 306", "ubicacion": "Salón 306", "source": "http://192.168.1.72:4747/video"},
}

SCALE = 0.35
TIPO_REGISTRO = "puerta_principal"

RECOGNIZE_EVERY_N_FRAMES = 15
STREAM_FPS = 20
JPEG_QUALITY = 45
# DETECT_MODEL, TOLERANCE y MIN_SECONDS_BETWEEN_LOGS se configuran en la sección principal de la app.

cam_state = {}
last_log_time = {}
state_lock = threading.Lock()


def init_cam_state():
    for cam_id in CAMERAS.keys():
        cam_state[cam_id] = {
            "latest_jpeg": None,
            "latest_match": {
                "matched": False,
                "id_persona": None,
                "nombre": None,
                "apellido": None,
                "carnet": None,
                "correo": None,
                "dist": None,
                "timestamp": None,
                "cam_id": cam_id
            },
            "last_log_time": last_log_time
        }

init_cam_state()


def load_known_faces():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id_persona, nombre, apellido, carnet, correo, encoding_facial
        FROM personas
        WHERE encoding_facial IS NOT NULL
          AND encoding_facial <> ''
          AND estado = 'activo'
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    known_encodings = []
    known_people = []

    for r in rows:
        try:
            enc_list = json.loads(r["encoding_facial"])
            enc = np.array(enc_list, dtype=np.float32)
            if enc.shape == (128,):
                known_encodings.append(enc)
                known_people.append({
                    "id_persona": r["id_persona"],
                    "nombre": r["nombre"],
                    "apellido": r["apellido"],
                    "carnet": r["carnet"],
                    "correo": r["correo"],
                })
        except Exception as e:
            print(f"Encoding inválido id_persona={r.get('id_persona')}: {e}")

    print(f"✔ Encodings cargados: {len(known_encodings)}")
    return known_encodings, known_people


def registrar_entrada(id_persona, ubicacion):
    conn = get_db_connection()
    cursor = conn.cursor()

    cutoff_time = (datetime.now() - timedelta(seconds=MIN_SECONDS_BETWEEN_LOGS)).time()
    cursor.execute("""
        SELECT COUNT(*)
        FROM registros_entrada
        WHERE id_persona = %s
          AND ubicacion = %s
          AND fecha = %s
          AND hora >= %s
    """, (id_persona, ubicacion, date.today(), cutoff_time))
    already_logged = cursor.fetchone()[0]

    if already_logged == 0:
        cursor.execute("""
            INSERT INTO registros_entrada (id_persona, ubicacion, fecha, hora, tipo_registro)
            VALUES (%s, %s, %s, %s, %s)
        """, (id_persona, ubicacion, date.today(), datetime.now().time().replace(microsecond=0), TIPO_REGISTRO))
        conn.commit()
    else:
        print(f"Entrada ya registrada recientemente para persona={id_persona} ubicacion={ubicacion}")

    cursor.close()
    conn.close()


KNOWN_ENCODINGS, KNOWN_PEOPLE = load_known_faces()
if not KNOWN_ENCODINGS:
    print("⚠ No hay encodings en la base de datos (personas.activo con encoding_facial).")


def open_camera(source):
    if isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def camera_loop(cam_id, source):
    known_encodings, known_people = KNOWN_ENCODINGS, KNOWN_PEOPLE
    if not known_encodings:
        print(f"[{cam_id}] No hay encodings para reconocimiento.")
        return

    print(f"[{cam_id}] Intentando abrir: {source}")
    cap = open_camera(source)
    if not cap.isOpened():
        print(f"[{cam_id}] ❌ No se pudo abrir la cámara: {source}")
        return
    print(f"[{cam_id}] Cámara abierta")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
    cap.set(cv2.CAP_PROP_FPS, STREAM_FPS)

    frame_count = 0
    last_boxes = []
    last_labels = []

    frame_interval = 1.0 / STREAM_FPS
    next_frame_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.05)
            continue

        frame_count += 1
        do_recognize = (frame_count % RECOGNIZE_EVERY_N_FRAMES == 0)

        if do_recognize:
            small = cv2.resize(frame, (0, 0), fx=SCALE, fy=SCALE)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb, model=DETECT_MODEL)
            face_encodings = face_recognition.face_encodings(rgb, face_locations, model=ENCODING_MODEL)

            last_boxes = []
            last_labels = []
            frame_match = None

            for (top, right, bottom, left), face_enc in zip(face_locations, face_encodings):
                distances = face_recognition.face_distance(known_encodings, face_enc)
                best_idx = int(np.argmin(distances))
                best_distance = float(distances[best_idx])

                if best_distance <= TOLERANCE:
                    person = known_people[best_idx]
                    pid = person["id_persona"]

                    now_ts = time.time()
                    with state_lock:
                        last_ts = cam_state[cam_id]["last_log_time"].get(pid, 0)

                    if now_ts - last_ts >= MIN_SECONDS_BETWEEN_LOGS:
                        try:
                            ubicacion_real = CAMERAS[cam_id]["ubicacion"]
                            registrar_entrada(pid, ubicacion=ubicacion_real)
                            with state_lock:
                                cam_state[cam_id]["last_log_time"][pid] = now_ts
                        except Exception as e:
                            print(f"[{cam_id}] Error registrando entrada:", e)

                    frame_match = {
                        "matched": True,
                        "id_persona": pid,
                        "nombre": person["nombre"],
                        "apellido": person["apellido"],
                        "carnet": person["carnet"],
                        "correo": person["correo"],
                        "dist": round(best_distance, 4),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "cam_id": cam_id
                    }

                    label = f"{person['nombre']} {person['apellido']} ({person['carnet']})"
                    color = (0, 255, 0)
                else:
                    label = f"NO REGISTRADO (dist={best_distance:.2f})"
                    color = (0, 0, 255)

                inv = 1.0 / SCALE
                top2, right2, bottom2, left2 = int(top*inv), int(right*inv), int(bottom*inv), int(left*inv)

                last_boxes.append((top2, right2, bottom2, left2, color))
                last_labels.append((label, left2, top2, color))

            if frame_match:
                with state_lock:
                    cam_state[cam_id]["latest_match"] = frame_match

        for (top2, right2, bottom2, left2, color) in last_boxes:
            cv2.rectangle(frame, (left2, top2), (right2, bottom2), color, 2)

        for (label, left2, top2, color) in last_labels:
            cv2.putText(frame, label, (left2, max(20, top2 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3)
            cv2.putText(frame, label, (left2, max(20, top2 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ok:
            with state_lock:
                cam_state[cam_id]["latest_jpeg"] = jpg.tobytes()

        now = time.time()
        sleep_time = next_frame_time - now
        if sleep_time > 0:
            time.sleep(sleep_time)
        next_frame_time = max(next_frame_time + frame_interval, now + frame_interval)


def mjpeg_generator(cam_id):
    while True:
        with state_lock:
            frame = cam_state[cam_id]["latest_jpeg"]
        if frame is None:
            time.sleep(0.05)
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

        time.sleep(1.0 / STREAM_FPS)


@app.route("/video_feed/<cam_id>")
def video_feed(cam_id):
    if cam_id not in CAMERAS:
        return "Cámara no existe", 404
    return Response(mjpeg_generator(cam_id),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/last_match/<cam_id>")
def last_match(cam_id):
    if cam_id not in CAMERAS:
        return jsonify({"error": "Cámara no existe"}), 404
    with state_lock:
        return jsonify(cam_state[cam_id]["latest_match"])


@app.route("/monitor/<cam_id>")
def monitor(cam_id):
    if cam_id not in CAMERAS:
        return "Cámara no existe", 404
    # Obtener datos del usuario para la plantilla
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.nombre, p.apellido, p.foto
        FROM usuarios u
        JOIN personas p ON u.id_persona = p.id_persona
        WHERE u.id_usuario = %s
    """, (session.get("user_id"),))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()

    if usuario and usuario.get("foto"):
        if isinstance(usuario["foto"], (bytes, bytearray)):
            usuario["foto"] = usuario["foto"].decode("utf-8")
    else:
        if usuario:
            usuario["foto"] = None

    return render_template("monitor.html", cam_id=cam_id, nombre_cam=CAMERAS[cam_id]["nombre"], usuario=usuario)


@app.route("/cameras_status")
def cameras_status():
    out = {}
    with state_lock:
        for cam_id in CAMERAS.keys():
            out[cam_id] = {
                "source": CAMERAS[cam_id],
                "has_frame": cam_state[cam_id]["latest_jpeg"] is not None,
                "last_match_ts": cam_state[cam_id]["latest_match"].get("timestamp"),
            }
    return jsonify(out)


def start_camera_threads():
    for cam_id, cam_data in CAMERAS.items():
        t = threading.Thread(target=camera_loop, args=(cam_id, cam_data["source"]), daemon=True)
        t.start()

# =========================================================
# RUTAS CURSOS
# =========================================================   
@app.route('/cursos/nuevo', methods=['GET', 'POST'])
def crear_curso():

    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    usuario = obtener_usuario_sesion()

    conexion = get_db_connection()
    cursor = conexion.cursor()

    form_data = {}
    id_catedratico = request.form.get('id_catedratico', '')
    id_sede = request.form.get('id_sede', '')
    carrera = request.form.get('carrera', '')
    seccion = request.form.get('seccion', '')
    id_curso = request.form.get('id_curso', '')

    if request.method == 'POST':
        form_data = request.form.to_dict(flat=True)

        if not id_catedratico:
            flash('Seleccione un catedrático válido.', 'danger')
        elif not id_sede:
            flash('Seleccione una sede válida.', 'danger')
        elif not carrera:
            flash('Seleccione una carrera válida.', 'danger')
        elif not seccion:
            flash('Seleccione una sección válida.', 'danger')
        elif not id_curso:
            flash('Seleccione un curso válido.', 'danger')
        else:
            try:
                cursor.execute(
                    "SELECT id_rol_persona FROM roles_persona WHERE id_persona = %s AND tipo_persona = 'catedratico' AND activo = 1",
                    (id_catedratico,)
                )
                rol_result = cursor.fetchone()
                if not rol_result:
                    flash('El catedrático seleccionado no es válido o no está activo.', 'danger')
                else:
                    id_rol_persona = rol_result[0]
                    cursor.execute(
                        "SELECT s.id_seccion, s.id_sede_carrera FROM secciones s JOIN sede_carrera sc ON s.id_sede_carrera = sc.id_sede_carrera WHERE s.nombre = %s AND s.id_carrera = (SELECT id_carrera FROM carreras WHERE nombre = %s) AND sc.id_sede = %s LIMIT 1",
                        (seccion, carrera, id_sede)
                    )
                    seccion_row = cursor.fetchone()
                    if not seccion_row:
                        flash('La sección seleccionada no es válida para la sede/carrera seleccionada.', 'danger')
                    else:
                        id_seccion = seccion_row[0]
                        id_sede_carrera = seccion_row[1]
                        cursor.execute(
                            "SELECT COUNT(*) FROM cursos WHERE id_curso = %s AND id_sede_carrera = %s",
                            (id_curso, id_sede_carrera)
                        )
                        curso_valido = cursor.fetchone()
                        if not curso_valido or curso_valido[0] == 0:
                            flash('El curso seleccionado no pertenece a la sede/carrera/sección seleccionada.', 'danger')
                        else:
                            cursor.execute(
                                "INSERT INTO asignacion_cursos (id_curso, id_rol_persona, id_sede_carrera, id_seccion) VALUES (%s, %s, %s, %s)",
                                (id_curso, id_rol_persona, id_sede_carrera, id_seccion)
                            )
                            conexion.commit()
                            flash('Curso asignado al catedrático correctamente.', 'success')
                            cursor.close()
                            conexion.close()
                            return redirect(url_for('listar_cursos'))
            except Exception as e:
                conexion.rollback()
                flash(f'Error asignando curso: {e}', 'danger')

    cursor.execute("""
        SELECT p.id_persona, p.nombre, p.apellido
        FROM personas p
        JOIN roles_persona r ON p.id_persona = r.id_persona
        WHERE r.tipo_persona = 'catedratico'
          AND r.activo = 1
          AND p.estado = 'activo'
        ORDER BY p.nombre, p.apellido
    """)
    catedraticos = cursor.fetchall()

    sede_options = get_sede_options()
    carrera_options = []
    curso_options = []
    seccion_options = []

    if id_sede:
        try:
            carrera_options = get_carreras_for_sede(id_sede)
        except Exception:
            carrera_options = []

    if id_sede and carrera:
        curso_options = get_cursos_for_sede_carrera(id_sede, carrera)
        seccion_options = get_seccion_options(id_sede, carrera)

    cursor.close()
    conexion.close()

    return render_template(
        'cursos/nuevo.html',
        usuario=usuario,
        catedraticos=catedraticos,
        sede_options=sede_options,
        carrera_options=carrera_options,
        curso_options=curso_options,
        seccion_options=seccion_options,
        form_data=form_data
    )


@app.route('/admin/usuarios/nuevo', methods=['GET', 'POST'])
def admin_crear_usuario():
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        id_persona = request.form.get('id_persona')
        rol = request.form.get('rol')
        username = request.form.get('username')
        password = request.form.get('password')

        if id_persona and not rol:
            cursor.execute("SELECT tipo_persona FROM roles_persona WHERE id_persona=%s AND activo=1 LIMIT 1", (id_persona,))
            rr = cursor.fetchone()
            rol = rr['tipo_persona'] if rr else None

        if not (id_persona and rol and username and password):
            flash('Todos los campos son obligatorios.', 'warning')
            return redirect(url_for('admin_crear_usuario'))

        try:
            # crear usuario
            password_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO usuarios (id_persona, username, password, rol) VALUES (%s, %s, %s, %s)", (id_persona, username, password_hash, rol))

            # desactivar roles previos y añadir rol nuevo
            cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_persona=%s AND activo=1", (date.today(), id_persona))
            # insertar nuevo rol
            cursor.execute("SELECT carnet FROM personas WHERE id_persona=%s", (id_persona,))
            rr = cursor.fetchone()
            carnet = rr['carnet'] if rr else None
            cursor.execute("INSERT INTO roles_persona (id_persona, tipo_persona, carnet, fecha_inicio, activo) VALUES (%s, %s, %s, %s, 1)", (id_persona, rol, carnet, date.today()))

            conn.commit()
            flash('Usuario y rol creados correctamente.', 'success')
            return redirect(url_for('dashboard_admin'))
        except Exception as e:
            conn.rollback()
            flash(f'Error creando usuario: {e}', 'danger')
            return redirect(url_for('admin_crear_usuario'))

    # GET: listar personas sin usuario
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    q = request.args.get('q', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    results = []
    if q:
        like = f"%{q}%"
        cursor.execute("SELECT id_persona, nombre, apellido, carnet FROM personas WHERE (nombre LIKE %s OR apellido LIKE %s) AND estado='activo' ORDER BY nombre, apellido", (like, like))
        results = cursor.fetchall()
        
        # attach active roles with joins
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM personas WHERE id_persona=%s", (id_persona,))
    persona = cursor.fetchone()
    if not persona:
        cursor.close()
        conn.close()
        flash('Persona no encontrada', 'warning')
        return redirect(url_for('admin_roles'))

    # active roles with joins
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

    # obtener sedes
    cursor.execute("SELECT id_sede, nombre FROM sedes ORDER BY nombre")
    sedes = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_role_detail.html', persona=persona, active_roles=roles, carrera_options=get_carrera_options(), sedes=sedes)


@app.route('/personas/<int:id_persona>/cambiar-carrera', methods=['POST'])
def change_carrera_persona(id_persona):
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

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

        cursor.execute("SELECT id_rol_persona, tipo_persona, carnet, id_seccion, id_sede, id_carrera FROM roles_persona WHERE id_persona=%s AND activo=1", (id_persona,))
        current = cursor.fetchone()
        if not current:
            flash('No existe un rol activo para esta persona.', 'warning')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        if current['id_carrera'] == id_carrera:
            flash('La carrera seleccionada es la misma que la actual.', 'info')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s", (date.today(), current['id_rol_persona']))
        cursor.execute(
            "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    id_sede = request.form.get('id_sede')

    if not id_sede or not is_valid_sede(id_sede):
        flash('Debe seleccionar una sede válida.', 'warning')
        return redirect(url_for('admin_role_detail', id_persona=id_persona))

    id_sede = int(id_sede)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id_rol_persona, tipo_persona, carnet, id_seccion, id_sede, id_carrera FROM roles_persona WHERE id_persona=%s AND activo=1", (id_persona,))
        current = cursor.fetchone()
        if not current:
            flash('No existe un rol activo para esta persona.', 'warning')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        if current['id_sede'] == id_sede:
            flash('La sede seleccionada es la misma que la actual.', 'info')
            return redirect(url_for('admin_role_detail', id_persona=id_persona))

        cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s", (date.today(), current['id_rol_persona']))
        cursor.execute(
            "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
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
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    carrera = request.form.get('carrera')
    seccion = request.form.get('seccion')
    id_sede = request.form.get('id_sede')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id_rol_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede FROM roles_persona WHERE id_persona=%s AND activo=1", (id_persona,))
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

        cursor.execute("UPDATE roles_persona SET activo=0, fecha_fin=%s WHERE id_rol_persona=%s", (date.today(), current['id_rol_persona']))
        cursor.execute(
            "INSERT INTO roles_persona (id_persona, tipo_persona, carnet, id_carrera, id_seccion, id_sede, fecha_inicio, activo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)",
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

# ========================================================= 
# Lista de cursos
# =========================================================
@app.route('/cursos')
def listar_cursos():
    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    usuario = obtener_usuario_sesion()

    id_sede = request.args.get('id_sede', '')
    carrera = request.args.get('carrera', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursos = []
    carrera_options = []
    curso_options = []

    # Si hay sede seleccionada, traer carreras
    if id_sede:
        try:
            id_sede_int = int(id_sede)
            carrera_options = get_carreras_for_sede(id_sede_int)
        except Exception:
            pass

    # Si hay carrera seleccionada, traer cursos
    if id_sede and carrera:
        try:
            id_sede_int = int(id_sede)
            curso_options = get_cursos_for_sede_carrera(id_sede_int, carrera)
            
            # Obtener los cursos con información completa
            cursor.execute(
                "SELECT c.id_curso, c.nombre, ca.nombre AS carrera, sd.nombre AS sede "
                "FROM cursos c "
                "JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera "
                "JOIN carreras ca ON sc.id_carrera = ca.id_carrera "
                "JOIN sedes sd ON sc.id_sede = sd.id_sede "
                "WHERE sc.id_sede = %s AND ca.nombre = %s "
                "ORDER BY c.nombre",
                (id_sede_int, carrera)
            )
            cursos = cursor.fetchall()
        except Exception:
            pass

    cursor.close()
    conn.close()

    return render_template('cursos/listar.html',
                           usuario=usuario,
                           sede_options=get_sede_options(),
                           carrera_options=carrera_options,
                           curso_options=curso_options,
                           cursos=cursos,
                           id_sede=id_sede,
                           carrera=carrera)

# =========================================================
# Inscripción de estudiantes a cursos
# =========================================================

@app.route('/cursos/<int:id_curso>/inscribir', methods=['GET', 'POST'])
def inscribir_estudiantes(id_curso):

    if session.get("rol") != "administrativo":
        return redirect(url_for("login"))

    usuario = obtener_usuario_sesion()

    conexion = get_db_connection()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT c.id_curso, c.nombre, ca.nombre AS carrera, sd.nombre AS sede,
               sc.id_carrera, sc.id_sede_carrera
        FROM cursos c
        JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera
        JOIN carreras ca ON sc.id_carrera = ca.id_carrera
        JOIN sedes sd ON sc.id_sede = sd.id_sede
        WHERE c.id_curso = %s
    """, (id_curso,))
    curso = cursor.fetchone()

    if not curso:
        cursor.close()
        conexion.close()
        flash('Curso no encontrado.', 'danger')
        return redirect(url_for('listar_cursos'))

    curso_id, curso_nombre, carrera_curso, sede_curso, carrera_id, id_sede_carrera = curso

    cursor.execute("""
        SELECT DISTINCT s.nombre
        FROM asignacion_cursos ac
        JOIN secciones s ON ac.id_seccion = s.id_seccion
        WHERE ac.id_curso = %s
        ORDER BY s.nombre
    """, (id_curso,))
    section_options = [row[0] for row in cursor.fetchall()]

    if not section_options:
        # If the course is not yet assigned to a section, show available sections for its sede/carrera
        cursor.execute("""
            SELECT DISTINCT s.nombre
            FROM secciones s
            JOIN cursos c ON c.id_sede_carrera = s.id_sede_carrera
            WHERE c.id_curso = %s
            ORDER BY s.nombre
        """, (id_curso,))
        section_options = [row[0] for row in cursor.fetchall()]

    if request.method == 'POST':
        selected_section = request.form.get('seccion', '')
    else:
        selected_section = request.args.get('seccion', '')

    if selected_section not in section_options:
        selected_section = ''

    if not selected_section and len(section_options) == 1:
        selected_section = section_options[0]

    curso = (curso_id, curso_nombre, carrera_curso, sede_curso)
    catedratico_info = None

    section_id = None
    if selected_section:
        cursor.execute("""
            SELECT s.id_seccion
            FROM secciones s
            WHERE s.nombre = %s
              AND s.id_sede_carrera = %s
            LIMIT 1
        """, (selected_section, id_sede_carrera))
        section_row = cursor.fetchone()
        section_id = section_row[0] if section_row else None

        if section_id:
            cursor.execute("""
                SELECT p.id_persona, p.nombre, p.apellido
                FROM asignacion_cursos ac
                JOIN roles_persona r ON ac.id_rol_persona = r.id_rol_persona
                JOIN personas p ON r.id_persona = p.id_persona
                WHERE ac.id_curso = %s
                  AND ac.id_seccion = %s
                ORDER BY ac.id_asignacion DESC
                LIMIT 1
            """, (id_curso, section_id))
            prof_row = cursor.fetchone()
            if prof_row:
                catedratico_info = {
                    'id_persona': prof_row[0],
                    'nombre': f"{prof_row[1]} {prof_row[2]}"
                }

    if request.method == 'POST':
        id_asignacion = None
        if selected_section and section_id:
            cursor.execute("""
                SELECT ac.id_asignacion
                FROM asignacion_cursos ac
                WHERE ac.id_curso = %s
                  AND ac.id_seccion = %s
                LIMIT 1
            """, (id_curso, section_id))
            asignacion_row = cursor.fetchone()
            id_asignacion = asignacion_row[0] if asignacion_row else None

        estudiantes_seleccionados = request.form.getlist('estudiantes')
        for id_persona in estudiantes_seleccionados:
            cursor.execute("""
                SELECT id_rol_persona
                FROM roles_persona
                WHERE id_persona = %s
                  AND tipo_persona = 'estudiante'
                  AND activo = 1
                ORDER BY fecha_inicio DESC
                LIMIT 1
            """, (id_persona,))
            rol = cursor.fetchone()
            if not rol or id_asignacion is None:
                continue

            cursor.execute("""
                SELECT COUNT(*)
                FROM roles_persona rr
                WHERE rr.id_persona = %s
                  AND rr.tipo_persona = 'catedratico'
                  AND rr.activo = 1
            """, (id_persona,))
            if cursor.fetchone()[0] > 0:
                continue

            id_rol_persona = rol[0]
            cursor.execute("""
                SELECT COUNT(*)
                FROM inscripciones
                WHERE id_rol_persona = %s
                  AND id_asignacion = %s
            """, (id_rol_persona, id_asignacion))
            if cursor.fetchone()[0] == 0:
                try:
                    cursor.execute("""
                        INSERT INTO inscripciones (id_rol_persona, id_asignacion)
                        VALUES (%s, %s)
                    """, (id_rol_persona, id_asignacion))
                except mysql.connector.Error:
                    pass

        conexion.commit()
        cursor.close()
        conexion.close()

        flash('Estudiantes inscritos correctamente.', 'success')
        return redirect(url_for('listar_cursos'))

    estudiantes = []
    inscritos = []

    if selected_section and section_id:
        cursor.execute("""
            SELECT p.id_persona, p.carnet, p.nombre, p.apellido, p.correo
            FROM personas p
            JOIN roles_persona r ON p.id_persona = r.id_persona
            WHERE r.tipo_persona = 'estudiante'
              AND r.activo = 1
              AND r.id_carrera = %s
              AND r.id_seccion = %s
              AND p.estado = 'activo'
              AND NOT EXISTS (
                  SELECT 1 FROM roles_persona rr
                  WHERE rr.id_persona = p.id_persona
                    AND rr.tipo_persona = 'catedratico'
                    AND rr.activo = 1
              )
            ORDER BY p.nombre, p.apellido
        """, (carrera_id, section_id))
        estudiantes = cursor.fetchall()

        cursor.execute("""
            SELECT p.id_persona
            FROM inscripciones i
            JOIN roles_persona r ON i.id_rol_persona = r.id_rol_persona
            JOIN personas p ON r.id_persona = p.id_persona
            JOIN asignacion_cursos ac ON i.id_asignacion = ac.id_asignacion
            WHERE ac.id_curso = %s
              AND ac.id_seccion = %s
        """, (id_curso, section_id))
        inscritos = [fila[0] for fila in cursor.fetchall()]

    cursor.close()
    conexion.close()

    return render_template(
        'cursos/inscribir.html',
        curso=curso,
        section_options=section_options,
        selected_section=selected_section,
        estudiantes=estudiantes,
        inscritos=inscritos,
        catedratico_info=catedratico_info,
        usuario=usuario
    )
#=========================================================
#PARA QUE EL CATEDRATICO PUEDA VER SUS CURSOS Y ASISTENCIAS
# =========================================================
@app.route('/mis_cursos')
def mis_cursos():
    if session.get("rol") != "catedratico":
        return redirect(url_for("login"))

    usuario = obtener_usuario_sesion()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id_persona
        FROM usuarios
        WHERE id_usuario = %s
    """, (session.get("user_id"),))
    fila = cursor.fetchone()

    if not fila:
        cursor.close()
        conn.close()
        flash("No se encontró el usuario.", "danger")
        return redirect(url_for("login"))

    id_catedratico = fila["id_persona"]

    cursor.close()

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT c.id_curso,
               c.nombre AS nombre_curso,
               ca.nombre AS carrera,
               s.nombre AS seccion
        FROM cursos c
        JOIN asignacion_cursos ac ON c.id_curso = ac.id_curso
        JOIN roles_persona r ON ac.id_rol_persona = r.id_rol_persona
        JOIN secciones s ON ac.id_seccion = s.id_seccion
        JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera
        JOIN carreras ca ON sc.id_carrera = ca.id_carrera
        WHERE r.id_persona = %s
          AND r.tipo_persona = 'catedratico'
          AND r.activo = 1
        ORDER BY c.nombre
    """, (id_catedratico,))
    cursos = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'catedratico/mis_cursos.html',
        cursos=cursos,
        usuario=usuario
    )
# =========================================================
# PARA VER LAS ASISTENCIASDE LOS CURSOS DEL CATEDRATICO
# =========================================================
from datetime import date
import base64

@app.route('/curso/<int:id_curso>/asistencia', methods=['GET'])
def ver_asistencia_curso(id_curso):

    if session.get("rol") != "catedratico":
        flash('Debe iniciar sesión como catedrático.', 'danger')
        return redirect(url_for('login'))

    usuario = obtener_usuario_sesion()

    if not usuario:
        flash('Debe iniciar sesión.', 'danger')
        return redirect(url_for('login'))

    id_catedratico = usuario["id_persona"]
    fecha_hoy = date.today()

    conexion = get_db_connection()
    cursor = conexion.cursor(dictionary=True)

    # Obtener curso
    cursor.execute("""
        SELECT c.id_curso,
               c.nombre AS nombre_curso,
               ca.nombre AS carrera,
               s.nombre AS seccion
        FROM cursos c
        JOIN asignacion_cursos ac ON c.id_curso = ac.id_curso
        JOIN roles_persona r ON ac.id_rol_persona = r.id_rol_persona
        JOIN secciones s ON ac.id_seccion = s.id_seccion
        JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera
        JOIN carreras ca ON sc.id_carrera = ca.id_carrera
        WHERE c.id_curso = %s
          AND r.id_persona = %s
          AND r.tipo_persona = 'catedratico'
          AND r.activo = 1
        LIMIT 1
    """, (id_curso, id_catedratico))

    curso = cursor.fetchone()

    if not curso:
        cursor.close()
        conexion.close()
        flash('No tiene acceso a este curso.', 'danger')
        return redirect(url_for('mis_cursos'))

    # Obtener estudiantes inscritos
    cursor.execute("""
        SELECT p.id_persona, p.nombre, p.apellido, p.correo, p.foto, r.carnet
        FROM inscripciones i
        JOIN roles_persona r ON i.id_rol_persona = r.id_rol_persona
        JOIN personas p ON r.id_persona = p.id_persona
        JOIN asignacion_cursos ac ON i.id_asignacion = ac.id_asignacion
        WHERE ac.id_curso = %s
        ORDER BY p.nombre, p.apellido
    """, (id_curso,))

    estudiantes_db = cursor.fetchall()

    estudiantes = []

    for e in estudiantes_db:

        # revisar si tiene registro hoy
        cursor.execute("""
            SELECT ubicacion, tipo_registro, hora
            FROM registros_entrada
            WHERE id_persona = %s AND fecha = %s
            ORDER BY hora DESC
            LIMIT 1
        """, (e["id_persona"], fecha_hoy))

        registro = cursor.fetchone()

        presente = registro is not None

        foto_base64 = None
        if e["foto"]:
            if isinstance(e["foto"], (bytes, bytearray)):
                foto_base64 = base64.b64encode(e["foto"]).decode("utf-8")

        estudiantes.append({
            "id_persona": e["id_persona"],
            "nombre_completo": f'{e["nombre"]} {e["apellido"]}',
            "correo": e["correo"],
            "carnet": e["carnet"],
            "foto": foto_base64,
            "presente": presente,
            "ubicacion": registro["ubicacion"] if registro else None,
            "hora": registro["hora"] if registro else None
        })

    cursor.close()
    conexion.close()

    return render_template(
        'catedratico/arbol_asistencia.html',
        curso=curso,
        estudiantes=estudiantes,
        usuario=usuario
    )
# =========================================================
# RUTA DE CONFIRMAR ASISTENCIA
# =========================================================
@app.route('/curso/<int:id_curso>/confirmar_asistencia', methods=['POST'])
def confirmar_asistencia(id_curso):
    if session.get("rol") != "catedratico":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": False,
                "message": "Debe iniciar sesión como catedrático.",
                "redirect_url": url_for('login')
            }), 401

        flash('Debe iniciar sesión como catedrático.', 'danger')
        return redirect(url_for('login'))

    usuario = obtener_usuario_sesion()
    if not usuario:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": False,
                "message": "Debe iniciar sesión.",
                "redirect_url": url_for('login')
            }), 401

        flash('Debe iniciar sesión.', 'danger')
        return redirect(url_for('login'))

    fecha_hoy = date.today()

    conexion = get_db_connection()
    cursor = conexion.cursor(dictionary=True)

    try:
        # Obtener curso validando que pertenece al catedrático
        cursor.execute("""
            SELECT c.id_curso,
                   c.nombre AS nombre_curso,
                   ca.nombre AS carrera,
                   s.nombre AS seccion
            FROM cursos c
            JOIN asignacion_cursos ac ON c.id_curso = ac.id_curso
            JOIN roles_persona r ON ac.id_rol_persona = r.id_rol_persona
            JOIN secciones s ON ac.id_seccion = s.id_seccion
            JOIN sede_carrera sc ON c.id_sede_carrera = sc.id_sede_carrera
            JOIN carreras ca ON sc.id_carrera = ca.id_carrera
            WHERE c.id_curso = %s
              AND r.id_persona = %s
              AND r.tipo_persona = 'catedratico'
              AND r.activo = 1
            LIMIT 1
        """, (id_curso, usuario["id_persona"]))
        curso = cursor.fetchone()

        if not curso:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "success": False,
                    "message": "No tiene acceso a este curso.",
                    "redirect_url": url_for('mis_cursos')
                }), 403

            flash("No tiene acceso a este curso.", "danger")
            return redirect(url_for('mis_cursos'))

        # Obtener datos del docente
        cursor.execute("""
            SELECT id_persona, nombre, apellido, correo
            FROM personas
            WHERE id_persona = %s
        """, (usuario["id_persona"],))
        docente = cursor.fetchone()

        # Obtener estudiantes inscritos
        cursor.execute("""
            SELECT p.id_persona, p.nombre, p.apellido, p.correo, r.carnet
            FROM inscripciones i
            JOIN roles_persona r ON i.id_rol_persona = r.id_rol_persona
            JOIN personas p ON r.id_persona = p.id_persona
            JOIN asignacion_cursos ac ON i.id_asignacion = ac.id_asignacion
            WHERE ac.id_curso = %s
            ORDER BY p.nombre, p.apellido
        """, (id_curso,))
        estudiantes_db = cursor.fetchall()

        estudiantes_pdf = []

        for e in estudiantes_db:
            cursor.execute("""
                SELECT id_registro, ubicacion, hora
                FROM registros_entrada
                WHERE id_persona = %s AND fecha = %s
                ORDER BY hora DESC
                LIMIT 1
            """, (e["id_persona"], fecha_hoy))
            registro = cursor.fetchone()

            presente = registro is not None
            estado = 'presente' if presente else 'ausente'

            # Insertar asistencia si no existe
            cursor.execute("""
                SELECT id_asistencia
                FROM asistencias
                WHERE id_estudiante = %s AND id_curso = %s AND fecha = %s
            """, (e["id_persona"], id_curso, fecha_hoy))
            existe = cursor.fetchone()

            if not existe:
                cursor.execute("""
                    INSERT INTO asistencias (id_estudiante, id_curso, fecha, estado)
                    VALUES (%s, %s, %s, %s)
                """, (e["id_persona"], id_curso, fecha_hoy, estado))

            estudiantes_pdf.append({
                "id_persona": e["id_persona"],
                "nombre_completo": f"{e['nombre']} {e['apellido']}",
                "correo": e["correo"],
                "carnet": e["carnet"],
                "presente": presente
            })

        conexion.commit()

        # Generar PDF
        ruta_pdf, nombre_archivo = generar_pdf_asistencia(curso, docente, estudiantes_pdf, fecha_hoy)

        # Enviar correo
        try:
            enviar_pdf_por_correo(docente["correo"], ruta_pdf, curso)
        except Exception as e:
            print("Error enviando correo:", e)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": True,
                "message": "La asistencia fue confirmada, el PDF fue generado y el correo enviado.",
                "download_url": url_for('descargar_reporte_asistencia', nombre_archivo=nombre_archivo),
                "redirect_url": url_for('mis_cursos')
            })

        flash("La asistencia fue confirmada correctamente.", "success")
        return redirect(url_for('mis_cursos'))

    except Exception as e:
        conexion.rollback()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": False,
                "message": f"Ocurrió un error: {str(e)}"
            }), 500

        flash(f"Ocurrió un error: {str(e)}", "danger")
        return redirect(url_for('mis_cursos'))

    finally:
        cursor.close()
        conexion.close()
# =========================================================
# DESCARGAR PDF
# =========================================================
@app.route('/descargar_reporte_asistencia/<nombre_archivo>')
def descargar_reporte_asistencia(nombre_archivo):
    carpeta_reportes = os.path.join("static", "reportes")
    ruta_pdf = os.path.join(carpeta_reportes, nombre_archivo)

    if not os.path.exists(ruta_pdf):
        flash("El archivo PDF no existe.", "danger")
        return redirect(url_for('mis_cursos'))

    return send_file(ruta_pdf, as_attachment=True)


# =========================================================
# GENERAR PDF
# =========================================================
def generar_pdf_asistencia(curso, docente, estudiantes, fecha_hoy):
    carpeta_reportes = os.path.join("static", "reportes")
    os.makedirs(carpeta_reportes, exist_ok=True)

    nombre_archivo = f"asistencia_curso_{curso['id_curso']}_{fecha_hoy}.pdf"
    ruta_pdf = os.path.join(carpeta_reportes, nombre_archivo)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Logo
    logo_path = os.path.join("static", "img", "logo.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, 10, 10, 25)

    # Encabezado
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "UNIVERSIDAD MARIANO GALVEZ", ln=True, align="C")
    pdf.cell(0, 10, "DE GUATEMALA", ln=True, align="C")

    pdf.set_font("Times", "", 13)
    pdf.cell(0, 8, "REPORTE DE ASISTENCIA", ln=True, align="C")

    pdf.ln(16)

    # Datos del curso
    pdf.set_font("Arial", "B", 11)

    pdf.cell(35, 8, "Curso:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(70, 8, curso["nombre_curso"])

    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "Carrera:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, curso["carrera"], ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(35, 8, "Seccion:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(70, 8, curso["seccion"] if curso["seccion"] else "-")

    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "Fecha:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, str(fecha_hoy), ln=True)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(35, 8, "Catedratico:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(70, 8, f"{docente['nombre']} {docente['apellido']}")

    pdf.set_font("Arial", "B", 11)
    pdf.cell(30, 8, "Correo:")
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, docente["correo"], ln=True)

    pdf.ln(16)

    # Tabla
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 10)

    pdf.cell(10, 10, "No", 1, 0, "C", True)
    pdf.cell(30, 10, "Carnet", 1, 0, "C", True)
    pdf.cell(55, 10, "Nombre", 1, 0, "C", True)
    pdf.cell(60, 10, "Correo", 1, 0, "C", True)
    pdf.cell(35, 10, "Estado", 1, 1, "C", True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 9)

    for i, est in enumerate(estudiantes, start=1):
        estado = "PRESENTE" if est["presente"] else "AUSENTE"
        nombre = est["nombre_completo"][:28]
        correo = est["correo"][:32] if est["correo"] else ""

        pdf.cell(10, 10, str(i), 1, 0, "C")
        pdf.cell(30, 10, str(est["carnet"]) if est["carnet"] else "-", 1, 0, "C")
        pdf.cell(55, 10, nombre, 1, 0, "L")
        pdf.cell(60, 10, correo, 1, 0, "L")
        pdf.cell(35, 10, estado, 1, 1, "C")

    pdf.ln(10)
    pdf.output(ruta_pdf)

    return ruta_pdf, nombre_archivo


# =========================================================
# ENVIAR PDF POR CORREO
# =========================================================
def enviar_pdf_por_correo(destinatario, ruta_pdf, curso):
    remitente = "16mynorgomez@gmail.com"
    password = "yuef jvmk gisp trtb"

    msg = EmailMessage()
    msg["Subject"] = f"Reporte de asistencia - {curso['nombre_curso']}"
    msg["From"] = remitente
    msg["To"] = destinatario

    msg.set_content(
        f"Adjunto se envia el reporte oficial de asistencia del curso {curso['nombre_curso']}."
    )

    with open(ruta_pdf, "rb") as f:
        pdf_data = f.read()

    msg.add_attachment(
        pdf_data,
        maintype="application",
        subtype="pdf",
        filename=os.path.basename(ruta_pdf)
    )

    contexto = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto) as smtp:
        smtp.login(remitente, password)
        smtp.send_message(msg)
# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    start_camera_threads()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)