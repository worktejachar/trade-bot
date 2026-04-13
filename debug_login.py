# -*- coding: utf-8 -*-
"""
Angel One Login Debugger
Tests each credential separately to find exactly what's wrong.
Run: python3 debug_login.py
"""
import sys
import time

try:
    import pyotp
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyotp"])
    import pyotp

try:
    from SmartApi import SmartConnect
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "smartapi-python"])
    from SmartApi import SmartConnect

print()
print("=" * 50)
print("  ANGEL ONE LOGIN DEBUGGER")
print("  Testing each credential step by step")
print("=" * 50)
print()

# Get credentials manually
api_key = input("API Key: ").strip()
client_id = input("Client ID (like V323414): ").strip()
password = input("PIN/MPIN: ").strip()
totp_secret = input("TOTP Secret: ").strip()

# Clean TOTP secret
totp_secret = totp_secret.replace(" ", "").upper()

print()
print("-" * 50)
print("CHECKING EACH PIECE:")
print("-" * 50)

# Check 1: API Key
print(f"\n1. API Key: '{api_key}' ({len(api_key)} chars)")
if len(api_key) < 5:
    print("   ERROR: API key too short. Get it from smartapi.angelbroking.com -> My Apps")
else:
    print("   OK: Length looks valid")

# Check 2: Client ID
print(f"\n2. Client ID: '{client_id}'")
if not client_id[0].isalpha():
    print("   WARNING: Usually starts with a letter (like V, S, A)")
else:
    print("   OK: Format looks valid")

# Check 3: Password
print(f"\n3. Password: '{password}' ({len(password)} chars)")
if len(password) == 4:
    print("   OK: 4-digit PIN")
elif len(password) == 6:
    print("   OK: 6-digit MPIN")
else:
    print(f"   WARNING: Usually 4 or 6 digits, yours is {len(password)}")

# Check 4: TOTP
print(f"\n4. TOTP Secret: '{totp_secret}' ({len(totp_secret)} chars)")

import re
if not re.match(r'^[A-Z2-7=]+$', totp_secret):
    bad = [c for c in totp_secret if c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567="]
    print(f"   ERROR: Invalid base32 characters: {bad}")
    print("   TOTP secret can only contain A-Z and 2-7")
    print("   Get fresh secret from: smartapi.angelbroking.com/enable-totp")
else:
    print("   OK: Valid base32 format")

# Generate TOTP
try:
    totp_code = pyotp.TOTP(totp_secret).now()
    print(f"\n   Generated TOTP: {totp_code}")
    print(f"   Check Google Authenticator — does it show {totp_code}?")
    
    match = input("   Match? (y/n): ").strip().lower()
    if match != "y":
        print("\n   PROBLEM FOUND: TOTP secret doesn't match your authenticator!")
        print("   This means the secret is wrong.")
        print("   Solution: Get the secret from SmartAPI portal, not Angel One app")
        sys.exit(1)
except Exception as e:
    print(f"   ERROR generating TOTP: {e}")
    sys.exit(1)

# Now try actual login
print()
print("-" * 50)
print("ATTEMPTING LOGIN...")
print("-" * 50)

# Generate fresh TOTP right before login (timing matters!)
time.sleep(1)  # Small delay to ensure we're not at boundary
totp_code = pyotp.TOTP(totp_secret).now()
print(f"Fresh TOTP: {totp_code}")

try:
    api = SmartConnect(api_key=api_key)
    data = api.generateSession(client_id, password, totp_code)
    
    if data and data.get("status") == True:
        print("\n✅ LOGIN SUCCESSFUL!")
        print(f"   Name: {data.get('data', {}).get('name', 'Unknown')}")
        print("\n   Your credentials are correct. Run: python3 start.py --setup")
    else:
        print(f"\n❌ LOGIN FAILED: {data}")
        msg = data.get("message", "") if data else ""
        
        if "totp" in msg.lower():
            print("\n   DIAGNOSIS: TOTP is wrong")
            print("   Even though the code matched Authenticator,")
            print("   the SECRET might not be registered with SmartAPI.")
            print()
            print("   FIX: Go to smartapi.angelbroking.com")
            print("   -> Login -> Profile -> TOTP section")
            print("   -> If you see 'Enable TOTP' -> click it -> get new secret")
            print("   -> If already enabled -> try disabling from Angel One app")
            print("      (Angel One app -> Settings -> TOTP -> Disable)")
            print("   -> Then re-enable from SmartAPI portal")
            
        elif "password" in msg.lower() or "client" in msg.lower():
            print("\n   DIAGNOSIS: Password or Client ID wrong")
            print("   -> Try your MPIN (from Angel One app) instead of login PIN")
            print("   -> Verify Client ID matches your Angel One account exactly")
            
        else:
            print(f"\n   Unknown error: {msg}")
            
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    
    if "Non-base32" in str(e):
        print("\n   DIAGNOSIS: TOTP secret has invalid characters")
        print("   FIX: Copy secret again without any spaces or special characters")
