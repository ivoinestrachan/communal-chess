"""
Chess Board Detection System
Detects chess piece movements from a camera feed in real-time
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChessBoardDetector:
    """
    Detects and tracks chess piece movements on a physical chess board
    """

    def __init__(self):
        self.board_corners = None
        self.previous_board_state = None
        self.current_board_state = None
        self.square_size = None

    def detect_board_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect the four corners of the chess board using edge detection
        Enhanced to work with decorative/ornate boards
        Returns: array of 4 corner points or None
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Try multiple edge detection strategies
        # Strategy 1: Standard Canny with adaptive thresholds
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # Calculate adaptive thresholds based on image statistics
        median = np.median(gray)
        lower = int(max(0, 0.7 * median))
        upper = int(min(255, 1.3 * median))

        edges = cv2.Canny(blur, lower, upper)

        # Dilate edges to connect broken lines
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by size and shape
        frame_area = frame.shape[0] * frame.shape[1]
        min_area = frame_area * 0.1  # Board should be at least 10% of frame
        max_area = frame_area * 0.9  # But not the entire frame

        valid_contours = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                peri = cv2.arcLength(contour, True)
                # Try different epsilon values for approximation
                for epsilon_mult in [0.01, 0.02, 0.03, 0.04, 0.05]:
                    approx = cv2.approxPolyDP(contour, epsilon_mult * peri, True)
                    if len(approx) == 4:
                        # Check if it's roughly square-shaped
                        (x, y, w, h) = cv2.boundingRect(approx)
                        aspect_ratio = w / float(h) if h > 0 else 0
                        if 0.7 < aspect_ratio < 1.3:  # Allow some tolerance
                            valid_contours.append((area, approx))
                            break

        # Return largest valid quadrilateral
        if valid_contours:
            valid_contours.sort(reverse=True, key=lambda x: x[0])
            return valid_contours[0][1].reshape(4, 2)

        return None

    def get_square_coordinates(self, board_corners: np.ndarray) -> Dict[str, Tuple[int, int]]:
        """
        Convert board corners to individual square coordinates
        Returns: dict mapping chess notation (e.g., 'e4') to pixel coordinates
        """
        # Order corners: top-left, top-right, bottom-right, bottom-left
        corners = self._order_corners(board_corners)

        # Calculate width and height
        width = int(np.linalg.norm(corners[1] - corners[0]))
        height = int(np.linalg.norm(corners[3] - corners[0]))

        # Destination points for perspective transform
        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype=np.float32)

        square_coords = {}
        square_width = width / 8
        square_height = height / 8

        # Generate coordinates for all 64 squares
        files = 'abcdefgh'
        for rank in range(8):
            for file_idx in range(8):
                file_name = files[file_idx]
                rank_name = str(8 - rank)  # Chess ranks go from 8 to 1
                square = f"{file_name}{rank_name}"

                # Center of the square
                x = int((file_idx + 0.5) * square_width)
                y = int((rank + 0.5) * square_height)

                square_coords[square] = (x, y)

        return square_coords

    def _order_corners(self, corners: np.ndarray) -> np.ndarray:
        """
        Order corners as: top-left, top-right, bottom-right, bottom-left
        """
        rect = np.zeros((4, 2), dtype=np.float32)

        # Sum and difference to find corners
        s = corners.sum(axis=1)
        diff = np.diff(corners, axis=1)

        rect[0] = corners[np.argmin(s)]  # Top-left
        rect[2] = corners[np.argmax(s)]  # Bottom-right
        rect[1] = corners[np.argmin(diff)]  # Top-right
        rect[3] = corners[np.argmax(diff)]  # Bottom-left

        return rect

    def extract_board_region(self, frame: np.ndarray, corners: np.ndarray) -> np.ndarray:
        """
        Extract and warp the chess board region to a flat view
        """
        corners = self._order_corners(corners)

        width = 800  # Fixed output size
        height = 800

        dst = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(corners, dst)
        warped = cv2.warpPerspective(frame, matrix, (width, height))

        return warped

    def detect_pieces(self, warped_board: np.ndarray) -> np.ndarray:
        """
        Detect which squares have pieces on them
        Returns: 8x8 array where 1 = piece present, 0 = empty
        """
        try:
            logger.info(f"detect_pieces called with board shape: {warped_board.shape}")
            board_state = np.zeros((8, 8), dtype=int)
            square_size = warped_board.shape[0] // 8

            piece_count = 0
            for row in range(8):
                for col in range(8):
                    # Extract square region
                    x1 = col * square_size
                    y1 = row * square_size
                    x2 = x1 + square_size
                    y2 = y1 + square_size

                    square = warped_board[y1:y2, x1:x2]

                    # Check if piece is present using color/edge detection
                    if self._has_piece(square):
                        board_state[row, col] = 1
                        piece_count += 1

            logger.info(f"Detected {piece_count} pieces on board")
            return board_state
        except Exception as e:
            logger.error(f"Error in detect_pieces: {e}", exc_info=True)
            return np.zeros((8, 8), dtype=int)

    def _has_piece(self, square_img: np.ndarray) -> bool:
        """
        Determine if a square contains a piece using multiple detection methods
        MUCH MORE STRICT for glass boards to avoid false positives
        """
        # Convert to grayscale
        gray = cv2.cvtColor(square_img, cv2.COLOR_BGR2GRAY)

        # Method 1: Texture variance (pieces have more detail)
        variance = np.var(gray)

        # Method 2: Edge density (pieces have more edges)
        edges = cv2.Canny(gray, 50, 150)  # Higher thresholds
        edge_density = np.sum(edges > 0) / edges.size

        # Method 3: Height detection using blur difference
        blur1 = cv2.GaussianBlur(gray, (5, 5), 0)
        blur2 = cv2.GaussianBlur(gray, (15, 15), 0)
        height_hint = np.abs(blur1.astype(float) - blur2.astype(float)).mean()

        # Method 4: Check center region (pieces usually occupy center)
        h, w = gray.shape
        center_region = gray[h//4:3*h//4, w//4:3*w//4]
        center_variance = np.var(center_region)

        # Method 5: Color saturation (pieces might have different color)
        hsv = cv2.cvtColor(square_img, cv2.COLOR_BGR2HSV)
        saturation_mean = np.mean(hsv[:, :, 1])

        # Method 6: Brightness difference from edges to center (pieces cast shadows)
        edge_region = np.concatenate([
            gray[0:h//4, :].flatten(),
            gray[3*h//4:h, :].flatten(),
            gray[:, 0:w//4].flatten(),
            gray[:, 3*w//4:w].flatten()
        ])
        edge_brightness = np.mean(edge_region)
        center_brightness = np.mean(center_region)
        brightness_diff = abs(edge_brightness - center_brightness)

        # MUCH MORE STRICT thresholds for glass boards
        has_texture = variance > 200  # High threshold
        has_edges = edge_density > 0.08  # Much higher threshold
        has_height = height_hint > 5  # More strict
        has_center_detail = center_variance > 150  # Much higher
        has_color = saturation_mean > 30  # Higher color requirement
        has_shadow = brightness_diff > 15  # More noticeable shadow required

        # Piece detected if AT LEAST 3 out of 6 methods agree (was 2)
        score = sum([has_texture, has_edges, has_height, has_center_detail, has_color, has_shadow])

        return score >= 3

    def detect_move(self, prev_state: np.ndarray, curr_state: np.ndarray) -> Optional[Dict[str, str]]:
        """
        Compare two board states to detect a move
        Returns: dict with 'from' and 'to' squares in chess notation
        """
        diff = curr_state - prev_state

        # Find squares that changed
        changed = np.argwhere(diff != 0)

        # Log detection attempt for debugging
        if len(changed) > 0:
            logger.debug(f"Detected {len(changed)} changed squares")

        if len(changed) == 2:
            # Exactly 2 squares changed - likely a valid move
            files = 'abcdefgh'

            move = {}
            for row, col in changed:
                square = f"{files[col]}{8 - row}"

                if diff[row, col] == -1:
                    # Piece left this square
                    move['from'] = square
                elif diff[row, col] == 1:
                    # Piece arrived at this square
                    move['to'] = square

            if 'from' in move and 'to' in move:
                logger.info(f"Valid move found: {move['from']} -> {move['to']}")
                return move
        elif len(changed) > 0:
            logger.debug(f"Invalid move: {len(changed)} squares changed (expected 2)")

        return None


class ChessCamera:
    """
    Manages camera feed and chess detection
    Supports multiple camera sources:
    - Built-in webcam (index 0)
    - External USB cameras (index 1, 2, etc.)
    - IP camera streams (RTSP/HTTP URLs)
    - Phone camera via IP Webcam app
    """

    def __init__(self, camera_source: int | str = 0):
        """
        Initialize camera with flexible source

        Args:
            camera_source: Can be:
                - int: Camera index (0 for built-in, 1+ for external)
                - str: RTSP/HTTP stream URL (e.g., 'rtsp://192.168.1.100:8080/h264')
                       or IP Webcam URL (e.g., 'http://192.168.1.100:8080/video')
        """
        self.camera_source = camera_source
        self.cap = None
        self.detector = ChessBoardDetector()
        self.is_calibrated = False

    def start(self):
        """Start the camera"""
        self.cap = cv2.VideoCapture(self.camera_source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera source: {self.camera_source}")

        # Log camera info
        if isinstance(self.camera_source, int):
            logger.info(f"Camera {self.camera_source} started")
        else:
            logger.info(f"Camera stream started: {self.camera_source}")

    def stop(self):
        """Stop the camera"""
        if self.cap:
            self.cap.release()
            logger.info("Camera stopped")

    def calibrate(self) -> bool:
        """
        Calibrate the board position
        Returns: True if calibration successful
        """
        if not self.cap:
            return False

        ret, frame = self.cap.read()
        if not ret:
            return False

        corners = self.detector.detect_board_corners(frame)
        if corners is not None:
            self.detector.board_corners = corners
            self.is_calibrated = True

            # Initialize board state
            warped = self.detector.extract_board_region(frame, corners)
            self.detector.previous_board_state = self.detector.detect_pieces(warped)

            logger.info("Board calibrated successfully")
            return True

        logger.warning("Could not detect board corners")
        return False

    def get_frame(self) -> Optional[np.ndarray]:
        """Get current camera frame"""
        if not self.cap:
            return None

        ret, frame = self.cap.read()
        return frame if ret else None

    def detect_move(self) -> Optional[Dict[str, str]]:
        """
        Detect if a move was made
        Returns: dict with 'from' and 'to' squares or None
        """
        if not self.is_calibrated:
            logger.warning("detect_move called but camera not calibrated")
            return None

        try:
            frame = self.get_frame()
            if frame is None:
                logger.warning("Could not get frame from camera")
                return None

            warped = self.detector.extract_board_region(frame, self.detector.board_corners)
            current_state = self.detector.detect_pieces(warped)

            move = self.detector.detect_move(
                self.detector.previous_board_state,
                current_state
            )

            if move:
                self.detector.previous_board_state = current_state
                logger.info(f"Move detected: {move['from']} -> {move['to']}")

            return move
        except Exception as e:
            logger.error(f"Error in detect_move: {e}", exc_info=True)
            return None
