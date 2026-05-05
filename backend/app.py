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
from multi_camera_system import MultiCameraChessSystem, CameraConfig
import threading
import time

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*")

# Global camera instances
camera = None  # Single camera mode (legacy)
multi_camera_system = None  # Multi-camera mode
detection_active = False
use_multi_camera = False  # Toggle between single/multi camera mode


def detection_loop():
    """
    Background thread that continuously checks for moves
    Supports both single-camera and multi-camera modes
    """
    global camera, multi_camera_system, detection_active, use_multi_camera

    logger.info("Detection loop started")
    scan_count = 0

    while detection_active:
        move = None
        scan_count += 1

        if use_multi_camera and multi_camera_system:
            # Multi-camera mode: automatically select best camera
            move = multi_camera_system.detect_move_from_best_camera()
        elif camera and camera.is_calibrated:
            # Single camera mode
            if scan_count % 5 == 1:  # Log every 5th scan to avoid spam
                logger.info(f"Scan #{scan_count}: Actively scanning for moves...")
            move = camera.detect_move()
        else:
            logger.warning("Camera not calibrated or not available")

        if move:
            # Emit move to all connected clients
            logger.info(f"MOVE DETECTED! Emitting: {move['from']} -> {move['to']}")
            socketio.emit('move_detected', {
                'from': move['from'],
                'to': move['to'],
                'timestamp': time.time()
            })

        time.sleep(0.5)  # Check every 500ms

    logger.info("Detection loop stopped")


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


