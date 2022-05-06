# server
import logging

host = '0.0.0.0'
port = 8888
username = '1'
password = '1'

remote_host = "http://127.0.0.1:{}".format(port)
remote_base_path = "/home/"

# .+数字结尾的
ignore_regular = [".*/[.git|.idea|log]/.*", "^.*~$", ".*\.sw[p|o|n|m|l]$", "^.*\.\d+$"]

# ignore files when event_type trigger
# keys: ["modified", "created", "deleted", "moved"]
ignore_with_event_type = {
    "deleted": [".*\.doNotDeletedFileType$"]
}

# client
retry_times = 2
timeout = 3
# local_path: remote_path
sync_conf = {
    "example1_abs_path":{
    "remote_path": "~/test",
        "switch": True,  # only watch when True
        "match": [".*"],  # reg for watch files
        "ignore": ignore_regular,  # ignore reg
        "ignore_hidden": True,  # watch hidden files
        "ignore_with_event_type": ignore_with_event_type,
    },
}


def new_log_handler(log, level, stdout=False):
    logger = logging.getLogger()  # root logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(funcName)s[line:%(lineno)d] - %(levelname)s: %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')

    file_handler = logging.FileHandler(log)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if stdout:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger
