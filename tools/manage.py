"""Consulter et arrêter les services Linux de cette démonstration locale."""
from pathlib import Path
import argparse
import math
import os
import select
import signal
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "app": "entrée HTTP",
    "frontend": "frontend Conversations",
    "conversations": "backend Conversations",
    "model": "modèle local",
    "postgres": "PostgreSQL",
}
SCRIPTS = {
    "tools/serve.py": "app",
    "tools/serve_conversations_frontend.py": "frontend",
    "tools/conversations.py": "conversations",
    "tools/serve_model.py": "model",
}


def process_service(entry: Path, root: Path) -> str | None:
    """Vérifier le propriétaire et les arguments, sans se fier aux fichiers PID."""
    try:
        if entry.stat().st_uid != os.getuid():
            return None
        args = (entry / "cmdline").read_bytes().split(b"\0")
        if len(args) > 1 and Path(os.fsdecode(args[0])).name.startswith("python"):
            for script, name in SCRIPTS.items():
                if args[1] == os.fsencode(root / script):
                    return name
        if args[0] == os.fsencode(root / ".runtime/llama/llama-b10883/llama-server"):
            return "model"
        if args[0] == os.fsencode(root / ".runtime/postgres/usr/bin/postgres"):
            for option, value in zip(args, args[1:]):
                if option == b"-D" and value == os.fsencode(root / ".runtime/pgdata"):
                    return "postgres"
    except (FileNotFoundError, ProcessLookupError):
        pass
    return None


def running_services(root: Path) -> dict[str, list[int]]:
    services = {name: [] for name in SERVICES}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            name = process_service(entry, root)
            if name is not None:
                services[name].append(int(entry.name))
    return services


def stop_process(pid: int, name: str, root: Path, timeout: float) -> bool:
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        return True
    try:
        # Le descripteur reste lié au processus même si son numéro est réutilisé.
        if process_service(Path("/proc", str(pid)), root) != name:
            return True
        # SIGINT demande l'arrêt rapide et propre de PostgreSQL (« fast »).
        sig = signal.SIGINT if name == "postgres" else signal.SIGTERM
        try:
            signal.pidfd_send_signal(descriptor, sig)
        except ProcessLookupError:
            return True
        if not select.select([descriptor], [], [], timeout)[0]:
            print(f"Délai dépassé : {SERVICES[name]} (PID {pid}). Aucun arrêt forcé.", flush=True)
            return False
        print(f"Arrêté : {SERVICES[name]} (PID {pid}).", flush=True)
        return True
    finally:
        os.close(descriptor)


def stop_services(root: Path, timeout: float, *, app_only: bool = False) -> int:
    services = running_services(root)
    names = ["app"] if app_only else list(SERVICES)
    # Attendre les applications avant d'arrêter le modèle et la base de données.
    for name in names:
        if not services[name]:
            print(f"Déjà arrêté : {SERVICES[name]}.", flush=True)
        for pid in services[name]:
            if not stop_process(pid, name, root, timeout):
                print("Arrêt incomplet ; les services suivants sont conservés.", flush=True)
                return 1
    remaining = running_services(root)
    if any(remaining[name] for name in names):
        print("Arrêt incomplet : des services sont encore actifs. Relancez la commande.", flush=True)
        return 1
    print("Arrêt terminé. Les données sont conservées.", flush=True)
    return 0


def positive_timeout(value: str) -> float:
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("Le délai doit être un nombre fini strictement positif.")
    return timeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "stop", "stop-app"])
    parser.add_argument("--timeout", type=positive_timeout, default=30,
                        help="Délai maximal par processus en secondes (défaut : 30).")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        print("Cette commande nécessite Linux avec la prise en charge de pidfd.", file=sys.stderr)
        return 1
    try:
        if args.action == "status":
            for name, pids in running_services(ROOT).items():
                state = "actif (PID " + ", ".join(map(str, pids)) + ")" if pids else "arrêté"
                print(f"{SERVICES[name]} : {state}.")
            return 0
        return stop_services(ROOT, args.timeout, app_only=args.action == "stop-app")
    except OSError as error:
        print(f"Impossible de vérifier ou d'arrêter les services : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