@app.route('/api/cameras/list', methods=['GET'])
def list_cameras():
    """
    Detect available cameras on the system
    Returns list of camera indices that can be opened
    """
    available_cameras = []

    # Try first 10 camera indices
    for index in range(10):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            # Get camera name if available
            backend_name = cap.getBackendName()
            available_cameras.append({
                'index': index,
                'name': f'Camera {index}',
                'backend': backend_name
            })
            cap.release()

    return jsonify({
        'success': True,
        'cameras': available_cameras
    })


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current system status"""
    global camera, multi_camera_system, use_multi_camera

    if use_multi_camera and multi_camera_system:
        return jsonify({
            'mode': 'multi_camera',
            'detection_active': detection_active,
            'cameras': multi_camera_system.get_all_statuses(),
            'active_camera': multi_camera_system.active_camera_id
        })
    else:
        return jsonify({
            'mode': 'single_camera',
            'camera_active': camera is not None and camera.cap is not None,
            'calibrated': camera.is_calibrated if camera else False,
            'detection_active': detection_active
        })


@app.route('/api/debug/warped', methods=['GET'])
def debug_warped():
    """Save the current warped board image to /tmp/warped_board.png with grid overlay.
    Use this to verify the 8x8 grid alignment matches the physical squares."""
    global camera

    if not camera or not camera.is_calibrated or camera.detector.board_corners is None:
        return jsonify({'success': False, 'error': 'Camera not calibrated'}), 400

    frame = camera.get_frame()
    if frame is None:
        return jsonify({'success': False, 'error': 'No frame'}), 500

    warped = camera.detector.extract_board_region(frame, camera.detector.board_corners)
    overlay = warped.copy()
    sq = warped.shape[0] // 8
    for i in range(9):
        cv2.line(overlay, (i * sq, 0), (i * sq, warped.shape[0]), (0, 255, 0), 1)
        cv2.line(overlay, (0, i * sq), (warped.shape[1], i * sq), (0, 255, 0), 1)

    cv2.imwrite('/tmp/warped_board.png', overlay)
    cv2.imwrite('/tmp/warped_board_clean.png', warped)
    return jsonify({
        'success': True,
        'message': 'Saved /tmp/warped_board.png (with grid) and /tmp/warped_board_clean.png'
    })


@app.route('/api/camera/start', methods=['POST'])
def start_camera():
    """
    Start the camera with flexible source support

    Request JSON params:
    - camera_source: int (0, 1, 2...) or str (URL for IP camera/stream)
    - camera_index: int (deprecated, use camera_source instead)

    Examples:
    {"camera_source": 0}  # Built-in webcam
    {"camera_source": 1}  # External USB camera
    {"camera_source": "http://192.168.1.100:8080/video"}  # Phone camera
    {"camera_source": "rtsp://192.168.1.100:8080/h264"}  # RTSP stream
    """
    global camera

    try:
        # Get camera source from JSON
        camera_source = 0  # Default to built-in webcam
        if request.is_json and request.json:
            # Support both new 'camera_source' and legacy 'camera_index'
            camera_source = request.json.get('camera_source',
                                            request.json.get('camera_index', 0))

        if camera is None:
            camera = ChessCamera(camera_source=camera_source)

        camera.start()

        return jsonify({
            'success': True,
            'message': f'Camera started successfully: {camera_source}'
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
    """
    Calibrate the chess board
    Optionally accepts manual corner coordinates if auto-detection fails
    """
    global camera

    if not camera:
        return jsonify({
            'success': False,
            'error': 'Camera not started'
        }), 400

    # Check if manual corners provided
    data = request.json if request.is_json else None
    if data and 'corners' in data:
        # Manual calibration with provided corners
        corners = np.array(data['corners'], dtype=np.float32)
        camera.detector.board_corners = corners

        # Capture reference snapshot for diff-based detection
        ret, frame = camera.cap.read()
        if ret:
            warped = camera.detector.extract_board_region(frame, corners)
            camera.detector.set_reference(warped)
            camera.is_calibrated = True
            logger.info("Board calibrated manually with provided corners")
            return jsonify({
                'success': True,
                'message': 'Board calibrated manually'
            })

    # Automatic calibration
    success = camera.calibrate()

    if success:
        return jsonify({
            'success': True,
            'message': 'Board calibrated successfully'
        })

    return jsonify({
        'success': False,
        'error': 'Could not detect board edges automatically. Tips: Ensure good lighting, clear board edges, and full board visibility. You may need to manually select corners.'
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


# Multi-Camera System Endpoints

@app.route('/api/multi-camera/setup', methods=['POST'])
def setup_multi_camera():
    """
    Setup multi-camera system with multiple camera sources

    Request JSON:
    {
        "cameras": [
            {"id": "north", "source": 0, "position": "north", "priority": 10},
            {"id": "south", "source": 1, "position": "south", "priority": 8},
            {"id": "east", "source": "http://192.168.1.100:8080/video", "position": "east", "priority": 5},
            {"id": "west", "source": 2, "position": "west", "priority": 5}
        ]
    }
    """
    global multi_camera_system, use_multi_camera, camera

    try:
        data = request.json
        if not data or 'cameras' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing cameras configuration'
            }), 400

        # Create camera configs
        camera_configs = []
        for cam_data in data['cameras']:
            config = CameraConfig(
                id=cam_data['id'],
                source=cam_data['source'],
                position=cam_data.get('position', cam_data['id']),
                priority=cam_data.get('priority', 5),
                enabled=cam_data.get('enabled', True)
            )
            camera_configs.append(config)

        # Stop single camera if active
        if camera:
            camera.stop()
            camera = None

        # Initialize multi-camera system
        multi_camera_system = MultiCameraChessSystem(camera_configs)
        use_multi_camera = True

        # Start all cameras
        results = multi_camera_system.start_all_cameras()

        return jsonify({
            'success': True,
            'message': 'Multi-camera system initialized',
            'camera_statuses': results
        })

    except Exception as e:
        logger.error(f"Failed to setup multi-camera system: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/multi-camera/calibrate', methods=['POST'])
def calibrate_multi_camera():
    """Calibrate all cameras in the multi-camera system"""
    global multi_camera_system

    if not multi_camera_system:
        return jsonify({
            'success': False,
            'error': 'Multi-camera system not initialized'
        }), 400

    results = multi_camera_system.calibrate_all_cameras()

    # Start monitoring after calibration
    multi_camera_system.start_monitoring()

    return jsonify({
        'success': True,
        'message': 'Cameras calibrated',
        'calibration_results': results
    })


@app.route('/api/multi-camera/status', methods=['GET'])
def get_multi_camera_status():
    """Get detailed status of all cameras"""
    global multi_camera_system

    if not multi_camera_system:
        return jsonify({
            'success': False,
            'error': 'Multi-camera system not initialized'
        }), 400

    return jsonify({
        'success': True,
        'cameras': multi_camera_system.get_all_statuses(),
        'active_camera': multi_camera_system.active_camera_id
    })


@app.route('/api/multi-camera/stop', methods=['POST'])
def stop_multi_camera():
    """Stop the multi-camera system"""
    global multi_camera_system, use_multi_camera, detection_active

    if multi_camera_system:
        detection_active = False
        multi_camera_system.stop_monitoring()
        multi_camera_system.stop_all_cameras()
        multi_camera_system = None
        use_multi_camera = False

        return jsonify({
            'success': True,
            'message': 'Multi-camera system stopped'
        })

    return jsonify({
        'success': False,
        'error': 'No multi-camera system active'
    }), 400


if __name__ == '__main__':
    logger.info("Starting Chess Detection Server...")
    logger.info("Server will run on http://localhost:5001")
    logger.info("WebSocket endpoint: ws://localhost:5001")

    # Run the server
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
