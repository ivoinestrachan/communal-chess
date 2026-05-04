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
        Returns: array of 4 corner points or None
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find the largest quadrilateral
        for contour in sorted(contours, key=cv2.contourArea, reverse=True):
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                return approx.reshape(4, 2)

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
        board_state = np.zeros((8, 8), dtype=int)
        square_size = warped_board.shape[0] // 8

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

        return board_state

    def _has_piece(self, square_img: np.ndarray) -> bool:
        """
        Determine if a square contains a piece using simple heuristics
        """
        # Convert to grayscale
        gray = cv2.cvtColor(square_img, cv2.COLOR_BGR2GRAY)

        # Calculate variance - pieces typically have more texture
        variance = np.var(gray)

        # Threshold - adjust based on your setup
        return variance > 200

    def detect_move(self, prev_state: np.ndarray, curr_state: np.ndarray) -> Optional[Dict[str, str]]:
        """
        Compare two board states to detect a move
        Returns: dict with 'from' and 'to' squares in chess notation
        """
        diff = curr_state - prev_state

        # Find squares that changed
        changed = np.argwhere(diff != 0)

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
                return move

        return None


class ChessCamera:
    """
    Manages camera feed and chess detection
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap = None
        self.detector = ChessBoardDetector()
        self.is_calibrated = False

    def start(self):
        """Start the camera"""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.camera_index}")
        logger.info(f"Camera {self.camera_index} started")

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
            return None

        frame = self.get_frame()
        if frame is None:
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
