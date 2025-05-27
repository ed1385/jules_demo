# app/logic/camera_handler.py
# Модуль для управления камерой, захвата и обработки видеопотока.
import cv2  # Библиотека OpenCV для работы с компьютерным зрением
import asyncio  # Для асинхронного выполнения операций
import time # Для отслеживания времени кадра и FPS
from PyQt5.QtCore import QObject, pyqtSignal, QSize, Qt # PySide6 -> PyQt5, Signal -> pyqtSignal
from PyQt5.QtGui import QImage  # PySide6 -> PyQt5

class CameraHandler(QObject):
    """
    Класс CameraHandler отвечает за захват видео с камеры,
    обработку кадров и передачу их для отображения в UI.
    Работает в асинхронном режиме, чтобы не блокировать основной поток приложения.
    """
    # Сигнал, передающий новый обработанный кадр (в формате QImage)
    new_frame = pyqtSignal(QImage) # Signal -> pyqtSignal
    # Сигнал, сообщающий об ошибках, возникших при работе с камерой
    camera_error = pyqtSignal(str) # Signal -> pyqtSignal

    def __init__(self, camera_index=1, capture_width=544, capture_height=288, target_display_size=QSize(400, 300), parent=None):
        """
        Инициализация обработчика камеры.
        Args:
            camera_index (int): Индекс камеры в системе. По умолчанию 1.
            capture_width (int): Целевая ширина захвата кадра с камеры.
            capture_height (int): Целевая высота захвата кадра с камеры.
            target_display_size (QSize): Целевой размер для отображения в GUI.
            parent (QObject, optional): Родительский объект PyQt.
        """
        super().__init__(parent)
        self.camera_index = camera_index  # Индекс камеры (по умолчанию 1 для внешней USB-камеры)
        self.capture_width = capture_width  # Ширина кадра при захвате с камеры
        self.capture_height = capture_height  # Высота кадра при захвате с камеры
        self.target_display_size = target_display_size  # Целевой размер для отображения в GUI (например, 400x300)

        self.cap = None  # Объект VideoCapture из OpenCV
        self.running = False  # Флаг, управляющий основным циклом захвата кадров
        
        self.FPS_LIMIT = 20.0  # Желаемое ограничение FPS для цикла захвата (исправлено с глобальной на локальную)
        self.last_frame_time = 0  # Время получения последнего кадра, используется для контроля FPS

        # Константы для логики восстановления камеры при сбоях
        self.MAX_OPEN_ATTEMPTS = 3  # Макс. число попыток полного переоткрытия камеры
        self.MAX_READ_FAILURES = 5  # Макс. число последовательных неудачных чтений кадра перед попыткой переоткрытия
        
        self._current_open_attempts = 0  # Счетчик текущих попыток открытия/переоткрытия
        self._current_read_failures = 0  # Счетчик текущих последовательных неудачных чтений
        print(f"CameraHandler инициализирован: камера_индекс={self.camera_index}, "
              f"разрешение_захвата={self.capture_width}x{self.capture_height}, FPS_лимит={self.FPS_LIMIT}, "
              f"размер_отображения={self.target_display_size.width()}x{self.target_display_size.height()}")


    async def _try_system_level_restart(self):
        """
        Заглушка для попытки системного перезапуска камеры.
        В реальной системе это может включать вызов платформо-зависимых команд.
        Здесь просто эмитирует сообщение об ошибке.
        """
        error_message = "Критический сбой камеры. Системный перезапуск не реализован/не удался. Проверьте подключение."
        print(f"Камера {self.camera_index}: {error_message}")
        self.camera_error.emit(error_message)
        return False # Возвращает False, так как реальный перезапуск не выполнен

    def start_capture(self):
        """
        Запускает процесс захвата видео с камеры.
        Устанавливает флаг self.running в True и создает асинхронную задачу для _capture_loop.
        Сбрасывает счетчики ошибок перед запуском.
        """
        self.running = True
        self._current_open_attempts = 0
        self._current_read_failures = 0
        # asyncio.create_task() планирует выполнение _capture_loop() в цикле событий asyncio
        asyncio.create_task(self._capture_loop())
        print(f"Камера {self.camera_index}: Запуск захвата видео.")

    def stop_capture(self):
        """
        Останавливает процесс захвата видео.
        Сбрасывает флаг self.running и освобождает ресурсы камеры.
        """
        self.running = False
        if self.cap:
            # Выполняем release в отдельном потоке, так как это может быть блокирующей операцией
            # Хотя обычно это быстро, но для единообразия с cap.read() и cap.open()
            try:
                # Не используем await здесь, т.к. stop_capture - синхронный метод.
                # Если бы stop_capture был async, можно было бы await asyncio.to_thread(self.cap.release)
                # В данном контексте, если release блокирует надолго, это может вызвать проблемы
                # при быстром закрытии приложения. Однако, обычно это не так.
                self.cap.release()
            except Exception as e:
                print(f"Камера {self.camera_index}: Исключение при self.cap.release(): {e}")
            self.cap = None
        print(f"Камера {self.camera_index}: Остановка захвата видео.")

    async def _attempt_open_camera(self):
        """Попытка открыть камеру и установить параметры."""
        print(f"Камера {self.camera_index}: Попытка открытия (попытка {self._current_open_attempts + 1}/{self.MAX_OPEN_ATTEMPTS})...")
        if self.cap:
            await asyncio.to_thread(self.cap.release) # Освобождаем предыдущий экземпляр, если был
            self.cap = None

        # self.cap = cv2.VideoCapture(self.camera_index) # Синхронный вызов
        self.cap = await asyncio.to_thread(cv2.VideoCapture, self.camera_index) # Асинхронный вызов

        if self.cap and self.cap.isOpened():
            print(f"Камера {self.camera_index}: Успешно открыта. Установка параметров разрешения захвата ({self.capture_width}x{self.capture_height})...")
            # Установка желаемой ширины и высоты кадра. Это также блокирующие операции.
            await asyncio.to_thread(self.cap.set, cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
            await asyncio.to_thread(self.cap.set, cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
            
            # (Опционально) Проверка установленных значений (может отличаться от запрошенных, если камера не поддерживает)
            # actual_width = await asyncio.to_thread(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH)
            # actual_height = await asyncio.to_thread(self.cap.get, cv2.CAP_PROP_FRAME_HEIGHT)
            # print(f"Камера {self.camera_index}: Запрошено {self.capture_width}x{self.capture_height}, фактическое {actual_width}x{actual_height}.")
            
            print(f"Камера {self.camera_index}: Параметры разрешения установлены.")
            self._current_open_attempts = 0  # Сброс счетчика попыток открытия при успехе
            self._current_read_failures = 0  # Также сбрасываем ошибки чтения, т.к. камера успешно (пере)открыта
            return True
        else:
            print(f"Камера {self.camera_index}: Не удалось открыть.")
            if self.cap: # Если объект создался, но не открылся
                 await asyncio.to_thread(self.cap.release)
                 self.cap = None
            return False

    async def _capture_loop(self):
        """
        Асинхронный метод, представляющий основной цикл захвата и обработки кадров.
        Включает логику повторных попыток открытия и чтения кадров.
        """
        # Начальная попытка открыть камеру
        if not await self._attempt_open_camera():
            self._current_open_attempts += 1
            # Если первая попытка не удалась, попробуем еще несколько раз перед полным отказом
            while self.running and self._current_open_attempts < self.MAX_OPEN_ATTEMPTS:
                await asyncio.sleep(2) # Пауза перед следующей попыткой открытия
                if not await self._attempt_open_camera():
                    self._current_open_attempts += 1
                else:
                    break # Успешно открыли, выходим из цикла попыток открытия
            
            if not (self.cap and self.cap.isOpened()):
                error_msg = f"Не удалось открыть камеру {self.camera_index} после {self._current_open_attempts} попыток."
                print(error_msg)
                self.camera_error.emit(error_msg)
                # Попытка "системного перезапуска" как крайняя мера
                await self._try_system_level_restart()
                self.running = False
                return

        # Основной цикл чтения кадров
        while self.running:
            if not (self.cap and self.cap.isOpened()):
                # Это условие не должно часто срабатывать, если камера была успешно открыта,
                # но на случай, если камера "отвалилась" без ошибки чтения.
                print(f"Камера {self.camera_index}: Внезапно обнаружена закрытой перед чтением.")
                self.camera_error.emit("Камера неожиданно закрылась.")
                self._current_read_failures = self.MAX_READ_FAILURES # Форсируем логику восстановления
            else:
                ret, frame = await asyncio.to_thread(self.cap.read) # Чтение кадра в отдельном потоке

                if ret:
                    self._current_read_failures = 0 # Сброс ошибок чтения при успехе
                    # self._current_open_attempts = 0 # Камера работает, все попытки открытия сброшены
                                                   # Сбрасывается в _attempt_open_camera
                    
                    # Поворот кадра на 90 градусов против часовой стрелки.
                    # Это может быть необходимо для некоторых USB-камер, которые по умолчанию дают перевернутое изображение.
                    try:
                        rotated_frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    except Exception as e:
                        print(f"Камера {self.camera_index}: Ошибка при повороте кадра: {e}")
                        # Пропускаем этот кадр, если поворот не удался
                        # Управление FPS нижезаботится о задержке
                        await asyncio.sleep(0.01) # Небольшая пауза
                        continue 
                    # === Конец интеграции кода пользователя ===
                    
                    # Конвертация повернутого кадра из BGR (OpenCV) в RGB.
                    rgb_image = cv2.cvtColor(rotated_frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_image.shape
                    bytes_per_line = ch * w
                    qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    qt_image_scaled = qt_image.scaled(self.target_display_size, Qt.KeepAspectRatio, Qt.SmoothTransformation) # Qt.AspectRatioMode.* -> Qt.*, Qt.TransformationMode.* -> Qt.*
                    self.new_frame.emit(qt_image_scaled)
                else:
                    # Кадр не получен
                    self._current_read_failures += 1
                    print(f"Камера {self.camera_index}: Не удалось получить кадр (попытка {self._current_read_failures}/{self.MAX_READ_FAILURES}).")

            # Логика восстановления камеры при сбоях чтения
            if self._current_read_failures >= self.MAX_READ_FAILURES:
                print(f"Камера {self.camera_index}: Превышено макс. число ошибок чтения. Попытка восстановления...")
                self.camera_error.emit(f"Сбой чтения с камеры {self.camera_index}. Попытка восстановления...")

                if await self._attempt_open_camera():
                    print(f"Камера {self.camera_index}: Восстановлена после сбоя чтения.")
                    # self._current_open_attempts уже сброшен в _attempt_open_camera
                    # self._current_read_failures уже сброшен в _attempt_open_camera
                else:
                    self._current_open_attempts += 1 # Увеличиваем, т.к. _attempt_open_camera не смогла открыть
                    print(f"Камера {self.camera_index}: Не удалось восстановить камеру стандартным способом (попытка открытия {self._current_open_attempts}/{self.MAX_OPEN_ATTEMPTS}).")
                    if self._current_open_attempts >= self.MAX_OPEN_ATTEMPTS:
                        print(f"Камера {self.camera_index}: Все попытки восстановления исчерпаны.")
                        await self._try_system_level_restart() # Крайняя мера
                        # Сообщение об ошибке уже было отправлено из _try_system_level_restart
                        self.running = False # Остановка цикла
                        break 
                    else:
                        # Даем шанс следующей итерации внешнего while self.running после паузы
                        await asyncio.sleep(1) # Короткая пауза перед следующей попыткой в цикле while self.running

            if self.running: # Если не остановили цикл из-за критического сбоя
                await asyncio.sleep(0.03) # Пауза для контроля FPS и предоставления времени другим задачам
        
        # Очистка при завершении цикла (если он не был прерван исключением)
        if self.cap and self.cap.isOpened():
            print(f"Камера {self.camera_index}: Освобождение ресурсов в конце _capture_loop.")
            await asyncio.to_thread(self.cap.release)
        self.cap = None
        print(f"Камера {self.camera_index}: Завершение работы _capture_loop (running={self.running}).")
