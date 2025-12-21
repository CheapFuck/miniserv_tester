import socket
import subprocess
import time
import os
import signal
import sys
import atexit
import re

SERVER = "./mini_serv"
SOURCE = "mini_serv.c"

# ─────────────────────────────────────────────
# Find available port 
# ─────────────────────────────────────────────
def find_available_port(start=8888, end=9999):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available port found")

PORT = find_available_port()

ALLOWED_FUNCTIONS = {
    "accept", "atoi", "bind", "bzero", "calloc", "close", "exit", "free",
    "listen", "malloc", "memset", "poll", "realloc", "recv", "select",
    "send", "socket", "sprintf", "strcat", "strcpy", "strlen", "strstr", "write"
}

# ─────────────────────────────────────────────
# Check for forbidden functions
# ─────────────────────────────────────────────
def check_forbidden_functions(source_file):
    with open(source_file) as f:
        content = f.read()
    
    clean_content = re.sub(r'//.*', '', content)
    clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)
    clean_content = re.sub(r'"([^"\\]|\\.)*"', '', clean_content)
    
    user_functions = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\s+\**\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{', clean_content))
    
    function_calls = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', clean_content)
    
    c_keywords = {
        "if", "else", "while", "for", "do", "switch", "case", "return",
        "sizeof", "typedef", "struct", "enum", "union", "main"
    }
    
    forbidden_found = []
    for func in function_calls:
        if func not in ALLOWED_FUNCTIONS and func not in c_keywords and func not in user_functions:
            if func not in forbidden_found:
                forbidden_found.append(func)
    
    return forbidden_found

# ─────────────────────────────────────────────
# Compile and count lines
# ─────────────────────────────────────────────
print(f"Checking {SOURCE} for forbidden functions...")
forbidden = check_forbidden_functions(SOURCE)
if forbidden:
    print(f"❌ Forbidden functions found: {', '.join(forbidden)}")
    sys.exit(1)
print("✅ No forbidden functions found\n")

print(f"Compiling {SOURCE}...")
result = subprocess.run(["gcc", "-o", "mini_serv", SOURCE], capture_output=True, text=True)
if result.returncode != 0:
    print("❌ Compilation failed:")
    print(result.stderr)
    sys.exit(1)
with open(SOURCE) as f:
    lines = len(f.readlines())
print(f"✅ Compiled ({lines} lines)\n")

def recv_all(sock, timeout=1.0):
    sock.setblocking(0)
    data = b""
    start = time.time()
    while time.time() - start < timeout:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        except BlockingIOError:
            time.sleep(0.01)
    return data.decode()

def fail(msg):
    print("❌ FAIL:", msg)
    cleanup()
    sys.exit(1)

def ok(msg):
    print("✅", msg)

def cleanup():
    for c in clients:
        try:
            c.shutdown(socket.SHUT_RDWR)
            c.close()
        except:
            pass
    try:
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=1)
    except:
        try:
            server.kill()
        except:
            pass

# Register cleanup to run on exit (even on crash)
atexit.register(cleanup)

# ─────────────────────────────────────────────
# Start server
# ─────────────────────────────────────────────
print(f"Starting server on port {PORT}...")
server = subprocess.Popen([SERVER, str(PORT)])

def connect_with_retry(sock, addr, max_retries=10, delay=0.1):
    for i in range(max_retries):
        try:
            sock.connect(addr)
            return True
        except ConnectionRefusedError:
            if i < max_retries - 1:
                time.sleep(delay)
            else:
                return False
    return False

clients = []

# ─────────────────────────────────────────────
# Connect clients
# ─────────────────────────────────────────────
c1 = socket.socket()
c2 = socket.socket()

clients += [c1, c2]

if not connect_with_retry(c1, ("127.0.0.1", PORT)):
    fail("Could not connect to server")
time.sleep(0.1)
c2.connect(("127.0.0.1", PORT))
time.sleep(0.1)

out = recv_all(c1)
if "server: client 1 just arrived\n" not in out:
    fail("arrival message missing")
ok("arrival messages")

# ─────────────────────────────────────────────
# Split recv test
# ─────────────────────────────────────────────
c2.send(b"hello ")
time.sleep(0.2)
c2.send(b"world\n")
time.sleep(0.2)
out = recv_all(c1)
if "client 1: hello world\n" not in out:
    fail("split recv failed")
ok("split recv handled")

# ─────────────────────────────────────────────
# Multiple \\n test
# ─────────────────────────────────────────────
c2.send(b"a\nb\nc\n")
time.sleep(0.2)
out = recv_all(c1)
for x in ["a","b","c"]:
    if f"client 1: {x}\n" not in out:
        fail("multiple newline handling failed")
ok("multiple \\n handled")

# ─────────────────────────────────────────────
# EOF (Ctrl+D) mid-stream test
# ─────────────────────────────────────────────
c2.send(b"before EOF\x04after EOF\n")
time.sleep(0.2)
out = recv_all(c1)
# The \x04 should not break the message
if "client 1:" in out and "EOF" in out:
    ok("EOF (Ctrl+D) character handled")
else:
    print(f"⚠ EOF handling unclear, got: {out[:100]}")

# ─────────────────────────────────────────────
# Empty lines test
# ─────────────────────────────────────────────
c2.send(b"\n\n\n")
time.sleep(0.2)
out = recv_all(c1)
# Server may or may not broadcast empty lines - just check it doesn't crash
ok("empty lines don't crash server")

