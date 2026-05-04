# Communal Chess

A real-time chess application that detects physical chess piece movements using computer vision and displays them on a digital board. Perfect for playing chess with friends while tracking the game digitally!

## Features

### Interactive Digital Board
- **Drag and Drop**: Move pieces by dragging them
- **Turn Indicator**: Shows whose turn it is (White/Black)
- **Check & Checkmate Detection**: Automatically detects check and checkmate states
- **Stalemate & Draw Detection**: Recognizes all draw conditions
- **Move History**: Complete game notation history
- **Game Reset**: Start a new game at any time

### Real-time Camera Detection
- **Computer Vision**: Detects chess piece movements on a physical board
- **Live Video Feed**: See the camera view with board detection overlay
- **Auto-Calibration**: Smart board corner detection
- **WebSocket Integration**: Real-time updates from camera to digital board
- **Move Validation**: Physical moves are validated using chess rules

## Tech Stack

### Frontend
- **Next.js 16** (React 19)
- **TypeScript**
- **react-chessboard**: Visual chess board component
- **chess.js**: Chess game logic and validation
- **Socket.IO Client**: WebSocket communication

### Backend
- **Python 3.x**
- **Flask**: REST API server
- **Flask-SocketIO**: WebSocket server
- **OpenCV**: Computer vision for board detection
- **NumPy**: Image processing

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- A webcam (for real-time detection)

### Frontend Setup

1. Install dependencies:
```bash
npm install
```

2. Run the development server:
```bash
npm run dev
```

3. Open [http://localhost:3000](http://localhost:3000) in your browser

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Run the Flask server:
```bash
python app.py
```

The backend will start on `http://localhost:5000`

## How to Use

### Playing Manually
1. Simply drag and drop pieces on the digital board
2. The board enforces chess rules automatically
3. Watch the turn indicator and check status

### Using Camera Detection

1. **Start the Backend**: Make sure the Flask server is running on port 5000

2. **Position Your Camera**:
   - Mount your webcam above your physical chess board
   - Ensure the entire board is visible in the frame
   - Good lighting is important for accurate detection

3. **In the Web App**:
   - Click **"Start Camera"** in the Real-time Detection panel
   - Click **"Calibrate Board"** - this detects the board corners
   - Once calibrated, click **"Start Auto-Detection"**
   - The system will now detect moves automatically!

4. **Make Physical Moves**:
   - Pick up a piece from one square
   - Place it on another square
   - The system detects the change and updates the digital board

## How It Works

### Computer Vision Pipeline

1. **Board Detection**: Finds the chess board corners using edge detection
2. **Perspective Transform**: Warps the board to a flat, top-down view
3. **Square Analysis**: Divides the board into 64 squares
4. **Piece Detection**: Detects presence/absence of pieces in each square
5. **Move Detection**: Compares current state to previous state
6. **Validation**: Uses chess.js to validate detected moves

### Communication Flow

```
Physical Board → Camera → OpenCV → Flask → WebSocket → React → chess.js → Digital Board
```

## API Endpoints

### REST API

- `POST /api/camera/start` - Start the camera
- `POST /api/camera/stop` - Stop the camera
- `POST /api/calibrate` - Calibrate the board position
- `POST /api/detection/start` - Start move detection
- `POST /api/detection/stop` - Stop move detection
- `GET /api/status` - Get system status
- `GET /api/video_feed` - Live video stream

### WebSocket Events

- `connect` - Client connected
- `disconnect` - Client disconnected
- `move_detected` - Move detected on physical board

## Project Structure

```
communal-chess/
├── app/
│   ├── page.tsx              # Main page
│   ├── layout.tsx            # Root layout
│   └── globals.css           # Global styles
├── components/
│   └── ChessGame.tsx         # Main chess game component with WebSocket
├── backend/
│   ├── app.py                # Flask server with WebSocket
│   ├── chess_detector.py     # Computer vision detection system
│   └── requirements.txt      # Python dependencies
└── package.json
```

## Troubleshooting

### Board Not Detected
- Ensure the entire chess board is visible in the camera frame
- Improve lighting conditions
- Make sure the board has clear edges and corners
- Try using a board with a contrasting border

### Moves Not Detected
- Recalibrate the board
- Make sure pieces are moved completely (not just nudged)
- Adjust lighting to reduce shadows
- Ensure pieces are placed in the center of squares

### Camera Connection Issues
- Check that no other application is using the camera
- Try a different camera index (modify in `app.py`)
- Verify camera permissions

### Frontend/Backend Connection Issues
- Ensure backend is running on port 5000
- Check that CORS is enabled
- Verify WebSocket connection in browser console

## Future Enhancements

- Piece recognition (distinguish between different pieces and colors)
- Multiple board support
- Game recording and replay
- Online multiplayer
- Move suggestions and analysis
- Integration with chess engines (Stockfish)

## License

MIT

## Credits

Built with Next.js, React, Python, Flask, OpenCV, and chess.js
