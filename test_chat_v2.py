#!/usr/bin/env python3
"""
Test script for Chat GraphRAG v2 API.

Tests both non-streaming and streaming endpoints with multiple providers.

Usage:
    # Test with default provider (from env)
    python test_chat_v2.py

    # Test specific provider
    python test_chat_v2.py --provider ollama

    # Test streaming
    python test_chat_v2.py --stream

    # Test all providers
    python test_chat_v2.py --all-providers
"""
import argparse
import requests
import json
import time
import sys


BASE_URL = "http://localhost:5000"


def test_non_streaming(message: str, provider: str = None):
    """Test non-streaming endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing Non-Streaming{f' ({provider})' if provider else ''}")
    print(f"{'='*60}")
    print(f"Message: {message}")

    payload = {"message": message}
    if provider:
        payload["provider"] = provider

    start = time.time()
    response = requests.post(
        f"{BASE_URL}/api/chat/graphrag/v2",
        json=payload,
        timeout=120
    )
    elapsed = time.time() - start

    print(f"\nStatus: {response.status_code}")
    print(f"Elapsed: {elapsed:.2f}s")

    if response.status_code == 200:
        data = response.json()
        print(f"\nReply: {data.get('reply', '')}")
        print(f"\nMetadata:")
        for k, v in data.get('metadata', {}).items():
            print(f"  {k}: {v}")
    else:
        print(f"Error: {response.text}")


def test_streaming(message: str, provider: str = None):
    """Test streaming endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing Streaming{f' ({provider})' if provider else ''}")
    print(f"{'='*60}")
    print(f"Message: {message}")

    payload = {"message": message}
    if provider:
        payload["provider"] = provider

    print(f"\nStreaming response:\n")

    start = time.time()
    response = requests.post(
        f"{BASE_URL}/api/chat/graphrag/v2/stream",
        json=payload,
        stream=True,
        timeout=120
    )

    if response.status_code != 200:
        print(f"Error: {response.text}")
        return

    full_response = []
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    event = json.loads(line_str[6:])
                    if event.get('type') == 'token':
                        content = event.get('content', '')
                        print(content, end='', flush=True)
                        full_response.append(content)
                    elif event.get('type') == 'done':
                        elapsed = time.time() - start
                        metadata = event.get('metadata', {})
                        print(f"\n\nCompleted in {elapsed:.2f}s")
                        print(f"Metadata:")
                        for k, v in metadata.items():
                            print(f"  {k}: {v}")
                    elif event.get('type') == 'error':
                        print(f"\nError: {event.get('error')}")
                except json.JSONDecodeError:
                    pass

    print(f"\n\nFull response: {''.join(full_response)}")


def check_providers():
    """Check available providers."""
    print(f"\n{'='*60}")
    print("Checking Available Providers")
    print(f"{'='*60}")

    response = requests.get(f"{BASE_URL}/api/chat/providers")

    if response.status_code == 200:
        data = response.json()
        providers = data.get('providers', {})

        for name, info in providers.items():
            status = info.get('status', 'unknown')
            print(f"\n{name.upper()}:")
            print(f"  Status: {status}")

            if status == 'ok':
                print(f"  Model: {info.get('model', 'N/A')}")
                if 'endpoint' in info:
                    print(f"  Endpoint: {info['endpoint']}")
                if 'available_models' in info:
                    models = info['available_models']
                    print(f"  Available Models: {', '.join(models[:3])}{'...' if len(models) > 3 else ''}")
            elif status == 'not_configured':
                print(f"  Hint: {info.get('hint', 'Configure this provider')}")
            elif status == 'error':
                print(f"  Error: {info.get('error', 'Unknown error')}")
    else:
        print(f"Error: {response.text}")


def check_schema_cache():
    """Check schema cache stats."""
    print(f"\n{'='*60}")
    print("Schema Cache Statistics")
    print(f"{'='*60}")

    response = requests.get(f"{BASE_URL}/api/chat/schema/cache/stats")

    if response.status_code == 200:
        data = response.json()
        print(f"Cache Size: {data.get('size', 0)}")
        print(f"TTL: {data.get('ttl_seconds', 0)}s")
        print(f"Cached Keys: {data.get('keys', [])}")

        timestamps = data.get('timestamps', {})
        if timestamps:
            print(f"Timestamps:")
            for key, ts in timestamps.items():
                print(f"  {key}: {ts}")
    else:
        print(f"Error: {response.text}")


def main():
    parser = argparse.ArgumentParser(description="Test Chat GraphRAG v2 API")
    parser.add_argument("--message", "-m", default="How many File nodes are in the database?",
                       help="Message to send")
    parser.add_argument("--provider", "-p", choices=['ollama', 'anthropic', 'openai'],
                       help="Specific provider to test")
    parser.add_argument("--stream", "-s", action="store_true",
                       help="Test streaming endpoint")
    parser.add_argument("--all-providers", "-a", action="store_true",
                       help="Test all available providers")
    parser.add_argument("--check-cache", "-c", action="store_true",
                       help="Check schema cache stats")
    parser.add_argument("--list-providers", "-l", action="store_true",
                       help="List available providers")

    args = parser.parse_args()

    # Check if server is running
    try:
        requests.get(f"{BASE_URL}/api/health", timeout=2)
    except requests.exceptions.RequestException:
        print(f"Error: Cannot reach SciDK at {BASE_URL}")
        print("Make sure SciDK is running: python -m scidk")
        sys.exit(1)

    if args.list_providers:
        check_providers()
        return

    if args.check_cache:
        check_schema_cache()
        return

    if args.all_providers:
        # Test all available providers
        check_providers()
        for provider in ['ollama', 'anthropic', 'openai']:
            try:
                if args.stream:
                    test_streaming(args.message, provider)
                else:
                    test_non_streaming(args.message, provider)
            except Exception as e:
                print(f"Skipping {provider}: {e}")
        return

    # Single test
    try:
        if args.stream:
            test_streaming(args.message, args.provider)
        else:
            test_non_streaming(args.message, args.provider)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
