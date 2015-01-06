from PyQt4.QtCore import QThread, QObject, QCoreApplication, QTimer, pyqtSlot, pyqtSignal
import sys
from time import sleep


class Worker(QObject):
    thread = None
    _continue = True

    def __init__(self):
        super(Worker, self).__init__()

    @pyqtSlot()
    def quit(self):
        self._continue = False

    @pyqtSlot()
    def run(self):
        while (self._continue):
            QCoreApplication.processEvents()
            #print 'TEST %d|%d' % (current_thread().ident, self._continue)
            sleep(1)
        self.thread.exit(0)


class Engine(QCoreApplication):
    _start = pyqtSignal()
    _stop = pyqtSignal()

    def __init__(self, processors=5):
        super(Engine, self).__init__(sys.argv)
        self.dao = self.create_thread()
        self.local_watcher = self.create_thread()
        self.remote_watcher = self.create_thread()
        self.queue_manager = self.create_thread()
        self.queue_processors = list()
        for i in range(0, processors):
            self.queue_processors.append(self.create_thread())
        self.gui = self.create_thread()
        self.threads = list()
        self.threads.append(self.dao)
        self.threads.append(self.local_watcher)
        self.threads.append(self.remote_watcher)
        self.threads.append(self.queue_manager)
        for processor in self.queue_processors:
            self.threads.append(processor)
        self.threads.append(self.gui)

        self.start()
        QTimer.singleShot(1000, self.stop)

    def create_thread(self, worker=None):
        if worker is None:
            worker = Worker()
        thread = QThread()
        worker.thread = thread
        thread.worker = worker
        worker.moveToThread(thread)
        self._start.connect(worker.run)
        self._stop.connect(worker.quit)
        return thread

    def start(self):
        print "START ENGINE"
        for thread in self.threads:
            thread.start()
        self._start.emit()

    def stop(self):
        print "STOP ENGINE"
        self._stop.emit()
        for thread in self.threads:
            if not thread.wait(3000):
                print "Thread is not responding - terminate it"
                thread.terminate()
        print "ENGINE STOPPED"
        QCoreApplication.exit()

if __name__ == "__main__":
    engine = Engine()
    print "EXEC ENGINE"
    engine.exec_()
