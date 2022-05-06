#!/usr/bin/env python3

"""Simple HTTP Server With Upload.

This module builds on http.server by implementing the standard GET
and HEAD requests in a fairly straightforward manner.

"""

__version__ = "0.1"
__all__ = ["SimpleHTTPRequestHandler"]
__author__ = [{"bones7456": ["http://li2z.cn/", "https://github.com/bones7456/bones7456/blob/master/SimpleHTTPServerWithUpload.py"]},
              {"UniIsland": "https://gist.github.com/UniIsland/3346170"},
              {"Tallguy297": "https://github.com/Tallguy297/SimpleHTTPServerWithUpload"},
              {"sgrontflix": "https://github.com/sgrontflix/simplehttpserverwithupload"},
              {"wonjohnchoi": "https://github.com/wonjohnchoi/Simple-Python-File-Server-With-Browse-Upload-and-Authentication"},
              {"xinghaixu": "https://github.com/xinghaixu/web_server/blob/master/SimpleHTTPServerWithUpload.py"},
              {"cpdef": "https://gist.github.com/cpdef/9f4fa956ff41ca8b9902c4b329596acc"}]

import datetime
import email.utils
import shutil
import mimetypes
import os
import sys
import base64
import time
import posixpath
import http.server
import urllib.request, urllib.parse, urllib.error
import html
import re
import socketserver
import logging
import threading
import traceback

from http import HTTPStatus
from io import BytesIO

import settings

# http.server need the shell,  if terminal closed, then python program terminated.
# another solution: nohup python server_sync.py &
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

OK, NG, SUCCESS, FAIL = 0, 1, "success", "fail"

logger = settings.new_log_handler("server.log", logging.INFO, True)

def fbytes(size):
   """Return the given bytes as a human friendly KB, MB, GB, or TB string"""
   B = float(size)
   KB = float(1024)
   MB = float(KB ** 2) # 1,048,576
   GB = float(KB ** 3) # 1,073,741,824
   TB = float(KB ** 4) # 1,099,511,627,776

   if B < KB:
      return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
   elif KB <= B < MB:
      return '{0:.2f} KB'.format(B/KB)
   elif MB <= B < GB:
      return '{0:.2f} MB'.format(B/MB)
   elif GB <= B < TB:
      return '{0:.2f} GB'.format(B/GB)
   elif TB <= B:
      return '{0:.2f} TB'.format(B/TB)

