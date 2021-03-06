#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Bertrand256
# Created on: 2017-03
import functools
import logging
import os
import threading
import traceback
from functools import partial
from typing import Callable, Optional, NewType, Any, Tuple, Dict, List

import app_defs
import app_utils
import thread_utils
import time
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QObject, QLocale, QEventLoop, QTimer, QPoint, QEvent, QPointF, QSize, QModelIndex, QRect, \
    QRectF
from PyQt5.QtGui import QPalette, QPainter, QBrush, QColor, QPen, QIcon, QPixmap, QTextDocument, QCursor, \
    QAbstractTextDocumentLayout, QFontMetrics, QTransform, QKeySequence
from PyQt5.QtWidgets import QMessageBox, QWidget, QFileDialog, QInputDialog, QItemDelegate, QLineEdit, \
    QAbstractItemView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QAction, QMenu, QApplication
import math
import message_dlg
from thread_fun_dlg import ThreadFunDlg, WorkerThread, CtrlObject


class WndUtils:

    def __init__(self, app_config=None):
        self.app_config = app_config
        self.debounce_timers: Dict[str, QTimer] = {}

    def messageDlg(self, message):
        ui = message_dlg.MessageDlg(self, message)
        ui.exec_()

    def set_app_config(self, app_config):
        self.app_config = app_config

    @staticmethod
    def displayMessage(type, message):
        msg = QMessageBox()
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse)
        msg.setIcon(type)

        # because of the bug: https://bugreports.qt.io/browse/QTBUG-48964
        # we'll convert a message to HTML format to avoid bolded font on Mac platform
        if message.find('<html') < 0:
            message = '<html style="font-weight:normal">' + message.replace('\n', '<br>') + '</html>'

        msg.setText(message)
        return msg.exec_()

    @staticmethod
    def errorMsg(message):
        if threading.current_thread() != threading.main_thread():
            return WndUtils.call_in_main_thread(WndUtils.displayMessage, QMessageBox.Critical, message)
        else:
            return WndUtils.displayMessage(QMessageBox.Critical, message)

    @staticmethod
    def warnMsg(message):
        if threading.current_thread() != threading.main_thread():
            return WndUtils.call_in_main_thread(WndUtils.displayMessage, QMessageBox.Warning, message)
        else:
            return WndUtils.displayMessage(QMessageBox.Warning, message)

    @staticmethod
    def infoMsg(message):
        if threading.current_thread() != threading.main_thread():
            return WndUtils.call_in_main_thread(WndUtils.displayMessage, QMessageBox.Information, message)
        else:
            return WndUtils.displayMessage(QMessageBox.Information, message)

    @staticmethod
    def queryDlg(message, buttons=QMessageBox.Ok | QMessageBox.Cancel, default_button=QMessageBox.Ok,
            icon=QMessageBox.Information):

        def dlg(message, buttons, default_button, icon):
            msg = QMessageBox()
            msg.setIcon(icon)
            msg.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse)

            # because of the bug: https://bugreports.qt.io/browse/QTBUG-48964
            # we'll convert a message to HTML format to avoid bolded font on Mac platform
            if message.find('<html') < 0:
                message = '<html style="font-weight:normal">' + message.replace('\n', '<br>') + '</html>'

            msg.setText(message)
            msg.setStandardButtons(buttons)
            msg.setDefaultButton(default_button)
            return msg.exec_()

        if threading.current_thread() != threading.main_thread():
            return WndUtils.call_in_main_thread(dlg, message, buttons, default_button, icon)
        else:
            return dlg(message, buttons, default_button, icon)

    def centerByWindow(self, parent):
        """
        Centers this window by window given by attribute 'center_by_window'
        :param center_by_window: Reference to (parent) window by wich this window will be centered.
        :return: None
        """
        self.move(parent.frameGeometry().topLeft() + parent.rect().center() - self.rect().center())

    @staticmethod
    def run_thread_dialog(worker_fun: Callable[[CtrlObject, Any], Any], worker_fun_args: Tuple[Any,...],
                          close_after_finish=True, buttons=None, title='', text=None, center_by_window=None,
                          show_window_delay_ms: Optional[int] = 0):
        """
        Executes worker_fun function inside a thread. Function provides a dialog for UI feedback (messages 
        and/or progressbar).
        :param worker_fun: user's method/function to be executed inside a thread 
        :param worker_fun_args:  argumets passed to worker_fun
        :param close_after_finish: True, if a dialog is to be closed after finishing worker_fun
        :param buttons: list of dialog button definitions; look at doc od whd_thread_fun.Ui_ThreadFunDialog class
        :return: value returned from worker_fun
        """
        def call(worker_fun, worker_fun_args, close_after_finish, buttons, title, text, center_by_window,
                 show_window_delay_ms):

            ui = ThreadFunDlg(worker_fun, worker_fun_args, close_after_finish,
                              buttons=buttons, title=title, text=text, center_by_window=center_by_window,
                              show_window_delay_ms=show_window_delay_ms)
            ui.wait_for_worker_completion()
            ret = ui.getResult()
            ret_exception = ui.worker_exception
            del ui
            QtWidgets.qApp.processEvents(QEventLoop.ExcludeUserInputEvents)  # wait until dialog hides
            if ret_exception:
                # if there was an exception in the worker function, pass it to the caller
                raise ret_exception
            return ret

        if threading.current_thread() != threading.main_thread():
            # dialog can be created only from the main thread; it the method is called otherwise, synchronize
            # with the main thread first
            ret = thread_wnd_utils.call_in_main_thread(
                call, worker_fun, worker_fun_args, close_after_finish=close_after_finish, buttons=buttons, title=title,
                text=text, center_by_window=center_by_window, show_window_delay_ms=show_window_delay_ms)
        else:
            ret = call(worker_fun, worker_fun_args, close_after_finish, buttons, title, text, center_by_window,
                       show_window_delay_ms)

        return ret

    @staticmethod
    def run_thread(parent, worker_fun, worker_fun_args, on_thread_finish=None,
                   on_thread_exception=None, skip_raise_exception=False):
        """
        Run a function inside a thread.
        :param worker_fun: reference to function to be executed inside a thread
        :param worker_fun_args: arguments passed to a thread function
        :param on_thread_finish: function to be called after thread finishes its execution
        :param skip_raise_exception: Exception raised inside the 'worker_fun' will be passed to the calling thread if:
            - on_thread_exception is a valid function (it's exception handler)
            - skip_raise_exception is False
        :return: reference to a thread object
        """

        def on_thread_finished_int(thread_arg, on_thread_finish_arg, skip_raise_exception_arg, on_thread_exception_arg):
            if thread_arg.worker_exception:
                if on_thread_exception_arg:
                    on_thread_exception_arg(thread_arg.worker_exception)
                else:
                    if not skip_raise_exception_arg:
                        raise thread_arg.worker_exception
            else:
                if on_thread_finish_arg:
                    on_thread_finish_arg()

        if threading.current_thread() != threading.main_thread():
            # starting thread from another thread causes an issue of not passing arguments'
            # values to on_thread_finished_int function, so on_thread_finish is not called
            st = traceback.format_stack()
            logging.error('Running thread from inside another thread. Stack: \n' + ''.join(st))

        thread = WorkerThread(parent=parent, worker_fun=worker_fun, worker_fun_args=worker_fun_args)

        # in Python 3.5 local variables sometimes are removed before calling on_thread_finished_int
        # so we have to bind that variables with the function ref
        bound_on_thread_finished = partial(on_thread_finished_int, thread, on_thread_finish, skip_raise_exception,
                                           on_thread_exception)

        thread.finished.connect(bound_on_thread_finished)
        thread.start()
        logging.debug('Started WorkerThread for: ' + str(worker_fun))
        return thread

    @staticmethod
    def call_in_main_thread(fun_to_call, *args, **kwargs):
        return thread_wnd_utils.call_in_main_thread(fun_to_call, *args, **kwargs)

    def setIcon(self, widget, ico, rotate=0):
        if isinstance(ico, str):
            icon = QIcon()
            if app_defs.APP_IMAGE_DIR:
                path = app_defs.APP_IMAGE_DIR
            else:
                path = 'img'

            path = os.path.join(path, ico)
            if not os.path.isfile(path):
                logging.warning(f'File {path} does not exist or is not a file')

            pixmap = QPixmap(path)
            if rotate:
                transf = QTransform().rotate(rotate)
                pixmap = QPixmap(pixmap.transformed(transf))

            icon.addPixmap(pixmap)
        else:
            icon = self.style().standardIcon(ico)

        widget.setIcon(icon)

    @staticmethod
    def open_file_query(main_wnd, message, directory='', filter='', initial_filter=''):
        """
        Creates an open file dialog for selecting a file or if the user configures not to use graphical dialogs
          (on some linuxes there are problems with graphic libs and app crashes) - normal input dialog for entering
          the full path to the file opens instead.
        :param message:
        :param directory:
        :param filter: example: "All Files (*);;Conf files (*.conf)"
        :param initial_filter: example: "Conf files (*.conf)"
        :return:
        """
        if main_wnd:
            sip_dialog = main_wnd.app_config.dont_use_file_dialogs if main_wnd.app_config else False
        else:
            sip_dialog = False
        file_name = ''

        if sip_dialog:
            file_name, ok = QInputDialog.getText(main_wnd, 'File name query', message)
            if not ok:
                file_name = ''
        else:
            file = QFileDialog.getOpenFileName(main_wnd, caption=message, directory=directory, filter=filter,
                                               initialFilter=initial_filter)
            if len(file) >= 2:
                file_name = file[0]
        return file_name

    @staticmethod
    def save_file_query(main_wnd, message, directory='', filter='', initial_filter=''):
        """
        Creates an open file dialog for selecting a file or if the user configures not to use graphical dialogs
          (on some linuxes there are problems with graphic libs and app crashes) - normal input dialog for entering
          the full path to the file opens instead.
        :param message:
        :param directory:
        :param filter: example: "All Files (*);;Conf files (*.conf)"
        :param initial_filter: example: "Conf files (*.conf)"
        :return:
        """
        sip_dialog = main_wnd.app_config.dont_use_file_dialogs if main_wnd.app_config else False
        file_name = ''

        if sip_dialog:
            file_name, ok = QInputDialog.getText(main_wnd, 'File name query', message)
            if not ok:
                file_name = ''
        else:
            file = QFileDialog.getSaveFileName(main_wnd, caption=message, directory=directory, filter=filter,
                                               initialFilter=initial_filter)
            if len(file) >= 2:
                file_name = file[0]
        return file_name

    @staticmethod
    def open_config_file_query(dir, main_wnd):
        file_name = WndUtils.open_file_query(main_wnd, message='Enter the path to the configuration file',
                                             directory=dir,
                                             filter="All Files (*);;Configuration files (*.ini)",
                                             initial_filter="Configuration files (*.ini)")
        return file_name

    @staticmethod
    def save_config_file_query(dir, main_wnd):
        file_name = WndUtils.save_file_query(main_wnd, message='Enter the configuration file name/path to save',
                                             directory=dir,
                                             filter="All Files (*);;Configuration files (*.ini)",
                                             initial_filter="Configuration files (*.ini)")
        return file_name

    def write_csv_row(self, file_ptr, elems):
        """ Writes list of values as a CSV row, converting values as cencessary (if value contains a character used
        as a CSV ddelimiter).  """

        delim = self.app_config.csv_delimiter if self.app_config else ';'
        delim_replacement = '_' if delim != '_' else '-'
        # elems = [str(elem if elem is not None else '').replace(delim, delim_replacement) for elem in elems]
        csv_row = []
        for elem in elems:
            if elem is None:
                elem = ''
            elif not isinstance(elem, str):
                elem = QLocale.toString(app_utils.get_default_locale(), elem if elem is not None else '')
            csv_row.append(elem.replace(delim, delim_replacement))
        file_ptr.write(delim.join(csv_row) + '\n')

    def debounce_call(self, name: str, function_to_call: Callable, delay_ms: int):
        def tm_timeout(timer: QTimer, function_to_call: Callable):
            timer.stop()
            function_to_call()

        if name not in self.debounce_timers:
            tm = QTimer(self)
            tm.timeout.connect(functools.partial(tm_timeout, tm, function_to_call))
            self.debounce_timers[name] = tm
        else:
            tm = self.debounce_timers[name]
        tm.start(delay_ms)


