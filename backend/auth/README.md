# Backend Auth Module

## Purpose
Handles authentication, JWT session token generation, CSRF token issuance, password hashing (PBKDF2/SHA256), Fernet encryption of secrets, and HTTP security headers.

## Contained Modules
- `security_utils.py`: Cryptographic helpers and token validators.

## Dependencies
- `PyJWT`, `cryptography` (Fernet), `hashlib`, `hmac`.

## Entry Points
- `issue_jwt(payload)`: Sign JWT session tokens.
- `verify_jwt(token)`: Decode and validate session tokens.
- `hash_password(password)`: Generate salted password hashes.
- `verify_password(password, hash_str)`: Verify password credentials.

## Important Files
- [`security_utils.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/auth/security_utils.py)