class SimpleHTTPRequestHandler(http.server.BaseHTTPRequestHandler):

    """Simple HTTP request handler with GET/HEAD/POST commands.

    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method. And can reveive file uploaded
    by client.

    The GET/HEAD/POST requests are identical except that the HEAD
    request omits the actual contents of the file.
    """

    server_version = "SimpleHTTPWithUpload/" + __version__

    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = os.getcwd()
        self.directory = directory
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Serve a GET request."""
        if not self.try_authenticate():
            # time.sleep(10)
            return

        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()

    def send_head(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers.

        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.

        """
        if not self.try_authenticate():
            return
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            parts = urllib.parse.urlsplit(self.path)
            if not parts.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] + '/',
                             parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header("Location", new_url)
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        # check for trailing "/" which should return 404. See Issue17324
        # The test for this was added in test_httpserver.py
        # However, some OS platforms accept a trailingSlash as a filename
        # See discussion on python-dev and Issue34711 regarding
        # parseing and rejection of filenames with a trailing slash
        if path.endswith("/"):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            # Use browser cache if possible
            if ("If-Modified-Since" in self.headers
                    and "If-None-Match" not in self.headers):
                # compare If-Modified-Since and time of last file modification
                try:
                    ims = email.utils.parsedate_to_datetime(
                        self.headers["If-Modified-Since"])
                except (TypeError, IndexError, OverflowError, ValueError):
                    # ignore ill-formed values
                    pass
                else:
                    if ims.tzinfo is None:
                        # obsolete format with no timezone, cf.
                        # https://tools.ietf.org/html/rfc7231#section-7.1.1.1
                        ims = ims.replace(tzinfo=datetime.timezone.utc)
                    if ims.tzinfo is datetime.timezone.utc:
                        # compare to UTC datetime of last modification
                        last_modif = datetime.datetime.fromtimestamp(
                            fs.st_mtime, datetime.timezone.utc)
                        # remove microseconds, like in If-Modified-Since
                        last_modif = last_modif.replace(microsecond=0)

                        if last_modif <= ims:
                            self.send_response(HTTPStatus.NOT_MODIFIED)
                            self.end_headers()
                            f.close()
                            return None

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified",
                self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            f.close()
            raise

    def do_POST(self):
        """Serve a POST request."""
        if not self.try_authenticate():
            # time.sleep(10)
            return

        path, param = self.parse_param(self.path)
        ok, info = self.deal_post_data(path, param)
        f = BytesIO()
        res = '{"msg": "%s", "status": %d}' % (info, ok)
        logger.info(res)
        f.write(res.encode())

        length = f.tell()
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def parse_param(self, data):
        d = data.split("?", 1)
        param = dict()
        path = d[0]
        if len(d) < 2:
            return path, param

        params = d[1].split("&")
        for p in params:
            kv = p.split("=")
            if len(kv) != 2 or kv[1] == '':
                continue
            _key = kv[0]
            _value = kv[1]
            if _key == "is_dir":
                _value = True if _value == "1" else False
            if _key == "mode":
                _value = int(_value)
            param[kv[0]] = _value

        logger.info(param)
        return path, param

    def deal_post_data(self, path, param):
        action = param.get("action", None)
        # from web
        if not action:
            path = self.translate_path(path)
            return self.save_file(path)
        # from watchdog
        if action in ["created", "modified", "deleted", "moved"]:
            func = "deal_" + action
            method = getattr(self, func)
            try:
                return method(path, param)
            except Exception as e:
                msg = "error occurs:%s check the server please" % e
                logger.error(msg)
                return NG, msg
        msg = "action not define"
        logger.info(msg)
        return NG, msg

    def deal_moved(self, path, param):
        src = param.get("src")
        dest = param.get("dest")
        if not src or not dest:
            logger.info("param error: move action require src and dest")
            return NG, "param error"

        if os.path.exists(src):
            dest_path = os.path.dirname(dest)
            if not os.path.exists(dest_path):
                try:
                    os.makedirs(dest_path, exist_ok=True)
                except Exception as e:
                    logger.error(e)
                    return NG, "No permission"
            shutil.move(src, dest)

        return OK, SUCCESS

    def deal_created(self, path, param):
        is_dir = param.get("is_dir", False)
        file_name = param.get("file_name")
        # create the dir when there is a file created
        if is_dir:
            return OK, SUCCESS

        return self.save_file(path, file_name)

    def deal_deleted(self, path, param):
        is_dir = param.get("is_dir", False)
        if is_dir:
            if os.path.exists(path):
                shutil.rmtree(path)
        else:
            file_name = param.get("file_name")
            file = os.path.join(path, file_name)
            if os.path.exists(path):
                os.remove(file)

        return OK, SUCCESS

    def deal_modified(self, path, param):
        # default 644
        mode = param.get("mode", 420)
        is_dir = param.get("is_dir", False)
        file_name = param.get("file_name")
        file = os.path.join(path, file_name)
        status, msg = self.save_file(path, file_name)
        target = path if is_dir else file
        os.chmod(target, mode)
        return status, msg

    def save_file(self, path, file_name=None):
        content_type = self.headers['content-type']
        if not content_type:
            msg = "Content-Type header doesn't contain boundary"
            logger.warning(msg)
            return NG, msg
        boundary = content_type.split("=")[1].encode()
        remainbytes = int(self.headers['content-length'])
        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            msg = "Content NOT begin with boundary"
            logger.warning(msg)
            return NG, msg
        if not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                logger.error(e)
                return NG, "No permission"

        while remainbytes > 0:
            line = self.rfile.readline()
            remainbytes -= len(line)
            if not file_name:
                fn = re.findall(r'Content-Disposition.*name="file"; filename="([^\/]*)"', line.decode())
                if not fn:
                    msg = "Can't find out file name..."
                    logger.error(msg)
                    return NG, msg
                file_name = fn[0]
            file = os.path.join(path, file_name)
            if not os.path.abspath(file).startswith(os.path.abspath(path)) \
                    or file_name == os.path.basename(__file__) \
                    or file_name == "__init__.py":
                logger.error("No permission")
                return NG, "No permission"

            line = self.rfile.readline()
            remainbytes -= len(line)
            # from web
            if b"Content-Type" in line:
                line = self.rfile.readline()
                remainbytes -= len(line)
            try:
                out = open(file, 'wb')
            except IOError as e:
                logger.error(e)
                return NG, "No permission"
            else:
                with out:
                    preline = self.rfile.readline()
                    remainbytes -= len(preline)
                    while remainbytes > 0:
                        line = self.rfile.readline()
                        remainbytes -= len(line)
                        if boundary in line:
                            preline = preline[0:-1]
                            if preline.endswith(b'\r'):
                                preline = preline[0:-1]
                            out.write(preline)
                            break
                        else:
                            out.write(preline)
                            preline = line
        return OK, SUCCESS

    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        f = BytesIO()
        try:
            diaplay_path = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            diaplay_path = urllib.parse.unquote(path)
        diaplay_path = html.escape(diaplay_path, quote=False)
        enc = sys.getfilesystemencoding()
        f.write(b'<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write(("<html>\n<title>Directory listing for %s</title>\n" % diaplay_path).encode())
        f.write(("<body>\n<h2>Directory listing for %s</h2>\n" % diaplay_path).encode())
        f.write(b"<hr>\n")
        f.write(b"<form ENCTYPE=\"multipart/form-data\" method=\"post\">")
        f.write(b"<input name=\"file\" type=\"file\" multiple/>")
        f.write(b"<input type=\"submit\" value=\"upload\"/></form>\n")
        f.write(b"<hr>\n")
        f.write(b'<table>\n')
        f.write(b'<tr><td><img src="data:image/gif;base64,R0lGODlhGAAYAMIAAP///7+/v7u7u1ZWVTc3NwAAAAAAAAAAACH+RFRoaXMgaWNvbiBpcyBpbiB0aGUgcHVibGljIGRvbWFpbi4gMTk5NSBLZXZpbiBIdWdoZXMsIGtldmluaEBlaXQuY29tACH5BAEAAAEALAAAAAAYABgAAANKGLrc/jBKNgIhM4rLcaZWd33KJnJkdaKZuXqTugYFeSpFTVpLnj86oM/n+DWGyCAuyUQymlDiMtrsUavP6xCizUB3NCW4Ny6bJwkAOw==" alt="[PARENTDIR]" width="24" height="24"></td><td><a href="../" >Parent Directory</a></td></tr>\n')
        for name in list:
            dirimage = 'data:image/gif;base64,R0lGODlhGAAYAMIAAP///7+/v7u7u1ZWVTc3NwAAAAAAAAAAACH+RFRoaXMgaWNvbiBpcyBpbiB0aGUgcHVibGljIGRvbWFpbi4gMTk5NSBLZXZpbiBIdWdoZXMsIGtldmluaEBlaXQuY29tACH5BAEAAAEALAAAAAAYABgAAANdGLrc/jAuQaulQwYBuv9cFnFfSYoPWXoq2qgrALsTYN+4QOg6veFAG2FIdMCCNgvBiAxWlq8mUseUBqGMoxWArW1xXYXWGv59b+WxNH1GV9vsNvd9jsMhxLw+70gAADs='
            fullname = os.path.join(path, name)
            displayname = linkname = name
            fsize = fbytes(os.path.getsize(fullname))
            created_date = time.ctime(os.path.getctime(fullname))
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                dirimage = 'data:image/png;base64,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'
                displayname = name + "/"
                linkname = name + "/"
                fsize = ''
                created_date = ''
            if os.path.islink(fullname):
                dirimage = 'data:image/gif;base64,R0lGODlhGAAYAPf/AJaWlpqampubm5ycnJ2dnZ6enp+fn6CgoKGhoaKioqOjo6SkpKWlpaampqioqKmpqaqqqqurq6ysrK2tra6urq+vr7CwsLGxsbKysrOzs7S0tLW1tba2tre3t7i4uLm5ubq6uru7u7y8vL29vb6+vr+/v8LCwsPDw8bGxtDQ0NTU1NXV1dbW1tfX19jY2Nra2tzc3N3d3eDg4OHh4eLi4uPj4+Tk5OXl5efn5+np6erq6uvr6+zs7O7u7u/v7/Dw8PHx8fLy8vPz8/T09PX19fb29vf39/j4+Pr6+vv7+/39/f7+/v///wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwAAAAAGAAYAAAI/wCZCBxIsKDBgwgLrsigwUXChEVGYNBwIYKIJA8LFunwocKGDA8ieMg4kAiHDxRmCGyhIAEKkhtR2iCYYYEAkiNQ3ijYIQGAjDkuVFBJsIcBAhcyttCgoSCQBQcUFMn44gIFEiwE/oAqIAfJIREeQLDAZIeCAwO8IuQRowYSIxQgBFhAoQBatQaFiLCQoQIFCxEMREUwoAEPhEA0dMQwQSwCIEFYpKCR8IfiCjWYgJCr4AhJyx13CFRhQYECGBmRcKwgmmAEBCsyltBQQUfBGwUG4MjoYMOIgjsSIJBAskGGEAR3IEhw4AdJExIeyBCIY/kBHySZLNEwgcGGDQYQNBbPLpAIBgULEhB4AIQ8wRMFBIhQ4j4gADs='
                displayname = name + "@"
            if name.endswith(('.bmp','.gif','.jpg','.png')):
                dirimage = name
            if name.endswith(('.avi','.mpg')):
                dirimage = 'data:image/gif;base64,R0lGODlhGAAYAMIAAP///7+/v7u7u1ZWVTc3NwAAAAAAAAAAACH+RFRoaXMgaWNvbiBpcyBpbiB0aGUgcHVibGljIGRvbWFpbi4gMTk5NSBLZXZpbiBIdWdoZXMsIGtldmluaEBlaXQuY29tACH5BAEAAAEALAAAAAAYABgAAANvGLrc/jAuQqu99BEh8OXE4GzdYJ4mQIZjNXAwp7oj+MbyKjY6ntstyg03E9ZKPoEKyLMll6UgAUCtVi07xspTYWptqBOUxXM9scfQ2Ttx+sbZifmNbiLpbEUPHy1TrIB1Xx1cFHkBW4VODmGNjQ4JADs='
            if name.endswith(('.idx','.srt','.sub')):
                dirimage = 'data:image/gif;base64,R0lGODlhGAAYAPf/AAAbDiAfDSoqHjQlADs+J3sxJ0BALERHMk5LN1pSPUZHRk9NQU1OR05ZUFBRRFVXTVdYTVtVQFlVRFtbSF5bTVZWUltbUFlZVFtcVlxdWl5eWl1gWmBiV2FiXWNhXGRjXWlpYmtqZ2xtZmxsaG5ubHJva3Jzb3J0bHN0b3Z5dHd8eXh4dX18dXx/dnt8e31+eahMP4JdWIdnZox4cpVoYKJkXrxqablwcNA6Otg7O/8AAPwHB/0GBvgODvsMDPMbG/ceHvkSEuYqKvYqKvU2NvM6OvQ6OsFQUNVbW8N4eNd0duNeXu9aWvFUVOVqau1jY+1mZu5mZuh5eYSFgIWGgYaFgIiGgYqKiY6LioyMiY2NiYyMio2OiI6OjZCSjZSQi5OSkJGUkpSVk5WVlJWVlZiZlpiZmJ6emp2dnZSko6GhnKGhoKOjoaKnoqSkpKSmpKWmpaampqqrqKurqKqrqq2sqq6urrSyrrCwsLa3tb63tbi4t7q6ur+/vsCbm96Li9iUlMqursmwr9KwsN69veSCguiMjOiOjuaQkOWVleaXmOGfn+aYmOaamuebm+adneecnOeenuiQkOWgoOWsrOasrOWxseW2tue3t+e8vOi+vsHBwcfHx8jIxs7Mx8nJyMvLy8zMy83NzM7Pzs/Pz9PR0dTU1NXV1dXW1tbW1tfX19bb29jY2NnZ2djb29ra2tvb2tvb29za2tzc3N3d3d7e3t/f3+bCwufDw+fGxuTJyejCwujHx+nHx+vPz+rT0+rU1OrX1+vX1+rY2Ojf3+Hh4eLi4uPj4+Hn5+Tk5OXl5ebm5ufn5+nn5+jo6Onp6erp6evr6+zs7PDn5/Dq6vDt7fHv7/Lu7vPu7vPv7/Dw8PHx8fLy8vPz8/Tx8fbz8/T09PX19fX39/b29vj39/j4+Pn4+Pn5+fr5+fr6+vv7+/z7+/z8/P39/f7+/v/+/v///wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwAAAAAGAAYAAAI/wDhCRxIsKDBgwgTZis00F27hAbRNSpSaSC7ZM6ePQsXjdmzZekKUpOio0lBVShjJXvYjp07gsEm/dLhqKC2aNG2LesES13BXJTg4dLBi2C7kPDSyQFTRY26c8akZbolkJGOaQTZFTO2LA8KCCA+zDFTp4aggVCCmCtYrJUxNiI4nAjh4o2HGW1CrhvCxGC5cOVqvcCgQQUWGRtanOkG75qOQwXbhWvZ7lOZMIGSsJjihY5AYTowFWRnipUtT6BGWIARY8IXPc1eXtIxrKC7cqJCjdJCIcIBAwRoaLqU6IkRHthGnwPzoEGKDBISMHDAZWAvHUTWjaa1J42NAgAELMBAMGCNwHbWekQxqA4VMkBKSokZE8AKtHLpjuHxo0OSQXfuLKJIOHdc0IECFaxgQivpxHGDDpYc9McS5oBTAhxUbNHFFX2I4Q4fR+iwi0GPCCGLK6rYgQYJWZDhBil7cMMJDjpAAg85L8ETCRDVqAONMuGMA0446rDjEzzi5KDDD4j48g48huxAyCqtODNZOeWcM85DAxEDzDcE+YDEK5u0EostbZ2SyizsQASPE4PAo4466TxVZzptuqmLN266GRAAOw=='
            if name.endswith('.iso'):
                dirimage = 'data:image/png;base64,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'
                # Note: a link to a directory displays with @ and links with /
            f.write(('<tr><td><img src="%s" width="24" height="24"></td><td><a href="%s">%s</a></td><td style="text-align:right; font-weight: bold; color:#FF0000">%s</td><td style="text-align:right; font-weight: bold;">%s</td></tr>\n'
                    % ( dirimage, urllib.parse.quote(linkname), html.escape(displayname) , fsize , created_date )).encode(enc))
        f.write(b"</table><hr>\n</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.

        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)

        """
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = self.directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.

        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).

        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.

        """
        shutil.copyfileobj(source, outputfile)

    def guess_type(self, path):
        """Guess the type of a file.

        Argument is a PATH (a filename).

        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.

        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.

        """

        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream', # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        })

    def is_authenticated(self):
        global key
        auth_header = self.headers['Authorization']
        if auth_header != None:
            auth_header = auth_header.encode("utf-8")
        return auth_header and auth_header == b'Basic ' + key

    def do_AUTHHEAD(self):
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header('WWW-Authenticate', 'Basic realm=\"Test\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def try_authenticate(self):
        if not self.is_authenticated():
            self.do_AUTHHEAD()
            logger.info('not authenticated')
            self.wfile.write(b'not authenticated')
            self.close_connection = True
            return False
        return True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


class MyServer(threading.Thread):
    def __init__(self, bind, port, ssl_cert):
        super().__init__()
        # self.server = http.server.ThreadingHTTPServer((bind, port), SimpleHTTPRequestHandler)
        self.server = ThreadedTCPServer((bind, port), SimpleHTTPRequestHandler)
        self.bind = bind
        self.port = port
        self.ssl_cert = ssl_cert

    def run(self):
        if self.ssl_cert:
            import ssl
            self.server.socket = ssl.wrap_socket(httpd.socket, certfile=args.certfile, server_side=True)
        logger.info("Serving HTTP on {host} port {port} (http{s}://{host}:{port}/) ...".format(
            host=self.bind, port=self.port, s="" if not self.ssl_cert else "s"))
        server_thread = threading.Thread(target=self.server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        server_thread.join()

    def stop(self):
        self.server.shutdown()

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', default=settings.username, help='auth username')
    parser.add_argument('--passwd', '-P', default=settings.password, help='auth password')
    parser.add_argument('--bind', '-b', default=settings.host, metavar='ADDRESS',
                        help='Specify alternate bind address '
                             '[default: all interfaces]')
    parser.add_argument('--port', '-p', action='store', default=settings.port, type=int,
                        nargs='?', help='Specify alternate port [default: 8000]')
    parser.add_argument('--directory', '-d', default=os.getcwd(),
                        help='Specify alternative directory '
                        '[default:current directory]')
    parser.add_argument('--certfile', '-s', default='', metavar='SSL',
                        help='ssl cert')

    args = parser.parse_args()
    key = base64.b64encode((args.user + ":" + args.passwd).encode("utf-8"))

    httpd = MyServer(args.bind, args.port, args.certfile)
    try:
        httpd.run()
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received, exiting.")
    except Exception as e:
        logger.error("catch exception: %s", traceback.format_exc())
    finally:
        httpd.stop()
        sys.exit(0)