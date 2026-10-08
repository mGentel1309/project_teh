import subprocess
import time
import os


#скачали с гита текущую версию
def download():
    try:
        subprocess.run(
            [
                "curl",
                "-L",
                "-o",
                "/Users/mgentel/Code/project_teh/list/listnow.txt",
                "https://raw.githubusercontent.com/FLAT447/v2ray-lists/refs/heads/main/BLACK_FULL.txt",
            ],
            check=True
        )
        subprocess.run(
             [
                  "git",
                  "add",
                  ".",


             ]
             
             
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Обновили список в " + time.strftime("%Y-%m-%d %H:%M:%S"),
            ],
            check=True
        )
        subprocess.run(
            [
                "git",
                "push",
            ],
            check=True
        )


    except subprocess.CalledProcessError as error:
        return error
    return None





#занесли в логи
def make_log(error):
    if error is None:
        

        with open("/Users/mgentel/Code/project_teh/logs/log.txt", "a") as f:
            f.write("Скачали с гита текущую версию " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    else:
        with open("/Users/mgentel/Code/project_teh/logs/log.txt", "a") as f:
                    f.write("Не удалось скачать в " + time.strftime("%Y-%m-%d %H:%M:%S") + " По причине " + str(error) + "\n")
    



def main():
    error = download()
    make_log(error)


if __name__ == "__main__":
    main()
