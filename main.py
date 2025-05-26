# main.py
import sys
import asyncio
import traceback
from PySide6.QtWidgets import QApplication, QMessageBox # PyQt6 -> PySide6
from app.window import MainWindow 
import quamash

# Глобальный флаг для предотвращения рекурсии в обработчике ошибок
error_handler_active = False

def global_exception_handler(exctype, value, tb):
    global error_handler_active
    if error_handler_active:
        # print("Рекурсивная ошибка в global_exception_handler.") # Отладочный вывод
        # sys.__excepthook__(exctype, value, tb) # Можно вернуть стандартный обработчик
        return # Просто выйти, чтобы избежать зависания
    error_handler_active = True

    error_message = ''.join(traceback.format_exception(exctype, value, tb))
    print(f"НЕОБРАБОТАННОЕ ИСКЛЮЧЕНИЕ:\n{error_message}")

    try:
        app_instance = QApplication.instance()
        if app_instance:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("Критическая ошибка")
            msg_box.setText("В приложении произошла критическая ошибка. Рекомендуется перезапуск.")
            msg_box.setInformativeText("Подробности ошибки записаны в консоль и файл error_restart_needed.flag.")
            msg_box.setDetailedText(error_message)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
        else:
            print("QApplication не инициализировано, QMessageBox не будет показано.")
    except Exception as e_msgbox:
        print(f"Ошибка при попытке показать QMessageBox: {e_msgbox}")

    try:
        with open("error_restart_needed.flag", "w", encoding='utf-8') as f:
            f.write(error_message)
        print("Файл error_restart_needed.flag создан.")
    except Exception as e_flag:
        print(f"Не удалось создать файл-флаг: {e_flag}")
    
    print("Критическая ошибка обработана. Пожалуйста, перезапустите приложение.")
    error_handler_active = False # Сброс флага в конце
    # sys.exit(1) # Раскомментируйте, если нужно принудительное завершение после ошибки

if __name__ == '__main__':
    # Установка глобального обработчика исключений для всего приложения.
    # Этот хук будет вызван для любых необработанных исключений, возникших в любом потоке.
    sys.excepthook = global_exception_handler

    try:
        # Создание экземпляра QApplication - это основа любого PyQt приложения.
        # sys.argv позволяет передавать аргументы командной строки в приложение.
        app = QApplication(sys.argv)
        
        # Инициализация quamash.QEventLoop для интеграции asyncio с циклом событий PyQt.
        # Это позволяет использовать `async/await` с PyQt.
        loop = quamash.QEventLoop(app)
        asyncio.set_event_loop(loop) # Установка созданного цикла событий как текущего для asyncio.
        
        # Создание главного окна приложения. Логика окна описана в app/window.py.
        window = MainWindow()
        window.show() # Отображение главного окна.

        # Запуск основного цикла событий приложения.
        # `loop` (Quamash QEventLoop) здесь используется как контекстный менеджер,
        # чтобы обеспечить корректное управление его жизненным циклом.
        # `app.exec()` запускает цикл событий PyQt, который теперь интегрирован с asyncio.
        # `sys.exit()` обеспечивает корректное завершение приложения с кодом возврата.
        with loop:
            sys.exit(app.exec())
            
    except Exception as e:
        # Этот блок try...except предназначен для перехвата исключений,
        # которые могут возникнуть на самом раннем этапе инициализации приложения,
        # еще до того, как `sys.excepthook` или основной цикл событий начнут полноценно работать.
        # Например, если ошибка происходит при создании QApplication или QEventLoop.
        print("Перехвачено критическое исключение на этапе инициализации приложения:")
        # Вызов глобального обработчика для стандартизированной обработки ошибки.
        global_exception_handler(type(e), e, e.__traceback__)
        sys.exit(1) # Принудительное завершение приложения с кодом ошибки.

    finally:
        # Блок finally гарантирует выполнение этого кода независимо от того,
        # было ли исключение или приложение завершилось штатно.
        if 'loop' in locals() and loop.is_running(): # Проверка, был ли loop создан и все еще работает.
            loop.stop() # Остановка цикла событий, если он активен.
        print("Завершение работы приложения.")
