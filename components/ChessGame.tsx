'use client';

import { useState, useEffect, useRef } from 'react';
import { Chessboard } from 'react-chessboard';
import { Chess } from 'chess.js';
import { io, Socket } from 'socket.io-client';

export default function ChessGame() {
  const [game, setGame] = useState(new Chess());
  const [gameStatus, setGameStatus] = useState('');
  const [moveHistory, setMoveHistory] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const socketRef = useRef<Socket | null>(null);

  // WebSocket connection
  useEffect(() => {
    const socket = io('http://localhost:5001');
    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to detection server');
      setConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from detection server');
      setConnected(false);
    });

    socket.on('move_detected', (data: { from: string; to: string }) => {
      console.log('Move detected:', data);
      makeExternalMove(data.from, data.to);
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  // Update game status whenever the game changes
  useEffect(() => {
    updateGameStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game, moveHistory]);

  function updateGameStatus(gameInstance = game) {
    let status = '';

    const isCheckmate = gameInstance.isCheckmate();
    const isCheck = gameInstance.isCheck();

    // Debug: show legal moves when in check
    if (isCheck && !isCheckmate) {
      const legalMoves = gameInstance.moves();
      console.log('In check but not mate. Legal moves:', legalMoves);
    }

    // Check for game-ending conditions first
    if (isCheckmate) {
      const winner = gameInstance.turn() === 'w' ? 'Black' : 'White';
      status = `Checkmate! ${winner} wins!`;
    } else if (gameInstance.isStalemate()) {
      status = 'Stalemate! Game is a draw.';
    } else if (gameInstance.isDraw()) {
      status = 'Draw!';
    } else if (isCheck) {
      // Only show check if game is not over
      status = `${gameInstance.turn() === 'w' ? 'White' : 'Black'} is in check!`;
    } else {
      status = `${gameInstance.turn() === 'w' ? 'White' : 'Black'}'s turn`;
    }

    setGameStatus(status);
  }

  function onDrop({ sourceSquare, targetSquare }: any) {
    if (!targetSquare) return false;

    try {
      // Create a copy of the game
      const gameCopy = new Chess(game.fen());

      // Attempt the move
      const move = gameCopy.move({
        from: sourceSquare,
        to: targetSquare,
        promotion: 'q', // Always promote to queen for simplicity
      });

      // If move is illegal, return false
      if (move === null) {
        return false;
      }

      // Update the game state
      setGame(gameCopy);

      // Add move to history
      setMoveHistory(prev => [...prev, move.san]);

      // Update status with the new game state
      updateGameStatus(gameCopy);

      return true;
    } catch (error) {
      console.error('Error during move:', error);
      return false;
    }
  }

  // Function to handle external moves from the camera detection
  function makeExternalMove(from: string, to: string, promotion?: string) {
    try {
      const gameCopy = new Chess(game.fen());
      const move = gameCopy.move({
        from,
        to,
        promotion: promotion || 'q',
      });

      if (move) {
        setGame(gameCopy);
        setMoveHistory(prev => [...prev, move.san]);
        return true;
      }
      return false;
    } catch (error) {
      console.error('External move error:', error);
      return false;
    }
  }

  function resetGame() {
    setGame(new Chess());
    setMoveHistory([]);
  }

  // Camera control functions
  async function startCamera() {
    try {
      const response = await fetch('http://localhost:5001/api/camera/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await response.json();
      if (data.success) {
        setCameraActive(true);
      }
    } catch (error) {
      console.error('Failed to start camera:', error);
    }
  }

  async function stopCamera() {
    try {
      await fetch('http://localhost:5001/api/camera/stop', { method: 'POST' });
      setCameraActive(false);
      setCalibrated(false);
    } catch (error) {
      console.error('Failed to stop camera:', error);
    }
  }

  async function calibrateBoard() {
    try {
      const response = await fetch('http://localhost:5001/api/calibrate', {
        method: 'POST'
      });
      const data = await response.json();
      if (data.success) {
        setCalibrated(true);
      } else {
        alert(data.error || 'Calibration failed');
      }
    } catch (error) {
      console.error('Failed to calibrate:', error);
    }
  }

  async function startDetection() {
    try {
      await fetch('http://localhost:5001/api/detection/start', { method: 'POST' });
    } catch (error) {
      console.error('Failed to start detection:', error);
    }
  }

  async function stopDetection() {
    try {
      await fetch('http://localhost:5001/api/detection/stop', { method: 'POST' });
    } catch (error) {
      console.error('Failed to stop detection:', error);
    }
  }

  return (
    <div style={{
      width: '100vw',
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      backgroundColor: '#1a1a1a',
      color: '#ffffff',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: '1rem',
      overflow: 'hidden'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '2000px',
        display: 'flex',
        gap: '2rem',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%'
      }}>
        {/* Chess Board */}
        <div style={{
          flex: '1',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          maxHeight: '100vh',
          aspectRatio: '1'
        }}>
          <div style={{ width: '100%', maxWidth: 'min(90vh, 1000px)' }}>
            <Chessboard
              options={{
                position: game.fen(),
                onPieceDrop: onDrop,
              }}
            />
          </div>
        </div>

        {/* Game Info Panel */}
        <div style={{
          width: '350px',
          minWidth: '300px',
          maxWidth: '400px',
          backgroundColor: '#2a2a2a',
          padding: '2rem',
          borderRadius: '12px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          maxHeight: '90vh',
          overflowY: 'auto'
        }}>
          <h2 style={{
            margin: '0 0 1.5rem 0',
            fontSize: '2.5rem',
            fontWeight: 'bold'
          }}>
            Communal Chess
          </h2>

          {/* Game Status */}
          <div style={{
            padding: '1.5rem',
            backgroundColor: game.isCheckmate() ? '#44ff44' : game.isCheck() ? '#ff4444' : '#3a3a3a',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            textAlign: 'center',
            fontSize: '1.8rem',
            fontWeight: 'bold'
          }}>
            {gameStatus}
          </div>

          {/* Move Counter */}
          <div style={{
            marginBottom: '1.5rem',
            fontSize: '1.2rem',
            color: '#aaa'
          }}>
            Move #{Math.floor(moveHistory.length / 2) + 1}
          </div>

          {/* Controls */}
          <button
            onClick={resetGame}
            style={{
              width: '100%',
              padding: '1rem',
              backgroundColor: '#4a4a4a',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '1.3rem',
              fontWeight: 'bold',
              marginBottom: '2rem'
            }}
            onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#5a5a5a'}
            onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#4a4a4a'}
          >
            Reset Game
          </button>

          {/* Move History */}
          <div>
            <h3 style={{
              fontSize: '1.4rem',
              marginBottom: '1rem',
              color: '#ccc'
            }}>
              Move History
            </h3>
            <div style={{
              maxHeight: '400px',
              overflowY: 'auto',
              backgroundColor: '#1a1a1a',
              padding: '1rem',
              borderRadius: '8px',
              fontSize: '1.2rem'
            }}>
              {moveHistory.length === 0 ? (
                <div style={{ color: '#666' }}>No moves yet</div>
              ) : (
                <div>
                  {moveHistory.map((move, index) => {
                    const moveNumber = Math.floor(index / 2) + 1;
                    const isWhiteMove = index % 2 === 0;

                    return (
                      <span key={`move-${index}`} style={{
                        color: isWhiteMove ? '#ffffff' : '#aaaaaa',
                        marginRight: '0.5rem',
                        display: 'inline-block'
                      }}>
                        {isWhiteMove && <span style={{ color: '#666' }}>{moveNumber}. </span>}
                        {move}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Real-time Detection Controls */}
          <div style={{
            marginTop: '1.5rem',
            padding: '1rem',
            backgroundColor: '#1a1a1a',
            borderRadius: '6px',
            fontSize: '0.85rem'
          }}>
            <h3 style={{
              fontSize: '1rem',
              marginBottom: '0.75rem',
              color: '#ccc'
            }}>
              Real-time Detection
            </h3>

            <div style={{ marginBottom: '0.75rem' }}>
              <div style={{ marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                Server: <span style={{ color: connected ? '#44ff44' : '#ff6b6b' }}>
                  {connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <div style={{ marginBottom: '0.5rem', fontSize: '0.8rem' }}>
                Camera: <span style={{ color: cameraActive ? '#44ff44' : '#666' }}>
                  {cameraActive ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div style={{ fontSize: '0.8rem' }}>
                Calibrated: <span style={{ color: calibrated ? '#44ff44' : '#666' }}>
                  {calibrated ? 'Yes' : 'No'}
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {!cameraActive ? (
                <button
                  onClick={startCamera}
                  disabled={!connected}
                  style={{
                    padding: '0.5rem',
                    backgroundColor: connected ? '#4a9eff' : '#333',
                    color: connected ? 'white' : '#666',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: connected ? 'pointer' : 'not-allowed',
                    fontSize: '0.9rem'
                  }}
                >
                  Start Camera
                </button>
              ) : (
                <>
                  <button
                    onClick={stopCamera}
                    style={{
                      padding: '0.5rem',
                      backgroundColor: '#ff4444',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.9rem'
                    }}
                  >
                    Stop Camera
                  </button>
                  {!calibrated ? (
                    <button
                      onClick={calibrateBoard}
                      style={{
                        padding: '0.5rem',
                        backgroundColor: '#ff9944',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.9rem'
                      }}
                    >
                      Calibrate Board
                    </button>
                  ) : (
                    <button
                      onClick={startDetection}
                      style={{
                        padding: '0.5rem',
                        backgroundColor: '#44ff44',
                        color: 'black',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                        fontWeight: 'bold'
                      }}
                    >
                      Start Auto-Detection
                    </button>
                  )}
                </>
              )}
            </div>

            {cameraActive && (
              <div style={{
                marginTop: '0.75rem',
                padding: '0.5rem',
                backgroundColor: '#2a2a2a',
                borderRadius: '4px',
                fontSize: '0.75rem',
                color: '#888'
              }}>
                <img
                  src="http://localhost:5001/api/video_feed"
                  alt="Camera feed"
                  style={{
                    width: '100%',
                    borderRadius: '4px',
                    backgroundColor: '#000'
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
