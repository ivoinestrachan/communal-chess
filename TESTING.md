# Chess Game Testing Guide

This document outlines all the chess rules and features to test in the Communal Chess application.

## Basic Movement Tests

### Pawn Movement
- [ ] Pawn can move 1 square forward
- [ ] Pawn can move 2 squares forward from starting position
- [ ] Pawn cannot move backward
- [ ] Pawn captures diagonally
- [ ] Pawn cannot capture forward
- [ ] Pawn promotes to queen at the end of the board

### Rook Movement
- [ ] Rook moves horizontally any number of squares
- [ ] Rook moves vertically any number of squares
- [ ] Rook cannot jump over pieces
- [ ] Rook can capture enemy pieces

### Knight Movement
- [ ] Knight moves in L-shape (2+1 squares)
- [ ] Knight can jump over pieces
- [ ] Knight can capture enemy pieces

### Bishop Movement
- [ ] Bishop moves diagonally any number of squares
- [ ] Bishop cannot jump over pieces
- [ ] Bishop can capture enemy pieces

### Queen Movement
- [ ] Queen moves horizontally any number of squares
- [ ] Queen moves vertically any number of squares
- [ ] Queen moves diagonally any number of squares
- [ ] Queen cannot jump over pieces
- [ ] Queen can capture enemy pieces

### King Movement
- [ ] King moves one square in any direction
- [ ] King cannot move into check
- [ ] King can capture adjacent enemy pieces

## Special Moves

### Castling
- [ ] Kingside castling works when conditions are met
- [ ] Queenside castling works when conditions are met
- [ ] Castling blocked if king has moved
- [ ] Castling blocked if rook has moved
- [ ] Castling blocked if squares between are occupied
- [ ] Castling blocked if king is in check
- [ ] Castling blocked if king moves through check
- [ ] Castling blocked if king ends in check

### En Passant
- [ ] En passant capture works when enemy pawn moves 2 squares
- [ ] En passant only available immediately after the 2-square pawn move
- [ ] En passant properly removes captured pawn

### Pawn Promotion
- [ ] White pawn promotes at rank 8
- [ ] Black pawn promotes at rank 1
- [ ] Promotion automatically creates queen

## Game State Tests

### Check
- [ ] Check is detected and displayed
- [ ] Player in check must move out of check
- [ ] Cannot make move that leaves king in check
- [ ] Check indicator shows which player is in check

### Checkmate
- [ ] Fool's mate works (2-move checkmate)
- [ ] Scholar's mate works (4-move checkmate)
- [ ] Back rank mate detected
- [ ] Checkmate message displays winner
- [ ] Game ends on checkmate

### Stalemate
- [ ] Stalemate detected when no legal moves available
- [ ] Stalemate detected when king not in check
- [ ] Stalemate message displays draw

### Draw Conditions
- [ ] Threefold repetition detected
- [ ] Insufficient material detected (K vs K)
- [ ] Insufficient material detected (K+B vs K)
- [ ] Insufficient material detected (K+N vs K)
- [ ] Draw message displays correctly

## Turn Management
- [ ] White moves first
- [ ] Turns alternate correctly
- [ ] Cannot move opponent's pieces
- [ ] Turn indicator shows current player
- [ ] Turn counter increments correctly

## UI/UX Tests

### Move Indicators
- [ ] Clicking a piece highlights valid moves
- [ ] Possible captures shown differently than empty squares
- [ ] Selected square highlighted
- [ ] Highlights clear after move

### Drag and Drop
- [ ] Pieces can be dragged to valid squares
- [ ] Invalid drag returns piece to origin
- [ ] Drag animation smooth
- [ ] Works on touch devices

### Right-Click Marking
- [ ] Right-clicking marks square
- [ ] Right-clicking again unmarks square
- [ ] Multiple squares can be marked
- [ ] Marks clear after making move

### Game Controls
- [ ] New Game button resets board
- [ ] Undo button steps back one move
- [ ] Undo disabled at game start
- [ ] Undo correctly reverses captured pieces

### Move History
- [ ] Moves recorded in algebraic notation
- [ ] Move history displays in two columns
- [ ] Move numbers increment correctly
- [ ] History scrolls for long games

### Captured Pieces
- [ ] Captured white pieces shown in black section
- [ ] Captured black pieces shown in white section
- [ ] Piece symbols display correctly
- [ ] Captures update in real-time

### Responsive Design
- [ ] Board scales on mobile devices
- [ ] Side panel stacks below board on mobile
- [ ] Touch interactions work
- [ ] Layout looks good on tablet

### Dark Mode
- [ ] Dark mode styling applied correctly
- [ ] Contrast sufficient in dark mode
- [ ] Board colors appropriate in dark mode

## Famous Game Scenarios

