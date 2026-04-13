# -*- coding: utf-8 -*-
"""
Quick test: Verify your Angel One TOTP secret is correct.
Run: python3 test_totp.py
"""
import sys

try:
    import pyotp
except ImportError:
    print("Installing pyotp...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyotp"])
    import pyotp

print()
print("=" * 40)
print("  ANGEL ONE TOTP TESTER")
print("=" * 40)
print()

secret = input("Paste your TOTP secret (from SmartAPI portal): ").strip()

# Clean the secret
secret = secret.replace(" ", "").upper()

print(f"\nCleaned secret: {secret}")
print(f"Length: {len(secret)} characters")

# Check if valid base32
import re
if not re.match(r'^[A-Z2-7=]+$', secret):
    print("\nERROR: This is NOT a valid TOTP secret!")
    print("Valid characters: A-Z and 2-7 only")
    print("No spaces, no lowercase, no special characters")
    bad_chars = [c for c in secret if c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567="]
    if bad_chars:
        print(f"Bad characters found: {bad_chars}")
    print("\nGo to smartapi.angelbroking.com -> Enable TOTP -> Copy the secret text")
    sys.exit(1)

try:
    totp = pyotp.TOTP(secret).now()
    print(f"\nGenerated TOTP code: {totp}")
    print("\nNow open Google Authenticator on your phone.")
    print(f"Does it show the same code? {totp}")
    print()
    match = input("Do they match? (y/n): ").strip().lower()
    
    if match == "y":
        print("\nSECRET IS CORRECT! Use this in setup:")
        print(f"  TOTP Secret: {secret}")
        print("\nNow run: python3 start.py --setup")
    else:
        print("\nSECRET IS WRONG. You need to:")
        print("  1. Go to smartapi.angelbroking.com")
        print("  2. Profile -> Disable TOTP")
        print("  3. Re-enable TOTP")  
        print("  4. Copy the NEW secret text below the QR code")
        print("  5. Also scan QR in Google Authenticator")
        print("  6. Run this test again with the new secret")
        
except Exception as e:
    print(f"\nERROR: {e}")
    print("This secret is invalid. Get a fresh one from SmartAPI portal.")
