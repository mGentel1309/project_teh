import importlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = ROOT_DIR / "list" / "listnow.txt"
OUTPUT_FILE = ROOT_DIR / "list" / "bestvpns.txt"
XRAY_PATH = ROOT_DIR / "xray"
LOCAL_PORT = 10808


def extract_host(line):
    """Возвращает хост из строки вида vless://..., ss://..., hysteria2://... или IP."""
    value = line.strip()
    if not value or value.startswith("#"):
        return None

    try:
        parsed = urlsplit(value)
        if parsed.hostname:
            return parsed.hostname
    except ValueError:
        pass

    match = re.search(r"@([^:/?#\s]+)", value)
    if match:
        return match.group(1)

    match = re.search(r"(?://)?([^:/?#\s]+)(?::\d+)?", value)
    if match:
        return match.group(1)

    return None


def get_ping(host):
    """Проверяет пинг до хоста через системный ping."""
    if not host:
        return 9999

    param = "-n" if os.name == "nt" else "-c"
    timeout_flag = "-w" if os.name == "nt" else "-W"
    command = ["ping", param, "1", timeout_flag, "2000", host]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            output = (result.stdout or "") + (result.stderr or "")
            if os.name == "nt":
                match = re.search(r"Average = (\d+(?:\.\d+)?)ms", output, re.IGNORECASE)
            else:
                match = re.search(r"time=(\d+(?:\.\d+)?) ms", output, re.IGNORECASE)
            if match:
                return float(match.group(1))
    except (OSError, subprocess.TimeoutExpired):
        pass

    return 9999


def parse_vless_url(vless_url):
    """Парсит vless:// URL в словарь с параметрами для Xray."""
    if not vless_url or not vless_url.startswith("vless://"):
        raise ValueError("Передана не vless-ссылка")

    parsed = urlsplit(vless_url)
    query = parse_qs(parsed.query)
    query = {key: value[0] for key, value in query.items()}

    return {
        "address": parsed.hostname,
        "port": parsed.port or 443,
        "id": parsed.username,
        "flow": query.get("flow", ""),
        "encryption": query.get("encryption", "none"),
        "security": query.get("security", "reality" if "pbk" in query else "none"),
        "sni": query.get("sni", parsed.hostname),
        "public_key": query.get("pbk", ""),
        "short_id": query.get("sid", ""),
        "fingerprint": query.get("fp", "chrome"),
        "network": query.get("type", "tcp"),
        "path": query.get("path", ""),
        "host": query.get("host", ""),
        "service_name": query.get("serviceName", ""),
    }


def generate_xray_config(vless_url, config_path="temp_config.json"):
    """Генерирует временный конфиг Xray из vless-ссылки."""
    config_data = parse_vless_url(vless_url)

    stream_settings = {
        "network": config_data["network"],
        "security": config_data["security"],
    }

    if config_data["security"] == "reality":
        stream_settings["realitySettings"] = {
            "show": False,
            "serverName": config_data["sni"],
            "publicKey": config_data["public_key"],
            "shortId": config_data["short_id"],
            "fingerprint": config_data["fingerprint"],
        }
    elif config_data["security"] == "tls":
        stream_settings["tlsSettings"] = {
            "serverName": config_data["sni"],
            "fingerprint": config_data["fingerprint"],
        }

    if config_data["network"] == "ws":
        ws_settings = {"path": config_data["path"] or "/"}
        if config_data["host"]:
            ws_settings["headers"] = {"Host": config_data["host"]}
        stream_settings["wsSettings"] = ws_settings
    elif config_data["network"] == "grpc":
        stream_settings["grpcSettings"] = {"serviceName": config_data["service_name"]}

    config = {
        "inbounds": [{
            "port": LOCAL_PORT,
            "listen": "127.0.0.1",
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
        }],
        "outbounds": [{
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": config_data["address"],
                    "port": config_data["port"],
                    "users": [{
                        "id": config_data["id"],
                        "encryption": config_data["encryption"],
                        "flow": config_data["flow"] or "",
                    }],
                }]
            },
            "streamSettings": stream_settings,
        }],
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    return config_path


def check_vless_ping(vless_url, xray_path="./xray", local_port=LOCAL_PORT):
    """Запускает Xray с данным VLESS, делает HTTP запрос и возвращает RTT в ms."""
    xray_path = Path(xray_path)
    if not xray_path.exists():
        raise FileNotFoundError(
            f"Xray не найден: {xray_path}. Скачайте бинарник Xray в корень проекта или передайте путь: "
            "python3 scripts/optitmize.py 'vless://...' /path/to/xray"
        )

    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError as exc:
        raise RuntimeError("Библиотека requests не установлена. Установите: pip install requests") from exc

    config_path = generate_xray_config(vless_url, "temp_config.json")
    process = subprocess.Popen(
        [str(xray_path), "run", "-c", config_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(1)
        proxies = {
            "http": f"socks5h://127.0.0.1:{local_port}",
            "https": f"socks5h://127.0.0.1:{local_port}",
        }

        start_time = time.time()
        response = requests.get("https://httpbin.org", proxies=proxies, timeout=5)
        end_time = time.time()

        if response.status_code == 200:
            return int((end_time - start_time) * 1000)
        return None
    except requests.exceptions.RequestException:
        return None
    finally:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            process.kill()


def select_best_vpns(xray_path=None):
    if not INPUT_FILE.exists():
        print(f"[{datetime.now()}] Файл {INPUT_FILE} не найден.")
        return

    xray_binary = Path(xray_path) if xray_path else XRAY_PATH
    if not xray_binary.exists():
        print(
            f"[{datetime.now()}] Xray не найден: {xray_binary}. "
            "Скачайте бинарник Xray в корень проекта или передайте путь: "
            "python3 scripts/optitmize.py 'vless://...' /path/to/xray"
        )
        return

    vpn_scores = []
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if not value.startswith("vless://"):
                continue

            try:
                ping_time = check_vless_ping(value, str(xray_binary))
            except Exception as exc:
                print(f"[{datetime.now()}] Ошибка проверки {value}: {exc}")
                continue

            if ping_time is not None:
                vpn_scores.append((value, ping_time))
                print(f"[{datetime.now()}] {value} - RTT: {ping_time} ms")

    if not vpn_scores:
        print(f"[{datetime.now()}] В файле {INPUT_FILE} нет живых vless-серверов после проверки через Xray.")
        return

    print(f"[{datetime.now()}] Проверяем {len(vpn_scores)} vless-серверов через Xray...")

    vpn_scores.sort(key=lambda x: x[1])
    top_10 = vpn_scores[:10]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for item in top_10:
            f.write(f"{item[0]}\n")

    print(f"[{datetime.now()}] Записано {len(top_10)} лучших vless-серверов в {OUTPUT_FILE}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1].startswith("vless://"):
            vless_url = sys.argv[1]
            xray_binary = sys.argv[2] if len(sys.argv) > 2 else str(XRAY_PATH)
            try:
                ping_ms = check_vless_ping(vless_url, xray_binary)
                if ping_ms is None:
                    print("❌ Проверка не удалась: сервер не отвечает или Xray не запустился.")
                else:
                    print(f"✅ RTT: {ping_ms} ms")
            except Exception as exc:
                print(f"❌ Ошибка: {exc}")
        else:
            print("Использование: python3 scripts/optitmize.py 'vless://...' [path/to/xray]")
    else:
        print("Скрипт запускается и выбирает 10 самых быстрых vless-серверов через Xray из listnow.txt.")
        select_best_vpns()