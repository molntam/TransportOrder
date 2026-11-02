import base64
import ctypes
import os


def protect(value, decrypt=False):
    if os.name != 'nt':
        return value
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value[6:]) if decrypt else value.encode()
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    method = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('Windows could not protect the workstation pairing key.')
    try:
        result = ctypes.string_at(output.data, output.size)
        return result.decode() if decrypt else 'dpapi:' + base64.b64encode(result).decode()
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))
