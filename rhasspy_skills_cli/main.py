import io
import json
import os
import shutil
import stat
import sys
import tarfile
import traceback
from pathlib import Path
from re import I
from typing import IO, Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import httpx
import typer
from click.exceptions import Abort
from git import Repo
from pydantic import ValidationError

from .manifest import Manifest

app = typer.Typer()

def ask_prompt_skill_config(manifest: Manifest, default_config: Optional[Dict[str, Any]] = None, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if manifest.schema is None:
        return {}
    if default_config is None:
        default_config = manifest.default_config
    if schema is None:
        schema = manifest.schema_config
    config: Dict[str, Any] = {} 
    for key, value in schema.items():
        if isinstance(value, str):
            config[key] = typer.prompt(f"skill require {key}",default=default_config.get(key, None) if default_config else None)
        elif isinstance(value, list):
            #TODO add support for list
            config[key] = typer.prompt(f"skill require {key}",default=default_config.get(key, None) if default_config else None)
        elif isinstance(value, dict):
            config = {**config, key: ask_prompt_skill_config(manifest, default_config.get(key, None) if default_config else None, schema[key])}
    return config

def generate_skill_config(skill_path: str):
    manifest_path = os.path.join(skill_path, "manifest.json")
    if not os.path.isfile(manifest_path):
        typer.echo("Folder doesn't containt a manifest")
        raise typer.Exit(1)
    try:    
        manifest = Manifest.parse_file(manifest_path)
    except ValidationError as e:
        typer.echo("Invalid manifest.json: " + str(e.errors()))
        raise typer.Exit(1)
    config: Dict[str, Any] = {}
    if manifest.schema_config:
        config = ask_prompt_skill_config(manifest)
    with open(os.path.join(skill_path, "config.json"),"w") as f:
        f.write(json.dumps(config))

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
    archive: bytes, file_name: str = "skill.tar", host: str = "http://127.0.0.1:9090", force: bool = False, star_on_boot: bool = False
) -> bool:
    try:
        with httpx.Client(timeout=60) as client:
            res = client.post(
                urljoin(host, "api/skills"),
                files={"file": (file_name, archive, "application/x-tar")},
                params={"force":force, "start_on_boot":star_on_boot}
            )
            if res.status_code != 200:
                typer.echo(f"Request failed: {res.text}")
                # TODO add different codes to handle different errors
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
    force: bool = typer.Option(False, "--force","-f"),
    start_on_boot: bool = typer.Option(False, "--run-at-startup", "-b")
):
    p = Path(path_or_name)
    if p.exists():
        if p.is_dir():
            generate_skill_config(p.resolve())
            typer.echo("Compressing folder")
            with io.BytesIO() as file:
                with tarfile.open(fileobj=file, mode="w") as tar:
                    tar.add(p, arcname="")
                typer.echo("sending request")
                raise typer.Exit(0 if send_archive(file.getvalue(), p.name, force=force, star_on_boot=start_on_boot) else 1)

        if p.is_file():
            if not tarfile.is_tarfile(p):
                typer.echo(f"{path_or_name} is not a tar archive")
                raise typer.Exit(code=1)
            raise typer.Exit(0 if send_archive(p.read_bytes(), p.name, force=force, star_on_boot=start_on_boot) else 1)
    typer.echo(f"Search {path_or_name}")
    skill_path = get_skill_by_repo(
        path_or_name, repositories, get_root_repo_folder(), cache
    )
    
    if skill_path is not None:
        typer.echo("Skill found")
        generate_skill_config(skill_path)
        res = send_archive(compress_folder(skill_path), path_or_name + ".tar", force=force, star_on_boot=start_on_boot)
        if not cache:
            clean_repo()
        raise typer.Exit(0 if res else 1)
    typer.echo(f"Skill {path_or_name} not found")

@app.command("ls",short_help="show installed skill")
def list_skill(host: str = typer.Option("http://127.0.0.1:9090")):
    with httpx.Client() as client:
        res = client.get(urljoin(host, f"api/skills"))
        skills = res.json()
        if len(skills) == 0:
            typer.echo("no skill installed")
        for skill in skills:
            typer.echo(skill["skill_name"])

@app.command()
def uninstall(name: str, force: bool = typer.Option(False, "--force","-f"), host: str = typer.Option("http://127.0.0.1:9090")):
    with httpx.Client(timeout=20) as client:
        res = client.delete(urljoin(host, f"api/skills/{name}"), params={"force":force})
        if res.status_code != 200:
            typer.echo(f"Request failed: {res.text}")
        else:
            typer.echo(f"Response: {res.text}")

@app.command()
def start(name: str, host: str = typer.Option("http://127.0.0.1:9090")):
    with httpx.Client(timeout=20) as client:
        res = client.post(urljoin(host, f"api/skills/{name}/start"))
        if res.status_code != 200:
            typer.echo(f"Request failed: {res.text}")
        else:
            typer.echo(f"Response: {res.text}")

@app.command()
def stop(name: str, force: bool = typer.Option(False, "--force","-f"), host: str = typer.Option("http://127.0.0.1:9090")):
    with httpx.Client(timeout=20) as client:
        res = client.post(urljoin(host, f"api/skills/{name}/stop"), params={"force":force})
        if res.status_code != 200:
            typer.echo(f"Request failed: {res.text}")
        else:
            typer.echo(f"Response: {res.text}")


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
        slug = typer.prompt("slug of new skill", default=name.strip().lower().replace(" ", "_"))
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
    schema = {}
    default_config = {}
    if interactive:
        r = typer.confirm("Your skill need options?")
        if r:
            typer.echo("You can stop adding new option with CTRL+C")
            try:
                while True:
                    name = typer.prompt("name of new option")
                    name = name.strip().lower().replace(" ","_")
                    default = typer.prompt(f"default value for {name}", default=None)
                    schema[name] = "str"
                    if default is not None: default_config[name] = default
            except Abort:
                pass
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
        default_config=default_config,
        schema_config=schema
    )
    if template is not None or template.lower() != "none":
        # download template
        skill_path = get_skill_by_repo(
            template, [template_repository], get_root_repo_folder()
        )
        if skill_path is not None:
            if sys.version_info >= (3,8):
                shutil.copytree(skill_path, new_skill_path, dirs_exist_ok=True)
            else:
                if os.path.isdir(new_skill_path):
                    shutil.rmtree(new_skill_path)
                shutil.copytree(skill_path, new_skill_path)
                
        else:
            typer.echo(f"Template {template} not found")
    with open(os.path.join(new_skill_path, "manifest.json"), "w") as f:
        f.write(manifest.json())


if __name__ == "__main__":
    app()
