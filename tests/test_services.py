"""Vérifier l'arrêt avec des processus isolés, sans démarrer la démonstration."""
from pathlib import Path
import importlib.util
import os
import select
import signal
import subprocess
import sys

import pytest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("service_manager", PROJECT / "tools/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not hasattr(os, "pidfd_open"),
    reason="La gestion des services nécessite Linux et pidfd.",
)

CHILD = """
from pathlib import Path
import signal
import sys

log, name, ignore = sys.argv[1:4]

def stop(number, frame):
    with Path(log).open('a') as stream:
        stream.write(f'{name}:{number}\\n')
    raise SystemExit(0)

signal.signal(signal.SIGTERM, signal.SIG_IGN if ignore == 'oui' else stop)
signal.signal(signal.SIGINT, stop)
print('prêt', flush=True)
while True:
    signal.pause()
"""


@pytest.fixture
def launch(tmp_path):
    processes = []

    def start(root, name, *, ignore=False, pgdata=None):
        scripts = {
            "app": "tools/serve.py",
            "frontend": "tools/serve_conversations_frontend.py",
            "conversations": "tools/conversations.py",
            "model_launcher": "tools/serve_model.py",
        }
        if name in scripts:
            path = root / scripts[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(CHILD)
            command = [sys.executable, str(path)]
        else:
            relative = (".runtime/postgres/usr/bin/postgres" if name == "postgres"
                        else ".runtime/llama/llama-b10883/llama-server")
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.symlink_to(sys.executable)
            command = [str(path), "-c", CHILD]
        command.extend([str(tmp_path / "signals.log"), name, "oui" if ignore else "non"])
        if name == "postgres":
            command.extend(["-D", str(pgdata or root / ".runtime/pgdata")])
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append(process)
        assert select.select([process.stdout], [], [], 5)[0]
        assert process.stdout.readline() == "prêt\n".encode()
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_stop_all_waits_in_order_and_preserves_data(tmp_path, launch):
    root = tmp_path / "demo"
    names = ["app", "frontend", "conversations", "model", "postgres"]
    processes = [launch(root, name) for name in names]
    data = root / ".runtime/mail-workspace.sqlite"
    data.write_bytes(b"donnees a conserver")

    assert manage.stop_services(root, 5) == 0
    assert all(process.wait(timeout=1) == 0 for process in processes)
    assert (tmp_path / "signals.log").read_text().splitlines() == [
        f"{name}:{int(signal.SIGINT if name == 'postgres' else signal.SIGTERM)}"
        for name in names
    ]
    assert data.read_bytes() == b"donnees a conserver"
    assert manage.stop_services(root, 5) == 0


def test_stale_records_and_other_checkout_are_not_stopped(tmp_path, launch):
    root = tmp_path / "demo"
    other = tmp_path / "demo-other"
    owned = launch(root, "app")
    foreign = launch(other, "app")
    wrong_cluster = launch(root, "postgres", pgdata=other / ".runtime/pgdata")
    runtime = root / ".runtime"
    (runtime / "app.pid").write_text(str(foreign.pid))
    (runtime / "model.pid").write_text("invalide")
    (runtime / "mail-services.json").write_text("{invalide")

    assert manage.stop_services(root, 5) == 0
    assert owned.wait(timeout=1) == 0
    assert foreign.poll() is None
    assert wrong_cluster.poll() is None
    assert (runtime / "app.pid").read_text() == str(foreign.pid)


def test_timeout_keeps_dependencies_running(tmp_path, launch, capsys):
    root = tmp_path / "demo"
    backend = launch(root, "conversations", ignore=True)
    model = launch(root, "model")
    database = launch(root, "postgres")

    assert manage.stop_services(root, .05) == 1
    assert all(process.poll() is None for process in (backend, model, database))
    assert "Délai dépassé" in capsys.readouterr().out


def test_status_and_legacy_stop_app(tmp_path, launch, monkeypatch, capsys):
    root = tmp_path / "demo"
    app = launch(root, "app")
    frontend = launch(root, "frontend")
    monkeypatch.setattr(manage, "ROOT", root)

    assert manage.main(["status"]) == 0
    assert str(app.pid) in capsys.readouterr().out
    assert app.poll() is None
    assert manage.main(["stop-app"]) == 0
    assert app.wait(timeout=1) == 0
    assert frontend.poll() is None


def test_process_identity_is_checked_again_before_signalling(tmp_path, launch):
    root = tmp_path / "demo"
    foreign = launch(tmp_path / "other", "app")
    assert manage.stop_process(foreign.pid, "app", root, .05)
    assert foreign.poll() is None


def test_stops_model_launcher_and_duplicate_services(tmp_path, launch):
    root = tmp_path / "demo"
    processes = [launch(root, name) for name in ("app", "app", "model_launcher")]
    assert manage.stop_services(root, 5) == 0
    assert all(process.wait(timeout=1) == 0 for process in processes)


def test_stop_entrypoint_without_installation(tmp_path):
    root = tmp_path / "demo"
    (root / "tools").mkdir(parents=True)
    for relative in ("stop.py", "tools/manage.py"):
        (root / relative).write_bytes((PROJECT / relative).read_bytes())
    for _ in range(2):
        result = subprocess.run([sys.executable, "-B", str(root / "stop.py")],
                                cwd=tmp_path, capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stderr
        assert "Arrêt terminé" in result.stdout
    assert not (root / ".runtime").exists()


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(SystemExit) as error:
        manage.main(["stop", "--timeout", timeout])
    assert error.value.code == 2
