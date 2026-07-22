from __future__ import annotations

import hashlib
import json
from base64 import b64decode, urlsafe_b64encode
from gzip import decompress

import pytest
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

from wwps import nhn_crypt
from wwps.rows import YwpUserItem, YwpUserYoukai, parser_for
from wwps.table_parser import TableParser

SALT = b"0bk2kvtFE2"


def client_encrypt(text: str) -> str:
    payload = text.encode("utf-8")
    first = hashlib.sha1(SALT + b" " + payload).digest()
    digest = hashlib.sha1(SALT + first).digest()
    blob = AES.new(nhn_crypt.NHN_KEY, AES.MODE_ECB).encrypt(
        pad(digest + payload, AES.block_size))
    return urlsafe_b64encode(blob).decode()


def client_decrypt(token: str) -> str:
    token = token.replace("-", "+").replace("_", "/")
    token += "=" * ((-len(token)) % 4)
    raw = unpad(AES.new(nhn_crypt.NHN_KEY, AES.MODE_ECB).decrypt(b64decode(token)),
                AES.block_size)
    return decompress(raw[20:]).decode("utf-8")


@pytest.mark.parametrize("payload", [
    '{"level5UserId":"abc","stageId":1001001}',
    '{"playerName":"ñandú","emoji":"x"}',
    "{}",
])
def test_server_reads_client_requests(payload):
    assert nhn_crypt.decrypt_request(client_encrypt(payload)) == payload


@pytest.mark.parametrize("payload", [
    '{"resultCode":0}',
    json.dumps({"name": "ñ", "list": [1, 2, 3]}),
])
def test_client_reads_server_responses(payload):
    assert client_decrypt(nhn_crypt.encrypt_response(payload)) == payload


def test_response_token_is_url_safe():
    token = nhn_crypt.encrypt_response(json.dumps({"x": "y" * 400}))
    assert "+" not in token and "/" not in token


def test_raw_table_roundtrip():
    parser = TableParser("1|2|3*4|5|6")
    assert parser.table == [["1", "2", "3"], ["4", "5", "6"]]
    assert str(parser) == "1|2|3*4|5|6"


def test_raw_table_find_index():
    parser = TableParser("10|a*20|b*30|c")
    assert parser.find_index(["20"]) == 1
    assert parser.find_index(["99"]) == -1


def test_empty_table_add_row():
    parser = TableParser("")
    parser.add_row(["7", "8"])
    assert str(parser) == "7|8"


def test_typed_table_roundtrip():
    parser = parser_for(YwpUserItem, "10|3*20|5")
    assert [(i.ItemId, i.Count) for i in parser.items] == [(10, 3), (20, 5)]
    parser.items[0].Count += 7
    assert str(parser) == "10|10*20|5"


def test_typed_table_alternate_delimiter():
    parser = parser_for(YwpUserItem, "10^3*20^5", delimiter="^")
    assert [(i.ItemId, i.Count) for i in parser.items] == [(10, 3), (20, 5)]


def test_typed_table_survives_bad_cells():
    parser = parser_for(YwpUserItem, "10|notanumber")
    assert parser.items[0].ItemId == 10
    assert parser.items[0].Count == 0


def test_row_field_order_is_the_wire_format():
    names = [name for name, _ in YwpUserYoukai.FIELDS]
    assert names == [
        "YoukaiId", "Level", "Exp", "Hp", "Atk", "ExpDenominator",
        "ExpNumerator", "Percentage", "IsLockedLevel", "BefriendDate",
        "BreakLimitCount"]
