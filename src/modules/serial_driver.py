
from modules.event_logger import EventLogger
from pathlib import Path
import yaml
import threading
import queue

import serial

class SerialDriver:
    """
    Synchronous-write serial driver with a background RX listener.

    Typical usage:

    """

    def __init__(self, 
                port, 
                baudrate,
                bytesize,
                parity,
                stopbits,
                timeout,
                write_timeout,
                xonxoff,
                rtscts,
                dsrdtr, 
                line_ending,
                rx_queue_size):
        """
        configurable variables
            port:               Serial port ("COM3", "/dev/ttyUSB0"). 
            baudrate:           Baud rate.
            bytesize/parity/stopbits/timeout/write_timeout/xonxoff/rtscts/dsrdtr:
                                Passed through to pyserial.
            line_ending:        Line terminator for TX framing and RX splitting.
            rx_queue_size:      Max buffered complete RX lines.
        """
        #state vars
        self.status = "Off"

        #create logger
        self.log = EventLogger().logger

        #load config
        self.port = port
        self.baudrate = baudrate

        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.dsrdtr = dsrdtr
        self.line_ending = line_ending

        # create Queue for messages received.
        self.rx_queue: queue.Queue[str] = queue.Queue(maxsize=rx_queue_size)


    #open the serial port
    def _open_serial_port(self):

        #code for opening serial port
        self.log.info(f"Serial port opened on port {self.port} at {self.baudrate} Baud")

    #close serial port
    def _close_serial_port(self):

        #code for closing serial port
        self.log.info(f"Serial port closed on port {self.port} at {self.baudrate} Baud")

    def open(self):
        #logic for retrying and such


        self.status = "Ready"
        self._open_serial_port()

    def close(self):
        self.status = "Off"
        self._close_serial_port()

    def send(self, message):
        #code for sending message here

        self.log.info(f"Message sent to Monitoring system on {self.port}: {message}")

    def add_rx_message(self, message):
        #puts a complete received message on the RX queue, for the RX listener and for testing without hardware
        #returns True if queued, False if the queue is full or the message is not a string
        if not isinstance(message, str):
            self.log.error(f"RX message must be a string, got {type(message).__name__}")
            return False
        try:
            self.rx_queue.put_nowait(message)
        except queue.Full:
            #never block the caller, a full queue means messages arrive faster than they are handled
            self.log.warning(f"RX queue full on {self.port}, dropped message: {message}")
            return False
        return True

    def read(self):
        #returns the oldest received message, or None if there are none
        try:
            return self.rx_queue.get_nowait()
        except queue.Empty:
            return None

    def read_all(self):
        #returns every received message in arrival order, empty list if there are none
        messages = []
        while True:
            message = self.read()
            if message is None:
                return messages
            messages.append(message)

    def get_status(self):
        return self.status

