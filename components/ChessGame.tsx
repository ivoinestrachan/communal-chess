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
  const [cameraSource, setCameraSource] = useState<number | string>(0);
  const [availableCameras, setAvailableCameras] = useState<Array<{index: number, name: string, backend: string}>>([]);
  const [manualCalibrationMode, setManualCalibrationMode] = useState(false);
  const [calibrationCorners, setCalibrationCorners] = useState<Array<{x: number, y: number}>>([]);
  const [detectionActive, setDetectionActive] = useState(false);
  const socketRef = useRef<Socket | null>(null);
  const videoRef = useRef<HTMLImageElement>(null);

  // Fetch available cameras on mount
  useEffect(() => {
    async function fetchCameras() {
      try {
        const response = await fetch('http://localhost:5001/api/cameras/list');
        const data = await response.json();
        if (data.success && data.cameras.length > 0) {
          setAvailableCameras(data.cameras);
          // Auto-select first camera
          setCameraSource(data.cameras[0].index);
        }
      } catch (error) {
        console.error('Failed to fetch cameras:', error);
      }
    }
    fetchCameras();
  }, []);

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

        // Update status with the new game state
        updateGameStatus(gameCopy);

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
        body: JSON.stringify({ camera_source: cameraSource })
      });
      const data = await response.json();
      if (data.success) {
        setCameraActive(true);
      } else {
        alert(data.error || 'Failed to start camera');
      }
    } catch (error) {
      console.error('Failed to start camera:', error);
      alert('Failed to start camera');
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
        alert('✅ Board calibrated successfully! You can now start auto-detection.');
      } else {
        // Auto-calibration failed, offer manual calibration
        const useManual = confirm(`❌ Auto-calibration failed: ${data.error || 'Board not detected'}\n\n🎯 Would you like to try MANUAL calibration?\n\nYou'll click the 4 corners of your chess board:\n1. Top-left corner\n2. Top-right corner\n3. Bottom-right corner\n4. Bottom-left corner`);

        if (useManual) {
          setManualCalibrationMode(true);
          setCalibrationCorners([]);
        }
      }
    } catch (error) {
      console.error('Failed to calibrate:', error);
      alert('Failed to calibrate. Check console for details.');
    }
  }

  function handleVideoClick(e: React.MouseEvent<HTMLImageElement>) {
    if (!manualCalibrationMode) return;

    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 640; // Normalize to video size
    const y = ((e.clientY - rect.top) / rect.height) * 480;

    const newCorners = [...calibrationCorners, { x, y }];
    setCalibrationCorners(newCorners);

    if (newCorners.length === 4) {
      submitManualCalibration(newCorners);
    }
  }

  async function submitManualCalibration(corners: Array<{x: number, y: number}>) {
    try {
      const response = await fetch('http://localhost:5001/api/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          corners: corners.map(c => [c.x, c.y])
        })
      });
      const data = await response.json();
      if (data.success) {
        setCalibrated(true);
        setManualCalibrationMode(false);
        setCalibrationCorners([]);
        alert('✅ Manual calibration successful! You can now start auto-detection.');
      } else {
        alert('❌ Manual calibration failed. Please try again.');
        setCalibrationCorners([]);
      }
    } catch (error) {
      console.error('Failed to submit manual calibration:', error);
      alert('Failed to calibrate. Check console for details.');
    }
  }

  function cancelManualCalibration() {
    setManualCalibrationMode(false);
    setCalibrationCorners([]);
  }

  async function startDetection() {
    try {
      const response = await fetch('http://localhost:5001/api/detection/start', { method: 'POST' });
      if (response.ok) {
        setDetectionActive(true);
      }
    } catch (error) {
      console.error('Failed to start detection:', error);
    }
  }

  async function stopDetection() {
    try {
      await fetch('http://localhost:5001/api/detection/stop', { method: 'POST' });
      setDetectionActive(false);
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
      overflow: 'hidden',
      position: 'relative'
    }}>
      {/* Camera Preview - Prominent Display */}
      {cameraActive && (
        <div style={{
          position: 'fixed',
          top: '2rem',
          right: '2rem',
          width: manualCalibrationMode ? '640px' : '480px',
          height: manualCalibrationMode ? '480px' : '360px',
          borderRadius: '16px',
          overflow: 'hidden',
          boxShadow: '0 12px 48px rgba(0, 0, 0, 0.6)',
          border: `4px solid ${manualCalibrationMode ? '#ff9944' : calibrated ? '#44ff44' : '#888'}`,
          backgroundColor: '#000',
          zIndex: 10,
          transition: 'all 0.3s ease'
        }}>
          <img
            ref={videoRef}
            src="http://localhost:5001/api/video_feed"
            alt="Camera feed"
            onClick={handleVideoClick}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              cursor: manualCalibrationMode ? 'crosshair' : 'default'
            }}
          />
          {/* Corner markers */}
          {calibrationCorners.map((corner, i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: `${(corner.x / 640) * 100}%`,
                top: `${(corner.y / 480) * 100}%`,
                width: '20px',
                height: '20px',
                borderRadius: '50%',
                backgroundColor: '#ff9944',
                border: '3px solid white',
                transform: 'translate(-50%, -50%)',
                zIndex: 10,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '12px',
                fontWeight: 'bold',
                color: 'white'
              }}
            >
              {i + 1}
            </div>
          ))}
          <div style={{
            position: 'absolute',
            top: '0.5rem',
            left: '0.5rem',
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            padding: '0.25rem 0.5rem',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 'bold',
            color: manualCalibrationMode ? '#ff9944' : '#44ff44',
            display: 'flex',
            alignItems: 'center',
            gap: '0.25rem'
          }}>
            <div style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: manualCalibrationMode ? '#ff9944' : '#ff4444',
              animation: 'pulse 2s infinite'
            }} />
            {manualCalibrationMode ? `CALIBRATING (${calibrationCorners.length}/4)` : 'LIVE'}
          </div>
          {calibrated && !manualCalibrationMode && (
            <div style={{
              position: 'absolute',
              bottom: '0.5rem',
              right: '0.5rem',
              backgroundColor: 'rgba(68, 255, 68, 0.9)',
              padding: '0.25rem 0.5rem',
              borderRadius: '4px',
              fontSize: '0.7rem',
              fontWeight: 'bold',
              color: '#000'
            }}>
              ✓ CALIBRATED
            </div>
          )}
          {detectionActive && (
            <div style={{
              position: 'absolute',
              top: '0.5rem',
              right: '0.5rem',
              backgroundColor: 'rgba(255, 68, 68, 0.95)',
              padding: '0.4rem 0.6rem',
              borderRadius: '4px',
              fontSize: '0.75rem',
              fontWeight: 'bold',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              animation: 'pulse 2s infinite'
            }}>
              <div style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: '#fff',
                animation: 'pulse 1s infinite'
              }} />
              DETECTING
            </div>
          )}
          {manualCalibrationMode && (
            <div style={{
              position: 'absolute',
              bottom: '0.5rem',
              left: '0.5rem',
              right: '0.5rem',
              backgroundColor: 'rgba(255, 153, 68, 0.95)',
              padding: '0.5rem',
              borderRadius: '6px',
              fontSize: '0.75rem',
              color: '#000',
              fontWeight: 'bold',
              textAlign: 'center'
            }}>
              Click the {['top-left', 'top-right', 'bottom-right', 'bottom-left'][calibrationCorners.length]} corner of your chess board
              <button
                onClick={cancelManualCalibration}
                style={{
                  marginTop: '0.5rem',
                  padding: '0.25rem 0.5rem',
                  backgroundColor: '#ff4444',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.7rem',
                  fontWeight: 'bold',
                  width: '100%'
                }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}

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
              position={game.fen()}
              onPieceDrop={onDrop}
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

          {/* Current Turn - Large & Prominent */}
          <div style={{
            padding: '2rem',
            backgroundColor: game.turn() === 'w' ? '#f0f0f0' : '#333',
            color: game.turn() === 'w' ? '#000' : '#fff',
            borderRadius: '12px',
            marginBottom: '2rem',
            textAlign: 'center',
            border: `4px solid ${game.turn() === 'w' ? '#fff' : '#000'}`,
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)'
          }}>
            <div style={{
              fontSize: '1.2rem',
              fontWeight: 'normal',
              marginBottom: '0.5rem',
              opacity: 0.8
            }}>
              Current Turn
            </div>
            <div style={{
              fontSize: '3rem',
              fontWeight: 'bold',
              letterSpacing: '2px'
            }}>
              {game.turn() === 'w' ? 'WHITE' : 'BLACK'}
            </div>
          </div>

          {/* Game Status Alert */}
          {(game.isCheckmate() || game.isCheck() || game.isStalemate() || game.isDraw()) && (
            <div style={{
              padding: '1.5rem',
              backgroundColor: game.isCheckmate() ? '#44ff44' : game.isCheck() ? '#ff4444' : '#ff9944',
              color: '#000',
              borderRadius: '8px',
              marginBottom: '1.5rem',
              textAlign: 'center',
              fontSize: '1.8rem',
              fontWeight: 'bold',
              animation: 'pulse 2s infinite'
            }}>
              {gameStatus}
            </div>
          )}

          {/* Move Counter */}
          <div style={{
            marginBottom: '1.5rem',
            fontSize: '1.4rem',
            color: '#ccc',
            fontWeight: 'bold'
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

          {/* Move History - Professional Table View */}
          <div>
            <h3 style={{
              fontSize: '1.6rem',
              marginBottom: '1rem',
              color: '#fff',
              fontWeight: 'bold',
              borderBottom: '2px solid #444',
              paddingBottom: '0.5rem'
            }}>
              📜 Move History
            </h3>
            <div style={{
              maxHeight: '400px',
              overflowY: 'auto',
              backgroundColor: '#1a1a1a',
              border: '2px solid #333',
              borderRadius: '8px',
              fontSize: '1.1rem'
            }}>
              {moveHistory.length === 0 ? (
                <div style={{
                  color: '#666',
                  padding: '2rem',
                  textAlign: 'center',
                  fontSize: '1rem'
                }}>
                  No moves yet - waiting for game to begin
                </div>
              ) : (
                <table style={{
                  width: '100%',
                  borderCollapse: 'collapse'
                }}>
                  <thead>
                    <tr style={{
                      backgroundColor: '#2a2a2a',
                      borderBottom: '2px solid #444'
                    }}>
                      <th style={{ padding: '0.75rem', textAlign: 'center', color: '#888', fontSize: '0.9rem' }}>#</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', color: '#fff', fontSize: '0.9rem' }}>White</th>
                      <th style={{ padding: '0.75rem', textAlign: 'left', color: '#888', fontSize: '0.9rem' }}>Black</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Array.from({ length: Math.ceil(moveHistory.length / 2) }).map((_, pairIndex) => {
                      const whiteMove = moveHistory[pairIndex * 2];
                      const blackMove = moveHistory[pairIndex * 2 + 1];
                      const isLatest = pairIndex === Math.floor(moveHistory.length / 2);

                      return (
                        <tr key={`move-pair-${pairIndex}`} style={{
                          backgroundColor: isLatest ? '#2a3a2a' : pairIndex % 2 === 0 ? '#1a1a1a' : '#222',
                          borderBottom: '1px solid #333'
                        }}>
                          <td style={{
                            padding: '0.75rem',
                            textAlign: 'center',
                            color: '#666',
                            fontWeight: 'bold',
                            fontSize: '0.9rem'
                          }}>
                            {pairIndex + 1}
                          </td>
                          <td style={{
                            padding: '0.75rem',
                            color: '#fff',
                            fontWeight: isLatest && moveHistory.length % 2 === 1 ? 'bold' : 'normal',
                            fontSize: '1.1rem',
                            fontFamily: 'monospace'
                          }}>
                            {whiteMove}
                          </td>
                          <td style={{
                            padding: '0.75rem',
                            color: '#aaa',
                            fontWeight: isLatest && moveHistory.length % 2 === 0 ? 'bold' : 'normal',
                            fontSize: '1.1rem',
                            fontFamily: 'monospace'
                          }}>
                            {blackMove || '...'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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

            {!cameraActive && (
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.25rem',
                  fontSize: '0.75rem',
                  color: '#aaa'
                }}>
                  Camera Source:
                </label>
                <select
                  value={typeof cameraSource === 'number' ? cameraSource : 'custom'}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === 'custom') {
                      const url = prompt('Enter camera stream URL (e.g., http://192.168.1.100:8080/video)');
                      if (url) setCameraSource(url);
                    } else {
                      setCameraSource(parseInt(val));
                    }
                  }}
                  style={{
                    width: '100%',
                    padding: '0.5rem',
                    backgroundColor: '#2a2a2a',
                    color: 'white',
                    border: '1px solid #444',
                    borderRadius: '4px',
                    fontSize: '0.85rem',
                    marginBottom: '0.5rem'
                  }}
                >
                  {availableCameras.length > 0 ? (
                    <>
                      {availableCameras.map((cam) => (
                        <option key={cam.index} value={cam.index}>
                          {cam.name} ({cam.backend})
                        </option>
                      ))}
                      <option value="custom">IP Camera / Phone...</option>
                    </>
                  ) : (
                    <>
                      <option value={0}>Camera 0 (Default)</option>
                      <option value={1}>Camera 1</option>
                      <option value={2}>Camera 2</option>
                      <option value="custom">IP Camera / Phone...</option>
                    </>
                  )}
                </select>
                {typeof cameraSource === 'string' && (
                  <div style={{
                    fontSize: '0.7rem',
                    color: '#44ff44',
                    marginTop: '0.25rem',
                    wordBreak: 'break-all'
                  }}>
                    Using: {cameraSource}
                  </div>
                )}
              </div>
            )}

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

            {/* Calibration Instructions */}
            {cameraActive && !calibrated && (
              <div style={{
                marginTop: '1rem',
                padding: '1rem',
                backgroundColor: '#2a2a2a',
                borderRadius: '6px',
                border: '2px solid #ff9944',
                fontSize: '0.8rem',
                lineHeight: '1.5'
              }}>
                <div style={{
                  fontWeight: 'bold',
                  fontSize: '0.9rem',
                  marginBottom: '0.5rem',
                  color: '#ff9944'
                }}>
                  📐 Calibration Tips:
                </div>
                <ul style={{
                  margin: '0',
                  paddingLeft: '1.2rem',
                  color: '#ccc'
                }}>
                  <li>Position camera to see <strong>entire chess board</strong></li>
                  <li>Board should have <strong>clear edges and corners</strong></li>
                  <li>Ensure good <strong>lighting</strong> - avoid shadows</li>
                  <li>Board should be <strong>flat</strong> on surface</li>
                  <li>Check the camera preview (bottom-right corner)</li>
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
