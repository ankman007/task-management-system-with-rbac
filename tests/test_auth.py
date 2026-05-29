def test_user_signup(client):
    response = client.post(
        "/auth/signup",
        json={
            "email": "testuser@example.com",
            "password": "strongpassword123",
            "role_id": 1,
        },
    )

    assert response.status_code == 201

    assert response.json()["user"]["email"] == "testuser@example.com"
    assert "access_token" in response.json()


def test_login_success(client):
    # 1. First, register the user so they actually exist in your memory database
    client.post(
        "/auth/signup",
        json={
            "email": "testuser@example.com",
            "password": "strongpassword123",
            "role_id": 1,
        },
    )

    # 2. Login using 'json=' instead of 'data=' with matching schema keys
    response = client.post(
        "/auth/login",
        json={"email": "testuser@example.com", "password": "strongpassword123"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
