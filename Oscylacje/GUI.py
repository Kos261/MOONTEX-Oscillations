import sys
from PyQt5.QtWidgets import (
    QApplication, QPushButton, QVBoxLayout, QWidget,
    QTextEdit, QDoubleSpinBox, QLabel,
    QHBoxLayout, QGridLayout
)
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread

from Oscillator_CLI import *
from Oscylacje import Oscillator_GUI


class StdoutRedirector(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        if text:
            self.text_written.emit(str(text))

    def flush(self):
        pass


class MotorThread(QThread):
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.func(*self.args, **self.kwargs)
        except Exception as e:
            print(e)


class MoontexGUI(QWidget):
    def __init__(self, tic):
        super().__init__()
        self.tic = tic
        self.Layout = QVBoxLayout(self)
        self.speed = 0.0
        self.cycles = 0.0
        self.x1 = 0.0
        self.x2 = 0.0
        self.worker = None
        self.createButtons()
        self.setFixedSize(500, 600)

    def createButtons(self):
        button0 = QPushButton("Manual")
        button0.setFixedSize(150, 150)
        button0.clicked.connect(self._gui_manual)

        button1 = QPushButton("Oscillations")
        button1.setFixedSize(150, 150)
        button1.clicked.connect(self._gui_oscillations)

        button2 = QPushButton("Move")
        button2.setFixedSize(150, 150)
        button2.clicked.connect(self._gui_keep_moving)

        button3 = QPushButton("STOP")
        button3.setFixedSize(150, 150)
        button3.clicked.connect(self._emergency_stop)
        button3.setStyleSheet("background-color: red; color: white; font-weight: bold;")

        self.console = QTextEdit()
        font = self.console.currentFont()
        font.setPointSize(13)
        self.console.setFont(font)
        self.console.setReadOnly(True)
        self.console.append("Moontex")

        self.stdout_redirector = StdoutRedirector()
        self.stdout_redirector.text_written.connect(self.console_append)
        sys.stdout = self.stdout_redirector

        self.speedLabel = QLabel("Speed: 0", self)
        self.speedbox = QDoubleSpinBox()
        self.speedbox.setFixedSize(150, 40)
        self.speedbox.setMinimum(0)
        self.speedbox.setMaximum(MAX_SPEED)
        self.speedbox.setSingleStep(100)
        self.speedbox.valueChanged.connect(self.get_speed)

        self.cyclesLabel = QLabel("Cycles: 0", self)
        self.cyclesbox = QDoubleSpinBox()
        self.cyclesbox.setFixedSize(150, 40)
        self.cyclesbox.setMinimum(0)
        self.cyclesbox.setMaximum(10_000)
        self.cyclesbox.valueChanged.connect(self.get_cycles)

        self.x1Label = QLabel("X1:", self)
        self.target1box = QDoubleSpinBox()
        self.target1box.setFixedSize(150, 40)
        self.target1box.setMinimum(0)
        self.target1box.setMaximum(10_000)
        self.target1box.setSingleStep(100)
        self.target1box.valueChanged.connect(self.get_x1)

        self.x2Label = QLabel("X2:", self)
        self.target2box = QDoubleSpinBox()
        self.target2box.setFixedSize(150, 40)
        self.target2box.setMinimum(-10_000)
        self.target2box.setMaximum(0)
        self.target2box.setSingleStep(100)
        self.target2box.valueChanged.connect(self.get_x2)

        spin_layout = QGridLayout()
        spin_layout.addWidget(self.speedLabel, 0, 0)
        spin_layout.addWidget(self.speedbox, 0, 1)
        spin_layout.addWidget(self.cyclesLabel, 0, 2)
        spin_layout.addWidget(self.cyclesbox, 0, 3)
        spin_layout.addWidget(self.x1Label, 1, 0)
        spin_layout.addWidget(self.target1box, 1, 1)
        spin_layout.addWidget(self.x2Label, 1, 2)
        spin_layout.addWidget(self.target2box, 1, 3)

        buttons_layout = QGridLayout()
        buttons_layout.addWidget(button0, 0, 0)
        buttons_layout.addWidget(button1, 0, 1)
        buttons_layout.addWidget(button2, 1, 0)
        buttons_layout.addWidget(button3, 1, 1)
        buttons_layout.setAlignment(Qt.AlignCenter)

        self.Layout.addLayout(spin_layout)
        self.Layout.addWidget(self.console)
        self.Layout.addLayout(buttons_layout)
        self.Layout.setStretch(1, 1)

    def console_append(self, text):
        self.console.moveCursor(self.console.textCursor().End)
        self.console.insertPlainText(text)
        self.console.moveCursor(self.console.textCursor().End)

    def get_speed(self):
        self.speed = self.speedbox.value()
        self.speedLabel.setText("Speed: " + str(self.speed))

    def get_cycles(self):
        self.cycles = self.cyclesbox.value()
        self.cyclesLabel.setText("Cycles: " + str(self.cycles))

    def get_x1(self):
        self.x1 = self.target1box.value()

    def get_x2(self):
        self.x2 = self.target2box.value()

    def _start_worker(self, func, *args):
        if self.worker is not None and self.worker.isRunning():
            print("Ruch już trwa – zatrzymaj go przed uruchomieniem nowego.")
            return
        self.worker = MotorThread(func, *args)
        self.worker.start()

    def _gui_oscillations(self):
        self._start_worker(Oscylacja_GUI.oscillations, self.tic, self.x1, self.x2, self.speed, self.cycles)

    def _gui_keep_moving(self):
        self._start_worker(Oscylacja_GUI.keep_moving, self.tic, self.speed, self.cycles)

    def _gui_manual(self):
        self._start_worker(Oscylacja_GUI.manual, self.tic)

    def _emergency_stop(self):
        try:
            Oscylacja_GUI._emergency_stop(self.tic)
        except Exception as e:
            print(e)
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()

    def closeEvent(self, event):
        self._emergency_stop()
        event.accept()


if __name__ == '__main__':
    tic = init_and_configure()

    try:
        app = QApplication(sys.argv)
        win = MoontexGUI(tic)
        win.show()
        app.exec_()
    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika.")
    finally:
        try:
            tic.enter_safe_start()
            tic.deenergize()
        except Exception:
            pass
        print("Silnik odłączony, safe start aktywny.")