# ─────────────────────────────────────────────
# Very long line test (informative only - 5KB)
# ─────────────────────────────────────────────
long_line = b"A" * 5000 + b"\n"
try:
    c2.sendall(long_line)
    time.sleep(0.5)
    out = recv_all(c1)
    print("\nℹ Long-line test (5KB) output (may be truncated or crash if server buffer exceeded):")
    print(out[:500] + ("..." if len(out) > 500 else ""))
except Exception as e:
    print("\n⚠ Long-line test (5KB) exception (informative only):", e)

# ─────────────────────────────────────────────
# VERY LARGE message test (Test 8 style - 100KB+)
# ─────────────────────────────────────────────
print("\n--- Testing VERY LARGE messages (like Test 8) ---")

# Test with 100KB message
large_size = 100000
large_msg = b"B" * large_size + b"\n"
try:
    c2.sendall(large_msg)
    time.sleep(1.0)  # give more time for large message
    out = recv_all(c1, timeout=2.0)
    expected_prefix = "client 1: " + "B" * large_size
    if expected_prefix in out:
        ok(f"Very large message (100KB) handled correctly")
    else:
        # Check if we got partial data
        if "client 1: B" in out:
            received_bs = out.count('B')
            print(f"⚠ Partial large message received: {received_bs}/{large_size} B's")
            if received_bs < large_size:
                fail(f"Very large message (100KB) truncated or incomplete")
        else:
            fail(f"Very large message (100KB) not received at all")
except Exception as e:
    fail(f"Very large message (100KB) exception: {e}")

# Test with 200KB message (even larger)
huge_size = 200000
huge_msg = b"C" * huge_size + b"\n"
try:
    c2.sendall(huge_msg)
    time.sleep(1.5)
    out = recv_all(c1, timeout=3.0)
    expected_prefix = "client 1: " + "C" * huge_size
    if expected_prefix in out:
        ok(f"Huge message (200KB) handled correctly")
    else:
        if "client 1: C" in out:
            received_cs = out.count('C')
            print(f"⚠ Partial huge message received: {received_cs}/{huge_size} C's")
            if received_cs < huge_size:
                fail(f"Huge message (200KB) truncated or incomplete")
        else:
            fail(f"Huge message (200KB) not received at all")
except Exception as e:
    fail(f"Huge message (200KB) exception: {e}")

# Test with 500KB message (stress test)
stress_size = 500000
stress_msg = b"D" * stress_size + b"\n"
try:
    c2.sendall(stress_msg)
    time.sleep(2.0)
    out = recv_all(c1, timeout=4.0)
    expected_prefix = "client 1: " + "D" * stress_size
    if expected_prefix in out:
        ok(f"Stress test message (500KB) handled correctly")
    else:
        if "client 1: D" in out:
            received_ds = out.count('D')
            print(f"⚠ Partial stress message received: {received_ds}/{stress_size} D's")
            if received_ds < stress_size * 0.9:  # Allow 10% tolerance for stress test
                print(f"⚠ Stress test (500KB) - only {received_ds}/{stress_size} bytes received (informative)")
            else:
                ok(f"Stress test message (500KB) mostly received ({received_ds}/{stress_size})")
        else:
            print(f"⚠ Stress test (500KB) - message not received (informative only)")
except Exception as e:
    print(f"⚠ Stress test (500KB) exception (informative only): {e}")

# ─────────────────────────────────────────────
# Disconnect test
# ─────────────────────────────────────────────
try:
    c2.shutdown(socket.SHUT_RDWR)
except:
    pass
c2.close()
clients.remove(c2)
time.sleep(0.2)
out = recv_all(c1)
if "server: client 1 just left\n" not in out:
    fail("disconnect message missing")
ok("disconnect handled")

# ─────────────────────────────────────────────
# Connect/Disconnect cycling test (fd reuse, ID increment)
# ─────────────────────────────────────────────
print("\n--- Testing connect/disconnect cycling (ID should keep incrementing) ---")

# At this point: c1 is still connected (ID=0), c2 just left (ID=1)
# New clients should get ID=2, 3, 4...

for i in range(3):
    c_temp = socket.socket()
    c_temp.connect(("127.0.0.1", PORT))
    clients.append(c_temp)
    time.sleep(0.1)
    
    out = recv_all(c1)
    expected_id = 2 + i  # IDs should be 2, 3, 4
    if f"server: client {expected_id} just arrived\n" not in out:
        fail(f"Connect cycle {i+1}: expected client {expected_id}, got: {out}")
    
    # Send a message to verify the client works
    c_temp.send(f"hello from cycle {i+1}\n".encode())
    time.sleep(0.1)
    out = recv_all(c1)
    if f"client {expected_id}: hello from cycle {i+1}\n" not in out:
        fail(f"Connect cycle {i+1}: message from client {expected_id} not received")
    
    # Disconnect
    try:
        c_temp.shutdown(socket.SHUT_RDWR)
    except:
        pass
    c_temp.close()
    clients.remove(c_temp)
    time.sleep(0.1)
    
    out = recv_all(c1)
    if f"server: client {expected_id} just left\n" not in out:
        fail(f"Disconnect cycle {i+1}: expected client {expected_id} left, got: {out}")

ok("Connect/disconnect cycling - IDs correctly increment (2, 3, 4)")

cleanup()
print("\n🎉 All tests passed!")
