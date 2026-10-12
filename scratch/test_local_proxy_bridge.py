import sys, os, time, socket, threading, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import undetected_chromedriver as uc
import kick_account_creator as kac

class LocalAuthProxyBridge:
    def __init__(self, target_ip, target_port, user, password):
        self.target_ip = target_ip
        self.target_port = int(target_port)
        self.user = user
        self.password = password
        self.server_socket = None
        self.port = 0
        self.is_running = False
        self._thread = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', 0))
        self.port = self.server_socket.getsockname()[1]
        self.server_socket.listen(50)
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self.port}"

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
            remote_sock.connect((self.target_ip, self.target_port))
            
            # Read first chunk from browser client
            data = client_sock.recv(8192)
            if not data:
                client_sock.close()
                remote_sock.close()
                return

            # Insert Proxy-Authorization header if CONNECT or HTTP request
            lines = data.split(b"\r\n")
            new_lines = [lines[0]] + [auth_header.encode()] + lines[1:]
            modified_data = b"\r\n".join(new_lines)
            
            remote_sock.sendall(modified_data)

            # Bidirectional pipe
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

            t1 = threading.Thread(target=pipe, args=(client_sock, remote_sock), daemon=True)
            t2 = threading.Thread(target=pipe, args=(remote_sock, client_sock), daemon=True)
            t1.start()
            t2.start()
        except Exception as e:
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

ip, port, user, pwd = kac.PROXY_POOL[0].split(":")
bridge = LocalAuthProxyBridge(ip, port, user, pwd)
local_proxy_url = bridge.start()
print("Local Auth Proxy Bridge started at:", local_proxy_url)

opts = uc.ChromeOptions()
opts.add_argument("--headless=new")
opts.add_argument(f"--proxy-server={local_proxy_url}")

driver = uc.Chrome(options=opts, use_subprocess=True)
try:
    driver.get("https://httpbin.org/ip")
    time.sleep(3)
    print("PAGE SOURCE WITH LOCAL PROXY BRIDGE:", driver.page_source)
finally:
    driver.quit()
    bridge.stop()
