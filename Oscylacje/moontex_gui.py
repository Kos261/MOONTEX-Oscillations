import sys
from PyQt5.QtWidgets import QApplication, QMainWindow


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.resize(800, 600)
    win.show()
    sys.exit(app.exec_())
