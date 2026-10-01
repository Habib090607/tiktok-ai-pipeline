#!/usr/bin/env python3
"""
TikTok AI Content Pipeline (D-ID)
Generates a script with Claude, turns it into a D-ID talking avatar video,
and saves it locally for manual posting to TikTok.
"""

import argparse
import os
import sys
import time

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
D_ID_API_KEY = os.environ.get("D_ID_API_KEY")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"
D_ID_API_URL = "https://api.d-id.com"


def check_config():
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not D_ID_API_KEY:
        missing.append("D_ID_API_KEY")
    if missing:
        raise SystemExit(
            "Missing required environment variables: " + ", ".join(missing)
        )


def generate_script(topic: str) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = (
        "You write short-form TikTok scripts. Start with a strong hook in the first sentence. "
        "Keep the narration under 150 words, around 30-45 seconds spoken. Write plain narration only, "
        "no camera directions or emojis. End with a soft call to action. Return only the script text."
    )
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    return response.content[0].text.strip()


def d_id_headers():
    return {
        "Authorization": f"Bearer {D_ID_API_KEY}",
        "Content-Type": "application/json",
    }


def generate_video(script: str) -> dict:
    payload = {
        "script": {
            "type": "text",
            "input": script,
            "provider": {
                "type": "elevenlabs",
                "voice_id": ELEVENLABS_VOICE_ID,
            },
            "ssml": False,
        },
        "config": {
            "fluent": True,
            "pad_audio": 0,
        },
        "source_url": "https://d-id-public-bucket.s3.amazonaws.com/videos/d91f11ba960bd50229a8970f86e44f51.jpg",
    }

    response = requests.post(f"{D_ID_API_URL}/talks", headers=d_id_headers(), json=payload, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"D-ID request failed: {response.status_code} {response.text}")

    data = response.json()
    talk_id = data.get("id")
    if not talk_id:
        raise RuntimeError(f"Could not create D-ID talk: {data}")

    for _ in range(60):
        time.sleep(5)
        status_response = requests.get(f"{D_ID_API_URL}/talks/{talk_id}", headers=d_id_headers(), timeout=60)
        if status_response.status_code >= 400:
            raise RuntimeError(f"D-ID status check failed: {status_response.status_code} {status_response.text}")

        status = status_response.json()
        state = status.get("status")
        if state == "done":
            return {
                "id": talk_id,
                "url": status.get("result_url"),
                "preview_url": status.get("preview_url"),
            }
        if state == "error":
            raise RuntimeError(f"D-ID generation failed: {status}")

    raise TimeoutError("D-ID video generation timed out")


def download_video(video_url: str, output_path: str) -> str:
    response = requests.get(video_url, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate a TikTok script and video with D-ID")
    parser.add_argument("--topic", required=True, help="Topic for the video")
    parser.add_argument("--output", default="output_video.mp4", help="Output filename")
    args = parser.parse_args()

    check_config()
    script = generate_script(args.topic)
    print("SCRIPT:\n" + script)
    video = generate_video(script)
    save_path = download_video(video["url"], args.output)
    print(f"VIDEO_SAVED:{save_path}")
    print(f"VIDEO_URL:{video['url']}")


if __name__ == "__main__":
    main()
