import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import asyncio
from db_io import *
from config import database_path
from db_updates import reload_maps, reload_requirements, update_files_provided


class OnMyWatch:
    # Set the directory on watch

    def __init__(self):
        self.observer = Observer()

    def run(self):
        event_handler = Handler()
        self.observer.schedule(event_handler, watchDirectory, recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("Observer Stopped")

        self.observer.join()


async def create_handler(event):
    conn = create_connection(database_path)

    now = str(datetime.now().time())
    print(now)  # '2017-12-26'
    if event.is_directory:
        print(f"+dir {event.src_path}")
        with open(log_path, "a+") as f:
            f.write(f"+dir {event.src_path} {now}\n")
    else:
        print(f"+file {event.src_path}")
        with open(log_path, "a+") as f:
            f.write(f"+file {event.src_path} {now}\n")
        if event.src_path.endswith(".bsp") and event.src_path.startswith(watchDirectory+"maps/"):
            print(event.src_path)
            map_path = event.src_path.replace(watchDirectory+"maps/", "").replace(".bsp", "")
            print(map_path)
            reload_maps(conn)
            await reload_requirements(conn, None, mapname=map_path)
            print("done reloading")
        else:
            await update_files_provided(conn)
        conn.commit()


async def delete_handler(event):
    conn = create_connection(database_path)

    now = str(datetime.now().time())
    print(now)  # '2017-12-26'
    if event.is_directory:
        print(f"-dir {event.src_path}")
        with open(log_path, "a+") as f:
            f.write(f"-dir {event.src_path} {now}\n")
    else:
        print(f"-file {event.src_path}")
        with open(log_path, "a+") as f:
            f.write(f"-file {event.src_path} {now}\n")
        if event.src_path.endswith(".bsp") and event.src_path.startswith(watchDirectory+"maps/"):
            print(event.src_path)
            map_path = event.src_path.replace(watchDirectory+"maps/", "")
            print(map_path)
            reload_maps(conn)
        else:
            await update_files_provided(conn)
        conn.commit()


class Handler(FileSystemEventHandler):
    @staticmethod
    def on_created(event):
        asyncio.run(create_handler(event))

    @staticmethod
    def on_deleted(event):
        asyncio.run(delete_handler(event))


if __name__ == '__main__':
    watchDirectory = "/var/www/html/pball/"
    log_path = "watchlog_pball.txt"  # used above

    watch = OnMyWatch()
    watch.run()
