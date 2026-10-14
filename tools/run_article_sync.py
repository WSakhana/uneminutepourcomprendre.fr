"""Point d’entrée de la tâche Windows : environnement utilisateur, journal local et aucune invite."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def environment_value(name):
    import winreg

    for hive, key in ((winreg.HKEY_CURRENT_USER, 'Environment'), (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
        try:
            with winreg.OpenKey(hive, key) as env:
                return winreg.QueryValueEx(env, name)[0]
        except FileNotFoundError:
            pass
    return os.environ.get(name)


def main():
    for name in ('UMPC_SFTP_HOST', 'UMPC_SFTP_USER', 'UMPC_SFTP_PASSWORD', 'UMPC_YOUTUBE_AUTH_DIR'):
        value = environment_value(name)
        if value:
            os.environ[name] = value
    os.environ['PYTHONUTF8'] = '1'
    (ROOT/'tracking').mkdir(exist_ok=True)
    with (ROOT/'tracking/sync.log').open('a', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, str(ROOT/'tools/sync_youtube_articles.py'), '--publish'], cwd=ROOT, stdout=log, stderr=log)
        if result.returncode == 0:
            result = subprocess.run([sys.executable, str(ROOT/'tools/write_article_report.py')], cwd=ROOT, stdout=log, stderr=log)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
