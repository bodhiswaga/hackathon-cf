from .test_acceptance import client, auth


def test_logout_revokes_only_current_session(client):
    first, second = auth(client), auth(client)
    assert client.post('/api/auth/logout', headers=first).status_code == 200
    assert client.get('/api/auth/me', headers=first).status_code == 401
    assert client.get('/api/auth/me', headers=second).status_code == 200
