"""
Generate Gmail OAuth2 Refresh Token

This script guides you through the OAuth2 flow to obtain a refresh token.

Run: python get_refresh_token.py
"""

import json
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

# Load credentials from file
with open("credentials.json", "r") as f:
    creds = json.load(f)["installed"]

CLIENT_ID = creds["client_id"]
CLIENT_SECRET = creds["client_secret"]
REDIRECT_URI = "http://localhost:8080"

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# OAuth2 URLs
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class CallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth2 callback."""

    auth_code = None

    def do_GET(self):
        query = urlparse(self.path).query
        params = parse_qs(query)

        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Success!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error: No auth code received")

    def log_message(self, format, *args):
        pass  # Suppress server logs


def main():
    print("=" * 60)
    print("Gmail OAuth2 Refresh Token Generator")
    print("=" * 60)

    # Step 1: Build authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }

    auth_url = f"{AUTH_URL}?" + "&".join(
        f"{k}={v}" for k, v in auth_params.items()
    )

    print(f"\nClient ID: {CLIENT_ID[:20]}...")
    print(f"\nScopes: {', '.join(SCOPES)}")

    # Step 2: Start local server
    server = HTTPServer(("localhost", 8080), CallbackHandler)

    print("\n" + "-" * 60)
    print("Opening browser for authorization...")
    print("If browser doesn't open, visit this URL:")
    print(f"\n{auth_url}\n")
    print("-" * 60)

    # Step 3: Open browser
    webbrowser.open(auth_url)

    # Step 4: Wait for callback
    print("\nWaiting for authorization...")
    while CallbackHandler.auth_code is None:
        server.handle_request()

    server.server_close()

    auth_code = CallbackHandler.auth_code
    print(f"\nAuthorization code received!")

    # Step 5: Exchange code for tokens
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(TOKEN_URL, data=token_data)

    if response.status_code != 200:
        print(f"\nError exchanging code: {response.text}")
        return

    tokens = response.json()

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    print("\n" + "=" * 60)
    print("SUCCESS! Here are your tokens:")
    print("=" * 60)
    print(f"\nREFRESH TOKEN:\n{refresh_token}")
    print(f"\nACCESS TOKEN (expires in {tokens.get('expires_in')}s):\n{access_token[:50]}...")

    # Step 6: Update .env file
    print("\n" + "-" * 60)

    # Read current .env or create new one
    env_content = ""
    try:
        with open(".env", "r") as f:
            env_content = f.read()
    except FileNotFoundError:
        pass

    # Update or add refresh token
    lines = env_content.split("\n") if env_content else []
    updated = False
    new_lines = []

    for line in lines:
        if line.startswith("GMAIL_REFRESH_TOKEN="):
            new_lines.append(f"GMAIL_REFRESH_TOKEN={refresh_token}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"GMAIL_REFRESH_TOKEN={refresh_token}")

    with open(".env", "w") as f:
        f.write("\n".join(new_lines))

    print("Updated .env file with refresh token!")
    print("\nYou can now run: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
