class EncodingError(Exception):
    def __init__(self, message):
        self.message = message
        super(EncodingError, self).__init__()
        

class ProtocolError(BaseException):
    pass