"""Gmail OAuth 2.0 authentication flow — run once per machine to generate token."""

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from src.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def authenticate_gmail():
    """Run the OAuth flow and save the token."""
    creds = None
    token_path = Path(settings.gmail_token_file)
    creds_path = Path(settings.gmail_credentials_file)

    # Check if token already exists
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    # If no valid credentials, run the flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Refreshing expired token...")
                creds.refresh(Request())
            except Exception as e:
                print(f"Refresh failed: {e}")
                print("Token revoked or expired beyond refresh — starting fresh OAuth flow...")
                creds = None

        if not creds or not creds.valid:
            if not creds_path.exists():
                print(f"ERROR: Credentials file not found at: {creds_path}")
                print("\nTo set up Gmail OAuth:")
                print("1. Go to https://console.cloud.google.com")
                print("2. Enable Gmail API")
                print("3. Create OAuth 2.0 Client ID (Desktop app)")
                print(f"4. Download credentials JSON and save as: {creds_path}")
                return

            print("Opening browser for Gmail OAuth consent...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the token
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"✓ Token saved to: {token_path}")

    print("✓ Gmail authentication successful!")
    print(f"  Token: {token_path}")
    return creds


if __name__ == "__main__":
    authenticate_gmail()
