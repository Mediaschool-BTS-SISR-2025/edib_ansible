TEST_USERS = {
    'alice': 'password123',
    'bob': 'password456',
    'admin': 'admin123',
}

def authenticate_test_user(username, password):
    return TEST_USERS.get(username) == password