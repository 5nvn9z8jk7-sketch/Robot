#!/usr/bin/env python3
# check_and_resume.py - Verification automatique + reprise apres recharge
# Usage: python3 check_and_resume.py [--quick] [--test-voice]

import json, os, sys, time, socket, argparse, urllib.request

try:
    import websocket
except ImportError:
    os.system("pip install websocket-client -q")
    import websocket

PC_OLLAMA = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
ROBOT_IP = os.environ.get("ROBOT_IP", "192.168.1.30")
ROBOT_WS = "ws://" + ROBOT_IP + ":9090"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

def ok(msg): print("  [OK] " + msg)
def fail(msg): print("  [FAIL] " + msg)
def warn(msg): print("  [WARN] " + msg)
def info(msg): print("  [INFO] " + msg)
def header(msg): print(); print("=" * 60); print(msg); print("=" * 60)

def check_ping(host, count=3):
    try:
        if sys.platform == "win32":
            return os.system("ping -n " + str(count) + " " + host + " >nul 2>&1") == 0
        return os.system("ping -c " + str(count) + " " + host + " >/dev/null 2>&1") == 0
    except: return False

def check_port(host, port, timeout=3):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except: return False

def check_ollama():
    try:
        with urllib.request.urlopen(PC_OLLAMA + "/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
            return True, [m["name"] for m in data.get("models", [])]
    except Exception as e:
        return False, str(e)

def check_rosbridge():
    try:
        ws = websocket.create_connection(ROBOT_WS, timeout=10)
        ws.send(json.dumps({"op": "call_service", "service": "/rosapi/nodes", "args": {}, "id": "1"}))
        time.sleep(1)
        data = json.loads(ws.recv())
        nodes = data.get("values", {}).get("nodes", [])
        ws.close()
        return True, nodes
    except Exception as e:
        return False, str(e)

def check_motors():
    try:
        ws = websocket.create_connection(ROBOT_WS, timeout=10)
        ws.send(json.dumps({"op": "subscribe", "topic": "/ros_robot_controller/set_motor", "id": "mc"}))
        time.sleep(0.5)
        ws.send(json.dumps({"op": "publish", "topic": "/controller/cmd_vel", "msg": {"linear": {"x": 0, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}}))
        time.sleep(1)
        try:
            ws.settimeout(2)
            data = json.loads(ws.recv())
            if data.get("op") == "publish" and "set_motor" in data.get("topic", ""):
                ws.close(); return True, "Moteurs actifs"
        except: pass
        ws.close(); return True, "rosbridge actif"
    except Exception as e:
        return False, str(e)

def check_llm_french():
    try:
        payload = json.dumps({"model": OLLAMA_MODEL, "prompt": "JSON: action=forward, response=OK. Commande: Avance", "stream": False, "options": {"num_predict": 256, "temperature": 0.1}}).encode()
        req = urllib.request.Request(PC_OLLAMA + "/api/generate", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            r = data.get("response", "")
            if "forward" in r.lower() or "avance" in r.lower():
                return True, "LLM comprend le francais"
            return False, "LLM: " + r[:80]
    except Exception as e:
        return False, str(e)

def quick_check():
    print("[" + time.strftime("%H:%M:%S") + "] Verification rapide...")
    if not check_ping(ROBOT_IP, 1):
        fail("Robot " + ROBOT_IP + " inaccessible"); return False
    ok("Robot " + ROBOT_IP + " repond")
    if not check_ping("192.168.1.20", 1):
        fail("PC inaccessible"); return False
    ok("PC repond")
    o_ok, _ = check_ollama()
    if o_ok: ok("Ollama actif")
    else: fail("Ollama inactif"); return False
    r_ok, nodes = check_rosbridge()
    if r_ok: ok("rosbridge actif (" + str(len(nodes)) + " noeuds)")
    else: fail("rosbridge inactif"); return False
    print(); print("Pret! Utilisez voice_bridge.py pour controler le robot.")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--test-voice", action="store_true")
    args = parser.parse_args()
    if args.quick:
        quick_check()
    elif args.test_voice:
        bridge = os.path.join(os.path.dirname(__file__), "voice_bridge.py")
        os.system('python3 "' + bridge + '" "Avance" --duration 1')
    else:
        header("DIAGNOSTIC COMPLET")
        print("Date: " + time.strftime("%Y-%m-%d %H:%M:%S"))
        print("PC: " + PC_OLLAMA + " | Robot: " + ROBOT_WS)
        results = {}
        print(); print("[1/5] PC - Ollama")
        if check_ping("192.168.1.20"): ok("PC ping OK")
        else: fail("PC ping FAIL")
        o_ok, o_info = check_ollama()
        if o_ok: ok("Ollama: " + str(len(o_info)) + " modeles")
        else: fail("Ollama: " + str(o_info))
        results["ollama"] = o_ok
        print(); print("[2/5] Robot - Connectivite")
        if check_ping(ROBOT_IP): ok("Robot ping OK")
        else: fail("Robot inaccessible - ALLUMER LE ROBOT"); return
        for p, n in [(22,"SSH"),(4000,"NoMachine"),(9090,"rosbridge"),(8080,"web")]:
            if check_port(ROBOT_IP, p): ok("Port " + str(p) + " (" + n + ")")
            else: warn("Port " + str(p) + " ferme")
        print(); print("[3/5] Robot - ROS2")
        r_ok, nodes = check_rosbridge()
        if r_ok: ok("rosbridge: " + str(len(nodes)) + " noeuds")
        else: fail("rosbridge: " + str(nodes))
        results["ros"] = r_ok
        print(); print("[4/5] Robot - Moteurs")
        m_ok, m_info = check_motors()
        if m_ok: ok(m_info)
        else: fail("Moteurs: " + str(m_info))
        results["motors"] = m_ok
        print(); print("[5/5] PC - LLM Francais")
        l_ok, l_info = check_llm_french()
        if l_ok: ok(l_info)
        else: fail("LLM: " + str(l_info))
        results["llm"] = l_ok
        print(); header("RESUME")
        for k, v in results.items():
            print("  " + k.ljust(12) + ": " + ("OK" if v else "FAIL"))
        print()
        if all(results.values()):
            print("TOUT EST FONCTIONNEL!")
        else:
            print("Certains elements a verifier")
        print(); print("Commandes: python3 speech_patch/voice_bridge.py \"Avance\"")

if __name__ == "__main__":
    main()
