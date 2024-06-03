from typing import List, Dict
import re
from collections import OrderedDict

from src.const import TOKEN_INTEGER, TOKEN_END, TOKEN_DICT,\
                  TOKEN_LIST, TOKEN_STRING_SEPERATOR
from src.exc import EncodingError

class Decoder:
    def __init__(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError(f"{self.__class__.__name__} only accepts bytes input")
        self._data = data
        self._index = 0
        self._size = len(self._data)
        
        self._handler = {
            TOKEN_INTEGER: self._decode_int,
            TOKEN_LIST: self._decode_list,
            TOKEN_DICT: self._decode_dict,
            
        }
    
    def decode(self):
        ch = self._peek()
        if ch is None:
            raise EOFError()
        elif ch in self._handler:
            return self._handler[ch]()
        elif re.match(b'^[0-9]$', ch):
            return self._decode_str()
        else:
            raise EncodingError(f"Invalid token read at {self._index}")
    
    def _peek(self):
        if self._index + 1 >= self._size:
            return
        res= self._data[self._index: self._index+1]
        return res
    
    def _consume(self, length: int=1):
        self._index += length

    def _read(self, length: int) -> bytes:
        if self._index + length > self._size:
            raise EncodingError(f"Cannot read {length} bytes from current position {self._index}")

        res = self._data[self._index: self._index+length]
        self._consume(length)
        return res
    
    def _read_until(self, token: bytes) -> bytes:
        try:
            token_idx = self._data.index(token, self._index)
            return self._read(token_idx-self._index+1).rstrip(token)
        except ValueError:
            raise EncodingError(f"Unable to find token {str(token)}")

    def _decode_int(self):
        self._consume()
        return int(self._read_until(TOKEN_END))
    
    def _decode_str(self):
        str_len = int(self._read_until(TOKEN_STRING_SEPERATOR))
        return self._read(str_len)
    def _decode_list(self):
        self._consume()
        res = []
        while self._data[self._index: self._index+1] != TOKEN_END:
            res.append(self.decode())
        self._consume()
        return res
    
    def _decode_dict(self):
        self._consume()
        res = OrderedDict()
        while self._data[self._index:self._index+1] != TOKEN_END:
            k = self.decode()
            v = self.decode()
            res[k] = v
        self._consume()
        return res
    
class Encoder:        
    def __init__(self, data):
        self._data = data
        
        self._handler = {
            int: self._encode_int,
            str: self._encode_str,
            bytes: self._encode_bytes,
            list: self._encode_list,
            dict: self._encode_dict,
            OrderedDict: self._encode_dict
        }
        
    def encode(self) -> bytes:
        return self._encode_next(self._data)
    
    def _encode_next(self, data):
        try:
            return self._handler[type(data)](data)
        except KeyError:
            return
    
    def _encode_int(self, value: int) -> bytes:
        return TOKEN_INTEGER + f"{value}".encode() + TOKEN_END
    
    def _encode_str(self, value: str) -> bytes:
        return f"{len(value)}".encode() + TOKEN_STRING_SEPERATOR + f"{value}".encode()
    
    def _encode_bytes(self, value: bytes) -> bytes:
        return str(len(value)).encode() + TOKEN_STRING_SEPERATOR + value 
    
    def _encode_list(self, value: List) -> bytes:
        result = TOKEN_LIST
        for item in value:
            result += self._encode_next(item)
        result += TOKEN_END
        return result

    def _encode_dict(self, value: Dict) -> bytes:
        result = TOKEN_DICT
        for k, v in value.items():
            result += self._encode_next(k)
            result += self._encode_next(v)
        result += TOKEN_END
        return result
                
        
        
    
    