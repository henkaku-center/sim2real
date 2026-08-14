#!/data/data/com.termux/files/usr/bin/python
import ctypes, fcntl, socket, sys, threading, errno
import serial
from serial import rfc2217

USBDEVFS_CONTROL = 3222820096
USBDEVFS_BULK = 3222820098
USBDEVFS_CLAIMINTERFACE = 2147767567
USBDEVFS_DISCONNECT_CLAIM = 2164806939
USBDEVFS_DISCONNECT_CLAIM_EXCEPT_DRIVER = 0x02

class Ctrl(ctypes.Structure):
    _fields_ = [
        ("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8),
        ("wValue", ctypes.c_uint16), ("wIndex", ctypes.c_uint16),
        ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
        ("data", ctypes.c_void_p),
    ]

class Bulk(ctypes.Structure):
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint), ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]

class DisconnectClaim(ctypes.Structure):
    _fields_ = [("interface", ctypes.c_uint), ("flags", ctypes.c_uint), ("driver", ctypes.c_char * 256)]

def ioctl_obj(fd, req, obj):
    return fcntl.ioctl(fd, req, obj, True)

class UsbCdcSerial:
    def __init__(self, fd):
        self.fd = fd
        self._baudrate = 115200
        self.bytesize = 8
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.xonxoff = False
        self.rtscts = False
        self.break_condition = False
        self._dtr = True
        self._rts = True
        self.cts = True
        self.dsr = True
        self.ri = False
        self.cd = True
        self.claim()
        self.apply_line()
        self.apply_control()

    def claim(self):
        for i in (0, 1):
            dc = DisconnectClaim(i, USBDEVFS_DISCONNECT_CLAIM_EXCEPT_DRIVER, b"")
            try:
                ioctl_obj(self.fd, USBDEVFS_DISCONNECT_CLAIM, dc)
            except OSError:
                pass
            ii = ctypes.c_uint(i)
            try:
                ioctl_obj(self.fd, USBDEVFS_CLAIMINTERFACE, ii)
            except OSError as e:
                print("claim", i, e, file=sys.stderr, flush=True)

    def ctrl(self, rt, req, val, idx, data=b""):
        if data:
            buf = ctypes.create_string_buffer(data)
            ptr = ctypes.cast(buf, ctypes.c_void_p)
        else:
            ptr = None
        c = Ctrl(rt, req, val, idx, len(data), 1000, ptr)
        return ioctl_obj(self.fd, USBDEVFS_CONTROL, c)

    def apply_line(self):
        b = int(self._baudrate).to_bytes(4, "little") + bytes([0, 0, int(self.bytesize)])
        try:
            self.ctrl(0x21, 0x20, 0, 0, b)
        except OSError as e:
            print("set_line", e, file=sys.stderr, flush=True)

    def apply_control(self):
        val = (1 if self._dtr else 0) | (2 if self._rts else 0)
        print("DTR", self._dtr, "RTS", self._rts, file=sys.stderr, flush=True)
        try:
            self.ctrl(0x21, 0x22, val, 0, b"")
        except OSError as e:
            print("set_ctl", e, file=sys.stderr, flush=True)

    @property
    def baudrate(self):
        return self._baudrate

    @baudrate.setter
    def baudrate(self, v):
        self._baudrate = int(v)
        print("baud", v, file=sys.stderr, flush=True)
        self.apply_line()

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, v):
        self._dtr = bool(v)
        self.apply_control()

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, v):
        self._rts = bool(v)
        self.apply_control()

    def write(self, data):
        data = bytes(data)
        off = 0
        while off < len(data):
            chunk = data[off:off + 4096]
            buf = ctypes.create_string_buffer(chunk)
            b = Bulk(0x03, len(chunk), 1000, ctypes.cast(buf, ctypes.c_void_p))
            try:
                n = ioctl_obj(self.fd, USBDEVFS_BULK, b)
            except OSError as e:
                print("usb write", e, file=sys.stderr, flush=True)
                raise
            off += n if n > 0 else len(chunk)
        return len(data)

    def read(self, size=4096, timeout_ms=1):
        buf = ctypes.create_string_buffer(size)
        b = Bulk(0x84, size, timeout_ms, ctypes.cast(buf, ctypes.c_void_p))
        try:
            n = ioctl_obj(self.fd, USBDEVFS_BULK, b)
        except OSError as e:
            if e.errno in (errno.ETIMEDOUT, errno.EAGAIN, errno.EPIPE, 110):
                return b""
            return b""
        return buf.raw[:max(0, n)]

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

class Conn:
    def __init__(self, sock):
        self.sock = sock
        self.lock = threading.Lock()

    def write(self, data):
        with self.lock:
            self.sock.sendall(data)

def handle(sock, ser):
    sock.settimeout(0.02)
    pm = rfc2217.PortManager(ser, Conn(sock))
    running = True

    def usb_reader():
        while running:
            d = ser.read(4096, 5)
            if d:
                try:
                    sock.sendall(b"".join(pm.escape(d)))
                except Exception:
                    break
            pm.check_modem_lines()

    th = threading.Thread(target=usb_reader, daemon=True)
    th.start()
    try:
        while True:
            try:
                d = sock.recv(4096)
            except socket.timeout:
                continue
            if not d:
                break
            out = b"".join(pm.filter(d))
            if out:
                ser.write(out)
    finally:
        running = False
        sock.close()

def main():
    fd = int(sys.argv[1])
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 7779
    ser = UsbCdcSerial(fd)
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", port))
    ls.listen(1)
    print("python rfc2217 bridge listening", port, "fd", fd, file=sys.stderr, flush=True)
    while True:
        s, addr = ls.accept()
        print("client", addr, file=sys.stderr, flush=True)
        handle(s, ser)

if __name__ == "__main__":
    main()
