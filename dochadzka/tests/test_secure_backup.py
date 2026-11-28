from secure_backup import seal, unseal
import pytest

def test_encrypted_backup_roundtrip():
    payload={"format":"bid-attendance-v1","tables":{"employee":[{"id":7,"name":"Fiktivny Testovaci"}]}}
    password="not-a-production-password-2026"
    encrypted=seal(payload,password)
    assert b"Fiktivny Testovaci" not in encrypted
    assert encrypted.startswith(b"BID-ATTENDANCE-BACKUP-1")
    assert unseal(encrypted,password)==payload

def test_bad_password_and_tampered_backup():
    payload={"format":"bid-attendance-v1","tables":{}}
    encrypted=seal(payload,"long-password-for-backup")
    with pytest.raises(Exception):unseal(encrypted,"wrong-long-password-123")
    tampered=bytearray(encrypted)
    tampered[-1]^=1
    with pytest.raises(Exception):unseal(bytes(tampered),"long-password-for-backup")
