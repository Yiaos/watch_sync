import os
import re
import stat
import time
import logging
import requests
import http
import json
import base64

from watchdog.observers import Observer
from watchdog.events import RegexMatchingEventHandler, FileModifiedEvent
from functools import wraps

import settings

logger = settings.new_log_handler("client.log", logging.INFO, True)


def catch_file_not_found(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError as e:
            logger.warning(e)
        return wrapper


class MyHandler(RegexMatchingEventHandler):
    def __init__(self, base_path, regexes=None, ignore_regexes=None,
                 ignore_directories=False, case_sensitive=False):
        super(MyHandler, self).__init__(regexes, ignore_regexes,
                                        ignore_directories, case_sensitive)
        self.base_path = base_path
        self.conf = settings.sync_conf.get(self.base_path)
        self.remote_host = settings.remote_host
        self.param = ""
        self.relat_path = ""

    def on_created(self, event):
        if event.is_directory:
            return
        return self.sync(event.event_type, event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        # dec mod
        mode = stat.S_IMODE(os.stat(event.src_path).st_mode)
        self.param += "&mode={}".format(mode)
        return self.sync(event.event_type, event.src_path)

    def on_moved(self, event):
        self.param += "&src={}&dest={}".format(event.src_path.replace(self.base_path, self.remote_path()),
                                               event.dest_path.replace(self.base_path, self.remote_path()))
        return self.sync(event.event_type, event.src_path)

    def on_deleted(self, event):
        return self.sync(event.event_type, event.src_path)

    def on_any_event(self, event):
        self.relat_path = event.src_path.split(self.base_path)[1]
        path = self.remote_path()
        if event.is_directory:
            path += self.relat_path
            file_name = ""
        else:
            file_path = self.relat_path.rsplit("/", 1)
            file_name = file_path[1]
            path += file_path[0]
        self.param = "{}?action={}&is_dir={}&file_name={}".format (
            path, event.event_type, 1 if event.is_directory else 0, file_name)

    def remote_path(self):
        return self.conf.get("remote_path")

    def sync(self, event_type, src_path):
        if self.ignore_event_file(event_type):
            logger.info("ignore file: %s, event_type: %s", src_path, event_type)
            return
        retry = 0
        while retry < settings.retry_times:
            try:
                headers = {
                    "Authorization": self.key(),
                }
                if event_type in ("modified", "created"):
                    files = {"file": open(src_path, "rb")}
                    res = requests.post(self.remote_host+self.param, files=files, headers=headers, timeout=settings.timeout)
                else:
                    res = requests.post(self.remote_host+self.param, headers=headers, timeout=settings.timeout)
                logger.info("{} {} {} retry:{}".format(src_path, event_type, res, retry))
                if res.status_code == http.HTTPStatus.OK:
                    # logger.info("{} {} {}".format(src_path, event_type, res.content.decode()))
                    if event_type == "deleted":
                        break
                    data = json.loads(res.content.decode())
                    if data.get("status") == 0 or data.get("msg") == "No permission":
                        # logger.info("{} {} {}".format(src_path, event_type, data.get("msg")))
                        break
                retry += 1
            except Exception as e:
                retry += 1
                logger.error("{} {} err:{}".format(src_path, event_type, e))

    def sync_all(self, path=None):
        base_path = path if path else self.base_path
        ignore_reg = self.conf.get("ignore")
        match_reg = self.conf.get("match")
        i_patterns = [re.compile(i_r) for i_r in ignore_reg]
        m_patterns = [re.compile(m_r) for m_r in match_reg]
        logger.info("ignore: %s, match_reg: %s", ignore_reg, match_reg)

        for root, dir, files in os.walk(base_path):
            logger.info(root)
            if self.skip(i_patterns, m_patterns, root):
                continue
            for name in files:
                if self.skip(i_patterns, m_patterns, name):
                    continue
                src_path = os.path.join(root, name)
                event = FileModifiedEvent(src_path)
                self.on_any_event(event)
                self.on_modified(event)
        logger.info("sync all done")

    def ignore_event_file(self, event_type):
        ignore_file_reg = self.conf.get("ignore_with_event_type", {}).get(event_type, [])
        if len(ignore_file_reg) > 0:
            i_patterns = [re.compile(i_r) for i_r in ignore_file_reg]
            return self.skip(i_patterns, [], self.relat_path, False)

    def skip(self, i_patterns, m_patterns, name_str, check_hidden=True):
        if check_hidden and  self.conf.get("ignore_hidden") and name_str.startswith("."):
            return True
        for i_p in i_patterns:
            if i_p.match(name_str):
                return True
        for m_p in m_patterns:
            if not m_p.match(name_str):
                return True
        return False

    def key(self):
        return b'Basic ' + base64.b64encode(("{}:{}".format(settings.username, settings.password)).encode("utf-8"))

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dirs", "-d",
                        nargs="+",
                        help="sync files immediately and begin observe\r\n"
                             "eg:python3 client.py -d abs_path_for_example1 abs_path_for_example2")
    args = parser.parse_args()
    observer = Observer()
    # add observer
    watch = settings.sync_conf
    for watch_path, conf in watch.items():
        switch = conf.get("switch")
        if switch and not watch_path.startswith("example"):
            match_reg = conf.get("match")
            ignore_reg = conf.get("ignore")
            if conf.get("ignore_hidden"):
                ignore_reg.extend(["^[.]{1}.*", ".*/[.]{1}.*"])
            event_handler = MyHandler(watch_path, match_reg, ignore_reg)
            if args.dirs:
                if watch_path.endswith("/"):
                    watch_path = watch_path[::-1].replace("/", "", 1)[::-1]
                for sync_dir in args.dirs:
                    if sync_dir.startswith(watch_path):
                        event_handler.sync_all(sync_dir)
            watcher = observer.schedule(event_handler, watch_path, recursive=True)
            logger.info("add watcher %s " % watcher)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
