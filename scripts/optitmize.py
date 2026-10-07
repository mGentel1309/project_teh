import os
import subprocess
import time
from datetime import datetime

# Пути к файлам
INPUT_FILE = "list/listnow.txt"      # Файл, который обновляется каждый час
OUTPUT_FILE = "list/bestvpns.txt"    # Файл, куда будут записываться топ-10

def get_ping(host):
    """Проверяет пинг до хоста. Возвращает время отклика в мс или 9999, если хост недоступен."""
    
    param = '-n' if os.name == 'nt' else '-c'
    command = ['ping', param, '1', host]
    
    try:
        start_time = time.time()
        # Выполняем команду без вывода в консоль
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        
        if result.returncode == 0:
            # Считаем примерное время отклика
            return (time.time() - start_time) * 1000
    except subprocess.TimeoutExpired:
        pass
    
    return 9999  # Возвращаем большое число, если узел лежит

def select_best_vpns():
    if not os.path.exists(INPUT_FILE):
        print(f"[{datetime.now()}] Файл {INPUT_FILE} не найден. Ждем следующего часа...")
        return

    # 1. Читаем список VPN
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        # Убираем пробелы и пустые строки. Предполагается, что один VPN/IP — в одной строке
        vpns = [line.strip() for line in f if line.strip()]

    print(f"[{datetime.now()}] Проверяем {len(vpns)} VPN...")

    # 2. Тестируем каждый VPN
    vpn_scores = []
    for vpn in vpns:
        ping_time = get_ping(vpn)
        if ping_time < 9999:
            vpn_scores.append((vpn, ping_time))
    
    # 3. Сортируем по возрастанию пинга (меньше — лучше) и берем топ-10
    vpn_scores.sort(key=lambda x: x[1])
    top_10 = [vpn for vpn, ping in vpn_scores[:10]]

    # Если живых VPN меньше 10, запишет сколько есть
    if top_10:
        # 4. Объединяем их в одну строку через запятую (или пробел)
        result_line = ", ".join(top_10)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Записываем в файл результатов (дописываем в конец 'a')
        with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {result_line}\n")
            
        print(f"[{datetime.now()}] Топ-10 успешно записаны в {OUTPUT_FILE}")
    else:
        print(f"[{datetime.now()}] Ни один VPN не ответил.")

# Главный цикл, который работает постоянно
if __name__ == "__main__":
    print("Скрипт запущен и будет проверять VPN каждые 60 минут.")
    while True:
        select_best_vpns()
        # Засыпаем на 1 час (3600 секунд)
        time.sleep(3600)