class DeadlockException(Exception):
    pass


class CloseDialogException(Exception):
    """ Raised when all processes executed inside a dialog must be aborted, because the dialog is being closing. """
    pass


class ThreadWndUtils(QObject):
    """
    Helps in calling functions interacting with GUI, executed from threads other than the main app's thread.
    """

    # signal for calling specified function in the main thread
    fun_call_signal = QtCore.pyqtSignal(object, object, object, object)

    def __init__(self):
        QObject.__init__(self)
        self.fun_call_signal.connect(self.fun_call_signalled)
        self.fun_call_ret_value = None
        self.fun_call_exception = None

    def fun_call_signalled(self, fun_to_call, args, kwargs, mutex):
        """
        Function-event executed in the main thread as a result of emiting signal fun_call_signal from BG threads.
        :param fun_to_call: ref to a function which is to be called
        :param args: args passed to the function fun_to_call
        :param mutex: mutex object (QMutex) which is used in the calling thread to wait until
            function 'fun_to_call' terminates; calling mutex.unlock() will signal that
        :return: return value from fun_to_call
        """
        try:
            self.fun_call_ret_value = fun_to_call(*args, **kwargs)
        except Exception as e:
            self.fun_call_exception = e
        finally:
            mutex.unlock()

    def call_in_main_thread(self, fun_to_call, *args, **kwargs):
        """
        This method is called from BG threads. Its purpose is to run 'fun_to_call' from main thread (used for dialogs)
        and return values ruturned from it.
        :param fun_to_call: ref to a function which is to be called
        :param args: args passed to the function fun_to_call
        :return: return value from fun_to_call
        """
        exception_to_rethrow = None
        ret = None
        try:
            if threading.current_thread() != threading.main_thread():

                # check whether the main thread waits for the lock acquired by the current thread
                # if so, raise deadlock detected exception
                dl_check = thread_utils.EnhRLock.detect_deadlock(threading.main_thread())
                if dl_check is not None:

                    # find a caller of the current method (skip callers from the current module)
                    caller_file = ''
                    caller_line = ''
                    for si in reversed(traceback.extract_stack()):
                        if si.name != 'call_in_main_thread':
                            caller_file = si.filename
                            caller_line = si.lineno
                            break
                    raise DeadlockException('Deadlock detected. Trying to synchronize with the main thread (c), which '
                                            'is waiting (b) for a lock acquired by this thread (a).\n'
                                            '  CURRENT_THREAD ->(a)[LOCK]--->(c)[MAIN_THREAD]\n'
                                            '  MAIN_THREAD ---->(b)[LOCK]\n'
                                            '    a. file "%s", line %s\n'
                                            '    b. file "%s", line %s\n'
                                            '    c. file "%s", line %s' %
                                            (dl_check[2], dl_check[3], dl_check[0], dl_check[1], caller_file,
                                             caller_line))

                mutex = QtCore.QMutex()
                mutex.lock()
                locked = False
                try:
                    self.fun_call_exception = None
                    self.fun_call_ret_value = None

                    # emit signal to call the function fun in the main thread
                    self.fun_call_signal.emit(fun_to_call, args, kwargs, mutex)

                    # wait for the function to finish; lock will be successful only when the first lock
                    # made a few lines above is released in the fun_call_signalled method
                    tm_begin = time.time()
                    locked = mutex.tryLock(3600000)  # wait 1h max
                    tm_diff = time.time() - tm_begin
                    if not locked:
                        logging.exception("Problem communicating with the main thread - couldn't lock mutex. Lock "
                                          "wait time: %ss." % str(tm_diff))
                        raise Exception("Problem communicating with the main thread - couldn't lock mutex. Lock "
                                        "wait time: %ss." % str(tm_diff))
                    ret = self.fun_call_ret_value
                finally:
                    if locked:
                        mutex.unlock()
                    del mutex
                if self.fun_call_exception:
                    # if there was an exception in the fun, pass it to the calling code
                    exception_to_rethrow = self.fun_call_exception
            else:
                return fun_to_call(*args, **kwargs)
        except DeadlockException:
            raise
        except Exception as e:
            logging.exception('ThreadWndUtils.call_in_main_thread error: %s' % str(e))
            raise

        if exception_to_rethrow:
            raise exception_to_rethrow
        return ret


