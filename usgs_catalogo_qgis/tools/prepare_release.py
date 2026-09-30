# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Validate public metadata and build a single-folder QGIS ZIP. No upload."""
import argparse
import configparser
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIELDS = ("email", "homepage", "repository", "tracker")
REQUIRED = ("name", "description", "about", "version", "author",
            "qgisMinimumVersion", *PUBLIC_FIELDS, "license")
SUFFIXES = {".py", ".txt", ".md", ".svg", ".png", ".geojson"}


def metadata(root):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(root / "metadata.txt", encoding="utf-8")
    return parser


def release_errors(root, values):
    errors = ["Campo obrigatório ausente: " + key for key in REQUIRED
              if not values.get(key, "").strip()]
    email = values.get("email", "")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors.append("E-mail de contato inválido.")
    for key in ("homepage", "repository", "tracker"):
        value = values.get(key, "")
        if not value:
            continue
        url = urlparse(value)
        host = (url.hostname or "").lower()
        if (url.scheme != "https" or not host or url.username or url.password
                or host in ("localhost", "example.com", "example.org", "example.net")
                or host.endswith((".invalid", ".example"))):
            errors.append("Use um endereço público HTTPS real em " + key + ".")
    for key in ("version", "qgisMinimumVersion", "qgisMaximumVersion"):
        if values.get(key) and not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", values[key]):
            errors.append("Versão inválida em " + key + ".")
    if values.get("license") != "GPL-2.0-or-later":
        errors.append("A licença declarada deve corresponder ao LICENSE e NOTICE.")
    for filename in ("__init__.py", "LICENSE", "NOTICE", "README.md", "icon.png"):
        if not (root / filename).is_file():
            errors.append("Arquivo obrigatório ausente: " + filename)
    if values.get("icon") != "icon.png":
        errors.append("O ícone dos metadados deve apontar para icon.png.")
    return errors


def package_files(root):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError("Não empacote links simbólicos: " + str(relative))
        if path.is_file() and (path.suffix in SUFFIXES or path.name in ("LICENSE", "NOTICE")):
            yield path


def build(root, target):
    target = Path(target)
    if target.suffix.lower() != ".zip":
        raise ValueError("O destino deve terminar em .zip.")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in package_files(root):
                archive.write(path, str(Path(root.name) / path.relative_to(root)))
        if partial.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("O pacote excede 25 MB.")
        with zipfile.ZipFile(partial) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP corrompido.")
        partial.replace(target)
    finally:
        if partial.exists():
            partial.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Somente validar; não altera arquivos")
    parser.add_argument("--configure", action="store_true", help="Salvar metadados válidos no código")
    parser.add_argument("--email")
    parser.add_argument("--repository")
    parser.add_argument("--homepage")
    parser.add_argument("--tracker")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.check and (args.configure or args.output):
        parser.error("--check não pode configurar nem gerar pacote.")
    if not args.configure and any(getattr(args, key) for key in PUBLIC_FIELDS):
        parser.error("Use --configure para gravar os dados reais do autor e do projeto.")
    config = metadata(ROOT)
    values = config["general"]
    for key in PUBLIC_FIELDS:
        value = getattr(args, key)
        if value:
            values[key] = value.strip()
    repository = values.get("repository", "").rstrip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    if repository:
        values["repository"] = repository
    if urlparse(repository).hostname == "github.com":
        if not values.get("homepage"):
            values["homepage"] = repository + "#readme"
        if not values.get("tracker"):
            values["tracker"] = repository + "/issues"
    errors = release_errors(ROOT, values)
    if errors:
        print("Publicação pendente:\n- " + "\n- ".join(errors))
        return 1
    if args.configure:
        with (ROOT / "metadata.txt").open("w", encoding="utf-8") as stream:
            config.write(stream, space_around_delimiters=False)
    if args.output:
        build(ROOT, args.output)
        print("ZIP gerado: " + str(args.output))
    print("Validação local concluída. Verifique os links públicos e teste no QGIS antes do envio.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
