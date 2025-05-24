# app/window.py
# Основной файл для главного окна приложения PyQt.
# Отвечает за компоновку UI, инициализацию логических модулей и обработку событий.

from PyQt6.QtWidgets import QMainWindow, QWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt, QUrl, QTimer, QPoint
from PyQt6.QtGui import QPalette, QColor, QPixmap # QPalette и QColor могут быть не нужны после перехода на стили
from PyQt6.QtWebEngineWidgets import QWebEngineView # Для отображения HTML контента (погода)

# Импорт логических модулей
from app.logic.camera_handler import CameraHandler
from app.logic.network_checker import NetworkChecker
from app.logic.gpio_controller import GPIOController
import asyncio # Для управления асинхронными задачами (например, GPIO)

class MainWindow(QMainWindow):
    """
    Главное окно приложения. Наследуется от QMainWindow.
    Отвечает за создание и отображение всех виджетов,
    а также за инициализацию и управление логическими компонентами.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Киоск Raspberry Pi") # Заголовок окна (не виден в полноэкранном режиме)
        
        # Установка флагов для режима киоска:
        # - FramelessWindowHint: убирает рамку окна и заголовок.
        # - WindowStaysOnTopHint: старается держать окно поверх других (полезно для киосков).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # 1. Общий фон окна и базовые стили
        self.setObjectName("mainWindow") # Имя объекта для применения стилей
        self.setStyleSheet("#mainWindow { background-color: #e0e0e0; }") # Базовый цвет фона
        
        # Центральный виджет, который будет содержать все остальные элементы
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        # Основной менеджер компоновки - сетка (2x2)
        layout = QGridLayout(central_widget)
        layout.setSpacing(10) # Расстояние между ячейками сетки
        layout.setContentsMargins(10, 10, 10, 10) # Отступы от краев окна до сетки

        # --- Первая часть экрана (0,0): Информер погоды ---
        self.weather_widget_view = QWebEngineView() # Виджет для отображения веб-страниц
        self.weather_widget_view.setObjectName("weatherView")
        self.weather_widget_view.setStyleSheet("#weatherView { border-radius: 10px; }") # Скругление углов
        # HTML-код виджета погоды (предоставлен сторонним сервисом)
        html_content = '<div id="ww_80462c5023641" v="1.3" loc="id" a=\'{"t":"responsive","lang":"ru","ids":["wl3996"],"font":"Arial","sl_ics":"one_a","sl_sot":"celsius","cl_bkg":"image","cl_font":"#FFFFFF","cl_cloud":"#FFFFFF","cl_persp":"#81D4FA","cl_sun":"#FFC107","cl_moon":"#FFC107","cl_thund":"#FF5722"}\'><a href="https://weatherwidget.org/" id="ww_80462c5023641_u" target="_blank">Free weather widget</a></div><script async src="https://app3.weatherwidget.org/js/?id=ww_80462c5023641"></script>'
        self.weather_widget_view.setHtml(html_content, baseUrl=QUrl("https://app3.weatherwidget.org/")) # Загрузка HTML
        layout.addWidget(self.weather_widget_view, 0, 0) # Добавление в сетку

        # --- Вторая часть экрана (0,1): Вид с камеры ---
        self.camera_view_label = QLabel("Ожидание видео...") # Метка для отображения кадров с камеры
        self.camera_view_label.setAlignment(Qt.AlignmentFlag.AlignCenter) # Текст по центру
        self.camera_view_label.setAutoFillBackground(False) # Отключаем автозаливку, т.к. используем стили
        self.camera_view_label.setObjectName("cameraView")
        # Стиль для области отображения камеры: черный фон, скругленные углы, белый текст
        camera_style = '''
        #cameraView {
            background-color: black;
            border-radius: 10px; 
            color: white; 
        }
        '''
        self.camera_view_label.setStyleSheet(camera_style)
        layout.addWidget(self.camera_view_label, 0, 1)

        # --- Третья часть экрана (1,0): Заглушка/Информационная панель ---
        self.part3_placeholder = QWidget() # Виджет-заглушка, может быть заменен на что-то полезное
        self.part3_placeholder.setAutoFillBackground(False) # Отключаем автозаливку
        self.part3_placeholder.setObjectName("infoPanel3")
        # Неоморфический стиль для панели
        panel_style = '''
        #infoPanel3 {
            background-color: #e0e0e0; /* Основной цвет фона, как у окна */
            border-radius: 15px; /* Скругление углов */
            border-width: 2px; /* Ширина границы */
            border-style: solid; /* Стиль границы */
            /* Цвета границ для эффекта "вдавленности/выпуклости" (сверху-слева светлее, снизу-справа темнее) */
            border-color: #c0c0c0 #f0f0f0 #f0f0f0 #c0c0c0; /* top right bottom left */
        }
        '''
        self.part3_placeholder.setStyleSheet(panel_style)
        layout.addWidget(self.part3_placeholder, 1, 0)

        # --- Четвертая часть экрана (1,1): Управление GPIO ---
        self.gpio_controller = GPIOController() # Инициализация контроллера GPIO
        
        # Контейнер для кнопок управления GPIO
        gpio_control_container = QWidget()
        gpio_control_container.setObjectName("gpioContainer")
        # Стиль для контейнера GPIO: фон и скругление
        gpio_container_style = '''
        #gpioContainer {
            background-color: #e0e0e0;
            border-radius: 10px;
        }
        '''
        gpio_control_container.setStyleSheet(gpio_container_style)
        
        # Вертикальный layout для кнопок GPIO внутри их контейнера
        gpio_layout = QVBoxLayout(gpio_control_container)
        gpio_layout.setContentsMargins(20, 20, 20, 20) # Отступы внутри контейнера
        gpio_layout.setSpacing(15) # Расстояние между кнопками

        # Создание кнопок GPIO
        self.gpio_button1 = QPushButton("GPIO Управление 1")
        self.gpio_button2 = QPushButton("GPIO Управление 2")
        self.gpio_button3 = QPushButton("GPIO Управление 3")
        self.gpio_button4 = QPushButton("GPIO Управление 4")

        # Общий неоморфический стиль для кнопок GPIO
        button_style = '''
        QPushButton {
            background-color: #e0e0e0; /* Фон кнопки */
            color: #444; /* Цвет текста */
            border-width: 2px; /* Ширина границы */
            border-style: solid; /* Стиль границы */
            /* Цвета границ для неоморфического эффекта (выпуклость) */
            border-color: #f0f0f0 #c0c0c0 #c0c0c0 #f0f0f0; /* top right bottom left */
            border-radius: 15px; /* Скругление углов */
            padding: 15px; /* Внутренние отступы */
            font-size: 14px; /* Размер шрифта */
            font-family: "DejaVu Sans", Arial, sans-serif; /* Шрифт (DejaVu Sans как хороший вариант для Linux) */
        }
        QPushButton:pressed { /* Стиль для нажатой кнопки */
            background-color: #d5d5d5; /* Слегка затемненный фон */
            /* Инвертированные цвета границ для эффекта "вдавленности" */
            border-color: #c0c0c0 #f0f0f0 #f0f0f0 #c0c0c0; 
        }
        '''
        # Применение стиля ко всем кнопкам GPIO
        self.gpio_button1.setStyleSheet(button_style)
        self.gpio_button2.setStyleSheet(button_style)
        self.gpio_button3.setStyleSheet(button_style)
        self.gpio_button4.setStyleSheet(button_style)

        # Добавление кнопок в QVBoxLayout
        gpio_layout.addWidget(self.gpio_button1)
        gpio_layout.addWidget(self.gpio_button2)
        gpio_layout.addWidget(self.gpio_button3)
        gpio_layout.addWidget(self.gpio_button4)

        # Подключение сигналов `clicked` от кнопок к асинхронным методам GPIOController.
        # Используется `asyncio.create_task` для запуска async-методов в цикле событий asyncio,
        # который интегрирован с PyQt через Quamash.
        self.gpio_button1.clicked.connect(lambda: asyncio.create_task(self.gpio_controller.control_gpio_1()))
        self.gpio_button2.clicked.connect(lambda: asyncio.create_task(self.gpio_controller.control_gpio_2()))
        self.gpio_button3.clicked.connect(lambda: asyncio.create_task(self.gpio_controller.control_gpio_3()))
        self.gpio_button4.clicked.connect(lambda: asyncio.create_task(self.gpio_controller.control_gpio_4()))
        
        layout.addWidget(gpio_control_container, 1, 1) # Добавление контейнера с кнопками в сетку
        
        # Инициализация и запуск обработчика камеры
        # camera_index=0 означает первую доступную камеру в системе.
        self.camera_handler = CameraHandler(camera_index=0) 
        self.camera_handler.new_frame.connect(self.update_camera_view) # Подключение сигнала нового кадра к слоту обновления
        self.camera_handler.camera_error.connect(self.show_camera_error) # Подключение сигнала ошибки камеры к слоту отображения
        self.camera_handler.start_capture() # Запуск захвата видео

        # Инициализация и запуск проверки сетевого соединения
        self.network_checker = NetworkChecker()
        self.network_checker.network_status_changed.connect(self.update_network_status_display) # Сигнал изменения статуса сети
        self.network_checker.start_monitoring() # Запуск мониторинга сети

        # Отображение окна в полноэкранном режиме в конце инициализации
        self.showFullScreen() 
        # self.resize(800, 600) # Можно использовать для отладки не в полноэкранном режиме
        
        print("MainWindow: Инициализация завершена. Окно готово.")
        # Атрибуты для управления всплывающими сообщениями (toast)
        self.toast_label = None # QLabel для текста сообщения
        self.toast_timer = None # QTimer для автоскрытия сообщения

    def show_toast(self, message, duration=3000):
        """
        Отображает всплывающее сообщение (toast) внизу окна.

        Args:
            message (str): Текст сообщения.
            duration (int): Длительность отображения в миллисекундах.
        """
        # Если уже есть активное сообщение, удаляем его и останавливаем таймер
        if self.toast_label:
            self.toast_label.deleteLater() 
            self.toast_label = None
        if self.toast_timer and self.toast_timer.isActive():
            self.toast_timer.stop()
            self.toast_timer = None

        # Создание нового QLabel для сообщения
        self.toast_label = QLabel(message, self) # `self` (MainWindow) как родитель
        self.toast_label.setObjectName("toastLabel")
        # Стиль для всплывающего сообщения
        toast_style = """
        #toastLabel {
            background-color: rgba(0, 0, 0, 180); /* Полупрозрачный черный фон */
            color: white; /* Белый текст */
            padding: 10px; /* Внутренние отступы */
            border-radius: 8px; /* Скругленные углы */
            font-size: 14px;
            font-family: "DejaVu Sans", Arial, sans-serif; 
        }
        """
        self.toast_label.setStyleSheet(toast_style)
        self.toast_label.adjustSize() # Автоматический подбор размера метки под текст
        
        # Позиционирование сообщения внизу по центру окна
        x = (self.width() - self.toast_label.width()) // 2
        y = self.height() - self.toast_label.height() - 20 # 20px отступ от нижнего края
        self.toast_label.move(QPoint(x, y))
        self.toast_label.show() # Показать сообщение

        # Таймер для автоматического скрытия сообщения
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True) # Таймер сработает один раз
        self.toast_timer.timeout.connect(self._hide_toast) # Подключение слота для скрытия
        self.toast_timer.start(duration) # Запуск таймера

    def _hide_toast(self):
        """Слот, вызываемый по таймауту для скрытия всплывающего сообщения."""
        if self.toast_label:
            self.toast_label.deleteLater() # Безопасное удаление виджета
            self.toast_label = None
        # Сбрасываем ссылку на таймер, т.к. он уже выполнил свою задачу
        if self.toast_timer: 
            self.toast_timer = None


    def update_camera_view(self, q_image):
        """Слот для обновления изображения с камеры в QLabel."""
        self.camera_view_label.setPixmap(QPixmap.fromImage(q_image))

    def update_network_status_display(self, is_available, message):
        """
        Слот для обработки изменения статуса сети.
        Отображает всплывающее сообщение при недоступности сети.
        """
        if not is_available:
            self.show_toast(f"Сеть: {message}", duration=4000)
        else:
            # Если сеть доступна, просто выводим информацию в консоль (можно убрать или изменить)
            print(f"Статус сети: {message}") 

    def show_camera_error(self, error_message):
        """
        Слот для отображения ошибок камеры через всплывающее сообщение.
        """
        # self.camera_view_label.setText(f"Ошибка камеры:\n{error_message}") # Можно также обновлять текст в QLabel камеры
        print(f"Camera Error: {error_message}") # Дублируем в консоль для отладки
        self.show_toast(f"Ошибка камеры: {error_message}", duration=5000)


    def closeEvent(self, event):
        """
        Обработчик события закрытия окна.
        Останавливает все фоновые процессы (камера, проверка сети) перед закрытием.
        """
        print("Завершение работы: остановка фоновых служб...")
        if hasattr(self, 'camera_handler') and self.camera_handler:
            self.camera_handler.stop_capture()
        if hasattr(self, 'network_checker') and self.network_checker:
            self.network_checker.stop_monitoring()
        super().closeEvent(event) # Вызов стандартного обработчика для завершения закрытия
