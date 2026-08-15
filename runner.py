#!/usr/bin/env python3
"""
Управляющий скрипт для подготовки изолированного Python и запуска игры.
Последовательность:
1. Скачивает и распаковывает встроенный Python 3.10.5
2. Устанавливает pip и зависимости в локальную папку
3. Запускает game.py через локальный Python
"""

import subprocess
import sys
import os
import signal
import time
import zipfile
import urllib.request
import shutil
from pathlib import Path

# Константы
PYTHON_ZIP_URL = "https://www.python.org/ftp/python/3.10.5/python-3.10.5-embed-amd64.zip"
PIP_PYZ_URL = "https://bootstrap.pypa.io/pip/pip.pyz"
REQUIREMENTS_URL = "https://raw.githubusercontent.com/Endlad2/PingPongMultiplayer/refs/heads/main/requirements.txt"
PYTHON_DIR = Path("python")
PYTHON_EXE = PYTHON_DIR / "python.exe"
PIP_PYZ = PYTHON_DIR / "pip.pyz"

def download_file(url, destination):
    """Скачивает файл по URL и сохраняет по пути destination."""
    print(f"Скачивание: {url}")
    try:
        urllib.request.urlretrieve(url, destination)
        print(f"Файл сохранен: {destination}")
        return True
    except Exception as e:
        print(f"Ошибка при скачивании {url}: {e}")
        return False

def extract_zip(zip_path, extract_to):
    """Распаковывает ZIP-архив в указанную папку."""
    print(f"Распаковка: {zip_path} -> {extract_to}")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print("Распаковка завершена.")
        return True
    except Exception as e:
        print(f"Ошибка при распаковке: {e}")
        return False

def setup_python_environment():
    """Настраивает изолированное окружение Python."""
    script_dir = Path(__file__).parent.absolute()
    python_dir_abs = script_dir / PYTHON_DIR
    python_exe_abs = script_dir / PYTHON_EXE
    pip_pyz_abs = script_dir / PIP_PYZ
    
    # Шаг 1: Скачиваем Python ZIP
    python_zip = script_dir / "python.zip"
    if not python_zip.exists():
        if not download_file(PYTHON_ZIP_URL, python_zip):
            return False
    else:
        print("ZIP-архив Python уже скачан.")
    
    # Шаг 2: Создаем папку и распаковываем
    if not python_dir_abs.exists():
        python_dir_abs.mkdir(parents=True)
    
    if not (python_dir_abs / "python310._pth").exists():
        if not extract_zip(python_zip, python_dir_abs):
            return False
    else:
        print("Python уже распакован.")
    
    # Шаг 3: Скачиваем pip.pyz
    if not pip_pyz_abs.exists():
        if not download_file(PIP_PYZ_URL, pip_pyz_abs):
            return False
    else:
        print("pip.pyz уже скачан.")
    
    # Шаг 4: Скачиваем requirements.txt
    req_file = script_dir / "requirements.txt"
    if not req_file.exists():
        print(f"Скачивание requirements.txt из {REQUIREMENTS_URL}")
        try:
            urllib.request.urlretrieve(REQUIREMENTS_URL, req_file)
            print(f"Сохранен в: {req_file}")
        except Exception as e:
            print(f"Ошибка при скачивании requirements.txt: {e}")
            return False
    else:
        print("requirements.txt уже скачан.")
    
    # Шаг 5: Устанавливаем зависимости
    print("Установка зависимостей через pip...")
    try:
        # Устанавливаем зависимости
        install_cmd = [
            str(python_exe_abs),
            str(pip_pyz_abs),
            "install",
            "-r",
            str(req_file),
            "--target",
            str(python_dir_abs)  # Устанавливаем прямо в папку python
        ]
        print(f"Выполнение: {' '.join(install_cmd)}")
        print(f"Рабочая директория: {script_dir}")
        
        result = subprocess.run(
            install_cmd,
            cwd=str(script_dir),
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("Зависимости установлены успешно.")
            return True
        else:
            print("Ошибка при установке зависимостей:")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"Ошибка при установке зависимостей: {e}")
        return False

def signal_handler(sig, frame):
    """Обработчик Ctrl+C для корректного завершения."""
    print("\nПолучен сигнал прерывания. Завершаем работу...")
    sys.exit(0)

def main():
    """Главная функция."""
    # Устанавливаем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Определяем корневую директорию (где находится этот скрипт)
    script_dir = Path(__file__).parent.absolute()
    
    print("=" * 60)
    print("ЗАПУСК УСТАНОВКИ ИЗОЛИРОВАННОГО ОКРУЖЕНИЯ PYTHON")
    print("=" * 60)
    print(f"Рабочая директория: {script_dir}")
    
    # Шаг 1: Настраиваем Python окружение
    if not setup_python_environment():
        print("Не удалось настроить Python окружение. Выход.")
        sys.exit(1)
    
    # Шаг 2: Проверяем наличие game.py
    game_script = script_dir / "game.py"
    if not game_script.exists():
        print("Ошибка: game.py не найден в текущей директории!")
        print(f"Ищем в: {game_script}")
        sys.exit(1)
    
    # Шаг 3: Запускаем game.py через локальный Python
    print("\n" + "=" * 60)
    print("ЗАПУСК ИГРОВОГО СКРИПТА ЧЕРЕЗ ИЗОЛИРОВАННЫЙ PYTHON")
    print("=" * 60)
    
    try:
        # Запускаем game.py и ждём его завершения
        python_path = script_dir / PYTHON_EXE
        game_cmd = [
            str(python_path),
            str(game_script)
        ]
        print(f"Выполнение: {' '.join(game_cmd)}")
        print(f"Рабочая директория: {script_dir}")
        
        game_result = subprocess.run(
            game_cmd,
            cwd=str(script_dir),
            check=False
        )
        
        if game_result.returncode == 0:
            print("\nИгра завершена успешно.")
        else:
            print(f"\nИгра завершилась с кодом: {game_result.returncode}")
            
    except KeyboardInterrupt:
        print("\nИгра прервана пользователем.")
    except Exception as e:
        print(f"Ошибка при запуске game.py: {e}")
    
    print("\nВсе процессы завершены. Выход.")

if __name__ == "__main__":
    main()
