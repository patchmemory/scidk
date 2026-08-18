#!/usr/bin/env python3
"""
Test the new streaming ReAct endpoint.

Sends a multi-step query that will trigger ReAct reasoning and displays
live step updates as they stream from the server.
"""
import pytest
import requests
import json
import time

BASE_URL = "http://localhost:5000"


# Hand-run script (see the __main__ block) that POSTs to a server already
# listening on BASE_URL. Nothing starts one for it, so under pytest it is an
# integration test by definition — unmarked, it was a ConnectionError on any
# machine without a dev server up, CI included.
@pytest.mark.integration
def test_streaming_react():
    """Test streaming endpoint with a ReAct query."""
    print("\n" + "="*70)
    print("Testing Streaming ReAct Endpoint")
    print("="*70)

    # This query should trigger ReAct (multi-step reasoning required)
    message = "Find all folders named 'data' and tell me how many files are inside them"

    print(f"\nQuery: {message}")
    print(f"\nSending POST request to /api/chat/graphrag/stream...")
    print("Expecting SSE stream with live step updates...\n")

    payload = {
        "message": message,
        "session_id": "test-streaming-react",
        "verbose": True
    }

    start_time = time.time()

    # Use stream=True to get response as it arrives
    with requests.post(
        f"{BASE_URL}/api/chat/graphrag/stream",
        json=payload,
        stream=True,
        timeout=180
    ) as response:

        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            print(response.text)
            return

        print("✅ Stream connected! Reading events...\n")
        print("-"*70)

        step_count = 0

        # Read SSE events line by line
        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode('utf-8')

            # SSE format: "data: {...json...}"
            if line.startswith('data: '):
                json_str = line[6:]  # Remove "data: " prefix

                try:
                    event = json.loads(json_str)
                    event_type = event.get('type', 'unknown')

                    if event_type == 'step':
                        step_count += 1
                        step_num = event.get('step_num', '?')
                        action = event.get('action', 'UNKNOWN')
                        content = event.get('content', '')
                        observation = event.get('observation', '')

                        # Display step
                        if action == 'THINK':
                            print(f"\n💭 Step {step_num}: THINKING")
                            print(f"   {content[:200]}{'...' if len(content) > 200 else ''}")

                        elif action == 'QUERY':
                            print(f"\n🔍 Step {step_num}: QUERYING")
                            print(f"   Query: {content[:150]}{'...' if len(content) > 150 else ''}")
                            if observation:
                                print(f"   Result: {observation[:150]}{'...' if len(observation) > 150 else ''}")

                        elif action == 'FINAL_ANSWER':
                            print(f"\n✅ Step {step_num}: FINAL ANSWER")

                    elif event_type == 'done':
                        elapsed = time.time() - start_time
                        print("\n" + "-"*70)
                        print(f"\n📦 FINAL RESPONSE:")
                        print(f"   {event.get('reply', 'No reply')}")

                        metadata = event.get('metadata', {})
                        print(f"\n📊 Metadata:")
                        print(f"   Engine: {event.get('engine', 'unknown')}")
                        print(f"   Steps: {metadata.get('steps_taken', 0)}")
                        print(f"   Queries: {metadata.get('queries_executed', 0)}")
                        print(f"   Server Time: {metadata.get('execution_time_ms', 0)}ms")
                        print(f"   Total Elapsed: {elapsed:.2f}s")
                        print(f"   Steps Streamed: {step_count}")

                    elif event_type == 'error':
                        print(f"\n❌ ERROR: {event.get('error', 'Unknown error')}")

                    elif event_type == 'info':
                        print(f"\nℹ️  {event.get('message', '')}")

                except json.JSONDecodeError as e:
                    print(f"⚠️  Failed to parse event: {e}")
                    print(f"   Raw: {json_str[:100]}")

    print("\n" + "="*70)
    print("✅ Test completed successfully!")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        test_streaming_react()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
