import socket

FB_PATH = "/dev/fb0"
PORT = 9999
BUFFER_SIZE = 480 * 320 * 2


def run_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(1)
    print(f"[+] Server attivo in modalità persistente sulla porta {PORT}...")

    try:
        with open(FB_PATH, "wb") as fb:
            while True:
                conn, addr = server.accept()
                print(f"[>] Laptop connesso: {addr}")

                # Legge lo stream continuo finché il client non si disconnette
                while True:
                    data = bytearray()
                    while len(data) < BUFFER_SIZE:
                        packet = conn.recv(BUFFER_SIZE - len(data))
                        if not packet:
                            break
                        data.extend(packet)

                    if len(data) == BUFFER_SIZE:
                        fb.seek(0)
                        fb.write(data)
                        fb.flush()
                    elif len(data) == 0:
                        # Il client si è disconnesso pulito
                        break
                print("[<] Laptop disconnesso.")
                conn.close()
    except Exception as e:
        print(f"[!] Errore: {e}")
    finally:
        server.close()


if __name__ == "__main__":
    run_server()
