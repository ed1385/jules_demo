# app/logic/gpio_controller.py
# Модуль для управления GPIO (General Purpose Input/Output) пинами.
# Включает обработку нажатия физической кнопки для выполнения системных действий,
# таких как закрытие браузера Chromium, проигрывание звука и системные уведомления.

# ВАЖНО: Для корректной работы функции закрытия Chromium и сопутствующих действий,
# в системе должны быть установлены следующие утилиты:
# - 'mpg123': для проигрывания MP3 файлов (например, звукового сигнала).
# - 'notify-send': для отображения системных уведомлений.
# Установка в Debian/Raspbian/Ubuntu:
#   sudo apt-get update
#   sudo apt-get install mpg123 notify-osd
#   (notify-osd обычно предоставляет команду notify-send)
# Убедитесь также, что файл /home/pi/Music/Gong.mp3 существует, или измените путь.

import asyncio
# import os # Закомментировано/удалено, т.к. os.system был заменен на asyncio.create_subprocess_shell
from PyQt5.QtCore import QObject, pyqtSignal # PySide6 -> PyQt5, Signal -> pyqtSignal
from gpiozero import Button # Класс для работы с физическими кнопками

class GPIOController(QObject):
    """
    Класс GPIOController управляет взаимодействием с GPIO Raspberry Pi.
    В текущей конфигурации он настроен на обработку нажатия кнопки, подключенной к GPIO 17,
    для запуска последовательности действий по "закрытию браузера".
    """
    # Сигнал, эмитируемый после завершения (успешного или неуспешного) действия закрытия браузера.
    # Передает строку с сообщением о результате.
    shutdown_action_finished = pyqtSignal(str) # Signal -> pyqtSignal

    def __init__(self, parent=None):
        """
        Инициализация контроллера GPIO.
        Настраивает кнопку на GPIO 17.
        Args:
            parent (QObject, optional): Родительский объект PyQt.
        """
        super().__init__(parent)
        
        self.shutdown_button = None # Атрибут для объекта кнопки, инициализируется как None
        try:
            # Инициализация кнопки на GPIO 17.
            # pull_up=True: Используется внутренний подтягивающий резистор к 3.3V.
            # Кнопка должна быть подключена между GPIO 17 и GND.
            # При нажатии кнопки пин замыкается на GND.
            self.shutdown_button = Button(17, pull_up=True) 
            # Связывание события нажатия кнопки с методом-обработчиком.
            self.shutdown_button.when_pressed = self.on_shutdown_button_pressed
            print("GPIOController: Кнопка Shutdown (GPIO17) успешно инициализирована.")
        except Exception as e:
            # Обработка возможных исключений при инициализации gpiozero:
            # - Запуск на системе без поддержки GPIO (не Raspberry Pi).
            # - Отсутствие необходимых прав доступа к GPIO.
            # - Библиотека gpiozero не установлена.
            print(f"GPIOController: КРИТИЧЕСКАЯ ОШИБКА инициализации кнопки Shutdown (GPIO17): {e}. "
                  "Функция физической кнопки будет недоступна.")
            # self.shutdown_button остается None, что будет учтено в on_shutdown_button_pressed.
            # Эмитируем сигнал, чтобы пользователь был в курсе проблемы через GUI.
            self.shutdown_action_finished.emit(f"Ошибка кнопки GPIO17: {e}")

        # ... (здесь может быть инициализация других GPIO компонентов в будущем) ...
        print("GPIOController: Инициализация завершена.")

    def on_shutdown_button_pressed(self):
        """
        Синхронный колбэк, вызываемый библиотекой gpiozero при нажатии физической кнопки.
        Запускает асинхронную задачу для выполнения основных действий.
        """
        if self.shutdown_button: # Проверка, что кнопка была успешно инициализирована
            print("GPIOController: Кнопка Shutdown (GPIO17) нажата.")
            # Запускаем асинхронную задачу для выполнения действий, чтобы не блокировать колбэк gpiozero
            asyncio.create_task(self._handle_shutdown_action())
        else:
            message = "GPIOController: Кнопка Shutdown (GPIO17) не была инициализирована или ошибка при инициализации."
            print(message)
            # Информируем пользователя через toast, если кнопка неисправна/не готова
            self.shutdown_action_finished.emit(message)


    async def _handle_shutdown_action(self):
        """
        Асинхронный метод, выполняющий основную логику закрытия браузера Chromium
        и сопутствующих действий.
        """
        action_name = "Закрытие Chromium"
        print(f"Выполняется действие: {action_name}...")
        
        try:
            # 1. Проигрывание звука (если mpg123 установлен и файл существует)
            # Убедитесь, что mpg123 установлен: sudo apt-get install mpg123
            # И что путь к файлу /home/pi/Music/Gong.mp3 корректен.
            # os.system() является блокирующим вызовом. Для длительных звуков лучше использовать subprocess.
            # Для короткого звука это может быть приемлемо, но в async-методе лучше избегать.
            # Заменим на asyncio.create_subprocess_shell для неблокирующего выполнения.
            process_sound = await asyncio.create_subprocess_shell('mpg123 /home/pi/Music/Gong.mp3')
            await process_sound.wait() # Дождемся завершения проигрывания звука
            
            # 2. Системное уведомление (если libnotify-bin установлен)
            # os.system('notify-send "Chromium Закрыт" "Браузер был принудительно завершен." --icon=dialog-information')
            process_notify = await asyncio.create_subprocess_shell(
                'notify-send "Chromium Закрыт" "Браузер был принудительно завершен." --icon=dialog-information'
            )
            await process_notify.wait()

            # 3. Завершение процесса chromium
            # -o означает "самый старый" из найденных процессов.
            # pkill возвращает 0 при успехе (хотя бы один процесс убит), 1 если процесс не найден.
            process_pkill = await asyncio.create_subprocess_shell('pkill -o chromium')
            return_code = await process_pkill.wait() 
            
            if return_code == 0:
                print("Процесс chromium успешно завершен.")
            else:
                print(f"Команда 'pkill -o chromium' завершилась с кодом {return_code}. Возможно, процесс chromium не был найден.")

            # 4. Пауза (если необходима)
            await asyncio.sleep(1) # Уменьшил паузу с 5 до 1 секунды
            
            message = f"Действие '{action_name}' выполнено."
            if return_code != 0 :
                 message += " (Chromium не найден)"
            print(message)
            self.shutdown_action_finished.emit(message) # Отправляем сигнал в MainWindow

        except Exception as e:
            error_message = f"Ошибка при выполнении действия '{action_name}': {e}"
            print(error_message)
            self.shutdown_action_finished.emit(error_message) # Отправляем сообщение об ошибке

    # --- Остальные методы-заглушки для GPIO ---
    # control_gpio_1 был удален, так как GPIO17 теперь используется для shutdown_button

    async def control_gpio_2(self):
        """Асинхронная заглушка для управления вторым GPIO-каналом/устройством."""
        print("Действие для GPIO 2 (заглушка): выполнено.")
        await asyncio.sleep(0.1)
        # Пример, если бы этот метод тоже отправлял сигнал:
        # self.shutdown_action_finished.emit("Заглушка GPIO 2 выполнена") 

    async def control_gpio_3(self):
        """Асинхронная заглушка для управления третьим GPIO-каналом/устройством."""
        print("Действие для GPIO 3 (заглушка): выполнено.")
        await asyncio.sleep(0.1)

    async def control_gpio_4(self):
        """Асинхронная заглушка для управления четвертым GPIO-каналом/устройством."""
        print("Действие для GPIO 4 (заглушка): выполнено.")
        await asyncio.sleep(0.1)

    def close(self):
        """
        Корректно освобождает ресурсы GPIO, используемые этим контроллером.
        Вызывается при закрытии приложения.
        """
        if hasattr(self, 'shutdown_button') and self.shutdown_button:
            try:
                self.shutdown_button.close()
                print("GPIOController: Кнопка Shutdown (GPIO17) успешно освобождена.")
            except Exception as e:
                print(f"GPIOController: Ошибка при освобождении кнопки Shutdown (GPIO17): {e}")
        
        # ... (закрытие других GPIO объектов, если они были инициализированы) ...
        print("GPIOController: Ресурсы освобождены.")

```
