# app/logic/network_checker.py
# Модуль для асинхронной проверки доступности сети с использованием PING.
import asyncio
import platform  # Для определения операционной системы и формирования корректной команды PING
from PyQt6.QtCore import QObject, pyqtSignal

class NetworkChecker(QObject):
    """
    Класс NetworkChecker выполняет периодическую проверку сетевого соединения
    с указанным хостом (ping_target) с помощью команды PING.
    Работает асинхронно, чтобы не блокировать основной поток приложения.
    """
    # Сигнал, информирующий об изменении статуса сети.
    # Передает:
    #   bool: True, если сеть доступна, False - если недоступна.
    #   str: Сообщение о статусе.
    network_status_changed = pyqtSignal(bool, str)

    def __init__(self, target="8.8.8.8", parent=None):
        """
        Инициализация NetworkChecker.
        Args:
            target (str): IP-адрес или доменное имя для PING-проверки (по умолчанию DNS Google).
            parent (QObject, optional): Родительский объект PyQt.
        """
        super().__init__(parent)
        self.ping_target = target  # Хост для PING
        self.ping_timeout = 1  # Таймаут для одной команды PING в секундах
        self.max_failures = 3  # Количество последовательных неудачных PING, после которых сеть считается недоступной
        self.current_failures = 0  # Текущее количество последовательных неудач PING
        self.is_network_available = True  # Начальное предположение о доступности сети
        self.running = False  # Флаг, управляющий циклом мониторинга
        self.check_interval = 10  # Интервал между проверками PING в секундах
        print(f"NetworkChecker инициализирован для цели: {self.ping_target}")

    def start_monitoring(self):
        """
        Запускает асинхронный цикл мониторинга сети.
        """
        print("Запуск мониторинга сети...")
        self.running = True
        asyncio.create_task(self._monitor_loop()) # Создание задачи asyncio для фонового выполнения

    def stop_monitoring(self):
        """
        Останавливает цикл мониторинга сети.
        """
        print("Остановка мониторинга сети...")
        self.running = False

    async def _do_ping(self):
        """
        Асинхронно выполняет одну PING-проверку к self.ping_target.
        Возвращает True, если PING успешен, иначе False.
        """
        system = platform.system().lower()  # Определение ОС для корректной команды PING
        # Формирование команды PING в зависимости от ОС
        if system == "windows":
            # -n 1: отправить 1 запрос
            # -w (timeout): таймаут в миллисекундах
            cmd = f"ping -n 1 -w {self.ping_timeout * 1000} {self.ping_target}"
        elif system == "linux" or system == "darwin":  # darwin для macOS
            # -c 1: отправить 1 пакет
            # -W (timeout): таймаут в секундах
            cmd = f"ping -c 1 -W {self.ping_timeout} {self.ping_target}"
        else:
            print(f"Платформа {system} не поддерживается для PING.")
            # Если платформа не поддерживается, считаем PING неудачным,
            # чтобы избежать ошибок при попытке выполнить неизвестную команду.
            return False

        try:
            # print(f"Выполнение PING: {cmd}")
            # Асинхронный запуск PING как подпроцесса оболочки.
            # stdout и stderr перенаправляются, чтобы избежать вывода в консоль основной программы.
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # Ожидание завершения процесса PING
            stdout, stderr = await process.communicate() 
            
            # Отладочный вывод результатов PING (можно раскомментировать при необходимости)
            # print(f"PING к {self.ping_target} код возврата: {process.returncode}")
            # if stdout:
            #     print(f"PING stdout: {stdout.decode(errors='ignore')}")
            # if stderr:
            #     print(f"PING stderr: {stderr.decode(errors='ignore')}")

            # Код возврата 0 обычно означает успешный PING
            return process.returncode == 0
        except FileNotFoundError:
            # Ошибка, если команда 'ping' не найдена в системе.
            print(f"Ошибка: команда 'ping' не найдена. Убедитесь, что она установлена и доступна в PATH.")
            return False
        except Exception as e:
            # Любые другие ошибки при выполнении PING.
            print(f"Ошибка при выполнении PING: {e}")
            return False

    async def _monitor_loop(self):
        """
        Основной асинхронный цикл мониторинга сети.
        Периодически выполняет PING и обновляет статус доступности сети.
        """
        print("Цикл мониторинга сети запущен.")
        # Первая проверка может быть выполнена сразу при запуске, если раскомментировать:
        # if self.running:
        #     await self._check_status() # (потребуется реализовать _check_status или встроить логику)

        while self.running:
            # Ожидание перед следующей проверкой.
            await asyncio.sleep(self.check_interval) 
            # Повторная проверка флага running, т.к. он мог измениться во время sleep.
            if not self.running: 
                break
            
            # print("Выполнение плановой проверки сети...")
            success = await self._do_ping() # Выполнение PING

            if success:
                # PING успешен
                # print(f"PING к {self.ping_target} успешен.")
                self.current_failures = 0 # Сброс счетчика неудач
                if not self.is_network_available:
                    # Если сеть ранее была недоступна, меняем статус и отправляем сигнал
                    self.is_network_available = True
                    status_message = f"Сеть доступна (цель: {self.ping_target})"
                    print(status_message)
                    self.network_status_changed.emit(True, status_message)
            else:
                # PING неуспешен
                # print(f"PING к {self.ping_target} не удался.")
                self.current_failures += 1 # Увеличение счетчика неудач
                if self.current_failures >= self.max_failures and self.is_network_available:
                    # Если достигнуто максимальное количество неудач и сеть считалась доступной,
                    # меняем статус на "недоступна" и отправляем сигнал.
                    self.is_network_available = False
                    status_message = f"Сеть недоступна: {self.current_failures} PING не прошли (цель: {self.ping_target})"
                    print(status_message)
                    self.network_status_changed.emit(False, status_message)
                # Дополнительные условия (в текущей логике не должны активно срабатывать, но оставлены для полноты):
                elif self.current_failures < self.max_failures and not self.is_network_available:
                    # Это условие маловероятно, т.к. is_network_available сбрасывается только при max_failures.
                    # Означало бы, что сеть была недоступна, но текущий PING прошел (уже обработано выше).
                    pass 
                elif self.current_failures >= self.max_failures and not self.is_network_available:
                    # Сеть по-прежнему недоступна, сигнал уже был отправлен ранее.
                    # Можно добавить логирование или периодическое напоминание, если необходимо.
                    # print(f"Сеть все еще недоступна: {self.current_failures} неудач для {self.ping_target}")
                    pass

        print("Цикл мониторинга сети остановлен.")

    # Пример вспомогательного метода для немедленной проверки статуса (не используется в текущей логике _monitor_loop)
    # async def _check_status(self):
    #     """Немедленно проверяет статус сети и обновляет его, если необходимо."""
    #     success = await self._do_ping()
    #     if success:
    #         self.current_failures = 0
    #         if not self.is_network_available:
    #             self.is_network_available = True
    #             self.network_status_changed.emit(True, f"Сеть доступна ({self.ping_target})")
    #     else:
    #         self.current_failures += 1
    #         if self.current_failures >= self.max_failures and self.is_network_available:
    #             self.is_network_available = False
    #             self.network_status_changed.emit(False, f"Сеть недоступна: {self.current_failures} PING не прошли ({self.ping_target})")
```
