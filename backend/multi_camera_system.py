"""
Multi-Camera Chess Detection System
Manages multiple cameras around a room for robust chess board tracking
Handles occlusion, automatic failover, and best-angle selection
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
import threading
import time
from dataclasses import dataclass
from chess_detector import ChessBoardDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuration for a single camera in the multi-camera setup"""
    id: str
    source: int | str  # Camera index or URL
    position: str  # Description like "north", "south", "east", "west", "overhead"
    priority: int = 1  # Higher priority cameras preferred (1-10)
    enabled: bool = True


@dataclass
class CameraStatus:
    """Runtime status of a camera"""
    id: str
    active: bool = False
    calibrated: bool = False
    board_visible: bool = False
    quality_score: float = 0.0  # 0-100, higher is better
    last_successful_detection: float = 0.0
    obstruction_detected: bool = False


class MultiCameraChessSystem:
    """
    Manages multiple cameras for robust chess board detection
    Features:
    - Automatic failover when primary camera is blocked
    - Quality scoring to select best camera angle
    - Simultaneous monitoring of all cameras
    - Occlusion detection
    """

    def __init__(self, camera_configs: List[CameraConfig]):
        self.cameras = {}  # id -> cv2.VideoCapture
        self.detectors = {}  # id -> ChessBoardDetector
        self.configs = {config.id: config for config in camera_configs}
        self.statuses = {config.id: CameraStatus(id=config.id) for config in camera_configs}
        self.active_camera_id = None
        self.monitoring_active = False
        self.monitoring_thread = None
        self.lock = threading.Lock()

    def start_all_cameras(self) -> Dict[str, bool]:
        """
        Start all configured cameras
        Returns: dict mapping camera_id to success status
        """
        results = {}

        for cam_id, config in self.configs.items():
            if not config.enabled:
                results[cam_id] = False
                continue

            try:
                cap = cv2.VideoCapture(config.source)
                if cap.isOpened():
                    self.cameras[cam_id] = cap
                    self.detectors[cam_id] = ChessBoardDetector()
                    self.statuses[cam_id].active = True
                    results[cam_id] = True
                    logger.info(f"Camera {cam_id} ({config.position}) started")
                else:
                    results[cam_id] = False
                    logger.warning(f"Camera {cam_id} failed to open")
            except Exception as e:
                logger.error(f"Error starting camera {cam_id}: {e}")
                results[cam_id] = False

        return results

    def stop_all_cameras(self):
        """Stop all cameras and cleanup"""
        with self.lock:
            for cam_id, cap in self.cameras.items():
                if cap:
                    cap.release()
                self.statuses[cam_id].active = False
                self.statuses[cam_id].calibrated = False

            self.cameras.clear()
            self.detectors.clear()
            logger.info("All cameras stopped")

    def calibrate_all_cameras(self) -> Dict[str, bool]:
        """
        Attempt to calibrate all active cameras
        Returns: dict mapping camera_id to calibration success
        """
        results = {}

        for cam_id, cap in self.cameras.items():
            if not cap or not cap.isOpened():
                results[cam_id] = False
                continue

            ret, frame = cap.read()
            if not ret:
                results[cam_id] = False
                continue

            detector = self.detectors[cam_id]
            corners = detector.detect_board_corners(frame)

            if corners is not None:
                detector.board_corners = corners
                # Initialize board state
                warped = detector.extract_board_region(frame, corners)
                detector.previous_board_state = detector.detect_pieces(warped)

                self.statuses[cam_id].calibrated = True
                self.statuses[cam_id].board_visible = True
                results[cam_id] = True
                logger.info(f"Camera {cam_id} ({self.configs[cam_id].position}) calibrated")
            else:
                results[cam_id] = False
                logger.warning(f"Camera {cam_id} calibration failed - board not visible")

        return results

    def get_frame(self, cam_id: str) -> Optional[np.ndarray]:
        """Get current frame from a specific camera"""
        if cam_id not in self.cameras:
            return None

        cap = self.cameras[cam_id]
        if not cap or not cap.isOpened():
            return None

        ret, frame = cap.read()
        return frame if ret else None

    def calculate_quality_score(self, cam_id: str, frame: np.ndarray) -> float:
        """
        Calculate quality score for a camera view (0-100)
        Higher score = better view of the board

        Factors:
        - Board visibility
        - Image sharpness
        - Lighting quality
        - Occlusion detection
        """
        score = 0.0

        if cam_id not in self.detectors or not self.statuses[cam_id].calibrated:
            return 0.0

        detector = self.detectors[cam_id]

        # Check if board is still visible (50 points)
        corners = detector.detect_board_corners(frame)
        if corners is not None:
            score += 50.0
            self.statuses[cam_id].board_visible = True
        else:
            self.statuses[cam_id].board_visible = False
            return score

        # Calculate sharpness (25 points) - higher variance = sharper image
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if detector.board_corners is not None:
            warped = detector.extract_board_region(frame, detector.board_corners)
            gray_warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray_warped, cv2.CV_64F).var()
            sharpness_score = min(25.0, laplacian_var / 20.0)  # Normalize
            score += sharpness_score

        # Lighting quality (15 points) - check for good contrast
        mean_brightness = np.mean(gray)
        # Ideal brightness around 100-150
        brightness_score = 15.0 * (1 - abs(mean_brightness - 125) / 125)
        score += max(0, brightness_score)

        # Camera priority bonus (10 points)
        priority_score = (self.configs[cam_id].priority / 10.0) * 10.0
        score += priority_score

        return min(100.0, score)

    def select_best_camera(self) -> Optional[str]:
        """
        Select the best camera based on quality scores
        Returns: camera_id of best camera, or None if no cameras available
        """
        best_cam_id = None
        best_score = -1.0

        for cam_id in self.cameras.keys():
            status = self.statuses[cam_id]

            if not status.active or not status.calibrated or not status.board_visible:
                continue

            frame = self.get_frame(cam_id)
            if frame is None:
                continue

            quality_score = self.calculate_quality_score(cam_id, frame)
            status.quality_score = quality_score

            if quality_score > best_score:
                best_score = quality_score
                best_cam_id = cam_id

        if best_cam_id:
            logger.info(f"Selected camera {best_cam_id} (score: {best_score:.1f})")

        return best_cam_id

    def detect_move_from_best_camera(self) -> Optional[Dict[str, str]]:
        """
        Detect a chess move using the best available camera
        Returns: dict with 'from' and 'to' squares, or None
        """
        # Select best camera
        best_cam_id = self.select_best_camera()

        if not best_cam_id:
            logger.warning("No suitable camera available for move detection")
            return None

        # Update active camera if changed
        if self.active_camera_id != best_cam_id:
            logger.info(f"Switching from camera {self.active_camera_id} to {best_cam_id}")
            self.active_camera_id = best_cam_id

        # Get move from best camera
        frame = self.get_frame(best_cam_id)
        if frame is None:
            return None

        detector = self.detectors[best_cam_id]
        if not detector.board_corners is None:
            warped = detector.extract_board_region(frame, detector.board_corners)
            current_state = detector.detect_pieces(warped)

            move = detector.detect_move(detector.previous_board_state, current_state)

            if move:
                detector.previous_board_state = current_state
                self.statuses[best_cam_id].last_successful_detection = time.time()
                logger.info(f"Move detected from camera {best_cam_id}: {move['from']} -> {move['to']}")
                return move

        return None

    def start_monitoring(self):
        """Start background monitoring thread for camera health"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        logger.info("Camera monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=2.0)
        logger.info("Camera monitoring stopped")

    def _monitoring_loop(self):
        """Background thread that monitors camera health and quality"""
        while self.monitoring_active:
            for cam_id in self.cameras.keys():
                if not self.statuses[cam_id].active:
                    continue

                frame = self.get_frame(cam_id)
                if frame is not None:
                    quality = self.calculate_quality_score(cam_id, frame)
                    self.statuses[cam_id].quality_score = quality

                    # Detect potential obstruction
                    if quality < 30 and self.statuses[cam_id].calibrated:
                        self.statuses[cam_id].obstruction_detected = True
                    else:
                        self.statuses[cam_id].obstruction_detected = False

            time.sleep(1.0)  # Check every second

    def get_all_statuses(self) -> Dict[str, dict]:
        """Get status of all cameras for monitoring/debugging"""
        return {
            cam_id: {
                'position': self.configs[cam_id].position,
                'active': status.active,
                'calibrated': status.calibrated,
                'board_visible': status.board_visible,
                'quality_score': round(status.quality_score, 1),
                'obstruction_detected': status.obstruction_detected,
                'is_primary': cam_id == self.active_camera_id
            }
            for cam_id, status in self.statuses.items()
        }
