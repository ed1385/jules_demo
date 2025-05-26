# app/logic/network_checker.py
# Модуль для асинхронной проверки доступности сети с использованием PingServer из gpiozero.
# Управляет светодиодами (зеленый/красный) для индикации статуса сети и
# отправляет сигналы для обновления GUI.

import asyncio
from PySide6.QtCore import QObject, Signal # PyQt6 -> PySide6, pyqtSignal -> Signal
from gpiozero import LED, PingServer
from gpiozero.tools import negated # Утилита для инвертирования значения источника gpiozero

class NetworkChecker(QObject):
    """
    Класс NetworkChecker использует gpiozero.PingServer для мониторинга доступности сети (8.8.8.8).
    Автоматически управляет зеленым и красным светодиодами для индикации статуса.
    Периодически проверяет статус и отправляет сигнал network_status_gui для обновления UI.
    """
    # Сигнал для обновления GUI: True/False (доступен/нет), строка сообщения
    network_status_gui = Signal(bool, str) # pyqtSignal -> Signal

    def __init__(self, parent=None):
        """
        Инициализация NetworkChecker.
        Настраивает светодиоды, PingServer и их взаимодействие.
        Args:
            parent (QObject, optional): Родительский объект PyQt.
        """
        super().__init__(parent)
        
        # PIN-коды для светодиодов (BCM нумерация GPIO).
        # Убедитесь, что эти пины не используются другими компонентами или службами ОС.
        # Зеленый светодиод: GPIO 21 (сигнализирует доступность сети).
        # Красный светодиод: GPIO 26 (сигнализирует отсутствие сети).
        try:
            self.green_led = LED(21)
            self.red_led = LED(26)
            
            # PingServer для проверки доступности хоста (по умолчанию 8.8.8.8 - DNS Google).
            self.ping_server = PingServer('8.8.8.8')

            # Настройка автоматического управления светодиодами на основе состояния PingServer.
            # source_delay: интервал (в секундах), с которым PingServer будет выполнять проверку PING.
            self.ping_server.source_delay = 10 
            # self.green_led.source: привязывает состояние светодиода к значению PingServer.
            # Зеленый светодиод будет гореть, когда self.ping_server.value (результат пинга) True.
            self.green_led.source = self.ping_server.values 
            # Красный светодиод будет гореть, когда self.ping_server.value False.
            # negated() инвертирует значение, так как красный LED должен гореть при отсутствии сети.
            self.red_led.source = negated(self.ping_server.values)

            # Начальное определение статуса сети на основе текущего значения PingServer.
            self.is_network_available = self.ping_server.value 
            self.running = False # Флаг для управления циклом _monitor_loop, который обновляет GUI.
            # Интервал в секундах для _monitor_loop, как часто проверять self.ping_server.value для обновления GUI.
            # Это может быть чаще, чем source_delay, чтобы GUI реагировал быстрее на уже определенное изменение.
            self.gui_check_interval = 1 

            print(f"NetworkChecker инициализирован. Зеленый LED: GPIO21, Красный LED: GPIO26. Начальный статус сети (gpiozero): {'Доступен' if self.is_network_available else 'Отсутствует'}")

        except Exception as e:
            # Обработка возможных исключений при инициализации gpiozero (например, если библиотека не установлена или запущено не на RPi)
            print(f"Ошибка инициализации NetworkChecker (gpiozero): {e}")
            # self.camera_error.emit(f"Ошибка GPIO: {e}") # Удалено, т.к. camera_error не определен здесь.
            # Вместо этого можно создать свой сигнал ошибки GPIO или использовать logging.
            # Для данной задачи рефакторинга просто убираем вызов неопределенного сигнала.
            # Устанавливаем заглушки, чтобы приложение не упало при вызове методов
            self.green_led = None
            self.red_led = None
            self.ping_server = None
            self.is_network_available = False # Предполагаем худший случай
            self.running = False
            # Можно было бы создать "пустые" объекты LED и PingServer, если бы gpiozero это поддерживала легко для заглушек.
            # Вместо этого просто проверяем на None в других методах.


    def start_monitoring(self):
        """
        Запускает асинхронный цикл _monitor_loop для периодической проверки статуса PingServer
        и отправки сигналов в GUI.
        """
        if not self.ping_server: # Если gpiozero не инициализировался
            print("NetworkChecker: gpiozero компоненты не инициализированы. Мониторинг для GUI не запущен.")
            return

        if not self.running:
            self.running = True
            # Создание задачи asyncio для фонового выполнения _monitor_loop
            asyncio.create_task(self._monitor_loop())
            print("Мониторинг сети для GUI (на основе gpiozero.PingServer) запущен.")

    def stop_monitoring(self):
        """
        Останавливает цикл _monitor_loop и освобождает ресурсы gpiozero.
        """
        self.running = False # Сигнал для остановки цикла _monitor_loop
        
        if not self.ping_server: # Если gpiozero не инициализировался
            print("NetworkChecker: gpiozero компоненты не инициализированы. Остановка не требуется.")
            return

        # Отключаем source перед закрытием, чтобы остановить внутренние активности gpiozero,
        # связанные с обновлением состояния светодиодов.
        if self.green_led and hasattr(self.green_led, 'source'):
             self.green_led.source = None
        if self.red_led and hasattr(self.red_led, 'source'):
             self.red_led.source = None
        
        # Закрываем GPIO устройства. Метод close() освобождает GPIO пины.
        if self.green_led:
            self.green_led.close()
        if self.red_led:
            self.red_led.close()
        if self.ping_server:
            self.ping_server.close()
            
        print("Мониторинг сети остановлен, ресурсы gpiozero освобождены.")

    async def _monitor_loop(self):
        """
        Асинхронный цикл, который периодически проверяет значение self.ping_server.value
        и, если оно изменилось, отправляет сигнал network_status_gui для обновления интерфейса.
        """
        if not self.ping_server: # Дополнительная проверка
            print("NetworkChecker: _monitor_loop не может быть запущен, PingServer не инициализирован.")
            self.running = False
            return
            
        print("Цикл мониторинга GUI для статуса сети (gpiozero) запущен...")
        
        # Отправляем начальный статус в GUI немедленно при запуске цикла
        # Это гарантирует, что GUI получит статус, даже если он не изменится в будущем.
        initial_message = "Интернет (gpiozero): доступен" if self.is_network_available else "Интернет (gpiozero): отсутствует"
        self.network_status_gui.emit(self.is_network_available, initial_message)

        while self.running:
            # Ожидание указанного интервала перед следующей проверкой
            await asyncio.sleep(self.gui_check_interval)
            
            # Если за время ожидания флаг running был изменен на False (например, вызовом stop_monitoring),
            # прерываем цикл.
            if not self.running:
                break

            # Получаем текущее значение от PingServer (True если пинг успешен, False если нет)
            current_status = self.ping_server.value
            
            # Если текущий статус отличается от ранее сохраненного, значит, произошло изменение.
            if current_status != self.is_network_available:
                self.is_network_available = current_status # Обновляем сохраненный статус
                message = "Интернет (gpiozero): доступен" if current_status else "Интернет (gpiozero): отсутствует"
                print(f"Статус сети изменился (для GUI, gpiozero): {message}")
                # Отправляем сигнал для обновления GUI
                self.network_status_gui.emit(current_status, message)
        
        print("Цикл мониторинга GUI для статуса сети (gpiozero) остановлен.")

```
