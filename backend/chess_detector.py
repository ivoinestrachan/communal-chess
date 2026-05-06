"""
Chess Board Detection System
Detects chess piece movements from a camera feed in real-time
"""

import cv2
import numpy as np
import os
from typing import Dict, List, Tuple, Optional
import logging
from sklearn.neighbors import KNeighborsClassifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set CHESS_BOARD_FLIPPED=1 if your camera sees white at the top of the image
# (camera is on the white player's side). When flipped, square labels are
# rotated 180 degrees so detected moves match standard chess notation.
BOARD_FLIPPED = os.environ.get('CHESS_BOARD_FLIPPED', '1') == '1'

# Path to the YOLO chess-piece detection model. Downloaded once during setup.
# Default to the larger yolov8m model (52MB) — better recall than yolo11n on
# unusual boards, at the cost of ~3x inference time. Override via env if needed.
_default_model = 'chess_yolo_m.pt' if os.path.exists(
    os.path.join(os.path.dirname(__file__), 'chess_yolo_m.pt')
) else 'chess_yolo.pt'
YOLO_MODEL_PATH = os.environ.get(
    'CHESS_YOLO_MODEL',
    os.path.join(os.path.dirname(__file__), _default_model)
)

# Class labels for board state representation
EMPTY = 0
WHITE = 1
BLACK = 2