thread_wnd_utils = ThreadWndUtils()


class SpinnerWidget(QWidget):
    def __init__(self, parent: QWidget, spinner_size, message: str = '', font_size=None):

        QWidget.__init__(self, parent)
        self.spinner_size = spinner_size
        self.message = message
        self.font_size = font_size
        self.timer_id = None

    def sizeHint(self):
        return self.parent().size()

    def paintEvent(self, event):
        par = self.parent()
        size = min(self.spinner_size, par.width(), par.height())
        dot_count = 5
        dot_size = int(size / dot_count) * 1.5

        r = par.rect()
        spinner_rect = QRect(r.width()/2 - size/2, r.height()/2 - size/2, size, size)

        painter = QPainter()
        painter.begin(self)
        painter.setPen(QPen(Qt.NoPen))

        for i in range(dot_count):
            if self.counter % dot_count == i:
                painter.setBrush(QBrush(QColor(0, 0, 0)))
                d_size = dot_size * 1.1
            else:
                painter.setBrush(QBrush(QColor(200, 200, 200)))
                d_size = dot_size

            r = size / 2 - dot_size / 2
            x = r * math.cos(2 * math.pi * i / dot_count)
            y = r * math.sin(2 * math.pi * i / dot_count)
            x_center = spinner_rect.left() + spinner_rect.width() / 2 - dot_size / 2
            y_center = spinner_rect.top() + spinner_rect.height() / 2 - dot_size / 2
            painter.drawEllipse(x_center + x, y_center + y, d_size, d_size)

        if self.message:
            painter.setPen(QPen(Qt.black))
            if self.font_size:
                f = painter.font()
                f.setPointSize(self.font_size)
                painter.setFont(f)
            spinner_rect.setTop(spinner_rect.bottom() + 3)
            spinner_rect.setHeight(painter.fontMetrics().height() * 1.5)
            r = painter.boundingRect(spinner_rect, Qt.AlignHCenter | Qt.AlignTop, self.message)
            painter.drawText(r.bottomLeft(), self.message)

        painter.end()

    def showEvent(self, event):
        self.timer_id = self.startTimer(200)
        self.counter = 0

    def timerEvent(self, event):
        target_geom = QRect(0, 0, self.parent().width(), self.parent().height())
        if self.geometry() != target_geom:
            self.setGeometry(target_geom)
        self.counter += 1
        self.update()

    def hideEvent(self, event):
        if self.timer_id:
            self.killTimer(self.timer_id)
            self.timer_id = None


