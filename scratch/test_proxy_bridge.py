from DrissionPage import ChromiumPage, ChromiumOptions
import time, socket, base64, threading

class LocalAuthProxyBridge:
    def __init__(self, target_ip: str, target_port: int, user: str, password: str):
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.user = user
        self.password = password
        self.server_socket = None
        self.port = 0
        self.is_running = False
        self._thread = None

    def start(self) -> str:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(50)
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return f"127.0.0.1:{self.port}"

    def _listen_loop(self):
        auth_header = "Proxy-Authorization: Basic " + base64.b64encode(f"{self.user}:{self.password}".encode()).decode() + "\r\n"
        while self.is_running:
            try:
                client_sock, _ = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, auth_header), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, client_sock, auth_header):
        try:
            remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_sock.settimeout(15)
            remote_sock.connect((self.target_ip, self.target_port))
            
            data = client_sock.recv(8192)
            if not data:
                client_sock.close()
                remote_sock.close()
                return

            lines = data.split(b"\r\n")
            new_lines = [lines[0]] + [auth_header.encode()] + lines[1:]
            modified_data = b"\r\n".join(new_lines)
            remote_sock.sendall(modified_data)

            def pipe(src, dst):
                try:
                    while True:
                        buf = src.recv(8192)
                        if not buf:
                            break
                        dst.sendall(buf)
                except Exception:
                    pass
                finally:
                    try:
                        src.close()
                    except Exception:
                        pass
                    try:
                        dst.close()
                    except Exception:
                        pass

            threading.Thread(target=pipe, args=(client_sock, remote_sock), daemon=True).start()
            threading.Thread(target=pipe, args=(remote_sock, client_sock), daemon=True).start()
        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

# Test first proxy: 31.59.20.176:6754:gpbzberw:ripdlkneqpn0
bridge = LocalAuthProxyBridge('31.59.20.176', 6754, 'gpbzberw', 'ripdlkneqpn0')
local_px = bridge.start()
print('Started local bridge at:', local_px)

co = ChromiumOptions()
co.headless(True)
co.set_browser_path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
co.set_proxy(f'http://{local_px}')

page = ChromiumPage(co)
try:
    print('Checking IP via proxy...')
    page.get('https://api.ipify.org?format=json')
    time.sleep(3)
    print('Page response:', page.html)
finally:
    page.quit()
    bridge.stop()
    print('Done!')
