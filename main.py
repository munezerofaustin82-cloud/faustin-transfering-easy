import sys
import flet as ft
import socket, threading, os, json

DISCOVERY_PORT = 50005
TRANSFER_PORT = 50006
BUFFER_SIZE = 8192
RECEIVE_FOLDER = os.path.join(os.path.expanduser('~'), 'Desktop', 'Faustin_Received')
os.makedirs(RECEIVE_FOLDER, exist_ok=True)

def main(page: ft.Page):
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    png_path = os.path.join(base_dir, "assets", "icon.png")
    page.window.icon = os.path.join(base_dir, "assets", "icon.ico")
    page.title = 'Faustin Transfering Easy'
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 460
    page.window.height = 700
    page.padding = 25

    my_name = socket.gethostname()
    target_ip = None
    target_device_name = ''
    selected_files = []
    file_picker = ft.FilePicker()

    my_device_input = ft.TextField(label='My Device Name', value=my_name, prefix_icon=ft.Icons.DEVICES, border_radius=10)
    target_device_input = ft.TextField(label='Enter Target Device Name', hint_text='Type exact device name', prefix_icon=ft.Icons.SEARCH, border_radius=10)
    status_text = ft.Text('Status: Ready (Offline Mode)', color=ft.Colors.GREEN_400, size=14)
    receive_status = ft.Text('Receiving folder: Desktop\\Faustin_Received', color=ft.Colors.GREY_400, size=13)
    connected_label = ft.Text('', size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
    files_list_text = ft.Text('No files selected yet.', size=13, color=ft.Colors.GREY_300)
    transfer_progress = ft.ProgressBar(width=400, value=0, visible=False)
    transfer_status = ft.Text('', size=14)
    def listen_for_discovery():
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: udp_sock.bind(('0.0.0.0', DISCOVERY_PORT))
        except Exception: return
        while True:
            try:
                data, addr = udp_sock.recvfrom(1024)
                msg = data.decode('utf-8')
                if msg.startswith('WHO_IS:'):
                    parts = msg.split(':', 1)
                    req = parts[1].strip() if len(parts) > 1 else ''
                    cur = my_device_input.value.strip()
                    if req.lower() == cur.lower():
                        udp_sock.sendto(f'I_AM:{cur}'.encode('utf-8'), addr)
            except Exception: pass

    def recv_exact(sock, n):
        data = bytearray()
        while len(data) < n:
            p = sock.recv(n - len(data))
            if not p: return None
            data.extend(p)
        return bytes(data)
    def listen_for_files():
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            tcp_sock.bind(('0.0.0.0', TRANSFER_PORT))
            tcp_sock.listen(5)
        except Exception: return
        while True:
            try:
                conn, addr = tcp_sock.accept()
                raw_len = recv_exact(conn, 10)
                if not raw_len: conn.close(); continue
                hlen = int(raw_len.decode('utf-8').strip())
                header = json.loads(recv_exact(conn, hlen).decode('utf-8'))
                fname = os.path.basename(header['filename'])
                fsize = header['filesize']
                receive_status.value = f'Receiving: {fname}...'
                receive_status.color = ft.Colors.RED_400
                page.update()
                spath = os.path.join(RECEIVE_FOLDER, fname)
                rec = 0
                with open(spath, 'wb') as f:
                    while rec < fsize:
                        chunk = conn.recv(min(BUFFER_SIZE, fsize - rec))
                        if not chunk: break
                        f.write(chunk)
                        rec += len(chunk)
                conn.close()
                receive_status.value = f'Received: {fname} (Saved in Faustin_Received)'
                receive_status.color = ft.Colors.GREEN_400
                page.update()
            except Exception as ex:
                receive_status.value = f'Receive error: {ex}'
                page.update()

    threading.Thread(target=listen_for_discovery, daemon=True).start()
    threading.Thread(target=listen_for_files, daemon=True).start()
    async def pick_files_clicked(e):
        nonlocal selected_files
        files = await file_picker.pick_files(allow_multiple=True)
        if files:
            selected_files = [f.path for f in files if f.path]
            names = '\n'.join([f'* {f.name}' for f in files])
            files_list_text.value = f'Selected ({len(selected_files)} files):\n{names}'
            send_btn.disabled = False
        else:
            selected_files = []
            files_list_text.value = 'No files selected.'
            send_btn.disabled = True
        page.update()

    def connect_clicked(e):
        nonlocal target_ip, target_device_name
        target = target_device_input.value.strip()
        if not target:
            status_text.value = 'Please enter the target device name!'
            status_text.color = ft.Colors.ORANGE_400
            page.update(); return
        status_text.value = f'Searching for {target}...'
        status_text.color = ft.Colors.RED_400
        page.update()
        def search():
            nonlocal target_ip, target_device_name
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_sock.settimeout(3.0)
            try:
                msg = f'WHO_IS:{target}'.encode('utf-8')
                udp_sock.sendto(msg, ('255.255.255.255', DISCOVERY_PORT))
                udp_sock.sendto(msg, ('127.0.0.1', DISCOVERY_PORT))
                data, addr = udp_sock.recvfrom(1024)
                res = data.decode('utf-8')
                if res.startswith('I_AM:'):
                    target_ip = addr[0]
                    parts = res.split(':', 1)
                    target_device_name = parts[1].strip() if len(parts) > 1 else target
                    show_transfer_screen()
            except socket.timeout:
                status_text.value = f'Device {target} not found. Ensure same Wi-Fi/Hotspot.'
                status_text.color = ft.Colors.RED_400
                page.update()
            finally: udp_sock.close()
        threading.Thread(target=search, daemon=True).start()
    def send_files_clicked(e):
        if not selected_files or not target_ip: return
        send_btn.disabled = True
        transfer_progress.visible = True
        transfer_progress.value = 0
        page.update()
        def transfer():
            tot = len(selected_files)
            for idx, fpath in enumerate(selected_files):
                try:
                    fname = os.path.basename(fpath)
                    fsize = os.path.getsize(fpath)
                    transfer_status.value = f'Sending ({idx+1}/{tot}): {fname}...'
                    transfer_status.color = ft.Colors.RED_400
                    page.update()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((target_ip, TRANSFER_PORT))
                    hb = json.dumps({'filename': fname, 'filesize': fsize}).encode('utf-8')
                    sock.sendall(f'{len(hb):<10}'.encode('utf-8') + hb)
                    sent = 0
                    with open(fpath, 'rb') as f:
                        while True:
                            chunk = f.read(BUFFER_SIZE)
                            if not chunk: break
                            sock.sendall(chunk)
                            sent += len(chunk)
                            transfer_progress.value = sent / max(fsize, 1)
                            page.update()
                    sock.close()
                except Exception as ex:
                    transfer_status.value = f'Error: {ex}'
                    transfer_status.color = ft.Colors.RED_400
                    send_btn.disabled = False
                    page.update(); return
            transfer_status.value = 'All files sent successfully!'
            transfer_status.color = ft.Colors.GREEN_400
            send_btn.disabled = False
            page.update()
        threading.Thread(target=transfer, daemon=True).start()

    connect_btn = ft.Button(content='Connect', icon=ft.Icons.LINK, on_click=connect_clicked, width=220, height=48, style=ft.ButtonStyle(bgcolor=ft.Colors.RED_600, color=ft.Colors.WHITE))
    send_btn = ft.Button(content='Send Files', icon=ft.Icons.SEND, on_click=send_files_clicked, disabled=True, width=220, height=48, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE))

    def show_transfer_screen():
        page.clean()
        connected_label.value = f'Connected to: {target_device_name} ({target_ip})'
        page.add(
            ft.Row([ft.Image(src=png_path, width=32, height=32), ft.Text('Faustin Transfering Easy', size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_400)], alignment=ft.MainAxisAlignment.CENTER),
            connected_label, ft.Divider(height=15),
            ft.Button(content='Select Files', icon=ft.Icons.FOLDER_OPEN, on_click=pick_files_clicked, height=45),
            ft.Container(content=files_list_text, padding=15, bgcolor=ft.Colors.GREY_900, border_radius=10, width=400),
            send_btn, transfer_progress, transfer_status, ft.Divider(height=15), receive_status,
            ft.TextButton(content='Disconnect / Back', icon=ft.Icons.ARROW_BACK, on_click=lambda _: show_home_screen())
        )
        page.update()

    def show_home_screen():
        page.clean()
        status_text.value = 'Status: Ready (Offline Mode)'
        status_text.color = ft.Colors.GREEN_400
        page.add(
            ft.Row([ft.Image(src=png_path, width=36, height=36), ft.Text('Faustin Transfering Easy', size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_400)], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text('Fast Offline File Sharing', size=14, color=ft.Colors.GREY_400),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT), my_device_input,
            ft.Divider(height=15, color=ft.Colors.TRANSPARENT), target_device_input,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            ft.Row([connect_btn], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT), status_text, ft.Divider(height=10), receive_status
        )
        page.update()

    show_home_screen()

ft.run(main)