class ReadOnlyTableCellDelegate(QItemDelegate):
    """
    Used for enabling read-only and text selectable cells in QTableView widgets.
    """
    def __init__(self, parent):
        QItemDelegate.__init__(self, parent)

    def createEditor(self, parent, option, index):
        e = QLineEdit(parent)
        e.setReadOnly(True)
        return e


class LineEditTableCellDelegate(QItemDelegate):
    """
    Used for enabling read-only and text selectable cells in QTableView widgets.
    """
    def __init__(self, parent, img_dir: str):
        QItemDelegate.__init__(self, parent, )
        self.img_dir = img_dir
        self.save_action = QAction('Save', self)
        self.set_icon(self.save_action, "save@16px.png")
        self.save_action.triggered.connect(self.on_save_data)
        self.undo_action = QAction('Revert', self)
        self.set_icon(self.undo_action, "undo@16px.png")
        self.undo_action.triggered.connect(self.on_revert_data)
        self.editor = None
        self.old_data = ''
        self.cur_item_index = None
        self.data_history: Dict[QModelIndex, List[str]] = {}

    def set_icon(self, widget, ico_name):
        icon = QIcon()
        icon.addPixmap(QPixmap(os.path.join(self.img_dir, ico_name)))
        widget.setIcon(icon)

    def on_save_data(self):
        if self.editor:
            self.commitData.emit(self.editor)
            self.closeEditor.emit(self.editor)
            self.editor = None

    def on_revert_data(self):
        if self.editor and self.cur_item_index:
            sd = self.data_history.get(self.cur_item_index)
            if sd:
                sd.pop()
                if sd:
                    t = sd[-1]
                else:
                    t = ''
                self.editor.setText(t)

    def createEditor(self, parent, option, index):
        self.cur_item_index = index
        self.editor = QLineEdit(parent)
        self.editor.addAction(self.save_action, QLineEdit.TrailingPosition)
        if self.data_history.get(index):
            self.editor.addAction(self.undo_action, QLineEdit.TrailingPosition)
        return self.editor

    def setEditorData(self, editor, index):
        self.old_data = index.data()
        editor.setText(self.old_data)
        sd = self.data_history.get(index)
        if not sd:
            sd = []
            self.data_history[index] = sd
        if self.old_data:
            if not sd or sd[-1] != self.old_data:
                sd.append(self.old_data)

    def setModelData(self, editor, model, index):
        new_data = editor.text()
        if new_data != self.old_data:
            model.setData(index, new_data)


