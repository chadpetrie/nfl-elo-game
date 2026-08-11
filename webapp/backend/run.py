""" Launches the app and opens the browser as soon as the server is actually ready. """

import socket
import threading
import time
import webbrowser

import uvicorn

HOST, PORT = "127.0.0.1", 8000


def wait_for_server_then_open_browser():
    while True:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    webbrowser.open("http://%s:%d" % (HOST, PORT))


if __name__ == "__main__":
    threading.Thread(target=wait_for_server_then_open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT)
