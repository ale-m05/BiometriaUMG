import json
import threading
import time
from datetime import date, datetime, timedelta

import cv2
import face_recognition
import numpy as np
from flask import Response, jsonify, render_template

from database import get_db_connection
from helpers import obtener_usuario_sesion

CAMERAS = {
    'cam1': {'nombre': 'Puerta Principal', 'ubicacion': 'Puerta Principal', 'source': 'http://10.159.145.12:4747/video'},
    'cam2': {'nombre': 'Salón 306', 'ubicacion': 'Salón 306', 'source': 'http://192.168.1.72:4747/video'},
}

SCALE = 0.35
TIPO_REGISTRO = 'puerta_principal'
RECOGNITION_LEVEL = 'medio'
RECOGNITION_PROFILES = {
    'facil': {'detect_model': 'hog', 'encoding_model': 'small', 'tolerance': 0.60},
    'medio': {'detect_model': 'hog', 'encoding_model': 'large', 'tolerance': 0.50},
    'avanzado': {'detect_model': 'cnn', 'encoding_model': 'large', 'tolerance': 0.45},
}
PROFILE = RECOGNITION_PROFILES[RECOGNITION_LEVEL]
DETECT_MODEL = PROFILE['detect_model']
ENCODING_MODEL = PROFILE['encoding_model']
TOLERANCE = PROFILE['tolerance']
MIN_SECONDS_BETWEEN_LOGS = 300
RECOGNIZE_EVERY_N_FRAMES = 15
STREAM_FPS = 20
JPEG_QUALITY = 45

cam_state = {}
last_log_time = {}
state_lock = threading.Lock()


def init_cam_state():
    for cam_id in CAMERAS.keys():
        cam_state[cam_id] = {
            'latest_jpeg': None,
            'latest_match': {
                'matched': False,
                'id_persona': None,
                'nombre': None,
                'apellido': None,
                'carnet': None,
                'correo': None,
                'dist': None,
                'timestamp': None,
                'cam_id': cam_id,
            },
            'last_log_time': last_log_time,
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
            enc_list = json.loads(r['encoding_facial'])
            enc = np.array(enc_list, dtype=np.float32)
            if enc.shape == (128,):
                known_encodings.append(enc)
                known_people.append({
                    'id_persona': r['id_persona'],
                    'nombre': r['nombre'],
                    'apellido': r['apellido'],
                    'carnet': r['carnet'],
                    'correo': r['correo'],
                })
        except Exception as e:
            print('Encoding inválido id_persona=%s: %s' % (r.get('id_persona'), e))

    print(f'✔ Encodings cargados: {len(known_encodings)}')
    return known_encodings, known_people


KNOWN_ENCODINGS, KNOWN_PEOPLE = load_known_faces()
if not KNOWN_ENCODINGS:
    print('⚠ No hay encodings en la base de datos (personas.activo con encoding_facial).')


def registrar_entrada(id_persona, ubicacion):
    conn = get_db_connection()
    cursor = conn.cursor()
    cutoff_time = (datetime.now() - timedelta(seconds=MIN_SECONDS_BETWEEN_LOGS)).time()
    cursor.execute(
        """
            SELECT COUNT(*)
            FROM registros_entrada
            WHERE id_persona = %s
              AND ubicacion = %s
              AND fecha = %s
              AND hora >= %s
        """,
        (id_persona, ubicacion, date.today(), cutoff_time)
    )
    already_logged = cursor.fetchone()[0]
    if already_logged == 0:
        cursor.execute(
            "INSERT INTO registros_entrada (id_persona, ubicacion, fecha, hora, tipo_registro) VALUES (%s, %s, %s, %s, %s)",
            (id_persona, ubicacion, date.today(), time.strftime('%H:%M:%S'), TIPO_REGISTRO)
        )
        conn.commit()
    else:
        print(f'Entrada ya registrada recientemente para persona={id_persona} ubicacion={ubicacion}')
    cursor.close()
    conn.close()


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
        print(f'[{cam_id}] No hay encodings para reconocimiento.')
        return

    print(f'[{cam_id}] Intentando abrir: {source}')
    cap = open_camera(source)
    if not cap.isOpened():
        print(f'[{cam_id}] ❌ No se pudo abrir la cámara: {source}')
        return
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
                    pid = person['id_persona']
                    now_ts = time.time()
                    with state_lock:
                        last_ts = cam_state[cam_id]['last_log_time'].get(pid, 0)
                    if now_ts - last_ts >= MIN_SECONDS_BETWEEN_LOGS:
                        try:
                            ubicacion_real = CAMERAS[cam_id]['ubicacion']
                            registrar_entrada(pid, ubicacion=ubicacion_real)
                            with state_lock:
                                cam_state[cam_id]['last_log_time'][pid] = now_ts
                        except Exception as e:
                            print(f'[{cam_id}] Error registrando entrada:', e)
                    frame_match = {
                        'matched': True,
                        'id_persona': pid,
                        'nombre': person['nombre'],
                        'apellido': person['apellido'],
                        'carnet': person['carnet'],
                        'correo': person['correo'],
                        'dist': round(best_distance, 4),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'cam_id': cam_id,
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
                    cam_state[cam_id]['latest_match'] = frame_match
        for (top2, right2, bottom2, left2, color) in last_boxes:
            cv2.rectangle(frame, (left2, top2), (right2, bottom2), color, 2)
        for (label, left2, top2, color) in last_labels:
            cv2.putText(frame, label, (left2, max(20, top2 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3)
            cv2.putText(frame, label, (left2, max(20, top2 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        ok, jpg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ok:
            with state_lock:
                cam_state[cam_id]['latest_jpeg'] = jpg.tobytes()
        now = time.time()
        sleep_time = next_frame_time - now
        if sleep_time > 0:
            time.sleep(sleep_time)
        next_frame_time = max(next_frame_time + frame_interval, now + frame_interval)


def mjpeg_generator(cam_id):
    while True:
        with state_lock:
            frame = cam_state[cam_id]['latest_jpeg']
        if frame is None:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(1.0 / STREAM_FPS)


def register_reconocimiento_routes(app):
    @app.route('/video_feed/<cam_id>')
    def video_feed(cam_id):
        if cam_id not in CAMERAS:
            return 'Cámara no existe', 404
        return Response(mjpeg_generator(cam_id), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route('/last_match/<cam_id>')
    def last_match(cam_id):
        if cam_id not in CAMERAS:
            return jsonify({'error': 'Cámara no existe'}), 404
        with state_lock:
            return jsonify(cam_state[cam_id]['latest_match'])

    @app.route('/monitor/<cam_id>')
    def monitor(cam_id):
        if cam_id not in CAMERAS:
            return 'Cámara no existe', 404
        usuario = obtener_usuario_sesion()
        return render_template('monitor.html', cam_id=cam_id, nombre_cam=CAMERAS[cam_id]['nombre'], usuario=usuario)

    @app.route('/cameras_status')
    def cameras_status():
        out = {}
        with state_lock:
            for cam_id in CAMERAS.keys():
                out[cam_id] = {
                    'source': CAMERAS[cam_id],
                    'has_frame': cam_state[cam_id]['latest_jpeg'] is not None,
                    'last_match_ts': cam_state[cam_id]['latest_match'].get('timestamp'),
                }
        return jsonify(out)


def start_camera_threads():
    for cam_id, cam_data in CAMERAS.items():
        t = threading.Thread(target=camera_loop, args=(cam_id, cam_data['source']), daemon=True)
        t.start()