HTML_LINK_HORZ_MARGIN = 3


class HyperlinkItemDelegate(QStyledItemDelegate):
    linkActivated = QtCore.pyqtSignal(str)

    def __init__(self, parentView: QTableView):
        QStyledItemDelegate.__init__(self, parentView)

        parentView.setMouseTracking(True)
        self.doc_hovered_item = QTextDocument(self)
        self.doc_hovered_item.setDocumentMargin(0)
        self.doc_not_hovered = QTextDocument(self)
        self.doc_not_hovered.setDocumentMargin(0)
        self.last_hovered_pos = QPoint(0, 0)
        self.ctx_mnu = QMenu()
        self.last_link = None
        self.last_text = None
        self.action_copy_link = self.ctx_mnu.addAction("Copy Link Location")
        self.action_copy_link.triggered.connect(self.on_action_copy_link_triggered)
        self.action_copy_text = self.ctx_mnu.addAction("Copy text")
        self.action_copy_text.triggered.connect(self.on_action_copy_text_triggered)

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):

        self.initStyleOption(option, index)
        mouse_over = option.state & QStyle.State_MouseOver
        painter.save()

        color = ''
        if option.state & QStyle.State_Selected:
            if option.state & QStyle.State_HasFocus:
                painter.fillRect(option.rect, QBrush(option.palette.color(QPalette.Active, option.palette.Highlight)))
                color = "color: white"
            else:
                painter.fillRect(option.rect, QBrush(option.palette.color(QPalette.Inactive, option.palette.Highlight)))
        else:
            painter.setBrush(QBrush(Qt.white))

        if mouse_over:
            doc = self.doc_hovered_item
            self.last_hovered_pos = option.rect.topLeft()
            doc.setDefaultStyleSheet(f"a {{{color}}}")
        else:
            doc = self.doc_not_hovered
            self.parent().unsetCursor()
            doc.setDefaultStyleSheet(f"a {{text-decoration: none;{color}}}")

        doc.setDefaultFont(option.font)
        doc.setHtml(option.text)

        painter.translate(option.rect.topLeft() + QPoint(HTML_LINK_HORZ_MARGIN, 0))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette = option.palette
        clip = QRect(0, 0, option.rect.width() - HTML_LINK_HORZ_MARGIN * 2, option.rect.height())
        painter.setClipRect(clip)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() not in [QEvent.MouseMove, QEvent.MouseButtonRelease] \
            or not (option.state & QStyle.State_Enabled):
            return False

        pos = QPointF(event.pos() - option.rect.topLeft())
        anchor = self.doc_hovered_item.documentLayout().anchorAt(pos)
        if not anchor:
            self.parent().unsetCursor()
        else:
            self.parent().setCursor(Qt.PointingHandCursor)
            if event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    self.linkActivated.emit(anchor)
                    return True
                elif event.button() == Qt.RightButton:
                    self.last_text = self.doc_hovered_item.toRawText()
                    self.last_link = anchor

                    p = QPoint(event.pos().x(), event.pos().y() + min(32, self.ctx_mnu.height()))
                    p = option.widget.mapToGlobal(p)
                    self.ctx_mnu.exec(p)
        return False

    def on_action_copy_link_triggered(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_link)

    def on_action_copy_text_triggered(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_text)