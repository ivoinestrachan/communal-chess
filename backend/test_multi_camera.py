#!/usr/bin/env python3
"""
Test script for multi-camera setup
Use this to verify your cameras are working before starting the full system
"""

import requests
import json
import time

API_BASE = "http://localhost:5001/api"


def setup_cameras():
    """Setup multi-camera system with example configuration"""
    print("🎥 Setting up multi-camera system...")

    # Example: 2 USB cameras + 1 phone camera
    # Adjust this based on your actual setup
    config = {
        "cameras": [
            {
                "id": "overhead",
                "source": 0,  # Built-in or first USB camera
                "position": "overhead",
                "priority": 10
            },
            {
                "id": "side1",
                "source": 1,  # External USB camera 1
                "position": "north",
                "priority": 7
            },
            # Uncomment and modify if you have more cameras:
            # {
            #     "id": "side2",
            #     "source": 2,  # External USB camera 2
            #     "position": "south",
            #     "priority": 7
            # },
            # {
            #     "id": "phone",
            #     "source": "http://192.168.1.100:8080/video",  # Phone IP Webcam
            #     "position": "east",
            #     "priority": 5
            # }
        ]
    }

    response = requests.post(f"{API_BASE}/multi-camera/setup", json=config)
    result = response.json()

    if result.get('success'):
        print("✅ Multi-camera system initialized!")
        print("\nCamera Status:")
        for cam_id, status in result.get('camera_statuses', {}).items():
            emoji = "✅" if status else "❌"
            print(f"  {emoji} {cam_id}: {'Started' if status else 'Failed'}")
        return True
    else:
        print(f"❌ Setup failed: {result.get('error')}")
        return False


def calibrate_cameras():
    """Calibrate all cameras"""
    print("\n📐 Calibrating cameras...")
    print("Make sure the chess board is visible to all cameras!")
    input("Press Enter when ready...")

    response = requests.post(f"{API_BASE}/multi-camera/calibrate")
    result = response.json()

    if result.get('success'):
        print("✅ Calibration complete!")
        print("\nCalibration Results:")
        for cam_id, success in result.get('calibration_results', {}).items():
            emoji = "✅" if success else "❌"
            print(f"  {emoji} {cam_id}: {'Calibrated' if success else 'Failed - board not visible'}")
        return True
    else:
        print(f"❌ Calibration failed: {result.get('error')}")
        return False


def check_status():
    """Get detailed status of all cameras"""
    print("\n📊 Checking camera status...")

    response = requests.get(f"{API_BASE}/multi-camera/status")
    result = response.json()

    if result.get('success'):
        print("\nCamera Details:")
        cameras = result.get('cameras', {})
        active_cam = result.get('active_camera')

        for cam_id, status in cameras.items():
            is_primary = "⭐ PRIMARY" if cam_id == active_cam else ""
            print(f"\n  📹 {cam_id} ({status['position']}) {is_primary}")
            print(f"     Active: {'✅' if status['active'] else '❌'}")
            print(f"     Calibrated: {'✅' if status['calibrated'] else '❌'}")
            print(f"     Board Visible: {'✅' if status['board_visible'] else '❌'}")
            print(f"     Quality Score: {status['quality_score']}/100")
            if status.get('obstruction_detected'):
                print(f"     ⚠️  Obstruction detected!")

        return True
    else:
        print(f"❌ Status check failed: {result.get('error')}")
        return False


def start_detection():
    """Start move detection"""
    print("\n🎯 Starting move detection...")

    response = requests.post(f"{API_BASE}/detection/start")
    result = response.json()

    if result.get('success'):
        print("✅ Detection started!")
        print("\n🎮 System is now monitoring for chess moves")
        print("   - Make a move on the physical board")
        print("   - The system will automatically use the best camera")
        print("   - Try blocking cameras to see automatic switching!")
        return True
    else:
        print(f"❌ Failed to start detection: {result.get('error')}")
        return False


def stop_system():
    """Stop the multi-camera system"""
    print("\n🛑 Stopping system...")

    # Stop detection first
    requests.post(f"{API_BASE}/detection/stop")

    # Stop multi-camera system
    response = requests.post(f"{API_BASE}/multi-camera/stop")
    result = response.json()

    if result.get('success'):
        print("✅ System stopped")
        return True
    else:
        print(f"❌ Failed to stop: {result.get('error')}")
        return False


def main():
    print("=" * 60)
    print("🎲 Communal Chess - Multi-Camera Test Script")
    print("=" * 60)

    try:
        # Step 1: Setup cameras
        if not setup_cameras():
            return

        # Step 2: Calibrate
        if not calibrate_cameras():
            return

        # Step 3: Check status
        check_status()

        # Step 4: Start detection
        start_detection()

        # Monitor status
        print("\n📡 Monitoring cameras (press Ctrl+C to stop)...")
        try:
            while True:
                time.sleep(10)
                check_status()
        except KeyboardInterrupt:
            print("\n\n⏸️  Interrupted by user")

    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to server!")
        print("   Make sure the Flask server is running:")
        print("   cd backend && python app.py")
        return
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        stop_system()


if __name__ == "__main__":
    main()