class YOLOPieceDetector:
    """Wraps a pretrained YOLO chess-piece detector and exposes a method that
    returns an 8x8 array of {EMPTY, WHITE, BLACK} for a warped board image.

    The model has 12 classes (white_pawn, white_knight, ..., black_king); we
    collapse to white/black/empty for the move-detection diff. SAN, captures,
    promotion, etc. are still handled by chess.js on the frontend.
    """

    def __init__(self, model_path: str = YOLO_MODEL_PATH) -> None:
        from ultralytics import YOLO  # local import: torch is heavy
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"YOLO chess model not found at {model_path}. "
                f"Download it from HuggingFace (yamero999/chess-piece-detection-yolo11n)."
            )
        self.model = YOLO(model_path)
        self.names: Dict[int, str] = self.model.names
        # Pre-compute color per class index so per-frame inference is fast
        self._class_to_color: Dict[int, int] = {}
        for idx, name in self.names.items():
            if name.startswith('white_'):
                self._class_to_color[idx] = WHITE
            elif name.startswith('black_'):
                self._class_to_color[idx] = BLACK
            else:
                self._class_to_color[idx] = EMPTY  # unexpected class
        logger.info(f"YOLO chess model loaded with {len(self.names)} classes")

    def predict_board(self, warped_board: np.ndarray, conf: float = 0.01) -> np.ndarray:
        """Run YOLO on the warped 800x800 board and return an 8x8 array of
        {EMPTY, WHITE, BLACK} indicating piece color per square.

        Each detection is snapped to its nearest grid square by box center.
        If multiple detections fall in the same square (rare), the highest-
        confidence one wins.

        Default conf=0.01 (1%) to catch all pieces - we rely on board-square
        snapping and chess.js validation, not raw YOLO confidence.
        Very low threshold needed for non-standard piece designs.
        """
        results = self.model(warped_board, conf=conf, verbose=False)
        board = np.full((8, 8), EMPTY, dtype=np.int8)
        if not results:
            logger.warning("YOLO returned no results")
            return board
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            logger.warning("YOLO returned no boxes")
            return board

        sq = warped_board.shape[0] // 8
        # Track best confidence per square so a stronger detection wins
        best_conf = np.zeros((8, 8), dtype=np.float32)
        total_pieces_detected = 0

        for box in boxes:
            cls = int(box.cls.item())
            piece_name = self.names.get(cls, '')

            # Skip "board" class - we only want individual pieces
            if piece_name == 'board' or not piece_name.startswith(('white_', 'black_')):
                continue

            conf_score = float(box.conf.item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            col = int(cx // sq)
            row = int(cy // sq)
            if not (0 <= row < 8 and 0 <= col < 8):
                continue
            color = self._class_to_color.get(cls, EMPTY)
            if conf_score > best_conf[row, col]:
                best_conf[row, col] = conf_score
                board[row, col] = color
                total_pieces_detected += 1

        logger.debug(f"YOLO detected {total_pieces_detected} pieces (conf >= {conf})")
        return board


def extract_square_features(square_img: np.ndarray) -> np.ndarray:
    """Extract a fixed-length feature vector describing one chess square's contents.
    Used by both training (during calibration) and inference (per scan).
    """
    if square_img.size == 0:
        return np.zeros(11, dtype=np.float32)

    gray = cv2.cvtColor(square_img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(square_img, cv2.COLOR_BGR2HSV)
    h, w = gray.shape

    # Center patch (where the piece body sits)
    cy0, cy1 = h // 3, 2 * h // 3
    cx0, cx1 = w // 3, 2 * w // 3
    center = gray[cy0:cy1, cx0:cx1]

    # Edge ring (approximation: outer 1/4 frame, where the square color shows
    # even when a piece is centered)
    edge_mask = np.ones_like(gray, dtype=bool)
    edge_mask[h // 4:3 * h // 4, w // 4:3 * w // 4] = False
    edge_pixels = gray[edge_mask]

    edges = cv2.Canny(gray, 50, 150)

    return np.array([
        float(np.mean(gray)),               # overall brightness
        float(np.std(gray)),                # overall texture
        float(np.mean(square_img[..., 0])), # mean blue
        float(np.mean(square_img[..., 1])), # mean green
        float(np.mean(square_img[..., 2])), # mean red
        float(np.mean(hsv[..., 1])),        # saturation
        float(np.sum(edges > 0) / edges.size),  # edge density
        float(np.mean(center)),             # center brightness (piece top)
        float(np.std(center)),              # center texture
        float(np.mean(edge_pixels)),        # surrounding-square brightness
        float(np.mean(center) - np.mean(edge_pixels)),  # piece-vs-square contrast
    ], dtype=np.float32)


class PieceClassifier:
    """Trains a kNN classifier at calibration time using the 64 squares of a
    starting-position board as labeled examples (32 white in rows 1-2,
    32 black in rows 7-8, 32 empty in rows 3-6). After training,
    predict_board() returns an 8x8 array of {EMPTY, WHITE, BLACK} per scan.
    """

    def __init__(self) -> None:
        self.model: Optional[KNeighborsClassifier] = None

    def train_from_starting_position(self, warped_board: np.ndarray) -> None:
        sq = warped_board.shape[0] // 8
        features: list[np.ndarray] = []
        labels: list[int] = []
        # In the warped image (camera-frame coords), `row` 0 is at the top of
        # the image. With BOARD_FLIPPED=1, white sits at the top of the image,
        # so warped rows 0-1 = white pieces, 6-7 = black pieces, 2-5 = empty.
        if BOARD_FLIPPED:
            white_rows = (0, 1)
            black_rows = (6, 7)
        else:
            white_rows = (6, 7)
            black_rows = (0, 1)

        for row in range(8):
            for col in range(8):
                patch = warped_board[row * sq:(row + 1) * sq, col * sq:(col + 1) * sq]
                if row in white_rows:
                    label = WHITE
                elif row in black_rows:
                    label = BLACK
                else:
                    label = EMPTY
                features.append(extract_square_features(patch))
                labels.append(label)

        X = np.stack(features)
        y = np.array(labels)
        # Standardize for kNN distance fairness
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0) + 1e-6
        Xn = (X - self._mean) / self._std

        self.model = KNeighborsClassifier(n_neighbors=3, weights='distance')
        self.model.fit(Xn, y)
        logger.info(
            f"PieceClassifier trained on {len(y)} samples "
            f"({(y == WHITE).sum()} white, {(y == BLACK).sum()} black, {(y == EMPTY).sum()} empty)"
        )

    def predict_board(self, warped_board: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (predictions, confidences) — both 8x8 arrays.
        Confidences are in [0, 1]; values near 1 mean kNN was unanimous."""
        if self.model is None:
            raise RuntimeError("Classifier not trained. Call train_from_starting_position first.")
        sq = warped_board.shape[0] // 8
        feats = []
        for row in range(8):
            for col in range(8):
                patch = warped_board[row * sq:(row + 1) * sq, col * sq:(col + 1) * sq]
                feats.append(extract_square_features(patch))
        X = np.stack(feats)
        Xn = (X - self._mean) / self._std
        proba = self.model.predict_proba(Xn)  # (64, n_classes)
        preds = self.model.classes_[np.argmax(proba, axis=1)]
        confs = np.max(proba, axis=1)
        return preds.reshape(8, 8), confs.reshape(8, 8)


class ChessBoardDetector:
    """
    Detects and tracks chess piece movements on a physical chess board
    """

    def __init__(self):
        self.board_corners = None
        self.previous_board_state = None
        self.current_board_state = None
        self.square_size = None
        # Diff-based detection state
        self.reference_squares: Optional[np.ndarray] = None  # (8, 8, sq, sq) grayscale ref
        self._pending_change: Optional[Tuple[int, int]] = None  # (changed_count, frame_idx) — unused, see _change_streak
        self._change_streak: Dict[Tuple[int, int], int] = {}  # square -> consecutive-frames-changed
        # Detection: YOLO if model is available, else fall back to per-square kNN.
        # For now, DISABLE YOLO because it doesn't work well with non-standard pieces
        # Use kNN classifier instead which learns from YOUR pieces during calibration
        self.yolo_detector: Optional[YOLOPieceDetector] = None
        USE_YOLO = os.environ.get('USE_YOLO', '0') == '1'
        if USE_YOLO and os.path.exists(YOLO_MODEL_PATH):
            try:
                self.yolo_detector = YOLOPieceDetector()
                logger.info("Using YOLO chess piece detector")
            except Exception as e:
                logger.warning(f"YOLO model load failed, falling back to kNN: {e}")
        else:
            logger.info("Using kNN classifier (learns from your pieces during calibration)")
        self.classifier = PieceClassifier()
        self.previous_classes: Optional[np.ndarray] = None  # 8x8 of {EMPTY, WHITE, BLACK}
        # Stability gate: only emit a move when the predicted board has been
        # consistent for N consecutive scans. Prevents transient misclassification flicker.
        self._candidate_classes: Optional[np.ndarray] = None
        self._candidate_streak: int = 0

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
                        # Use minAreaRect so rotated boards still register as square
                        rect = cv2.minAreaRect(approx)
                        (rw, rh) = rect[1]
                        if rw <= 0 or rh <= 0:
                            continue
                        rotated_aspect = max(rw, rh) / min(rw, rh)
                        rotated_area = rw * rh
                        # Fill ratio: real boards fill their rotated bbox tightly
                        fill_ratio = area / rotated_area if rotated_area > 0 else 0
                        if rotated_aspect < 1.25 and fill_ratio > 0.85:
                            # Score = how "square + filled" it is, weighted by area
                            squareness = 1.0 / rotated_aspect
                            score = area * squareness * fill_ratio
                            valid_contours.append((score, approx))
                            break

        # Return best-scoring valid quadrilateral
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

    def _split_squares(self, warped_board: np.ndarray) -> np.ndarray:
        """Split the warped board into 8x8 grayscale squares. Returns (8, 8, sq, sq)."""
        gray = cv2.cvtColor(warped_board, cv2.COLOR_BGR2GRAY)
        sq = gray.shape[0] // 8
        squares = np.zeros((8, 8, sq, sq), dtype=np.uint8)
        for row in range(8):
            for col in range(8):
                squares[row, col] = gray[row * sq:(row + 1) * sq, col * sq:(col + 1) * sq]
        return squares

    def set_reference(self, warped_board: np.ndarray) -> None:
        """Calibrate from the warped starting-position board. With YOLO available,
        we just snapshot the YOLO prediction. Without YOLO, we train the kNN
        classifier on the 32 piece + 32 empty squares.
        """
        if self.yolo_detector is not None:
            # YOLO needs no training; just snapshot the current board state
            self.previous_classes = self.yolo_detector.predict_board(warped_board)
        else:
            self.classifier.train_from_starting_position(warped_board)
            preds, _ = self.classifier.predict_board(warped_board)
            self.previous_classes = preds

        self._candidate_classes = None
        self._candidate_streak = 0
        self._scan_counter = 0
        # Keep diff-based reference too, for any legacy paths still using it.
        self.reference_squares = self._split_squares(warped_board)
        self._change_streak = {}
        logger.info(
            f"Calibrated. Detector sees: "
            f"{(self.previous_classes == WHITE).sum()} white, "
            f"{(self.previous_classes == BLACK).sum()} black, "
            f"{(self.previous_classes == EMPTY).sum()} empty squares"
        )
        logger.info(f"Initial board state:\n{self._format_board(self.previous_classes)}")

    def detect_move_classified(
        self,
        warped_board: np.ndarray,
        confirm_frames: int = 2,
        confidence_threshold: float = 0.6,
    ) -> Optional[Dict[str, str]]:
        """Detect a move by predicting the full board state per frame and
        diffing against the last known state. Uses YOLO when available, kNN
        otherwise. Robust to lighting drift because predictions are absolute,
        not against a temporal reference.
        """
        if self.previous_classes is None:
            return None

        if self.yolo_detector is not None:
            current_classes = self.yolo_detector.predict_board(warped_board)
        else:
            raw_preds, confs = self.classifier.predict_board(warped_board)
            current_classes = np.where(confs >= confidence_threshold, raw_preds, self.previous_classes)

        # Periodic state log so we can see the detector's view if things go wrong.
        self._scan_counter = getattr(self, '_scan_counter', 0) + 1
        if self._scan_counter % 20 == 0:
            logger.info(
                f"Detector state (scan #{self._scan_counter}):\n"
                + self._format_board(current_classes)
            )

        # Stability gate
        if self._candidate_classes is None or not np.array_equal(self._candidate_classes, current_classes):
            self._candidate_classes = current_classes
            self._candidate_streak = 1
            return None
        self._candidate_streak += 1
        if self._candidate_streak < confirm_frames:
            return None

        # Stable. Compare to last known position.
        if np.array_equal(current_classes, self.previous_classes):
            return None  # No change

        files = 'abcdefgh'

        def _label(row: int, col: int) -> str:
            if BOARD_FLIPPED:
                return f"{files[7 - col]}{row + 1}"
            return f"{files[col]}{8 - row}"

        diff_squares = [
            (r, c, int(self.previous_classes[r, c]), int(current_classes[r, c]))
            for r in range(8) for c in range(8)
            if self.previous_classes[r, c] != current_classes[r, c]
        ]

        # Try to identify the move from the diff
        move = self._reduce_diff_to_move(diff_squares, _label)
        if move is None:
            return None

        # Commit the new state
        self.previous_classes = current_classes
        self._candidate_classes = None
        self._candidate_streak = 0
        logger.info(
            f"Classified move: {move['from']} -> {move['to']} (piece={move.get('color')}, "
            f"diff_squares={len(diff_squares)})"
        )
        return move

    @staticmethod
    def _format_board(classes: np.ndarray) -> str:
        symbols = {EMPTY: '.', WHITE: 'W', BLACK: 'B'}
        return '\n'.join(' '.join(symbols[int(classes[r, c])] for c in range(8)) for r in range(8))

    def _reduce_diff_to_move(self, diff_squares, label_fn) -> Optional[Dict[str, str]]:
        """Convert a list of (row, col, prev_class, curr_class) tuples into a
        {from, to, color} move dict. Handles plain moves (2 squares), captures
        (2 squares with color change), castling (4 squares — pick the king),
        and en passant (3 squares — pick the pawn move).
        Returns None if the diff doesn't look like any single legal move pattern.
        """
        if len(diff_squares) == 0:
            return None

        # Helper: find a square that gained a piece of given color
        def gained(color):
            return [(r, c, p, n) for r, c, p, n in diff_squares if p == EMPTY and n == color]

        # Helper: find a square that lost a piece of given color
        def lost(color):
            return [(r, c, p, n) for r, c, p, n in diff_squares if p == color and n == EMPTY]

        # Helper: find a square where one color was replaced by another (capture target)
        def replaced(from_color, to_color):
            return [(r, c, p, n) for r, c, p, n in diff_squares
                    if p == from_color and n == to_color]

        for color in (WHITE, BLACK):
            other = BLACK if color == WHITE else WHITE
            color_str = 'white' if color == WHITE else 'black'

            # Plain move: piece of `color` left one square, arrived at an empty one.
            l = lost(color)
            g = gained(color)
            if len(l) == 1 and len(g) == 1 and len(diff_squares) == 2:
                fr = l[0]
                to = g[0]
                return {
                    'from': label_fn(fr[0], fr[1]),
                    'to': label_fn(to[0], to[1]),
                    'color': color_str,
                }

            # Capture: piece of `color` left one square, replaced opponent on another.
            r = replaced(other, color)
            if len(l) == 1 and len(r) == 1 and len(diff_squares) == 2:
                fr = l[0]
                to = r[0]
                return {
                    'from': label_fn(fr[0], fr[1]),
                    'to': label_fn(to[0], to[1]),
                    'color': color_str,
                }

            # Castling: king + rook both move. 4 squares change, all on same rank.
            # We emit the king move (e1->g1 or e1->c1, on the back rank); chess.js
            # auto-handles the rook leg.
            if len(diff_squares) == 4 and len(l) == 2 and len(g) == 2:
                rows = {r for r, _, _, _ in diff_squares}
                if len(rows) == 1:
                    # All on same rank. Find the e-file mover (king starts there)
                    e_col = 4
                    king_loss = next((s for s in l if s[1] == e_col), None)
                    if king_loss is not None:
                        # King goes to col 6 (kingside) or col 2 (queenside)
                        king_dest = next((s for s in g if s[1] in (2, 6)), None)
                        if king_dest is not None:
                            return {
                                'from': label_fn(king_loss[0], king_loss[1]),
                                'to': label_fn(king_dest[0], king_dest[1]),
                                'color': color_str,
                            }

            # En passant: 3 squares change. Capturing pawn (color) goes from one
            # square to a diagonally adjacent empty square, opponent pawn on
            # capturer's old rank disappears.
            if len(diff_squares) == 3 and len(l) == 1 and len(g) == 1 and len(lost(other)) == 1:
                fr = l[0]
                to = g[0]
                # Sanity: en passant target is diagonally adjacent
                if abs(fr[0] - to[0]) == 1 and abs(fr[1] - to[1]) == 1:
                    return {
                        'from': label_fn(fr[0], fr[1]),
                        'to': label_fn(to[0], to[1]),
                        'color': color_str,
                    }

        # Couldn't reduce: log and skip. (Common: classifier flicker before stability)
        logger.info(
            f"Unrecognized diff pattern ({len(diff_squares)} squares): "
            + ', '.join(f"({label_fn(r, c)} {p}->{n})" for r, c, p, n in diff_squares[:6])
        )
        return None

    def detect_move_by_diff(
        self,
        warped_board: np.ndarray,
        diff_threshold: float = 18.0,
        confirm_frames: int = 2,
    ) -> Optional[Dict[str, str]]:
        """
        Detect a move by comparing current squares to the reference snapshot.
        A square is "changed" when mean absolute pixel diff exceeds diff_threshold
        for at least confirm_frames consecutive scans.
        Returns: {'from': sq, 'to': sq} when exactly 2 squares are persistently changed.
        """
        if self.reference_squares is None:
            return None

        current = self._split_squares(warped_board)
        ref = self.reference_squares
        diffs = np.abs(current.astype(np.int16) - ref.astype(np.int16)).mean(axis=(2, 3))

        files = 'abcdefgh'

        def _label(row: int, col: int) -> str:
            if BOARD_FLIPPED:
                return f"{files[7 - col]}{row + 1}"
            return f"{files[col]}{8 - row}"

        changed_now = {(r, c) for r in range(8) for c in range(8) if diffs[r, c] > diff_threshold}

        # Update streaks: increment for currently-changed squares, reset others
        for key in list(self._change_streak.keys()):
            if key not in changed_now:
                del self._change_streak[key]
        for key in changed_now:
            self._change_streak[key] = self._change_streak.get(key, 0) + 1

        confirmed = [k for k, n in self._change_streak.items() if n >= confirm_frames]

        if len(confirmed) != 2:
            if len(confirmed) > 2:
                logger.debug(f"Too many changed squares ({len(confirmed)}), waiting for stability")
            return None

        # Geometric sanity check: real chess moves connect from→to via rank, file,
        # diagonal, or knight L. Reject anything else as camera noise.
        (r1, c1), (r2, c2) = confirmed
        dr, dc = abs(r1 - r2), abs(c1 - c2)
        is_rank_or_file = (dr == 0 or dc == 0)
        is_diagonal = (dr == dc)
        is_knight = (dr, dc) in {(1, 2), (2, 1)}
        if not (is_rank_or_file or is_diagonal or is_knight):
            logger.info(
                f"Rejecting non-chess geometry: {_label(r1, c1)} - {_label(r2, c2)} "
                f"(dr={dr}, dc={dc})"
            )
            self._change_streak = {}
            return None

        # Distinguish from vs. to by mean intensity vs. reference.
        # Heuristic: 'from' becomes more like the empty-square baseline (less detail),
        # 'to' gains a piece (often shifts brightness more dramatically).
        # We use absolute change magnitude — the larger-change square gets 'to' if the
        # other one's current intensity is closer to reference of that square than ours.
        a, b = confirmed
        sq_a = _label(a[0], a[1])
        sq_b = _label(b[0], b[1])

        # 'from' = square whose current image is most different (piece left, exposing surface)
        # vs. 'to' = square whose current image gained content
        # Use variance: 'to' typically has higher variance (piece detail) vs. 'from' (now empty)
        var_a = float(np.var(current[a[0], a[1]]))
        var_b = float(np.var(current[b[0], b[1]]))

        if var_a < var_b:
            move = {'from': sq_a, 'to': sq_b}
            from_idx, to_idx = a, b
        else:
            move = {'from': sq_b, 'to': sq_a}
            from_idx, to_idx = b, a

        # Identify which piece color moved by sampling the center of the 'to' square.
        # White wooden pieces are bright; black pieces are dark. We look at the center
        # to avoid sampling the (lighter or darker) square color around the piece base.
        to_square_img = current[to_idx[0], to_idx[1]]
        h, w = to_square_img.shape
        center_patch = to_square_img[h // 3:2 * h // 3, w // 3:2 * w // 3]
        center_brightness = float(np.mean(center_patch))
        # Threshold tuned for wooden boards/pieces; tweak via env if needed.
        piece_color = 'white' if center_brightness > 110 else 'black'
        move['color'] = piece_color

        # Refresh the ENTIRE reference to current state. The two moved squares now
        # match physical reality, and every other square is re-baselined so accumulated
        # drift (autoexposure, lighting, micro-vibrations) doesn't poison future detections.
        # This is critical for keeping detection working past the first few moves.
        self.reference_squares = current.copy()
        self._change_streak = {}

        logger.info(
            f"Diff-based move: {move['from']} -> {move['to']} "
            f"(piece={piece_color}, brightness={center_brightness:.0f}, "
            f"var_from={min(var_a, var_b):.0f}, var_to={max(var_a, var_b):.0f})"
        )
        return move

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

        # Force a known frame size so frontend click coordinates align with backend pixels.
        # Frontend handleVideoClick normalizes clicks to 640x480.
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if isinstance(self.camera_source, int):
            logger.info(f"Camera {self.camera_source} started at {actual_w}x{actual_h}")
        else:
            logger.info(f"Camera stream started at {actual_w}x{actual_h}: {self.camera_source}")

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

            # Capture reference snapshot for diff-based detection
            warped = self.detector.extract_board_region(frame, corners)
            self.detector.set_reference(warped)

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
            move = self.detector.detect_move_classified(warped)

            if move:
                logger.info(f"Move detected: {move['from']} -> {move['to']}")

            return move
        except Exception as e:
            logger.error(f"Error in detect_move: {e}", exc_info=True)
            return None
