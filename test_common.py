"""
test_common.py - 测试 common.py 协议编解码
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from common import (
    encode, decode, make_hello, make_heartbeat, make_list_response, make_bye,
)

def test_encode_decode():
    # 测试基本编解码
    msg = make_hello("测试机", "Windows 10")
    data = encode(msg)
    print(f"[测试] 编码后字节: {data[:20]}... 总长={len(data)}")

    decoded = decode(data)
    print(f"[测试] 解码结果: {decoded}")
    assert decoded["type"] == "hello"
    assert decoded["name"] == "测试机"
    print("[通过] 基本编解码 ✓")

def test_heartbeat():
    data = encode(make_heartbeat())
    decoded = decode(data)
    assert decoded["type"] == "heartbeat"
    print("[通过] 心跳消息 ✓")

def test_list_response():
    machines = [
        {"id": "abc", "name": "PC1", "os": "Win10", "status": "online"},
        {"id": "def", "name": "PC2", "os": "Win11", "status": "online"},
    ]
    data = encode(make_list_response(machines))
    decoded = decode(data)
    assert len(decoded["machines"]) == 2
    print(f"[通过] 机器列表: {decoded['machines']} ✓")

def test_bye():
    data = encode(make_bye())
    decoded = decode(data)
    assert decoded["type"] == "bye"
    print("[通过] 下线消息 ✓")

if __name__ == "__main__":
    print("=" * 40)
    print("  协议编解码测试")
    print("=" * 40)
    test_encode_decode()
    test_heartbeat()
    test_list_response()
    test_bye()
    print("=" * 40)
    print("  全部测试通过! ✓")
