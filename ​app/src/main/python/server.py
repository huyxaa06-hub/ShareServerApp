import os
import http.server
import socketserver
import urllib.parse
import html
import cgi
import http.cookies
import json
from datetime import datetime

PORT = 9999
ROOT_DIR = "/sdcard/Download/uploads"
CONFIG_FILE = "/sdcard/Download/config.txt"

# Tạo thư mục gốc nếu chưa có
if not os.path.exists(ROOT_DIR):
    os.makedirs(ROOT_DIR, exist_ok=True)

# Bộ nhớ log realtime (50 dòng gần nhất)
SERVER_LOGS = []
def addLog(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logLine = f"[{timestamp}] {msg}"
    print(logLine)
    SERVER_LOGS.append(logLine)
    if len(SERVER_LOGS) > 50:
        SERVER_LOGS.pop(0)

# Đọc/Ghi file cấu hình config.txt
def loadConfig():
    cfg = {
        "title": "nguyễn ngọc Minh",
        "password": "admin",
        "share_dir": ROOT_DIR,
        "public_folder_name": "Kho_Tai_Lieu_Chung",
        "quick_dirs": "",
        "local_domain": "nguyenngocminh.local",
        "admin_notice": "Chào mừng mọi người đến với server chia sẻ tài liệu!",
        "shared_items": "",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg

def saveConfig(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            for k, v in cfg.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        addLog(f"Lỗi lưu config: {e}")

class PythonServerHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        addLog(f"{self.client_address[0]} - - \"{self.command} {self.path}\"")

    def isLoggedIn(self):
        if "Cookie" in self.headers:
            cookie = http.cookies.SimpleCookie(self.headers["Cookie"])
            if "auth" in cookie and cookie["auth"].value == "loggedIn":
                return True
        return False

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path_str = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # 1. API Logs
        if path_str == "/api/logs":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("\n".join(SERVER_LOGS).encode("utf-8"))
            return

        # 2. Restart Server
        if path_str == "/restart_server":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            addLog("🔄 Admin đã yêu cầu khởi động lại server...")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Server dang khoi dong lai...")
            os._exit(0)

        # 3. Logout
        if path_str == "/logout":
            self.send_response(303)
            expire_cookie = http.cookies.SimpleCookie()
            expire_cookie["auth"] = ""
            expire_cookie["auth"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
            self.send_header("Set-Cookie", expire_cookie.output(header="").strip())
            self.send_header("Location", "/")
            self.end_headers()
            return

        # 4. Toggle Share
        if path_str == "/toggle_share":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            target = query_params.get("target", [""])[0]
            subDir = query_params.get("dir", [""])[0]
            if target:
                cfg = loadConfig()
                sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                if target in sharedList:
                    sharedList.remove(target)
                else:
                    sharedList.append(target)
                cfg["shared_items"] = ",".join(sharedList)
                saveConfig(cfg)
            redirect_url = f"/?dir={urllib.parse.quote(subDir)}" if subDir else "/"
            self.send_redirect(redirect_url)
            return

        # 5. Delete File/Folder
        if path_str == "/delete":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            targetName = query_params.get("target", [""])[0]
            subDir = query_params.get("dir", [""])[0]
            if targetName:
                targetPath = os.path.join(ROOT_DIR, subDir, os.path.basename(targetName))
                if os.path.exists(targetPath):
                    try:
                        if os.path.isdir(targetPath):
                            import shutil
                            shutil.rmtree(targetPath)
                        else:
                            os.remove(targetPath)
                        addLog(f"Đã xóa thành công: {targetPath}")
                    except Exception as e:
                        addLog(f"Lỗi xóa: {e}")
            redirect_url = f"/?dir={urllib.parse.quote(subDir)}" if subDir else "/"
            self.send_redirect(redirect_url)
            return

        # 6. Serve static uploads
        if path_str.startswith("/uploads/"):
            relPath = path_str[len("/uploads/"):]
            filePath = os.path.join(ROOT_DIR, urllib.parse.unquote(relPath))
            if os.path.exists(filePath) and os.path.isfile(filePath):
                cfg = loadConfig()
                sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                norm_relPath = relPath.replace("\\", "/")
                if not self.isLoggedIn() and norm_relPath not in sharedList:
                    self.send_error(403, "Forbidden")
                    return
                self.serve_file(filePath)
                return
            else:
                self.send_error(404, "File not found")
                return

        # 7. Trang chủ (Home & Render Giao diện)
        if path_str == "/":
            self.render_home_page(query_params)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path_str = parsed_path.path

        # 1. Login Handler
        if path_str == "/login":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            form_data = urllib.parse.parse_qs(post_data)
            password = form_data.get("password", [""])[0]

            cfg = loadConfig()
            cookie = http.cookies.SimpleCookie()
            if password == cfg["password"]:
                addLog("Admin đăng nhập thành công.")
                cookie["auth"] = "loggedIn"
                cookie["auth"]["path"] = "/"
            else:
                addLog("Đăng nhập Admin thất bại (sai mật khẩu).")

            self.send_response(303)
            self.send_header("Set-Cookie", cookie.output(header="").strip())
            self.send_header("Location", "/")
            self.end_headers()
            return

        # 2. Upload Handler
        if path_str == "/upload" or path_str == "/":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers.get('Content-Type'),
                }
            )

            subDir = form.getvalue("current_dir", "")
            targetDir = os.path.join(ROOT_DIR, subDir)
            if not os.path.exists(targetDir):
                os.makedirs(targetDir, exist_ok=True)

            if "file" in form:
                file_item = form["file"]
                if file_item.filename:
                    filename = os.path.basename(file_item.filename)
                    filePath = os.path.join(targetDir, filename)
                    with open(filePath, "wb") as f:
                        f.write(file_item.file.read())

                    relFilePath = os.path.join(subDir, filename).replace("\\", "/") if subDir else filename
                    cfg = loadConfig()
                    sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                    if relFilePath not in sharedList:
                        sharedList.append(relFilePath)
                        cfg["shared_items"] = ",".join(sharedList)
                        saveConfig(cfg)
                    addLog(f"Tải lên và tự động chia sẻ file: {filename}")

            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        self.send_error(404, "Not Found")

    def send_redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def serve_file(self, filePath):
        try:
            with open(filePath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Internal Server Error")

    def render_home_page(self, query_params):
        cfg = loadConfig()
        loggedIn = self.isLoggedIn()
        subDir = query_params.get("dir", [""])[0]
        targetDir = os.path.join(ROOT_DIR, subDir)

        if not os.path.exists(targetDir):
            self.send_redirect("/")
            return

        try:
            items = os.listdir(targetDir)
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(targetDir, x)), x.lower()))
        except Exception:
            items = []

        sharedItemsSet = set([x.strip() for x in cfg["shared_items"].split(",") if x.strip()])

        displayItems = items if loggedIn else [name for name in items if (os.path.join(subDir, name).replace("\\", "/") if subDir else name) in sharedItemsSet]

        template_path = "index.html"
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as tf:
                htmlTemplate = tf.read()
        else:
            htmlTemplate = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>{{TITLE}}</title></head>
            <body><h1>{{TITLE}}</h1>{{{ADMIN_NOTICE}}}{{{AUTH_BOX}}}{{{ADMIN_PANEL}}}<hr><div>{{{BREADCRUMB}}}</div><ul>{{{ITEMS_LIST}}}</ul></body></html>"""

        itemsHtmlStr = ""
        for name in displayItems:
            itemPath = os.path.join(targetDir, name)
            isDir = os.path.isdir(itemPath)
            relPath = os.path.join(subDir, name).replace("\\", "/") if subDir else name
            isShared = relPath in sharedItemsSet
            checkIcon = "✅ " if isShared else ""
            checkboxHtml = f'<input type="checkbox" class="item-checkbox" value="{relPath}" style="width: auto; margin: 0; cursor: pointer;">' if loggedIn else ""

            if isDir:
                folderIdKey = relPath.replace("/", "_").replace(".", "_")
                shareBtnText = "✅ Chia sẻ tất cả" if isShared else "📂 Chia sẻ tất cả"
                shareBtnClass = "btn-share active" if isShared else "btn-share"
                
                admin_actions = f"""
                        <a class="{shareBtnClass}" href="/toggle_share?target={urllib.parse.quote(relPath)}&dir={urllib.parse.quote(subDir)}">{shareBtnText}</a>
                        <button class="btn-rename" onclick="renameItem('{name}')">✏️ Sửa</button>
                        <a class="btn-delete" href="/delete?target={urllib.parse.quote(name)}&dir={urllib.parse.quote(subDir)}" onclick="return confirm('Xóa thư mục này?');">🗑️ Xóa</a>""" if loggedIn else ""

                itemsHtmlStr += f"""
                <li style="flex-direction: column; align-items: stretch; border-bottom: 1px solid #eee; padding: 8px 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; width: 100%;">
                        <span class="item-name">{checkboxHtml} {checkIcon}📁 <b>{name}</b></span>
                        <div class="action-buttons">
                            <button class="btn-open" onclick="toggleSubFolder('{folderIdKey}')">📂 Mở tại chỗ</button>
                            {admin_actions}
                        </div>
                    </div>
                    <div id="sub_{folderIdKey}" class="sub-tree"><ul></ul></div>
                </li>"""
            else:
                encodedFilepath = urllib.parse.quote(relPath)
                shareBtnText = "✅ Đang chia sẻ" if isShared else "📤 Chia sẻ"
                shareBtnClass = "btn-share active" if isShared else "btn-share"
                
                admin_actions = f"""
                    <a class="{shareBtnClass}" href="/toggle_share?target={urllib.parse.quote(relPath)}&dir={urllib.parse.quote(subDir)}">{shareBtnText}</a>
                    <button class="btn-rename" onclick="renameItem('{name}')">✏️ Sửa</button>
                    <a class="btn-delete" href="/delete?target={urllib.parse.quote(name)}&dir={urllib.parse.quote(subDir)}" onclick="return confirm('Xóa file này?');">🗑️ Xóa</a>""" if loggedIn else ""

                itemsHtmlStr += f"""
                <li>
                    <span class="item-name">{checkboxHtml} {checkIcon}📄 {name}</span>
                    <div class="action-buttons">
                        <a class="btn-download" href="/uploads/{encodedFilepath}" download="{name}">📥 Tải</a>
                        {admin_actions}
                    </div>
                </li>"""

        if not displayItems:
            itemsHtmlStr = '<li style="justify-content: center; color: #777; font-style: italic; padding: 15px;">Trống (Chưa có mục nào được chia sẻ).</li>'

        breadcrumbHtml = f'<a href="/">🏠 {cfg["public_folder_name"]}</a>'
        if subDir:
            parts = subDir.replace("\\", "/").split("/")
            acc = ""
            for part in parts:
                if part:
                    acc = os.path.join(acc, part)
                    breadcrumbHtml += f' / <a href="/?dir={urllib.parse.quote(acc)}">{part}</a>'

        adminPanelHtml = ""
        if loggedIn:
            adminPanelHtml = f"""
            <div class="admin-panel">
                <h3>🛠️ Bảng Điều Khiển Quản Trị & Cấu Hình Hệ Thống</h3>
                <div class="admin-grid">
                    <div class="admin-card" style="grid-column: 1 / -1;">
                        <label>💻 Server & Web Real-time Logs:</label>
                        <div id="logContainer" class="log-box">Đang tải log thời gian thực...</div>
                    </div>
                </div>
            </div>
            <form id="uploadForm" enctype="multipart/form-data" method="post" action="/">
                <p style="margin-top:0; font-weight:bold; font-size:13px;">📤 Tải file lên trực tiếp (Tự động chia sẻ lên web):</p>
                <input type="hidden" name="current_dir" value="{subDir}">
                <input id="fileInput" name="file" type="file" required>
                <input type="submit" value="Tải Lên & Chia Sẻ Ngay">
                <div id="progress-container">
                    <progress id="progressBar" value="0" max="100"></progress>
                    <div id="status">Đang chuẩn bị...</div>
                </div>
            </form>"""

        authBoxHtml = '👑 <b>Admin</b> | <button class="btn-restart-top" onclick="restartServer()">🔄 Khởi động lại</button> | <a href="/logout">Đăng xuất</a>' if loggedIn else '<a href="#" onclick="document.getElementById(\'loginForm\').style.display=\'block\'; return false;" style="background:#007bff; color:white; padding:6px 12px; border-radius:5px;">🔐 Đăng nhập Admin</a>'

        finalHtml = htmlTemplate \
            .replace("{{TITLE}}", cfg["title"]) \
            .replace("{{VIDEO_BLOCK}}", "") \
            .replace("{{AUTH_BOX}}", authBoxHtml) \
            .replace("{{LOGO_HTML}}", "📁") \
            .replace("{{ADMIN_NOTICE}}", f'<div class="notice-box"><span>📢 <b>Thông báo:</b> {cfg["admin_notice"]}</span></div>' if cfg["admin_notice"] else "") \
            .replace("{{ADMIN_PANEL}}", adminPanelHtml) \
            .replace("{{BREADCRUMB}}", breadcrumbHtml) \
            .replace("{{BATCH_SHARE_TOOLS}}", '<div style="margin-bottom: 10px; display: flex; gap: 6px;"><button type="button" class="btn-share active" onclick="toggleSelectAll(true)">☑️ Chọn tất cả</button><button class="btn-share" onclick="submitSelectedShare()">✅ Chia sẻ đã chọn</button></div>' if loggedIn else "") \
            .replace("{{ITEMS_LIST}}", itemsHtmlStr) \
            .replace("{{CURRENT_SUB_DIR}}", subDir) \
            .replace("{{CURRENT_SHORTCUTS}}", cfg["quick_dirs"]) \
            .replace("{{ROOT_DIR}}", ROOT_DIR) \
            .replace("{{PUBLIC_NAME}}", cfg["public_folder_name"]) \
            .replace("{{DOMAIN}}", cfg["local_domain"])

        content_bytes = finalHtml.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content_bytes)))
        self.end_headers()
        self.wfile.write(content_bytes)

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), PythonServerHandler) as httpd:
        addLog(f"Python Server ready at http://localhost:{PORT}")
        httpd.serve_forever()
import os
import http.server
import socketserver
import urllib.parse
import html
import cgi
import http.cookies
import json
from datetime import datetime

PORT = 9999
ROOT_DIR = "/sdcard/Download/uploads"
CONFIG_FILE = "/sdcard/Download/config.txt"

# Tạo thư mục gốc nếu chưa có
if not os.path.exists(ROOT_DIR):
    os.makedirs(ROOT_DIR, exist_ok=True)

# Bộ nhớ log realtime (50 dòng gần nhất)
SERVER_LOGS = []
def addLog(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logLine = f"[{timestamp}] {msg}"
    print(logLine)
    SERVER_LOGS.append(logLine)
    if len(SERVER_LOGS) > 50:
        SERVER_LOGS.pop(0)

# Đọc/Ghi file cấu hình config.txt
def loadConfig():
    cfg = {
        "title": "nguyễn ngọc Minh",
        "password": "admin",
        "share_dir": ROOT_DIR,
        "public_folder_name": "Kho_Tai_Lieu_Chung",
        "quick_dirs": "",
        "local_domain": "nguyenngocminh.local",
        "admin_notice": "Chào mừng mọi người đến với server chia sẻ tài liệu!",
        "shared_items": "",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg

def saveConfig(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            for k, v in cfg.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        addLog(f"Lỗi lưu config: {e}")

class PythonServerHandler(http.server.BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        addLog(f"{self.client_address[0]} - - \"{self.command} {self.path}\"")

    def isLoggedIn(self):
        if "Cookie" in self.headers:
            cookie = http.cookies.SimpleCookie(self.headers["Cookie"])
            if "auth" in cookie and cookie["auth"].value == "loggedIn":
                return True
        return False

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path_str = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)

        # 1. API Logs
        if path_str == "/api/logs":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("\n".join(SERVER_LOGS).encode("utf-8"))
            return

        # 2. Restart Server
        if path_str == "/restart_server":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            addLog("🔄 Admin đã yêu cầu khởi động lại server...")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Server dang khoi dong lai...")
            os._exit(0)

        # 3. Logout
        if path_str == "/logout":
            self.send_response(303)
            expire_cookie = http.cookies.SimpleCookie()
            expire_cookie["auth"] = ""
            expire_cookie["auth"]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
            self.send_header("Set-Cookie", expire_cookie.output(header="").strip())
            self.send_header("Location", "/")
            self.end_headers()
            return

        # 4. Toggle Share
        if path_str == "/toggle_share":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            target = query_params.get("target", [""])[0]
            subDir = query_params.get("dir", [""])[0]
            if target:
                cfg = loadConfig()
                sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                if target in sharedList:
                    sharedList.remove(target)
                else:
                    sharedList.append(target)
                cfg["shared_items"] = ",".join(sharedList)
                saveConfig(cfg)
            redirect_url = f"/?dir={urllib.parse.quote(subDir)}" if subDir else "/"
            self.send_redirect(redirect_url)
            return

        # 5. Delete File/Folder
        if path_str == "/delete":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return
            targetName = query_params.get("target", [""])[0]
            subDir = query_params.get("dir", [""])[0]
            if targetName:
                targetPath = os.path.join(ROOT_DIR, subDir, os.path.basename(targetName))
                if os.path.exists(targetPath):
                    try:
                        if os.path.isdir(targetPath):
                            import shutil
                            shutil.rmtree(targetPath)
                        else:
                            os.remove(targetPath)
                        addLog(f"Đã xóa thành công: {targetPath}")
                    except Exception as e:
                        addLog(f"Lỗi xóa: {e}")
            redirect_url = f"/?dir={urllib.parse.quote(subDir)}" if subDir else "/"
            self.send_redirect(redirect_url)
            return

        # 6. Serve static uploads
        if path_str.startswith("/uploads/"):
            relPath = path_str[len("/uploads/"):]
            filePath = os.path.join(ROOT_DIR, urllib.parse.unquote(relPath))
            if os.path.exists(filePath) and os.path.isfile(filePath):
                cfg = loadConfig()
                sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                norm_relPath = relPath.replace("\\", "/")
                if not self.isLoggedIn() and norm_relPath not in sharedList:
                    self.send_error(403, "Forbidden")
                    return
                self.serve_file(filePath)
                return
            else:
                self.send_error(404, "File not found")
                return

        # 7. Trang chủ (Home & Render Giao diện)
        if path_str == "/":
            self.render_home_page(query_params)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path_str = parsed_path.path

        # 1. Login Handler
        if path_str == "/login":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            form_data = urllib.parse.parse_qs(post_data)
            password = form_data.get("password", [""])[0]

            cfg = loadConfig()
            cookie = http.cookies.SimpleCookie()
            if password == cfg["password"]:
                addLog("Admin đăng nhập thành công.")
                cookie["auth"] = "loggedIn"
                cookie["auth"]["path"] = "/"
            else:
                addLog("Đăng nhập Admin thất bại (sai mật khẩu).")

            self.send_response(303)
            self.send_header("Set-Cookie", cookie.output(header="").strip())
            self.send_header("Location", "/")
            self.end_headers()
            return

        # 2. Upload Handler
        if path_str == "/upload" or path_str == "/":
            if not self.isLoggedIn():
                self.send_error(403, "Forbidden")
                return

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers.get('Content-Type'),
                }
            )

            subDir = form.getvalue("current_dir", "")
            targetDir = os.path.join(ROOT_DIR, subDir)
            if not os.path.exists(targetDir):
                os.makedirs(targetDir, exist_ok=True)

            if "file" in form:
                file_item = form["file"]
                if file_item.filename:
                    filename = os.path.basename(file_item.filename)
                    filePath = os.path.join(targetDir, filename)
                    with open(filePath, "wb") as f:
                        f.write(file_item.file.read())

                    relFilePath = os.path.join(subDir, filename).replace("\\", "/") if subDir else filename
                    cfg = loadConfig()
                    sharedList = [x.strip() for x in cfg["shared_items"].split(",") if x.strip()]
                    if relFilePath not in sharedList:
                        sharedList.append(relFilePath)
                        cfg["shared_items"] = ",".join(sharedList)
                        saveConfig(cfg)
                    addLog(f"Tải lên và tự động chia sẻ file: {filename}")

            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            return

        self.send_error(404, "Not Found")

    def send_redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def serve_file(self, filePath):
        try:
            with open(filePath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Internal Server Error")

    def render_home_page(self, query_params):
        cfg = loadConfig()
        loggedIn = self.isLoggedIn()
        subDir = query_params.get("dir", [""])[0]
        targetDir = os.path.join(ROOT_DIR, subDir)

        if not os.path.exists(targetDir):
            self.send_redirect("/")
            return

        try:
            items = os.listdir(targetDir)
            items.sort(key=lambda x: (not os.path.isdir(os.path.join(targetDir, x)), x.lower()))
        except Exception:
            items = []

        sharedItemsSet = set([x.strip() for x in cfg["shared_items"].split(",") if x.strip()])

        displayItems = items if loggedIn else [name for name in items if (os.path.join(subDir, name).replace("\\", "/") if subDir else name) in sharedItemsSet]

        template_path = "index.html"
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as tf:
                htmlTemplate = tf.read()
        else:
            htmlTemplate = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>{{TITLE}}</title></head>
            <body><h1>{{TITLE}}</h1>{{{ADMIN_NOTICE}}}{{{AUTH_BOX}}}{{{ADMIN_PANEL}}}<hr><div>{{{BREADCRUMB}}}</div><ul>{{{ITEMS_LIST}}}</ul></body></html>"""

        itemsHtmlStr = ""
        for name in displayItems:
            itemPath = os.path.join(targetDir, name)
            isDir = os.path.isdir(itemPath)
            relPath = os.path.join(subDir, name).replace("\\", "/") if subDir else name
            isShared = relPath in sharedItemsSet
            checkIcon = "✅ " if isShared else ""
            checkboxHtml = f'<input type="checkbox" class="item-checkbox" value="{relPath}" style="width: auto; margin: 0; cursor: pointer;">' if loggedIn else ""

            if isDir:
                folderIdKey = relPath.replace("/", "_").replace(".", "_")
                shareBtnText = "✅ Chia sẻ tất cả" if isShared else "📂 Chia sẻ tất cả"
                shareBtnClass = "btn-share active" if isShared else "btn-share"
                
                admin_actions = f"""
                        <a class="{shareBtnClass}" href="/toggle_share?target={urllib.parse.quote(relPath)}&dir={urllib.parse.quote(subDir)}">{shareBtnText}</a>
                        <button class="btn-rename" onclick="renameItem('{name}')">✏️ Sửa</button>
                        <a class="btn-delete" href="/delete?target={urllib.parse.quote(name)}&dir={urllib.parse.quote(subDir)}" onclick="return confirm('Xóa thư mục này?');">🗑️ Xóa</a>""" if loggedIn else ""

                itemsHtmlStr += f"""
                <li style="flex-direction: column; align-items: stretch; border-bottom: 1px solid #eee; padding: 8px 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; width: 100%;">
                        <span class="item-name">{checkboxHtml} {checkIcon}📁 <b>{name}</b></span>
                        <div class="action-buttons">
                            <button class="btn-open" onclick="toggleSubFolder('{folderIdKey}')">📂 Mở tại chỗ</button>
                            {admin_actions}
                        </div>
                    </div>
                    <div id="sub_{folderIdKey}" class="sub-tree"><ul></ul></div>
                </li>"""
            else:
                encodedFilepath = urllib.parse.quote(relPath)
                shareBtnText = "✅ Đang chia sẻ" if isShared else "📤 Chia sẻ"
                shareBtnClass = "btn-share active" if isShared else "btn-share"
                
                admin_actions = f"""
                    <a class="{shareBtnClass}" href="/toggle_share?target={urllib.parse.quote(relPath)}&dir={urllib.parse.quote(subDir)}">{shareBtnText}</a>
                    <button class="btn-rename" onclick="renameItem('{name}')">✏️ Sửa</button>
                    <a class="btn-delete" href="/delete?target={urllib.parse.quote(name)}&dir={urllib.parse.quote(subDir)}" onclick="return confirm('Xóa file này?');">🗑️ Xóa</a>""" if loggedIn else ""

                itemsHtmlStr += f"""
                <li>
                    <span class="item-name">{checkboxHtml} {checkIcon}📄 {name}</span>
                    <div class="action-buttons">
                        <a class="btn-download" href="/uploads/{encodedFilepath}" download="{name}">📥 Tải</a>
                        {admin_actions}
                    </div>
                </li>"""

        if not displayItems:
            itemsHtmlStr = '<li style="justify-content: center; color: #777; font-style: italic; padding: 15px;">Trống (Chưa có mục nào được chia sẻ).</li>'

        breadcrumbHtml = f'<a href="/">🏠 {cfg["public_folder_name"]}</a>'
        if subDir:
            parts = subDir.replace("\\", "/").split("/")
            acc = ""
            for part in parts:
                if part:
                    acc = os.path.join(acc, part)
                    breadcrumbHtml += f' / <a href="/?dir={urllib.parse.quote(acc)}">{part}</a>'

        adminPanelHtml = ""
        if loggedIn:
            adminPanelHtml = f"""
            <div class="admin-panel">
                <h3>🛠️ Bảng Điều Khiển Quản Trị & Cấu Hình Hệ Thống</h3>
                <div class="admin-grid">
                    <div class="admin-card" style="grid-column: 1 / -1;">
                        <label>💻 Server & Web Real-time Logs:</label>
                        <div id="logContainer" class="log-box">Đang tải log thời gian thực...</div>
                    </div>
                </div>
            </div>
            <form id="uploadForm" enctype="multipart/form-data" method="post" action="/">
                <p style="margin-top:0; font-weight:bold; font-size:13px;">📤 Tải file lên trực tiếp (Tự động chia sẻ lên web):</p>
                <input type="hidden" name="current_dir" value="{subDir}">
                <input id="fileInput" name="file" type="file" required>
                <input type="submit" value="Tải Lên & Chia Sẻ Ngay">
                <div id="progress-container">
                    <progress id="progressBar" value="0" max="100"></progress>
                    <div id="status">Đang chuẩn bị...</div>
                </div>
            </form>"""

        authBoxHtml = '👑 <b>Admin</b> | <button class="btn-restart-top" onclick="restartServer()">🔄 Khởi động lại</button> | <a href="/logout">Đăng xuất</a>' if loggedIn else '<a href="#" onclick="document.getElementById(\'loginForm\').style.display=\'block\'; return false;" style="background:#007bff; color:white; padding:6px 12px; border-radius:5px;">🔐 Đăng nhập Admin</a>'

        finalHtml = htmlTemplate \
            .replace("{{TITLE}}", cfg["title"]) \
            .replace("{{VIDEO_BLOCK}}", "") \
            .replace("{{AUTH_BOX}}", authBoxHtml) \
            .replace("{{LOGO_HTML}}", "📁") \
            .replace("{{ADMIN_NOTICE}}", f'<div class="notice-box"><span>📢 <b>Thông báo:</b> {cfg["admin_notice"]}</span></div>' if cfg["admin_notice"] else "") \
            .replace("{{ADMIN_PANEL}}", adminPanelHtml) \
            .replace("{{BREADCRUMB}}", breadcrumbHtml) \
            .replace("{{BATCH_SHARE_TOOLS}}", '<div style="margin-bottom: 10px; display: flex; gap: 6px;"><button type="button" class="btn-share active" onclick="toggleSelectAll(true)">☑️ Chọn tất cả</button><button class="btn-share" onclick="submitSelectedShare()">✅ Chia sẻ đã chọn</button></div>' if loggedIn else "") \
            .replace("{{ITEMS_LIST}}", itemsHtmlStr) \
            .replace("{{CURRENT_SUB_DIR}}", subDir) \
            .replace("{{CURRENT_SHORTCUTS}}", cfg["quick_dirs"]) \
            .replace("{{ROOT_DIR}}", ROOT_DIR) \
            .replace("{{PUBLIC_NAME}}", cfg["public_folder_name"]) \
            .replace("{{DOMAIN}}", cfg["local_domain"])

        content_bytes = finalHtml.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content_bytes)))
        self.end_headers()
        self.wfile.write(content_bytes)

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), PythonServerHandler) as httpd:
        addLog(f"Python Server ready at http://localhost:{PORT}")
        httpd.serve_forever()
