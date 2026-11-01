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