### Test with Famous Games
- [ ] Immortal Game (Anderssen vs Kieseritzky, 1851)
- [ ] Opera Game (Morphy vs Duke of Brunswick, 1858)
- [ ] Game of the Century (Byrne vs Fischer, 1956)

## Edge Cases

- [ ] Cannot capture own pieces
- [ ] Moving into check is blocked
- [ ] Discovered check works correctly
- [ ] Double check works correctly
- [ ] Pinned pieces move legally
- [ ] Board position updates correctly after each move
- [ ] FEN position remains valid throughout game

## Performance Tests

- [ ] Board renders quickly
- [ ] Move validation is instant
- [ ] No lag when dragging pieces
- [ ] Memory doesn't leak over long games
- [ ] Undo performance acceptable with many moves

## Common Chess Patterns to Test

### Scholar's Mate
```
1. e4 e5
2. Bc4 Nc6
3. Qh5 Nf6
4. Qxf7# (Checkmate)
```

### Fool's Mate
```
1. f3 e5
2. g4 Qh4# (Checkmate)
```

### Basic Stalemate
```
Place white king on a1, black king on a3, white queen on b2
Black to move = stalemate
```

### En Passant Setup
```
1. e4 a6
2. e5 d5
3. exd6 (en passant)
```

### Castling Test
```
1. e4 e5
2. Nf3 Nf6
3. Bc4 Bc5
4. O-O (kingside castle)
```

## Browser Compatibility

Test in:
- [ ] Chrome/Edge (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Mobile Safari (iOS)
- [ ] Chrome Mobile (Android)

## Accessibility

- [ ] Keyboard navigation possible
- [ ] Screen reader compatible
- [ ] Color contrast meets WCAG standards
- [ ] Focus indicators visible

## Real-time Camera Detection Tests

### Backend Setup
- [ ] Python backend starts without errors
- [ ] Flask server runs on port 5000
- [ ] All Python dependencies installed correctly
- [ ] Camera permissions granted

### Connection Tests
- [ ] WebSocket connection established
- [ ] Server status shows "Connected" in UI
- [ ] Connection survives page refresh
- [ ] Reconnection works after disconnect

### Camera Tests
- [ ] Camera starts successfully
- [ ] Video feed displays in UI panel
- [ ] Camera stops cleanly
- [ ] Multiple start/stop cycles work

### Board Calibration
- [ ] Board corners detected correctly
- [ ] Green overlay lines appear on board edges
- [ ] Calibration works in different lighting
- [ ] Recalibration updates detection area

### Move Detection
- [ ] Physical e2-e4 detected and displayed
- [ ] Physical Nf3 detected correctly
- [ ] Captures detected (piece removed)
- [ ] Invalid moves rejected
- [ ] Move history updated from camera moves
- [ ] Turn indicator updates from camera

### Performance
- [ ] Detection latency < 2 seconds
- [ ] Video feed runs at acceptable FPS
- [ ] No memory leaks during extended use
- [ ] System handles rapid moves

### Error Handling
- [ ] Graceful failure if camera unavailable
- [ ] Clear error message if calibration fails
- [ ] Recovery from lost WebSocket connection
- [ ] Proper cleanup on camera stop

### Integration Tests
- [ ] Manual moves + camera moves work together
- [ ] Game state stays synchronized
- [ ] Reset game clears camera state
- [ ] Checkmate detected from camera moves

## Testing Camera Detection

### Quick Test (Without Physical Board)
1. Start frontend: `npm run dev`
2. Start backend: `cd backend && python app.py`
3. Click "Start Camera"
4. Verify video feed appears
5. Click "Stop Camera"

### Full Test (With Physical Board)
1. Mount webcam above chess board
2. Start both servers
3. Click "Start Camera"
4. Click "Calibrate Board" (verify green lines)
5. Click "Start Auto-Detection"
6. Make move e2-e4 on physical board
7. Verify digital board updates
8. Check move history includes "e4"

### Debugging Camera Issues

**Board Not Detected:**
- Improve lighting
- Ensure entire board visible
- Use board with clear edges
- Adjust Canny edge detection thresholds

**Moves Not Detected:**
- Recalibrate board
- Move pieces completely (not just nudge)
- Reduce shadows
- Place pieces in center of squares
- Adjust variance threshold in `_has_piece()`

**Wrong Moves Detected:**
- Only move one piece at a time
- Wait for detection to stabilize
- Improve lighting consistency
- Increase detection delay

## Notes

All chess logic is handled by the chess.js library, which has been extensively tested. The main focus should be on:
1. UI interactions work correctly
2. Game state displays accurately
3. User experience is smooth and intuitive
4. Edge cases are handled gracefully
5. Camera detection works reliably in various conditions
