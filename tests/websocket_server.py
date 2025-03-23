#!/usr/bin/env python3
import asyncio
import json
import websockets
import time

# Configuration
WS_SERVER = "ws://localhost:8000/ws"
MOTORS = ["base", "shoulder", "elbow", "wrist", "hand", "thumb"]
TEST_SPEED = 50  # Optional speed value to include in commands

async def test_robot_motors():
    print(f"Connecting to WebSocket server at {WS_SERVER}...")
    
    try:
        async with websockets.connect(WS_SERVER) as websocket:
            print("✅ Connected to WebSocket server successfully")
            
            # Test incrementing all motors
            print("\n--- Testing INCREMENT for all motors ---")
            for motor in MOTORS:
                command = {
                    "command": "move",
                    "motor": motor,
                    "direction": "inc",
                    "speed": TEST_SPEED
                }
                
                command_json = json.dumps(command)
                print(f"Sending: {command_json}")
                
                await websocket.send(command_json)
                response = await websocket.recv()
                print(f"Response: {response}")
                
                # Wait a moment before stopping
                await asyncio.sleep(2)
                
                # Stop the motor
                stop_command = {
                    "command": "stop",
                    "motor": motor
                }
                
                stop_json = json.dumps(stop_command)
                print(f"Sending stop: {stop_json}")
                
                await websocket.send(stop_json)
                stop_response = await websocket.recv()
                print(f"Stop response: {stop_response}")
                
                # Brief pause between motors
                await asyncio.sleep(1)
            
            # Test decrementing all motors
            print("\n--- Testing DECREMENT for all motors ---")
            for motor in MOTORS:
                command = {
                    "command": "move",
                    "motor": motor,
                    "direction": "dec",
                    "speed": TEST_SPEED
                }
                
                command_json = json.dumps(command)
                print(f"Sending: {command_json}")
                
                await websocket.send(command_json)
                response = await websocket.recv()
                print(f"Response: {response}")
                
                # Wait a moment before stopping
                await asyncio.sleep(2)
                
                # Stop the motor
                stop_command = {
                    "command": "stop",
                    "motor": motor
                }
                
                stop_json = json.dumps(stop_command)
                print(f"Sending stop: {stop_json}")
                
                await websocket.send(stop_json)
                stop_response = await websocket.recv()
                print(f"Stop response: {stop_response}")
                
                # Brief pause between motors
                await asyncio.sleep(1)
            
            # Test stop_all command
            print("\n--- Testing STOP ALL command ---")
            stop_all_command = {
                "command": "stop_all"
            }
            
            stop_all_json = json.dumps(stop_all_command)
            print(f"Sending stop all: {stop_all_json}")
            
            await websocket.send(stop_all_json)
            stop_all_response = await websocket.recv()
            print(f"Stop all response: {stop_all_response}")
            
            print("\nAll tests completed successfully!")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nPlease make sure the WebSocket server is running at localhost:8000")

if __name__ == "__main__":
    print("Simple Robot Motor Test")
    print("======================")
    print("This script will test increment and decrement commands for all motors.")
    print("Make sure the WebSocket server is running before continuing.")
    
    input("Press Enter to start the tests...")
    
    asyncio.run(test_robot_motors())
