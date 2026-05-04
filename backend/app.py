"""
Flask API for Chess Detection System
Provides WebSocket and REST endpoints for real-time chess piece tracking
"""

from flask import Flask, jsonify, request, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import cv2
import base64
import numpy as np
import logging
from chess_detector import ChessCamera
import threading
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Global camera instance
camera = None
detection_active = False


def detection_loop():
    """
    Background thread that continuously checks for moves
    """
    global camera, detection_active

    while detection_active:
        if camera and camera.is_calibrated:
            move = camera.detect_move()

            if move:
                # Emit move to all connected clients
                socketio.emit('move_detected', {
                    'from': move['from'],
                    'to': move['to'],
                    'timestamp': time.time()
                }, broadcast=True)

        time.sleep(0.5)  # Check every 500ms


def generate_frames():
    """
    Generator function for video streaming
    """
    global camera

    while True:
        if camera:
            frame = camera.get_frame()

            if frame is not None:
                # Draw board overlay if calibrated
                if camera.is_calibrated and camera.detector.board_corners is not None:
                    cv2.polylines(
                        frame,
                        [camera.detector.board_corners.astype(int)],
                        True,
                        (0, 255, 0),
                        3
                    )

                # Encode frame
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        time.sleep(0.033)  # ~30 FPS


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current system status"""
    return jsonify({
        'camera_active': camera is not None and camera.cap is not None,
        'calibrated': camera.is_calibrated if camera else False,
        'detection_active': detection_active
    })


@app.route('/api/camera/start', methods=['POST'])
def start_camera():
    """Start the camera"""
    global camera

    try:
        # Get camera index from JSON if provided, otherwise use default
        camera_index = 0
        if request.is_json and request.json:
            camera_index = request.json.get('camera_index', 0)

        if camera is None:
            camera = ChessCamera(camera_index=camera_index)

        camera.start()

        return jsonify({
            'success': True,
            'message': 'Camera started successfully'
        })
    except Exception as e:
        logger.error(f"Failed to start camera: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/camera/stop', methods=['POST'])
def stop_camera():
    """Stop the camera"""
    global camera, detection_active

    if camera:
        detection_active = False
        camera.stop()
        camera = None

        return jsonify({
            'success': True,
            'message': 'Camera stopped'
        })

    return jsonify({
        'success': False,
        'error': 'No camera active'
    }), 400


@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """Calibrate the chess board"""
    global camera

    if not camera:
        return jsonify({
            'success': False,
            'error': 'Camera not started'
        }), 400

    success = camera.calibrate()

    if success:
        return jsonify({
            'success': True,
            'message': 'Board calibrated successfully'
        })

    return jsonify({
        'success': False,
        'error': 'Could not detect board. Make sure the entire board is visible.'
    }), 400


@app.route('/api/detection/start', methods=['POST'])
def start_detection():
    """Start move detection"""
    global camera, detection_active

    if not camera or not camera.is_calibrated:
        return jsonify({
            'success': False,
            'error': 'Camera must be started and calibrated first'
        }), 400

    if not detection_active:
        detection_active = True
        thread = threading.Thread(target=detection_loop)
        thread.daemon = True
        thread.start()

    return jsonify({
        'success': True,
        'message': 'Detection started'
    })


@app.route('/api/detection/stop', methods=['POST'])
def stop_detection():
    """Stop move detection"""
    global detection_active

    detection_active = False

    return jsonify({
        'success': True,
        'message': 'Detection stopped'
    })


@app.route('/api/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    emit('connected', {'message': 'Connected to chess detection server'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')


@socketio.on('request_frame')
def handle_frame_request():
    """Send a single frame to the client"""
    global camera

    if camera:
        frame = camera.get_frame()
        if frame is not None:
            # Encode frame to base64
            ret, buffer = cv2.imencode('.jpg', frame)
            if ret:
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                emit('frame', {'image': frame_base64})


if __name__ == '__main__':
    logger.info("Starting Chess Detection Server...")
    logger.info("Server will run on http://localhost:5001")
    logger.info("WebSocket endpoint: ws://localhost:5001")

    # Run the server
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
