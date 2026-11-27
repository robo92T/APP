from auth import make_hash, verify_password

def test_correct_password():
    secret = "Long-Password-For-Test-12345"
    hashed = make_hash(secret)
    assert secret not in hashed
    assert verify_password(secret, hashed)
    assert not verify_password("wrong", hashed)

def test_invalid_hash_fails_closed():
    assert not verify_password("anything", "invalid")
