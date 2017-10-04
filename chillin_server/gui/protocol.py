# -*- coding: utf-8 -*-

# python imports
from threading import Thread, Lock, Event
import sys

if sys.version_info > (3,):
    from queue import Queue
else:
    from Queue import Queue

# project imports
from ..config import Config
from .network import Network
from .parser import Parser
from .messages import Auth


class Protocol:

    def __init__(self, authenticate_func, game_info):
        self._auth_func = authenticate_func
        self._game_info = game_info
        self._network = Network()
        self._parser = Parser()
        self._clients = set()
        self._lock = Lock()
        self._running = Event()
        self.send_queue = Queue()


    def _add_client(self, sock):
        self._send_msg(sock, self._game_info)
        self._lock.acquire()
        self._clients.add(sock)
        self._lock.release()


    def _remove_clients(self, socks):
        for sock in socks:
            self._network.close(sock)
        self._lock.acquire()
        self._clients.difference_update(socks)
        self._lock.release()


    def _accept(self):

        def auth(sock):
            token = self._network.recv_data(sock)
            if token and self._auth_func(token):
                self._send_msg(sock, Auth(authenticated=True))
                self._add_client(sock)
            else:
                self._send_msg(sock, Auth(authenticated=False))
                self._network.close(sock)

        while self._running.is_set():
            sock = self._network.accept()
            if sock and self._running.is_set():
                if Config.config['general']['offline_mode']:
                    self._add_client(sock)
                else:
                    Thread(target=auth, args=(sock,)).start()


    def _send_msg(self, sock, msg):
        data = self._parser.encode(msg)
        self._network.send_data(sock, data)


    def _broadcast_msg(self, msg):
        data = self._parser.encode(msg)
        disconnected_clients = []
        for sock in self._clients:
            if not self._network.send_data(sock, data):
                disconnected_clients.append(sock)

        self._remove_clients(disconnected_clients)


    def _send_thread(self):
        while self._running.is_set():
            msg = self.send_queue.get()
            if msg:
                self._broadcast_msg(msg)


    def start(self):
        self._network.start()
        self._running.set()
        t = Thread(target=self._accept)
        t.setDaemon(True)
        t.start()
        t = Thread(target=self._send_thread)
        t.setDaemon(True)
        t.start()


    def stop(self):
        for sock in self._clients:
            self._network.close(sock)
        self._running.clear()
        self.send_queue.put(None)
        self._network.stop()