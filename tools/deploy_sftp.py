"""Envoie le contenu de public/ sur l'hébergement OVH en SFTP.

Outil de développement local : il n'est pas à envoyer sur l'hébergement.
Nécessite paramiko (py -3 -m pip install paramiko).

  py -3 tools/deploy_sftp.py --list            affiche le contenu distant
  py -3 tools/deploy_sftp.py                   envoie public/ dans www/
  py -3 tools/deploy_sftp.py --dry-run         liste les fichiers locaux à envoyer, sans connexion ni mot de passe

L'hôte et l'utilisateur SFTP sont lus dans les variables d'environnement UMPC_SFTP_HOST et
UMPC_SFTP_USER (à définir une fois : setx UMPC_SFTP_HOST "..." puis setx UMPC_SFTP_USER "...").
Le mot de passe est lu dans UMPC_SFTP_PASSWORD, ou demandé au clavier. Rien de tout cela n'est écrit dans le projet.
"""
import argparse
import getpass
import os
import posixpath
import stat
import sys
from pathlib import Path

import paramiko

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PORT = 22
REMOTE_DIR = "www"
PUBLIC = Path(__file__).resolve().parent.parent / "public"


def connect():
    host, user = os.environ.get("UMPC_SFTP_HOST"), os.environ.get("UMPC_SFTP_USER")
    if not host or not user:
        raise SystemExit("UMPC_SFTP_HOST et UMPC_SFTP_USER doivent être définies (hôte et utilisateur SFTP de l'hébergement OVH, "
                         "voir l'espace client OVH). Exemple : setx UMPC_SFTP_HOST \"ftp.clusterXXX.hosting.ovh.net\", "
                         "puis ouvrir un nouveau terminal.")
    password = os.environ.get("UMPC_SFTP_PASSWORD") or getpass.getpass(f"Mot de passe SFTP de {user} : ")
    transport = paramiko.Transport((host, PORT))
    transport.connect(username=user, password=password)
    return transport, paramiko.SFTPClient.from_transport(transport)


def listing(sftp, path, depth=0, max_depth=1):
    for entry in sorted(sftp.listdir_attr(path), key=lambda e: e.filename):
        is_dir = stat.S_ISDIR(entry.st_mode)
        print(f"{'  ' * depth}{entry.filename}{'/' if is_dir else ''}  {'' if is_dir else f'{entry.st_size} o'}")
        if is_dir and depth < max_depth:
            listing(sftp, posixpath.join(path, entry.filename), depth + 1, max_depth)


def ensure_dir(sftp, path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        sftp.mkdir(path)


def upload(sftp, remote_root):
    ensure_dir(sftp, remote_root)
    count = 0
    for local in sorted(PUBLIC.rglob("*")):
        rel = local.relative_to(PUBLIC).as_posix()
        remote = posixpath.join(remote_root, rel)
        if local.is_dir():
            ensure_dir(sftp, remote)
        else:
            # OVH livre www/index.html sous forme de lien vers sa page « Site en construction ».
            try:
                if stat.S_ISLNK(sftp.lstat(remote).st_mode):
                    sftp.remove(remote)
            except FileNotFoundError:
                pass
            sftp.put(str(local), remote)
            count += 1
            print(f"  {rel}")
    print(f"{count} fichiers envoyés dans {remote_root}/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="afficher le contenu distant sans rien envoyer")
    parser.add_argument("--remote-dir", default=REMOTE_DIR)
    parser.add_argument("--dry-run", action="store_true", help="lister les fichiers à envoyer sans se connecter")
    args = parser.parse_args()

    if args.dry_run:
        files = sorted(p for p in PUBLIC.rglob("*") if p.is_file())
        for p in files:
            print(f"  {p.relative_to(PUBLIC).as_posix()}")
        print(f"{len(files)} fichiers seraient envoyés dans {args.remote_dir}/ (simulation, rien n'est envoyé)")
        return

    transport, sftp = connect()
    try:
        if args.list:
            print(f"Dossier courant : {sftp.normalize('.')}")
            listing(sftp, ".")
        else:
            upload(sftp, args.remote_dir)
    finally:
        sftp.close()
        transport.close()


if __name__ == "__main__":
    main()
