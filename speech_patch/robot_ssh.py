#!/usr/bin/env python3
# robot_ssh.py — Helper SSH pour contrôler le robot depuis le PC
#
# Usage:
#   python3 robot_ssh.py "commande"           # Exécute une commande sur le robot
#   python3 robot_ssh.py --copy fichier       # Copie un fichier vers le robot
#   python3 robot_ssh.py --deploy             # Déploie le speech_patch
#
# Configuration:
#   ROBOT_HOST     (défaut: 192.168.1.30)
#   ROBOT_USER     (défaut: ubuntu)
#   ROBOT_PASSWORD (mot de passe SSH, ou utiliser la clé ~/.ssh/id_robot)

import os
import sys
import argparse
import subprocess

ROBOT_HOST = os.environ.get("ROBOT_HOST", "192.168.1.30")
ROBOT_USER = os.environ.get("ROBOT_USER", "ubuntu")
SSH_KEY = os.path.expanduser("~/.ssh/id_robot")
ROBOT_PASSWORD = os.environ.get("ROBOT_PASSWORD", "")


def get_ssh_cmd():
    """Retourne la commande SSH de base."""
    if os.path.exists(SSH_KEY):
        return ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10", f"{ROBOT_USER}@{ROBOT_HOST}"]
    elif ROBOT_PASSWORD:
        # Utiliser sshpass si disponible, sinon paramiko
        return ["sshpass", "-p", ROBOT_PASSWORD, "ssh",
                "-o", "StrictHostKeyChecking=no", f"{ROBOT_USER}@{ROBOT_HOST}"]
    else:
        return ["ssh", "-o", "StrictHostKeyChecking=no", f"{ROBOT_USER}@{ROBOT_HOST}"]


def run_on_robot(command, timeout=60):
    """Exécute une commande sur le robot et retourne le résultat."""
    ssh_cmd = get_ssh_cmd() + [command]
    print(f"[SSH] {ROBOT_USER}@{ROBOT_HOST}: {command[:80]}...")
    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            print(result.stdout)
            return result.stdout
        else:
            print(f"[ERREUR] {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print(f"[ERREUR] Timeout après {timeout}s")
        return None
    except Exception as e:
        print(f"[ERREUR] {e}")
        return None


def copy_to_robot(local_path, remote_path):
    """Copie un fichier local vers le robot."""
    if os.path.exists(SSH_KEY):
        scp_cmd = ["scp", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
                   local_path, f"{ROBOT_USER}@{ROBOT_HOST}:{remote_path}"]
    else:
        scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no",
                   local_path, f"{ROBOT_USER}@{ROBOT_HOST}:{remote_path}"]
    print(f"[SCP] {local_path} -> {ROBOT_USER}@{ROBOT_HOST}:{remote_path}")
    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("[OK] Fichier copié")
            return True
        else:
            print(f"[ERREUR] {result.stderr}")
            return False
    except Exception as e:
        print(f"[ERREUR] {e}")
        return False


def check_connection():
    """Vérifie la connexion SSH au robot."""
    result = run_on_robot("echo 'CONNECTED' && hostname && uptime", timeout=15)
    return result is not None and "CONNECTED" in result


def deploy_speech_patch():
    """Déploie le speech_patch sur le robot."""
    print("=" * 50)
    print("  Déploiement speech_patch sur le robot")
    print("=" * 50)

    # 1. Copier le patch
    patch_local = os.path.join(os.path.dirname(__file__), "speech_offline_patch.py")
    if not copy_to_robot(patch_local, "~/speech_offline_patch.py"):
        return False

    # 2. Copier le script d'installation
    install_local = os.path.join(os.path.dirname(__file__), "install_on_robot.sh")
    if not copy_to_robot(install_local, "~/install_on_robot.sh"):
        return False

    # 3. Exécuter l'installation
    print("\n[INFO] Installation sur le robot...")
    run_on_robot("cd ~ && bash install_on_robot.sh", timeout=300)

    # 4. Vérifier
    print("\n[INFO] Vérification...")
    run_on_robot("python3 ~/speech_offline_patch.py --selftest", timeout=60)

    print("\n[OK] Déploiement terminé")
    return True


def main():
    parser = argparse.ArgumentParser(description="Helper SSH pour le robot")
    parser.add_argument("command", nargs="?", help="Commande à exécuter sur le robot")
    parser.add_argument("--copy", metavar="FICHIER", help="Copie un fichier vers le robot")
    parser.add_argument("--to", metavar="CHEMIN", default="~", help="Destination distante (défaut: ~)")
    parser.add_argument("--deploy", action="store_true", help="Déploie le speech_patch")
    parser.add_argument("--check", action="store_true", help="Vérifie la connexion")
    args = parser.parse_args()

    print(f"Robot: {ROBOT_USER}@{ROBOT_HOST}")
    print(f"Clé SSH: {SSH_KEY} ({'trouvée' if os.path.exists(SSH_KEY) else 'absente'})")
    print()

    if args.check:
        if check_connection():
            print("[OK] Connexion SSH fonctionnelle!")
        else:
            print("[ERREUR] Connexion SSH échouée")
            print("\nPour configurer l'accès SSH:")
            print("  1. Se connecter au robot via NoMachine")
            print("  2. Copier speech_patch/setup_ssh_access.sh sur le robot")
            print("  3. Exécuter: bash setup_ssh_access.sh")
            sys.exit(1)
    elif args.deploy:
        if not check_connection():
            print("[ERREUR] Connexion SSH requise pour le déploiement")
            sys.exit(1)
        deploy_speech_patch()
    elif args.copy:
        copy_to_robot(args.copy, args.to)
    elif args.command:
        run_on_robot(args.command)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
