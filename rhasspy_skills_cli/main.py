import io
import os
import shutil
import stat
import tarfile
import traceback
from pathlib import Path
from re import I
from typing import IO, List, Union
from urllib.parse import urljoin

import git
import httpx
import typer
from git import Repo

from .manifest import Manifest

app = typer.Typer()


def get_skill_by_repo(
    skill_name: str,
    repositories: List[str],
    dest_path: str,
    cache: bool = False,
) -> Union[str, None]:
    #TODO use cache
    dowload_or_update_repo(repositories, dest_path)
    for repo in repositories:
        repo_folder = os.path.join(get_root_repo_folder(), get_repo_name_by_link(repo))
        if any([f == skill_name for f in os.listdir(repo_folder)]):
            return os.path.join(repo_folder, skill_name)
        return None


def get_repo_name_by_link(repo: str) -> str:
    return repo.split("/")[-1].replace(".git", "")


def get_root_repo_folder():
    return os.path.join(typer.get_app_dir("rhasspy_skills"), "repo")


def dowload_or_update_repo(
    repositories: List[str], dest_path: str, cache: bool = False
):
    # TODO use cache
    if not cache:
        clean_repo()
    for repository in repositories:
        repo_folder = os.path.join(dest_path, get_repo_name_by_link(repository))
        r = Repo.clone_from(repository, repo_folder)


def compress_folder(path: str) -> bytes:
    with io.BytesIO() as file:
        with tarfile.open(fileobj=file, mode="w") as tar:
            tar.add(path, arcname="")
        return file.getvalue()


def clean_repo():
    def rem_error(func, path, exc_info):
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)

    root_repo_folder = os.path.join(typer.get_app_dir("rhasspy_skills"), "repo")
    if os.path.isdir(root_repo_folder):
        pass
        shutil.rmtree(root_repo_folder, onerror=rem_error)


def send_archive(
    archive: bytes, file_name: str = "skill.tar", host: str = "http://127.0.0.1:9090"
) -> bool:
    try:
        with httpx.Client(timeout=60) as client:
            res = client.post(
                urljoin(host, "api/skills"),
                files={"file": (file_name, archive, "application/x-tar")},
            )
            if res.status_code != 200:
                typer.echo(f"Request failed: {res.text}")
                # TODO add different code two handle different error
                return False
            return True
    except Exception:
        traceback.print_exc()
        return False


@app.command()
def install(
    path_or_name: str,
    repositories: List[str] = [
        "https://github.com/razzo04/rhasspy-skills-examples.git"
    ],
    cache: bool = False,
):
    p = Path(path_or_name)
    if p.exists():
        if p.is_dir():
            typer.echo("Compressing folder")
            with io.BytesIO() as file:
                with tarfile.open(fileobj=file, mode="w") as tar:
                    tar.add(p, arcname="")
                with open("archive.tar", "wb") as f:
                    f.write(file.getvalue())
                typer.echo("sending request")
                raise typer.Exit(0 if send_archive(file.getvalue(), p.name) else 1)

        if p.is_file():
            if not tarfile.is_tarfile(p):
                typer.echo(f"{path_or_name} is not a tar archive")
                raise typer.Exit(code=1)
            raise typer.Exit(0 if send_archive(p.read_bytes(), p.name) else 1)
    typer.echo(f"Search {path_or_name}")
    skill_path = get_skill_by_repo(
        path_or_name, repositories, get_root_repo_folder(), cache
    )
    if skill_path is not None:
        typer.echo("Skill found installing")
        res = send_archive(compress_folder(skill_path), path_or_name + ".tar")
        if not cache:
            clean_repo()
        raise typer.Exit(0 if res else 1)
    typer.echo(f"Skill {path_or_name} not found")


@app.command()
def uninstall(name: str):
    pass


@app.command()
def create(
    dest_path: Path = typer.Argument("."),
    name: str = typer.Option(None, help="name of new skill"),
    slug: str = typer.Option(None, help="slug of new skill"),
    version: str = typer.Option("0.1.0"),
    description: str = typer.Option(None),
    internet_access: bool = typer.Option(False),
    languages: str = typer.Option(
        "en",
        help="list of languages supported, each languages must be separate by a comma",
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i"),
    template: str = typer.Option("time_skill"),
    template_repository: str = typer.Option(
        "https://github.com/razzo04/rhasspy-skills-examples.git"
    ),
):
    if name is None:
        name = typer.prompt("name of new skill")
    if slug is None:
        slug = typer.prompt("slug of new skill", default=name.lower().replace(" ", "_"))
    if version is None or interactive:
        version = typer.prompt("version of new skill", default="0.1.0")
    if description is None:
        description = typer.prompt(
            "description of new skill", default="Fantastic new skill"
        )
    if internet_access is None or interactive:
        internet_access = typer.confirm(
            "the skill require internet access",
            default=False if internet_access is None else internet_access,
        )
    if languages is None or interactive:
        languages = typer.prompt("list of languages supported", default="en")
    if template is None or interactive:
        template = typer.prompt(
            "chose witch template to use, if you want only generate the manifest you can type none",
            default="time_skill",
        )
    new_skill_path = os.path.join(dest_path, slug)
    if os.path.isdir(new_skill_path):
        shutil.rmtree(new_skill_path)
    else:
        os.makedirs(new_skill_path)
    manifest = Manifest(
        name=name,
        slug=slug,
        version=version,
        description=description,
        internet_access=internet_access,
        languages=languages.split(","),
    )
    if template is not None or template.lower() != "none":
        # download template
        skill_path = get_skill_by_repo(
            template, [template_repository], get_root_repo_folder()
        )
        if skill_path is not None:
            shutil.copytree(skill_path, new_skill_path, dirs_exist_ok=True)
        else:
            typer.echo(f"Template {template} not found")
    with open(os.path.join(new_skill_path, "manifest.json"), "w") as f:
        f.write(manifest.json())


if __name__ == "__main__":
    app()
