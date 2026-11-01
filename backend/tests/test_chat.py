import pytest
from fastapi import WebSocket

from backend.connection_manager import ConnectionManager
from backend.schemas import clean_text


def test_clean_text():
    assert clean_text("  小雨 ", max_length=20, label="昵称") == "小雨"
    with pytest.raises(ValueError):
        clean_text(" ", max_length=20, label="昵称")
    with pytest.raises(ValueError):
        clean_text("a" * 21, max_length=20, label="昵称")


def test_connection_manager_count():
    manager = ConnectionManager()
    class Socket(WebSocket):
        pass
    socket = object.__new__(Socket)
    client = manager.add("小雨", socket)
    assert manager.count == 1
    manager.remove(client.user_id)
    assert manager.count == 0


def test_presence_lists_members_on_join_and_leave(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    def receive_presence(socket):
        while True:
            packet = socket.receive_json()
            if packet['type'] == 'presence':
                return packet

    with TestClient(app) as client:
        with client.websocket_connect('/ws?nickname=Alice') as first:
            first_ready = first.receive_json()
            assert first_ready['members'] == [{'userId': first_ready['userId'], 'nickname': 'Alice'}]
            receive_presence(first)
            with client.websocket_connect('/ws?nickname=Bob') as second:
                second_ready = second.receive_json()
                assert {x['nickname'] for x in second_ready['members']} == {'Alice', 'Bob'}
                assert {x['nickname'] for x in receive_presence(first)['members']} == {'Alice', 'Bob'}
            assert [x['nickname'] for x in receive_presence(first)['members']] == ['Alice']
